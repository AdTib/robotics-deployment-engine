"""
Output views (spec section 19.2). Every number here comes from calling
engine functions directly -- this module only formats results for display.
"""

from __future__ import annotations

import streamlit as st

from app.charts import monthly_line_chart, stage_bar_chart
from app.theme import ACCENT_AMBER, ACCENT_RUST, ACCENT_STEEL, render_instrument_card
from engine.capacity import check_service_coverage
from engine.concentration import compute_concentration, solve_diversification_target
from engine.economics import operating_breakeven_fleet_size, unit_payback_months_constant, unit_payback_months_with_ramp
from engine.funnel import expected_time_to_stage, expected_units_for_cohort, survival_to_stage, time_to_stage_range
from engine.simulation import ScenarioAssumptions, ScenarioSummary


def render_funnel_view(assumptions: ScenarioAssumptions, summary: ScenarioSummary) -> None:
    """Spec 19.2 Funnel View: opportunities by stage, expected cohort
    progression, time-to-pilot, time-to-production deployment, conversion
    losses. Calls engine.funnel directly (per-stage figures aren't part of
    ScenarioSummary's monthly series, which only tracks aggregate contracted
    units by month)."""
    st.subheader("Funnel View")

    stages = sorted(assumptions.commercial_stages, key=lambda s: s.stage_order)
    stage_names = [s.stage_name for s in stages]

    st.markdown("**Cumulative survival probability by stage** (`engine.funnel.survival_to_stage`)")
    survival = [survival_to_stage(stages, s.stage_order) * 100 for s in stages]
    st.plotly_chart(stage_bar_chart(stage_names, survival, "Share of entering opportunities reaching each stage", "% surviving"), use_container_width=True)

    st.markdown("**Conversion loss per stage** -- the drop from the prior stage's survival")
    conversion_loss = [0.0] + [survival[i - 1] - survival[i] for i in range(1, len(survival))]
    st.dataframe(
        {
            "Stage": stage_names,
            "Conversion probability (this stage)": [f"{s.conversion_probability:.0%}" for s in stages],
            "Cumulative survival": [f"{v:.1f}%" for v in survival],
            "Conversion loss vs. prior stage": [f"{v:.1f} pts" for v in conversion_loss],
        },
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Expected time to reach each stage** (`engine.funnel.expected_time_to_stage` / `time_to_stage_range`)")
    expected_months = [expected_time_to_stage(stages, s.stage_order) for s in stages]
    ranges = [time_to_stage_range(stages, s.stage_order) for s in stages]
    st.dataframe(
        {
            "Stage": stage_names,
            "Expected months to reach": [f"{v:.1f}" for v in expected_months],
            "10th-90th percentile range (months)": [f"{lo:.1f} - {hi:.1f}" for lo, hi in ranges],
        },
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Range is a normal approximation to the sum of independent Triangular dwell-time distributions "
        "(exact closed-form mean/variance, not Monte Carlo sampling -- see engine/funnel.py docstring)."
    )

    expected_units = expected_units_for_cohort(stages, entrants=1.0)
    st.metric("Expected operational-track units per opportunity entering the funnel", f"{expected_units:.2f}", help="engine.funnel.expected_units_for_cohort")

    st.divider()
    st.markdown("**Monthly contracted vs. commercially-ready units** (aggregated across all monthly cohorts)")
    months = [r.month for r in summary.monthly_results]
    st.plotly_chart(
        monthly_line_chart(
            months,
            {
                "Contracted units (commercial funnel output)": [r.contracted_units for r in summary.monthly_results],
                "Commercially ready units (post-deployment-funnel dwell)": [r.ready_units for r in summary.monthly_results],
            },
            "Contracted vs. Ready Units by Month",
            "Units",
        ),
        use_container_width=True,
    )


def render_capacity_view(assumptions: ScenarioAssumptions, summary: ScenarioSummary) -> None:
    """Spec 19.2 Capacity View: demand vs. capacity, manufacturing/deployment-
    team/commissioning utilization, service coverage, deferred deployments
    and revenue. All figures come from ScenarioSummary.monthly_results,
    which is produced by engine.capacity.run_capacity_model inside
    engine.simulation.run_scenario -- this view only charts them."""
    st.subheader("Capacity View")

    months = [r.month for r in summary.monthly_results]

    st.markdown("**Capacity utilization by month** (`engine.capacity.run_capacity_model`)")
    st.plotly_chart(
        monthly_line_chart(
            months,
            {
                "Manufacturing utilization": [r.manufacturing_utilization * 100 for r in summary.monthly_results],
                "Implementation (deployment-team) utilization": [r.implementation_utilization * 100 for r in summary.monthly_results],
                "Commissioning utilization": [r.commissioning_utilization * 100 for r in summary.monthly_results],
            },
            "Capacity Utilization by Month",
            "% utilized",
        ),
        use_container_width=True,
    )

    st.markdown("**Deployment backlog and deferred revenue**")
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(
            monthly_line_chart(months, {"Deployment backlog (undeployed ready units)": [r.deployment_backlog for r in summary.monthly_results]}, "Deployment Backlog by Month", "Units"),
            use_container_width=True,
        )
    with col2:
        st.plotly_chart(
            monthly_line_chart(months, {"Deferred revenue": [r.deferred_revenue for r in summary.monthly_results]}, "Revenue Deferred by the Capacity Bottleneck", "$ / month"),
            use_container_width=True,
        )
    st.caption("Deferred revenue = backlog x expected revenue per unit (spec section 5.6) -- units still waiting on manufacturing/implementation/commissioning capacity are not yet generating revenue (spec rule 4).")

    st.divider()
    st.markdown("**Field-service coverage check** (`engine.capacity.check_service_coverage`)")
    final_active_units = summary.monthly_results[-1].active_units
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Active units, final month", f"{final_active_units:.1f}")
        available_fte = st.number_input("Available field-service FTEs", min_value=0.0, value=max(1.0, final_active_units / max(assumptions.company_assumptions.service_units_per_fte, 1e-9)), step=1.0, key="in_available_service_fte")
    with col2:
        coverage = check_service_coverage(final_active_units, available_fte, assumptions.company_assumptions.service_units_per_fte)
        st.metric("Required field-service FTEs", f"{coverage.required_fte:.2f}")
        if coverage.is_understaffed:
            st.error(f"Understaffed by {coverage.shortfall_fte:.2f} FTE at the final month's active fleet size.")
        else:
            st.success("Field-service coverage is adequate at the final month's active fleet size.")


def render_economics_view(assumptions: ScenarioAssumptions, summary: ScenarioSummary) -> None:
    """Spec 19.2 Fleet Economics View. The three breakeven concepts (spec
    section 22 rules 5-6) are rendered as three visually separate sections,
    never combined into a single number."""
    st.subheader("Fleet Economics View")
    st.caption("Three distinct breakeven concepts -- see engine/economics.py module docstring for why they must never be conflated.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.caption("`engine.economics.operating_breakeven_fleet_size` -- steady-state fleet size where ANNUAL contribution margin covers annual fixed costs. Says nothing about cash timing.")
        try:
            result = operating_breakeven_fleet_size(assumptions.company_assumptions.fixed_operating_cost_monthly, assumptions.unit_economics)
            render_instrument_card(
                "1. Operating Breakeven Fleet Size",
                f"{result.operating_breakeven_fleet_size:.1f} units",
                ACCENT_STEEL,
                f"Annual fixed ${result.annual_fixed_operating_costs:,.0f} / margin per unit ${result.annual_contribution_margin_per_unit:,.0f}",
            )
        except ValueError as exc:
            st.warning(f"Not computable: {exc}")

    with col2:
        st.caption("`engine.economics.unit_payback_months_constant` / `unit_payback_months_with_ramp` -- how long ONE unit takes to repay its own upfront investment.")
        try:
            constant = unit_payback_months_constant(assumptions.unit_economics)
            ramp_payback = unit_payback_months_with_ramp(assumptions.unit_economics, assumptions.company_assumptions.utilization_ramp)
            ramp_text = f"{ramp_payback:.0f} months" if ramp_payback is not None else "not reached"
            render_instrument_card(
                "2. Unit Deployment Payback",
                f"{constant:.1f} months",
                ACCENT_AMBER,
                f"constant margin -- with the actual utilization ramp: {ramp_text}",
            )
        except ValueError as exc:
            st.warning(f"Not computable: {exc}")

    with col3:
        st.caption("`engine.economics.company_cash_breakeven_month` -- first month the WHOLE COMPANY's cumulative cash flow (excluding opening cash) is non-negative.")
        breakeven_text = f"Month {summary.company_cash_breakeven_month}" if summary.company_cash_breakeven_month is not None else "Not reached"
        render_instrument_card(
            "3. Company Cash Breakeven",
            breakeven_text,
            ACCENT_RUST,
            f"min cash ${summary.minimum_cash_balance:,.0f} / capital required ${summary.external_capital_required:,.0f}",
        )

    st.divider()
    st.markdown("**Monthly revenue, cost, and cash flow** (`engine.economics.project_monthly_cash_flow`, run inside `engine.simulation.run_scenario`)")
    months = [r.month for r in summary.monthly_results]
    st.plotly_chart(
        monthly_line_chart(
            months,
            {
                "Revenue": [r.revenue for r in summary.monthly_results],
                "Variable cost": [r.variable_cost for r in summary.monthly_results],
                "Fixed cost": [r.fixed_cost for r in summary.monthly_results],
                "Net cash flow": [r.net_cash_flow for r in summary.monthly_results],
            },
            "Monthly Revenue, Cost, and Net Cash Flow",
            "$",
        ),
        use_container_width=True,
    )
    st.plotly_chart(
        monthly_line_chart(
            months,
            {
                "Cumulative cash flow (excl. opening cash)": [r.cumulative_cash_flow for r in summary.monthly_results],
                "Cash balance (incl. opening cash)": [r.cash_balance for r in summary.monthly_results],
            },
            "Cumulative Cash Flow vs. Cash Balance",
            "$",
        ),
        use_container_width=True,
    )
    st.caption("Cumulative cash flow crossing zero is the Company Cash Breakeven Month above; cash balance's lowest point is the Minimum Cash Balance above -- two different lines, deliberately.")


def render_concentration_view(assumptions: ScenarioAssumptions, summary: ScenarioSummary) -> None:
    """Spec 19.2 Concentration View. Backlog basis only (spec section
    21.1/25) -- engine.concentration.compute_concentration would raise if
    asked for any other basis, so there is no code path here that could
    silently mix bases."""
    st.subheader("Concentration View")
    st.caption("Basis: **backlog** (`engine.concentration.compute_concentration`, basis='backlog'). Revenue/installed-base/projected-revenue bases are Expansion Release -- see Customer Portfolio input panel.")

    baseline = compute_concentration(assumptions.existing_customers, basis="backlog")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Largest-customer share (existing customers only)", f"{baseline.largest_customer_share:.1%}")
    col2.metric("Top-three share", f"{baseline.top_three_share:.1%}")
    col3.metric("HHI (standard, 0-10,000)", f"{baseline.hhi_standard:,.0f}")
    col4.metric("Normalized score (0-100)", f"{baseline.normalized_concentration_score:.1f}")
    st.caption(f"Effective customer count: {baseline.effective_customer_count:.2f} (of {baseline.num_customers} existing customers)")

    st.divider()
    st.markdown("**Concentration over time** (existing customers + new contracted accounts, spec section 8.7)")
    months, hhi_vals, largest_vals, eff_vals = [], [], [], []
    for r in summary.monthly_results:
        if r.hhi_standard is None:
            continue
        months.append(r.month)
        hhi_vals.append(r.hhi_standard)
        largest_vals.append(r.largest_customer_share * 100)
        eff_vals.append(r.effective_customer_count)

    if months:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(monthly_line_chart(months, {"HHI (standard)": hhi_vals}, "Backlog HHI by Month", "HHI"), use_container_width=True)
        with col2:
            st.plotly_chart(
                monthly_line_chart(months, {"Largest-customer share (%)": largest_vals, "Effective customer count": eff_vals}, "Largest Share & Effective Customer Count by Month", "Value"),
                use_container_width=True,
            )
    else:
        st.info("No new contracted backlog has entered yet at the current input settings -- concentration stays at the existing-customer baseline above.")

    st.divider()
    st.markdown("**Diversification-target solver** (`engine.concentration.solve_diversification_target`)")
    col1, col2 = st.columns(2)
    with col1:
        target_hhi = st.number_input("Target HHI (standard, 0-10,000)", min_value=0.0, max_value=10_000.0, value=2_500.0, step=100.0, key="in_target_hhi")
    with col2:
        new_account_value = st.number_input("Assumed new-account backlog size ($, equal-sized)", min_value=1.0, value=1_000_000.0, step=100_000.0, key="in_diversification_new_account_value")

    current_values = [e.contracted_backlog for e in assumptions.existing_customers]
    result = solve_diversification_target(current_values, target_hhi, new_account_value)
    if result.achieved:
        st.success(f"{result.new_accounts_required} new equal-sized account(s) of ${new_account_value:,.0f} would bring HHI to {result.projected_hhi_standard:,.0f} (<= target {target_hhi:,.0f}).")
    else:
        st.warning(f"Target not reached within the search cap; HHI after the cap is {result.projected_hhi_standard:,.0f}.")
