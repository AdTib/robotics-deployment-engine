"""
Required integration tests (spec section 16.5).
"""

import pytest

from engine.schemas import (
    CapacityEntry,
    CompanyAssumptions,
    CustomerConcentrationEntry,
    FunnelStage,
    UnitEconomics,
    UtilizationRampPoint,
)
from engine.simulation import (
    ScenarioAssumptions,
    compare_scenarios,
    make_capacity_expansion_scenario,
    make_fast_conversion_scenario,
    make_service_cost_downside_scenario,
    make_slow_conversion_scenario,
    run_scenario,
)


def base_assumptions(**overrides) -> ScenarioAssumptions:
    commercial_stages = [
        FunnelStage(
            stage_name="Contracted",
            stage_order=0,
            conversion_probability=1.0,
            dwell_min_months=1,
            dwell_mode_months=1,
            dwell_max_months=1,
            expected_units=10,
        )
    ]
    deployment_stages = [
        FunnelStage(
            stage_name="Scheduled",
            stage_order=0,
            conversion_probability=1.0,
            dwell_min_months=1,
            dwell_mode_months=1,
            dwell_max_months=1,
        )
    ]
    company_assumptions = CompanyAssumptions(
        commercial_model="raas",
        opening_cash=100_000,
        fixed_operating_cost_monthly=0,
        manufacturing_capacity_monthly=100,
        deployment_teams=1,
        units_per_team_monthly=100,
        service_units_per_fte=20,
        utilization_ramp=[UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)],
    )
    unit_economics = UnitEconomics(
        hardware_cost_per_unit=1_000,
        deployment_cost_per_unit=0,
        upfront_customer_payment=0,
        monthly_base_revenue=100,
        usage_price=0,
        expected_monthly_usage=0,
        monthly_variable_support_cost=0,
        contract_term_months=100,
    )
    defaults = dict(
        scenario_name="base",
        commercial_stages=commercial_stages,
        deployment_stages=deployment_stages,
        opportunities_per_month={0: 1},
        company_assumptions=company_assumptions,
        commissioning_capacity_monthly=100,
        unit_economics=unit_economics,
        backlog_value_per_unit=100,
        num_months=6,
    )
    defaults.update(overrides)
    return ScenarioAssumptions(**defaults)


class TestNoRevenueBeforeOperational:
    """Required test: units cannot generate recurring revenue before becoming operational."""

    def test_revenue_zero_until_units_deployed(self):
        summary = run_scenario(base_assumptions())
        # Contracted units land month 1 (1 month dwell), ready units land month 2
        # (1 more month dwell), ample capacity deploys them immediately at month 2.
        assert summary.monthly_results[0].revenue == 0
        assert summary.monthly_results[1].revenue == 0
        assert summary.monthly_results[0].active_units == 0
        assert summary.monthly_results[1].active_units == 0
        assert summary.monthly_results[2].revenue > 0
        assert summary.monthly_results[2].active_units == pytest.approx(10.0)


class TestDeploymentCannotExceedCapacity:
    """Required test: deployment cannot exceed capacity."""

    def test_manufacturing_bottleneck_caps_monthly_deployment(self):
        assumptions = base_assumptions()
        assumptions.company_assumptions = CompanyAssumptions(
            commercial_model="raas",
            opening_cash=100_000,
            fixed_operating_cost_monthly=0,
            manufacturing_capacity_monthly=3,  # bottleneck
            deployment_teams=1,
            units_per_team_monthly=100,
            service_units_per_fte=20,
            utilization_ramp=[UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)],
        )
        summary = run_scenario(assumptions)
        for result in summary.monthly_results:
            assert result.units_deployed <= 3.0 + 1e-9
        # 10 units at 3/month takes 4 months to fully clear (3,3,3,1) starting month 2.
        total_deployed = sum(r.units_deployed for r in summary.monthly_results)
        assert total_deployed == pytest.approx(10.0)
        assert summary.monthly_results[-1].deployment_backlog == pytest.approx(0.0)


class TestDelayedDeploymentDelaysRevenue:
    """Required test: delayed deployment delays revenue."""

    def test_site_readiness_delay_pushes_revenue_later(self):
        on_time = run_scenario(base_assumptions())
        delayed = run_scenario(base_assumptions(site_readiness_delay_months=3))

        # On-time scenario has revenue by month 2; delayed scenario does not.
        assert on_time.monthly_results[2].revenue > 0
        assert delayed.monthly_results[2].revenue == 0

        # Delayed scenario eventually catches up (revenue appears later).
        assert delayed.monthly_results[5].revenue > 0


