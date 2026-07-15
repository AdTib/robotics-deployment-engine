"""
Fleet and unit economics engine (spec sections 6-7) -- RaaS preset only.

Core Release scope (spec section 21.1 / section 25 scope constraint): only
the Robotics-as-a-Service commercial-model preset is implemented. Direct-sale
and hybrid presets are Expansion Release (section 21.2) and are intentionally
not built here -- there is no code path for them to avoid an unused,
untested abstraction.

This module keeps the three breakeven concepts spec section 22 explicitly
requires never be conflated:
  - Operating Breakeven Fleet Size (section 7.7): steady-state fleet size at
    which ANNUAL contribution margin covers annual fixed operating costs.
    Says nothing about cash timing.
  - Unit Deployment Payback Period (section 7.8): how long a SINGLE unit
    takes to repay its own net upfront deployment investment.
  - Company Cash Breakeven Month (section 7.9): the first month the WHOLE
    COMPANY's cumulative cash flow (excluding opening cash) is non-negative.

Modeling assumptions made explicit here (label: assumed, per spec section
11.1 -- override via function arguments as needed):
  - Both revenue per unit and variable support cost per unit scale with the
    same utilization-ramp fraction (spec section 7.3/7.4 allow costs to vary
    by utilization; this applies one ramp curve to both for simplicity).
  - A unit stops generating revenue/cost and leaves the active fleet after
    `contract_term_months`, with no auto-renewal modeled in Core Release.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.schemas import UnitEconomics, UtilizationRampPoint


# ---------------------------------------------------------------------------
# Utilization ramp lookup
# ---------------------------------------------------------------------------


def utilization_at(ramp: list[UtilizationRampPoint], month_since_commissioning: int) -> float:
    """Step-function lookup: utilization fraction at `month_since_commissioning`,
    using the ramp point with the largest month_since_commissioning <= the
    queried month. Before the first defined point, utilization is 0."""
    if month_since_commissioning < 0:
        return 0.0
    sorted_ramp = sorted(ramp, key=lambda p: p.month_since_commissioning)
    applicable = [p for p in sorted_ramp if p.month_since_commissioning <= month_since_commissioning]
    if not applicable:
        return 0.0
    return applicable[-1].utilization


# ---------------------------------------------------------------------------
# Per-unit economics (spec section 7.1-7.6)
# ---------------------------------------------------------------------------


def upfront_deployment_cost_per_unit(economics: UnitEconomics) -> float:
    """Spec 7.1 (RaaS schema has no separate integration/training/site-launch
    fields, so hardware + deployment cost together represent the full
    upfront deployment cost)."""
    return economics.hardware_cost_per_unit + economics.deployment_cost_per_unit


def net_upfront_deployment_investment(economics: UnitEconomics) -> float:
    return upfront_deployment_cost_per_unit(economics) - economics.upfront_customer_payment


def revenue_per_unit_at_utilization(economics: UnitEconomics, utilization: float) -> float:
    """Spec 7.2, RaaS-scoped: recurring base fee + usage revenue, scaled by
    utilization (usage revenue is naturally utilization-driven; base fee is
    treated the same way here as a simplifying Core Release assumption)."""
    full_revenue = economics.monthly_base_revenue + economics.usage_price * economics.expected_monthly_usage
    return full_revenue * utilization


def variable_cost_per_unit_at_utilization(economics: UnitEconomics, utilization: float) -> float:
    """Spec 7.4, scaled by utilization (see module docstring for the ramp assumption)."""
    return economics.monthly_variable_support_cost * utilization


def contribution_margin_per_unit_at_utilization(economics: UnitEconomics, utilization: float) -> float:
    """Spec 7.5."""
    return revenue_per_unit_at_utilization(economics, utilization) - variable_cost_per_unit_at_utilization(economics, utilization)


def annual_contribution_margin_per_unit(economics: UnitEconomics) -> float:
    """Spec 7.6: steady-state (utilization = 1.0) annual contribution margin."""
    return 12.0 * contribution_margin_per_unit_at_utilization(economics, utilization=1.0)


# ---------------------------------------------------------------------------
# Operating breakeven fleet size (spec 7.7) -- NOT cash breakeven
# ---------------------------------------------------------------------------


@dataclass
class OperatingBreakevenResult:
    label: str
    operating_breakeven_fleet_size: float
    annual_fixed_operating_costs: float
    annual_contribution_margin_per_unit: float


def operating_breakeven_fleet_size(fixed_operating_cost_monthly: float, economics: UnitEconomics) -> OperatingBreakevenResult:
    """N_Operating Breakeven = Annual Fixed Operating Costs / Annual Contribution
    Margin per Active Unit. This is the steady-state active fleet size needed
    to cover fixed costs -- it says nothing about cumulative cash timing and
    must never be reported as "cash breakeven"."""
    annual_fixed = fixed_operating_cost_monthly * 12.0
    annual_margin = annual_contribution_margin_per_unit(economics)
    if annual_margin <= 0:
        raise ValueError("annual_contribution_margin_per_unit must be positive to compute an operating breakeven fleet size")
    return OperatingBreakevenResult(
        label="Operating Breakeven Fleet Size",
        operating_breakeven_fleet_size=annual_fixed / annual_margin,
        annual_fixed_operating_costs=annual_fixed,
        annual_contribution_margin_per_unit=annual_margin,
    )


# ---------------------------------------------------------------------------
# Unit deployment payback (spec 7.8) -- NOT company cash breakeven
# ---------------------------------------------------------------------------


def unit_payback_months_constant(economics: UnitEconomics) -> float:
    """Simple version: constant steady-state monthly contribution margin.
    Payback Months = Net Upfront Deployment Investment / Steady-State Monthly
    Contribution Margin."""
    monthly_margin = contribution_margin_per_unit_at_utilization(economics, utilization=1.0)
    if monthly_margin <= 0:
        raise ValueError("steady-state monthly contribution margin must be positive to compute unit payback")
    return net_upfront_deployment_investment(economics) / monthly_margin


def unit_payback_months_with_ramp(
    economics: UnitEconomics, utilization_ramp: list[UtilizationRampPoint], max_months: int = 600
) -> float | None:
    """Accurate version: Payback Month = minimum T such that cumulative unit
    contribution cash flow through T >= Net Upfront Deployment Investment,
    using the actual monthly utilization ramp. Returns None if payback is not
    reached within `max_months` (e.g. the ramp never yields positive margin)."""
    target = net_upfront_deployment_investment(economics)
    cumulative = 0.0
    for month in range(max_months):
        utilization = utilization_at(utilization_ramp, month)
        cumulative += contribution_margin_per_unit_at_utilization(economics, utilization)
        if cumulative >= target:
            return float(month + 1)  # month is 0-indexed; "through month 1" means index 0 completed
    return None


# ---------------------------------------------------------------------------
# Company-level monthly cash flow and cash breakeven (spec 7.9-7.11)
# ---------------------------------------------------------------------------


@dataclass
class MonthlyEconomicsResult:
    month: int
    active_units: float
    revenue: float
    variable_cost: float
    fixed_cost: float
    upfront_inflow: float
    upfront_outflow: float
    net_cash_flow: float
    cumulative_cash_flow: float
    cash_balance: float


def project_monthly_cash_flow(
    newly_deployed_units: dict[int, float],
    economics: UnitEconomics,
    utilization_ramp: list[UtilizationRampPoint],
    fixed_operating_cost_monthly: float,
    opening_cash: float,
    num_months: int,
) -> list[MonthlyEconomicsResult]:
    """Company-wide monthly cash flow, respecting deployment timing (spec
    rule 11: revenue/costs cannot be recognized before a unit is actually
    deployed) and contract-term churn (a unit leaves the active fleet
    `contract_term_months` after its own deployment month)."""
    results: list[MonthlyEconomicsResult] = []
    cumulative = 0.0

    for t in range(num_months):
        active_units = 0.0
        revenue = 0.0
        variable_cost = 0.0

        window_start = max(0, t - economics.contract_term_months + 1)
        for d in range(window_start, t + 1):
            units_d = newly_deployed_units.get(d, 0.0)
            if units_d <= 0:
                continue
            months_since_commissioning = t - d
            utilization = utilization_at(utilization_ramp, months_since_commissioning)
            active_units += units_d
            revenue += units_d * revenue_per_unit_at_utilization(economics, utilization)
            variable_cost += units_d * variable_cost_per_unit_at_utilization(economics, utilization)

        units_deployed_this_month = newly_deployed_units.get(t, 0.0)
        upfront_outflow = units_deployed_this_month * upfront_deployment_cost_per_unit(economics)
        upfront_inflow = units_deployed_this_month * economics.upfront_customer_payment

        net_cash_flow = revenue - variable_cost - fixed_operating_cost_monthly + upfront_inflow - upfront_outflow
        cumulative += net_cash_flow

        results.append(
            MonthlyEconomicsResult(
                month=t,
                active_units=active_units,
                revenue=revenue,
                variable_cost=variable_cost,
                fixed_cost=fixed_operating_cost_monthly,
                upfront_inflow=upfront_inflow,
                upfront_outflow=upfront_outflow,
                net_cash_flow=net_cash_flow,
                cumulative_cash_flow=cumulative,
                cash_balance=opening_cash + cumulative,
            )
        )

    return results


def company_cash_breakeven_month(monthly_results: list[MonthlyEconomicsResult]) -> int | None:
    """Spec 7.9: minimum T such that Cumulative Cash Flow_T >= 0 (cumulative
    flow only, opening cash excluded by definition)."""
    for result in monthly_results:
        if result.cumulative_cash_flow >= 0:
            return result.month
    return None


def minimum_cash_balance(monthly_results: list[MonthlyEconomicsResult]) -> float:
    """Spec 7.10: minimum over t of (Opening Cash + Cumulative Cash Flow_t)."""
    if not monthly_results:
        raise ValueError("monthly_results must contain at least one month")
    return min(r.cash_balance for r in monthly_results)


def external_capital_required(min_cash_balance: float, desired_cash_buffer: float = 0.0) -> float:
    """Spec 7.11: max(0, -Minimum Cash Balance + Minimum Desired Cash Buffer)."""
    return max(0.0, -min_cash_balance + desired_cash_buffer)


def lifetime_contribution_per_unit(
    economics: UnitEconomics, utilization_ramp: list[UtilizationRampPoint], discount_rate_monthly: float = 0.0
) -> float:
    """Spec 7.12. discount_rate_monthly = 0.0 reports undiscounted lifetime
    contribution (the spec's recommended first-version default); pass a
    positive monthly rate for a discounted advanced-output variant."""
    cumulative = 0.0
    for month in range(economics.contract_term_months):
        utilization = utilization_at(utilization_ramp, month)
        margin = contribution_margin_per_unit_at_utilization(economics, utilization)
        discount_factor = 1.0 / ((1.0 + discount_rate_monthly) ** month)
        cumulative += margin * discount_factor
    return cumulative - net_upfront_deployment_investment(economics) + economics.residual_value
