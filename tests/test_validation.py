import pytest

from engine.schemas import (
    CapacityEntry,
    CompanyAssumptions,
    CustomerConcentrationEntry,
    FunnelStage,
    UnitEconomics,
    UtilizationRampPoint,
)
from engine.validation import (
    EngineValidationError,
    raise_if_errors,
    validate_capacity_entries,
    validate_company_assumptions,
    validate_customer_concentration_entries,
    validate_funnel_stage,
    validate_funnel_stages,
    validate_unit_economics,
)


def make_stage(**overrides):
    defaults = dict(
        stage_name="Qualified opportunity",
        stage_order=1,
        conversion_probability=0.5,
        dwell_min_months=1,
        dwell_mode_months=2,
        dwell_max_months=4,
    )
    defaults.update(overrides)
    return FunnelStage(**defaults)


class TestFunnelStageValidation:
    def test_valid_stage_has_no_errors(self):
        assert validate_funnel_stage(make_stage()) == []

    def test_dwell_min_exceeds_mode_is_error(self):
        stage = make_stage(dwell_min_months=5, dwell_mode_months=2, dwell_max_months=6)
        errors = validate_funnel_stage(stage)
        assert any("dwell_min_months" in e for e in errors)

    def test_dwell_mode_exceeds_max_is_error(self):
        stage = make_stage(dwell_min_months=1, dwell_mode_months=8, dwell_max_months=6)
        errors = validate_funnel_stage(stage)
        assert any("dwell_mode_months" in e for e in errors)

    def test_duplicate_stage_order_is_error(self):
        stages = [make_stage(stage_name="A", stage_order=1), make_stage(stage_name="B", stage_order=1)]
        errors = validate_funnel_stages(stages)
        assert any("unique stage_order" in e for e in errors)

    def test_empty_funnel_is_error(self):
        errors = validate_funnel_stages([])
        assert any("at least one stage" in e for e in errors)

    def test_raise_if_errors_raises(self):
        with pytest.raises(EngineValidationError):
            raise_if_errors(["some problem"])

    def test_raise_if_errors_noop_when_empty(self):
        raise_if_errors([])  # should not raise


class TestCompanyAssumptionsValidation:
    def make_assumptions(self, ramp):
        return CompanyAssumptions(
            commercial_model="raas",
            opening_cash=1_000_000,
            fixed_operating_cost_monthly=100_000,
            manufacturing_capacity_monthly=10,
            deployment_teams=2,
            units_per_team_monthly=5,
            service_units_per_fte=20,
            utilization_ramp=ramp,
        )

    def test_valid_ramp_has_no_errors(self):
        ramp = [
            UtilizationRampPoint(month_since_commissioning=0, utilization=0.25),
            UtilizationRampPoint(month_since_commissioning=1, utilization=0.40),
            UtilizationRampPoint(month_since_commissioning=2, utilization=0.65),
            UtilizationRampPoint(month_since_commissioning=3, utilization=1.0),
        ]
        assert validate_company_assumptions(self.make_assumptions(ramp)) == []

    def test_empty_ramp_is_error(self):
        errors = validate_company_assumptions(self.make_assumptions([]))
        assert any("at least one point" in e for e in errors)

    def test_decreasing_utilization_is_error(self):
        ramp = [
            UtilizationRampPoint(month_since_commissioning=0, utilization=0.5),
            UtilizationRampPoint(month_since_commissioning=1, utilization=0.3),
        ]
        errors = validate_company_assumptions(self.make_assumptions(ramp))
        assert any("non-decreasing" in e for e in errors)

    def test_zero_deployment_teams_with_positive_throughput_is_error(self):
        assumptions = CompanyAssumptions(
            commercial_model="raas",
            opening_cash=1_000_000,
            fixed_operating_cost_monthly=100_000,
            manufacturing_capacity_monthly=10,
            deployment_teams=0,
            units_per_team_monthly=5,
            service_units_per_fte=20,
            utilization_ramp=[UtilizationRampPoint(month_since_commissioning=0, utilization=1.0)],
        )
        errors = validate_company_assumptions(assumptions)
        assert any("deployment_teams is 0" in e for e in errors)


class TestUnitEconomicsValidation:
    def test_valid_economics_has_no_errors(self):
        economics = UnitEconomics(
            hardware_cost_per_unit=50_000,
            deployment_cost_per_unit=10_000,
            upfront_customer_payment=5_000,
            monthly_base_revenue=3_000,
            monthly_variable_support_cost=500,
            contract_term_months=36,
        )
        assert validate_unit_economics(economics) == []

    def test_zero_revenue_is_error(self):
        economics = UnitEconomics(
            hardware_cost_per_unit=50_000,
            deployment_cost_per_unit=10_000,
            monthly_base_revenue=0,
            usage_price=0,
            expected_monthly_usage=0,
            monthly_variable_support_cost=500,
            contract_term_months=36,
        )
        errors = validate_unit_economics(economics)
        assert any("must include either monthly_base_revenue" in e for e in errors)

    def test_upfront_payment_exceeding_cost_is_error(self):
        economics = UnitEconomics(
            hardware_cost_per_unit=10_000,
            deployment_cost_per_unit=1_000,
            upfront_customer_payment=20_000,
            monthly_base_revenue=3_000,
            monthly_variable_support_cost=500,
            contract_term_months=36,
        )
        errors = validate_unit_economics(economics)
        assert any("upfront_customer_payment exceeds" in e for e in errors)


class TestCapacityValidation:
    def test_zero_capacity_and_zero_cost_is_error(self):
        entry = CapacityEntry(capacity_type="manufacturing", available_capacity=0, unit_of_measure="units/month")
        errors = validate_capacity_entries([entry])
        assert any("zero capacity and zero cost" in e for e in errors)

    def test_valid_capacity_has_no_errors(self):
        entry = CapacityEntry(capacity_type="manufacturing", available_capacity=10, unit_of_measure="units/month")
        assert validate_capacity_entries([entry]) == []


class TestConcentrationValidation:
    def test_duplicate_customer_id_is_error(self):
        entries = [
            CustomerConcentrationEntry(customer_id="1", customer_name="A", contracted_backlog=100),
            CustomerConcentrationEntry(customer_id="1", customer_name="B", contracted_backlog=200),
        ]
        errors = validate_customer_concentration_entries(entries)
        assert any("unique" in e for e in errors)

    def test_all_zero_backlog_is_error(self):
        entries = [CustomerConcentrationEntry(customer_id="1", customer_name="A", contracted_backlog=0)]
        errors = validate_customer_concentration_entries(entries)
        assert any("zero contracted_backlog" in e for e in errors)

    def test_valid_entries_have_no_errors(self):
        entries = [
            CustomerConcentrationEntry(customer_id="1", customer_name="A", contracted_backlog=100),
            CustomerConcentrationEntry(customer_id="2", customer_name="B", contracted_backlog=200),
        ]
        assert validate_customer_concentration_entries(entries) == []
