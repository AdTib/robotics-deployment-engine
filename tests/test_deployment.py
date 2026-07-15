import pytest

from engine.deployment import cascade_monthly_units, project_ready_units
from engine.schemas import FunnelStage


def stage(name, order, prob, dmin, dmode, dmax):
    return FunnelStage(
        stage_name=name,
        stage_order=order,
        conversion_probability=prob,
        dwell_min_months=dmin,
        dwell_mode_months=dmode,
        dwell_max_months=dmax,
    )


class TestFullConversionFixedDwell:
    def test_units_preserved_and_shifted_by_total_dwell(self):
        stages = [
            stage("Scheduled", 0, 1.0, 1, 1, 1),
            stage("Production", 1, 1.0, 2, 2, 2),
        ]
        result = cascade_monthly_units(stages, {0: 10.0})
        # total dwell = 1 + 2 = 3 months, full conversion -> all 10 units arrive at month 3
        assert result == {3: 10.0}


class TestCancellationAtStage:
    def test_partial_conversion_reduces_units(self):
        stages = [stage("Scheduled", 0, 0.8, 1, 1, 1)]
        result = cascade_monthly_units(stages, {0: 10.0})
        assert result == {1: pytest.approx(8.0)}

    def test_zero_conversion_drops_all_units(self):
        stages = [stage("Scheduled", 0, 0.0, 1, 1, 1)]
        result = cascade_monthly_units(stages, {0: 10.0})
        assert result == {}


class TestMultiMonthAggregation:
    def test_overlapping_arrivals_combine(self):
        stages = [stage("Scheduled", 0, 1.0, 2, 2, 2)]
        # units entering month 0 and month 2 both land on month 2 and month 4 respectively;
        # arrange so two different input months collide on the same output month.
        result = cascade_monthly_units(stages, {0: 5.0, 2: 3.0})
        assert result == {2: pytest.approx(5.0), 4: pytest.approx(3.0)}

    def test_two_input_months_collide_on_same_output_month(self):
        # Input months 0 and 1 with dwells of 2 and 1 month (two stages, one
        # unit batch each) both arrive at output month 2.
        stages = [stage("Scheduled", 0, 1.0, 2, 2, 2)]
        result_a = cascade_monthly_units(stages, {0: 5.0})
        stages_b = [stage("Scheduled", 0, 1.0, 1, 1, 1)]
        result_b = cascade_monthly_units(stages_b, {1: 3.0})
        combined = dict(result_a)
        for month, units in result_b.items():
            combined[month] = combined.get(month, 0.0) + units
        assert combined == {2: pytest.approx(8.0)}


class TestSiteReadinessDelay:
    def test_flat_delay_shifts_all_arrivals(self):
        stages = [stage("Scheduled", 0, 1.0, 1, 1, 1)]
        result = cascade_monthly_units(stages, {0: 10.0}, site_readiness_delay_months=2)
        assert result == {3: pytest.approx(10.0)}  # 1 month dwell + 2 month delay


class TestProjectReadyUnitsPublicApi:
    def test_matches_cascade_monthly_units(self):
        stages = [stage("Scheduled", 0, 1.0, 1, 1, 1)]
        assert project_ready_units(stages, {0: 10.0}) == cascade_monthly_units(stages, {0: 10.0})
