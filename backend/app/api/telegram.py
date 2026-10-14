from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import _set_cookie
from app.api.deps import audit, current_user, rate_limit
from app.config import get_settings
from app.db import get_db
from app.models import TelegramConnection, User
from app.security import create_access_token
from app.telegram_auth import InitDataError, issue_link_code, validate_init_data

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/connect", dependencies=[Depends(rate_limit("tg_connect", 10, 600))])
def connect(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_bot_username:
        raise HTTPException(503, "Telegram bot is not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_BOT_USERNAME)")
    code = issue_link_code(db, user.id)
    audit(db, request, user, "telegram.link_code_issued")
    db.commit()
    return {"deep_link": f"https://t.me/{s.telegram_bot_username}?start={code}", "expires_in_seconds": 600,
            "manual": f"/start {code}"}


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(current_user)):
    conn = db.scalar(select(TelegramConnection).where(TelegramConnection.user_id == user.id))
    s = get_settings()
    return {"bot_configured": bool(s.telegram_bot_token and s.telegram_bot_username),
            "bot_username": s.telegram_bot_username or None,
            "status": conn.status if conn else "none", "username": conn.username if conn else None,
            "connected_at": conn.connected_at if conn else None}


@router.delete("/connect")
def disconnect(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    conn = db.scalar(select(TelegramConnection).where(TelegramConnection.user_id == user.id))
    if conn:
        conn.status, conn.chat_id, conn.telegram_user_id, conn.code_hash = "revoked", None, None, None
        audit(db, request, user, "telegram.disconnected")
        db.commit()
    return {"ok": True}


class InitDataIn(BaseModel):
    init_data: str = Field(min_length=10, max_length=8192)


@router.post("/webapp/auth", dependencies=[Depends(rate_limit("tg_webapp", 30, 60))])
def webapp_auth(body: InitDataIn, response: Response, db: Session = Depends(get_db)):
    """Telegram Mini App login: validated initData of a *linked* Telegram account -> session."""
    try:
        data = validate_init_data(body.init_data, get_settings().telegram_bot_token)
    except InitDataError as exc:
        raise HTTPException(401, f"invalid initData: {exc}") from None
    conn = db.scalar(select(TelegramConnection).where(TelegramConnection.telegram_user_id == int(data["user"]["id"]),
                                                      TelegramConnection.status == "active"))
    if conn is None:
        raise HTTPException(403, "this Telegram account is not linked; open the website settings and connect Telegram")
    user = db.get(User, conn.user_id)
    if user is None or not user.is_active:
        raise HTTPException(403, "account disabled")
    token = create_access_token(user.id, user.role, minutes=120)
    _set_cookie(response, token)
    return {"ok": True, "user": {"id": user.id, "display_name": user.display_name, "email": user.email}}
