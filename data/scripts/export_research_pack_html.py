#!/usr/bin/env python3
"""
scripts/export_research_pack_html.py
====================================
Generate a standalone HTML research pack from DATA.xlsx using existing models.

Usage:
    python scripts/export_research_pack_html.py

Output:
    reports/research_pack_<YYYYMMDD>.html

No Streamlit dependency. Uses Plotly for charts (included inline).
"""
from __future__ import annotations

import sys, os, html as _html, json
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Data + models
# ---------------------------------------------------------------------------
from data.loader import load_data, latest_valid_date, source_signature
from index.composite import compute_index
from config.pages import PAGES, STATUS_LABELS
from config.theme import SECTION_COLORS

# Phase 2 models
from models.rate_decomposition import (
    available_us_tenors, build_us_curve_snapshot,
    rolling_rate_attribution, rolling_curve_decomposition,
)
from models.curve_regimes import (
    build_regime_matrix, classify_pair_history,
    days_in_current_regime, REGIME_COLORS as CURVE_REGIME_COLORS,
)
from models.global_rates import (
    available_country_curves, build_slope_ranking,
    country_1m_changes, build_curve_snapshots, COUNTRY_LABELS,
)
from models.cross_asset.directional import (
    classify_8regime, REGIMES_8,
    days_in_current_regime as ca_days_in,
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
CSS = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #0b0b0b; color: #ccc; font-family: Inter, system-ui, sans-serif;
         font-size: 12px; line-height: 1.5; }
  .container { max-width: 900px; margin: 0 auto; padding: 24px 32px; }
  .page { page-break-after: always; padding-bottom: 40px; margin-bottom: 20px;
          border-bottom: 1px solid #1a1a1a; }
  .page:last-child { page-break-after: avoid; }
  h1 { font-size: 22px; font-weight: 700; color: #fff; letter-spacing: 0.04em; }
  h2 { font-size: 16px; font-weight: 700; color: #fff; letter-spacing: 0.03em;
       margin: 18px 0 8px; }
  h3 { font-size: 12px; font-weight: 700; color: #888; letter-spacing: 0.1em;
       text-transform: uppercase; margin: 14px 0 6px; }
  .sub { font-size: 11px; color: #888; letter-spacing: 0.06em; }
  .header-stripe { border-left: 3px solid #333; padding: 6px 0 8px 14px; margin-bottom: 16px; }
  .section-num { font-size: 10px; color: #888; letter-spacing: 0.16em; text-transform: uppercase; }
  .kpi-strip { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 16px; }
  .kpi { background: #0f0f0f; border: 1px solid #1a1a1a; border-radius: 4px;
         padding: 10px 14px; border-top: 2px solid #333; flex: 1; min-width: 140px; }
  .kpi-label { font-size: 10px; color: #888; letter-spacing: 0.1em; text-transform: uppercase; }
  .kpi-value { font-size: 20px; font-weight: 700; color: #fff; }
  .kpi-sub { font-size: 10px; color: #888; margin-top: 3px; }
  .box { border: 1px solid #1a1a1a; background: #0d0d0d; border-radius: 4px;
         padding: 10px 14px; margin: 8px 0; }
  .box-label { font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
               color: #aaa; margin-bottom: 4px; }
  .box-reading { border-left: 2px solid #5fb04f; }
  .box-method { border-left: 2px solid #b184ff; }
  .box-warn { border-left: 2px solid #d99830; background: rgba(217,152,48,0.06); }
  table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 11px; }
  th { text-align: left; padding: 6px 8px; border-bottom: 1px solid #222;
       color: #888; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
  td { padding: 5px 8px; border-bottom: 1px solid #111; color: #ccc; }
  .chip { display: inline-block; padding: 2px 8px; border-radius: 3px;
          font-size: 10px; font-weight: 700; letter-spacing: 0.06em; }
  .plotly-chart { margin: 12px 0; }
  @media print {
    body { background: #0b0b0b; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .page { page-break-after: always; }
  }
</style>
"""

E = _html.escape


def _kpi(label, value, sub="", accent=""):
    top = f"border-top-color:{accent};" if accent else ""
    vc = f"color:{accent};" if accent else ""
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    return (f"<div class='kpi' style='{top}'>"
            f"<div class='kpi-label'>{E(label)}</div>"
            f"<div class='kpi-value' style='{vc}'>{E(str(value))}</div>"
            f"{sub_html}</div>")


def _kpi_strip(cards):
    return "<div class='kpi-strip'>" + "".join(
        _kpi(c.get("label",""), c.get("value",""), c.get("sub",""), c.get("accent",""))
        for c in cards
    ) + "</div>"


def _section_header(num, title, color, subtitle=""):
    return (f"<div class='header-stripe' style='border-left-color:{color};'>"
            f"<div class='section-num' style='color:{color};'>{E(num)} · Section</div>"
            f"<h2>{E(title)}</h2>"
            f"<div class='sub'>{E(subtitle)}</div></div>")


def _reading_box(title, items):
    body = "<br>".join(f"<span style='color:#888;'>{E(k)}:</span> <b>{v}</b>"
                       for k, v in items)
    return f"<div class='box box-reading'><div class='box-label'>{E(title)}</div>{body}</div>"


def _method_box(title, text):
    return f"<div class='box box-method'><div class='box-label'>{E(title)}</div>{text}</div>"


def _df_table(df, max_rows=30):
    if df.empty:
        return "<p class='sub'>No data.</p>"
    df = df.head(max_rows)
    hdr = "".join(f"<th>{E(str(c))}</th>" for c in df.columns)
    rows = ""
    for _, r in df.iterrows():
        rows += "<tr>" + "".join(f"<td>{E(str(v))}</td>" for v in r.values) + "</tr>"
    return f"<table><thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table>"


def _try_plotly_html(fig) -> str:
    """Convert a Plotly figure to an HTML fragment."""
    try:
        return ("<div class='plotly-chart'>"
                + fig.to_html(full_html=False, include_plotlyjs=False)
                + "</div>")
    except Exception:
        return "<p class='sub'>Chart rendering failed.</p>"


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------
def _build_cover(df, r, lvd, sig):
    regime = r.latest_regime
    from config.theme import REGIME_COLORS
    rc = REGIME_COLORS.get(regime, "#888")
    return (
        "<div class='page'>"
        f"<h1>Rates &amp; Liquidity Research Pack</h1>"
        f"<div class='sub' style='margin:6px 0 16px;'>"
        f"Latest: {lvd.strftime('%B %d, %Y')} · DATA.xlsx hash: {sig[:12]}…</div>"
        + _kpi_strip([
            {"label": "Composite Liquidity Index", "value": f"{r.latest:.1f}",
             "sub": regime, "accent": rc},
            {"label": "1W", "value": f"{r.changes().get('1w', 0):+.1f}"},
            {"label": "1M", "value": f"{r.changes().get('1m', 0):+.1f}"},
            {"label": "3M", "value": f"{r.changes().get('3m', 0):+.1f}"},
        ])
        + "</div>"
    )


def _build_contents():
    rows = ""
    for p in PAGES:
        sc = SECTION_COLORS.get(p["color_key"], "#888")
        rows += (f"<tr><td style='color:{sc};font-weight:700;'>{E(p['section'])}</td>"
                 f"<td>{E(p['title'])}</td>"
                 f"<td><span class='chip' style='color:{sc};border:1px solid {sc}55;'>"
                 f"{E(STATUS_LABELS[p['status']])}</span></td>"
                 f"<td class='sub'>{E(p['description'][:80])}</td></tr>")
    return ("<div class='page'><h2>Contents</h2>"
            f"<table><thead><tr><th>No.</th><th>Section</th><th>Status</th>"
            f"<th>Description</th></tr></thead><tbody>{rows}</tbody></table></div>")


def _build_liquidity(r):
    regime = r.latest_regime
    from config.theme import REGIME_COLORS
    rc = REGIME_COLORS.get(regime, "#888")
    changes = r.changes()

    html = ("<div class='page'>"
            + _section_header("00", "Liquidity Overview", "#5fb04f")
            + _kpi_strip([
                {"label": "CLI", "value": f"{r.latest:.1f}", "sub": regime, "accent": rc},
                {"label": "1W Δ", "value": f"{changes.get('1w',0):+.1f} pts"},
                {"label": "1M Δ", "value": f"{changes.get('1m',0):+.1f} pts"},
                {"label": "3M Δ", "value": f"{changes.get('3m',0):+.1f} pts"},
            ]))

    # Bucket contributions
    try:
        bc = r.level_contributions()
        if bc is not None and not bc.empty:
            bdf = pd.DataFrame({"Bucket": bc.index, "Contribution": bc.values.round(2)})
            html += "<h3>Bucket contributions</h3>" + _df_table(bdf)
    except Exception:
        pass

    # Drivers
    try:
        d = r.drivers("1m")
        if d:
            html += _reading_box("1M drivers", [
                ("Top easing", d[0] if d[0] else "—"),
                ("Top tightening", d[1] if d[1] else "—"),
            ])
    except Exception:
        pass

    html += _method_box("Methodology",
        "Rolling z-score composite across 5 buckets. 50 = neutral, higher = looser.")
    html += "</div>"
    return html


def _build_decomposition(df):
    snap = build_us_curve_snapshot(df)
    if snap.empty:
        return ""
    color = "#35bdf4"
    html = ("<div class='page'>"
            + _section_header("02", "Rate Decomposition", color))

    r10 = snap[snap["tenor"] == "10Y"]
    if not r10.empty:
        r = r10.iloc[0]
        html += _kpi_strip([
            {"label": "10Y Nominal", "value": f"{r['nominal']:.2f}%",
             "sub": f"1M: {r['nominal_1m_change_bp']:+.0f} bp"},
            {"label": "10Y Real", "value": f"{r['real']:.2f}%", "accent": "#06b6d4",
             "sub": f"1M: {r['real_1m_change_bp']:+.0f} bp"},
            {"label": "10Y Inflation", "value": f"{r['inflation']:.2f}%", "accent": "#f97316",
             "sub": f"1M: {r['inflation_1m_change_bp']:+.0f} bp"},
            {"label": "1M Driver", "value": r["driver_1m"],
             "sub": f"{r['driver_share_1m']:.0%} share"},
        ])

    # Curve snapshot table
    disp = snap[["tenor", "nominal", "real", "inflation",
                 "nominal_1m_change_bp", "real_1m_change_bp", "inflation_1m_change_bp",
                 "driver_1m"]].copy()
    for c in ["nominal", "real", "inflation"]:
        disp[c] = disp[c].apply(lambda x: f"{x:.2f}%")
    for c in ["nominal_1m_change_bp", "real_1m_change_bp", "inflation_1m_change_bp"]:
        disp[c] = disp[c].apply(lambda x: f"{x:+.0f} bp")
    disp.columns = ["Tenor", "Nominal", "Real", "Inflation", "Nom 1M", "Real 1M", "Infl 1M", "Driver"]
    html += "<h3>US Curve Snapshot</h3>" + _df_table(disp)

    # Attribution chart
    try:
        import plotly.graph_objects as go
        att = rolling_rate_attribution(df, "10Y", 10).dropna().iloc[-252:]
        if not att.empty:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=att.index, y=att["real_contribution_bp"],
                name="Real", marker_color="#06b6d4"))
            fig.add_trace(go.Bar(x=att.index, y=att["inflation_contribution_bp"],
                name="Inflation", marker_color="#f97316"))
            fig.add_trace(go.Scatter(x=att.index, y=att["nominal_change_bp"],
                mode="lines", name="Nominal 10D", line=dict(color="#fff", width=1.2)))
            fig.update_layout(template="plotly_dark", paper_bgcolor="#0b0b0b",
                plot_bgcolor="#0b0b0b", height=280, barmode="relative",
                margin=dict(l=40, r=20, t=20, b=20), showlegend=True,
                legend=dict(orientation="h", y=1.02, font=dict(size=10)),
                yaxis=dict(title="bp", gridcolor="#1a1a1a"), xaxis=dict(showgrid=False))
            html += "<h3>10Y Rolling Attribution (1Y)</h3>" + _try_plotly_html(fig)
    except Exception:
        pass

    html += _method_box("Methodology",
        "Breakeven identity: nominal = real + inflation. Residual is zero by construction.")
    html += "</div>"
    return html


def _build_regimes(df):
    matrix = build_regime_matrix(df)
    if matrix.empty:
        return ""
    color = "#f0c000"
    html = ("<div class='page'>"
            + _section_header("03", "Curve Regimes", color))

    # KPIs
    kpis = []
    for ctype in ["Nominal", "Real", "Inflation"]:
        h = classify_pair_history(df, ctype.lower(), ("2Y", "10Y"), 10)
        if not h.empty and h["regime"].dropna().shape[0]:
            reg = h["regime"].dropna().iloc[-1]
            days = days_in_current_regime(h["regime"])
            rc = CURVE_REGIME_COLORS.get(reg, "#888") if pd.notna(reg) else "#888"
            kpis.append({"label": f"{ctype} 2s10s", "value": str(reg) if pd.notna(reg) else "—",
                         "sub": f"{days}d", "accent": rc})
    html += _kpi_strip(kpis) if kpis else ""

    # Matrix
    html += "<h3>Regime Matrix</h3>"
    mdisp = matrix.copy()
    html += _df_table(mdisp.reset_index().rename(columns={"index": "Curve"}))

    html += _method_box("Methodology",
        "10D regime window, 7 regimes, 6 tenor pairs (2Y/5Y/10Y/30Y).")
    html += "</div>"
    return html


def _build_global(df):
    slopes = build_slope_ranking(df)
    changes = country_1m_changes(df)
    snapshots = build_curve_snapshots(df)
    color = "#00d07a"

    html = ("<div class='page'>"
            + _section_header("04", "Global Rates", color))

    kpis = []
    if not changes.empty:
        kpis.append({"label": "Top 1M riser",
                     "value": f"{changes.iloc[0]['label']} ({changes.iloc[0]['change_1m_bp']:+.0f} bp)",
                     "accent": "#ef4444"})
        kpis.append({"label": "Top 1M faller",
                     "value": f"{changes.iloc[-1]['label']} ({changes.iloc[-1]['change_1m_bp']:+.0f} bp)",
                     "accent": "#22c55e"})
    if not slopes.empty:
        kpis.append({"label": "Steepest 2s10s",
                     "value": f"{slopes.iloc[0]['label']} ({slopes.iloc[0]['slope_bp']:+.0f} bp)"})
    html += _kpi_strip(kpis) if kpis else ""

    # 10Y table
    if not changes.empty:
        html += "<h3>10Y Levels &amp; 1M Changes</h3>"
        cdisp = changes[["label", "yield_10y", "change_1m_bp"]].copy()
        cdisp["yield_10y"] = cdisp["yield_10y"].apply(lambda x: f"{x:.2f}%")
        cdisp["change_1m_bp"] = cdisp["change_1m_bp"].apply(lambda x: f"{x:+.0f} bp")
        cdisp.columns = ["Country", "10Y Yield", "1M Change"]
        html += _df_table(cdisp)

    # Slope ranking
    if not slopes.empty:
        html += "<h3>2s10s Slope Ranking</h3>"
        sdisp = slopes[["label", "slope_bp", "inverted"]].copy()
        sdisp["slope_bp"] = sdisp["slope_bp"].apply(lambda x: f"{x:+.0f} bp")
        sdisp["inverted"] = sdisp["inverted"].apply(lambda x: "Yes" if x else "No")
        sdisp.columns = ["Country", "2s10s Slope", "Inverted"]
        html += _df_table(sdisp)

    html += "</div>"
    return html


def _build_cross_asset(df):
    from data.external_loaders import load_crossasset
    prices = load_crossasset()
    if prices is None:
        return ""
    color = "#b184ff"
    result = classify_8regime(prices)
    if result.empty:
        return ""

    cur = result["regime"].iloc[-1]
    info = REGIMES_8[cur]
    days = ca_days_in(result["regime"])

    html = ("<div class='page'>"
            + _section_header("05", "Cross-Asset Regime Timeline", color))

    last = result.iloc[-1]
    html += _kpi_strip([
        {"label": "Current Regime", "value": info["label"],
         "sub": f"{cur} · {days}d", "accent": info["color"]},
        {"label": "SPX Signal", "value": f"{last['spx_signal']:+.2f}"},
        {"label": "Rates Signal", "value": f"{last['rates_signal']:+.2f}"},
        {"label": "DXY Signal", "value": f"{last['dxy_signal']:+.2f}"},
    ])

    # Frequency table
    freq = result["regime"].value_counts().reindex([f"R{i}" for i in range(1,9)], fill_value=0)
    pct = (freq / len(result) * 100).round(1)
    ftbl = pd.DataFrame({
        "Regime": [f"R{i}" for i in range(1,9)],
        "Label": [REGIMES_8[f"R{i}"]["label"] for i in range(1,9)],
        "Days": freq.values, "% Total": [f"{p:.1f}%" for p in pct.values],
    })
    html += "<h3>Regime Frequency</h3>" + _df_table(ftbl)

    html += _method_box("Methodology",
        "20D change ÷ 21D trailing vol. Sign of vol-scaled signal → UP/DOWN. 2³ = 8 regimes.")
    html += "</div>"
    return html


def _build_data_quality(df, lvd, sig):
    color = "#9aa0a6"
    html = ("<div class='page'>"
            + _section_header("07", "Data Quality & Model Readiness", color))

    html += _kpi_strip([
        {"label": "Latest Valid Date", "value": str(lvd.date()) if lvd else "—"},
        {"label": "Source Hash", "value": sig[:12] + "…"},
        {"label": "Sheet1 Rows", "value": f"{len(df):,}"},
        {"label": "Sheet1 Cols", "value": f"{df.shape[1]}"},
    ])

    # Phase 2 readiness
    from models.rate_decomposition import US_NOMINAL, US_BREAKEVEN
    req_decomp = list(US_NOMINAL.values()) + list(US_BREAKEVEN.values())
    cols = set(str(c) for c in df.columns)
    miss_decomp = [c for c in req_decomp if c not in cols]

    readiness = [
        ("Rate Decomposition", "Ready" if not miss_decomp else "Missing"),
        ("Curve Regimes", "Ready" if not miss_decomp else "Missing"),
        ("Global Rates", f"{len(available_country_curves(df))} countries"),
        ("Cross-Asset", "Ready" if all(c in cols for c in ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]) else "Missing"),
    ]
    html += _reading_box("Phase 2 Model Readiness", readiness)

    # Future
    future = [
        ("FOMC path", "Missing data"),
        ("SOFR futures strip", "Missing data"),
        ("FX rate-differential", "Missing data"),
        ("SPX sector attribution", "Missing data"),
        ("Earnings vs valuation", "Missing data"),
    ]
    html += "<h3>Future Models</h3>"
    html += _reading_box("Requires additional data", future)

    html += "</div>"
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_html(include_plotlyjs: bool = True,
               plotly_mode: str = "inline") -> tuple[str, str]:
    """Build the full HTML report. Returns (html_string, filename).

    plotly_mode:
        "inline" (default) — embed Plotly JS inline for offline use
        "cdn"    — use CDN (smaller file, needs internet)
        "none"   — no Plotly JS (tables only)
    """
    df = load_data()
    lvd = latest_valid_date(df)
    sig = source_signature()
    r = compute_index(df)
    date_str = lvd.strftime("%Y%m%d") if lvd else "unknown"

    # Plotly JS include
    plotly_js = ""
    if include_plotlyjs and plotly_mode != "none":
        try:
            if plotly_mode == "cdn":
                import plotly
                plotly_js = f'<script src="https://cdn.plot.ly/plotly-{plotly.__version__}.min.js"></script>'
            else:  # inline (default)
                from plotly.offline import get_plotlyjs
                plotly_js = f"<script>{get_plotlyjs()}</script>"
        except ImportError:
            pass

    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>Research Pack — {date_str}</title>",
        CSS, plotly_js,
        f"</head><body><div class='container'>",
        _build_cover(df, r, lvd, sig),
        _build_contents(),
        _build_liquidity(r),
        _build_decomposition(df),
        _build_regimes(df),
        _build_global(df),
        _build_cross_asset(df),
        _build_data_quality(df, lvd, sig),
        "</div></body></html>",
    ]

    html = "\n".join(parts)
    filename = f"research_pack_{date_str}.html"
    return html, filename


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export HTML research pack")
    parser.add_argument("--plotly", choices=["inline", "cdn", "none"],
                        default="inline", help="Plotly JS mode (default: inline)")
    args = parser.parse_args()
    html, filename = build_html(plotly_mode=args.plotly)
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / filename
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")
