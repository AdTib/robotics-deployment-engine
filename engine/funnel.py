"""
Commercial funnel (spec section 4.1) and account/site/unit translation (spec section 3).

Scope note: this module owns the ACCOUNT-LEVEL commercial funnel only --
target account through production-expansion contracted. Unit-level deployment
stages (installed, commissioned, operational, at-target-utilization) and
capacity constraints live in engine/deployment.py and engine/capacity.py
respectively (spec section 18 repository layout keeps these as separate
files with separate responsibilities).

Timing model: dwell time in each stage is Triangular(T_min, T_mode, T_max)
per spec section 4.3. This is the "deterministic first version" (spec
section 10.1) -- expected values and ranges are computed analytically from
the closed-form triangular distribution (mean, variance, and a normal
approximation for percentile ranges). No random sampling occurs anywhere in
this module; Monte Carlo sampling is explicitly Expansion Release scope
(spec section 10.2 / section 21.2) and is out of bounds for Core Release.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.schemas import Account, FunnelStage

DEFAULT_COMMERCIAL_STAGE_NAMES: list[str] = [
    "Target account",
    "Qualified opportunity",
    "Technical discovery",
    "Site and workflow assessment",
    "Commercial proposal",
    "Contracted pilot",
    "Pilot active",
    "Pilot technically accepted",
    "Production expansion contracted",
    "Multi-site or fleet expansion",
]

# z-scores for the standard normal distribution at common percentiles, used
# by the normal-approximation range below.
_Z_SCORE_BY_PERCENTILE: dict[float, float] = {
    0.10: -1.2815515655446004,
    0.90: 1.2815515655446004,
}


def triangular_mean(t_min: float, t_mode: float, t_max: float) -> float:
    """E[X] for X ~ Triangular(t_min, t_mode, t_max)."""
    return (t_min + t_mode + t_max) / 3.0


def triangular_variance(t_min: float, t_mode: float, t_max: float) -> float:
    """Var[X] for X ~ Triangular(t_min, t_mode, t_max)."""
    a, b, c = t_min, t_mode, t_max
    return (a**2 + b**2 + c**2 - a * b - a * c - b * c) / 18.0


def _sorted_stages(stages: list[FunnelStage]) -> list[FunnelStage]:
    return sorted(stages, key=lambda s: s.stage_order)


def expected_time_to_stage(stages: list[FunnelStage], stage_order: int) -> float:
    """Cumulative expected dwell time (months) to complete all stages up to and
    including `stage_order`, i.e. the expected time an opportunity spends
    before it exits that stage."""
    total = 0.0
    for stage in _sorted_stages(stages):
        if stage.stage_order > stage_order:
            break
        total += triangular_mean(stage.dwell_min_months, stage.dwell_mode_months, stage.dwell_max_months)
    return total


def time_to_stage_range(
    stages: list[FunnelStage], stage_order: int, low_pct: float = 0.10, high_pct: float = 0.90
) -> tuple[float, float]:
    """10th-to-90th percentile range (by default) for time to reach `stage_order`,
    using a normal approximation to the sum of independent triangular dwell
    times (mean and variance of a triangular distribution are exact closed
    forms; summing independent variances and applying a normal z-score is a
    standard deterministic approximation -- not Monte Carlo sampling)."""
    if low_pct not in _Z_SCORE_BY_PERCENTILE or high_pct not in _Z_SCORE_BY_PERCENTILE:
        raise ValueError(f"Unsupported percentile pair ({low_pct}, {high_pct}); supported: {sorted(_Z_SCORE_BY_PERCENTILE)}")

    mean_total = 0.0
    variance_total = 0.0
    for stage in _sorted_stages(stages):
        if stage.stage_order > stage_order:
            break
        mean_total += triangular_mean(stage.dwell_min_months, stage.dwell_mode_months, stage.dwell_max_months)
        variance_total += triangular_variance(stage.dwell_min_months, stage.dwell_mode_months, stage.dwell_max_months)

    std_total = math.sqrt(variance_total)
    low = mean_total + _Z_SCORE_BY_PERCENTILE[low_pct] * std_total
    high = mean_total + _Z_SCORE_BY_PERCENTILE[high_pct] * std_total
    return max(0.0, low), high


def expected_units_for_cohort(stages: list[FunnelStage], entrants: float = 1.0) -> float:
    """Expected operational-track units produced by a cohort of `entrants`
    opportunities entering the funnel, per spec section 4.4:

        E[Units] = sum over milestone stages of
                   P(reach stage) * expected_units(stage) * entrants
                   + expansion contribution at that stage

    A "milestone stage" is any stage with expected_units > 0 (e.g. the pilot
    stage carries the pilot's unit count; the production-expansion stage
    carries the initial production deployment size). P(reach stage) is the
    cumulative product of conversion_probability across all stages up to and
    including that stage. Expansion at a milestone stage adds
    expected_units * expansion_probability * (expansion_multiple - 1) on top
    of the milestone's own units, representing the incremental units from a
    successful expansion beyond the base commitment.
    """
    survival = 1.0
    total_units = 0.0
    for stage in _sorted_stages(stages):
        survival *= stage.conversion_probability
        if stage.expected_units <= 0:
            continue
        base_units = survival * stage.expected_units * entrants
        expansion_units = base_units * stage.expansion_probability * (stage.expansion_multiple - 1.0)
        total_units += base_units + expansion_units
    return total_units


def survival_to_stage(stages: list[FunnelStage], stage_order: int) -> float:
    """Cumulative probability an entrant reaches (converts into) `stage_order`."""
    survival = 1.0
    for stage in _sorted_stages(stages):
        if stage.stage_order > stage_order:
            break
        survival *= stage.conversion_probability
    return survival


@dataclass
class CohortProjection:
    """Monthly-indexed expected newly-contracted units produced by a single
    monthly cohort of opportunities, keyed by calendar month index (0-based,
    relative to the start of the simulation, not the cohort's own entry
    month)."""

    cohort_start_month: int
    entrants: float
    monthly_contracted_units: dict[int, float]

    @property
    def total_contracted_units(self) -> float:
        return sum(self.monthly_contracted_units.values())


def project_cohort(stages: list[FunnelStage], entrants: float, cohort_start_month: int) -> CohortProjection:
    """Project a single cohort's expected contracted-unit output by month.

    For each milestone stage (expected_units > 0), the stage's expected unit
    contribution (base + expansion, per `expected_units_for_cohort`'s logic)
    is placed at the cohort's expected arrival month for that stage: the
    cohort's start month plus the cumulative expected dwell time to that
    stage, rounded to the nearest whole month.
    """
    monthly: dict[int, float] = {}
    survival = 1.0
    cumulative_dwell = 0.0
    for stage in _sorted_stages(stages):
        cumulative_dwell += triangular_mean(stage.dwell_min_months, stage.dwell_mode_months, stage.dwell_max_months)
        survival *= stage.conversion_probability
        if stage.expected_units <= 0:
            continue
        base_units = survival * stage.expected_units * entrants
        expansion_units = base_units * stage.expansion_probability * (stage.expansion_multiple - 1.0)
        stage_units = base_units + expansion_units
        arrival_month = cohort_start_month + round(cumulative_dwell)
        monthly[arrival_month] = monthly.get(arrival_month, 0.0) + stage_units

    return CohortProjection(cohort_start_month=cohort_start_month, entrants=entrants, monthly_contracted_units=monthly)


def aggregate_cohorts(projections: list[CohortProjection]) -> dict[int, float]:
    """Combine multiple cohorts' monthly contracted-unit projections into one
    monthly series (spec section 4.5 -- cohorts, not a static snapshot)."""
    combined: dict[int, float] = {}
    for projection in projections:
        for month, units in projection.monthly_contracted_units.items():
            combined[month] = combined.get(month, 0.0) + units
    return combined


def total_units_for_account(account: Account) -> int:
    """Account -> site -> pilot -> unit translation (spec section 3): total
    committed unit count across every pilot at every site under this account.
    An account is never assumed to equal a single deployment."""
    return sum(pilot.unit_count for site in account.sites for pilot in site.pilots)
