"""
config/theme.py
===============
Central visual configuration for the dashboard. Everything here is about
*look and feel* so that the rest of the codebase never hard-codes a colour or a
font. The palette is the original OFR-style institutional dark theme — clean,
low-saturation, suitable for a macro / rates research desk (requirement #13).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Core palette — OFR dark theme
# ---------------------------------------------------------------------------
BG = "#0a0a0a"           # page / chart background
PANEL_BG = "#0f0f0f"     # slightly lighter panel background
LINE_WHITE = "#ffffff"   # primary series colour
GRID = "rgba(255,255,255,0.05)"
TEXT_DIM = "#888"
TEXT_VERY_DIM = "#666"

# Accent line colours for multi-series charts (muted, not retail-bright)
ACCENT_GREEN = "#5fb04f"
ACCENT_RED = "#d04848"
ACCENT_AMBER = "#d99830"
ACCENT_CYAN = "#4fa8b8"
ACCENT_PURPLE = "#9080d0"

# Brighter signal colours reserved for "good / bad" deltas
POS_GREEN = "#67c757"
NEG_RED = "#e64545"

# ---------------------------------------------------------------------------
# Section colour system (research-pack shell)
# ---------------------------------------------------------------------------
# One accent colour per top-level section — used for the left-border stripe on
# the page header, the highlighted top-tab, the section footer, and any KPI
# card that wants to inherit the section identity. Every page renderer should
# resolve its accent from here, never hard-code a hex.
SECTION_COLORS = {
    "liquidity":     "#5fb04f",   # green — the anchor / summary section
    "policy":        "#ff8a00",   # orange — policy & short-rate plumbing
    "decomposition": "#35bdf4",   # cyan  — real / inflation / nominal breakdown
    "regimes":       "#f0c000",   # gold  — curve regime classification
    "global_rates":  "#00d07a",   # emerald — cross-country rates
    "cross_asset":   "#b184ff",   # violet — cross-asset regime blocks
    "equities":      "#ff745c",   # coral  — equities, breadth and earnings
    "fx":            "#ff2f7d",   # magenta — FX section
    "data_quality":  "#9aa0a6",   # grey  — utility / infrastructure
    "scoring":       "#e8b931",   # gold  — global scoring / CTA model
}


def section_color(key: str) -> str:
    """Look up a section colour by registry key. Falls back to a neutral grey
    so an unknown key never breaks the page shell."""
    return SECTION_COLORS.get(key, "#9aa0a6")

# OFR-style interpretation note boxes
NOTE_RED_BG = "rgba(120,30,30,0.85)"
NOTE_RED_BORDER = "#C04040"
NOTE_RED_TEXT = "#FFB0B0"
NOTE_GREEN_BG = "rgba(30,80,40,0.85)"
NOTE_GREEN_BORDER = "#40A060"
NOTE_GREEN_TEXT = "#B0E8B8"

# ---------------------------------------------------------------------------
# Liquidity-regime colours (used by the Composite Liquidity Index section)
# Looser conditions are green, tighter conditions shade toward red.
# ---------------------------------------------------------------------------
REGIME_COLORS = {
    "Loose":   "#5fb04f",
    "Neutral": "#9aa0a6",
    "Tight":   "#d99830",
    "Stress":  "#d04848",
}

# Curve-regime colours (rates section) — matches the Bloomberg Studio look
CURVE_REGIME_COLORS = {
    "bull_steepener":  "#67c757",
    "bear_steepener":  "#e64545",
    "steepener_twist": "#f0a020",
    "bull_flattener":  "#9fc8e8",
    "bear_flattener":  "#5e95c2",
    "flattener_twist": "#f0e040",
    "none":            "#444444",
}
CURVE_REGIME_LABELS = {
    "bull_steepener":  "Bull steepener",
    "bear_steepener":  "Bear steepener",
    "steepener_twist": "Steepener twist",
    "bull_flattener":  "Bull flattener",
    "bear_flattener":  "Bear flattener",
    "flattener_twist": "Flattener twist",
}

# Bucket colours for the contribution chart (one stable colour per sub-index)
BUCKET_COLORS = {
    "central_bank": "#9bd62a",
    "money_market": "#4fa8b8",
    "xccy":         "#9080d0",
    "credit":       "#d99830",
    "market_liq":   "#d04848",
}

# ---------------------------------------------------------------------------
# Shared Plotly layout — applied to (almost) every chart for consistency
# ---------------------------------------------------------------------------
DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=BG,
    plot_bgcolor=BG,
    font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
    hovermode="x unified",
    showlegend=False,
)


def page_css() -> str:
    """Return the global CSS block injected once at app start."""
    return """
    <style>
    .stApp {
        background-color: #0a0a0a;
        color: #e0e0e0;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    section[data-testid="stSidebar"] {
        background:
            radial-gradient(circle at 20% 0%, rgba(95,176,79,0.07), transparent 30%),
            #050505;
        border-right: 1px solid #1a1a1a;
    }
    section[data-testid="stSidebar"] { color: #ccc; }
    section[data-testid="stSidebar"] > div { padding-top: 0.35rem; }
    section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-left: 0.35rem; padding-right: 0.35rem;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        letter-spacing: 0.04em;
        font-family: 'Inter', system-ui, sans-serif !important;
    }
    .stCaption, [data-testid="stCaptionContainer"] {
        color: #888 !important;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        font-size: 11px !important;
    }
    .stMarkdown p { color: #ccc; }
    hr { border-color: #1a1a1a !important; margin: 0.75rem 0 !important; }
    /* Sidebar research shell */
    .sidebar-brand {
        padding: 0.75rem 0.15rem 0.85rem;
        border-bottom: 1px solid #1d1d1d;
    }
    .sidebar-brand-kicker {
        color: #69c85a; font-size: 8px; font-weight: 700;
        letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 5px;
    }
    .sidebar-brand-title {
        color: #fff; font-size: 17px; font-weight: 750;
        letter-spacing: 0.035em; line-height: 1.1;
    }
    .sidebar-brand-sub {
        color: #777; font-size: 9px; letter-spacing: 0.14em;
        text-transform: uppercase; margin-top: 4px;
    }
    .sidebar-data-status {
        margin: 0.75rem 0 0.9rem; padding: 0.65rem 0.75rem;
        background: rgba(255,255,255,0.025); border: 1px solid #1d1d1d;
        border-radius: 7px;
    }
    .sidebar-status-row {
        display: flex; align-items: center; justify-content: space-between;
        gap: 10px; min-height: 22px; font-size: 10px;
    }
    .sidebar-status-row span {
        color: #737373; letter-spacing: 0.08em; text-transform: uppercase;
    }
    .sidebar-status-row strong {
        color: #d8d8d8; font-size: 10px; font-weight: 650;
        letter-spacing: 0.04em; text-align: right;
    }
    .sidebar-status-pending {
        margin: 4px -3px -1px; padding: 3px 3px 0;
        border-top: 1px solid #1b1b1b;
    }
    .sidebar-status-pending strong { color: #d99830; }
    .sidebar-section-label {
        color: #6f6f6f; font-size: 9px; font-weight: 700;
        letter-spacing: 0.14em; text-transform: uppercase;
        margin: 0.2rem 0.15rem 0.4rem;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] {
        border: 0 !important; background: transparent !important;
        margin-bottom: 2px;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] details {
        border: 0 !important; background: transparent !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        min-height: 34px; padding: 0.15rem 0.45rem !important;
        border-radius: 5px;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        background: rgba(255,255,255,0.035);
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary p {
        color: #9a9a9a !important; font-size: 10px !important;
        font-weight: 700 !important; letter-spacing: 0.105em !important;
        text-transform: uppercase;
    }
    [data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
        padding: 0.05rem 0 0.35rem 0.45rem !important;
    }
    [data-testid="stSidebar"] .stButton { margin: 1px 0; }
    [data-testid="stSidebar"] .stButton > button {
        min-height: 32px; padding: 0.32rem 0.65rem;
        justify-content: flex-start; text-align: left;
        color: #a7a7a7; background: transparent;
        border: 1px solid transparent; border-radius: 5px;
        font-size: 12px; font-weight: 450;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        color: #fff; background: rgba(255,255,255,0.04);
        border-color: #242424;
    }
    [data-testid="stSidebar"] .stButton > button:focus:not(:active) {
        color: #fff; border-color: #2b2b2b;
        box-shadow: none;
    }
    .sidebar-nav-active {
        display: flex; align-items: center; justify-content: space-between;
        gap: 8px; min-height: 34px; padding: 0.38rem 0.65rem;
        margin: 1px 0; border-radius: 5px;
        color: #fff; background: color-mix(in srgb, var(--nav-accent) 11%, transparent);
        border: 1px solid color-mix(in srgb, var(--nav-accent) 42%, #1f1f1f);
        box-shadow: inset 2px 0 0 var(--nav-accent);
        font-size: 12px; font-weight: 600;
    }
    .sidebar-nav-active small {
        color: var(--nav-accent); font-size: 7px; font-weight: 800;
        letter-spacing: 0.12em; text-transform: uppercase;
    }
    .sidebar-lookback-label {
        margin-top: 0.85rem; padding-top: 0.75rem;
        border-top: 1px solid #1b1b1b;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
        background: #0d0d0d; border-color: #222; border-radius: 6px;
    }
    .sidebar-liquidity-card {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; margin: 0.8rem 0 0.65rem; padding: 0.65rem 0.75rem;
        background: #0c0c0c; border: 1px solid #1e1e1e;
        border-left: 2px solid var(--regime-color); border-radius: 6px;
    }
    .sidebar-liquidity-card > div:first-child {
        display: flex; flex-direction: column;
    }
    .sidebar-liquidity-card span {
        color: #777; font-size: 8px; letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    .sidebar-liquidity-card strong {
        color: var(--regime-color); font-size: 20px; line-height: 1.1;
    }
    .sidebar-liquidity-meta {
        display: flex; flex-direction: column; align-items: flex-end;
    }
    .sidebar-liquidity-meta strong {
        color: var(--regime-color); font-size: 9px; letter-spacing: 0.08em;
        text-transform: uppercase;
    }
    .sidebar-liquidity-meta span { margin-top: 3px; }
    [data-testid="stSidebar"] [data-testid="stDownloadButton"] button {
        min-height: 36px; background: #111; border: 1px solid #262626;
        border-radius: 6px; color: #d8d8d8;
    }
    [data-testid="stPlotlyChart"] { background-color: transparent !important; }
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 1rem !important;
        max-width: 100% !important;
    }
    /* Hide Streamlit Cloud chrome */
    [data-testid="stDecoration"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    [data-testid="stDeployButton"] { display: none !important; }
    [data-testid="stActionButtonIcon"] { display: none !important; }
    [data-testid="stToolbarActions"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }
    .viewerBadge_container__1QSob { display: none !important; }
    .viewerBadge_link__1S137 { display: none !important; }
    /* Section header */
    .section-header {
        background: #0a0a0a; padding: 0.6rem 0; margin: 0.5rem 0 0.25rem 0;
        border-bottom: 1px solid #1a1a1a;
    }
    .section-title {
        font-size: 18px; font-weight: 700; letter-spacing: 0.06em;
        color: #ffffff; text-transform: uppercase;
    }
    .section-sub {
        font-size: 10px; color: #888; letter-spacing: 0.08em;
        text-transform: uppercase; margin-top: 2px;
    }
    /* KPI metric cards used on the liquidity summary panel */
    .kpi-card {
        background: #0f0f0f; border: 1px solid #1a1a1a; border-radius: 6px;
        padding: 0.9rem 1rem; height: 100%;
    }
    .kpi-label {
        font-size: 10px; color: #888; letter-spacing: 0.1em;
        text-transform: uppercase; margin-bottom: 6px;
    }
    .kpi-value { font-size: 30px; font-weight: 700; line-height: 1; }
    .kpi-sub { font-size: 11px; color: #aaa; margin-top: 6px; }

    /* ----- Research-pack shell (Phase 1) ----- */
    /* Page header with left-border accent (colour set inline per section). */
    .rp-page-header {
        border-left: 3px solid #333; padding: 0.35rem 0 0.45rem 0.9rem;
        margin: 0.25rem 0 0.9rem 0;
    }
    .rp-page-section {
        font-size: 10px; color: #888; letter-spacing: 0.16em;
        text-transform: uppercase; margin-bottom: 2px;
    }
    .rp-page-title {
        font-size: 22px; font-weight: 700; letter-spacing: 0.03em;
        color: #ffffff; line-height: 1.15;
    }
    .rp-page-sub {
        font-size: 11px; color: #888; letter-spacing: 0.06em;
        text-transform: uppercase; margin-top: 4px;
    }

    /* Top section tabs — horizontal strip of section chips. */
    .rp-tabs {
        display: flex; flex-wrap: wrap; gap: 4px;
        border-bottom: 1px solid #1a1a1a;
        padding: 0.15rem 0 0.6rem 0; margin-bottom: 0.9rem;
    }
    .rp-tab {
        display: inline-flex; align-items: baseline; gap: 6px;
        padding: 4px 10px; border-radius: 3px;
        font-size: 11px; letter-spacing: 0.05em; text-transform: uppercase;
        color: #888; background: transparent;
        border: 1px solid transparent;
    }
    .rp-tab .rp-tab-num {
        font-size: 9px; opacity: 0.7; letter-spacing: 0.1em;
    }
    .rp-tab-active {
        color: #fff; background: rgba(255,255,255,0.03);
        border: 1px solid #262626;
    }

    /* KPI strip and its cards (variant with a coloured top rule). */
    .rp-kpi-strip {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px; margin: 0.2rem 0 1rem 0;
    }
    .rp-kpi {
        background: #0f0f0f; border: 1px solid #1a1a1a; border-radius: 4px;
        padding: 0.75rem 0.9rem; border-top: 2px solid #333;
    }
    .rp-kpi-label {
        font-size: 10px; color: #888; letter-spacing: 0.1em;
        text-transform: uppercase; margin-bottom: 4px;
    }
    .rp-kpi-value {
        font-size: 22px; font-weight: 700; line-height: 1.1; color: #fff;
    }
    .rp-kpi-sub { font-size: 10px; color: #888; margin-top: 4px; }

    /* Rounded content boxes: explanation, current reading, model note, warning. */
    .rp-box {
        border: 1px solid #1a1a1a; background: #0d0d0d;
        border-radius: 4px; padding: 0.8rem 1rem; margin: 0.4rem 0;
    }
    .rp-box-label {
        font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
        color: #aaa; margin-bottom: 6px;
    }
    .rp-box-body { font-size: 12.5px; color: #ccc; line-height: 1.55; }
    .rp-box-explain    { border-left: 2px solid #35bdf4; }
    .rp-box-reading    { border-left: 2px solid #5fb04f; }
    .rp-box-note       { border-left: 2px solid #b184ff; }
    .rp-box-warn       {
        border-left: 2px solid #d99830; background: rgba(217,152,48,0.06);
    }

    /* Section footer with Builds on / Next chips. */
    .rp-footer {
        display: flex; justify-content: space-between; align-items: baseline;
        border-top: 1px solid #1a1a1a; margin-top: 1.4rem; padding-top: 0.6rem;
        color: #666; font-size: 10px; letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    .rp-footer a { color: #aaa; text-decoration: none; }
    .rp-footer a:hover { color: #fff; }
    </style>
    """
