"""Skills dictionary and job-category title patterns (Persian + English)."""
import re

# canonical skill -> (family, aliases). Aliases are regex fragments, matched case-insensitively
# on word boundaries against normalised text.
SKILLS: dict[str, tuple[str, list[str]]] = {
    # containers / orchestration / IaC
    "Docker": ("devops", [r"docker", r"داکر", r"دوکر"]),
    "Kubernetes": ("devops", [r"kubernetes", r"k8s", r"کوبرنتیز", r"کوبرنتیس", r"کوبرنیتیز"]),
    "OpenShift": ("devops", [r"openshift"]),
    "Helm": ("devops", [r"helm"]),
    "Terraform": ("devops", [r"terraform", r"ترافرم", r"تراform"]),
    "Ansible": ("devops", [r"ansible", r"انسیبل"]),
    "Puppet": ("devops", [r"puppet"]),
    "Chef": ("devops", [r"chef"]),
    "Vagrant": ("devops", [r"vagrant"]),
    "Packer": ("devops", [r"packer"]),
    "CI/CD": ("devops", [r"ci\s*/\s*cd", r"ci-cd", r"continuous integration", r"continuous delivery"]),
    "GitLab CI": ("devops", [r"gitlab[\s-]?ci"]),
    "GitLab": ("devops", [r"gitlab", r"گیت\s?لب"]),
    "GitHub Actions": ("devops", [r"github actions"]),
    "Jenkins": ("devops", [r"jenkins", r"جنکینز"]),
    "ArgoCD": ("devops", [r"argo\s?cd"]),
    "GitOps": ("devops", [r"gitops"]),
    "Git": ("general", [r"git(?![\s-]?(lab|hub|ops))", r"گیت(?!\s?لب)"]),
    "Linux": ("devops", [r"linux", r"لینوکس", r"ubuntu", r"centos", r"debian", r"red\s?hat", r"rhel"]),
    "Bash": ("devops", [r"bash", r"shell scripting", r"shell script", r"اسکریپت\s?نویسی"]),
    "Nginx": ("devops", [r"nginx", r"انجین\s?ایکس"]),
    "HAProxy": ("devops", [r"haproxy"]),
    "AWS": ("devops", [r"aws", r"amazon web services"]),
    "GCP": ("devops", [r"gcp", r"google cloud"]),
    "Azure": ("devops", [r"azure"]),
    "OpenStack": ("devops", [r"openstack"]),
    "VMware": ("devops", [r"vmware", r"vsphere", r"esxi"]),
    "Proxmox": ("devops", [r"proxmox"]),
    "Ceph": ("devops", [r"ceph"]),
    "Vault": ("devops", [r"hashicorp vault"]),
    "Consul": ("devops", [r"consul"]),
    "Istio": ("devops", [r"istio", r"service mesh"]),
    "Cilium": ("devops", [r"cilium"]),
    "Networking": ("devops", [r"tcp/ip", r"dns", r"شبکه\s?های\s?کامپیوتری"]),
    # observability / reliability
    "Prometheus": ("sre", [r"prometheus", r"پرومتئوس", r"پرومتیوس"]),
    "Grafana": ("sre", [r"grafana", r"گرافانا"]),
    "Loki": ("sre", [r"loki"]),
    "Elasticsearch": ("sre", [r"elastic\s?search", r"\belk\b", r"\befk\b"]),
    "Kibana": ("sre", [r"kibana"]),
    "Logstash": ("sre", [r"logstash"]),
    "Zabbix": ("sre", [r"zabbix", r"زبیکس"]),
    "Jaeger": ("sre", [r"jaeger"]),
    "OpenTelemetry": ("sre", [r"opentelemetry", r"otel"]),
    "Alertmanager": ("sre", [r"alert\s?manager"]),
    "SLO/SLI": ("sre", [r"slo", r"sli", r"error budget"]),
    "Incident Management": ("sre", [r"incident (management|response)", r"on[\s-]?call", r"post[\s-]?mortem"]),
    # python
    "Python": ("python", [r"python", r"پایتون", r"پایثون"]),
    "Django": ("python", [r"django", r"جنگو"]),
    "Django REST Framework": ("python", [r"django rest framework", r"\bdrf\b"]),
    "FastAPI": ("python", [r"fast\s?api"]),
    "Flask": ("python", [r"flask", r"فلسک"]),
    "Celery": ("python", [r"celery"]),
    "SQLAlchemy": ("python", [r"sqlalchemy"]),
    "Pandas": ("python", [r"pandas", r"پانداس"]),
    "NumPy": ("python", [r"numpy"]),
    "asyncio": ("python", [r"asyncio"]),
    "Pytest": ("python", [r"pytest"]),
    # AI / ML
    "PyTorch": ("ai_ml", [r"pytorch", r"torch"]),
    "TensorFlow": ("ai_ml", [r"tensorflow", r"تنسورفلو"]),
    "Keras": ("ai_ml", [r"keras"]),
    "scikit-learn": ("ai_ml", [r"scikit[\s-]?learn", r"sklearn"]),
    "Hugging Face": ("ai_ml", [r"hugging\s?face", r"transformers"]),
    "LLM": ("ai_ml", [r"llms?", r"large language models?", r"مدل(\s|‌)?های زبانی بزرگ"]),
    "LangChain": ("ai_ml", [r"langchain", r"llamaindex", r"llama[\s-]?index"]),
    "RAG": ("ai_ml", [r"rag", r"retrieval[\s-]augmented"]),
    "NLP": ("ai_ml", [r"nlp", r"natural language processing", r"پردازش زبان طبیعی"]),
    "Computer Vision": ("ai_ml", [r"computer vision", r"بینایی ماشین", r"پردازش تصویر"]),
    "OpenCV": ("ai_ml", [r"opencv"]),
    "Deep Learning": ("ai_ml", [r"deep learning", r"یادگیری عمیق"]),
    "Machine Learning": ("ai_ml", [r"machine learning", r"یادگیری ماشین"]),
    "XGBoost": ("ai_ml", [r"xgboost", r"lightgbm"]),
    # MLOps / data
    "MLflow": ("mlops_data", [r"mlflow"]),
    "Kubeflow": ("mlops_data", [r"kubeflow"]),
    "Airflow": ("mlops_data", [r"airflow"]),
    "Spark": ("mlops_data", [r"spark", r"pyspark"]),
    "Kafka": ("mlops_data", [r"kafka", r"کافکا"]),
    "Hadoop": ("mlops_data", [r"hadoop"]),
    "dbt": ("mlops_data", [r"dbt"]),
    "ClickHouse": ("mlops_data", [r"clickhouse"]),
    "Triton": ("mlops_data", [r"triton inference"]),
    "vLLM": ("mlops_data", [r"vllm"]),
    "Ray": ("mlops_data", [r"ray serve", r"\bray\b cluster"]),
    "ETL": ("mlops_data", [r"etl", r"elt", r"data pipelines?"]),
    "Feature Store": ("mlops_data", [r"feature store", r"feast"]),
    "Model Serving": ("mlops_data", [r"model serving", r"torchserve", r"bentoml", r"kserve", r"seldon"]),
    # data stores / messaging (general backend)
    "PostgreSQL": ("general", [r"postgres(ql)?", r"پستگرس"]),
    "MySQL": ("general", [r"mysql", r"mariadb"]),
    "MongoDB": ("general", [r"mongo\s?db", r"مونگو"]),
    "Redis": ("general", [r"redis", r"ردیس"]),
    "RabbitMQ": ("general", [r"rabbit\s?mq"]),
    "SQL": ("general", [r"sql(?!\s?alchemy)"]),
    "REST API": ("general", [r"rest(ful)?\s?api", r"restful"]),
    "gRPC": ("general", [r"grpc"]),
    "Microservices": ("general", [r"micro[\s-]?services?", r"میکروسرویس"]),
    # other stacks (used to detect unrelated skill sprawl)
    "Go": ("other_backend", [r"golang"]),
    "Java": ("other_backend", [r"java(?!script)", r"spring boot"]),
    "C#/.NET": ("other_backend", [r"c#", r"\.net", r"asp\.net", r"دات\s?نت"]),
    "PHP": ("other_backend", [r"php", r"laravel"]),
    "Node.js": ("other_backend", [r"node\.?js", r"nestjs", r"express\.js"]),
    "JavaScript": ("frontend", [r"javascript", r"\bjs\b", r"typescript"]),
    "React": ("frontend", [r"react(\.js)?", r"next\.?js"]),
    "Vue": ("frontend", [r"vue(\.js)?", r"nuxt"]),
    "Angular": ("frontend", [r"angular"]),
    "HTML/CSS": ("frontend", [r"html5?", r"css3?", r"tailwind", r"bootstrap"]),
    "Android": ("mobile", [r"android", r"kotlin"]),
    "iOS": ("mobile", [r"ios", r"swift"]),
    "Flutter": ("mobile", [r"flutter"]),
    "Photoshop": ("design", [r"photoshop", r"فتوشاپ", r"illustrator"]),
    "Figma": ("design", [r"figma"]),
    "Excel": ("office", [r"excel", r"اکسل"]),
    "Accounting software": ("office", [r"حسابداری", r"سپیدار", r"همکاران سیستم"]),
    "Cisco": ("network", [r"cisco", r"ccna", r"ccnp", r"سیسکو"]),
    "MikroTik": ("network", [r"mikrotik", r"میکروتیک"]),
    "Windows Server": ("network", [r"windows server", r"active directory", r"اکتیو دایرکتوری"]),
    "CCTV": ("network", [r"دوربین مدار\s?بسته", r"cctv"]),
}

