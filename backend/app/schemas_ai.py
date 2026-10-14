"""Structured analysis output - shared by the rule engine and the LLM providers.

The LLM must return `LLMAnalysis` (JSON-schema constrained, then validated here);
it is merged with the deterministic results into `AnalysisResult`.
"""
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["devops", "sre", "python", "ai_ml", "mlops_data"]
Level = Literal["junior", "mid", "senior", "staff", "principal", "unknown"]


class CategoryVerdict(BaseModel):
    category: Category
    subcategory: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    primary: bool = False


class SkillItem(BaseModel):
    name: str
    required: bool = True
    evidence: str | None = None
    origin: Literal["structured", "extracted", "llm"] = "extracted"


class SeniorityVerdict(BaseModel):
    level: Level = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    years_min: float | None = None


class QualityCriterion(BaseModel):
    key: str
    label: str
    score: int
    max: int
    reason: str


class QualityScore(BaseModel):
    total: int
    criteria: list[QualityCriterion]
    note: str = "این امتیاز فقط کیفیت و شفافیت اطلاعات آگهی را می‌سنجد، نه اعتبار شرکت."


class RedFlag(BaseModel):
    code: str
    message: str
    evidence: str | None = None
    severity: Literal["info", "warning"] = "warning"


class AnalysisResult(BaseModel):
    categories: list[CategoryVerdict]
    skills: list[SkillItem]
    seniority: SeniorityVerdict
    quality: QualityScore
    red_flags: list[RedFlag]
    summary_fa: str
    engine: Literal["rules", "claude", "ollama"] = "rules"
    model: str | None = None
    llm_notes: list[str] = Field(default_factory=list)
    disclaimer: str = "هشدارها احتمالی و قابل بررسی‌اند و حکم قطعی درباره شرکت نیستند."


# ---- what the LLM is asked to return --------------------------------------------------

class LLMCategory(BaseModel):
    category: Category
    subcategory: str
    confidence: float
    evidence_quote: str


class LLMSkill(BaseModel):
    name: str
    required: bool
    evidence_quote: str


class LLMSeniority(BaseModel):
    level: Level
    confidence: float
    evidence_quote: str


class LLMRedFlag(BaseModel):
    code: Literal["vague_description", "skill_sprawl", "missing_terms", "seniority_mismatch",
                  "unpaid_work", "unrelated_duties", "other"]
    message_fa: str
    evidence_quote: str


class LLMAnalysis(BaseModel):
    is_relevant_tech_role: bool
    categories: list[LLMCategory]
    skills: list[LLMSkill]
    seniority: LLMSeniority
    red_flags: list[LLMRedFlag]
    summary_fa: str


def llm_json_schema() -> dict:
    """JSON schema for output_config.format - every object closed, every field required."""

    def close(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}).keys())
            for v in node.values():
                close(v)
        elif isinstance(node, list):
            for v in node:
                close(v)
        return node

    schema = LLMAnalysis.model_json_schema()
    return close(schema)
