"""Telegram bot (aiogram 3). Runs as the `telegram-bot` service.

* /start <code> links the chat to a site account (code issued by the website).
* Read commands show jobs; notifications are sent by the worker, not here.
* Mode: long polling (default, no public URL needed) or webhook - the webhook
  only accepts updates carrying TELEGRAM_WEBHOOK_SECRET in
  X-Telegram-Bot-Api-Secret-Token (checked by aiogram).
"""
from __future__ import annotations

import asyncio
import html

import structlog
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.filters import JobFilters, apply_filters, job_query
from app.logging_setup import setup_logging
from app.models import Job, NotificationSubscription, SavedSearch, TelegramConnection
from app.pipeline import taxonomy as tx
from app.telegram_auth import redeem_link_code

setup_logging()
log = structlog.get_logger()
dp = Dispatcher()

COMMANDS = [
    ("latest", "آخرین آگهی‌های مرتبط"),
    ("devops", "آخرین آگهی‌های DevOps / Platform"),
    ("sre", "آخرین آگهی‌های SRE"),
    ("python", "آخرین آگهی‌های Python"),
    ("ai", "آخرین آگهی‌های AI / ML"),
    ("saved", "جست‌وجوهای ذخیره‌شده من"),
    ("alerts", "هشدارهای فعال من"),
    ("settings", "تنظیمات اعلان"),
    ("help", "راهنما"),
]
CMD_CATEGORY = {"devops": ["devops"], "sre": ["sre"], "python": ["python"], "ai": ["ai_ml", "mlops_data"]}
WORK_MODE_FA = {"onsite": "حضوری", "hybrid": "هیبریدی", "remote": "دورکاری"}
SAL_FA = {"reported": "اعلام‌شده", "estimated": "تخمینی", "unknown": "نامشخص"}


def base_url() -> str:
    return get_settings().public_base_url.rstrip("/")


def esc(v) -> str:
    return html.escape(str(v or ""), quote=False)


def _linked_user_id(tg_user_id: int) -> int | None:
    with session_scope() as db:
        conn = db.scalar(select(TelegramConnection).where(TelegramConnection.telegram_user_id == tg_user_id,
                                                          TelegramConnection.status == "active"))
        return conn.user_id if conn else None


def _jobs_text(categories: list[str] | None, limit: int = 5) -> list[tuple[str, InlineKeyboardMarkup]]:
    out = []
    with session_scope() as db:
        f = JobFilters(categories=categories or [])
        for j in db.scalars(job_query(f, "newest").limit(limit)):
            cats = ", ".join(tx.CATEGORY_LABELS_FA.get(c.category, c.category) for c in j.categories)
            loc = " / ".join(x for x in (j.province, j.city) if x)
            if j.work_mode in WORK_MODE_FA:
                loc += f" · {WORK_MODE_FA[j.work_mode]}"
            sal = SAL_FA.get(j.salary_status, "نامشخص")
            if j.salary_status != "unknown" and j.effective_salary_min:
                sal += f": {j.effective_salary_min // 1_000_000}-{(j.effective_salary_max or j.effective_salary_min) // 1_000_000} میلیون"
            text = (f"<b>{esc(j.title)}</b>\n{esc(j.company_name or 'شرکت نامشخص')}" + (f" · {esc(loc)}" if loc else "")
                    + f"\nدسته: {esc(cats)}\nحقوق ({esc(sal)})" + (f"\nکیفیت آگهی: {j.quality_score}/100" if j.quality_score is not None else ""))
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="آگهی اصلی", url=j.canonical_url),
                InlineKeyboardButton(text="تحلیل", url=f"{base_url()}/jobs/{j.id}"),
            ]])
            out.append((text, kb))
    return out


@dp.message(CommandStart(deep_link=True))
async def start_with_code(message: Message, command: CommandObject):
    code = (command.args or "").strip()
    if not code or len(code) > 64 or message.from_user is None:
        await message.answer("کد اتصال نامعتبر است. از صفحه تنظیمات سایت یک لینک جدید بگیرید.")
        return

    def link():
        with session_scope() as db:
            conn = redeem_link_code(db, code, message.chat.id, message.from_user.id, message.from_user.username)
            return conn is not None

    ok = await asyncio.to_thread(link)
    if ok:
        await message.answer("✅ حساب شما متصل شد. اعلان‌های هشدارهایی که کانال تلگرام دارند از این پس اینجا ارسال می‌شود.\n/help")
    else:
        await message.answer("❌ این کد منقضی شده یا قبلاً استفاده شده است. از صفحه تنظیمات سایت دوباره «اتصال تلگرام» را بزنید.")


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "سلام! این ربات آگهی‌های DevOps، SRE، Python و AI/ML ایران را نشان می‌دهد و هشدارهای شما را ارسال می‌کند.\n\n"
        f"برای اتصال حساب: در سایت <a href=\"{esc(base_url())}/settings\">تنظیمات</a> روی «اتصال تلگرام» بزنید.\n/help")


