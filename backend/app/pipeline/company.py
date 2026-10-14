"""Company transparency: how much *verifiable public information* the employer
publishes. Independent of ad quality. No claims about finances, payroll
reliability, employee satisfaction or reputation - we have no evidence for those.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.models import Company

CHECKS = [
    # key, label, points
    ("website", "وب‌سایت رسمی اعلام شده", 25),
    ("description", "توضیحات فعالیت شرکت", 20),
    ("size", "اندازه سازمان منتشر شده", 15),
    ("industry", "حوزه فعالیت مشخص", 10),
    ("establishment_year", "سال تأسیس منتشر شده", 10),
    ("products", "محصول یا خدمات معرفی شده", 10),
    ("multi_source", "حضور در بیش از یک منبع", 10),
]


def assess(company: Company) -> dict:
    facts: dict[str, list[dict]] = {}
    for p in company.profiles or []:
        for k, v in (p.get("facts") or {}).items():
            facts.setdefault(k, []).append({"source": p.get("source"), "url": p.get("url"), "seen_at": p.get("seen_at"), "value": v})
    present = {
        "website": bool(company.website),
        "description": bool(company.description and len(company.description) >= 100),
        "size": bool(company.size),
        "industry": bool(company.industry),
        "establishment_year": bool(facts.get("establishment_year")),
        "products": bool(company.description and any(w in company.description for w in ("محصول", "خدمات", "product", "service", "پلتفرم", "platform"))),
        "multi_source": len({p.get("source") for p in company.profiles or []}) > 1,
    }
    items = []
    for key, label, pts in CHECKS:
        ev = facts.get(key) or []
        items.append({
            "key": key, "label": label, "points": pts if present[key] else 0, "max": pts, "present": present[key],
            "evidence": ev[:3] or ([{"source": p.get("source"), "url": p.get("url"), "seen_at": p.get("seen_at")}
                                    for p in (company.profiles or [])][:2] if present[key] else []),
        })
    known_points = sum(1 for k in ("website", "description", "size", "industry") if present[k])
    score = sum(i["points"] for i in items)
    if known_points < 2:
        level, score_out, confidence = "unknown", None, 0.3
    else:
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        score_out = score
        confidence = round(min(0.9, 0.4 + 0.1 * known_points + (0.1 if present["multi_source"] else 0)), 2)
    return {
        "score": score_out,
        "level": level,
        "confidence": confidence,
        "items": items,
        "sources": [{"source": p.get("source"), "url": p.get("url"), "seen_at": p.get("seen_at")} for p in company.profiles or []],
        "assessed_at": datetime.now(UTC).isoformat(),
        "note": "این ارزیابی فقط میزان اطلاعات عمومی و قابل بررسی شرکت را نشان می‌دهد و درباره وضعیت مالی، "
                "پرداخت حقوق، رضایت کارکنان یا اعتبار واقعی شرکت هیچ ادعایی ندارد.",
    }


def apply(company: Company) -> None:
    a = assess(company)
    company.transparency = a
    company.transparency_score = a["score"]
    company.transparency_level = a["level"]
    company.assessed_at = datetime.now(UTC)