_EN = re.compile(r"[a-z]")


def _compile(alias: str) -> re.Pattern:
    # English aliases need ASCII word boundaries; Persian ones need whitespace/edge boundaries.
    if _EN.search(alias):
        return re.compile(rf"(?<![a-z0-9+#]){alias}(?![a-z0-9+#])", re.I)
    return re.compile(rf"(?<![\w؀-ۿ]){alias}(?![\w؀-ۿ])")


SKILL_PATTERNS: list[tuple[str, str, list[re.Pattern]]] = [
    (name, fam, [_compile(a) for a in aliases]) for name, (fam, aliases) in SKILLS.items()
]
SKILL_FAMILY = {name: fam for name, (fam, _) in SKILLS.items()}


def canonical_skill(raw: str) -> str | None:
    """Map a source-provided skill label ('Shell scripting', 'Docker') to the dictionary."""
    text = raw.strip()
    for name, _fam, pats in SKILL_PATTERNS:
        if text.lower() == name.lower() or any(p.fullmatch(text) or p.search(text) for p in pats):
            return name
    return None


def find_skills(text: str) -> dict[str, str]:
    """All dictionary skills in text -> the matched snippet (evidence)."""
    found: dict[str, str] = {}
    for name, _fam, pats in SKILL_PATTERNS:
        for p in pats:
            m = p.search(text)
            if m:
                found[name] = m.group(0)
                break
    return found


