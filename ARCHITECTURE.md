<div dir="rtl">

# معماری Iran Tech Job Intelligence

## ۱. نمای کلی

<div dir="ltr">

```text
                 ┌────────────── egress (internet) ──────────────┐
 user ──HTTPS──▶ nginx ──▶ frontend (Next.js)                     │
                   │  └──▶ backend (FastAPI /api/v1) ──┐          │
                   └──▶ telegram-bot (webhook, optional)│          │
                                                        ▼          │
   scheduler ──enqueue──▶ Redis (RQ queues) ◀── worker: collect ───┼─▶ jobinja.ir / jobvision.ir
        │                                    └─ worker: notify/analyze ─▶ SMTP / Telegram / Anthropic / Ollama
        └──────────────▶ PostgreSQL ◀──────────────────────────────┘
          (postgres + redis live only on the `internal` network, which has no outbound route)
```

</div>

| سرویس | فرایند | وظیفه |
|---|---|---|
| backend | `uvicorn app.main:app` | API، احراز هویت؛ در شروع کار `alembic upgrade head` و seed منابع و مدیر را اجرا می‌کند |
| worker | دو پروسس `rq worker` | `collect`: جمع‌آوری کند و طولانی؛ `notify` و `analyze`: اعلان و تحلیل. یک crawl طولانی هیچ‌وقت اعلان‌ها را معطل نمی‌کند |
| scheduler | `app.scheduler` | تصمیم «کی» (هر ۳۰ ثانیه)؛ کار واقعی را worker انجام می‌دهد؛ heartbeat در Redis برای health check |
| telegram-bot | `app.bot.main` | فرمان‌های کاربر و اتصال حساب؛ پیام‌های اعلان را worker مستقیم با Bot API می‌فرستد |
| certs | `app.certs` (یک‌بار) | کپی گواهی واقعی یا ساخت گواهی self-signed |

یک image مشترک (`backend/Dockerfile`) با نقش‌های `api|worker|scheduler|bot|certs|migrate` در `docker/entrypoint.sh` استفاده می‌شود.

## ۲. ساختار مخزن

<div dir="ltr">

```text
backend/app
  collectors/   base.py (adapter contract) · http.py (polite client) · jobinja.py · jobvision.py · registry.py · runner.py
  pipeline/     normalize.py · taxonomy.py · rules.py · ingest.py (upsert + change detection) · salary.py · company.py · matching.py
  ai/           providers.py (Claude, Ollama) · engine.py (merge + persist + Sync)
  notifications/ emailer.py · telegram_send.py · dispatcher.py
  api/          auth · jobs · companies · insights · alerts · telegram · admin
  bot/main.py   aiogram
  models.py · filters.py · settings_store.py · security.py · telegram_auth.py · tasks.py · scheduler.py
backend/alembic/versions/0001_initial_schema.py
backend/tests/  107 tests + fixtures/pages.py (synthetic pages mirroring the real structure)
frontend/src/app  (app)/{page,jobs,jobs/[id],companies,companies/[id],insights,alerts,sources,settings} · login · tg
nginx/          nginx.conf + templates/jobintel.conf.template
scripts/        backup.sh · restore.sh · frontend-smoke.sh
```

</div>

## ۳. جمع‌آوری داده

### قرارداد Adapter

برای افزودن یک منبع جدید:
1. یک کلاس `SourceAdapter` بنویسید که این‌ها را پیاده کند:
   - `discover()`: لیست Candidate شامل شناسه، URL و lastmod، به‌همراه تعداد فهرست‌شده و یادداشت پوشش.
   - `parse_job()`: خروجی `PageOutcome` با یکی از وضعیت‌های `active`، `expired`، `gone` یا `not_job`، به‌همراه `RawJob`.
   - `job_url()`
   - و ویژگی‌های `access_method`، `limitations`، `min_interval_minutes` و `complete_listing`.
2. آن را در `registry.py` اضافه کنید.
3. نام host را به `ALLOWED_HOSTS` در `http.py` اضافه کنید. این تنها راه درخواست به host جدید است.

### PoliteClient

