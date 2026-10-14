<div dir="rtl">

# Iran Tech Job Intelligence

سامانه جمع‌آوری، تحلیل، طبقه‌بندی و پایش فرصت‌های شغلی فناوری اطلاعات ایران در این حوزه‌ها:
- DevOps / Platform
- SRE
- Python
- AI / ML
- MLOps / Data

**منابع نسخه اول:** `jobinja.ir` و `jobvision.ir`. ساختار Adapter-محور است و منبع جدید با یک ماژول اضافه می‌شود.

| بخش | فناوری |
|---|---|
| Backend | FastAPI (`/api/v1`)، SQLAlchemy، Alembic، PostgreSQL 17 |
| صف و زمان‌بندی | Redis، RQ (worker)، scheduler |
| ربات تلگرام | aiogram 3 + Mini App |
| رابط وب | Next.js 15، TypeScript، Tailwind CSS 4، کامپوننت‌های shadcn/ui، فارسی و RTL، Dark Mode |
| تحلیل هوش مصنوعی | قاعده‌محور (همیشه فعال) + Claude (Anthropic API) یا Ollama محلی، با دکمه فعال/غیرفعال و Sync |
| استقرار | Docker Compose، nginx با HTTPS |

جزئیات معماری: [ARCHITECTURE.md](ARCHITECTURE.md)

---

## ۱. وضعیت واقعی دسترسی به منابع (بررسی ۲۲ مهر ۱۴۰۵)

| منبع | robots.txt | API رسمی/فید | روش استفاده‌شده | محدودیت پوشش |
|---|---|---|---|---|
| **jobinja.ir** | `Disallow:` خالی؛ همه‌چیز جز `/style_guide/` مجاز | API یا فید عمومی منتشر نشده؛ sitemap هم ندارد | صفحه جست‌وجوی عمومی با کلیدواژه + صفحه هر آگهی (JSON-LD و جعبه اطلاعات) | فقط آگهی‌هایی که با کلیدواژه‌های تعریف‌شده پیدا می‌شوند (پیش‌فرض ۲۲ کلیدواژه × ۵ صفحه) |
| **jobvision.ir** | `disallow: *?*`، `*utm_*` و `*/Login/*`؛ sitemap معرفی شده | API داخلی `candidateapi.jobvision.ir` در robots خودش `Disallow: /` است، پس **استفاده نمی‌شود** | `sitemap/jobposts.xml` (همه آگهی‌های زنده با lastmod) + صفحه عمومی هر آگهی (داده‌ای که خود صفحه embed کرده) | فقط آگهی‌هایی که slug آدرسشان کلیدواژه فنی دارد؛ URL دارای `?` هرگز درخواست نمی‌شود |

**قواعد رعایت‌شده:**
- robots.txt در **ابتدای هر اجرا** دوباره خوانده می‌شود و هر URL پیش از درخواست با آن چک می‌شود.
- **Crawl-delay** رعایت می‌شود و فاصله پیش‌فرض بین درخواست‌ها ۲٫۵ ثانیه است.
- برای هر منبع فقط یک درخواست هم‌زمان ارسال می‌شود.
- **Retry و Backoff** پیاده‌سازی شده است.
- با دریافت پیاپی 403 یا 429، یا مشاهده صفحه CAPTCHA، اجرا متوقف می‌شود و منبع **Blocked** علامت می‌خورد. **هیچ تلاشی برای دور زدن انجام نمی‌شود.**
- **مقدار `baseSalary` در JSON-LD هر دو سایت قابل اعتماد نیست.** آگهی «توافقی» در jobinja مقدار ۵٬۰۰۰٬۰۰۰ و در jobvision مقدار 12000 داشت. حقوق فقط از متن یا داده واقعی صفحه خوانده می‌شود.
- شرایط استفاده (ToS) هیچ‌کدام از دو سایت **API یا مجوز رسمی برای استفاده داده منتشر نکرده است.** این سامانه فقط اطلاعات عمومی را با نرخ پایین و برای پژوهش بازار کار می‌خواند. اگر قصد استفاده تجاری یا انتشار داده را دارید، از خود سایت‌ها مجوز بگیرید.
- **ادعای پوشش کامل نمی‌شود.** پوشش هر اجرا (تعداد فهرست‌شده توسط منبع، یافته، دریافت‌شده و موکول‌شده به اجرای بعد) در صفحه «منابع و پوشش» ثبت و نمایش داده می‌شود.

