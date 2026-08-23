"""Structured contracts for the five manufacturing workflow agents."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ManufacturingIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_type: str = "general_manufacturing"
    objectives: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    requested_outputs: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    raw: dict[str, Any] = Field(default_factory=dict)


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


class AnalysisPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tasks: list[AnalysisTask] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


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