CATEGORY_LABELS_FA = {
    "devops": "DevOps / Platform",
    "sre": "SRE / Reliability",
    "python": "Python Development",
    "ai_ml": "AI / Machine Learning",
    "mlops_data": "MLOps / Data",
}

# (category, subcategory, title regex, confidence). Order matters only for the
# "primary" pick - every match is kept (a job can be SRE *and* DevOps).
TITLE_RULES: list[tuple[str, str, str, float]] = [
    ("sre", "Site Reliability Engineer", r"\bsre\b|site reliability|مهندس قابلیت اطمینان", 0.95),
    ("sre", "Reliability Engineer", r"reliability engineer", 0.9),
    ("sre", "Production Engineer", r"production engineer", 0.85),
    ("sre", "Observability Engineer", r"observability|مشاهده\s?پذیری", 0.9),
    ("sre", "Monitoring Engineer", r"monitoring (engineer|specialist|expert)|کارشناس مانیتورینگ|مهندس مانیتورینگ", 0.8),
    ("mlops_data", "MLOps Engineer", r"\bmlops\b|ml ops|ام ال اپس", 0.95),
    ("mlops_data", "LLMOps Engineer", r"llm\s?ops", 0.95),
    ("mlops_data", "AI Infrastructure Engineer", r"ai infrastructure|زیرساخت هوش مصنوعی", 0.9),
    ("mlops_data", "Model Serving Engineer", r"model serving|inference engineer", 0.9),
    ("mlops_data", "ML Platform Engineer", r"ml platform|machine learning platform", 0.9),
    ("mlops_data", "Data Engineer", r"data engineer|مهندس داده|مهندسی داده|big data engineer|کارشناس داده های کلان", 0.9),
    ("devops", "DevSecOps Engineer", r"devsecops|dev sec ops|دوسک\s?آپس", 0.95),
    ("devops", "DevOps Engineer", r"devops|dev ops|دواپس|دوآپس|دو آپس|دِواپس|دوپس", 0.95),
    ("devops", "Platform Engineer", r"platform engineer|مهندس پلتفرم", 0.85),
    ("devops", "Kubernetes Engineer", r"kubernetes|k8s|کوبرنتیز", 0.9),
    ("devops", "Cloud Engineer", r"cloud (engineer|architect|specialist|administrator)|مهندس (ابر|کلاد)|کارشناس (کلاد|ابر)", 0.85),
    ("devops", "Linux Engineer", r"linux (engineer|admin|administrator|specialist|expert|sysadmin)|(کارشناس|مهندس|مدیر)( ارشد)? (سیستم )?لینوکس|لینوکس ادمین", 0.85),
    ("devops", "GitOps Engineer", r"gitops", 0.9),
    ("devops", "Infrastructure Automation", r"infrastructure automation|اتوماسیون زیرساخت", 0.85),
    ("devops", "Infrastructure Engineer", r"infrastructure engineer|مهندس زیرساخت(?! شبکه)|کارشناس زیرساخت(?! شبکه)", 0.6),
    ("ai_ml", "LLM Engineer", r"\bllm\b|large language|مدل(های)? زبانی", 0.9),
    ("ai_ml", "Generative AI Engineer", r"generative ai|gen ?ai|هوش مصنوعی مولد", 0.9),
    ("ai_ml", "NLP Engineer", r"\bnlp\b|natural language|پردازش زبان", 0.9),
    ("ai_ml", "Computer Vision Engineer", r"computer vision|بینایی ماشین|بینایی کامپیوتر|پردازش تصویر", 0.9),
    ("ai_ml", "Deep Learning Engineer", r"deep learning|یادگیری عمیق", 0.9),
    ("ai_ml", "ML Engineer", r"machine learning|\bml\b engineer|یادگیری ماشین|ماشین لرنینگ", 0.9),
    ("ai_ml", "AI Engineer", r"\bai\b (engineer|developer|specialist|researcher)|(مهندس|متخصص|برنامه نویس|توسعه دهنده|کارشناس|پژوهشگر) هوش مصنوعی|\bai\b$|^\bai\b", 0.85),
    ("ai_ml", "Applied AI Engineer", r"applied ai", 0.9),
    ("ai_ml", "Data Scientist", r"data scien|دانشمند داده|علم داده|دیتا ساینس", 0.7),
    ("python", "Django Developer", r"django|جنگو", 0.95),
    ("python", "FastAPI Developer", r"fast ?api", 0.95),
    ("python", "Python Automation Engineer", r"python automation|اتوماسیون( با)? پایتون", 0.9),
    ("python", "Backend Python Developer", r"(back[\s-]?end|بک[\s-]?اند|بکند).*(python|پایتون)|(python|پایتون).*(back[\s-]?end|بک[\s-]?اند|بکند)", 0.95),
    ("python", "Python Developer", r"python|پایتون", 0.9),
]

