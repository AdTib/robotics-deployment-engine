"""
Bot Auto and Symbotic worked-example presets (spec sections 13-14, 19.3).

Every value here is displayed with its source classification (disclosed /
derived / assumed / scenario) via app.source_labels -- not just documented
in the README. The two Bot Auto figures that could not be independently
verified during this build (BOTAUTO-003/004: the 30-truck 2026 / 100-truck
breakeven targets) are shown with their 'assumed' / 'low confidence' badges
directly in this view, and the Bedrock Robotics construction-vs-trucking
segment correction is shown wherever calibration segment defaults surface
(the calibration table below, and the Commercial Funnel input panel would
draw on the same table if it offered segment presets).

Loading a preset only writes values into st.session_state (or hands data to
engine.concentration.compute_concentration for a live check) -- it does not
compute anything new.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.data_loading import (
    load_bot_auto_demo_inputs,
    load_calibration_timelines,
    load_source_registry,
    load_symbotic_demo_customers,
    symbotic_entries_from_df,
)
from app.source_labels import classification_legend, render_source_registry_row, render_source_registry_table
from engine.concentration import compute_concentration


def _bot_auto_value(df: pd.DataFrame, name: str) -> float:
    return float(df[df["input_name"] == name].iloc[0]["value"])


def render_demo_presets_view() -> None:
    st.subheader("Worked Examples & Source Calibration")
    st.caption("Every demo value below is labeled per spec section 11's source classification -- not just in the README.")
    classification_legend()

    registry = load_source_registry()

    st.divider()
    st.markdown("### Calibration timeline reference (spec section 12)")
    calibration = load_calibration_timelines()
    st.dataframe(calibration, use_container_width=True, hide_index=True)

    bedrock_row = calibration[calibration["company"] == "Bedrock Robotics"].iloc[0]
    st.warning(
        "**Segment correction:** " + bedrock_row["notes_on_comparability"],
        icon="⚠️",
    )

    st.divider()
    st.markdown("### Bot Auto: implied-economics sensitivity case (spec section 13)")
    st.caption("Treated as an implied-economics sensitivity case, never as a reconstruction of Bot Auto's actual P&L (spec section 13/24).")

    bot_auto_registry = registry[registry["company"] == "Bot Auto"]
    for _, row in bot_auto_registry.iterrows():
        render_source_registry_row(row)

    bot_auto_inputs = load_bot_auto_demo_inputs()
    st.markdown("**Sensitivity matrix: assumed annual fixed costs -> required annual contribution per truck at a 100-truck target**")
    matrix_rows = []
    for label, fixed_key, contrib_key in [
        ("Low", "assumed_annual_fixed_costs_case_low", "required_annual_contribution_per_truck_case_low"),
        ("Mid-low", "assumed_annual_fixed_costs_case_mid_low", "required_annual_contribution_per_truck_case_mid_low"),
        ("Mid-high", "assumed_annual_fixed_costs_case_mid_high", "required_annual_contribution_per_truck_case_mid_high"),
        ("High", "assumed_annual_fixed_costs_case_high", "required_annual_contribution_per_truck_case_high"),
    ]:
        matrix_rows.append(
            {
                "Case": label,
                "Assumed annual fixed costs ($)": f"{_bot_auto_value(bot_auto_inputs, fixed_key):,.0f}",
                "Required annual contribution per truck ($)": f"{_bot_auto_value(bot_auto_inputs, contrib_key):,.0f}",
            }
        )
    st.dataframe(matrix_rows, use_container_width=True, hide_index=True)
    st.caption("Both columns are 'derived' (spec section 11.1) -- computed directly from the assumed fixed-cost cases and the 100-truck target, not fabricated facts about Bot Auto.")

    st.markdown("**Load Bot Auto sensitivity-case assumptions into the Business Model panel**")
    case_choice = st.selectbox("Fixed-cost case to load", ["Low ($5M)", "Mid-low ($10M)", "Mid-high ($15M)", "High ($20M)"], key="in_bot_auto_case_choice")
    case_key_map = {
        "Low ($5M)": "assumed_annual_fixed_costs_case_low",
        "Mid-low ($10M)": "assumed_annual_fixed_costs_case_mid_low",
        "Mid-high ($15M)": "assumed_annual_fixed_costs_case_mid_high",
        "High ($20M)": "assumed_annual_fixed_costs_case_high",
    }
    if st.button("Load Bot Auto preset", key="load_bot_auto_preset"):
        annual_fixed = _bot_auto_value(bot_auto_inputs, case_key_map[case_choice])
        annual_revenue_per_truck = _bot_auto_value(bot_auto_inputs, "assumed_annual_revenue_per_truck")
        annual_variable_cost_per_truck = _bot_auto_value(bot_auto_inputs, "assumed_annual_variable_operating_cost_per_truck")
        st.session_state["in_hardware_cost"] = _bot_auto_value(bot_auto_inputs, "assumed_upfront_autonomy_system_cost_per_truck")
        st.session_state["in_deployment_cost"] = _bot_auto_value(bot_auto_inputs, "assumed_deployment_cost_per_truck")
        st.session_state["in_base_revenue"] = annual_revenue_per_truck / 12.0
        st.session_state["in_variable_cost"] = annual_variable_cost_per_truck / 12.0
        st.session_state["in_fixed_cost"] = annual_fixed / 12.0
        st.success(
            f"Loaded. Fixed cost set to \\${annual_fixed / 12.0:,.0f}/month. Open the **Business Model** tab once "
            f"(this applies the preset -- Streamlit only rebuilds a tab's values when you visit it), then check "
            f"Fleet Economics View for the resulting Operating Breakeven Fleet Size versus the "
            f"{int(_bot_auto_value(bot_auto_inputs, 'target_operating_breakeven_fleet_size'))}-truck target "
            f"(BOTAUTO-004, flagged assumed/low-confidence above)."
        )
        st.rerun()

    st.divider()
    st.markdown("### Symbotic: backlog concentration case (spec section 14)")
    st.caption("Backlog concentration, not recognized revenue (spec section 8.5/14). Customer-by-customer split is not separately disclosed -- multiple sensitivity scenarios are shown rather than one estimate presented as fact.")

    symbotic_registry = registry[registry["company"] == "Symbotic"]
    for _, row in symbotic_registry.iterrows():
        render_source_registry_row(row)

    symbotic_df = load_symbotic_demo_customers()
    scenario_choice = st.radio(
        "Backlog-split sensitivity scenario",
        ["equal_split_assumed", "walmart_heavy_assumed", "greenbox_floor_bound"],
        key="in_symbotic_scenario_choice",
        help="All three are labeled 'assumed' allocations of the disclosed $22.5B total backlog -- none is presented as the confirmed split.",
    )
    scenario_rows = symbotic_df[symbotic_df["scenario"] == scenario_choice]
    st.dataframe(
        scenario_rows[["customer_id", "customer_name", "contracted_backlog_usd", "share_of_total_backlog", "classification", "notes"]],
        use_container_width=True,
        hide_index=True,
    )

    entries = symbotic_entries_from_df(symbotic_df, scenario_choice)
    live_result = compute_concentration(entries, basis="backlog")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Largest-customer share", f"{live_result.largest_customer_share:.1%}")
    col2.metric("Top-three share", f"{live_result.top_three_share:.1%}")
    col3.metric("HHI (standard)", f"{live_result.hhi_standard:,.0f}")
    col4.metric("Effective customer count", f"{live_result.effective_customer_count:.2f}")
    st.caption("Computed live by `engine.concentration.compute_concentration` on the scenario shown above -- not a precomputed/hardcoded figure.")

    if st.button("Load this Symbotic scenario into Customer Portfolio", key="load_symbotic_preset"):
        new_df = pd.DataFrame([{"customer_id": e.customer_id, "customer_name": e.customer_name, "contracted_backlog": e.contracted_backlog} for e in entries])
        st.session_state["in_customers_preset_df"] = new_df
        st.session_state["customers_editor_version"] = st.session_state.get("customers_editor_version", 0) + 1
        st.success(
            "Loaded. Open the **Customer Portfolio** tab once (this applies the preset -- Streamlit only "
            "rebuilds a tab's values when you visit it), then check Concentration View."
        )
        st.rerun()

    st.divider()
    render_source_registry_table(registry)
