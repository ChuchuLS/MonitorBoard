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
        background-color: #050505;
        border-right: 1px solid #1a1a1a;
    }
    section[data-testid="stSidebar"] * { color: #ccc !important; }
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
    [data-testid="stSidebar"] [role="radiogroup"] label {
        color: #ccc !important; font-size: 13px !important;
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
