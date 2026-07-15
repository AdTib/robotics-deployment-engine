"""
Integrated deterministic scenario simulator (spec section 9) -- Core Release
scope (spec section 21.1 / 25): deterministic scenarios only, no Monte Carlo
(section 10.2 / 21.2 is Expansion Release). One concentration basis
(backlog) and one commercial-model preset (RaaS), matching
engine.concentration and engine.economics.

Wiring, month by month:
    opportunities_per_month --[engine.funnel]--> monthly contracted units
    --[engine.deployment]--> monthly commercially-ready units
    --[engine.capacity]--> monthly units deployed (operational), backlog, deferred revenue
    --[engine.economics]--> monthly revenue, cost, cash flow, cash balance
    --[engine.concentration]--> backlog HHI / largest-customer share over time

Spec rule 11 (timing integrity) is enforced structurally: a unit cannot
generate revenue or incur variable cost before engine.capacity has actually
gated it into `units_deployed`, and engine.economics only recognizes cash
flow for units present in that gated series.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Literal

from engine.capacity import monthly_capacity_series, run_capacity_model
from engine.concentration import ConcentrationResult, compute_concentration
from engine.deployment import project_ready_units
from engine.economics import (
    OperatingBreakevenResult,
    company_cash_breakeven_month,
    external_capital_required,
    minimum_cash_balance,
    operating_breakeven_fleet_size,
    project_monthly_cash_flow,
    unit_payback_months_constant,
    unit_payback_months_with_ramp,
)
from engine.funnel import aggregate_cohorts, project_cohort
from engine.schemas import CapacityEntry, CompanyAssumptions, CustomerConcentrationEntry, FunnelStage, UnitEconomics

NewAccountStrategy = Literal["anchor", "diversified"]


@dataclass
class ScenarioAssumptions:
    scenario_name: str
    commercial_stages: list[FunnelStage]
    deployment_stages: list[FunnelStage]
    opportunities_per_month: dict[int, float]
    company_assumptions: CompanyAssumptions
    commissioning_capacity_monthly: float
    unit_economics: UnitEconomics
    backlog_value_per_unit: float
    num_months: int = 36
    capacity_additions: list[CapacityEntry] = field(default_factory=list)
    existing_customers: list[CustomerConcentrationEntry] = field(default_factory=list)
    new_account_strategy: NewAccountStrategy = "diversified"
    new_account_backlog_value: float = 0.0
    desired_cash_buffer: float = 0.0
    site_readiness_delay_months: float = 0.0


@dataclass
class MonthlyScenarioResult:
    month: int
    contracted_units: float
    ready_units: float
    units_deployed: float
    deployment_backlog: float
    deferred_revenue: float
    revenue: float
    variable_cost: float
    fixed_cost: float
    net_cash_flow: float
    cumulative_cash_flow: float
    cash_balance: float
    active_units: float
    manufacturing_utilization: float
    implementation_utilization: float
    commissioning_utilization: float
    largest_customer_share: float | None
    top_three_share: float | None
    hhi_standard: float | None
    effective_customer_count: float | None


@dataclass
class ScenarioSummary:
    scenario_name: str
    monthly_results: list[MonthlyScenarioResult]
    operating_breakeven: OperatingBreakevenResult
    unit_payback_months_constant: float
    unit_payback_months_with_ramp: float | None
    company_cash_breakeven_month: int | None
    minimum_cash_balance: float
    external_capital_required: float

    @property
    def final(self) -> MonthlyScenarioResult:
        return self.monthly_results[-1]


def _new_synthetic_accounts_for_month(
    month_backlog_value: float,
    strategy: NewAccountStrategy,
    new_account_backlog_value: float,
    anchor_cumulative: float,
    diversified_accounts: list[float],
) -> tuple[float, list[float]]:
    """Update running new-account state for one month. Returns the updated
    (anchor_cumulative, diversified_accounts) state."""
    if strategy == "anchor":
        anchor_cumulative += month_backlog_value
    else:
        if new_account_backlog_value > 0 and month_backlog_value > 0:
            n_new = max(1, round(month_backlog_value / new_account_backlog_value))
            per_account_value = month_backlog_value / n_new
            diversified_accounts.extend([per_account_value] * n_new)
        elif month_backlog_value > 0:
            diversified_accounts.append(month_backlog_value)
    return anchor_cumulative, diversified_accounts


def run_scenario(assumptions: ScenarioAssumptions) -> ScenarioSummary:
    num_months = assumptions.num_months

    # 1. Commercial funnel: opportunities -> monthly contracted units.
    cohorts = [
        project_cohort(assumptions.commercial_stages, entrants=entrants, cohort_start_month=month)
        for month, entrants in assumptions.opportunities_per_month.items()
        if entrants > 0
    ]
    monthly_contracted = aggregate_cohorts(cohorts) if cohorts else {}

    # 2. Deployment funnel: contracted units -> commercially ready units.
    monthly_ready = project_ready_units(
        assumptions.deployment_stages, monthly_contracted, assumptions.site_readiness_delay_months
    )

    # 3. Capacity gating.
    ca = assumptions.company_assumptions
    implementation_base = ca.deployment_teams * ca.units_per_team_monthly
    manufacturing_series = monthly_capacity_series(
        ca.manufacturing_capacity_monthly, assumptions.capacity_additions, num_months, "manufacturing"
    )
    implementation_series = monthly_capacity_series(
        implementation_base, assumptions.capacity_additions, num_months, "implementation"
    )
    commissioning_series = monthly_capacity_series(
        assumptions.commissioning_capacity_monthly, assumptions.capacity_additions, num_months, "commissioning"
    )

    expected_revenue_per_unit = assumptions.unit_economics.monthly_base_revenue + (
        assumptions.unit_economics.usage_price * assumptions.unit_economics.expected_monthly_usage
    )
    capacity_results = run_capacity_model(
        monthly_ready, manufacturing_series, implementation_series, commissioning_series, num_months, expected_revenue_per_unit
    )
    newly_deployed_units = {r.month: r.units_deployed for r in capacity_results}

    # 4. Economics: deployed units -> revenue, cost, cash flow.
    economics_results = project_monthly_cash_flow(
        newly_deployed_units,
        assumptions.unit_economics,
        ca.utilization_ramp,
        ca.fixed_operating_cost_monthly,
        ca.opening_cash,
        num_months,
    )

    # 5. Concentration over time (backlog basis only, spec 8.7).
    anchor_cumulative = 0.0
    diversified_accounts: list[float] = []
    monthly_results: list[MonthlyScenarioResult] = []

    for t in range(num_months):
        cap_r = capacity_results[t]
        econ_r = economics_results[t]
        month_backlog_value = monthly_contracted.get(t, 0.0) * assumptions.backlog_value_per_unit

        anchor_cumulative, diversified_accounts = _new_synthetic_accounts_for_month(
            month_backlog_value,
            assumptions.new_account_strategy,
            assumptions.new_account_backlog_value,
            anchor_cumulative,
            diversified_accounts,
        )

        synthetic_entries: list[CustomerConcentrationEntry] = []
        if assumptions.new_account_strategy == "anchor" and anchor_cumulative > 0:
            synthetic_entries.append(
                CustomerConcentrationEntry(customer_id="new_anchor", customer_name="New Anchor Account", contracted_backlog=anchor_cumulative)
            )
        else:
            for i, value in enumerate(diversified_accounts):
                synthetic_entries.append(
                    CustomerConcentrationEntry(customer_id=f"new_{i}", customer_name=f"New Account {i + 1}", contracted_backlog=value)
                )

        all_entries = assumptions.existing_customers + synthetic_entries
        concentration: ConcentrationResult | None = None
        if all_entries and sum(e.contracted_backlog for e in all_entries) > 0:
            concentration = compute_concentration(all_entries, basis="backlog")

        monthly_results.append(
            MonthlyScenarioResult(
                month=t,
                contracted_units=monthly_contracted.get(t, 0.0),
                ready_units=monthly_ready.get(t, 0.0),
                units_deployed=cap_r.units_deployed,
                deployment_backlog=cap_r.backlog,
                deferred_revenue=cap_r.deferred_revenue,
                revenue=econ_r.revenue,
                variable_cost=econ_r.variable_cost,
                fixed_cost=econ_r.fixed_cost,
                net_cash_flow=econ_r.net_cash_flow,
                cumulative_cash_flow=econ_r.cumulative_cash_flow,
                cash_balance=econ_r.cash_balance,
                active_units=econ_r.active_units,
                manufacturing_utilization=cap_r.manufacturing_utilization,
                implementation_utilization=cap_r.implementation_utilization,
                commissioning_utilization=cap_r.commissioning_utilization,
                largest_customer_share=concentration.largest_customer_share if concentration else None,
                top_three_share=concentration.top_three_share if concentration else None,
                hhi_standard=concentration.hhi_standard if concentration else None,
                effective_customer_count=concentration.effective_customer_count if concentration else None,
            )
        )

    operating_breakeven = operating_breakeven_fleet_size(ca.fixed_operating_cost_monthly, assumptions.unit_economics)
    payback_constant = unit_payback_months_constant(assumptions.unit_economics)
    payback_ramp = unit_payback_months_with_ramp(assumptions.unit_economics, ca.utilization_ramp)
    breakeven_month = company_cash_breakeven_month(economics_results)
    min_cash = minimum_cash_balance(economics_results)
    capital_required = external_capital_required(min_cash, assumptions.desired_cash_buffer)

    return ScenarioSummary(
        scenario_name=assumptions.scenario_name,
        monthly_results=monthly_results,
        operating_breakeven=operating_breakeven,
        unit_payback_months_constant=payback_constant,
        unit_payback_months_with_ramp=payback_ramp,
        company_cash_breakeven_month=breakeven_month,
        minimum_cash_balance=min_cash,
        external_capital_required=capital_required,
    )


# ---------------------------------------------------------------------------
# Default scenario builders (spec section 9.2) -- all deterministic transforms
# of a base ScenarioAssumptions. None of these sample randomly.
# ---------------------------------------------------------------------------


def _scale_conversion_and_dwell(stages: list[FunnelStage], conversion_multiplier: float, dwell_multiplier: float) -> list[FunnelStage]:
    scaled = []
    for s in stages:
        scaled.append(
            s.model_copy(
                update={
                    "conversion_probability": min(1.0, s.conversion_probability * conversion_multiplier),
                    "dwell_min_months": s.dwell_min_months * dwell_multiplier,
                    "dwell_mode_months": s.dwell_mode_months * dwell_multiplier,
                    "dwell_max_months": s.dwell_max_months * dwell_multiplier,
                }
            )
        )
    return scaled


def make_slow_conversion_scenario(base: ScenarioAssumptions, conversion_multiplier: float = 0.7, dwell_multiplier: float = 1.3) -> ScenarioAssumptions:
    return replace(
        copy.deepcopy(base),
        scenario_name="slow_conversion",
        commercial_stages=_scale_conversion_and_dwell(base.commercial_stages, conversion_multiplier, dwell_multiplier),
    )


def make_fast_conversion_scenario(base: ScenarioAssumptions, conversion_multiplier: float = 1.3, dwell_multiplier: float = 0.7) -> ScenarioAssumptions:
    return replace(
        copy.deepcopy(base),
        scenario_name="fast_conversion",
        commercial_stages=_scale_conversion_and_dwell(base.commercial_stages, conversion_multiplier, dwell_multiplier),
    )


def make_anchor_customer_scenario(base: ScenarioAssumptions) -> ScenarioAssumptions:
    return replace(copy.deepcopy(base), scenario_name="anchor_customer", new_account_strategy="anchor")


def make_diversified_scenario(base: ScenarioAssumptions, new_account_backlog_value: float | None = None) -> ScenarioAssumptions:
    updated = copy.deepcopy(base)
    return replace(
        updated,
        scenario_name="diversified_accounts",
        new_account_strategy="diversified",
        new_account_backlog_value=new_account_backlog_value if new_account_backlog_value is not None else base.new_account_backlog_value,
    )


def make_capacity_constrained_scenario(base: ScenarioAssumptions) -> ScenarioAssumptions:
    return replace(copy.deepcopy(base), scenario_name="capacity_constrained", capacity_additions=[])


def make_capacity_expansion_scenario(base: ScenarioAssumptions, additional_capacity: list[CapacityEntry]) -> ScenarioAssumptions:
    updated = copy.deepcopy(base)
    return replace(updated, scenario_name="capacity_expansion", capacity_additions=list(updated.capacity_additions) + list(additional_capacity))


def make_utilization_downside_scenario(base: ScenarioAssumptions, delay_months: int = 2) -> ScenarioAssumptions:
    updated = copy.deepcopy(base)
    shifted_ramp = [
        p.model_copy(update={"month_since_commissioning": p.month_since_commissioning + delay_months})
        for p in updated.company_assumptions.utilization_ramp
    ]
    updated.company_assumptions = updated.company_assumptions.model_copy(update={"utilization_ramp": shifted_ramp})
    return replace(updated, scenario_name="utilization_downside")


def make_service_cost_downside_scenario(base: ScenarioAssumptions, cost_multiplier: float = 1.5) -> ScenarioAssumptions:
    updated = copy.deepcopy(base)
    updated.unit_economics = updated.unit_economics.model_copy(
        update={"monthly_variable_support_cost": updated.unit_economics.monthly_variable_support_cost * cost_multiplier}
    )
    return replace(updated, scenario_name="service_cost_downside")


def compare_scenarios(summaries: list[ScenarioSummary]) -> list[dict]:
    """Spec section 9.4 comparison table, as a list of plain dict rows
    (rendering is an /app concern, not built in Core Release)."""
    rows = []
    for s in summaries:
        final = s.final
        rows.append(
            {
                "scenario": s.scenario_name,
                "cash_breakeven_month": s.company_cash_breakeven_month,
                "minimum_cash_balance": s.minimum_cash_balance,
                "external_capital_required": s.external_capital_required,
                "operational_units_final": final.active_units,
                "deployment_backlog_final": final.deployment_backlog,
                "hhi_standard_final": final.hhi_standard,
                "largest_customer_share_final": final.largest_customer_share,
            }
        )
    return rows