# Titles that are not engineering roles even if they mention AI/Python
# ("AI product manager", "sales of AI products", "Python teacher").
NEGATIVE_TITLE = re.compile(
    r"product (manager|owner)|مدیر محصول|مالک محصول|فروش|sales|marketing|بازاریاب|تولید محتوا|content|"
    r"مدرس|teacher|instructor|tutor|آموزش|پشتیبانی مشتری|customer support|اپراتور|operator|"
    r"حسابدار|account manager|recruit|منابع انسانی|\bhr\b|طراح گرافیک|ui/ux designer|copywriter",
    re.I,
)

# Generic engineering titles that may be categorised from strong description evidence.
GENERIC_TECH_TITLE = re.compile(
    r"back[\s-]?end|بک[\s-]?اند|بکند|software (engineer|developer)|مهندس نرم\s?افزار|برنامه\s?نویس|"
    r"توسعه\s?دهنده|developer|engineer|مهندس|programmer|technical lead|tech lead|team lead|سرپرست فنی|"
    r"مدیر فنی|\bcto\b|system administrator|sysadmin|کارشناس فنی|کارشناس it|کارشناس فناوری",
    re.I,
)

# Strong description evidence needed to categorise a generic title.
# Order matters: Python is evaluated last - it only applies when nothing else did.
DESCRIPTION_RULES: dict[str, tuple[str, int]] = {
    "devops": ("DevOps Engineer", 4),
    "sre": ("Site Reliability Engineer", 4),
    "ai_ml": ("ML Engineer", 3),
    "mlops_data": ("Data Engineer", 3),
    "python": ("Backend Python Developer", 2),  # Python required (+ python-family skills)
}
# Extra evidence needed for a *secondary* category next to a title-based one.
SECONDARY_EXTRA = 2
