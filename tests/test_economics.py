"""
Required economics tests (spec section 16.1). Core Release builds the RaaS
preset only (spec section 21.1 / 25) -- direct-sale and hybrid economics
tests are Expansion Release and are intentionally not included here; there
is no direct_sale/hybrid code path to test yet.
"""

import pytest

from engine.economics import (
    OperatingBreakevenResult,
    annual_contribution_margin_per_unit,
    company_cash_breakeven_month,
    contribution_margin_per_unit_at_utilization,
    external_capital_required,
    lifetime_contribution_per_unit,
    minimum_cash_balance,
    net_upfront_deployment_investment,
    operating_breakeven_fleet_size,
    project_monthly_cash_flow,
    unit_payback_months_constant,
    unit_payback_months_with_ramp,
    upfront_deployment_cost_per_unit,
    utilization_at,
)
from engine.schemas import UnitEconomics, UtilizationRampPoint


def make_economics(**overrides):
    defaults = dict(
        hardware_cost_per_unit=40_000,
        deployment_cost_per_unit=10_000,
        upfront_customer_payment=0,
        monthly_base_revenue=3_000,
        usage_price=0,
        expected_monthly_usage=0,
        monthly_variable_support_cost=500,
        contract_term_months=36,
        residual_value=0,
    )
    defaults.update(overrides)
    return UnitEconomics(**defaults)


class TestUtilizationAt:
    def test_before_first_point_is_zero(self):
        ramp = [UtilizationRampPoint(month_since_commissioning=1, utilization=0.5)]
        assert utilization_at(ramp, 0) == 0.0

    def test_steps_at_defined_points(self):
        ramp = [
            UtilizationRampPoint(month_since_commissioning=0, utilization=0.25),
            UtilizationRampPoint(month_since_commissioning=2, utilization=0.65),
        ]
        assert utilization_at(ramp, 0) == pytest.approx(0.25)
        assert utilization_at(ramp, 1) == pytest.approx(0.25)
        assert utilization_at(ramp, 2) == pytest.approx(0.65)

    def test_holds_last_value_beyond_final_point(self):
        ramp = [UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)]
        assert utilization_at(ramp, 50) == pytest.approx(1.0)

    def test_negative_month_is_zero(self):
        ramp = [UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)]
        assert utilization_at(ramp, -1) == 0.0


class TestOperatingBreakevenFleetSize:
    """Required test: operating breakeven fleet with known fixed cost and contribution margin."""

    def test_hand_calculated_round_number(self):
        economics = make_economics()
        # steady-state monthly margin = 3000 - 500 = 2500; annual = 30,000
        assert annual_contribution_margin_per_unit(economics) == pytest.approx(30_000)
        result = operating_breakeven_fleet_size(fixed_operating_cost_monthly=100_000, economics=economics)
        assert isinstance(result, OperatingBreakevenResult)
        assert result.label == "Operating Breakeven Fleet Size"
        # annual fixed = 1,200,000 / annual margin 30,000 = 40 units
        assert result.operating_breakeven_fleet_size == pytest.approx(40.0)

    def test_zero_margin_raises(self):
        economics = make_economics(monthly_base_revenue=500, monthly_variable_support_cost=500)
        with pytest.raises(ValueError):
            operating_breakeven_fleet_size(fixed_operating_cost_monthly=100_000, economics=economics)


class TestUnitPaybackConstant:
    """Required test: unit payback with constant monthly contribution."""

    def test_hand_calculated(self):
        economics = make_economics(hardware_cost_per_unit=1_000, deployment_cost_per_unit=0, monthly_base_revenue=100, monthly_variable_support_cost=0)
        assert net_upfront_deployment_investment(economics) == pytest.approx(1_000)
        assert contribution_margin_per_unit_at_utilization(economics, 1.0) == pytest.approx(100)
        assert unit_payback_months_constant(economics) == pytest.approx(10.0)


