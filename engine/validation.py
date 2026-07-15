"""
Cross-field and cross-object business-rule validation.

Pydantic (engine/schemas.py) already enforces single-field constraints
(non-negative costs, probabilities in [0, 1], etc.). This module checks
relationships *between* fields and *between* objects that Pydantic field
validators cannot express on their own -- e.g. a triangular dwell-time
distribution where min > mode, or two funnel stages sharing the same
stage_order.

Every public `validate_*` function returns a list of human-readable error
strings (empty list == valid). `raise_if_errors` turns a non-empty list into
an `EngineValidationError` for callers that want fail-fast behavior.
"""

from __future__ import annotations

from engine.schemas import (
    CapacityEntry,
    CompanyAssumptions,
    CustomerConcentrationEntry,
    FunnelStage,
    UnitEconomics,
)


class EngineValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def raise_if_errors(errors: list[str]) -> None:
    if errors:
        raise EngineValidationError(errors)


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------


def validate_funnel_stage(stage: FunnelStage) -> list[str]:
    errors: list[str] = []
    prefix = f"Funnel stage '{stage.stage_name}'"

    if stage.dwell_min_months > stage.dwell_mode_months:
        errors.append(f"{prefix}: dwell_min_months ({stage.dwell_min_months}) exceeds dwell_mode_months ({stage.dwell_mode_months})")
    if stage.dwell_mode_months > stage.dwell_max_months:
        errors.append(f"{prefix}: dwell_mode_months ({stage.dwell_mode_months}) exceeds dwell_max_months ({stage.dwell_max_months})")
    if stage.dwell_min_months > stage.dwell_max_months:
        errors.append(f"{prefix}: dwell_min_months ({stage.dwell_min_months}) exceeds dwell_max_months ({stage.dwell_max_months})")

    return errors


def validate_funnel_stages(stages: list[FunnelStage]) -> list[str]:
    errors: list[str] = []
    if not stages:
        errors.append("Funnel must contain at least one stage")
        return errors

    for stage in stages:
        errors.extend(validate_funnel_stage(stage))

    orders = [s.stage_order for s in stages]
    if len(set(orders)) != len(orders):
        errors.append("Funnel stages must have unique stage_order values")

    names = [s.stage_name for s in stages]
    if len(set(names)) != len(names):
        errors.append("Funnel stages must have unique stage_name values")

    return errors


# ---------------------------------------------------------------------------
# Company assumptions / utilization ramp
# ---------------------------------------------------------------------------


def validate_company_assumptions(assumptions: CompanyAssumptions) -> list[str]:
    errors: list[str] = []

    ramp = assumptions.utilization_ramp
    if not ramp:
        errors.append("utilization_ramp must contain at least one point")
        return errors

    months = [p.month_since_commissioning for p in ramp]
    if len(set(months)) != len(months):
        errors.append("utilization_ramp months must be unique")

    sorted_ramp = sorted(ramp, key=lambda p: p.month_since_commissioning)
    if sorted_ramp != ramp:
        errors.append("utilization_ramp must be sorted by month_since_commissioning")

    prev_util = None
    for point in sorted_ramp:
        if prev_util is not None and point.utilization < prev_util:
            errors.append(
                f"utilization_ramp must be non-decreasing (month {point.month_since_commissioning} "
                f"utilization {point.utilization} < prior {prev_util})"
            )
        prev_util = point.utilization

    if assumptions.deployment_teams == 0 and assumptions.units_per_team_monthly > 0:
        errors.append("units_per_team_monthly is set but deployment_teams is 0 -- implementation capacity is impossible")

    return errors


# ---------------------------------------------------------------------------
# Unit economics
# ---------------------------------------------------------------------------


def validate_unit_economics(economics: UnitEconomics) -> list[str]:
    errors: list[str] = []

    if economics.monthly_base_revenue == 0 and economics.usage_price * economics.expected_monthly_usage == 0:
        errors.append("Unit economics must include either monthly_base_revenue or usage-based revenue (usage_price x expected_monthly_usage)")

    if economics.upfront_customer_payment > economics.hardware_cost_per_unit + economics.deployment_cost_per_unit:
        errors.append(
            "upfront_customer_payment exceeds hardware_cost_per_unit + deployment_cost_per_unit -- "
            "this would make net upfront deployment investment negative, which is inconsistent for a RaaS preset"
        )

    return errors


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


def validate_capacity_entry(entry: CapacityEntry) -> list[str]:
    errors: list[str] = []
    if entry.available_capacity == 0 and entry.upfront_cost == 0 and entry.monthly_cost == 0:
        errors.append(f"Capacity entry '{entry.capacity_type}' has zero capacity and zero cost -- likely an incomplete input")
    return errors


def validate_capacity_entries(entries: list[CapacityEntry]) -> list[str]:
    errors: list[str] = []
    for entry in entries:
        errors.extend(validate_capacity_entry(entry))
    return errors


# ---------------------------------------------------------------------------
# Customer concentration
# ---------------------------------------------------------------------------


def validate_customer_concentration_entries(entries: list[CustomerConcentrationEntry]) -> list[str]:
    errors: list[str] = []
    if not entries:
        errors.append("Customer concentration list must contain at least one customer")
        return errors

    ids = [e.customer_id for e in entries]
    if len(set(ids)) != len(ids):
        errors.append("customer_id values must be unique")

    if all(e.contracted_backlog == 0 for e in entries):
        errors.append("All customers have zero contracted_backlog -- backlog concentration cannot be computed")

    return errors