- robots.txt با `urllib.robotparser` در **هر اجرا** دوباره خوانده می‌شود و هر URL پیش از درخواست با آن چک می‌شود.
- فقط hostهای مجاز درخواست می‌شوند و URL خارج از منبع رد می‌شود.
- Crawl-delay، فاصله حداقلی و jitter رعایت می‌شوند.
- Timeout داریم و Retry با backoff نمایی روی 5xx، timeout و خطای شبکه انجام می‌شود.
- 429 مقدار `Retry-After` را رعایت می‌کند.
- با سه بار 403 یا 429 پیاپی، یا نشانه CAPTCHA، استثنای `BlockedError` رخ می‌دهد: اجرا متوقف می‌شود و وضعیت منبع `blocked` می‌شود.

### Runner

**بودجه:** `COLLECTOR_MAX_PAGES_PER_RUN` (پیش‌فرض ۲۵۰ درخواست صفحه آگهی در هر اجرا). ترتیب اولویت:
1. آگهی‌های جدید
2. آگهی‌هایی که lastmod آن‌ها از آخرین دریافت ما جدیدتر است
3. بررسی دوباره آگهی‌هایی که از فهرست ناپدید شده‌اند (تأیید انقضا)
4. تازه‌سازی آگهی‌های قدیمی (فقط برای منابع بدون lastmod)

باقی‌مانده با عدد دقیق در `coverage_note` گزارش می‌شود.

**انقضای محتاطانه:** آگهی فقط وقتی `expired` می‌شود که **صفحه خودش** بگوید (404 یا 410، `isExpired`، یا نشانه انقضا)، آن هم در اجرایی که مسدود یا ناموفق نیست.
- در sitemap (که فهرست کامل است)، ناپدید شدن یک آگهی باعث بررسی فوری می‌شود.
- در جست‌وجو (فهرست ناقص)، فقط آگهی‌هایی که بیش از ۳ روز دیده نشده‌اند بررسی می‌شوند.
- اگر discovery خطا داشته باشد، هیچ آگهی‌ای بر اساس «ناپدید شدن» بررسی نمی‌شود.

**سلامت منبع:**

| وضعیت | شرط |
|---|---|
| `healthy` | خطای صفحه کمتر از ۲۰٪ |
| `degraded` | خطای بیشتر، یا discovery ناقص یا ناموفق |
| `blocked` | 403 یا 429 پیاپی، یا CAPTCHA |
| `disabled` | منبع توسط مدیر غیرفعال شده |

شکست یک منبع روی منبع دیگر اثری ندارد: هر منبع کار، lock و تراکنش جداگانه دارد.

**Baseline:** همه رویدادهای اولین اجرای موفق هر منبع با `is_baseline=true` ثبت می‌شوند و dispatcher هرگز برای آن‌ها اعلان نمی‌فرستد. به این ترتیب در اولین اجرا هزاران اعلان ارسال نمی‌شود.

### نرمال‌سازی (`normalize.py`)

- حروف عربی به فارسی (ي→ی، ك→ک و…) و ارقام فارسی و عربی به لاتین تبدیل می‌شوند.
- ZWNJ یکتا می‌شود و ZWNJ چسبیده به فاصله حذف می‌شود.
- کاراکترهای نامرئی و جهت‌دهی، تطویل و اعراب حذف می‌شوند.
- `compare_key()` برای تشخیص تغییر: بدون فاصله، ZWNJ، نقطه‌گذاری و حروف بزرگ و کوچک.
- `canonical_url()`: حذف query، fragment و پارامترهای رهگیری.
- حقوق «۲۰ تا ۳۰ میلیون»، «ریال به تومان» و «توافقی» به min و max ماهانه به تومان تبدیل می‌شود.

### تکرار و تغییر (`ingest.py`)

**تکرار:**
- `(source_id, source_job_id)` و `(source_id, canonical_url)` یکتا هستند.
- آگهی یکسان در دو سایت یک `dedup_key` مشترک دارد: هش «نام نرمال شرکت + عنوان + شهر». هر دو رکورد و منبع اصلی هر کدام حفظ می‌شوند و در صفحه جزئیات به هم پیوند دارند.
- شرکت با `normalized_name` یکی می‌شود؛ پسوندهای «شرکت»، «گروه»، «Co.» و مانند آن حذف می‌شوند.

**Snapshot و رویدادها:**
- `content_hash` روی `compare_key` فیلدهای معنادار حساب می‌شود.
- با تغییر هش، snapshot جدید ذخیره می‌شود و diff با snapshot قبلی ساخته می‌شود:

