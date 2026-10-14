from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import COOKIE_NAME, audit, current_user, rate_limit
from app.config import get_settings
from app.db import get_db
from app.models import TelegramConnection, User
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RegisterIn(Credentials):
    display_name: str | None = Field(default=None, max_length=120)


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    skills: list[str] = Field(default_factory=list, max_length=100)
    preferred_skills: list[str] = Field(default_factory=list, max_length=100)
    years_experience: float | None = Field(default=None, ge=0, le=60)
    cities: list[str] = Field(default_factory=list, max_length=30)
    work_modes: list[str] = Field(default_factory=list, max_length=3)


def user_out(db: Session, u: User) -> dict:
    tg = db.scalar(select(TelegramConnection).where(TelegramConnection.user_id == u.id))
    return {
        "id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role,
        "profile": u.profile or {}, "notify_email": u.notify_email,
        "notify_email_verified": bool(u.notify_email_verified_at),
        "telegram": {"status": tg.status, "username": tg.username} if tg and tg.status == "active" else None,
        "created_at": u.created_at,
    }


def _set_cookie(resp: Response, token: str) -> None:
    secure = get_settings().public_base_url.startswith("https")
    resp.set_cookie(COOKIE_NAME, token, httponly=True, secure=secure, samesite="lax",
                    max_age=get_settings().access_token_minutes * 60, path="/")


@router.post("/register", dependencies=[Depends(rate_limit("register", 5, 3600))])
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    if not get_settings().allow_registration:
        raise HTTPException(403, "registration is disabled")
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "email already registered")
    user = User(email=email, password_hash=hash_password(body.password), display_name=body.display_name,
                role="user", profile={})
    db.add(user)
    db.flush()
    audit(db, request, user, "auth.register")
    db.commit()
    _set_cookie(response, create_access_token(user.id, user.role))
    return user_out(db, user)


@router.post("/login", dependencies=[Depends(rate_limit("login", 10, 300))])
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, request, None, "auth.login_failed", body.email.lower())
        db.commit()
        raise HTTPException(401, "invalid email or password")
    user.last_login_at = datetime.now(UTC)
    audit(db, request, user, "auth.login")
    db.commit()
    token = create_access_token(user.id, user.role)
    _set_cookie(response, token)
    return {"user": user_out(db, user), "access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_out(db, user)


@router.put("/me/profile")
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.display_name = body.display_name
    user.profile = {
        "skills": sorted({s.strip() for s in body.skills if s.strip()}),
        "preferred_skills": sorted({s.strip() for s in body.preferred_skills if s.strip()}),
        "years_experience": body.years_experience,
        "cities": sorted({c.strip() for c in body.cities if c.strip()}),
        "work_modes": [m for m in body.work_modes if m in ("onsite", "hybrid", "remote")],
    }
    db.commit()
    return user_out(db, user)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


@router.put("/me/password", dependencies=[Depends(rate_limit("password", 5, 300))])
def change_password(body: PasswordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "current password is wrong")
    user.password_hash = hash_password(body.new_password)
    audit(db, request, user, "auth.password_changed")
    db.commit()
    return {"ok": True}
