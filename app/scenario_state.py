"""
Assembles engine.simulation.ScenarioAssumptions from whatever the input
panels (app/inputs.py) have placed in st.session_state, and runs it through
engine.simulation.run_scenario. No calculation logic lives here -- this is
object construction plus a single call into the tested engine.
"""

from __future__ import annotations

import streamlit as st

from engine.simulation import ScenarioAssumptions, ScenarioSummary, run_scenario

REQUIRED_KEYS = [
    "unit_economics",
    "company_assumptions",
    "commercial_stages",
    "deployment_stages",
    "existing_customers",
]


def missing_inputs() -> list[str]:
    return [k for k in REQUIRED_KEYS if st.session_state.get(k) is None]


def build_scenario_assumptions(scenario_name: str = "base") -> ScenarioAssumptions | None:
    if missing_inputs():
        return None

    return ScenarioAssumptions(
        scenario_name=scenario_name,
        commercial_stages=st.session_state["commercial_stages"],
        deployment_stages=st.session_state["deployment_stages"],
        opportunities_per_month=st.session_state.get("opportunities_per_month", {}),
        company_assumptions=st.session_state["company_assumptions"],
        commissioning_capacity_monthly=st.session_state.get("commissioning_capacity_monthly", 0.0),
        unit_economics=st.session_state["unit_economics"],
        backlog_value_per_unit=st.session_state.get("backlog_value_per_unit", 0.0),
        num_months=st.session_state.get("num_months", 36),
        capacity_additions=st.session_state.get("capacity_additions", []),
        existing_customers=st.session_state["existing_customers"],
        new_account_strategy=st.session_state.get("new_account_strategy", "diversified"),
        new_account_backlog_value=st.session_state.get("new_account_backlog_value", 0.0),
        desired_cash_buffer=st.session_state.get("desired_cash_buffer", 0.0),
        site_readiness_delay_months=st.session_state.get("site_readiness_delay_months", 0.0),
    )


def run_base_scenario() -> tuple[ScenarioAssumptions, ScenarioSummary] | None:
    assumptions = build_scenario_assumptions("base")
    if assumptions is None:
        return None
    return assumptions, run_scenario(assumptions)