| رویداد | شرط و محتوای diff |
|---|---|
| `SALARY_CHANGED` | تغییر حقوق |
| `DESCRIPTION_CHANGED` | فقط اگر شباهت متن کمتر از ۰٫۹۷ باشد؛ diff خط‌به‌خط |
| `REQUIREMENTS_CHANGED` | مهارت‌های اضافه و حذف‌شده، سابقه |
| `WORK_MODE_CHANGED` | تغییر شیوه همکاری |
| `JOB_EXPIRED` و `JOB_REOPENED` | انقضا و فعال شدن دوباره |

جابه‌جایی HTML، فاصله و کد رهگیری هش را عوض نمی‌کند، پس رویدادی هم ساخته نمی‌شود (تست شده است).

**تاریخ انتشار:** فقط اگر منبع ذکر کند در `published_at` ثبت می‌شود. در غیر این صورت NULL می‌ماند و UI «اولین مشاهده» را با همین عنوان نشان می‌دهد.

## ۴. تحلیل (مستقل از Collector)

**`rules.py`** (همیشه اجرا می‌شود؛ قطعی و قابل توضیح):
- **مهارت‌ها:** دیکشنری حدود ۱۲۰ مهارت با نام فارسی و انگلیسی؛ تفکیک ضروری و ترجیحی از سرتیترهای «Nice to have» و «امتیاز محسوب می‌شود».
- **دسته‌بندی:**
  - الگوی عنوان با اطمینان ۰٫۶ تا ۰٫۹۵.
  - عنوان غیرفنی (فروش، مدیر محصول، مدرس، حسابدار) جریمه می‌شود، پس ذکر سطحی Python یا AI کافی نیست.
  - عنوان عمومی (Backend، Software Engineer) فقط با شواهد قوی از شرح شغل دسته می‌گیرد.
  - دسته ثانویه کنار دسته‌ای که از عنوان آمده، شواهد بیشتری لازم دارد.
  - Python به‌عنوان ابزار یک نقش دیگر، شغل Python Developer محسوب نمی‌شود.
  - SRE به نشانه عملی reliability نیاز دارد (SLO، on-call، incident)؛ ابزار مانیتورینگ به‌تنهایی کافی نیست.
- **سطح ارشدیت:** عنوان، سپس سابقه، سپس برچسب منبع؛ همراه با درجه اطمینان و شاهد.
- **امتیاز کیفیت آگهی (۰ تا ۱۰۰)** با شش معیار و دلیل هر کدام:

| معیار | امتیاز |
|---|---|
| شفافیت حقوق | ۲۵ |
| وضوح شرح وظایف | ۲۰ |
| مزایا و شرایط همکاری | ۱۵ |
| سازگاری سطح تجربه با انتظارات | ۱۵ |
| مشخص بودن مهارت‌های فنی | ۱۵ |
| اطلاعات قابل بررسی درباره کارفرما | ۱۰ |

- **هشدارها:** شرح کوتاه، مهارت‌های نامتناسب، نبود شرایط، ناسازگاری سطح با سابقه، کار بدون پرداخت، وظایف نامرتبط. همه «احتمالی» هستند.
- `RULES_VERSION`: با تغییر قواعد، bootstrap یک کار پس‌زمینه برای تحلیل دوباره آگهی‌هایی که تحلیل قاعده‌محور دارند در صف می‌گذارد.

**`ai/providers.py`:**
- **Claude:** `client.beta.messages.create` با:
  - `output_config.format=json_schema` (schema بسته از `LLMAnalysis`)
  - `effort` قابل تنظیم (پیش‌فرض low)
  - `fallbacks="default"`
  - بررسی `stop_reason` برای `refusal` و `max_tokens`
- **Ollama:** `/api/chat` با `format=<schema>`.

**`ai/engine.py`:**
- **ادغام:** هر دسته، مهارت، سطح یا هشدار مدل باید `evidence_quote` داشته باشد و این نقل‌قول باید (پس از نرمال‌سازی) **عیناً در متن آگهی** باشد، وگرنه کنار گذاشته و در `llm_notes` ثبت می‌شود. امتیاز کیفیت همیشه قطعی است.
- **Sync:** آگهی‌هایی در انتظار تحلیل می‌مانند که `input_hash` تحلیل فعلی‌شان (هش محتوا + موتور + مدل + نسخه prompt) با پیکربندی فعلی فرق کند، یا تحلیل قبلی خطا داشته باشد.
- **خطای مدل:** تحلیل قاعده‌محور حفظ می‌شود، خطا ثبت می‌شود و آگهی در صف Sync باقی می‌ماند.

