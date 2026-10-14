"""match_score 0-100 between a user's skill profile and a job, with a breakdown."""
from __future__ import annotations

from app.pipeline.taxonomy import canonical_skill

WEIGHTS = {"required": 40, "preferred": 15, "experience": 20, "city": 10, "work_mode": 15}


def _norm_set(items) -> set[str]:
    out = set()
    for s in items or []:
        if not s:
            continue
        out.add((canonical_skill(s) or s.strip()).lower())
    return out


def match(profile: dict, job) -> dict:
    user_skills = _norm_set(profile.get("skills"))
    user_pref = _norm_set(profile.get("preferred_skills"))
    job_req = {s.skill.lower() for s in job.skills if s.skill_type == "required"} or _norm_set(job.required_skills)
    job_opt = {s.skill.lower() for s in job.skills if s.skill_type == "optional"} | _norm_set(job.optional_skills)
    parts = []

    # required skills of the job covered by the user
    if job_req:
        hit = job_req & (user_skills | user_pref)
        s = WEIGHTS["required"] * len(hit) / len(job_req)
        parts.append({"key": "required", "label": "مهارت‌های ضروری", "score": round(s, 1), "max": WEIGHTS["required"],
                      "detail": f"{len(hit)} از {len(job_req)}", "matched": sorted(hit), "missing": sorted(job_req - hit)})
    else:
        parts.append({"key": "required", "label": "مهارت‌های ضروری", "score": WEIGHTS["required"] / 2,
                      "max": WEIGHTS["required"], "detail": "آگهی مهارت ضروری مشخصی ندارد", "matched": [], "missing": []})

    # optional skills of the job + the user's preferred technologies present in the job
    pool = job_opt | job_req
    pref_hit = user_pref & pool
    opt_hit = job_opt & user_skills
    denom = max(1, len(job_opt) + len(user_pref))
    s = WEIGHTS["preferred"] * min(1.0, (len(opt_hit) + len(pref_hit)) / denom) if (job_opt or user_pref) else WEIGHTS["preferred"] / 2
    parts.append({"key": "preferred", "label": "مهارت‌های ترجیحی", "score": round(s, 1), "max": WEIGHTS["preferred"],
                  "detail": f"اختیاری آگهی: {len(opt_hit)}/{len(job_opt)}؛ ترجیحات شما در آگهی: {len(pref_hit)}/{len(user_pref)}",
                  "matched": sorted(opt_hit | pref_hit)})

    years = profile.get("years_experience")
    need = job.experience_min_years
    if years is None or need is None:
        s, d = WEIGHTS["experience"] / 2, "نامشخص"
    elif years >= need:
        s, d = WEIGHTS["experience"], f"شما {years:g} سال، آگهی {need:g} سال"
    elif years >= need - 1:
        s, d = WEIGHTS["experience"] / 2, f"شما {years:g} سال، آگهی {need:g} سال"
    else:
        s, d = 0, f"شما {years:g} سال، آگهی {need:g} سال"
    parts.append({"key": "experience", "label": "سابقه", "score": s, "max": WEIGHTS["experience"], "detail": d})

    cities = {c.strip() for c in profile.get("cities") or [] if c}
    if job.work_mode == "remote":
        s, d = WEIGHTS["city"], "دورکاری"
    elif not cities or not job.city:
        s, d = WEIGHTS["city"] / 2, "نامشخص"
    elif job.city in cities:
        s, d = WEIGHTS["city"], job.city
    else:
        s, d = 0, f"{job.city} در شهرهای شما نیست"
    parts.append({"key": "city", "label": "شهر", "score": s, "max": WEIGHTS["city"], "detail": d})

    modes = set(profile.get("work_modes") or [])
    if not modes or not job.work_mode:
        s, d = WEIGHTS["work_mode"] / 2, "نامشخص"
    elif job.work_mode in modes:
        s, d = WEIGHTS["work_mode"], job.work_mode
    else:
        s, d = 0, f"{job.work_mode} جزو ترجیحات شما نیست"
    parts.append({"key": "work_mode", "label": "شیوه همکاری", "score": s, "max": WEIGHTS["work_mode"], "detail": d})

    total = round(sum(p["score"] for p in parts))
    return {"match_score": total, "breakdown": parts, "profile_complete": bool(user_skills)}
