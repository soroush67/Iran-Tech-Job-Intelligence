"""Persian/English text normalisation shared by collectors, change detection and search."""
import hashlib
import html
import json
import re
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit

ZWNJ = "‌"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ARABIC = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه", "ؤ": "و", "إ": "ا", "أ": "ا", "ٱ": "ا"})
_INVISIBLE = re.compile("[​‍‎‏‪-‮⁦-⁩﻿­]")
_TATWEEL = "ـ"
_DIACRITICS = re.compile("[ً-ٰٟ]")
_WS = re.compile(r"[ \t\r\f\v  -   　]+")
_BLOCK_TAGS = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|table|section)\b[^>]*>", re.I)
_TAGS = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)


def to_ascii_digits(text: str) -> str:
    return text.translate(_DIGITS)


def normalize_text(text: str | None) -> str:
    """Canonical display text: unified letters/digits, one ZWNJ, collapsed spaces."""
    if not text:
        return ""
    t = html.unescape(text)
    t = unicodedata.normalize("NFC", t)
    t = t.translate(_ARABIC).translate(_DIGITS)
    t = _INVISIBLE.sub("", t).replace(_TATWEEL, "")
    t = _DIACRITICS.sub("", t)
    t = re.sub(f"{ZWNJ}+", ZWNJ, t)
    t = re.sub(f" ?{ZWNJ} ?", lambda m: ZWNJ if m.group(0) == ZWNJ else " ", t)
    t = t.replace("،", "، ").replace(" ،", "،")
    lines = [_WS.sub(" ", ln).strip() for ln in t.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def html_to_text(fragment: str | None) -> str:
    if not fragment:
        return ""
    t = _SCRIPT_STYLE.sub(" ", fragment)
    t = _BLOCK_TAGS.sub("\n", t)
    t = _TAGS.sub(" ", t)
    # one line per block: <p>/<br>/<li> soup otherwise renders as double-spaced text
    return "\n".join(ln for ln in normalize_text(t).split("\n") if ln.strip())


def compare_key(text: str | None) -> str:
    """Text reduced to what matters for change detection: no whitespace, ZWNJ,
    punctuation or case differences (HTML reflow must not look like a change)."""
    t = normalize_text(text).lower().replace(ZWNJ, "")
    return re.sub(r"[\W_]+", "", t)


def normalize_name(name: str | None) -> str:
    """Company / title key: drop legal forms and punctuation."""
    t = normalize_text(name).lower().replace(ZWNJ, " ")
    t = re.sub(r"\b(شرکت|گروه|موسسه|مؤسسه|هلدینگ|سهامی\s*خاص|سهامی\s*عام|بامسئولیت\s*محدود|co\.?|ltd\.?|inc\.?|company|group)\b", " ", t)
    t = re.sub(r"[\W_]+", " ", t)
    return " ".join(t.split())


_TRACKING_PARAMS = re.compile(r"^(utm_|_ref$|_t$|ref$|fbclid$|gclid$)")


def canonical_url(url: str) -> str:
    """Absolute URL without query string, fragment or trailing slash."""
    parts = urlsplit(url.strip())
    path = unquote(parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower(), path, "", ""))


def stable_hash(data) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# --- numbers & salary --------------------------------------------------------

_NUM = re.compile(r"\d[\d,٬'.]*")


def parse_number(token: str) -> float | None:
    t = to_ascii_digits(token).replace("٬", "").replace(",", "").replace("'", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse_salary_text(text: str | None) -> dict | None:
    """'۲۰ تا ۳۰ میلیون تومان' / '20,000,000 - 30,000,000 تومان' / 'توافقی'.

    Returns monthly toman min/max, or None when the ad does not state a figure.
    """
    if not text:
        return None
    t = normalize_text(text)
    if re.search(r"توافقی|negotiable|agreement|قانون کار", t, re.I) and not _NUM.search(t):
        return None
    nums = [n for n in (parse_number(x) for x in _NUM.findall(t)) if n is not None]
    if not nums:
        return None
    mult = 1.0
    if re.search(r"میلیون|million", t, re.I):
        mult = 1_000_000
    elif re.search(r"هزار|thousand", t, re.I):
        mult = 1_000
    currency = "IRT"
    if re.search(r"ریال|rial", t, re.I) and not re.search(r"تومان|toman", t, re.I):
        mult /= 10  # store toman
    if re.search(r"دلار|usd|\$", t, re.I):
        currency = "USD"
        mult = mult if mult != 1_000_000 else 1_000_000
    values = [int(round(n * mult)) for n in nums[:2]]
    lo, hi = (min(values), max(values)) if len(values) == 2 else (values[0], values[0])
    if currency == "IRT" and hi < 100_000:  # "۲۵" without unit is not a monthly salary
        return None
    period = "monthly"
    if re.search(r"ساعتی|hourly|per hour", t, re.I):
        period = "hourly"
    elif re.search(r"سالانه|annual|yearly", t, re.I):
        period = "yearly"
    return {"min": lo, "max": hi, "currency": currency, "period": period}


_FA_NUMBER_WORDS = {
    "یک": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
}


def parse_experience_years(text: str | None) -> float | None:
    """'سه تا شش سال' -> 3, 'کمتر از سه سال' -> 0, '2 years experience' -> 2."""
    if not text:
        return None
    t = normalize_text(text).lower()
    if re.search(r"بدون سابقه|نیاز به سابقه نیست|no experience|entry level", t):
        return 0.0
    if re.search(r"کمتر از|less than", t):
        return 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|تا|-|سال|years?|yrs?)", t)
    if m:
        return float(m.group(1))
    for word, val in _FA_NUMBER_WORDS.items():
        if re.search(rf"(^|\s){word}(\s|$)", t):
            return float(val)
    return None


# --- location ------------------------------------------------------------------

PROVINCE_CAPITALS = {
    "تهران": "تهران", "البرز": "کرج", "اصفهان": "اصفهان", "فارس": "شیراز", "خراسان رضوی": "مشهد",
    "آذربایجان شرقی": "تبریز", "قم": "قم", "گیلان": "رشت", "مازندران": "ساری", "یزد": "یزد",
    "کرمان": "کرمان", "خوزستان": "اهواز", "قزوین": "قزوین", "همدان": "همدان", "کرمانشاه": "کرمانشاه",
    "مرکزی": "اراک", "سمنان": "سمنان", "زنجان": "زنجان", "هرمزگان": "بندرعباس", "بوشهر": "بوشهر",
    "آذربایجان غربی": "ارومیه", "اردبیل": "اردبیل", "گلستان": "گرگان", "لرستان": "خرم آباد",
    "کردستان": "سنندج", "سیستان و بلوچستان": "زاهدان", "چهارمحال و بختیاری": "شهرکرد",
    "کهگیلویه و بویراحمد": "یاسوج", "ایلام": "ایلام", "خراسان شمالی": "بجنورد", "خراسان جنوبی": "بیرجند",
}
CITY_TO_PROVINCE = {v: k for k, v in PROVINCE_CAPITALS.items()}


def split_location(text: str | None) -> tuple[str | None, str | None]:
    """'تهران ، تهران' (province، city) -> (province, city)."""
    if not text:
        return None, None
    t = normalize_text(text)
    parts = [p.strip() for p in re.split(r"[،,/]", t) if p.strip()]
    if not parts:
        return None, None
    if len(parts) == 1:
        p = parts[0]
        if p in PROVINCE_CAPITALS:
            return p, PROVINCE_CAPITALS[p] if p == "تهران" else None
        return CITY_TO_PROVINCE.get(p), p
    return parts[0], parts[1]
