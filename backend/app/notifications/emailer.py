"""SMTP notification service. Credentials come from settings_store (DB, encrypted)
or the environment and are never logged or returned by the API."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from app import settings_store

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates"),
    autoescape=select_autoescape(["html"]),
)


class EmailNotConfigured(Exception):
    pass


def smtp_config(db: Session) -> dict:
    cfg = {k: settings_store.get(db, f"smtp.{k}") for k in ("host", "port", "username", "password", "from", "starttls", "ssl")}
    if not cfg["host"] or not cfg["from"]:
        raise EmailNotConfigured("SMTP host and From address are not configured")
    return cfg


def render(template: str, **ctx) -> str:
    return TEMPLATES.get_template(template).render(**ctx)


def send_email(db: Session, to: str, subject: str, html: str, text: str, headers: dict | None = None) -> str:
    cfg = smtp_config(db)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr(("Iran Tech Job Intelligence", cfg["from"]))
    msg["To"] = to
    msg_id = make_msgid(domain=cfg["from"].split("@")[-1])
    msg["Message-ID"] = msg_id
    for k, v in (headers or {}).items():
        msg[k] = v
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    port = int(cfg["port"] or 587)
    ctx = ssl.create_default_context()
    if cfg["ssl"]:
        server = smtplib.SMTP_SSL(cfg["host"], port, timeout=30, context=ctx)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=30)
    try:
        server.ehlo()
        if cfg["starttls"] and not cfg["ssl"]:
            server.starttls(context=ctx)
            server.ehlo()
        if cfg["username"]:
            server.login(cfg["username"], cfg["password"] or "")
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except smtplib.SMTPException:
            pass
    return msg_id
