"""Structured JSON logs. Secrets are scrubbed before rendering."""
import logging
import re
import sys

import structlog

_SECRET_KEYS = re.compile(r"(password|token|secret|api_key|authorization|cookie)", re.I)
_BOT_TOKEN = re.compile(r"bot\d+:[A-Za-z0-9_-]{20,}")
_API_KEY = re.compile(r"sk-ant-[A-Za-z0-9_-]+")


def _scrub(_, __, event_dict):
    for k in list(event_dict):
        if _SECRET_KEYS.search(k):
            event_dict[k] = "***"
        elif isinstance(event_dict[k], str):
            event_dict[k] = _API_KEY.sub("sk-ant-***", _BOT_TOKEN.sub("bot***", event_dict[k]))
    return event_dict


_configured = False


def setup_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    # httpx logs full URLs at INFO - Telegram URLs contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _scrub,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True
