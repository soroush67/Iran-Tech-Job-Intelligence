from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import audit, current_user, rate_limit
from app.config import get_settings
from app.db import get_db
from app.filters import JobFilters
from app.models import EVENT_TYPES, NotificationDelivery, NotificationSubscription, SavedSearch, TelegramConnection, User
from app.notifications import emailer, telegram_send
from app.security import new_token, token_hash

router = APIRouter(tags=["alerts"])

VERIFY_HOURS = 24


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    filters: JobFilters


def ss_out(s: SavedSearch, subs: list[NotificationSubscription]) -> dict:
    return {"id": s.id, "name": s.name, "filters": s.filters, "created_at": s.created_at, "updated_at": s.updated_at,
            "subscriptions": [sub_out(x) for x in subs if x.saved_search_id == s.id]}


def sub_out(x: NotificationSubscription) -> dict:
    return {"id": x.id, "saved_search_id": x.saved_search_id, "channel": x.channel, "event_types": x.event_types,
            "frequency": x.frequency, "categories": x.categories, "min_match_score": x.min_match_score,
            "active": x.active, "created_at": x.created_at}


@router.get("/saved-searches")
def list_saved(db: Session = Depends(get_db), user: User = Depends(current_user)):
    searches = db.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.created_at)).all()
    subs = db.scalars(select(NotificationSubscription).where(NotificationSubscription.user_id == user.id)).all()
    return {"items": [ss_out(s, subs) for s in searches],
            "unattached_subscriptions": [sub_out(x) for x in subs if x.saved_search_id is None]}


@router.post("/saved-searches", status_code=201)
def create_saved(body: SavedSearchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if db.scalar(select(SavedSearch).where(SavedSearch.user_id == user.id, SavedSearch.name == body.name)):
        raise HTTPException(409, "a saved search with this name exists")
    if len(db.scalars(select(SavedSearch.id).where(SavedSearch.user_id == user.id)).all()) >= 50:
        raise HTTPException(400, "limit of 50 saved searches reached")
    s = SavedSearch(user_id=user.id, name=body.name, filters=body.filters.model_dump(mode="json", exclude_defaults=True))
    db.add(s)
    db.commit()
    return ss_out(s, [])


def _own_search(db: Session, user: User, sid: int) -> SavedSearch:
    s = db.get(SavedSearch, sid)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "saved search not found")
    return s


