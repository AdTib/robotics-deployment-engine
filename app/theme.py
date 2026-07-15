"""
Visual design system for the app. See the design brief this was built from
for the reasoning; in short: an instrument-panel aesthetic (this tool tracks
physical fleets, not SaaS accounts), a three-hue accent system tied directly
to the three breakeven concepts so that distinction is visible everywhere it
matters, and a type pairing (Big Shoulders Display / IBM Plex Sans / IBM
Plex Mono) chosen for an industrial/engineering-documentation register
rather than a generic startup-dashboard one.

Pure presentation. `inject_theme()` writes CSS; `render_instrument_card` and
`badge_html`-equivalent styling below format numbers that are computed
entirely elsewhere.
"""

from __future__ import annotations

import streamlit as st

# Three-hue accent system: each hue is permanently associated with one of the
# three breakeven concepts (spec section 22 rules 5-6) and reused everywhere
# that concept resurfaces -- charts, badges, comparison tables -- so the
# association becomes a learned visual language, not a one-off color choice.
ACCENT_STEEL = "#4a90a4"   # Operating Breakeven Fleet Size -- steady-state, structural
ACCENT_AMBER = "#c98a3f"   # Unit Deployment Payback -- one unit's own clock
ACCENT_RUST = "#b1543f"    # Company Cash Breakeven -- the one that can actually hurt you
POSITIVE = "#5a9e6f"
NEGATIVE = "#c05a52"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {{
    --bg: #12161a;
    --surface: #1b2126;
    --surface-raised: #232a30;
    --border: #2c353c;
    --text: #e6eaec;
    --text-muted: #8b969e;
    --accent-steel: {ACCENT_STEEL};
    --accent-amber: {ACCENT_AMBER};
    --accent-rust: {ACCENT_RUST};
    --positive: {POSITIVE};
    --negative: {NEGATIVE};
    --font-display: 'Big Shoulders Display', 'Arial Narrow', system-ui, sans-serif;
    --font-body: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
    --font-mono: 'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, monospace;
    --radius: 6px;
}}

/* ---- base surfaces ---- */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--font-body) !important;
}}

[data-testid="stHeader"] {{
    background-color: var(--bg) !important;
    border-bottom: 1px solid var(--border);
}}

[data-testid="stMainBlockContainer"] {{
    padding-top: 2.25rem;
    max-width: 1200px;
}}

/* ---- typography ---- */
[data-testid="stHeading"] h1 {{
    font-family: var(--font-display) !important;
    font-weight: 800 !important;
    letter-spacing: 0.01em;
    text-transform: uppercase;
    font-size: 2.4rem !important;
    line-height: 1.05 !important;
    color: var(--text) !important;
    border-left: 4px solid var(--accent-steel);
    padding-left: 0.75rem;
}}

[data-testid="stHeading"] h2 {{
    font-family: var(--font-display) !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    font-size: 1.4rem !important;
    color: var(--text) !important;
    margin-top: 1.5rem;
}}

[data-testid="stHeading"] h3, [data-testid="stHeading"] h4 {{
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    color: var(--text-muted) !important;
    font-size: 1.05rem !important;
    text-transform: uppercase;
}}

p, li, [data-testid="stMarkdownContainer"] {{
    font-family: var(--font-body);
    color: var(--text);
}}

[data-testid="stCaptionContainer"] {{
    font-family: var(--font-mono) !important;
    color: var(--text-muted) !important;
    font-size: 0.78rem !important;
}}

code {{
    font-family: var(--font-mono) !important;
    background: var(--surface-raised) !important;
    color: var(--accent-amber) !important;
    border-radius: 4px;
}}

/* ---- sidebar / page nav ---- */
[data-testid="stSidebar"] {{
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border);
}}

