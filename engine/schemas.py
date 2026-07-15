"""
Domain schemas for the robotics deployment decision engine.

Core Release scope (spec §21.1 / §25):
  - commercial_model is fixed to "raas" (direct_sale / hybrid are Expansion
    Release, §21.2 — the field is typed to allow only "raas" for now so the
    rest of the engine cannot silently assume an unbuilt preset).
  - CustomerConcentration carries all four value fields from the spec's
    §15.4 schema, but Core Release concentration logic (engine/concentration.py)
    only operates on `contracted_backlog`. The other fields exist so the
    schema doesn't have to change shape when revenue/installed-base/projected
    bases are added later.

All models are Pydantic v2 BaseModels. Field-level constraints (non-negative,
probabilities in [0, 1], etc.) are enforced here. Cross-field and cross-object
business-rule checks (e.g. dwell_min <= dwell_mode <= dwell_max) live in
engine/validation.py, not here.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

CommercialModel = Literal["raas"]


# ---------------------------------------------------------------------------
# Entity hierarchy (spec §3)
# ---------------------------------------------------------------------------


class Pilot(BaseModel):
    pilot_id: str
    site_id: str
    unit_count: int = Field(ge=0)
    start_month: int = Field(ge=0)
    technically_accepted: bool = False


class Site(BaseModel):
    site_id: str
    account_id: str
    name: str
    pilots: list[Pilot] = Field(default_factory=list)


class Account(BaseModel):
    account_id: str
    name: str
    sites: list[Site] = Field(default_factory=list)
    industry: Optional[str] = None
    geography: Optional[str] = None


# ---------------------------------------------------------------------------
# Company Assumptions Schema (spec §15.1)
# ---------------------------------------------------------------------------


class UtilizationRampPoint(BaseModel):
    """One point in a utilization ramp: months since commissioning -> utilization fraction."""

    month_since_commissioning: int = Field(ge=0)
    utilization: float = Field(ge=0.0, le=1.0)


class CompanyAssumptions(BaseModel):
    commercial_model: CommercialModel = "raas"
    opening_cash: float
    fixed_operating_cost_monthly: float = Field(ge=0)
    manufacturing_capacity_monthly: float = Field(ge=0)
    deployment_teams: int = Field(ge=0)
    units_per_team_monthly: float = Field(ge=0)
    service_units_per_fte: float = Field(gt=0)
    utilization_ramp: list[UtilizationRampPoint]


# ---------------------------------------------------------------------------
# Unit Economics Schema (spec §15.2) -- RaaS preset only
# ---------------------------------------------------------------------------


class UnitEconomics(BaseModel):
    hardware_cost_per_unit: float = Field(ge=0)
    deployment_cost_per_unit: float = Field(ge=0)
    upfront_customer_payment: float = Field(ge=0, default=0.0)
    monthly_base_revenue: float = Field(ge=0)
    usage_price: float = Field(ge=0, default=0.0)
    expected_monthly_usage: float = Field(ge=0, default=0.0)
    monthly_variable_support_cost: float = Field(ge=0)
    contract_term_months: int = Field(gt=0)
    residual_value: float = Field(ge=0, default=0.0)


# ---------------------------------------------------------------------------
# Funnel Schema (spec §15.3)
# ---------------------------------------------------------------------------


class FunnelStage(BaseModel):
    stage_name: str
    stage_order: int = Field(ge=0)
    conversion_probability: float = Field(ge=0.0, le=1.0)
    dwell_min_months: float = Field(ge=0)
    dwell_mode_months: float = Field(ge=0)
    dwell_max_months: float = Field(ge=0)
    expected_units: float = Field(ge=0, default=0.0)
    expansion_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    expansion_multiple: float = Field(ge=0.0, default=1.0)


# ---------------------------------------------------------------------------
# Customer Concentration Schema (spec §15.4)
# ---------------------------------------------------------------------------


class CustomerConcentrationEntry(BaseModel):
    customer_id: str
    customer_name: str
    recognized_revenue: float = Field(ge=0, default=0.0)
    contracted_backlog: float = Field(ge=0, default=0.0)
    operational_units: float = Field(ge=0, default=0.0)
    projected_revenue: float = Field(ge=0, default=0.0)
    industry: Optional[str] = None
    geography: Optional[str] = None


ConcentrationBasis = Literal["backlog"]
"""Core Release supports backlog concentration only (spec §25 scope constraint).
Revenue / installed-base / projected-revenue bases are Expansion Release."""


# ---------------------------------------------------------------------------
# Capacity Schema (spec §15.5)
# ---------------------------------------------------------------------------


CapacityType = Literal["manufacturing", "implementation", "commissioning", "field_service"]


class CapacityEntry(BaseModel):
    capacity_type: CapacityType
    available_capacity: float = Field(ge=0)
    unit_of_measure: str
    activation_date: Optional[date] = None
    lead_time_months: float = Field(ge=0, default=0.0)
    upfront_cost: float = Field(ge=0, default=0.0)
    monthly_cost: float = Field(ge=0, default=0.0)
    ramp_months: float = Field(ge=0, default=0.0)


# ---------------------------------------------------------------------------
# Source classification (spec §11)
# ---------------------------------------------------------------------------

SourceClassification = Literal["disclosed", "derived", "assumed", "scenario"]


class SourceRegistryEntry(BaseModel):
    metric_id: str
    company: str
    metric_name: str
    value: str
    unit: str
    as_of_date: Optional[date] = None
    source_title: str
    source_url: Optional[str] = None
    source_type: str
    classification: SourceClassification
    confidence: str
    notes: Optional[str] = None
