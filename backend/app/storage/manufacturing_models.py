"""Manufacturing domain models and tenant access boundaries."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManufacturingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(alias="_id", min_length=1)
    tenant_id: str = Field(min_length=1)
    created_at: str = ""
    updated_at: str = ""

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)


class AccessLevel(str, Enum):
    TENANT = "tenant"
    GROUP = "group"
    FACTORY = "factory"
    WORKSHOP = "workshop"
    PRODUCTION_LINE = "production_line"
    PROJECT = "project"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AccessScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: AccessLevel = AccessLevel.TENANT
    resource_ids: list[str] = Field(default_factory=list)
    classification: DataClassification = DataClassification.INTERNAL

    @model_validator(mode="after")
    def require_scoped_resources(self) -> "AccessScope":
        if self.level != AccessLevel.TENANT and not self.resource_ids:
            raise ValueError(f"resource_ids is required for {self.level.value} access")
        return self


class Tenant(ManufacturingModel):
    name: str = Field(min_length=1)
    industry_codes: list[str] = Field(default_factory=list)
    status: str = "active"


class OrganizationUnit(ManufacturingModel):
    name: str = Field(min_length=1)
    unit_type: AccessLevel
    parent_id: Optional[str] = None
    country: str = ""
    region: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> "OrganizationUnit":
        if self.unit_type == AccessLevel.TENANT:
            raise ValueError("tenant must use the Tenant model")
        if self.unit_type in {AccessLevel.WORKSHOP, AccessLevel.PRODUCTION_LINE} and not self.parent_id:
            raise ValueError(f"parent_id is required for {self.unit_type.value}")
        return self


class ManufacturingEntity(ManufacturingModel):
    name: str = Field(min_length=1)
    access_scope: AccessScope = Field(default_factory=AccessScope)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Industry(ManufacturingEntity):
    code: str = ""
    parent_code: str = ""


class Process(ManufacturingEntity):
    industry_ids: list[str] = Field(default_factory=list)
    process_type: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class ProcessStep(ManufacturingEntity):
    process_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    equipment_ids: list[str] = Field(default_factory=list)
    parameter_ids: list[str] = Field(default_factory=list)


class ProcessRoute(ManufacturingEntity):
    product_id: str = Field(min_length=1)
    step_ids: list[str] = Field(min_length=1)
    version: str = "1.0"
    status: str = "draft"


class Product(ManufacturingEntity):
    product_code: str = ""
    material_ids: list[str] = Field(default_factory=list)
    process_route_ids: list[str] = Field(default_factory=list)


class Material(ManufacturingEntity):
    specification: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class EquipmentModel(ManufacturingEntity):
    manufacturer: str = ""
    model_number: str = ""
    capabilities: dict[str, Any] = Field(default_factory=dict)


class Equipment(ManufacturingEntity):
    equipment_model_id: str = ""
    asset_code: str = ""
    organization_unit_id: str = ""
    status: str = "active"


class Parameter(ManufacturingEntity):
    symbol: str = ""
    quantity_type: str = ""
    default_unit: str = ""


class ParameterWindow(ManufacturingModel):
    parameter_id: str = Field(min_length=1)
    process_step_id: str = ""
    original_value: str = Field(min_length=1)
    normalized_min: Optional[float] = None
    normalized_max: Optional[float] = None
    normalized_unit: str = ""
    applicability: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_range(self) -> "ParameterWindow":
        if self.normalized_min is not None and self.normalized_max is not None:
            if self.normalized_min > self.normalized_max:
                raise ValueError("normalized_min cannot exceed normalized_max")
        return self


class Defect(ManufacturingEntity):
    process_ids: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)


class RootCause(ManufacturingEntity):
    defect_ids: list[str] = Field(default_factory=list)
    evidence_level: str = "F"


class Inspection(ManufacturingEntity):
    defect_ids: list[str] = Field(default_factory=list)
    method: str = ""
    acceptance_criteria: dict[str, Any] = Field(default_factory=dict)


class CorrectiveAction(ManufacturingEntity):
    root_cause_ids: list[str] = Field(default_factory=list)
    verification_method: str = ""


class Measurement(ManufacturingModel):
    value: float
    unit: str = Field(min_length=1)
    period_start: str = ""
    period_end: str = ""
    organization_unit_id: str = ""
    process_id: str = ""
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class EnergyConsumption(Measurement):
    energy_type: str = Field(min_length=1)


class EmissionFactor(Measurement):
    emission_scope: str = ""
    factor_source: str = ""


class CarbonBaseline(Measurement):
    boundary: dict[str, Any] = Field(default_factory=dict)
    methodology: str = ""


class ImprovementMeasure(ManufacturingEntity):
    target_process_ids: list[str] = Field(default_factory=list)
    expected_benefits: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)


class FinancialEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = "CNY"
    capex: float = Field(ge=0)
    annual_opex: float = 0
    annual_savings: float = 0
    npv: Optional[float] = None
    irr: Optional[float] = None
    payback_years: Optional[float] = Field(default=None, ge=0)
    assumptions: dict[str, Any] = Field(default_factory=dict)


class CaseStudy(ManufacturingEntity):
    industry_ids: list[str] = Field(default_factory=list)
    process_ids: list[str] = Field(default_factory=list)
    baseline: dict[str, Any] = Field(default_factory=dict)
    measure_ids: list[str] = Field(default_factory=list)
    verified_results: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    evidence_level: str = "F"
    financials: Optional[FinancialEvaluation] = None


class ProjectCandidate(ManufacturingEntity):
    factory_id: str = Field(min_length=1)
    measure_ids: list[str] = Field(min_length=1)
    objectives: list[str] = Field(default_factory=list)
    financials: Optional[FinancialEvaluation] = None
    status: str = "candidate"
