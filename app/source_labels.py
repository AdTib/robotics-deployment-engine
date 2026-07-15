"""
Source-classification badges (spec section 19.3 / section 11).

Every demo input surfaced in the UI must visibly show whether it is
disclosed, derived, assumed, or scenario -- not just documented in the
README. This module renders small colored badges plus an optional detail
expander (source title/URL/confidence/notes) wherever a labeled value
appears. Pure presentation -- no calculation logic lives here.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

def badge_html(classification: str) -> str:
    """Spec-plate stamp styling (see app/theme.py): solid fill for disclosed,
    outline for derived, dashed border for assumed, dotted border for
    scenario. Classes are defined once in the injected theme stylesheet."""
    css_class = classification if classification in {"disclosed", "derived", "assumed", "scenario"} else ""
    return f'<span class="spec-badge {css_class}">{classification}</span>'


def render_badge(classification: str) -> None:
    st.markdown(badge_html(classification), unsafe_allow_html=True)


def render_labeled_value(
    label: str,
    value: str,
    classification: str,
    notes: str = "",
    source_title: str = "",
    source_url: str | None = None,
    confidence: str | None = None,
) -> None:
    """Render `label: value [BADGE]` with an optional expander for source detail."""
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f"**{label}:** {value}")
    with col2:
        render_badge(classification)

    if notes or source_title:
        with st.expander("Source detail", expanded=False):
            if source_title:
                if source_url:
                    st.markdown(f"**Source:** [{source_title}]({source_url})")
                else:
                    st.markdown(f"**Source:** {source_title} (no URL on file)")
            if confidence:
                st.markdown(f"**Confidence:** {confidence}")
            if notes:
                st.markdown(f"**Notes:** {notes}")


def render_source_registry_row(row: pd.Series) -> None:
    """Render one row of source_registry.csv as a labeled-value block."""
    render_labeled_value(
        label=f"{row['company']} -- {row['metric_name']}",
        value=f"{row['value']} {row['unit']}",
        classification=row["classification"],
        notes=row.get("notes", ""),
        source_title=row.get("source_title", ""),
        source_url=row.get("source_url") or None,
        confidence=row.get("confidence"),
    )


def render_source_registry_table(df: pd.DataFrame, title: str = "Full source registry (audit trail)") -> None:
    """Collapsed-by-default full audit table -- every metric_id, classification,
    confidence, and citation in one place (spec section 11.2)."""
    with st.expander(title, expanded=False):
        display_cols = ["metric_id", "company", "metric_name", "value", "unit", "classification", "confidence", "source_title", "source_url", "notes"]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)


def render_locked_selector(title: str, available_label: str, locked_labels: list[str]) -> None:
    """Render a row of buttons where only `available_label` is clickable; the
    rest are disabled and tagged 'Expansion Release'. Used for the
    commercial-model and concentration-basis selectors (spec section 25 scope
    constraint: only one preset/basis is built in Core Release) -- the point
    is to show the other options exist without silently omitting them or
    letting them be selected.
    """
    st.markdown(f"**{title}**")
    cols = st.columns(1 + len(locked_labels))
    with cols[0]:
        st.button(f"{available_label}  ✓", disabled=False, key=f"locked_selector_available_{title}_{available_label}", type="primary")
    for i, label in enumerate(locked_labels):
        with cols[i + 1]:
            st.button(label, disabled=True, key=f"locked_selector_locked_{title}_{label}")
            st.caption("Expansion Release")


def classification_legend() -> None:
    st.markdown(
        " &nbsp; ".join(
            f"{badge_html(c)} = {desc}"
            for c, desc in [
                ("disclosed", "directly stated by a credible source"),
                ("derived", "calculated from disclosed information"),
                ("assumed", "modeling input where the true value is unknown"),
                ("scenario", "intentionally varied to compare outcomes"),
            ]
        ),
        unsafe_allow_html=True,
    )
