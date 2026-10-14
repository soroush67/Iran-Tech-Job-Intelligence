"""4. No duplicate notifications, 9. SMTP sending in the test environment."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import JobEvent, NotificationDelivery, NotificationSubscription, SavedSearch, User
from app.notifications.dispatcher import dispatch_digest, dispatch_instant
from app.security import new_token
from tests.fixtures import pages
from tests.helpers import jobinja_raw, put


def make_user(db, email="alert@example.com", verified=True, profile=None):
    u = User(email=email, password_hash="x", role="user", profile=profile or {},
             notify_email=email, notify_email_verified_at=datetime.now(UTC) if verified else None)
    db.add(u)
    db.commit()
    return u


def subscribe(db, user, *, filters=None, frequency="instant", events=("NEW_JOB",), categories=(), min_match=None,
              created_at=None):
    ss = None
    if filters is not None:
        ss = SavedSearch(user_id=user.id, name=f"s{new_token(4)}", filters=filters)
        db.add(ss)
        db.flush()
    sub = NotificationSubscription(user_id=user.id, saved_search_id=ss.id if ss else None, channel="email",
                                   event_types=list(events), frequency=frequency, categories=list(categories),
                                   min_match_score=min_match, unsubscribe_token=new_token(16))
    if created_at:
        sub.created_at = created_at
    db.add(sub)
    db.commit()
    return sub


def deliveries(db):
    return db.scalar(select(func.count()).select_from(NotificationDelivery))


def test_new_job_email_sent_once(db, smtp_server):
    u = make_user(db)
    subscribe(db, u, filters={"categories": ["devops"]})
    subscribe(db, u, categories=["devops"])  # second matching subscription, same channel
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    r1 = dispatch_instant(db)
    r2 = dispatch_instant(db)  # re-run: nothing new
    assert r1["deliveries"] == 1 and r2["events"] == 0
    assert deliveries(db) == 1
    assert len(smtp_server.messages) == 1
    msg = smtp_server.messages[0]["data"]
    assert "List-Unsubscribe" in msg and "text/html" in msg
    d = db.scalar(select(NotificationDelivery))
    assert d.status == "sent"


def test_dispatch_cursor_reset_cannot_duplicate(db, smtp_server):
    from app import settings_store
    u = make_user(db)
    subscribe(db, u)
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    dispatch_instant(db)
    settings_store.set_value(db, "notify.event_cursor", 0)  # simulate a replay
    db.commit()
    dispatch_instant(db)
    assert deliveries(db) == 1 and len(smtp_server.messages) == 1


def test_baseline_events_never_notified(db, smtp_server):
    u = make_user(db)
    subscribe(db, u)
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION), baseline=True)
    dispatch_instant(db)
    assert deliveries(db) == 0 and smtp_server.messages == []


def test_events_older_than_subscription_not_notified(db, smtp_server):
    u = make_user(db)
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    subscribe(db, u, created_at=datetime.now(UTC) + timedelta(minutes=1))
    dispatch_instant(db)
    assert deliveries(db) == 0


def test_filters_events_and_match_threshold(db, smtp_server):
    u = make_user(db, profile={"skills": ["Excel"]})
    subscribe(db, u, filters={"categories": ["python"]})  # wrong category
    subscribe(db, u, events=("SALARY_CHANGED",))  # wrong event type
    subscribe(db, u, min_match=90)  # profile does not match a DevOps ad
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    dispatch_instant(db)
    assert deliveries(db) == 0


def test_unverified_email_gets_nothing(db, smtp_server):
    u = make_user(db, verified=False)
    subscribe(db, u)
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    dispatch_instant(db)
    assert deliveries(db) == 0


def test_change_event_notification_contains_diff(db, smtp_server):
    u = make_user(db)
    subscribe(db, u, events=("SALARY_CHANGED",))
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION, salary="توافقی"))
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION, salary="40 - 60 میلیون تومان"))
    dispatch_instant(db)
    assert len(smtp_server.messages) == 1
    import email
    msg = email.message_from_string(smtp_server.messages[0]["data"])
    html = next(p.get_payload(decode=True).decode() for p in msg.walk() if p.get_content_type() == "text/html")
    assert 'dir="rtl"' in html and "تغییر حقوق" in html and "40 - 60" in html


def test_daily_digest_one_per_day(db, smtp_server):
    u = make_user(db)
    subscribe(db, u, frequency="daily")
    put(db, "jobinja", jobinja_raw(code="d1", description_html=pages.DEVOPS_DESCRIPTION))
    put(db, "jobinja", jobinja_raw(code="d2", title="Site Reliability Engineer", description_html=pages.DEVOPS_DESCRIPTION))
    now = datetime.now(UTC) + timedelta(seconds=1)
    assert dispatch_digest(db, now)["digests"] == 1
    assert dispatch_digest(db, now)["digests"] == 0
    d = db.scalar(select(NotificationDelivery))
    assert len(d.payload["items"]) == 2 and d.status == "sent"


def test_smtp_failure_is_retried_not_lost(db):
    from app import settings_store
    u = make_user(db)
    subscribe(db, u)
    settings_store.set_value(db, "smtp.host", "127.0.0.1")
    settings_store.set_value(db, "smtp.port", 1)  # nothing listens there
    settings_store.set_value(db, "smtp.from", "a@example.com")
    settings_store.set_value(db, "smtp.starttls", False)
    db.commit()
    put(db, "jobinja", jobinja_raw(description_html=pages.DEVOPS_DESCRIPTION))
    dispatch_instant(db)
    d = db.scalar(select(NotificationDelivery))
    assert d.status == "pending" and d.attempts == 1 and d.last_error


def test_unsubscribe_link(client, db):
    u = make_user(db)
    sub = subscribe(db, u)
    r = client.get(f"/api/v1/notifications/unsubscribe/{sub.unsubscribe_token}")
    assert r.status_code == 200 and "لغو" in r.text
    db.refresh(sub)
    assert sub.active is False
    assert db.scalar(select(func.count()).select_from(JobEvent)) == 0
