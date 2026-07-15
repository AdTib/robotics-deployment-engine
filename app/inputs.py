"""
Input panels (spec section 19.1). Every panel here only collects values and
hands them to engine.schemas / engine.validation -- no economics, funnel,
capacity, or concentration math is computed in this module. Constructed
objects are stashed in st.session_state so the output-view pages (built
next) can read them without re-rendering the widgets.

Only RaaS (commercial model) and backlog (concentration basis) are
selectable, per spec section 25's scope constraint -- see
source_labels.render_locked_selector for how the other options are shown
but disabled.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.source_labels import render_locked_selector
from engine.schemas import CapacityEntry, CompanyAssumptions, CustomerConcentrationEntry, FunnelStage, UnitEconomics, UtilizationRampPoint
from engine.validation import (
    validate_capacity_entries,
    validate_company_assumptions,
    validate_customer_concentration_entries,
    validate_funnel_stages,
    validate_unit_economics,
)

DEFAULT_UTILIZATION_RAMP = pd.DataFrame(
    [
        {"month_since_commissioning": 0, "utilization": 0.25},
        {"month_since_commissioning": 1, "utilization": 0.40},
        {"month_since_commissioning": 2, "utilization": 0.65},
        {"month_since_commissioning": 3, "utilization": 0.85},
        {"month_since_commissioning": 4, "utilization": 1.00},
    ]
)

DEFAULT_COMMERCIAL_STAGES = pd.DataFrame(
    [
        {"stage_name": "Target account", "stage_order": 0, "conversion_probability": 1.0, "dwell_min_months": 0.5, "dwell_mode_months": 1.0, "dwell_max_months": 2.0, "expected_units": 0.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
        {"stage_name": "Qualified opportunity", "stage_order": 1, "conversion_probability": 0.6, "dwell_min_months": 1.0, "dwell_mode_months": 2.0, "dwell_max_months": 4.0, "expected_units": 0.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
        {"stage_name": "Pilot active", "stage_order": 2, "conversion_probability": 0.7, "dwell_min_months": 3.0, "dwell_mode_months": 6.0, "dwell_max_months": 12.0, "expected_units": 5.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
        {"stage_name": "Production expansion contracted", "stage_order": 3, "conversion_probability": 0.5, "dwell_min_months": 2.0, "dwell_mode_months": 4.0, "dwell_max_months": 8.0, "expected_units": 15.0, "expansion_probability": 0.4, "expansion_multiple": 3.0},
    ]
)

DEFAULT_DEPLOYMENT_STAGES = pd.DataFrame(
    [
        {"stage_name": "Units commercially committed", "stage_order": 0, "conversion_probability": 0.95, "dwell_min_months": 0.0, "dwell_mode_months": 1.0, "dwell_max_months": 1.0, "expected_units": 0.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
        {"stage_name": "Units scheduled", "stage_order": 1, "conversion_probability": 0.97, "dwell_min_months": 1.0, "dwell_mode_months": 2.0, "dwell_max_months": 3.0, "expected_units": 0.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
        {"stage_name": "Units in production or procurement", "stage_order": 2, "conversion_probability": 0.98, "dwell_min_months": 2.0, "dwell_mode_months": 4.0, "dwell_max_months": 8.0, "expected_units": 0.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
        {"stage_name": "Units delivered to site", "stage_order": 3, "conversion_probability": 0.99, "dwell_min_months": 1.0, "dwell_mode_months": 2.0, "dwell_max_months": 4.0, "expected_units": 0.0, "expansion_probability": 0.0, "expansion_multiple": 1.0},
    ]
)

DEFAULT_CAPACITY = pd.DataFrame(
    [
        {"capacity_type": "manufacturing", "available_capacity": 8.0, "unit_of_measure": "units/month", "lead_time_months": 0.0, "upfront_cost": 0.0, "monthly_cost": 0.0, "ramp_months": 0.0},
        {"capacity_type": "commissioning", "available_capacity": 10.0, "unit_of_measure": "units/month", "lead_time_months": 0.0, "upfront_cost": 0.0, "monthly_cost": 0.0, "ramp_months": 0.0},
    ]
)

DEFAULT_CAPACITY_ADDITIONS = pd.DataFrame(
    [
        {"capacity_type": "manufacturing", "available_capacity": 6.0, "unit_of_measure": "units/month", "lead_time_months": 6.0, "upfront_cost": 500_000.0, "monthly_cost": 20_000.0, "ramp_months": 3.0},
    ]
)

DEFAULT_CUSTOMERS = pd.DataFrame(
    [
        {"customer_id": "cust_1", "customer_name": "Anchor Customer", "contracted_backlog": 5_000_000.0},
        {"customer_id": "cust_2", "customer_name": "Mid-size Customer A", "contracted_backlog": 1_500_000.0},
        {"customer_id": "cust_3", "customer_name": "Mid-size Customer B", "contracted_backlog": 1_000_000.0},
    ]
)


def _sv(key: str, fallback):
    """Read a widget's current session_state value, falling back to a
    default. Passing this (rather than a bare literal) as a widget's
    `value=` argument is required for programmatic presets to work: if both
    `value=<literal>` and `key=` are passed to a Streamlit widget, the
    literal wins on every rerun and silently overwrites anything written to
    st.session_state[key] beforehand (a well-known Streamlit gotcha)."""
    return st.session_state.get(key, fallback)


def _stage_df_to_list(df: pd.DataFrame) -> list[FunnelStage]:
    return [
        FunnelStage(
            stage_name=row["stage_name"],
            stage_order=int(row["stage_order"]),
            conversion_probability=float(row["conversion_probability"]),
            dwell_min_months=float(row["dwell_min_months"]),
            dwell_mode_months=float(row["dwell_mode_months"]),
            dwell_max_months=float(row["dwell_max_months"]),
            expected_units=float(row["expected_units"]),
            expansion_probability=float(row["expansion_probability"]),
            expansion_multiple=float(row["expansion_multiple"]),
        )
        for _, row in df.iterrows()
    ]


def render_business_model_panel() -> None:
    """Spec 19.1 'Business Model' page: commercial model (RaaS-locked),
    pricing, unit cost, deployment cost, support cost, fixed cost, payment
    timing, opening cash."""
    st.subheader("Business Model")
    render_locked_selector("Commercial model", "RaaS", ["Direct Sale", "Hybrid"])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Unit cost & payment**")
        hardware_cost = st.number_input("Hardware cost per unit ($)", min_value=0.0, value=_sv("in_hardware_cost", 40_000.0), step=1_000.0, key="in_hardware_cost")
        deployment_cost = st.number_input("Deployment/installation cost per unit ($)", min_value=0.0, value=_sv("in_deployment_cost", 10_000.0), step=1_000.0, key="in_deployment_cost")
        upfront_payment = st.number_input("Upfront customer payment per unit ($)", min_value=0.0, value=_sv("in_upfront_payment", 0.0), step=1_000.0, key="in_upfront_payment")
        residual_value = st.number_input("Residual value per unit at contract end ($)", min_value=0.0, value=_sv("in_residual_value", 0.0), step=500.0, key="in_residual_value")
        contract_term = st.number_input("Contract term (months)", min_value=1, value=_sv("in_contract_term", 36), step=1, key="in_contract_term")
    with col2:
        st.markdown("**Recurring revenue & cost**")
        monthly_base_revenue = st.number_input("Monthly recurring base fee per unit ($)", min_value=0.0, value=_sv("in_base_revenue", 3_000.0), step=100.0, key="in_base_revenue")
        usage_price = st.number_input("Usage price per unit of usage ($)", min_value=0.0, value=_sv("in_usage_price", 0.0), step=1.0, key="in_usage_price")
        expected_usage = st.number_input("Expected monthly usage volume per unit", min_value=0.0, value=_sv("in_expected_usage", 0.0), step=1.0, key="in_expected_usage")
        variable_support_cost = st.number_input("Monthly variable support cost per unit ($)", min_value=0.0, value=_sv("in_variable_cost", 500.0), step=50.0, key="in_variable_cost")

    col3, col4 = st.columns(2)
    with col3:
        opening_cash = st.number_input("Opening cash balance ($)", value=_sv("in_opening_cash", 5_000_000.0), step=100_000.0, key="in_opening_cash")
        fixed_operating_cost = st.number_input("Fixed operating cost per month ($)", min_value=0.0, value=_sv("in_fixed_cost", 200_000.0), step=10_000.0, key="in_fixed_cost")
    with col4:
        desired_cash_buffer = st.number_input("Desired minimum cash buffer ($)", min_value=0.0, value=_sv("in_cash_buffer", 1_000_000.0), step=100_000.0, key="in_cash_buffer")

    st.markdown("**Utilization ramp** (spec 7.3 -- newly commissioned units do not start at full utilization)")
    ramp_df = st.data_editor(
        st.session_state.get("in_ramp_df", DEFAULT_UTILIZATION_RAMP),
        num_rows="dynamic",
        key="in_ramp_editor",
        use_container_width=True,
    )
    st.session_state["in_ramp_df"] = ramp_df

    try:
        unit_economics = UnitEconomics(
            hardware_cost_per_unit=hardware_cost,
            deployment_cost_per_unit=deployment_cost,
            upfront_customer_payment=upfront_payment,
            monthly_base_revenue=monthly_base_revenue,
            usage_price=usage_price,
            expected_monthly_usage=expected_usage,
            monthly_variable_support_cost=variable_support_cost,
            contract_term_months=int(contract_term),
            residual_value=residual_value,
        )
        errors = validate_unit_economics(unit_economics)
        for e in errors:
            st.error(e)
        st.session_state["unit_economics"] = unit_economics if not errors else None
    except Exception as exc:
        st.error(f"Unit economics input error: {exc}")
        st.session_state["unit_economics"] = None

    try:
        ramp_points = [UtilizationRampPoint(month_since_commissioning=int(r["month_since_commissioning"]), utilization=float(r["utilization"])) for _, r in ramp_df.iterrows()]
        company_assumptions = CompanyAssumptions(
            commercial_model="raas",
            opening_cash=opening_cash,
            fixed_operating_cost_monthly=fixed_operating_cost,
            manufacturing_capacity_monthly=0.0,  # set on the Deployment Capacity panel
            deployment_teams=0,
            units_per_team_monthly=0.0,
            service_units_per_fte=1.0,
            utilization_ramp=ramp_points,
        )
        errors = validate_company_assumptions(company_assumptions)
        # manufacturing/implementation are filled in by the capacity panel; skip
        # the "deployment_teams is 0" warning here since it hasn't run yet.
        errors = [e for e in errors if "deployment_teams is 0" not in e]
        for e in errors:
            st.error(e)
        st.session_state["company_assumptions_partial"] = company_assumptions
        st.session_state["desired_cash_buffer"] = desired_cash_buffer
    except Exception as exc:
        st.error(f"Company assumptions input error: {exc}")
        st.session_state["company_assumptions_partial"] = None


def render_commercial_funnel_panel() -> None:
    """Spec 19.1 'Commercial Funnel' page."""
    st.subheader("Commercial Funnel")
    st.caption("Account-level stages, stage-entry conversion probability, and Triangular(min, mode, max) dwell time (spec section 4.1/4.3).")
    df = st.data_editor(
        st.session_state.get("in_commercial_stages_df", DEFAULT_COMMERCIAL_STAGES),
        num_rows="dynamic",
        key="in_commercial_stages_editor",
        use_container_width=True,
    )
    st.session_state["in_commercial_stages_df"] = df

    try:
        stages = _stage_df_to_list(df)
        errors = validate_funnel_stages(stages)
        for e in errors:
            st.error(e)
        st.session_state["commercial_stages"] = stages if not errors else None
    except Exception as exc:
        st.error(f"Commercial funnel input error: {exc}")
        st.session_state["commercial_stages"] = None

    st.markdown("**New opportunities entering the funnel**")
    col1, col2 = st.columns(2)
    with col1:
        opportunities_per_month = st.number_input("New qualified opportunities per month", min_value=0.0, value=_sv("in_opportunities_rate", 2.0), step=0.5, key="in_opportunities_rate")
    with col2:
        num_months = st.number_input("Months to simulate", min_value=1, value=_sv("in_num_months", 36), step=1, key="in_num_months")
    st.session_state["opportunities_per_month"] = {t: opportunities_per_month for t in range(int(num_months))}
    st.session_state["num_months"] = int(num_months)


def render_deployment_funnel_panel() -> None:
    """Unit-level pre-capacity deployment stages (spec section 4.2, engine.deployment scope)."""
    st.subheader("Deployment Funnel (pre-capacity stages)")
    st.caption("Committed -> scheduled -> in production/procurement -> delivered to site. Installed/commissioned/operational are capacity-gated on the Deployment Capacity panel, not set here (spec section 18 module split).")
    df = st.data_editor(
        st.session_state.get("in_deployment_stages_df", DEFAULT_DEPLOYMENT_STAGES),
        num_rows="dynamic",
        key="in_deployment_stages_editor",
        use_container_width=True,
    )
    st.session_state["in_deployment_stages_df"] = df

    site_readiness_delay = st.number_input("Additional customer-site readiness delay (months)", min_value=0.0, value=_sv("in_site_readiness_delay", 0.0), step=1.0, key="in_site_readiness_delay")
    st.session_state["site_readiness_delay_months"] = site_readiness_delay

    try:
        stages = _stage_df_to_list(df)
        errors = validate_funnel_stages(stages)
        for e in errors:
            st.error(e)
        st.session_state["deployment_stages"] = stages if not errors else None
    except Exception as exc:
        st.error(f"Deployment funnel input error: {exc}")
        st.session_state["deployment_stages"] = None


def render_capacity_panel() -> None:
    """Spec 19.1 'Deployment Capacity' page."""
    st.subheader("Deployment Capacity")
    st.caption("Manufacturing, implementation-team, and commissioning throughput (spec section 5). Implementation capacity = deployment teams x units per team per month.")

    col1, col2, col3 = st.columns(3)
    with col1:
        deployment_teams = st.number_input("Deployment teams", min_value=0, value=_sv("in_deployment_teams", 1), step=1, key="in_deployment_teams")
    with col2:
        units_per_team = st.number_input("Units per team per month", min_value=0.0, value=_sv("in_units_per_team", 10.0), step=1.0, key="in_units_per_team")
    with col3:
        service_units_per_fte = st.number_input("Units supported per field-service FTE", min_value=0.1, value=_sv("in_service_units_per_fte", 20.0), step=1.0, key="in_service_units_per_fte")

    base_df = st.data_editor(
        st.session_state.get("in_capacity_base_df", DEFAULT_CAPACITY),
        num_rows="dynamic",
        key="in_capacity_base_editor",
        use_container_width=True,
    )
    st.session_state["in_capacity_base_df"] = base_df

    add_expansion = st.checkbox("Add a capacity-expansion scenario (lead time + productivity ramp)", value=False, key="in_add_expansion")
    additions: list[CapacityEntry] = []
    if add_expansion:
        additions_df = st.data_editor(
            st.session_state.get("in_capacity_additions_df", DEFAULT_CAPACITY_ADDITIONS),
            num_rows="dynamic",
            key="in_capacity_additions_editor",
            use_container_width=True,
        )
        st.session_state["in_capacity_additions_df"] = additions_df
        try:
            additions = [
                CapacityEntry(
                    capacity_type=row["capacity_type"],
                    available_capacity=float(row["available_capacity"]),
                    unit_of_measure=row["unit_of_measure"],
                    lead_time_months=float(row["lead_time_months"]),
                    upfront_cost=float(row["upfront_cost"]),
                    monthly_cost=float(row["monthly_cost"]),
                    ramp_months=float(row["ramp_months"]),
                )
                for _, row in additions_df.iterrows()
            ]
        except Exception as exc:
            st.error(f"Capacity expansion input error: {exc}")
            additions = []

    manufacturing_rows = base_df[base_df["capacity_type"] == "manufacturing"]
    commissioning_rows = base_df[base_df["capacity_type"] == "commissioning"]
    manufacturing_capacity_monthly = float(manufacturing_rows["available_capacity"].sum()) if not manufacturing_rows.empty else 0.0
    commissioning_capacity_monthly = float(commissioning_rows["available_capacity"].sum()) if not commissioning_rows.empty else 0.0

    partial = st.session_state.get("company_assumptions_partial")
    if partial is not None:
        updated = partial.model_copy(
            update={
                "manufacturing_capacity_monthly": manufacturing_capacity_monthly,
                "deployment_teams": int(deployment_teams),
                "units_per_team_monthly": units_per_team,
                "service_units_per_fte": service_units_per_fte,
            }
        )
        errors = validate_company_assumptions(updated)
        for e in errors:
            st.error(e)
        st.session_state["company_assumptions"] = updated if not errors else None
    else:
        st.warning("Fill in the Business Model panel first.")
        st.session_state["company_assumptions"] = None

    st.session_state["commissioning_capacity_monthly"] = commissioning_capacity_monthly

    try:
        base_entries = [
            CapacityEntry(
                capacity_type=row["capacity_type"],
                available_capacity=float(row["available_capacity"]),
                unit_of_measure=row["unit_of_measure"],
                lead_time_months=float(row["lead_time_months"]),
                upfront_cost=float(row["upfront_cost"]),
                monthly_cost=float(row["monthly_cost"]),
                ramp_months=float(row["ramp_months"]),
            )
            for _, row in base_df.iterrows()
        ]
        errors = validate_capacity_entries(base_entries)
        for e in errors:
            st.warning(e)
    except Exception as exc:
        st.error(f"Base capacity input error: {exc}")

    st.session_state["capacity_additions"] = additions


def render_customer_portfolio_panel() -> None:
    """Spec 19.1 'Customer Portfolio' page: current customers, backlog,
    projected growth. Concentration basis is backlog-locked (spec section
    21.1/25 scope constraint)."""
    st.subheader("Customer Portfolio")
    render_locked_selector("Concentration basis", "Backlog", ["Revenue", "Installed-base", "Projected revenue"])

    # data_editor doesn't reliably pick up a programmatic st.session_state[key]
    # override the way simple widgets do (its key stores edit-tracking state,
    # not the raw DataFrame). To let a preset replace its contents, we mount
    # a fresh widget under a new key -- demo_presets.py bumps
    # "customers_editor_version" and stashes the replacement in
    # "in_customers_preset_df" when a preset is loaded.
    customers_editor_key = f"in_customers_editor_v{st.session_state.get('customers_editor_version', 0)}"
    df = st.data_editor(
        st.session_state.get("in_customers_preset_df", DEFAULT_CUSTOMERS),
        num_rows="dynamic",
        key=customers_editor_key,
        use_container_width=True,
    )

    try:
        entries = [CustomerConcentrationEntry(customer_id=row["customer_id"], customer_name=row["customer_name"], contracted_backlog=float(row["contracted_backlog"])) for _, row in df.iterrows()]
        errors = validate_customer_concentration_entries(entries)
        for e in errors:
            st.error(e)
        st.session_state["existing_customers"] = entries if not errors else None
    except Exception as exc:
        st.error(f"Customer portfolio input error: {exc}")
        st.session_state["existing_customers"] = None

    st.markdown("**New-account growth strategy** (both options are built -- this is a real, functional choice, unlike the locked selectors above)")
    col1, col2 = st.columns(2)
    with col1:
        strategy = st.radio("How do new contracted accounts enter the portfolio?", ["diversified", "anchor"], key="in_new_account_strategy")
    with col2:
        new_account_value = st.number_input("Target new-account backlog size ($, diversified only)", min_value=0.0, value=_sv("in_new_account_value", 1_000_000.0), step=100_000.0, key="in_new_account_value")
    default_backlog_value_per_unit = _sv("in_backlog_value_per_unit", st.session_state.get("in_base_revenue", 3_000.0) * st.session_state.get("in_contract_term", 36))
    backlog_value_per_unit = st.number_input(
        "Contracted backlog value per unit ($, e.g. monthly base revenue x contract term)",
        min_value=0.0,
        value=default_backlog_value_per_unit,
        step=10_000.0,
        key="in_backlog_value_per_unit",
    )
    st.session_state["new_account_strategy"] = strategy
    st.session_state["new_account_backlog_value"] = new_account_value
    st.session_state["backlog_value_per_unit"] = backlog_value_per_unit
