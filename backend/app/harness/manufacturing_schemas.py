"""兼容制造业的通用场景决策数据契约。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScenarioIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_type: str = "general_manufacturing"
    industry: str = "manufacturing"
    domain: str = "manufacturing"
    business_domain: str = "general"
    scenario_type: str = "optimization"
    response_mode: Literal["analysis", "capability_info", "boundary_redirect"] = "analysis"
    complexity: Literal["simple", "standard", "complex"] = "standard"
    objectives: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    processes: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _compatibility_mapping(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        value = dict(data)
        # Accept both old plural manufacturing fields and the new generic names.
        if not value.get("industry") and value.get("industries"):
            value["industry"] = value["industries"][0]
        if not value.get("entities"):
            entities = []
            for key in ("processes", "equipment", "materials"):
                for item in value.get(key, []) or []:
                    entities.append({"type": key[:-1], "name": item})
            value["entities"] = entities
        elif isinstance(value.get("entities"), dict):
            # LLMs may return a compact object (e.g. {"store_count": 30})
            # although the public contract uses a list of entity records.
            value["entities"] = [
                {"type": str(key), "value": item} for key, item in value["entities"].items()
            ]
        elif isinstance(value.get("entities"), list):
            value["entities"] = [
                item if isinstance(item, dict) else {"type": "entity", "name": str(item)}
                for item in value["entities"]
            ]
        if isinstance(value.get("metrics"), list):
            metrics: dict[str, Any] = {}
            for index, item in enumerate(value["metrics"]):
                if isinstance(item, dict) and item.get("name"):
                    metrics[str(item["name"])] = item.get("value")
                else:
                    metrics[f"metric_{index + 1}"] = item
            value["metrics"] = metrics
        return value


# Public compatibility name retained for existing integrations and tests.
ManufacturingIntent = ScenarioIntent


class ContextFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: Any
    source_type: Literal["user_input", "enterprise_document", "public_document", "assumption"]
    source_id: str = ""
    page_start: int | None = None
    page_end: int | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class EnterpriseContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = "default_company"
    company_name: str | None = None
    industries: list[str] = Field(default_factory=list)
    industry: str | None = None
    domain: str | None = None
    scenario_type: str | None = None
    entities: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    stores: list[dict[str, Any]] = Field(default_factory=list)
    warehouses: list[dict[str, Any]] = Field(default_factory=list)
    vehicles: list[dict[str, Any]] = Field(default_factory=list)
    routes: list[dict[str, Any]] = Field(default_factory=list)
    factories: list[dict[str, Any]] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    current_problems: list[str] = Field(default_factory=list)
    baseline_metrics: dict[str, Any] = Field(default_factory=dict)
    targets: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    facts: list[ContextFact] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class AnalysisTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    title: str
    objective: str
    role: str = "general_analysis"
    priority: int = Field(default=1, ge=1)
    dependencies: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    allowed_skills: list[str] = Field(default_factory=list)
    input_data: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=60, ge=1, le=900)
    completion_criteria: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_llm_lists(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        value = dict(data)
        for field in ("dependencies", "required_capabilities", "allowed_skills", "completion_criteria"):
            item = value.get(field)
            if isinstance(item, str):
                value[field] = [item]
        return value


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[AnalysisTask] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


AllowedAnalysisSkill = Literal[
    "retrieve", "understand", "analyze", "compare", "calculate", "optimize", "check", "verify",
    "search_manufacturing_knowledge", "search_case_studies", "get_document_evidence",
    "check_applicability", "compare_technical_options", "extract_process_parameters",
    "calculate_project_financials", "calculate_energy_savings", "calculate_emission_reduction",
    "verify_citations", "check_constraint_compliance",
]


class AnalysisTaskDraft(AnalysisTask):
    allowed_skills: list[AllowedAnalysisSkill] = Field(min_length=1)


class AnalysisPlanDraft(BaseModel):
    """Only the task list is model-generated; trusted context is injected by code."""

    model_config = ConfigDict(extra="forbid")
    tasks: list[AnalysisTaskDraft] = Field(min_length=1)


class EvidenceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    value: Any = None
    source_id: str = ""
    chunk_id: str = ""
    page_start: int | None = None
    page_end: int | None = None
    excerpt: str = ""
    visibility: Literal["public", "enterprise_private"] = "public"


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    status: Literal["completed", "failed", "skipped"]
    summary: str = ""
    artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    data_schema: str = "v1"
    sources: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    unsupported_claims: list[str] = Field(default_factory=list)
    citation_errors: list[str] = Field(default_factory=list)
    numeric_errors: list[str] = Field(default_factory=list)
    assumption_errors: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)


class ExecutiveSolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str = ""
    problem_definition: str = ""
    findings: list[dict[str, Any]] = Field(default_factory=list)
    recommended_actions: list[dict[str, Any]] = Field(default_factory=list)
    implementation_roadmap: list[dict[str, Any]] = Field(default_factory=list)
    risks_and_constraints: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    citations: list[EvidenceArtifact] = Field(default_factory=list)
