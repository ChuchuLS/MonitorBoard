"""
charts/common.py
================
Reusable, theme-aware chart primitives shared across every section. Each
builder returns a Plotly figure (pure) so the rendering layer in app.py just
calls st.plotly_chart.

Includes the y-axis auto-scaling helper that replaces hard-coded ranges
(requirement #4): axes follow the visible data and only pull zero into view when
the data crosses zero or sits close to it.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.theme import (
    BG, GRID, LINE_WHITE, TEXT_DIM, TEXT_VERY_DIM, DARK_LAYOUT,
    ACCENT_GREEN, ACCENT_RED, NOTE_RED_BG, NOTE_RED_BORDER, NOTE_RED_TEXT,
    NOTE_GREEN_BG, NOTE_GREEN_BORDER, NOTE_GREEN_TEXT,
)


# ---------------------------------------------------------------------------
# Y-axis auto-scaling (requirement #4)
# ---------------------------------------------------------------------------
def autoscale_range(values, pad_frac: float = 0.08,
                    zero_proximity: float = 0.30) -> list | None:
    """Compute a sensible [min, max] y-range from the data.

    Rules:
      * Pad above and below the data by ``pad_frac`` of its span.
      * Only force zero into view when the series crosses zero, or when it sits
        within ``zero_proximity`` of its own range from zero. Otherwise zoom to
        where the data actually lives — no dead vertical space.
      * Return None when there is nothing to scale, letting Plotly autorange.
    """
    vals = [v for v in values if v is not None and pd.notna(v)]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    span = hi - lo if hi > lo else (abs(hi) or 1.0)
    pad = span * pad_frac
    y_min, y_max = lo - pad, hi + pad

    if lo < 0 < hi:
        return [y_min, y_max]                 # crosses zero -> keep both sides
    if 0 < lo < span * zero_proximity:
        return [-span * 0.05, y_max]          # hugs zero from above -> show it
    if -span * zero_proximity < hi < 0:
        return [y_min, span * 0.05]           # hugs zero from below -> show it
    return [y_min, y_max]                     # zoom to data


def section_header(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-header">
          <div class="section-title">{title}</div>
          <div class="section-sub">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mini_dark(series: pd.Series, title: str, color: str = LINE_WHITE,
              height: int = 180, zero_line: bool = True,
              fmt: str = "{:+.1f}") -> go.Figure:
    """Compact dark line chart with a last-value badge in the title."""
    fig = go.Figure()
    s = series.dropna()
    if len(s):
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, mode="lines",
            line=dict(color=color, width=1.1),
            hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[s.index[-1]], y=[s.iloc[-1]], mode="markers",
            marker=dict(color=color, size=5, line=dict(color=BG, width=1)),
            hoverinfo="skip", showlegend=False,
        ))
    if zero_line:
        fig.add_hline(y=0, line=dict(color=TEXT_VERY_DIM, width=0.5, dash="dot"))

    last_val = s.iloc[-1] if len(s) else float("nan")
    last_str = fmt.format(last_val) if pd.notna(last_val) else "—"
    last_color = ACCENT_GREEN if (pd.notna(last_val) and last_val >= 0) else ACCENT_RED
    title_html = (
        f"<span style='color:#fff;font-weight:700;letter-spacing:0.05em'>"
        f"{title.upper()}</span>  "
        f"<span style='color:{last_color};font-size:10px;font-weight:700'>"
        f"{last_str}</span>"
    )
    fig.update_layout(
        **DARK_LAYOUT, height=height,
        margin=dict(l=35, r=10, t=28, b=22),
        title=dict(text=title_html, font=dict(size=10), x=0, xanchor="left", y=0.97),
    )
    fig.update_xaxes(showgrid=False, tickfont=dict(size=8, color=TEXT_DIM), linecolor="#222")
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False,
                     tickfont=dict(size=8, color=TEXT_DIM), linecolor="#222")
    return fig


def ofr_chart(series: pd.Series, top_note: str | None,
              bottom_note: str | None, height: int = 160) -> go.Figure:
    """OFR-style dark chart with optional red/green interpretation boxes."""
    fig = go.Figure()
    s = series.dropna()
    if len(s):
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, mode="lines",
            line=dict(color=LINE_WHITE, width=1),
            hovertemplate="%{x|%Y-%m-%d}: %{y:.3f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=[s.index[-1]], y=[s.iloc[-1]], mode="markers",
            marker=dict(color=LINE_WHITE, size=6, line=dict(color=BG, width=1)),
            hoverinfo="skip", showlegend=False,
        ))
    fig.add_hline(y=0, line=dict(color=TEXT_VERY_DIM, width=0.5, dash="dot"))

    if top_note:
        fig.add_annotation(
            xref="paper", yref="paper", x=0.5, y=0.92,
            text=f"<b>{top_note}</b>", showarrow=False,
            bgcolor=NOTE_RED_BG, bordercolor=NOTE_RED_BORDER, borderwidth=1,
            font=dict(color=NOTE_RED_TEXT, size=9, family="Inter, sans-serif"),
            align="center",
        )
    if bottom_note:
        fig.add_annotation(
            xref="paper", yref="paper", x=0.5, y=0.08,
            text=f"<b>{bottom_note}</b>", showarrow=False,
            bgcolor=NOTE_GREEN_BG, bordercolor=NOTE_GREEN_BORDER, borderwidth=1,
            font=dict(color=NOTE_GREEN_TEXT, size=9, family="Inter, sans-serif"),
            align="center",
        )

    fig.update_layout(
        **DARK_LAYOUT, height=height,
        margin=dict(l=10, r=55, t=10, b=20),
        yaxis=dict(side="right", showgrid=True, gridcolor=GRID, zeroline=False,
                   tickfont=dict(color=TEXT_DIM, size=9),
                   title=dict(text="<i>spread</i>",
                              font=dict(size=9, color="#aaa"), standoff=2)),
        xaxis=dict(showgrid=False, tickfont=dict(color=TEXT_DIM, size=9)),
    )
    return fig


# ===========================================================================
# Research-pack shell helpers (Phase 1)
# ===========================================================================
# These are the reusable UI primitives every page renderer uses to build the
# PDF-style shell — page header, top-tab strip, KPI strip, content boxes, and
# the section footer with Builds on / Next linkage.
#
# Everything below is presentation-only. It never touches data or the index
# calculation; page renderers are responsible for computing whatever they show
# and just handing values to these helpers.

import html as _html

from config.theme import section_color as _section_color
from config.pages import PAGES as _PAGES, PAGES_BY_ID as _PAGES_BY_ID


def _esc(x) -> str:
    """Cheap HTML escaper for values injected into templates."""
    return _html.escape(str(x) if x is not None else "")


def render_page_header(page: dict, latest_date: str | None = None,
                       viewing: str | None = None) -> None:
    """Institutional page header: '00 · SECTION' + big title + subtitle.

    ``page`` is a dict from the PAGES registry (or any dict with 'section',
    'title', 'description', 'color_key'). ``latest_date`` and ``viewing`` are
    optional context strings appended to the subtitle line.
    """
    color = _section_color(page.get("color_key"))
    section = _esc(page.get("section", ""))
    title = _esc(page.get("title", ""))
    subtitle = _esc(page.get("description", ""))
    ctx_bits = []
    if latest_date:
        ctx_bits.append(f"Latest: <span style='color:#ccc;'>{_esc(latest_date)}</span>")
    if viewing:
        ctx_bits.append(f"Viewing: <span style='color:#ccc;'>{_esc(viewing)}</span>")
    ctx = "  ·  ".join(ctx_bits)
    ctx_row = (f"<div class='rp-page-sub'>{ctx}</div>" if ctx else "")

    st.markdown(
        f"""
        <div class="rp-page-header" style="border-left-color:{color};">
          <div class="rp-page-section" style="color:{color};">
            {section} · Section
          </div>
          <div class="rp-page-title">{title}</div>
          <div class="rp-page-sub">{subtitle}</div>
          {ctx_row}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_top_tabs(current_id: str) -> None:
    """Horizontal strip of section chips at the top of every page, current
    section highlighted. Purely visual — the sidebar radio remains the
    primary nav — so the strip stays orientation without adding click
    complexity mid-render."""
    chips = []
    for p in _PAGES:
        color = _section_color(p["color_key"])
        active = (p["id"] == current_id)
        border = color if active else "transparent"
        text_color = "#fff" if active else "#888"
        bg = "rgba(255,255,255,0.03)" if active else "transparent"
        label = _esc(p["label"])
        num = _esc(p["section"])
        chips.append(
            f"<span class='rp-tab {'rp-tab-active' if active else ''}' "
            f"style='color:{text_color};background:{bg};"
            f"border-color:{border};'>"
            f"<span class='rp-tab-num' style='color:{color};'>{num}</span>"
            f"{label}</span>"
        )
    st.markdown(f"<div class='rp-tabs'>{''.join(chips)}</div>",
                unsafe_allow_html=True)