@dp.message(Command("help"))
async def help_cmd(message: Message):
    lines = [f"/{c} - {d}" for c, d in COMMANDS]
    await message.answer("دستورها:\n" + "\n".join(lines) +
                         "\n\nاعلان‌ها فقط بر اساس جست‌وجوهای ذخیره‌شده و هشدارهای خودتان ارسال می‌شوند.")


async def _require_link(message: Message) -> int | None:
    uid = await asyncio.to_thread(_linked_user_id, message.from_user.id) if message.from_user else None
    if uid is None:
        await message.answer(f"ابتدا حساب خود را از <a href=\"{esc(base_url())}/settings\">تنظیمات سایت</a> متصل کنید.")
    return uid


@dp.message(Command("latest", "devops", "sre", "python", "ai"))
async def jobs_cmd(message: Message, command: CommandObject):
    if await _require_link(message) is None:
        return
    items = await asyncio.to_thread(_jobs_text, CMD_CATEGORY.get(command.command))
    if not items:
        await message.answer("فعلاً آگهی فعالی در این دسته ثبت نشده است.")
        return
    for text, kb in items:
        await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


@dp.message(Command("saved"))
async def saved_cmd(message: Message):
    uid = await _require_link(message)
    if uid is None:
        return

    def load():
        with session_scope() as db:
            out = []
            for s in db.scalars(select(SavedSearch).where(SavedSearch.user_id == uid).order_by(SavedSearch.created_at)):
                n = db.scalar(apply_filters(select(func.count()).select_from(Job), JobFilters(**(s.filters or {}))))
                out.append(f"• {esc(s.name)}: {n} آگهی")
            return out

    lines = await asyncio.to_thread(load)
    await message.answer("جست‌وجوهای ذخیره‌شده:\n" + "\n".join(lines) if lines else
                         f"جست‌وجوی ذخیره‌شده‌ای ندارید. از <a href=\"{esc(base_url())}/jobs\">صفحه آگهی‌ها</a> فیلتر را ذخیره کنید.")


@dp.message(Command("alerts"))
async def alerts_cmd(message: Message):
    uid = await _require_link(message)
    if uid is None:
        return

    def load():
        with session_scope() as db:
            rows = db.execute(select(NotificationSubscription, SavedSearch.name)
                              .outerjoin(SavedSearch, SavedSearch.id == NotificationSubscription.saved_search_id)
                              .where(NotificationSubscription.user_id == uid)).all()
            return [f"• {'✅' if s.active else '⏸'} {esc(name or 'همه آگهی‌ها')} - {s.channel} - "
                    f"{'فوری' if s.frequency == 'instant' else 'روزانه'} - {', '.join(s.event_types)}" for s, name in rows]

    lines = await asyncio.to_thread(load)
    await message.answer("هشدارها:\n" + "\n".join(lines) if lines else
                         f"هشداری تعریف نشده. از <a href=\"{esc(base_url())}/alerts\">صفحه هشدارها</a> بسازید.")


@dp.message(Command("settings"))
async def settings_cmd(message: Message):
    rows = [[InlineKeyboardButton(text="تنظیمات در سایت", url=f"{base_url()}/settings")]]
    if base_url().startswith("https://"):
        rows.append([InlineKeyboardButton(text="باز کردن Mini App", web_app=WebAppInfo(url=f"{base_url()}/tg"))])
    await message.answer("تنظیمات اعلان، کانال‌ها و هشدارها:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.message(F.text)
async def fallback(message: Message):
    await message.answer("دستور شناخته نشد. /help")


async def on_startup(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in COMMANDS])
    if base_url().startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="داشبورد", web_app=WebAppInfo(url=f"{base_url()}/tg")))


def make_bot() -> Bot:
    s = get_settings()
    session = AiohttpSession(proxy=s.telegram_proxy) if s.telegram_proxy else None
    return Bot(token=s.telegram_bot_token, session=session, default=DefaultBotProperties(parse_mode="HTML"))


async def run_polling() -> None:
    bot = make_bot()
    dp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=["message"])


def run_webhook() -> None:
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    s = get_settings()
    if len(s.telegram_webhook_secret) < 16:
        raise SystemExit("TELEGRAM_WEBHOOK_SECRET (>=16 chars) is required in webhook mode")
    bot = make_bot()

    async def startup(bot: Bot):
        await on_startup(bot)
        await bot.set_webhook(f"{base_url()}/telegram/webhook", secret_token=s.telegram_webhook_secret,
                              allowed_updates=["message"], drop_pending_updates=False)

    dp.startup.register(startup)
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=s.telegram_webhook_secret).register(app, path="/telegram/webhook")
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=8081)


def main() -> None:
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("telegram_bot_disabled", reason="TELEGRAM_BOT_TOKEN is not set; sleeping")
        import time
        while True:  # keep the container healthy-but-idle until configured
            time.sleep(3600)
    if s.telegram_mode == "webhook":
        run_webhook()
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
