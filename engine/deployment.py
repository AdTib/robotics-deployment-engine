"""
Unit-level deployment funnel (spec section 4.2), pre-capacity-gating stages only.

Scope split (spec section 18 keeps funnel.py / deployment.py / capacity.py as
separate files):
  - engine.funnel produces a monthly "newly contracted units" series from the
    account-level commercial funnel.
  - engine.deployment (this module) cascades that series through the
    unconstrained pre-capacity deployment stages -- commercially committed,
    scheduled, in production/procurement, delivered to site -- using the same
    triangular-dwell-time logic as the commercial funnel, to produce a
    monthly "Commercially Ready Units" series.
  - engine.capacity then gates "Commercially Ready Units" against
    manufacturing/implementation/commissioning capacity (spec section 5's
    `Units Deployed_t = min(Commercially Ready Units_t, ...)` formula),
    producing the actual installed/commissioned/operational timeline,
    backlog, and deferred revenue.

Installed, commissioned, operational, and at-target-utilization are
therefore NOT modeled here: installed/commissioned/operational are
capacity-gated outcomes (engine.capacity), and at-target-utilization is the
utilization ramp applied to operational units (engine.economics).
"""

from __future__ import annotations

from engine.funnel import triangular_mean
from engine.schemas import FunnelStage

DEFAULT_DEPLOYMENT_STAGE_NAMES: list[str] = [
    "Units commercially committed",
    "Units scheduled",
    "Units in production or procurement",
    "Units delivered to site",
]


def _sorted_stages(stages: list[FunnelStage]) -> list[FunnelStage]:
    return sorted(stages, key=lambda s: s.stage_order)


def cascade_monthly_units(
    stages: list[FunnelStage],
    monthly_input: dict[int, float],
    site_readiness_delay_months: float = 0.0,
) -> dict[int, float]:
    """Cascade a monthly unit inflow series through deployment stages.

    Each stage applies its conversion_probability (units that fall out --
    e.g. a cancelled order -- do not proceed) and shifts surviving units
    forward by the stage's expected (triangular-mean) dwell time, rounded to
    the nearest whole month. `site_readiness_delay_months` (spec section 9.1)
    is an additional flat delay applied once, after all stages, to represent
    customer-site readiness (e.g. site not yet prepared to receive units).
    """
    current: dict[int, float] = dict(monthly_input)

    for stage in _sorted_stages(stages):
        dwell = round(triangular_mean(stage.dwell_min_months, stage.dwell_mode_months, stage.dwell_max_months))
        next_level: dict[int, float] = {}
        for month, units in current.items():
            surviving = units * stage.conversion_probability
            if surviving <= 0:
                continue
            arrival_month = month + dwell
            next_level[arrival_month] = next_level.get(arrival_month, 0.0) + surviving
        current = next_level

    if site_readiness_delay_months:
        shift = round(site_readiness_delay_months)
        current = {month + shift: units for month, units in current.items()}

    return current


def project_ready_units(
    stages: list[FunnelStage],
    monthly_committed_units: dict[int, float],
    site_readiness_delay_months: float = 0.0,
) -> dict[int, float]:
    """Public entry point: monthly newly-contracted units (from
    engine.funnel) -> monthly Commercially Ready Units (input to
    engine.capacity's capacity gating)."""
    return cascade_monthly_units(stages, monthly_committed_units, site_readiness_delay_months)