def render_kpi_card(label: str, value: str, sub: str | None = None,
                    accent: str | None = None) -> str:
    """Return the HTML for one KPI card. ``accent`` is a hex; when supplied it
    colours the top rule and the value. Returned as a string so a caller can
    assemble a whole strip in a single st.markdown call."""
    value_color = accent or "#fff"
    top_border = f"border-top-color:{accent};" if accent else ""
    sub_html = (f"<div class='rp-kpi-sub'>{_esc(sub)}</div>" if sub else "")
    return (
        f"<div class='rp-kpi' style='{top_border}'>"
        f"<div class='rp-kpi-label'>{_esc(label)}</div>"
        f"<div class='rp-kpi-value' style='color:{value_color};'>{_esc(value)}</div>"
        f"{sub_html}</div>"
    )


def render_kpi_strip(cards: list[dict]) -> None:
    """Render a row of KPI cards from a list of dicts. Each dict may contain:
        label   - required
        value   - required (already formatted)
        sub     - optional caption line
        accent  - optional hex colour for the top rule + value
    """
    if not cards:
        return
    inner = "".join(
        render_kpi_card(c["label"], c["value"], c.get("sub"), c.get("accent"))
        for c in cards
    )
    st.markdown(f"<div class='rp-kpi-strip'>{inner}</div>",
                unsafe_allow_html=True)


