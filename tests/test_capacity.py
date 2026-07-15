import pytest

from engine.capacity import (
    check_service_coverage,
    monthly_capacity_series,
    required_service_fte,
    run_capacity_model,
)
from engine.schemas import CapacityEntry


def flat(value: float, num_months: int) -> dict[int, float]:
    return {t: value for t in range(num_months)}


class TestDemandBelowCapacity:
    """Required capacity test: demand below capacity."""

    def test_all_ready_units_deploy_immediately(self):
        ready = {0: 5.0, 1: 5.0, 2: 5.0}
        results = run_capacity_model(ready, flat(100, 3), flat(100, 3), flat(100, 3), num_months=3)
        assert [r.units_deployed for r in results] == [5.0, 5.0, 5.0]
        assert [r.backlog for r in results] == [0.0, 0.0, 0.0]


class TestManufacturingBottleneck:
    """Required capacity test: manufacturing bottleneck."""

    def test_manufacturing_caps_deployment(self):
        ready = {0: 10.0}
        results = run_capacity_model(ready, flat(3, 1), flat(100, 1), flat(100, 1), num_months=1)
        assert results[0].units_deployed == pytest.approx(3.0)
        assert results[0].backlog == pytest.approx(7.0)


class TestDeploymentTeamBottleneck:
    """Required capacity test: deployment-team (implementation) bottleneck."""

    def test_implementation_caps_deployment(self):
        ready = {0: 10.0}
        results = run_capacity_model(ready, flat(100, 1), flat(4, 1), flat(100, 1), num_months=1)
        assert results[0].units_deployed == pytest.approx(4.0)
        assert results[0].backlog == pytest.approx(6.0)


class TestCommissioningBottleneck:
    """Required capacity test: commissioning bottleneck."""

    def test_commissioning_caps_deployment(self):
        ready = {0: 10.0}
        results = run_capacity_model(ready, flat(100, 1), flat(100, 1), flat(2, 1), num_months=1)
        assert results[0].units_deployed == pytest.approx(2.0)
        assert results[0].backlog == pytest.approx(8.0)


class TestBacklogAccumulation:
    """Required capacity test: backlog accumulation."""

    def test_backlog_grows_across_months_under_sustained_excess_demand(self):
        ready = {0: 10.0, 1: 10.0, 2: 10.0}
        results = run_capacity_model(ready, flat(4, 3), flat(4, 3), flat(4, 3), num_months=3)
        # month 0: deploy 4, backlog 6
        # month 1: available 6+10=16, deploy 4, backlog 12
        # month 2: available 12+10=22, deploy 4, backlog 18
        assert [r.units_deployed for r in results] == [4.0, 4.0, 4.0]
        assert [r.backlog for r in results] == [6.0, 12.0, 18.0]

    def test_backlog_can_be_worked_down_once_demand_drops(self):
        ready = {0: 10.0, 1: 0.0}
        results = run_capacity_model(ready, flat(4, 2), flat(4, 2), flat(4, 2), num_months=2)
        assert results[0].backlog == pytest.approx(6.0)
        # month 1: available = 6 + 0 = 6, deploy min(6,4,4,4)=4, backlog=2
        assert results[1].units_deployed == pytest.approx(4.0)
        assert results[1].backlog == pytest.approx(2.0)


class TestCapacityExpansionAfterLeadTime:
    """Required capacity test: capacity expansion after a lead time."""

    def test_addition_inactive_before_lead_time(self):
        addition = CapacityEntry(
            capacity_type="manufacturing",
            available_capacity=10,
            unit_of_measure="units/month",
            lead_time_months=3,
            ramp_months=0,
        )
        series = monthly_capacity_series(base_capacity=5, additions=[addition], num_months=3, capacity_type="manufacturing")
        assert series == {0: 5.0, 1: 5.0, 2: 5.0}

    def test_addition_fully_active_immediately_after_lead_time_with_no_ramp(self):
        addition = CapacityEntry(
            capacity_type="manufacturing",
            available_capacity=10,
            unit_of_measure="units/month",
            lead_time_months=2,
            ramp_months=0,
        )
        series = monthly_capacity_series(base_capacity=5, additions=[addition], num_months=4, capacity_type="manufacturing")
        assert series == {0: 5.0, 1: 5.0, 2: 15.0, 3: 15.0}

    def test_addition_ramps_linearly_after_activation(self):
        addition = CapacityEntry(
            capacity_type="manufacturing",
            available_capacity=10,
            unit_of_measure="units/month",
            lead_time_months=0,
            ramp_months=2,
        )
        series = monthly_capacity_series(base_capacity=5, additions=[addition], num_months=2, capacity_type="manufacturing")
        # month 0: fraction = (0+1)/2 = 0.5 -> +5 = 10
        # month 1: fraction = (1+1)/2 = 1.0 -> +10 = 15
        assert series == {0: pytest.approx(10.0), 1: pytest.approx(15.0)}

    def test_addition_only_applies_to_matching_capacity_type(self):
        addition = CapacityEntry(
            capacity_type="commissioning",
            available_capacity=10,
            unit_of_measure="engineers",
            lead_time_months=0,
            ramp_months=0,
        )
        series = monthly_capacity_series(base_capacity=5, additions=[addition], num_months=1, capacity_type="manufacturing")
        assert series == {0: 5.0}


class TestFieldServiceCoverage:
    """Required capacity test: field-service coverage shortfall."""

    def test_required_fte_hand_calculated(self):
        assert required_service_fte(active_units=100, units_supported_per_fte=20) == pytest.approx(5.0)

    def test_zero_units_per_fte_raises(self):
        with pytest.raises(ValueError):
            required_service_fte(active_units=100, units_supported_per_fte=0)

    def test_shortfall_flagged_when_understaffed(self):
        result = check_service_coverage(active_units=100, available_fte=3, units_supported_per_fte=20)
        assert result.required_fte == pytest.approx(5.0)
        assert result.shortfall_fte == pytest.approx(2.0)
        assert result.is_understaffed is True

    def test_no_shortfall_when_adequately_staffed(self):
        result = check_service_coverage(active_units=100, available_fte=10, units_supported_per_fte=20)
        assert result.shortfall_fte == pytest.approx(0.0)
        assert result.is_understaffed is False
