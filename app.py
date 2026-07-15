"""
Robotics Deployment Economics, Scale Readiness & Customer Diversification Engine
-- Streamlit interface.

This file wires together the input panels and output views built on top of
the tested engine/ modules. It contains no calculation logic of its own.
"""

from __future__ import annotations

import streamlit as st

from app.inputs import (
    render_business_model_panel,
    render_capacity_panel,
    render_commercial_funnel_panel,
    render_customer_portfolio_panel,
    render_deployment_funnel_panel,
)
from app.demo_presets import render_demo_presets_view
from app.outputs import render_capacity_view, render_concentration_view, render_economics_view, render_funnel_view
from app.scenario_builder import render_scenario_simulator_view
from app.scenario_state import build_scenario_assumptions, missing_inputs, run_base_scenario
from app.theme import inject_theme

st.set_page_config(page_title="Robotics Deployment Engine", layout="wide", initial_sidebar_state="expanded")
inject_theme()

st.title("Deployment Economics Engine")
st.caption(
    "Core Release build: RaaS commercial-model preset only, deterministic scenarios only, "
    "backlog concentration basis only. See README.md for full scope notes."
)

page = st.sidebar.radio("Page", ["Inputs", "Funnel View", "Capacity View", "Fleet Economics View", "Concentration View", "Scenario Simulator", "Worked Examples"])

if page == "Inputs":
    tabs = st.tabs(["Business Model", "Commercial Funnel", "Deployment Funnel", "Deployment Capacity", "Customer Portfolio"])
    with tabs[0]:
        render_business_model_panel()
    with tabs[1]:
        render_commercial_funnel_panel()
    with tabs[2]:
        render_deployment_funnel_panel()
    with tabs[3]:
        render_capacity_panel()
    with tabs[4]:
        render_customer_portfolio_panel()

    st.divider()
    st.subheader("Input status")
    checks = {
        "Unit economics": st.session_state.get("unit_economics") is not None,
        "Company assumptions": st.session_state.get("company_assumptions") is not None,
        "Commercial funnel stages": st.session_state.get("commercial_stages") is not None,
        "Deployment funnel stages": st.session_state.get("deployment_stages") is not None,
        "Existing customers": st.session_state.get("existing_customers") is not None,
    }
    for label, ok in checks.items():
        st.write(("✅ " if ok else "❌ ") + label)

elif page == "Funnel View":
    if missing_inputs():
        st.warning(f"Fill in the Inputs page first. Missing: {', '.join(missing_inputs())}")
    else:
        assumptions, summary = run_base_scenario()
        render_funnel_view(assumptions, summary)

elif page == "Capacity View":
    if missing_inputs():
        st.warning(f"Fill in the Inputs page first. Missing: {', '.join(missing_inputs())}")
    else:
        assumptions, summary = run_base_scenario()
        render_capacity_view(assumptions, summary)

elif page == "Fleet Economics View":
    if missing_inputs():
        st.warning(f"Fill in the Inputs page first. Missing: {', '.join(missing_inputs())}")
    else:
        assumptions, summary = run_base_scenario()
        render_economics_view(assumptions, summary)

elif page == "Concentration View":
    if missing_inputs():
        st.warning(f"Fill in the Inputs page first. Missing: {', '.join(missing_inputs())}")
    else:
        assumptions, summary = run_base_scenario()
        render_concentration_view(assumptions, summary)

elif page == "Scenario Simulator":
    if missing_inputs():
        st.warning(f"Fill in the Inputs page first. Missing: {', '.join(missing_inputs())}")
    else:
        base_assumptions = build_scenario_assumptions("Base case")
        render_scenario_simulator_view(base_assumptions)

elif page == "Worked Examples":
    render_demo_presets_view()