**شفافیت شرکت (`company.py`):** مستقل از کیفیت آگهی است. بر اساس وب‌سایت، توضیحات، اندازه، حوزه، سال تأسیس، محصول و حضور در چند منبع؛ همراه با شواهد (منبع، URL و تاریخ) و درجه اطمینان. اگر کمتر از دو مورد اطلاعات پایه وجود داشته باشد، نتیجه **Unknown** است. درباره وضعیت مالی، پرداخت حقوق یا اعتبار شرکت ادعایی نمی‌شود.

**تطابق (`matching.py`):**

| بخش | امتیاز |
|---|---|
| مهارت‌های ضروری | ۴۰ |
| مهارت‌های ترجیحی | ۱۵ |
| سابقه | ۲۰ |
| شهر | ۱۰ |
| شیوه همکاری | ۱۵ |

برای هر بخش جزئیات نمایش داده می‌شود. اگر داده نامشخص باشد، نصف امتیاز آن بخش داده می‌شود.

**حقوق (`salary.py`):**
- **Reported:** همیشه اولویت دارد.
- **Estimated:** ابتدا از دیتاست فعال (تطبیق دسته، سطح و شهر؛ اطمینان بر اساس دقت تطبیق و تازگی سال داده)، و اگر نبود، از چارک‌های حقوق‌های اعلام‌شده آگهی‌های هم‌دسته و هم‌سطح (حداقل ۵ نمونه، ۱۸۰ روز اخیر).
- **Unknown:** در غیر این دو حالت؛ همراه با دلیل.

## ۵. پایگاه داده

جدول‌ها (مایگریشن `0001`):
- `users`، `sources`، `source_runs`، `companies`
- `jobs`، `job_categories`، `job_skills`، `job_snapshots`، `job_events`، `job_analyses`
- `salary_datasets`، `salary_benchmarks`
- `saved_searches`، `notification_subscriptions`، `notification_deliveries`
- `telegram_connections`، `audit_logs`، `app_settings`

**محدودیت‌های یکتا و ایندکس‌های کلیدی:**
- `jobs (source_id, source_job_id)` و `jobs (source_id, canonical_url)`
- `notification_deliveries (user_id, channel, job_event_id)` و `(user_id, channel, digest_key)` برای تضمین عدم تکرار در سطح پایگاه داده
- `job_analyses (job_id, is_current)`
- `saved_searches (user_id, name)` و `salary_datasets (name, version)`
- ایندکس روی وضعیت، تاریخ‌ها، شهر و استان، دسته و مهارت

## ۶. اعلان‌ها

**dispatcher هر دقیقه:**
1. رویدادهای جدید را با یک cursor پیمایش می‌کند. رویدادهای baseline و رویدادهای قدیمی‌تر از ساخت اشتراک کنار گذاشته می‌شوند.
2. فیلتر جست‌وجوی ذخیره‌شده **با همان SQL صفحه آگهی‌ها** (`filters.py`) روی آگهی اجرا می‌شود.
3. نوع رویداد، دسته‌ها و حداقل امتیاز تطابق بررسی می‌شوند.
4. کانال باید تأییدشده باشد: ایمیل verify شده یا تلگرام فعال.
5. `INSERT ... ON CONFLICT DO NOTHING`: اگر کاربر چند اشتراک منطبق داشته باشد هم فقط یک ارسال انجام می‌شود، و اجرای دوباره یا reset شدن cursor هم تکرار ایجاد نمی‌کند.
6. سقف ساعتی بررسی می‌شود.
7. ارسال انجام می‌شود. خطای موقت به `pending` با backoff منجر می‌شود؛ خطای دائمی (ربات مسدود، تنظیم نشده) به `failed`.

**گزارش روزانه:** در ساعت تنظیم‌شده (به وقت تهران)، یک پیام برای هر کاربر و کانال در هر روز.

## ۷. امنیت