@router.put("/saved-searches/{sid}")
def update_saved(sid: int, body: SavedSearchIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = _own_search(db, user, sid)
    s.name = body.name
    s.filters = body.filters.model_dump(mode="json", exclude_defaults=True)
    db.commit()
    return ss_out(s, db.scalars(select(NotificationSubscription).where(NotificationSubscription.saved_search_id == s.id)).all())


@router.delete("/saved-searches/{sid}")
def delete_saved(sid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_own_search(db, user, sid))
    db.commit()
    return {"ok": True}


class SubscriptionIn(BaseModel):
    saved_search_id: int | None = None
    channel: Literal["email", "telegram"]
    event_types: list[Literal[EVENT_TYPES]] = Field(default_factory=lambda: ["NEW_JOB"], min_length=1)  # type: ignore[valid-type]
    frequency: Literal["instant", "daily"] = "instant"
    categories: list[Literal["devops", "sre", "python", "ai_ml", "mlops_data"]] = Field(default_factory=list)
    min_match_score: int | None = Field(default=None, ge=0, le=100)
    active: bool = True


@router.post("/subscriptions", status_code=201)
def create_subscription(body: SubscriptionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.saved_search_id is not None:
        _own_search(db, user, body.saved_search_id)
    x = NotificationSubscription(user_id=user.id, unsubscribe_token=new_token(24), **body.model_dump())
    db.add(x)
    db.commit()
    return sub_out(x)


def _own_sub(db: Session, user: User, sub_id: int) -> NotificationSubscription:
    x = db.get(NotificationSubscription, sub_id)
    if x is None or x.user_id != user.id:
        raise HTTPException(404, "subscription not found")
    return x


@router.put("/subscriptions/{sub_id}")
def update_subscription(sub_id: int, body: SubscriptionIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    x = _own_sub(db, user, sub_id)
    if body.saved_search_id is not None:
        _own_search(db, user, body.saved_search_id)
    for k, v in body.model_dump().items():
        setattr(x, k, v)
    db.commit()
    return sub_out(x)


@router.delete("/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    db.delete(_own_sub(db, user, sub_id))
    db.commit()
    return {"ok": True}


@router.get("/notifications/deliveries")
def my_deliveries(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(NotificationDelivery).where(NotificationDelivery.user_id == user.id)
                      .order_by(NotificationDelivery.created_at.desc()).limit(100)).all()
    return {"items": [{"id": d.id, "channel": d.channel, "status": d.status, "attempts": d.attempts,
                       "last_error": d.last_error, "created_at": d.created_at, "sent_at": d.sent_at,
                       "digest_key": d.digest_key,
                       "title": ((d.payload or {}).get("items") or [{}])[0].get("title")} for d in rows]}


# ---- e-mail address & verification ---------------------------------------------------

class EmailIn(BaseModel):
    email: EmailStr


@router.post("/notifications/email", dependencies=[Depends(rate_limit("email_verify", 5, 3600))])
def set_notify_email(body: EmailIn, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    token = new_token(32)
    user.notify_email = body.email.lower()
    user.notify_email_verified_at = None
    user.notify_email_token_hash = token_hash(token)
    user.notify_email_token_expires_at = datetime.now(UTC) + timedelta(hours=VERIFY_HOURS)
    audit(db, request, user, "notify.email_set", user.notify_email)
    db.commit()
    url = f"{get_settings().public_base_url.rstrip('/')}/api/v1/notifications/email/verify/{token}"
    try:
        html = emailer.render("verify.html", subject="تأیید نشانی ایمیل", verify_url=url, hours=VERIFY_HOURS)
        emailer.send_email(db, user.notify_email, "تأیید نشانی ایمیل - Iran Tech Job Intelligence", html,
                           f"برای تأیید این نشانی باز کنید:\n{url}")
    except emailer.EmailNotConfigured as exc:
        raise HTTPException(503, f"email is not configured on the server: {exc}") from None
    except Exception as exc:
        raise HTTPException(502, f"could not send the verification email: {type(exc).__name__}") from None
    return {"ok": True, "message": "verification link sent"}


def _page(title: str, body: str) -> HTMLResponse:
    base = get_settings().public_base_url.rstrip("/")
    return HTMLResponse(f"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title></head>
<body style="font-family:Tahoma,sans-serif;background:#f3f4f6;padding:40px 16px;text-align:center">
<div style="max-width:420px;margin:auto;background:#fff;border-radius:12px;padding:24px">
<h2>{title}</h2><p>{body}</p><p><a href="{base}/settings">بازگشت به تنظیمات</a></p></div></body></html>""")


@router.get("/notifications/email/verify/{token}", include_in_schema=False)
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.notify_email_token_hash == token_hash(token)))
    if user is None or not user.notify_email_token_expires_at or user.notify_email_token_expires_at < datetime.now(UTC):
        return _page("لینک نامعتبر است", "این لینک منقضی شده یا قبلاً استفاده شده است.")
    user.notify_email_verified_at = datetime.now(UTC)
    user.notify_email_token_hash = None
    db.commit()
    return _page("ایمیل تأیید شد", "از این پس اعلان‌های فعال شما به این نشانی ارسال می‌شود.")


@router.get("/notifications/unsubscribe/{token}", include_in_schema=False)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    sub = db.scalar(select(NotificationSubscription).where(NotificationSubscription.unsubscribe_token == token))
    if sub is None:
        return _page("لینک نامعتبر است", "این هشدار پیدا نشد.")
    sub.active = False
    db.commit()
    return _page("لغو شد", "این هشدار غیرفعال شد. می‌توانید دوباره از صفحه هشدارها فعالش کنید.")


@router.post("/notifications/unsubscribe/{token}", include_in_schema=False)
def unsubscribe_one_click(token: str, db: Session = Depends(get_db)):
    """RFC 8058 List-Unsubscribe-Post."""
    sub = db.scalar(select(NotificationSubscription).where(NotificationSubscription.unsubscribe_token == token))
    if sub is not None:
        sub.active = False
        db.commit()
    return {"ok": True}


class TestIn(BaseModel):
    channel: Literal["email", "telegram"]


@router.post("/notifications/test", dependencies=[Depends(rate_limit("notify_test", 5, 600))])
def test_notification(body: TestIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if body.channel == "email":
        if not user.notify_email or not user.notify_email_verified_at:
            raise HTTPException(400, "set and verify a notification email first")
        try:
            html = emailer.render("test.html", subject="ایمیل آزمایشی", sent_at=now)
            emailer.send_email(db, user.notify_email, "ایمیل آزمایشی - Iran Tech Job Intelligence", html,
                               f"ایمیل آزمایشی - {now}")
        except emailer.EmailNotConfigured as exc:
            raise HTTPException(503, str(exc)) from None
        except Exception as exc:
            raise HTTPException(502, f"SMTP error: {type(exc).__name__}: {str(exc)[:200]}") from None
        return {"ok": True, "sent_to": user.notify_email}
    conn = db.scalar(select(TelegramConnection).where(TelegramConnection.user_id == user.id,
                                                      TelegramConnection.status == "active"))
    if conn is None:
        raise HTTPException(400, "connect Telegram first")
    try:
        telegram_send.send_message(conn.chat_id, f"✅ پیام آزمایشی Iran Tech Job Intelligence\n{now}")
    except telegram_send.TelegramNotConfigured as exc:
        raise HTTPException(503, str(exc)) from None
    except telegram_send.TelegramSendError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"ok": True}