class TestAccountExpansionChangesConcentration:
    """Required test: account expansion changes concentration."""

    def test_new_account_lowers_concentration(self):
        existing = [CustomerConcentrationEntry(customer_id="existing", customer_name="Existing Co", contracted_backlog=1000)]
        assumptions = base_assumptions(
            existing_customers=existing,
            new_account_strategy="diversified",
            new_account_backlog_value=1000,
            backlog_value_per_unit=100,  # 10 units * 100 = 1000 new backlog in the contracting month
        )
        summary = run_scenario(assumptions)

        # Month 0: only the existing customer exists -> fully concentrated.
        assert summary.monthly_results[0].hhi_standard == pytest.approx(10_000)
        assert summary.monthly_results[0].largest_customer_share == pytest.approx(1.0)

        # Month 1: the new contracted cohort adds a second, equally-sized account.
        assert summary.monthly_results[1].hhi_standard == pytest.approx(5_000)
        assert summary.monthly_results[1].largest_customer_share == pytest.approx(0.5)


class TestCashFlowReflectsTiming:
    """Required test: cash flow reflects manufacturing and deployment timing."""

    def test_upfront_cost_hits_cash_flow_at_deployment_not_contracting(self):
        summary = run_scenario(base_assumptions())
        # No cash impact before deployment (month 2): no revenue, no upfront spend yet.
        assert summary.monthly_results[0].net_cash_flow == pytest.approx(0.0)
        assert summary.monthly_results[1].net_cash_flow == pytest.approx(0.0)
        # At month 2: revenue 10*100=1000, upfront outflow 10*1000=10000 -> net = -9000.
        assert summary.monthly_results[2].net_cash_flow == pytest.approx(-9_000.0)
        assert summary.monthly_results[2].cumulative_cash_flow == pytest.approx(-9_000.0)


class TestScenarioOutputsInternallyConsistent:
    """Required test: scenario outputs remain internally consistent."""

    def test_deployed_units_never_exceed_ready_units_cumulative(self):
        summary = run_scenario(base_assumptions())
        cumulative_ready = sum(r.ready_units for r in summary.monthly_results)
        cumulative_deployed = sum(r.units_deployed for r in summary.monthly_results)
        assert cumulative_deployed <= cumulative_ready + 1e-9

    def test_summary_has_one_row_per_month(self):
        assumptions = base_assumptions(num_months=8)
        summary = run_scenario(assumptions)
        assert len(summary.monthly_results) == 8
        assert [r.month for r in summary.monthly_results] == list(range(8))

    def test_breakeven_metrics_are_well_formed(self):
        summary = run_scenario(base_assumptions(company_assumptions=base_assumptions().company_assumptions.model_copy(update={"fixed_operating_cost_monthly": 1000})))
        assert summary.operating_breakeven.operating_breakeven_fleet_size > 0
        assert summary.unit_payback_months_constant > 0
        if summary.company_cash_breakeven_month is not None:
            assert summary.company_cash_breakeven_month >= 0


class TestScenarioBuilders:
    def test_slow_conversion_reduces_conversion_and_lengthens_dwell(self):
        base = base_assumptions()
        slow = make_slow_conversion_scenario(base)
        assert slow.commercial_stages[0].conversion_probability < base.commercial_stages[0].conversion_probability
        assert slow.commercial_stages[0].dwell_mode_months > base.commercial_stages[0].dwell_mode_months
        assert slow.scenario_name == "slow_conversion"

    def test_fast_conversion_increases_conversion_and_shortens_dwell(self):
        base = base_assumptions()
        fast = make_fast_conversion_scenario(base)
        assert fast.commercial_stages[0].conversion_probability >= base.commercial_stages[0].conversion_probability
        assert fast.commercial_stages[0].dwell_mode_months < base.commercial_stages[0].dwell_mode_months

    def test_capacity_expansion_adds_entries(self):
        base = base_assumptions()
        addition = CapacityEntry(capacity_type="manufacturing", available_capacity=50, unit_of_measure="units/month")
        expanded = make_capacity_expansion_scenario(base, [addition])
        assert len(expanded.capacity_additions) == len(base.capacity_additions) + 1

    def test_service_cost_downside_scales_cost(self):
        base = base_assumptions()
        downside = make_service_cost_downside_scenario(base, cost_multiplier=2.0)
        assert downside.unit_economics.monthly_variable_support_cost == pytest.approx(
            base.unit_economics.monthly_variable_support_cost * 2.0 if base.unit_economics.monthly_variable_support_cost > 0 else 0.0
        )

    def test_compare_scenarios_produces_one_row_per_scenario(self):
        base = base_assumptions()
        fast = make_fast_conversion_scenario(base)
        summaries = [run_scenario(base), run_scenario(fast)]
        rows = compare_scenarios(summaries)
        assert len(rows) == 2
        assert {row["scenario"] for row in rows} == {"base", "fast_conversion"}