def _rp_box(label: str, body_html: str, cls: str) -> None:
    st.markdown(
        f"""
        <div class="rp-box {cls}">
          <div class="rp-box-label">{_esc(label)}</div>
          <div class="rp-box-body">{body_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_explanation_box(title: str, body_html: str) -> None:
    """Cyan-accented 'what this shows' side box."""
    _rp_box(title, body_html, "rp-box-explain")


def render_current_reading_box(title: str, body_html: str) -> None:
    """Green-accented 'today's reading' box."""
    _rp_box(title, body_html, "rp-box-reading")


def render_model_note(title: str, body_html: str) -> None:
    """Violet-accented 'model / caveat' note."""
    _rp_box(title, body_html, "rp-box-note")


def render_missing_data_warning(required: list[str] | None = None,
                                available: list[str] | None = None,
                                missing: list[str] | None = None,
                                message: str = "") -> None:
    """Amber-accented, structured missing-data warning for scaffold pages.

    Any of ``required`` / ``available`` / ``missing`` may be None; the empty
    ones are simply omitted. ``message`` is free-form HTML placed above the
    lists (e.g. 'FOMC path requires meeting-dated futures data...')."""
    def _list(label: str, items: list[str], color: str) -> str:
        if not items:
            return ""
        pills = " ".join(
            f"<span style='display:inline-block;padding:2px 8px;margin:2px;"
            f"border:1px solid {color}40;color:{color};border-radius:3px;"
            f"font-size:11px;letter-spacing:0.04em;'>{_esc(x)}</span>"
            for x in items
        )
        return (
            f"<div style='margin-top:8px;'>"
            f"<span style='font-size:10px;color:#888;letter-spacing:0.1em;"
            f"text-transform:uppercase;'>{_esc(label)}</span><br>{pills}</div>"
        )

    body = ""
    if message:
        body += f"<div>{message}</div>"
    body += _list("Required", required or [], "#d99830")
    body += _list("Available now", available or [], "#5fb04f")
    body += _list("Missing", missing or [], "#d04848")
    _rp_box("Missing data", body, "rp-box-warn")


def render_section_footer(page: dict) -> None:
    """Section footer with 'Builds on: <prev>' and 'Next: <next>' chips."""
    builds_on = page.get("builds_on")
    nxt = page.get("next")

    def _chip(prefix: str, page_id: str | None) -> str:
        if not page_id:
            return f"<span>{prefix}: <span style='color:#444;'>—</span></span>"
        p = _PAGES_BY_ID.get(page_id, {})
        color = _section_color(p.get("color_key"))
        num = _esc(p.get("section", ""))
        label = _esc(p.get("title", page_id))
        return (
            f"<span>{prefix}: "
            f"<span style='color:{color};font-weight:700;'>{num}</span> "
            f"<span style='color:#ccc;'>{label}</span></span>"
        )

    st.markdown(
        f"""
        <div class="rp-footer">
          {_chip("Builds on", builds_on)}
          {_chip("Next", nxt)}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# Phase 3 — Consistent reading / status / source helpers
# ===========================================================================

def render_current_reading_list(title: str, items: list[tuple[str, str]]) -> None:
    """Render a reading box with a list of key/value pairs."""
    if not items:
        return
    body = "<br>".join(
        f"<span style='color:#888;'>{_esc(k)}:</span> <b>{v}</b>"
        for k, v in items
    )
    _rp_box(title, body, "rp-box-reading")


def render_model_status_chip(status: str, detail: str = "") -> str:
    """Return HTML for an inline status chip (Ready / Partial / Missing / Experimental)."""
    colors = {
        "Ready": "#5fb04f", "Live": "#5fb04f",
        "Partial": "#d99830",
        "Missing data": "#d04848", "Missing": "#d04848",
        "Experimental": "#b184ff",
    }
    c = colors.get(status, "#888")
    det = f" — {_esc(detail)}" if detail else ""
    return (
        f"<span style='display:inline-block;padding:2px 8px;border:1px solid {c}55;"
        f"color:{c};border-radius:3px;font-size:10px;letter-spacing:0.06em;"
        f"font-weight:700;text-transform:uppercase;'>{_esc(status)}</span>"
        f"<span style='font-size:11px;color:#888;margin-left:6px;'>{det}</span>"
    )


def render_data_source_note(source: str, latest_date: str | None = None,
                            caveat: str | None = None) -> None:
    """Render a small data-source footnote at the bottom of a section."""
    parts = [f"Data source: <b>{_esc(source)}</b>"]
    if latest_date:
        parts.append(f"Latest: <b>{_esc(latest_date)}</b>")
    if caveat:
        parts.append(f"<span style='color:#d99830;'>{_esc(caveat)}</span>")
    st.markdown(
        f"<div style='font-size:10px;color:#666;margin:0.4rem 0;'>"
        f"{'  ·  '.join(parts)}</div>",
        unsafe_allow_html=True,
    )


def render_experimental_badge() -> None:
    """Render a visible but tasteful Experimental badge."""
    st.markdown(
        "<div style='display:inline-block;padding:3px 10px;border:1px solid #b184ff55;"
        "color:#b184ff;border-radius:3px;font-size:10px;letter-spacing:0.08em;"
        "font-weight:700;text-transform:uppercase;margin-bottom:0.6rem;'>"
        "Experimental model — not part of core PDF-style methodology</div>",
        unsafe_allow_html=True,
    )
