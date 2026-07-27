"""
charts/pages/data_quality.py
============================
Section 07 — Data Quality & Methodology.

Ordering (Phase 1.5 cleanup):
  1. All data source status (external audit FIRST)
  2. Data freshness warnings
  3. DATA.xlsx ticker coverage
  4. Composite Liquidity Index methodology & audit trail
  5. Forward-fill audit
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from config.pages import get_page, DATA_SOURCES
from config.theme import ACCENT_GREEN, ACCENT_AMBER, ACCENT_RED
from config.tickers import TICKERS

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_missing_data_warning, render_section_footer,
)
from data.loader import load_meta, cache_status_label
from data.quality import validate_data, quality_summary, STALE_BDAYS
from index.methodology import INDEX_METHODOLOGY

from ._context import PageContext

# Required scoring-model sheets expected inside DATA.xlsx
REQUIRED_SCORING_SHEETS = ["Macro_GDP", "Macro_CPI", "Macro_Fiscal", "Rates_10Y",
                           "Equity_ToT", "Equity_FCI", "Equity_EPS", "Equity_Prices"]

# Cross-asset columns required in DATA.xlsx Sheet1
REQUIRED_CROSSASSET_COLS = ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]
REQUIRED_FICC_COLS = ["USGG10YR INDEX", "DXY CURNCY", "SPX INDEX",
                      "USYC2Y10 INDEX", "USGGBE10 INDEX", "USGGT10Y INDEX",
                      "MOVE INDEX", "FXJPEMCS INDEX", "JYBSS12M CURNCY"]


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "—"
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16] + "…"


def render(ctx: PageContext) -> None:
    page = get_page("data_quality")

    render_top_tabs(page["id"])
    from data.loader import latest_valid_date as _lvd
    valid_latest = (_lvd(ctx.df) or ctx.df.index.max()).date()
    latest_date = valid_latest
    render_page_header(page, latest_date=str(valid_latest))

    # Raw workbook audit (reads the raw Excel to detect trailing empty rows)
    def _raw_sheet1_audit(path):
        try:
            raw = pd.read_excel(path, sheet_name="Sheet1")
            raw = raw.rename(columns={raw.columns[0]: "Date"})
            raw["Date"] = pd.to_datetime(raw["Date"], errors="coerce")
            raw = raw.dropna(subset=["Date"]).sort_values("Date").set_index("Date")
            non_empty = raw.notna().any(axis=1)
            lne = raw.index[non_empty].max() if non_empty.any() else None
            rim = raw.index.max() if len(raw) else None
            return {
                "raw_first": str(raw.index.min().date()) if len(raw) else "—",
                "raw_last_index": str(rim.date()) if rim else "—",
                "latest_non_empty": str(lne.date()) if lne else "—",
                "trailing_empty": int((raw.index > lne).sum()) if lne else 0,
                "raw_rows": len(raw), "raw_cols": raw.shape[1],
            }
        except Exception:
            return {"raw_first": "—", "raw_last_index": "—", "latest_non_empty": "—",
                    "trailing_empty": 0, "raw_rows": 0, "raw_cols": 0}

    fpath = Path("data/DATA.xlsx")
    exists = fpath.exists()
    raw_audit = _raw_sheet1_audit(fpath) if exists else {}

    render_explanation_box(
        "Trust chain",
        "The dashboard reads one source-of-truth workbook, <b>DATA.xlsx</b>. "
        "Sheet1 supplies daily market data and model inputs. "
        "Additional sheets supply the global scoring model. "
        "The loader drops all-empty trailing rows so models use only real "
        "market observations.",
    )

    # ==================================================================
    # 1. DATA.xlsx WORKBOOK SECTIONS AUDIT
    # ==================================================================
    st.markdown(
        "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "DATA.xlsx workbook sections</div>",
        unsafe_allow_html=True,
    )

    fhash = _file_hash(fpath) if exists else "—"

    from data.external_loaders import load_pulsar
    scoring_data = load_pulsar() if exists else None
    scoring_first, scoring_last, scoring_rows, scoring_cols = "—", "—", 0, 0
    if scoring_data:
        all_d = [d.index.max() for d in scoring_data.values() if len(d)]
        all_s = [d.index.min() for d in scoring_data.values() if len(d)]
        if all_d: scoring_last = str(max(all_d).date())
        if all_s: scoring_first = str(min(all_s).date())
        scoring_rows = sum(len(d) for d in scoring_data.values())
        scoring_cols = sum(d.shape[1] for d in scoring_data.values())

    all_req_cols = sorted(set(REQUIRED_CROSSASSET_COLS + REQUIRED_FICC_COLS))
    present_cols = set(str(c).strip() for c in ctx.df.columns)
    missing_cols = [c for c in all_req_cols if c not in present_cols]

    try:
        import openpyxl
        wb = openpyxl.load_workbook(fpath, read_only=True)
        sheet_names = set(wb.sheetnames)
        wb.close()
        missing_sheets = [s for s in REQUIRED_SCORING_SHEETS if s not in sheet_names]
    except Exception:
        missing_sheets = ["(could not read sheets)"]

    audit_rows = [
        {
            "Source": "sheet1_market",
            "File": "data/DATA.xlsx",
            "Sheet": "Sheet1",
            "Exists": "✓" if exists else "✗",
            "Hash": fhash,
            "Raw index max": raw_audit.get("raw_last_index", "—"),
            "Latest non-empty": raw_audit.get("latest_non_empty", "—"),
            "Trailing empty": raw_audit.get("trailing_empty", 0),
            "Loaded rows": len(ctx.df),
            "Cols": ctx.df.shape[1],
            "Required": f"{len(all_req_cols)} cross-asset/FICC cols",
            "Missing": ", ".join(missing_cols) if missing_cols else "✓ all present",
        },
        {
            "Source": "scoring_sheets",
            "File": "data/DATA.xlsx",
            "Sheet": "Macro_GDP … Equity_Prices",
            "Exists": "✓" if exists and not missing_sheets else "✗",
            "Hash": "— (same workbook)",
            "First date": scoring_first,
            "Latest date": scoring_last,
            "Rows": scoring_rows,
            "Cols": scoring_cols,
            "Required": f"{len(REQUIRED_SCORING_SHEETS)} scoring sheets",
            "Missing": (", ".join(missing_sheets)
                        if missing_sheets else "✓ all present"),
            "Role": DATA_SOURCES.get("scoring_sheets", {}).get("role", ""),
            "Pages": ", ".join(DATA_SOURCES.get("scoring_sheets", {}).get("pages", [])),
        },
    ]

    st.dataframe(pd.DataFrame(audit_rows), hide_index=True,
                 use_container_width=True, height=min(200, 42 + 34 * len(audit_rows)))

    # ==================================================================
    # 2. FRESHNESS WARNING (scoring sheets vs Sheet1)
    # ==================================================================
    sheet1_latest = ctx.df.index.max().date()
    if scoring_last != "—":
        try:
            sc_date = pd.Timestamp(scoring_last).date()
            gap = (sheet1_latest - sc_date).days
            if gap > 5:
                render_missing_data_warning(
                    message=f"<b>Scoring sheets lag Sheet1 by {gap} days</b><br>"
                            f"Sheet1 latest: {sheet1_latest} · "
                            f"Scoring sheets latest: {sc_date}")
        except Exception:
            pass

    # ==================================================================
    # 2b. PHASE 2 MODEL READINESS
    # ==================================================================
    st.markdown(
        "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Phase 2 model readiness</div>",
        unsafe_allow_html=True,
    )
    REQUIRED_RATE_DECOMP = [
        "USGG2YR INDEX", "USGG5YR INDEX", "USGG10YR INDEX", "USGG30YR INDEX",
        "USGGBE02 INDEX", "USGGBE05 INDEX", "USGGBE10 INDEX", "USGGBE30 INDEX",
    ]
    decomp_missing = [c for c in REQUIRED_RATE_DECOMP if c not in present_cols]
    decomp_status = "Ready" if not decomp_missing else "Missing data"

    # Global Rates — dynamic from tickers
    from config.tickers import TICKERS, REGIME_COUNTRIES
    from models.global_rates import STANDARD_TENORS, COUNTRY_LABELS
    gr_countries_ok, gr_countries_partial, gr_missing_detail = [], [], []
    for country in REGIME_COUNTRIES:
        missing_t = []
        for t in STANDARD_TENORS:
            key = f"{country}_{t}"
            tick = TICKERS.get(key)
            if not tick or tick not in present_cols:
                missing_t.append(t)
        if not missing_t:
            gr_countries_ok.append(country)
        elif len(missing_t) < len(STANDARD_TENORS):
            gr_countries_partial.append(country)
            gr_missing_detail.append(f"{country}: missing {', '.join(missing_t)}")
        else:
            gr_missing_detail.append(f"{country}: no data")
    if gr_countries_ok:
        gr_status = "Ready" if not gr_countries_partial and not gr_missing_detail else "Partial"
    else:
        gr_status = "Missing data"

    readiness = pd.DataFrame([
        {"Model": "Rate Decomposition", "Status": decomp_status,
         "Required": f"{len(REQUIRED_RATE_DECOMP)} cols",
         "Missing": ", ".join(decomp_missing) if decomp_missing else "—",
         "Notes": "Uses breakeven identity"},
        {"Model": "Curve Regimes", "Status": decomp_status,
         "Required": "Same as Rate Decomposition",
         "Missing": ", ".join(decomp_missing) if decomp_missing else "—",
         "Notes": "6 tenor pairs × 3 curve types"},
        {"Model": "Global Rates", "Status": gr_status,
         "Required": f"{len(REGIME_COUNTRIES)} countries × 4 tenors",
         "Missing": "; ".join(gr_missing_detail) if gr_missing_detail else "—",
         "Notes": f"{len(gr_countries_ok)} full + {len(gr_countries_partial)} partial"},
    ])

    def _status_color(val):
        if val == "Ready": return "color: #5fb04f; font-weight: 700;"
        if val == "Partial": return "color: #d99830; font-weight: 700;"
        return "color: #d04848; font-weight: 700;"

    st.dataframe(readiness.style.map(_status_color, subset=["Status"]),
                 hide_index=True, use_container_width=True)

    # ==================================================================
    # 2c. MODEL DATA DEPENDENCY MAP
    # ==================================================================
    st.markdown(
        "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Model data dependency map</div>",
        unsafe_allow_html=True,
    )
    from data.loader import latest_valid_date as _lvd2
    from models.rate_decomposition import US_NOMINAL, US_BREAKEVEN
    dep_req_decomp = list(US_NOMINAL.values()) + list(US_BREAKEVEN.values())
    dep_req_ca = ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]
    dep_req_ficc = ["USGG10YR INDEX", "USYC2Y10 INDEX", "USGGBE10 INDEX",
                    "USGGT10Y INDEX", "MOVE INDEX", "FXJPEMCS INDEX", "JYBSS12M CURNCY"]

    def _dep_status(req_cols):
        miss = [c for c in req_cols if c not in present_cols]
        lvd = _lvd2(ctx.df, req_cols)
        return ("Ready" if not miss else "Missing data",
                ", ".join(miss) if miss else "—",
                str(lvd.date()) if lvd else "—")

    dep_rows = []
    for label, model, req, exp in [
        ("00 Liquidity", "Composite Liquidity Index", None, False),
        ("01 Policy", "Money-market plumbing", None, False),
        ("02 Rate Decomp", "Breakeven identity", dep_req_decomp, False),
        ("03 Curve Regimes", "7-regime classifier", dep_req_decomp, False),
        ("04 Global Rates", "Cross-country curves", None, False),
        ("05 Cross-Asset", "8-regime directional", dep_req_ca, False),
        ("05b Linkage", "PCA 4-regime", dep_req_ca, True),
        ("02b Rates PCA", "Within-rates PCA", dep_req_ficc, True),
        ("06 FX PCA", "FX complex PCA", dep_req_ficc, True),
        ("A1 Scoring", "Macro + market scoring", None, False),
    ]:
        if req:
            dep_st, miss, lvd = _dep_status(req)
        else:
            dep_st, miss, lvd = "Ready", "—", str(valid_latest)
        dep_rows.append({
            "Page": label, "Model": model, "Status": dep_st,
            "Missing": miss, "Latest model date": lvd,
            "Type": "Experimental" if exp else "Core",
        })
    st.dataframe(pd.DataFrame(dep_rows).style.map(_status_color, subset=["Status"]),
                 hide_index=True, use_container_width=True)

    # ==================================================================
    # 2d. FUTURE PDF-STYLE MODEL READINESS
    # ==================================================================
    st.markdown(
        "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Future PDF-style model readiness</div>",
        unsafe_allow_html=True,
    )
    future_models = [
        {"Model": "FOMC implied policy path",
         "Required": "Meeting-dated futures, FOMC calendar, contract conventions",
         "Status": "Not implemented",
         "Notes": "Generic FF/SFR/SER futures prices available in Sheet1. "
                  "Expiry metadata, conventions, and calendar not yet documented."},
        {"Model": "SOFR futures strip",
         "Required": "SOFR futures by expiry, contract month mapping, price-to-rate convention",
         "Status": "Not implemented",
         "Notes": "SFR1/SFR2/SFR3 generic prices available. Contract metadata missing."},
        {"Model": "FX rate-differential attribution",
         "Required": "FX spot + matching yield differentials + model implementation",
         "Status": "Not implemented",
         "Notes": "EURUSD/USDJPY/GBPUSD/AUDUSD spot data available. "
                  "Rate-differential models not yet implemented."},
        {"Model": "SPX sector attribution",
         "Required": "Sector indices + weights + model implementation",
         "Status": "Not implemented",
         "Notes": "11 S&P 500 sector indices and SPX_Sector_Weights sheet available. "
                  "Sector models not yet implemented."},
        {"Model": "Earnings vs valuation",
         "Required": "SPX forward EPS + trailing EPS or PE",
         "Status": "Missing data",
         "Notes": "EPS/PE field presence and meanings not confirmed in workbook."},
    ]
    st.dataframe(pd.DataFrame(future_models).style.map(_status_color, subset=["Status"]),
                 hide_index=True, use_container_width=True)
    st.caption("'Not implemented' = data available but model not built. "
               "'Missing data' = required fields not confirmed in DATA.xlsx.")

    # ==================================================================
    # 3. DATA.xlsx TICKER COVERAGE
    # ==================================================================
    st.markdown(
        "<div style='margin:1.2rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "DATA.xlsx ticker coverage</div>",
        unsafe_allow_html=True,
    )

    meta = load_meta()
    status = cache_status_label()
    status_color = (ACCENT_GREEN if status.startswith(("Fresh", "Rebuilt"))
                    else ACCENT_AMBER)

    report = validate_data(ctx.df, TICKERS)
    summary = quality_summary(report)

    render_kpi_strip([
        {"label": "Source file", "value": "DATA.xlsx", "sub": "manual Bloomberg pull"},
        {"label": "Parquet cache", "value": status,
         "sub": f"end date: {meta.get('end_date', str(latest_date))}",
         "accent": status_color},
        {"label": "Latest data date", "value": str(latest_date),
         "sub": f"{len(ctx.df):,} rows · {ctx.df.shape[1]:,} cols"},
        {"label": "Tickers healthy", "value": f"{summary['healthy']}",
         "sub": f"of {summary['total']} tracked", "accent": ACCENT_GREEN},
        {"label": "Stale / missing",
         "value": f"{summary['stale']} / {summary['missing']}",
         "sub": f"stale = no obs in {STALE_BDAYS} bdays",
         "accent": ACCENT_AMBER if summary['stale'] else "#fff"},
    ])

    show = st.radio("FILTER", ["All", "Problems only (missing or stale)"],
                    index=0, horizontal=True, key="dq_filter")
    table = report.copy()
    if show.startswith("Problems"):
        table = table[(~table["exists"]) | (table["stale"])]

    table["last_date"] = pd.to_datetime(table["last_date"]).dt.date.astype("string")
    table["last_date"] = table["last_date"].fillna("—")
    table["missing_pct"] = (table["missing_pct"] * 100)
    disp = table.rename(columns={
        "key": "Key", "ticker": "Bloomberg ticker", "exists": "Exists",
        "last_date": "Last date", "missing_pct": "Missing %", "n_obs": "Obs",
        "stale": "Stale"})
    disp = disp[["Key", "Bloomberg ticker", "Exists", "Last date",
                 "Missing %", "Obs", "Stale"]]

    def _row_style(row):
        if not row["Exists"]:
            return ["background-color: rgba(208,72,72,0.12)"] * len(row)
        if row["Stale"]:
            return ["background-color: rgba(217,152,48,0.12)"] * len(row)
        return [""] * len(row)

    st.dataframe(
        disp.style.apply(_row_style, axis=1).format(
            {"Missing %": "{:.1f}", "Obs": "{:,}"}, na_rep="—"),
        hide_index=True, use_container_width=True, height=460)
    st.caption(
        "Red = ticker absent · amber = stale. Missing tickers degrade "
        "gracefully — the index and charts skip them.")

    # ==================================================================
    # 4. METHODOLOGY AUDIT
    # ==================================================================
    st.markdown(
        "<div style='margin:1.6rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Composite Liquidity Index — methodology & audit trail</div>",
        unsafe_allow_html=True,
    )
    audit = ctx.audit_bundle.get("methodology", {}) if ctx.audit_bundle else {}
    ver = audit.get("version", INDEX_METHODOLOGY.get("version", "?"))
    st.markdown(
        f"<div style='font-size:13px;color:#fff;margin-bottom:6px;'>"
        f"Methodology Version: <b>{ver}</b></div>"
        f"<div style='font-size:11px;color:#888;margin-bottom:10px;'>"
        f"{INDEX_METHODOLOGY.get('description','')}</div>",
        unsafe_allow_html=True,
    )
    params = {
        "Version": ver,
        "Z-score window": audit.get("z_window", INDEX_METHODOLOGY.get("z_window")),
        "Min periods": audit.get("z_min_periods", INDEX_METHODOLOGY.get("z_min_periods")),
        "Z clip": f"±{audit.get('z_clip', INDEX_METHODOLOGY.get('z_clip'))}",
        "Min unique observations": audit.get("z_min_unique",
                                             INDEX_METHODOLOGY.get("z_min_unique")),
        "Min buckets": audit.get("min_available_buckets",
                                 INDEX_METHODOLOGY.get("min_available_buckets")),
        "Min components": audit.get("min_available_components",
                                    INDEX_METHODOLOGY.get("min_available_components")),
        "Min components / bucket": audit.get("min_components_per_bucket",
            INDEX_METHODOLOGY.get("min_components_per_bucket")),
        "Warm-up (bdays)": audit.get("warmup_days_after_first_valid",
            INDEX_METHODOLOGY.get("warmup_days_after_first_valid")),
        "Latest DATA.xlsx hash": str(audit.get("data_hash", "n/a"))[:16] + "…",
        "Components on latest date": audit.get("components_on_latest", "—"),
        "Buckets on latest date": audit.get("buckets_on_latest", "—"),
        "Latest index":
            f"{audit.get('latest_index'):.2f}"
            if audit.get("latest_index") is not None else "—",
    }
    pdf_frame = pd.DataFrame(
        {"Parameter": list(params.keys()),
         "Value": [str(v) for v in params.values()]})
    st.dataframe(pdf_frame, hide_index=True, use_container_width=True,
                 height=min(560, 42 + 34 * len(pdf_frame)))

    # ==================================================================
    # 5. FORWARD-FILL AUDIT
    # ==================================================================
    ffa = ctx.audit_bundle.get("ffill_audit") if ctx.audit_bundle else None
    if ffa is not None and len(ffa):
        st.markdown(
            "<div style='margin:1.3rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Forward-fill audit</div>",
            unsafe_allow_html=True,
        )
        disp_ffa = ffa.rename(columns={
            "component": "ID", "name": "Component", "frequency": "Freq",
            "max_ffill_days": "Max ffill", "latest_raw_obs": "Latest raw",
            "latest_true_obs": "Latest true obs",
            "days_since_true_obs": "Days since",
            "is_live": "Live", "reason": "Reason",
            "stale_days_1y": "Stale days (1y)",
            "pct_ffilled_1y": "% ffilled (1y)"})
        st.dataframe(
            disp_ffa.style.format({"% ffilled (1y)": "{:.0f}%"}),
            hide_index=True, use_container_width=True, height=460)
        st.caption(
            "Weekly series (Fed reserves/repo) are observed on Wednesdays; "
            "the z-score is computed on those true observations and forward-"
            "filled at most 'Max ffill' business days.")

    render_section_footer(page)