class TestUnitPaybackWithRamp:
    """Required test: unit payback with utilization ramp."""

    def test_ramp_delays_payback_versus_constant(self):
        economics = make_economics(hardware_cost_per_unit=1_000, deployment_cost_per_unit=0, monthly_base_revenue=100, monthly_variable_support_cost=0)
        ramp = [
            UtilizationRampPoint(month_since_commissioning=0, utilization=0.5),
            UtilizationRampPoint(month_since_commissioning=1, utilization=1.0),
        ]
        # Hand calc: month0 margin=50 (cum 50), month1..9 margin=100 each.
        # cum after month k (k>=1) = 50 + 100*k. Need cum >= 1000 -> 50+100k>=1000 -> k>=9.5 -> k=10.
        # cum after month10 = 50+1000=1050 >= 1000, first month index where target is met is 10 -> returns 11.
        assert unit_payback_months_with_ramp(economics, ramp) == pytest.approx(11.0)
        assert unit_payback_months_constant(economics) == pytest.approx(10.0)

    def test_returns_none_if_never_reached(self):
        economics = make_economics(hardware_cost_per_unit=1_000_000, deployment_cost_per_unit=0, monthly_base_revenue=1, monthly_variable_support_cost=0)
        ramp = [UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)]
        assert unit_payback_months_with_ramp(economics, ramp, max_months=12) is None


class TestCompanyCashFlow:
    """Required tests: company cash breakeven, minimum cash balance, capital requirement."""

    def setup_economics_and_ramp(self):
        economics = make_economics(
            hardware_cost_per_unit=1_000,
            deployment_cost_per_unit=0,
            upfront_customer_payment=200,
            monthly_base_revenue=100,
            monthly_variable_support_cost=0,
            contract_term_months=100,
        )
        ramp = [UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)]
        return economics, ramp

    def test_company_cash_breakeven_hand_calculated(self):
        economics, ramp = self.setup_economics_and_ramp()
        # 10 units deployed at month 0 only, fixed cost 200/month, opening cash 5000.
        results = project_monthly_cash_flow(
            newly_deployed_units={0: 10.0},
            economics=economics,
            utilization_ramp=ramp,
            fixed_operating_cost_monthly=200,
            opening_cash=5_000,
            num_months=15,
        )
        # month0: revenue=1000, upfront_outflow=10*1000=10000, upfront_inflow=10*200=2000
        # net0 = 1000 - 0 - 200 + 2000 - 10000 = -7200
        assert results[0].net_cash_flow == pytest.approx(-7_200)
        assert results[0].cumulative_cash_flow == pytest.approx(-7_200)
        # months 1+: net = 1000 - 200 = 800/month; cumulative_t = -7200 + 800*t
        assert results[9].cumulative_cash_flow == pytest.approx(-7_200 + 800 * 9)
        assert results[9].cumulative_cash_flow == pytest.approx(0.0)

        breakeven = company_cash_breakeven_month(results)
        assert breakeven == 9

    def test_minimum_cash_balance_hand_calculated(self):
        economics, ramp = self.setup_economics_and_ramp()
        results = project_monthly_cash_flow(
            newly_deployed_units={0: 10.0},
            economics=economics,
            utilization_ramp=ramp,
            fixed_operating_cost_monthly=200,
            opening_cash=5_000,
            num_months=15,
        )
        # min cash balance occurs at month 0: 5000 + (-7200) = -2200
        assert minimum_cash_balance(results) == pytest.approx(-2_200)

    def test_external_capital_required_hand_calculated(self):
        min_balance = -2_200
        assert external_capital_required(min_balance, desired_cash_buffer=1_000) == pytest.approx(3_200)

    def test_external_capital_required_is_zero_when_balance_never_negative(self):
        assert external_capital_required(min_cash_balance=500, desired_cash_buffer=0) == pytest.approx(0.0)

    def test_no_deployment_never_breaks_even_without_revenue(self):
        economics, ramp = self.setup_economics_and_ramp()
        results = project_monthly_cash_flow(
            newly_deployed_units={},
            economics=economics,
            utilization_ramp=ramp,
            fixed_operating_cost_monthly=200,
            opening_cash=5_000,
            num_months=6,
        )
        assert company_cash_breakeven_month(results) is None
        assert all(r.active_units == 0 for r in results)


class TestUpfrontDeploymentCost:
    def test_hand_calculated(self):
        economics = make_economics(hardware_cost_per_unit=40_000, deployment_cost_per_unit=10_000, upfront_customer_payment=5_000)
        assert upfront_deployment_cost_per_unit(economics) == pytest.approx(50_000)
        assert net_upfront_deployment_investment(economics) == pytest.approx(45_000)


class TestLifetimeContribution:
    def test_undiscounted_hand_calculated(self):
        economics = make_economics(
            hardware_cost_per_unit=1_000,
            deployment_cost_per_unit=0,
            monthly_base_revenue=100,
            monthly_variable_support_cost=0,
            contract_term_months=12,
            residual_value=50,
        )
        ramp = [UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)]
        # 12 months * 100 margin = 1200, minus net investment 1000, plus residual 50 = 250
        assert lifetime_contribution_per_unit(economics, ramp) == pytest.approx(250.0)
