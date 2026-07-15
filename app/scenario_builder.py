"""
Integrated scenario simulator view (spec section 9, section 19.2 Scenario
Comparison). Deterministic scenarios only (spec section 21.1/25 scope
constraint) -- every scenario here is a call into one of the
engine.simulation.make_*_scenario deterministic transforms plus
engine.simulation.run_scenario. There is no random sampling, no probability
distribution over outcomes, and no UI element implying one (no confidence
intervals, no "probability of X" language) -- Monte Carlo is Expansion
Release (section 10.2/21.2) and does not exist in this engine yet.
"""

from __future__ import annotations

import streamlit as st

from app.charts import monthly_line_chart
from engine.schemas import CapacityEntry
from engine.simulation import (
    ScenarioAssumptions,
    compare_scenarios,
    make_anchor_customer_scenario,
    make_capacity_constrained_scenario,
    make_capacity_expansion_scenario,
    make_diversified_scenario,
    make_fast_conversion_scenario,
    make_service_cost_downside_scenario,
    make_slow_conversion_scenario,
    make_utilization_downside_scenario,
    run_scenario,
)

SCENARIO_BUILDERS = {
    "Base case": lambda base: base,
    "Slow conversion": make_slow_conversion_scenario,
    "Fast conversion": make_fast_conversion_scenario,
    "Anchor-customer strategy": make_anchor_customer_scenario,
    "Diversified-account strategy": make_diversified_scenario,
    "Capacity-constrained": make_capacity_constrained_scenario,
    "Utilization downside": make_utilization_downside_scenario,
    "Service-cost downside": make_service_cost_downside_scenario,
}


def render_scenario_simulator_view(base_assumptions: ScenarioAssumptions) -> None:
    st.subheader("Integrated Scenario Simulator")
    st.caption(
        "Deterministic scenarios only (spec section 9.2) -- each option below calls a "
        "`engine.simulation.make_*_scenario` transform, then `run_scenario`. No Monte Carlo, "
        "no probability distributions, no confidence intervals on this page."
    )

    default_selection = ["Base case", "Anchor-customer strategy", "Diversified-account strategy"]
    selected = st.multiselect("Scenarios to compare", list(SCENARIO_BUILDERS.keys()), default=default_selection, key="in_selected_scenarios")

    include_capacity_expansion = st.checkbox(
        "Also include Capacity-expansion strategy (requires at least one entry in the Deployment Capacity panel's expansion table)",
        value=False,
        key="in_include_capacity_expansion",
    )

    if not selected and not include_capacity_expansion:
        st.info("Select at least one scenario above.")
        return

    summaries = []
    for name in selected:
        builder = SCENARIO_BUILDERS[name]
        assumptions = builder(base_assumptions)
        summaries.append(run_scenario(assumptions))

    if include_capacity_expansion:
        additions: list[CapacityEntry] = base_assumptions.capacity_additions
        if not additions:
            st.warning("No capacity-expansion entries found -- add one in the Deployment Capacity input panel to include this scenario.")
        else:
            expansion_assumptions = make_capacity_expansion_scenario(base_assumptions, additions)
            summaries.append(run_scenario(expansion_assumptions))

    if not summaries:
        return

    st.markdown("**Scenario comparison table** (`engine.simulation.compare_scenarios`, spec section 9.4)")
    rows = compare_scenarios(summaries)
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Operational units by month, per scenario**")
    months = list(range(base_assumptions.num_months))
    st.plotly_chart(
        monthly_line_chart(months, {s.scenario_name: [r.active_units for r in s.monthly_results] for s in summaries}, "Operational (Active) Units by Scenario", "Units"),
        use_container_width=True,
    )

    st.markdown("**Cumulative cash flow by month, per scenario**")
    st.plotly_chart(
        monthly_line_chart(months, {s.scenario_name: [r.cumulative_cash_flow for r in s.monthly_results] for s in summaries}, "Cumulative Cash Flow by Scenario", "$"),
        use_container_width=True,
    )

    st.markdown("**Backlog HHI by month, per scenario**")
    st.plotly_chart(
        monthly_line_chart(
            months,
            {s.scenario_name: [r.hhi_standard if r.hhi_standard is not None else 0.0 for r in s.monthly_results] for s in summaries},
            "Backlog HHI by Scenario",
            "HHI",
        ),
        use_container_width=True,
    )
    st.caption("HHI shown as 0 for months before any contracted backlog exists in a given scenario (not a modeled value of zero concentration).")
