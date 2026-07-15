"""
Deployment-capacity and scale-readiness model (spec section 5).

Commercial demand (Commercially Ready Units, from engine.deployment) does
not automatically convert into deployed units. This module gates readiness
against manufacturing, implementation-team, and commissioning capacity,
tracks the resulting backlog, computes revenue deferred by the bottleneck,
flags field-service coverage shortfalls, and supports capacity expansion
with a lead time and productivity ramp (spec sections 5.1-5.7).
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.schemas import CapacityEntry, CapacityType


def monthly_capacity_series(
    base_capacity: float,
    additions: list[CapacityEntry],
    num_months: int,
    capacity_type: CapacityType,
) -> dict[int, float]:
    """Available capacity of `capacity_type` for months 0..num_months-1,
    given a flat base capacity plus any capacity-expansion entries.

    Each addition activates `lead_time_months` (rounded) after simulation
    start, then ramps linearly from 0 to full `available_capacity` over
    `ramp_months` (spec section 5.7's "hiring or procurement lead time" and
    "productivity ramp period"). An addition with ramp_months == 0 is fully
    available the month it activates. `activation_date` on CapacityEntry is
    accepted by the schema for future calendar-aware scheduling but Core
    Release scheduling uses lead_time_months relative to simulation month 0.
    """
    series: dict[int, float] = {}
    relevant = [a for a in additions if a.capacity_type == capacity_type]

    for t in range(num_months):
        capacity = base_capacity
        for entry in relevant:
            activation_month = round(entry.lead_time_months)
            if t < activation_month:
                continue
            months_since_activation = t - activation_month
            if entry.ramp_months <= 0:
                fraction = 1.0
            else:
                fraction = min(1.0, (months_since_activation + 1) / entry.ramp_months)
            capacity += entry.available_capacity * fraction
        series[t] = capacity

    return series


@dataclass
class MonthlyCapacityResult:
    month: int
    available_to_deploy: float
    units_deployed: float
    backlog: float
    deferred_revenue: float
    manufacturing_capacity: float
    implementation_capacity: float
    commissioning_capacity: float
    manufacturing_utilization: float
    implementation_utilization: float
    commissioning_utilization: float


def run_capacity_model(
    newly_ready_units: dict[int, float],
    manufacturing_capacity: dict[int, float],
    implementation_capacity: dict[int, float],
    commissioning_capacity: dict[int, float],
    num_months: int,
    expected_revenue_per_unit_monthly: float = 0.0,
) -> list[MonthlyCapacityResult]:
    """Run the capacity-gated deployment model month by month.

    Units Deployed_t = min(Commercially Ready Units_t + Backlog_(t-1),
                            Manufacturing Capacity_t,
                            Implementation Capacity_t,
                            Commissioning Capacity_t)
    Deployment Backlog_t = Deployment Backlog_(t-1) + Newly Ready Units_t - Units Deployed_t
    Deferred Revenue_t = Backlog_t (undeployed ready units) x Expected Revenue per Unit_t
    """
    results: list[MonthlyCapacityResult] = []
    backlog = 0.0

    for t in range(num_months):
        ready_this_month = newly_ready_units.get(t, 0.0)
        available_to_deploy = backlog + ready_this_month

        mfg_cap = manufacturing_capacity.get(t, 0.0)
        impl_cap = implementation_capacity.get(t, 0.0)
        comm_cap = commissioning_capacity.get(t, 0.0)

        units_deployed = min(available_to_deploy, mfg_cap, impl_cap, comm_cap)
        units_deployed = max(0.0, units_deployed)

        new_backlog = backlog + ready_this_month - units_deployed
        deferred_revenue = new_backlog * expected_revenue_per_unit_monthly

        results.append(
            MonthlyCapacityResult(
                month=t,
                available_to_deploy=available_to_deploy,
                units_deployed=units_deployed,
                backlog=new_backlog,
                deferred_revenue=deferred_revenue,
                manufacturing_capacity=mfg_cap,
                implementation_capacity=impl_cap,
                commissioning_capacity=comm_cap,
                manufacturing_utilization=(units_deployed / mfg_cap) if mfg_cap > 0 else 0.0,
                implementation_utilization=(units_deployed / impl_cap) if impl_cap > 0 else 0.0,
                commissioning_utilization=(units_deployed / comm_cap) if comm_cap > 0 else 0.0,
            )
        )
        backlog = new_backlog

    return results


def required_service_fte(active_units: float, units_supported_per_fte: float) -> float:
    """Spec section 5.4: Required Service FTE_t = Active Units_t / Units Supported per Service FTE."""
    if units_supported_per_fte <= 0:
        raise ValueError("units_supported_per_fte must be positive")
    return active_units / units_supported_per_fte


@dataclass
class ServiceCoverageResult:
    required_fte: float
    available_fte: float
    shortfall_fte: float
    is_understaffed: bool


def check_service_coverage(active_units: float, available_fte: float, units_supported_per_fte: float) -> ServiceCoverageResult:
    """Flag scenarios where projected active units exceed available field-service
    coverage (spec section 5.4)."""
    required = required_service_fte(active_units, units_supported_per_fte)
    shortfall = max(0.0, required - available_fte)
    return ServiceCoverageResult(
        required_fte=required,
        available_fte=available_fte,
        shortfall_fte=shortfall,
        is_understaffed=shortfall > 0,
    )
