"""Turns job events into notifications for matching saved-search subscriptions.

Guarantees:
* baseline events (first crawl of a source) are never notified;
* events older than a subscription are never notified to it;
* one delivery per (user, channel, event) and per (user, channel, digest day)
  enforced by unique constraints - re-running the dispatcher cannot duplicate;
* per-user hourly cap; failed sends are retried with backoff, permanent
  failures (bot blocked, bad address) stop.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import settings_store
from app.config import get_settings
from app.filters import JobFilters, apply_filters
from app.models import (
    Job,
    JobEvent,
    NotificationDelivery,
    NotificationSubscription,
    SavedSearch,
    TelegramConnection,
    User,
)
from app.notifications import emailer, telegram_send
from app.pipeline import taxonomy as tx
from app.pipeline.matching import match

log = structlog.get_logger()

MAX_ATTEMPTS = 5
EVENT_LABELS_FA = {
    "NEW_JOB": "آگهی جدید",
    "SALARY_CHANGED": "تغییر حقوق",
    "DESCRIPTION_CHANGED": "تغییر شرح شغل",
    "REQUIREMENTS_CHANGED": "تغییر شرایط و مهارت‌ها",
    "WORK_MODE_CHANGED": "تغییر شیوه همکاری",
    "JOB_EXPIRED": "آگهی منقضی شد",
    "JOB_REOPENED": "آگهی دوباره فعال شد",
}
SALARY_LABELS = {"reported": "اعلام‌شده", "estimated": "تخمینی", "unknown": "نامشخص"}
WORK_MODE_FA = {"onsite": "حضوری", "hybrid": "هیبریدی", "remote": "دورکاری"}


def _now() -> datetime:
    return datetime.now(UTC)


def fmt_toman(v: int | None) -> str:
    if not v:
        return "-"
    if v >= 1_000_000:
        return f"{v / 1_000_000:,.0f} میلیون تومان"
    return f"{v:,} تومان"


def salary_text(job: Job) -> str:
    est = job.salary_estimate or {}
    if job.salary_status == "reported":
        return job.salary_original or f"{fmt_toman(est.get('min'))} تا {fmt_toman(est.get('max'))}"
    if job.salary_status == "estimated":
        return (f"{fmt_toman(est.get('min'))} تا {fmt_toman(est.get('max'))} "
                f"(روش: {est.get('method')}، منبع: {est.get('source')}، اطمینان: {est.get('confidence')})")
    return "داده کافی برای تخمین نیست (نبودن حقوق به معنای پایین بودن آن نیست)"


def describe_changes(event: JobEvent) -> list[str]:
    d = event.diff or {}
    out = []
    if event.event_type == "SALARY_CHANGED":
        o, n = (d.get("salary_original") or {}).get("old"), (d.get("salary_original") or {}).get("new")
        out.append(f"حقوق: «{o or '-'}» ← «{n or '-'}»")
    elif event.event_type == "REQUIREMENTS_CHANGED":
        rs = d.get("required_skills") or {}
        if rs.get("added"):
            out.append("مهارت‌های اضافه‌شده: " + ", ".join(rs["added"]))
        if rs.get("removed"):
            out.append("مهارت‌های حذف‌شده: " + ", ".join(rs["removed"]))
        ex = d.get("experience_required") or {}
        if ex.get("old") != ex.get("new"):
            out.append(f"سابقه: «{ex.get('old') or '-'}» ← «{ex.get('new') or '-'}»")
    elif event.event_type == "WORK_MODE_CHANGED":
        wm = d.get("work_mode") or {}
        out.append(f"شیوه همکاری: {WORK_MODE_FA.get(wm.get('old'), '-')} ← {WORK_MODE_FA.get(wm.get('new'), '-')}")
    elif event.event_type == "DESCRIPTION_CHANGED":
        out.append(f"شرح شغل تغییر کرد (شباهت با نسخه قبل: {round((d.get('similarity') or 0) * 100)}٪)")
    return out


def job_item(job: Job, event: JobEvent, match_score: int | None) -> dict:
    base = get_settings().public_base_url.rstrip("/")
    cats = "، ".join(tx.CATEGORY_LABELS_FA.get(c.category, c.category) + (f" / {c.subcategory}" if c.subcategory else "")
                     for c in sorted(job.categories, key=lambda c: not c.is_primary)) or "-"
    return {
        "event_type": event.event_type,
        "event_label": EVENT_LABELS_FA.get(event.event_type, event.event_type),
        "title": job.title,
        "company": job.company_name,
        "location": " / ".join(x for x in (job.province, job.city) if x) + (f" · {WORK_MODE_FA[job.work_mode]}" if job.work_mode in WORK_MODE_FA else ""),
        "categories": cats,
        "salary_label": SALARY_LABELS.get(job.salary_status, "نامشخص"),
        "salary_text": salary_text(job),
        "summary": _summary(job),
        "changes": describe_changes(event),
        "match_score": match_score,
        "source_url": job.canonical_url,
        "dashboard_url": f"{base}/jobs/{job.id}",
    }


def _summary(job: Job) -> str | None:
    from sqlalchemy.orm import object_session

    from app.models import JobAnalysis
    db = object_session(job)
    if db is None:
        return None
    row = db.scalar(select(JobAnalysis.result).where(JobAnalysis.job_id == job.id, JobAnalysis.is_current))
    return (row or {}).get("summary_fa") if row else None


def channel_ready(db: Session, user: User, channel: str) -> bool:
    if not user.is_active:
        return False
    if channel == "email":
        return bool(user.notify_email and user.notify_email_verified_at)
    if channel == "telegram":
        return db.scalar(select(func.count()).select_from(TelegramConnection).where(
            TelegramConnection.user_id == user.id, TelegramConnection.status == "active")) > 0
    return False


def subscription_matches(db: Session, sub: NotificationSubscription, job: Job, event: JobEvent, user: User) -> tuple[bool, int | None]:
    if event.event_type not in (sub.event_types or []):
        return False, None
    if event.created_at < sub.created_at:
        return False, None
    if sub.categories and not ({c.category for c in job.categories} & set(sub.categories)):
        return False, None
    if sub.saved_search_id:
        ss = db.get(SavedSearch, sub.saved_search_id)
        if ss is None:
            return False, None
        f = JobFilters(**(ss.filters or {}))
        if event.event_type == "JOB_EXPIRED":
            f.status = ["active", "expired"]
        hit = db.scalar(apply_filters(select(func.count()).select_from(Job).where(Job.id == job.id), f))
        if not hit:
            return False, None
    score = None
    if sub.min_match_score is not None or (user.profile or {}).get("skills"):
        score = match(user.profile or {}, job)["match_score"]
        if sub.min_match_score is not None and score < sub.min_match_score:
            return False, score
    return True, score


def _rate_limited(db: Session, user_id: int) -> bool:
    cap = int(settings_store.get(db, "notify.max_per_user_per_hour") or 30)
    n = db.scalar(select(func.count()).select_from(NotificationDelivery).where(
        NotificationDelivery.user_id == user_id, NotificationDelivery.status == "sent",
        NotificationDelivery.sent_at >= _now() - timedelta(hours=1)))
    return n >= cap


def _create_delivery(db: Session, *, user_id: int, sub_id: int, channel: str, event_id: int | None = None,
                     digest_key: str | None = None, payload: dict) -> NotificationDelivery | None:
    stmt = insert(NotificationDelivery).values(
        user_id=user_id, subscription_id=sub_id, channel=channel, job_event_id=event_id, digest_key=digest_key,
        status="pending", attempts=0, payload=payload,
    ).on_conflict_do_nothing().returning(NotificationDelivery.id)
    new_id = db.execute(stmt).scalar()
    return db.get(NotificationDelivery, new_id) if new_id else None


def _unsubscribe_url(sub: NotificationSubscription) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/api/v1/notifications/unsubscribe/{sub.unsubscribe_token}"


def send_delivery(db: Session, d: NotificationDelivery) -> None:
    user = db.get(User, d.user_id)
    sub = db.get(NotificationSubscription, d.subscription_id) if d.subscription_id else None
    items = d.payload.get("items", [])
    d.attempts += 1
    try:
        if d.channel == "email":
            settings_url = f"{get_settings().public_base_url.rstrip('/')}/alerts"
            if d.digest_key:
                subject = f"گزارش روزانه فرصت‌های شغلی - {len(items)} مورد"
                html = emailer.render("digest.html", subject=subject, items=items, date_label=d.payload.get("date_label", ""),
                                      truncated=d.payload.get("truncated"), unsubscribe_url=_unsubscribe_url(sub) if sub else None,
                                      settings_url=settings_url)
            else:
                it = items[0]
                subject = f"{it['event_label']}: {it['title']}" + (f" - {it['company']}" if it.get("company") else "")
                html = emailer.render("job_alert.html", subject=subject, items=items, intro="یک مورد مطابق هشدار شما:",
                                      unsubscribe_url=_unsubscribe_url(sub) if sub else None, settings_url=settings_url)
            text = "\n\n".join(f"{i['event_label']}: {i['title']} - {i.get('company') or ''}\n{i['source_url']}\n{i['dashboard_url']}" for i in items)
            headers = {"List-Unsubscribe": f"<{_unsubscribe_url(sub)}>"} if sub else None
            emailer.send_email(db, user.notify_email, subject, html, text, headers)
        elif d.channel == "telegram":
            conn = db.scalar(select(TelegramConnection).where(TelegramConnection.user_id == d.user_id,
                                                              TelegramConnection.status == "active"))
            if conn is None:
                raise telegram_send.TelegramSendError("telegram not connected", permanent=True)
            for it in items[:10]:
                e = telegram_send.esc
                lines = [f"<b>{e(it['event_label'])}</b>", f"<b>{e(it['title'])}</b>",
                         e(it.get("company") or "شرکت نامشخص") + (f" · {e(it['location'])}" if it.get("location") else ""),
                         f"دسته: {e(it['categories'])}", f"حقوق ({e(it['salary_label'])}): {e(it['salary_text'])}"]
                if it.get("match_score") is not None:
                    lines.append(f"تطابق: {it['match_score']}٪")
                lines += [e(c) for c in it.get("changes") or []]
                if it.get("summary"):
                    lines.append(f"<i>{e(it['summary'])}</i>")
                telegram_send.send_message(conn.chat_id, "\n".join(lines),
                                           [("مشاهده آگهی اصلی", it["source_url"]), ("تحلیل در داشبورد", it["dashboard_url"])])
        d.status = "sent"
        d.sent_at = _now()
        d.last_error = None
    except (emailer.EmailNotConfigured, telegram_send.TelegramNotConfigured) as exc:
        d.status = "failed"
        d.last_error = str(exc)
    except telegram_send.TelegramSendError as exc:
        d.last_error = str(exc)
        d.status = "failed" if exc.permanent or d.attempts >= MAX_ATTEMPTS else "pending"
    except Exception as exc:  # SMTP errors etc. - retried
        d.last_error = f"{type(exc).__name__}: {exc}"[:500]
        d.status = "failed" if d.attempts >= MAX_ATTEMPTS else "pending"
    db.commit()


def _event_cursor(db: Session) -> int:
    return int(settings_store.get(db, "notify.event_cursor") or 0)


def dispatch_instant(db: Session, batch: int = 500) -> dict:
    cursor = _event_cursor(db)
    events = db.scalars(select(JobEvent).where(JobEvent.id > cursor).order_by(JobEvent.id).limit(batch)).all()
    if not events:
        return {"events": 0, "deliveries": 0}
    subs = db.scalars(select(NotificationSubscription).where(
        NotificationSubscription.active, NotificationSubscription.frequency == "instant")).all()
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({s.user_id for s in subs})))} if subs else {}
    created = 0
    for ev in events:
        if ev.is_baseline:
            continue
        job = db.get(Job, ev.job_id)
        if job is None:
            continue
        for sub in subs:
            user = users.get(sub.user_id)
            if user is None or not channel_ready(db, user, sub.channel):
                continue
            ok, score = subscription_matches(db, sub, job, ev, user)
            if not ok:
                continue
            d = _create_delivery(db, user_id=user.id, sub_id=sub.id, channel=sub.channel, event_id=ev.id,
                                 payload={"items": [job_item(job, ev, score)]})
            if d is None:
                continue  # already delivered via another subscription
            created += 1
            if _rate_limited(db, user.id):
                d.status, d.last_error = "skipped", "rate limited (per-user hourly cap)"
                db.commit()
                continue
            db.commit()
            send_delivery(db, d)
    settings_store.set_value(db, "notify.event_cursor", events[-1].id)
    db.commit()
    return {"events": len(events), "deliveries": created}


def dispatch_digest(db: Session, day: datetime | None = None, max_items: int = 30) -> dict:
    day = day or _now()
    key = f"daily:{day.date().isoformat()}"
    since = day - timedelta(hours=24)
    subs = db.scalars(select(NotificationSubscription).where(
        NotificationSubscription.active, NotificationSubscription.frequency == "daily")).all()
    events = db.scalars(select(JobEvent).where(JobEvent.created_at >= since, JobEvent.created_at <= day,
                                               JobEvent.is_baseline.is_(False)).order_by(JobEvent.id)).all()
    per_target: dict[tuple[int, str], tuple[NotificationSubscription, dict[int, dict]]] = {}
    for sub in subs:
        user = db.get(User, sub.user_id)
        if user is None or not channel_ready(db, user, sub.channel):
            continue
        for ev in events:
            job = db.get(Job, ev.job_id)
            if job is None:
                continue
            ok, score = subscription_matches(db, sub, job, ev, user)
            if ok:
                bucket = per_target.setdefault((user.id, sub.channel), (sub, {}))[1]
                bucket.setdefault(ev.id, job_item(job, ev, score))
    sent = 0
    for (user_id, channel), (sub, items) in per_target.items():
        vals = list(items.values())
        payload = {"items": vals[:max_items], "truncated": len(vals) > max_items, "date_label": day.date().isoformat()}
        d = _create_delivery(db, user_id=user_id, sub_id=sub.id, channel=channel, digest_key=key, payload=payload)
        db.commit()
        if d is not None:
            send_delivery(db, d)
            sent += 1
    return {"digests": sent}


def retry_pending(db: Session) -> int:
    """Resend deliveries that failed transiently, with exponential backoff on attempts."""
    rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.status == "pending",
                                                         NotificationDelivery.attempts > 0)).all()
    n = 0
    for d in rows:
        wait = timedelta(minutes=2 ** d.attempts)
        if (d.sent_at or d.created_at) + wait > _now():
            continue
        send_delivery(db, d)
        n += 1
    return n