**نتیجه اولین اجرای واقعی در محیط آزمایش:** به [بخش ۱۰](#run-results) نگاه کنید.

---

## ۲. راه‌اندازی

پیش‌نیاز: Docker با Compose v2. فقط برای build به اینترنت نیاز است. پورت‌های پیش‌فرض: **8443** (HTTPS) و **8088** (که به HTTPS هدایت می‌شود).

<div dir="ltr">

```bash
git clone <repo> Iran_Tech_Job_Intelligence && cd Iran_Tech_Job_Intelligence
cp .env.example .env
# Fill in at least: POSTGRES_PASSWORD, SECRET_KEY, ENCRYPTION_KEY, ADMIN_EMAIL, ADMIN_PASSWORD, PUBLIC_BASE_URL
openssl rand -base64 48            # for SECRET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # ENCRYPTION_KEY
docker compose up -d --build
docker compose ps                  # all services must be healthy
```

</div>

**ورود:**
1. آدرس `https://<server>:8443` را باز کنید.
2. با `ADMIN_EMAIL` و `ADMIN_PASSWORD` که در `.env` گذاشته‌اید وارد شوید. **بعد از ورود، رمز را از «تنظیمات» عوض کنید.**
3. گواهی پیش‌فرض self-signed است و مرورگر هشدار می‌دهد. برای گواهی واقعی، فایل‌های `fullchain.pem` و `privkey.pem` را در `nginx/certs/` بگذارید و دستور زیر را بزنید:

<div dir="ltr">

```bash
docker compose run --rm certs && docker compose restart nginx
```

</div>

**اولین اجرا:**
- scheduler جمع‌آوری را بلافاصله شروع می‌کند.
- اجرای اول هر منبع «پایه» (baseline) است: آگهی‌های موجود ثبت می‌شوند ولی **هیچ اعلانی ارسال نمی‌شود**.
- هر اجرا حداکثر ۲۵۰ صفحه می‌خواند و باقی به اجرای بعد موکول می‌شود. فاصله پیش‌فرض اجراها ۴ ساعت است.

| سرویس | نقش |
|---|---|
| `nginx` | HTTPS، هدرهای امنیتی، Rate Limit، مسیر Webhook تلگرام |
| `frontend` | رابط وب Next.js |
| `backend` | API؛ در هر start مایگریشن و bootstrap را اجرا می‌کند |
| `worker` | دو پروسس RQ: یکی برای `collect` و دیگری برای `notify` و `analyze` |
| `scheduler` | زمان‌بندی جمع‌آوری، ارسال اعلان (هر دقیقه) و گزارش روزانه |
| `telegram-bot` | ربات تلگرام (polling یا webhook) |
| `postgres` و `redis` | فقط روی شبکه داخلی `internal` (بدون دسترسی به بیرون) با volume ماندگار |
| `ollama` (اختیاری) | مدل محلی: `docker compose --profile ollama up -d` |

حالت توسعه: `docker compose -f compose.yaml -f compose.dev.yaml up -d --build`. در این حالت API روی `127.0.0.1:8000` با reload، Postgres روی 5433 و Redis روی 6380 در دسترس است.

---

## ۳. اتصال به Claude (هوش مصنوعی)

**مسیر:** تنظیمات ← تب «هوش مصنوعی» (فقط مدیر)

1. **API Key** را از console.anthropic.com بگیرید و در فیلد مربوط وارد کنید. کلید رمزنگاری‌شده (Fernet) در پایگاه داده ذخیره می‌شود و دیگر نمایش داده نمی‌شود. راه دیگر: مقدار `ANTHROPIC_API_KEY` در `.env`.
2. مدل را انتخاب کنید. پیش‌فرض `claude-opus-5-5` است. برای هزینه کمتر `claude-haiku-5-5` یا `claude-sonnet-5-5` را بزنید.
3. دکمه **تست اتصال** را بزنید.
4. کلید **فعال/غیرفعال** را روشن کنید.
5. **Sync** آگهی‌های مرتبطی را که هنوز با مدل فعلی تحلیل نشده‌اند، یا محتوایشان تغییر کرده، به مدل می‌فرستد.
6. گزینه «تحلیل خودکار پس از هر جمع‌آوری» هم موجود است.

**نکات:**
- وقتی تحلیل با مدل غیرفعال است یا کلید ندارد، **تحلیل قاعده‌محور** انجام می‌شود: دسته، مهارت، سطح، امتیاز کیفیت، هشدارها و حقوق.
- متن آگهی به‌عنوان **داده** در تگ `<job_ad>` فرستاده می‌شود و هرگز به‌عنوان دستور تلقی نمی‌شود.
- خروجی مدل با JSON Schema محدود و با Pydantic اعتبارسنجی می‌شود. هر «شاهد» که عیناً در متن آگهی نباشد حذف می‌شود.
- اگر مدل درخواستی را رد کند، `fallbacks: "default"` فعال است.

**هزینه تقریبی:** هر آگهی حدود ۲ تا ۴ هزار توکن ورودی دارد. هزینه دقیق را در کنسول Anthropic ببینید.

**Ollama:**
1. `docker compose --profile ollama up -d`
2. `docker compose exec ollama ollama pull qwen2.5:7b`
3. در تنظیمات، ارائه‌دهنده را «Ollama» بگذارید.

---

## ۴. ایمیل (SMTP)

**تنظیم (مدیر):** تنظیمات ← «SMTP و اعلان» (Host، Port، Username، Password، From، STARTTLS یا SSL)، یا متغیرهای `SMTP_*` در `.env`. مقدار UI اولویت دارد. رمز رمزنگاری‌شده ذخیره می‌شود.

**کاربر:**
1. تنظیمات ← «ایمیل»: نشانی را وارد کنید. لینک تأیید (۲۴ ساعته) ارسال می‌شود.
2. «ارسال ایمیل آزمایشی» را بزنید.
3. در صفحه «جست‌وجوها و هشدارها» برای هر فیلتر ذخیره‌شده هشدار بسازید و این‌ها را مشخص کنید:
   - کانال
   - رویدادها: `NEW_JOB`، `SALARY_CHANGED` و بقیه
   - تناوب: فوری یا گزارش روزانه
   - دسته‌ها
   - حداقل امتیاز تطابق

**تضمین‌ها:**
- هر ایمیل قالب HTML فارسی، RTL و سازگار با موبایل دارد، با لینک آگهی اصلی، لینک داشبورد و لینک لغو (`List-Unsubscribe`).
- جلوگیری از ارسال تکراری با محدودیت یکتا روی (کاربر، کانال، رویداد) و (کاربر، کانال، روز گزارش) انجام می‌شود.
- سقف ساعتی برای هر کاربر وجود دارد.
- ارسال ناموفق با backoff دوباره تلاش می‌شود.

---

## ۵. ربات تلگرام

1. در `@BotFather` دستور `/newbot` را بزنید و توکن را بگیرید.
2. در `.env` این دو را بگذارید:
   - `TELEGRAM_BOT_TOKEN=...`
   - `TELEGRAM_BOT_USERNAME=نام_ربات_بدون_@`
3. `docker compose up -d telegram-bot backend worker` را اجرا کنید.
4. **اتصال حساب:**
   1. در سایت: تنظیمات ← «تلگرام» ← «اتصال تلگرام».
   2. یک لینک `t.me/<bot>?start=<code>` ساخته می‌شود. کد یک‌بارمصرف است، ۱۰ دقیقه اعتبار دارد و فقط هش آن ذخیره می‌شود.
   3. روی لینک بزنید و Start را انتخاب کنید.
   4. Chat ID **فقط از خود پیام تلگرام** گرفته می‌شود و هیچ‌وقت از کاربر پذیرفته نمی‌شود.
5. **دستورها:** `/start`، `/latest`، `/devops`، `/sre`، `/python`، `/ai`، `/saved`، `/alerts`، `/settings`، `/help`
6. **حالت‌ها:**
   - **polling** (پیش‌فرض): آدرس عمومی لازم ندارد.
   - **webhook**:
     - این‌ها را بگذارید: `TELEGRAM_MODE=webhook`، یک `TELEGRAM_WEBHOOK_SECRET` حداقل ۱۶ نویسه‌ای، و `PUBLIC_BASE_URL` عمومی با HTTPS معتبر.
     - nginx فقط درخواست POST را به `/telegram/webhook` می‌فرستد.
     - ربات هر update بدون هدر `X-Telegram-Bot-Api-Secret-Token` درست را رد می‌کند.
7. **Mini App:** مسیر `https://<domain>/tg`.
   - از دکمه منوی ربات یا `/settings` باز می‌شود.
   - `initData` در Backend با HMAC و توکن ربات اعتبارسنجی می‌شود و تاریخ آن هم بررسی می‌شود.
   - Telegram فقط Mini App با **HTTPS معتبر** (نه self-signed) را باز می‌کند، پس برای Mini App دامنه و گواهی واقعی لازم است.
8. اگر `api.telegram.org` از سرور در دسترس نیست، `TELEGRAM_PROXY` را تنظیم کنید (مثلاً `socks5://host:1080`).

---

## ۶. داده حقوق

**وضعیت‌های حقوق:**
- **Reported:** حقوقی که خود آگهی ذکر کرده است.
- **Estimated:** تخمین از یکی از این دو:
  - دیتاست معتبری که مدیر بارگذاری کرده است (مثلاً گزارش حقوق ۱۴۰۵).
  - حداقل ۵ آگهی هم‌دسته و هم‌سطح با حقوق اعلام‌شده در ۱۸۰ روز اخیر.
  
  در هر دو حالت روش، منبع، سال داده، تعداد نمونه و درجه اطمینان نمایش داده می‌شود.
- **Unknown:** داده کافی وجود ندارد. **عدد بدون پشتوانه ساخته نمی‌شود.**

**دیتاست حقوق در مخزن نیست**، چون داده معتبر ۱۴۰۵ باید از منبع مجاز تهیه شود. بارگذاری: تنظیمات ← «دیتاست حقوق». فایل CSV با کدگذاری UTF-8 و این ستون‌ها:

<div dir="ltr">

```text
category,role_title,seniority,city,employment_type,min_years,max_years,salary_min,salary_max,salary_median,sample_size
devops,DevOps Engineer,senior,تهران,full_time,5,8,60000000,90000000,75000000,40
```

</div>

- مبالغ ماهانه و به **تومان** هستند.
- `category` یکی از این‌هاست: `devops`، `sre`، `python`، `ai_ml`، `mlops_data`.
- `seniority` یکی از این‌هاست: `junior`، `mid`، `senior`، `staff`، `principal`.
- هر بارگذاری با همان نام، نسخه جدید می‌سازد و نسخه قبلی غیرفعال می‌شود. نسخه‌ها قابل فعال یا غیرفعال کردن هستند.

---

## ۷. تست‌ها

<div dir="ltr">

```bash
# Backend: 107 tests (pytest) against real Postgres + Redis inside compose; the network is mocked
docker compose --profile test run --rm test
# Frontend smoke test (Playwright/Chromium, desktop + mobile) against the running stack
./scripts/frontend-smoke.sh
```

</div>

| # | الزام | فایل تست |
|---|---|---|
| ۱ | استخراج و نرمال‌سازی | `test_normalize_extract.py` |
| ۲ | آگهی تکراری | `test_dedup_changes.py` |
| ۳ | تغییر واقعی و تغییر غیرواقعی | `test_dedup_changes.py` |
| ۴ | اعلان تکراری | `test_notifications.py` |
| ۵ | طبقه‌بندی | `test_classification.py` |
| ۶ و ۷ | حقوق اعلام‌شده، تخمینی و نبود داده | `test_salary.py` |
| ۸ | قطع یک منبع | `test_collector.py` |
| ۹ | SMTP (سرور aiosmtpd داخلی) | `test_notifications.py` و `test_api.py` |
| ۱۰ | اتصال امن تلگرام | `test_telegram.py` |
| ۱۱ | API | `test_api.py` |
| ۱۲ | Frontend Smoke | `frontend/tests/smoke.mjs` |

- لایه Claude با mock تست می‌شود: `test_ai_engine.py`.
- داده تست **ساختگی** است و فقط ساختار صفحات واقعی را تقلید می‌کند. در محیط عملیاتی هیچ داده نمونه‌ای وارد نمی‌شود.

---

## ۸. پشتیبان‌گیری و بازیابی

<div dir="ltr">

```bash
./scripts/backup.sh                       # backups/jobintel-<date>.dump (pg_dump -Fc + verification, keeps the newest 14)
KEEP=30 ./scripts/backup.sh
./scripts/restore.sh backups/jobintel-20261014-033000.dump   # asks for confirmation; on failure rolls back to the previous DB
# cron: 30 3 * * * cd /path/Iran_Tech_Job_Intelligence && ./scripts/backup.sh >> backups/backup.log 2>&1
```

</div>

داده‌های PostgreSQL در volume `jobintel_pgdata` ماندگار است. **`docker compose down -v` همه داده را پاک می‌کند.**

---

## ۹. امنیت (خلاصه)

**احراز هویت و دسترسی:**
- JWT در کوکی `httpOnly`، `Secure` و `SameSite=Lax`.
- بررسی Origin برای درخواست‌های تغییردهنده (CSRF).
- نقش‌های `admin` و `user`؛ همه مسیرهای `/api/v1/admin/*` فقط برای مدیر هستند.

**محدودسازی درخواست:** Rate Limit در nginx و همچنین در API (ورود، ثبت‌نام، تست اعلان، خروجی CSV).

**محافظت از داده و اسرار:**
- secretها فقط در `.env` یا رمزنگاری‌شده در پایگاه داده نگهداری می‌شوند.
- SMTP Password، API Key و Bot Token هرگز از API برنمی‌گردند و در لاگ‌ها ماسک می‌شوند.
- لاگ‌ها ساختاریافته (JSON) هستند.
- کوئری‌ها پارامتری‌اند (ORM) و ورودی‌ها با Pydantic اعتبارسنجی می‌شوند.
- متن آگهی در React escape می‌شود و `dangerouslySetInnerHTML` استفاده نشده است. CSP هم فعال است.
- در خروجی CSV از تزریق فرمول جلوگیری می‌شود.

**شبکه:**
- Postgres و Redis روی شبکه بدون خروجی هستند.
- collector فقط دو host مجاز را درخواست می‌کند (اعتبارسنجی URL منابع).

جزئیات بیشتر در [ARCHITECTURE.md](ARCHITECTURE.md).

---

<a id="run-results"></a>

## ۱۰. نتیجه اجرای واقعی در محیط آزمایش

اجرای واقعی روی همین سرور در ۲۲ مهر ۱۴۰۵ (۱۴ اکتبر ۲۰۲۶):

| اجرا | نوع | یافته (کاندید) | دریافت | مرتبط | خطا | مدت |
|---|---|---|---|---|---|---|
| jobinja #1 | پایه (بدون اعلان) | ۷۳۵ (جمع نتایج گزارش‌شده توسط سایت: ۳۲۹۶، با هم‌پوشانی) | ۲۵۰ | ۱۸۴ | ۰ | ۱۵ دقیقه |
| jobvision #1 | پایه (بدون اعلان) | ۹۱۴ از کل sitemap | ۲۵۰ | ۱۴۳ | ۰ | ۱۳ دقیقه |
| jobinja #2 | عادی | ۷۳۴ | ۲۵۰ | ۱۴۰ آگهی جدید | ۰ | ۱۵ دقیقه |

**نتایج:**
- در مجموع **۴۶۸ آگهی مرتبط** از **۵۳۲ شرکت** ثبت شد.
- وضعیت حقوق: ۱۰۱ اعلام‌شده، ۲۴۴ تخمینی (از حقوق‌های اعلام‌شده آگهی‌های مشابه) و ۱۲۳ نامشخص.
- هیچ ۴۰۳ یا ۴۲۹ یا CAPTCHA یا درخواست غیرمجازی از نظر robots رخ نداد.
- آگهی‌های باقی‌مانده هر منبع در اجراهای بعدی دریافت می‌شوند و عدد آن در یادداشت پوشش هر اجرا ثبت است.

**صحت‌سنجی‌های انجام‌شده روی همین stack:**
- `docker compose up -d --build` از image خالی در یک مرحله اجرا شد و هر ۸ سرویس healthy شدند.
- HTTPS، هدایت HTTP به HTTPS با حفظ پورت، و هدرهای HSTS و CSP بررسی شد.
- ۱۰۷ تست backend داخل Docker (روی شبکه بدون اینترنت) پاس شد.
- Smoke test فرانت در Chromium برای دسکتاپ و موبایل پاس شد: ۷ صفحه و صفحه جزئیات، RTL، بدون اسکرول افقی، Dark Mode و بدون خطای JS.
- ایمیل سرتاسری با یک SMTP محلی آزمایشی (Mailpit) بررسی شد:
  - ثبت نشانی، لینک تأیید، تأیید و ایمیل آزمایشی.
  - سپس در اجرای دوم، **۱۷ اعلان واقعی آگهی جدید** مطابق فیلتر ذخیره‌شده ارسال شد، بدون تکرار و بدون اعلان برای اجرای پایه (۳۲۷ رویداد پایه، صفر اعلان).
- پشتیبان‌گیری و بازیابی کامل روی همین داده انجام شد و تعداد ردیف‌ها قبل و بعد یکسان بود.

**موارد اجرانشده به دلیل نبود Credential:**
- **Claude:** لایه کامل با mock تست شده است؛ با ثبت API Key، دکمه «تست اتصال» آن را تأیید می‌کند.
- **تلگرام:** اتصال، HMAC و ربات تست واحد دارند؛ اجرای واقعی به توکن ربات نیاز دارد.
- **SMTP واقعی** شما.

---

## ۱۱. مواردی که به ورودی شما نیاز دارد

| مورد | کجا |
|---|---|
| API Key مربوط به Anthropic | تنظیمات ← هوش مصنوعی، یا `ANTHROPIC_API_KEY` |
| SMTP | تنظیمات ← SMTP، یا `SMTP_*` |
| ربات تلگرام | `TELEGRAM_BOT_TOKEN` و `TELEGRAM_BOT_USERNAME` |
| دامنه و گواهی معتبر (برای Mini App و Webhook) | `PUBLIC_BASE_URL` و `nginx/certs/` |
| دیتاست معتبر حقوق ۱۴۰۵ | تنظیمات ← دیتاست حقوق |

</div>