| موضوع | پیاده‌سازی |
|---|---|
| احراز هویت | Argon2id برای رمز؛ JWT (HS256) در کوکی httpOnly، Secure و SameSite=Lax؛ Bearer هم پذیرفته می‌شود |
| دسترسی | `require_admin` روی همه `/admin/*`؛ کاربران فقط به جست‌وجوها و اشتراک‌های خودشان دسترسی دارند (۴۰۴ برای منابع دیگران) |
| CSRF | بررسی Origin در همه درخواست‌های تغییردهنده با کوکی |
| تزریق SQL | SQLAlchemy پارامتری؛ escape کردن LIKE؛ sort از whitelist |
| XSS | React escape؛ بدون `dangerouslySetInnerHTML`؛ CSP؛ قالب ایمیل Jinja2 با autoescape؛ HTML تلگرام escape |
| Secretها | `.env` (در git نیست)؛ secretهای UI با Fernet (`ENCRYPTION_KEY`)؛ API فقط `*_configured` برمی‌گرداند؛ scrub در لاگ (کلید، توکن ربات، رمزها)؛ لاگ httpx که URL حاوی توکن را چاپ می‌کند خاموش است |
| شبکه | `internal: true` برای Postgres و Redis؛ پورت backend منتشر نمی‌شود؛ فقط nginx بیرونی است |
| Rate limit | nginx (۲۰ درخواست بر ثانیه برای API، ۱۰ در دقیقه برای auth) و Redis (ورود، ثبت‌نام، اعلان آزمایشی، export، اتصال تلگرام) |
| تلگرام | کد اتصال یک‌بارمصرف هش‌شده با TTL ده دقیقه؛ chat_id فقط از update تلگرام؛ HMAC و تاریخ برای `initData`؛ secret token برای webhook |
| Prompt injection | آگهی به‌عنوان داده در `<job_ad>`؛ schema بسته؛ اعتبارسنجی نقل‌قول‌ها |
| Audit | ورود، ورود ناموفق، تغییر تنظیمات، اجرای دستی، بارگذاری دیتاست، تغییر کاربران |

## ۸. محدودیت‌های شناخته‌شده

- **پوشش:** محدود به کلیدواژه‌ها (jobinja) و slug (jobvision). پوشش هر اجرا گزارش می‌شود ولی **کامل نیست**.
- **Mini App:** به دامنه و گواهی معتبر نیاز دارد؛ با self-signed باز نمی‌شود.
- **ToS:** هیچ‌کدام از دو سایت API یا مجوز رسمی منتشر نکرده‌اند. استفاده فعلی با نرخ پایین و فقط برای داده عمومی است.
- **حقوق تخمینی:** بدون دیتاست معتبر یا حداقل ۵ نمونه، «نامشخص» است.

<a id="verification"></a>

## ۹. گزارش صحت‌سنجی

نتایج اجرای واقعی و همه بررسی‌ها در [README، بخش ۱۰](README.md#run-results) آمده است.

**باگ‌های واقعی که در همین فرایند پیدا و رفع شد:**
- `db.rollback()` در collector شمارنده‌های اجرا را reset می‌کرد. شمارنده‌ها اکنون بیرون از ORM نگهداری می‌شوند.
- خروجی CSV با session درخواست stream می‌شد و آن را «idle in transaction» نگه می‌داشت؛ این وضعیت قفل جدول را نگه می‌داشت و TRUNCATE و مایگریشن را معطل می‌کرد. اکنون session اختصاصی دارد.
- SDK نسخه 1.x شرکت Anthropic از `httpx2` استفاده می‌کند و respx آن را رهگیری نمی‌کند، پس تست‌ها ناخواسته به API واقعی می‌رسیدند (با کلید جعلی و پاسخ 401).
  - اکنون mock در سطح SDK انجام می‌شود.
  - در تست‌ها `ANTHROPIC_BASE_URL` به یک آدرس بسته اشاره می‌کند.
- چند سرویس هم‌زمان یک image را build می‌کردند و race رخ می‌داد. اکنون فقط backend image را می‌سازد.
- عنوان DevSecOps شناخته نمی‌شد، Python به‌عنوان «ابزار» شغل را Python Developer می‌کرد، و ابزار مانیتورینگ به‌تنهایی برچسب SRE می‌زد. قواعد اصلاح، `RULES_VERSION` بالا برده و داده موجود بازتحلیل شد.

</div>
