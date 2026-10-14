from app.collectors.base import SourceAdapter
from app.collectors.jobinja import JobinjaAdapter
from app.collectors.jobvision import JobvisionAdapter

ADAPTERS: dict[str, SourceAdapter] = {a.key: a for a in (JobinjaAdapter(), JobvisionAdapter())}


def get_adapter(key: str) -> SourceAdapter:
    return ADAPTERS[key]
