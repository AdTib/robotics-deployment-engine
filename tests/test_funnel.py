import math

import pytest

from engine.funnel import (
    CohortProjection,
    aggregate_cohorts,
    expected_time_to_stage,
    expected_units_for_cohort,
    project_cohort,
    survival_to_stage,
    time_to_stage_range,
    total_units_for_account,
    triangular_mean,
    triangular_variance,
)
from engine.schemas import Account, FunnelStage, Pilot, Site


def stage(name, order, prob, dmin, dmode, dmax, units=0.0, exp_prob=0.0, exp_mult=1.0):
    return FunnelStage(
        stage_name=name,
        stage_order=order,
        conversion_probability=prob,
        dwell_min_months=dmin,
        dwell_mode_months=dmode,
        dwell_max_months=dmax,
        expected_units=units,
        expansion_probability=exp_prob,
        expansion_multiple=exp_mult,
    )


class TestTriangularStats:
    def test_mean_hand_calculated(self):
        assert triangular_mean(1, 2, 3) == pytest.approx(2.0)

    def test_variance_hand_calculated(self):
        # Var = (a^2+b^2+c^2-ab-ac-bc)/18 = (1+4+9-2-3-6)/18 = 3/18 = 1/6
        assert triangular_variance(1, 2, 3) == pytest.approx(1.0 / 6.0)


class TestFullConversionFixedDwell:
    """Required funnel test: 100% conversion with fixed dwell time."""

    def test_expected_time_equals_fixed_dwell(self):
        stages = [stage("A", 0, 1.0, 2, 2, 2), stage("B", 1, 1.0, 3, 3, 3)]
        assert expected_time_to_stage(stages, 1) == pytest.approx(5.0)

    def test_full_survival(self):
        stages = [stage("A", 0, 1.0, 2, 2, 2), stage("B", 1, 1.0, 3, 3, 3)]
        assert survival_to_stage(stages, 1) == pytest.approx(1.0)


class TestZeroConversion:
    """Required funnel test: zero conversion at one stage."""

    def test_zero_conversion_kills_downstream_units(self):
        stages = [
            stage("A", 0, 1.0, 1, 1, 1, units=10),
            stage("B", 1, 0.0, 1, 1, 1, units=20),
        ]
        # Stage A still contributes its own units; stage B's conversion is zero
        # so survival to B is zero and it contributes nothing.
        assert survival_to_stage(stages, 1) == pytest.approx(0.0)
        total = expected_units_for_cohort(stages, entrants=1.0)
        assert total == pytest.approx(10.0)  # only stage A's units count


class TestMultiStageExpectedValue:
    """Required funnel test: multi-stage expected-value calculation."""

    def test_hand_calculated_two_milestone_stages(self):
        # Stage A: 50% conversion, 5 units, no expansion.
        # Stage B: 40% conversion (conditional on A), 8 units, no expansion.
        stages = [
            stage("Pilot", 0, 0.5, 1, 2, 3, units=5),
            stage("Production", 1, 0.4, 2, 3, 4, units=8),
        ]
        # E = 0.5*5 + (0.5*0.4)*8 = 2.5 + 1.6 = 4.1
        assert expected_units_for_cohort(stages) == pytest.approx(4.1)

    def test_scales_with_entrants(self):
        stages = [stage("Pilot", 0, 0.5, 1, 2, 3, units=5)]
        assert expected_units_for_cohort(stages, entrants=10) == pytest.approx(25.0)


class TestPilotToExpansionConversion:
    """Required funnel test: pilot-to-expansion conversion."""

    def test_expansion_adds_incremental_units(self):
        # Pilot stage: 100% conversion, 5 units, 40% chance of a 3x expansion.
        stages = [stage("Pilot", 0, 1.0, 1, 1, 1, units=5, exp_prob=0.4, exp_mult=3.0)]
        # base = 5, expansion = 5 * 0.4 * (3-1) = 4 -> total 9
        assert expected_units_for_cohort(stages) == pytest.approx(9.0)

    def test_zero_expansion_probability_no_change(self):
        stages = [stage("Pilot", 0, 1.0, 1, 1, 1, units=5, exp_prob=0.0, exp_mult=3.0)]
        assert expected_units_for_cohort(stages) == pytest.approx(5.0)


class TestTimeToStageRange:
    def test_range_brackets_mean(self):
        stages = [stage("A", 0, 1.0, 10, 15, 30)]
        low, high = time_to_stage_range(stages, 0)
        mean = expected_time_to_stage(stages, 0)
        assert low < mean < high

    def test_invalid_percentiles_raise(self):
        stages = [stage("A", 0, 1.0, 10, 15, 30)]
        with pytest.raises(ValueError):
            time_to_stage_range(stages, 0, low_pct=0.05, high_pct=0.95)


class TestCohortTiming:
    """Required funnel test: cohort timing."""

    def test_units_land_in_expected_month(self):
        # Single stage, dwell mean = 3 months exactly, entering month 0.
        stages = [stage("Pilot", 0, 1.0, 3, 3, 3, units=10)]
        projection = project_cohort(stages, entrants=1.0, cohort_start_month=0)
        assert projection.monthly_contracted_units == {3: 10.0}
        assert projection.total_contracted_units == pytest.approx(10.0)

    def test_cohort_start_month_offsets_arrival(self):
        stages = [stage("Pilot", 0, 1.0, 3, 3, 3, units=10)]
        projection = project_cohort(stages, entrants=1.0, cohort_start_month=5)
        assert projection.monthly_contracted_units == {8: 10.0}

    def test_aggregate_cohorts_sums_overlapping_months(self):
        stages = [stage("Pilot", 0, 1.0, 2, 2, 2, units=4)]
        p1 = project_cohort(stages, entrants=1.0, cohort_start_month=0)  # lands month 2
        p2 = project_cohort(stages, entrants=1.0, cohort_start_month=2)  # lands month 4
        p3 = project_cohort(stages, entrants=1.0, cohort_start_month=0)  # also lands month 2
        combined = aggregate_cohorts([p1, p2, p3])
        assert combined == {2: 8.0, 4: 4.0}


class TestAccountToSiteToUnitTranslation:
    """Required funnel test: account-to-site-to-unit translation."""

    def test_sums_units_across_sites_and_pilots(self):
        account = Account(
            account_id="acc-1",
            name="Acme Logistics",
            sites=[
                Site(
                    site_id="site-1",
                    account_id="acc-1",
                    name="Dallas DC",
                    pilots=[
                        Pilot(pilot_id="p1", site_id="site-1", unit_count=3, start_month=0),
                        Pilot(pilot_id="p2", site_id="site-1", unit_count=2, start_month=4),
                    ],
                ),
                Site(
                    site_id="site-2",
                    account_id="acc-1",
                    name="Houston DC",
                    pilots=[Pilot(pilot_id="p3", site_id="site-2", unit_count=5, start_month=6)],
                ),
            ],
        )
        # One signed account does not automatically equal one deployment --
        # this must sum across sites and pilots, not assume a single unit count.
        assert total_units_for_account(account) == 10

    def test_account_with_no_sites_has_zero_units(self):
        account = Account(account_id="acc-2", name="Empty Co", sites=[])
        assert total_units_for_account(account) == 0