[data-testid="stSidebar"] label {{
    font-family: var(--font-mono) !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: var(--text-muted) !important;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] > div {{
    gap: 0.15rem;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label {{
    width: 100%;
    padding: 0.5rem 0.6rem;
    border-radius: 4px;
    border-left: 3px solid transparent;
    text-transform: none;
    font-size: 0.92rem !important;
    color: var(--text) !important;
    transition: background-color 120ms ease, border-color 120ms ease;
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
    background-color: var(--surface-raised);
}}

[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{
    border-left-color: var(--accent-steel);
    background-color: var(--surface-raised);
}}

/* ---- tabs ---- */
[data-testid="stTabs"] button[role="tab"] {{
    font-family: var(--font-mono) !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 0.82rem !important;
    color: var(--text-muted) !important;
}}

[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
    color: var(--accent-steel) !important;
    border-bottom-color: var(--accent-steel) !important;
}}

/* ---- buttons ---- */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {{
    font-family: var(--font-mono) !important;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    font-size: 0.8rem !important;
    border-radius: var(--radius) !important;
    transition: background-color 120ms ease, border-color 120ms ease, transform 120ms ease;
}}

[data-testid="stBaseButton-secondary"] {{
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-muted) !important;
}}

[data-testid="stBaseButton-secondary"]:disabled {{
    opacity: 0.55;
    border-style: dashed !important;
}}

[data-testid="stBaseButton-primary"] {{
    background-color: var(--accent-steel) !important;
    border: 1px solid var(--accent-steel) !important;
    color: #0d1114 !important;
    font-weight: 600;
}}

[data-testid="stBaseButton-primary"]:hover {{
    transform: translateY(-1px);
}}

/* ---- inputs ---- */
[data-testid="stNumberInputField"], [data-testid="stSelectbox"] > div,
[data-testid="stTextInput"] input {{
    font-family: var(--font-mono) !important;
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: var(--radius) !important;
}}

[data-testid="stWidgetLabel"] p {{
    font-family: var(--font-body) !important;
    font-size: 0.85rem !important;
    color: var(--text-muted) !important;
}}

/* ---- metrics ---- */
[data-testid="stMetric"] {{
    background-color: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent-steel);
    border-radius: var(--radius);
    padding: 0.75rem 1rem;
}}

[data-testid="stMetricLabel"] {{
    font-family: var(--font-body) !important;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    font-size: 0.75rem !important;
    color: var(--text-muted) !important;
}}

[data-testid="stMetricValue"] {{
    font-family: var(--font-mono) !important;
    color: var(--text) !important;
}}

/* ---- alerts ---- */
[data-testid="stAlert"] {{
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background-color: var(--surface);
    font-family: var(--font-body);
}}

/* ---- expanders ---- */
[data-testid="stExpander"] {{
    background-color: var(--surface);
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
}}

/* ---- dataframe / data_editor container ---- */
[data-testid="stDataFrame"], [data-testid="stDataFrameResizable"] {{
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}}

/* ---- keyboard focus (quality floor: visible on every interactive element) ---- */
button:focus-visible, input:focus-visible, [role="tab"]:focus-visible,
[role="radio"]:focus-visible, a:focus-visible {{
    outline: 2px solid var(--accent-steel) !important;
    outline-offset: 2px !important;
}}

/* ---- instrument card (the three-breakeven signature element) ---- */
.instrument-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-top: 3px solid var(--accent);
    border-radius: var(--radius);
    padding: 1rem 1.1rem 0.9rem 1.1rem;
    height: 100%;
}}

.instrument-card .instrument-label {{
    font-family: var(--font-body);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    margin-bottom: 0.35rem;
}}

.instrument-card .instrument-value {{
    font-family: var(--font-mono);
    font-size: 1.9rem;
    font-weight: 600;
    color: var(--text);
    line-height: 1.1;
}}

.instrument-card .instrument-sub {{
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.3rem;
}}

.instrument-card .instrument-ticks {{
    height: 6px;
    margin: 0.6rem 0 0.2rem 0;
    border-radius: 3px;
    background-image: repeating-linear-gradient(
        90deg,
        var(--accent) 0px, var(--accent) 2px,
        transparent 2px, transparent 8px
    );
    opacity: 0.55;
}}

/* ---- spec-plate provenance badges ---- */
.spec-badge {{
    display: inline-block;
    font-family: var(--font-mono);
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    clip-path: polygon(0 0, calc(100% - 6px) 0, 100% 100%, 0 100%);
}}

.spec-badge.disclosed {{
    background-color: var(--accent-steel);
    color: #0d1114;
}}

.spec-badge.derived {{
    background: transparent;
    border: 1px solid var(--accent-steel);
    color: var(--accent-steel);
}}

.spec-badge.assumed {{
    background: transparent;
    border: 1px dashed var(--accent-amber);
    color: var(--accent-amber);
}}

.spec-badge.scenario {{
    background: transparent;
    border: 1px dotted var(--accent-rust);
    color: var(--accent-rust);
}}
</style>
"""


def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_instrument_card(label: str, value: str, accent: str, sublabel: str = "") -> None:
    """The three-breakeven signature element. `accent` is one of
    ACCENT_STEEL / ACCENT_AMBER / ACCENT_RUST."""
    st.markdown(
        f"""
        <div class="instrument-card" style="--accent: {accent};">
            <div class="instrument-label">{label}</div>
            <div class="instrument-value">{value}</div>
            <div class="instrument-ticks"></div>
            <div class="instrument-sub">{sublabel}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
