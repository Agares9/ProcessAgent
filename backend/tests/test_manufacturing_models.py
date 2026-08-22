"""Manufacturing domain model validation tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.storage.manufacturing_models import (
    AccessLevel,
    AccessScope,
    CaseStudy,
    FinancialEvaluation,
    OrganizationUnit,
    ParameterWindow,
    ProcessRoute,
    Tenant,
)
from app.storage.store import COLLECTIONS


def test_private_manufacturing_models_require_tenant_id():
    with pytest.raises(ValidationError):
        Tenant(_id="tenant_acme", tenant_id="", name="Acme Manufacturing")


def test_organization_hierarchy_requires_parent_for_workshop():
    with pytest.raises(ValidationError, match="parent_id is required"):
        OrganizationUnit(
            _id="workshop_1",
            tenant_id="tenant_acme",
            name="Machining Workshop",
            unit_type=AccessLevel.WORKSHOP,
        )


def test_non_tenant_access_scope_requires_resource_ids():
    with pytest.raises(ValidationError, match="resource_ids is required"):
        AccessScope(level=AccessLevel.FACTORY)


def test_parameter_window_preserves_original_and_normalized_values():
    window = ParameterWindow(
        _id="window_1",
        tenant_id="tenant_acme",
        parameter_id="cutting_speed",
        original_value="120-180 m/min (for 45 steel)",
        normalized_min=120,
        normalized_max=180,
        normalized_unit="m/min",
        applicability={"material": "45 steel"},
        source_refs=[{"doc_id": "standard_1", "page": 17}],
    )
    assert window.to_mongo()["_id"] == "window_1"
    assert window.applicability["material"] == "45 steel"


def test_parameter_window_rejects_reversed_range():
    with pytest.raises(ValidationError, match="normalized_min cannot exceed"):
        ParameterWindow(
            _id="window_bad",
            tenant_id="tenant_acme",
            parameter_id="temperature",
            original_value="200-180 C",
            normalized_min=200,
            normalized_max=180,
            normalized_unit="degC",
        )


def test_case_study_keeps_evidence_limits_and_financials():
    case = CaseStudy(
        _id="case_1",
        tenant_id="tenant_acme",
        name="Compressed air optimization",
        evidence_level="B",
        limitations=["Single factory validation"],
        financials=FinancialEvaluation(capex=500000, annual_savings=240000, payback_years=2.1),
    )
    assert case.financials is not None
    assert case.financials.payback_years == 2.1


def test_process_route_requires_at_least_one_step():
    with pytest.raises(ValidationError):
        ProcessRoute(
            _id="route_1",
            tenant_id="tenant_acme",
            name="Empty route",
            product_id="product_1",
            step_ids=[],
        )


def test_manufacturing_collections_are_registered():
    assert {"tenants", "organization_units", "processes", "case_studies"}.issubset(COLLECTIONS)
