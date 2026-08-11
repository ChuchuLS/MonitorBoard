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
REQUIRED_LINKAGE_COLS = ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY", "BCOM INDEX", "LF98OAS INDEX"]
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
                "audit_status": "OK",
                "audit_error_type": None,
                "audit_error_message": None,
                "raw_first": str(raw.index.min().date()) if len(raw) else "—",
                "raw_last_index": str(rim.date()) if rim else "—",
                "latest_non_empty": str(lne.date()) if lne else "—",
                "trailing_empty": int((raw.index > lne).sum()) if lne else 0,
                "raw_rows": len(raw), "raw_cols": raw.shape[1],
            }
        except Exception as exc:
            return {
                "audit_status": "Failed",
                "audit_error_type": type(exc).__name__,
                "audit_error_message": str(exc)[:200],
                "raw_first": "Failed / unavailable",
                "raw_last_index": "Failed / unavailable",
                "latest_non_empty": "Failed / unavailable",
                "trailing_empty": None,
                "raw_rows": None,
                "raw_cols": None,
            }

    fpath = Path("data/DATA.xlsx")
    exists = fpath.exists()
    raw_audit = _raw_sheet1_audit(fpath) if exists else {}
    if raw_audit.get("audit_status") == "Failed":
        st.warning(
            f"Raw Sheet1 audit is unavailable because the audit failed. "
            f"({raw_audit.get('audit_error_type')}: "
            f"{raw_audit.get('audit_error_message', '')[:120]})"
        )

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

    all_req_cols = sorted(set(REQUIRED_CROSSASSET_COLS + REQUIRED_FICC_COLS + REQUIRED_LINKAGE_COLS))
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

    _rs_failed = raw_audit.get("audit_status") == "Failed"
    _rs_trailing = "Failed / unavailable" if _rs_failed else raw_audit.get("trailing_empty", 0)
    audit_rows = [
        {
            "Source": "sheet1_market",
            "File": "data/DATA.xlsx",
            "Sheet": "Sheet1",
            "Exists": "✓" if exists else "✗",
            "Hash": fhash,
            "Raw index max": raw_audit.get("raw_last_index", "—"),
            "Latest non-empty": raw_audit.get("latest_non_empty", "—"),
            "Trailing empty": _rs_trailing,
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

    # Country Rate Boards — readiness is based on fully aligned four-tenor
    # histories rather than column presence alone.
    try:
        from models.country_rate_boards import (
            available_country_boards, build_global_country_board_overview,
        )
        _cb_ready = available_country_boards(ctx.df)
        _cb_overview = build_global_country_board_overview(ctx.df, horizon=20)
        st.markdown(
            "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Country Rate Boards — aligned input readiness</div>",
            unsafe_allow_html=True,
        )
        _cb_rows = []
        for _country, _info in _cb_ready.items():
            _cb_rows.append({
                "Country": _info.get("label", _country),
                "Status": _info.get("status", "Missing data"),
                "Aligned observations": _info.get("aligned_observations", 0),
                "First common date": _info.get("first_date") or "—",
                "Latest common date": _info.get("model_date") or "—",
                "Missing tenors": ", ".join(_info.get("missing_tenors", [])) or "—",
            })
        st.dataframe(
            pd.DataFrame(_cb_rows).style.map(_status_color, subset=["Status"]),
            hide_index=True, use_container_width=True,
        )
        if not _cb_overview.empty:
            st.caption(
                "Seven-country comparison common date: "
                f"{_cb_overview['model_date'].iloc[0]} · "
                f"common observations: {_cb_overview['aligned_observations'].iloc[0]}. "
                "No forward-fill is used in country-board calculations."
            )
    except Exception as exc:
        st.warning(
            "Country Rate Boards readiness is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

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
    dep_req_linkage = ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]
    dep_req_ficc = ["USGG10YR INDEX", "USYC2Y10 INDEX", "USGGBE10 INDEX",
                    "USGGT10Y INDEX", "MOVE INDEX", "FXJPEMCS INDEX", "JYBSS12M CURNCY"]

    def _dep_status(req_cols):
        miss = [c for c in req_cols if c not in present_cols]
        lvd = _lvd2(ctx.df, req_cols)
        return ("Ready" if not miss else "Missing data",
                ", ".join(miss) if miss else "—",
                str(lvd.date()) if lvd else "—")

    dep_req_policy = ["SOFRRATE INDEX", "FEDL01 INDEX", "IRRBIOER INDEX"]

    # Dynamic dependency results for the two models whose common model dates
    # cannot be inferred from simple column presence alone.
    special_dependencies = {}
    try:
        from models.sector_rotation import build_sector_snapshot
        from data.external_loaders import load_spx_sector_weights
        sector_dep = build_sector_snapshot(ctx.df, load_spx_sector_weights())
        special_dependencies["Sector rotation & breadth"] = (
            sector_dep.get("status", "Missing data"),
            ", ".join(sector_dep.get("missing", [])) or "—",
            str(sector_dep.get("relative_model_date") or "—"),
        )
    except Exception as exc:
        special_dependencies["Sector rotation & breadth"] = (
            "Missing data", f"Audit failed: {type(exc).__name__}", "—"
        )

    try:
        from models.country_rate_boards import (
            available_country_boards as _available_country_boards,
            build_global_country_board_overview as _build_country_board_overview,
        )
        _cb_dep = _available_country_boards(ctx.df)
        _cb_statuses = [v.get("status", "Missing data") for v in _cb_dep.values()]
        _cb_status = (
            "Ready" if _cb_statuses and all(v == "Ready" for v in _cb_statuses)
            else "Partial" if any(v in {"Ready", "Partial"} for v in _cb_statuses)
            else "Missing data"
        )
        _cb_missing = sorted({
            f"{country}:{tenor}"
            for country, info in _cb_dep.items()
            for tenor in info.get("missing_tenors", [])
        })
        _cb_overview = _build_country_board_overview(ctx.df, horizon=20)
        _cb_date = (
            str(_cb_overview["model_date"].iloc[0])
            if not _cb_overview.empty else "—"
        )
        special_dependencies["Country rate boards"] = (
            _cb_status, ", ".join(_cb_missing) or "—", _cb_date,
        )
    except Exception as exc:
        special_dependencies["Country rate boards"] = (
            "Missing data", f"Audit failed: {type(exc).__name__}", "—"
        )

    try:
        from data.equity_earnings_loader import load_equity_earnings_data
        from models.earnings_valuation import assess_earnings_readiness
        _earnings_dep = assess_earnings_readiness(load_equity_earnings_data(), code="ES1")
        special_dependencies["SPX FY1 earnings & valuation"] = (
            _earnings_dep.get("status", "Missing data"),
            ", ".join(_earnings_dep.get("missing", [])) or "—",
            str(_earnings_dep.get("model_date") or "—"),
        )
    except Exception as exc:
        special_dependencies["SPX FY1 earnings & valuation"] = (
            "Missing data", f"Audit failed: {type(exc).__name__}", "—"
        )

    try:
        from data.external_loaders import load_ficc as _load_linkage_ficc
        from models.market_linkage import assess_market_linkage_readiness as _assess_linkage
        _linkage_ficc = _load_linkage_ficc()
        _linkage_dep = _assess_linkage(_linkage_ficc, corr_window=63) if _linkage_ficc is not None else {
            "status": "Missing data", "missing": ["FICC input frame"],
            "common_latest_date": None,
        }
        special_dependencies["Market linkage & correlations"] = (
            _linkage_dep.get("status", "Missing data"),
            ", ".join(_linkage_dep.get("missing", [])) or "—",
            str(_linkage_dep.get("common_latest_date") or "—"),
        )
    except Exception as exc:
        special_dependencies["Market linkage & correlations"] = (
            "Missing data", f"Audit failed: {type(exc).__name__}", "—"
        )

    try:
        from models.fx_rate_differential import available_fx_pairs
        fx_dep = available_fx_pairs(ctx.df)
        fx_statuses = [v.get("status", "Missing data") for v in fx_dep.values()]
        fx_status = (
            "Ready" if fx_statuses and all(v == "Ready" for v in fx_statuses)
            else "Partial" if any(v in {"Ready", "Partial"} for v in fx_statuses)
            else "Missing data"
        )
        fx_missing = sorted({m for v in fx_dep.values() for m in v.get("missing", [])})
        fx_dates = [v.get("common_latest_date") for v in fx_dep.values()
                    if v.get("common_latest_date") is not None]
        special_dependencies["FX rate-differential monitor"] = (
            fx_status,
            ", ".join(fx_missing) or "—",
            str(max(fx_dates)) if fx_dates else "—",
        )
    except Exception as exc:
        special_dependencies["FX rate-differential monitor"] = (
            "Missing data", f"Audit failed: {type(exc).__name__}", "—"
        )

    dep_rows = []
    for label, model, req, exp in [
        ("00 Liquidity", "Composite Liquidity Index", None, False),
        ("01 Policy", "Funding pressure model", dep_req_policy, False),
        ("02 Rate Decomp", "Breakeven identity", dep_req_decomp, False),
        ("03 Curve Regimes", "7-regime classifier", dep_req_decomp, False),
        ("04 Global Rates", "Cross-country curves", None, False),
        ("04b Country Boards", "Country rate boards", None, False),
        ("05 Cross-Asset", "8-regime directional", dep_req_ca, False),
        ("05b Linkage", "Market linkage & correlations", dep_req_linkage, False),
        ("06 Sectors", "Sector rotation & breadth", None, False),
        ("06c Earnings", "SPX FY1 earnings & valuation", None, False),
        ("07 FX Rates", "FX rate-differential monitor", None, False),
        ("A1 Scoring", "Macro + market scoring", None, False),
    ]:
        if model in special_dependencies:
            dep_st, miss, lvd = special_dependencies[model]
        elif req:
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

    # ── CLI component verification ──
    st.markdown(
        "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Composite Liquidity Index component verification</div>",
        unsafe_allow_html=True,
    )
    cli_verify = pd.DataFrame([
        {"Component": "cb_reserves", "Ticker": "FARBRBFB INDEX",
         "Confirmed identity": "Reserve Balances with Federal Reserve Banks",
         "Unit": "USD millions", "Frequency": "weekly",
         "Ticker status": "Confirmed", "Model-role status": "Confirmed"},
        {"Component": "cb_liquidity_swaps", "Ticker": "FARWCBLS INDEX",
         "Confirmed identity": "Central Bank Liquidity Swaps",
         "Unit": "USD millions", "Frequency": "weekly",
         "Ticker status": "Confirmed",
         "Model-role status": "Methodology review required"},
    ])
    st.dataframe(cli_verify, hide_index=True, use_container_width=True)
    st.markdown(
        "<div style='font-size:11px;color:#ccc;border-left:2px solid #5fb04f;"
        "padding:8px 12px;background:#0a1a0a;border-radius:4px;'>"
        "Both ticker identities are now <b>confirmed</b> via Bloomberg DES.<br>"
        "Earlier project versions incorrectly described FARWCBLS as "
        "'Fed repo / SRF usage'. The ticker has been relabelled without "
        "changing historical numerical values.<br>"
        "The ticker identity is confirmed, but the inclusion, direction, and "
        "weight of cb_liquidity_swaps inside the CLI require a separate "
        "methodology review."
        "</div>", unsafe_allow_html=True,
    )

    # ── Scoring date integrity ──
    try:
        from data.external_loaders import load_pulsar
        from models.scoring.engine import determine_scoring_asof
        scoring_data = load_pulsar()
        if scoring_data:
            sinfo = determine_scoring_asof(scoring_data)
            if sinfo["future_rows"]:
                st.markdown(
                    "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#d99830;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "⚠ Future-dated scoring rows</div>",
                    unsafe_allow_html=True,
                )
                fdf = pd.DataFrame(sinfo["future_rows"])
                st.dataframe(fdf, hide_index=True, use_container_width=True)
                st.caption(f"Production scoring as-of date: {sinfo['asof_date']} "
                           f"(rows after {sinfo['current_date']} need classification)")
    except Exception as exc:
        st.warning(
            f"Future-dated scoring audit is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ── Future-dated Sheet1 rows ──
    try:
        from data.date_integrity import split_market_data_by_asof
        from data.loader import load_data as _ld_full
        full_df = _ld_full(include_future=True)
        split = split_market_data_by_asof(full_df)
        if split["future_row_count"] > 0:
            st.markdown(
                "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#d99830;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "⚠ Future-dated Sheet1 rows</div>",
                unsafe_allow_html=True,
            )
            future_info = [{"Date": d, "Populated fields": n}
                           for d, n in split["future_non_null_by_date"].items()]
            st.dataframe(pd.DataFrame(future_info), hide_index=True,
                         use_container_width=True)
            st.caption(
                f"Current production date: {split['current_date']} · "
                f"Production latest eligible: {split['production_asof']} · "
                f"Future rows: {split['future_row_count']} (excluded from production)")
    except Exception as exc:
        st.warning(
            f"Future-dated Sheet1 audit is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ==================================================================
    # 2d. SOURCE CALENDAR INTEGRITY
    # ==================================================================
    try:
        from data.calendar_integrity import (
            audit_ticker_group_calendar,
            audit_sector_calendar,
            audit_parent_sector_return_range,
        )

        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Source calendar integrity</div>",
            unsafe_allow_html=True,
        )
        groups = [
            audit_sector_calendar(ctx.df),
            audit_ticker_group_calendar(
                ctx.df,
                ["EURUSD BGN CURNCY", "USDJPY BGN CURNCY", "GBPUSD BGN CURNCY", "AUDUSD BGN CURNCY"],
                "FX spot",
            ),
            audit_ticker_group_calendar(
                ctx.df,
                ["SFR1 COMB COMDTY", "SFR2 COMB COMDTY", "SFR3 COMB COMDTY"],
                "Legacy SFR1–SFR3 generic ranks (not production)",
            ),
            audit_ticker_group_calendar(
                ctx.df,
                ["GSWISS02 INDEX", "GSWISS05 INDEX", "GSWISS10 INDEX", "GSWISS30 INDEX"],
                "Switzerland yields",
            ),
            audit_ticker_group_calendar(ctx.df, ["SPX INDEX"], "SPX benchmark"),
            audit_ticker_group_calendar(
                ctx.df, ["USGG2YR INDEX", "USGG10YR INDEX"], "US Treasury yields"
            ),
        ]
        cal_rows = []
        for audit in groups:
            counts = audit["weekday_counts"]
            observed = ", ".join(
                f"{name[:3]}={count}" for name, count in counts.items() if count
            ) or "—"
            cal_rows.append({
                "Group": audit["group"],
                "First date": str(audit["first_date"] or "—"),
                "Latest date": str(audit["latest_date"] or "—"),
                "Observations": audit["observation_count"],
                "Observed weekdays": observed,
                "Weekend observations": audit["weekend_observation_count"],
                "Missing tickers": ", ".join(audit["missing_tickers"]) or "—",
                "Status": audit["status"],
            })
        st.dataframe(
            pd.DataFrame(cal_rows).style.map(_status_color, subset=["Status"]),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "The current workbook refresh contains normal weekday calendars for the "
            "expanded Sheet1 series. The fixed-contract SFR worksheet is audited "
            "separately because each contract has its own Bloomberg Date output. "
            "No interpolation, forward fill, zero substitution, row-position merge, "
            "or inferred day shift is used."
        )

        parent_audit = audit_parent_sector_return_range(ctx.df)
        if not parent_audit.empty:
            parent_display = parent_audit.rename(columns={
                "horizon": "Horizon",
                "start_date": "Start date",
                "end_date": "End date",
                "spx_return_pct": "SPX return (%)",
                "min_sector_return_pct": "Min sector return (%)",
                "max_sector_return_pct": "Max sector return (%)",
                "sectors_above_spx": "Sectors above SPX",
                "sectors_below_spx": "Sectors below SPX",
                "sector_count": "Sector count",
                "range_test_passed": "Range test passed",
            })
            parent_display["Status"] = parent_display["Range test passed"].map(
                {True: "OK", False: "Needs investigation"}
            )
            st.markdown(
                "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "SPX parent / sector range audit</div>",
                unsafe_allow_html=True,
            )
            st.dataframe(
                parent_display.style.map(_status_color, subset=["Status"]).format({
                    "SPX return (%)": "{:+.2f}",
                    "Min sector return (%)": "{:+.2f}",
                    "Max sector return (%)": "{:+.2f}",
                }),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "This necessary consistency check uses identical labelled timestamps. "
                "A failure is an investigation flag, not proof of a particular date shift."
            )
    except Exception as exc:
        st.warning(
            f"Source-calendar audit is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ── Three-asset Market Linkage audit ──
    try:
        from data.external_loaders import load_ficc as _load_ml_ficc
        from models.market_linkage import (
            MARKET_LINKAGE_CONFIG as _ML_CONFIG,
            build_market_linkage_snapshot as _build_ml_snapshot,
        )
        _ml_ficc = _load_ml_ficc()
        _ml_snap = _build_ml_snapshot(_ml_ficc, corr_window=20, long_window=63) if _ml_ficc is not None else {}
        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Market Linkage &amp; Correlations — source and alignment audit</div>",
            unsafe_allow_html=True,
        )
        _ml_rows = []
        _missing_ml = set(_ml_snap.get("missing", []))
        for _asset, _meta in _ML_CONFIG.items():
            _ml_rows.append({
                "Asset": _meta["label"],
                "Bloomberg ticker": _meta["ticker"],
                "Transformation": _meta["transform"],
                "Present": "No" if _asset in _missing_ml else "Yes",
            })
        st.dataframe(pd.DataFrame(_ml_rows), hide_index=True, use_container_width=True)
        st.caption(
            f"Status: {_ml_snap.get('status', 'Missing data')} · "
            f"Common observations: {_ml_snap.get('aligned_observations', 0)} · "
            f"Common first date: {_ml_snap.get('common_first_date', '—')} · "
            f"Common latest date: {_ml_snap.get('common_latest_date', '—')}. "
            "SPX, UST 10Y and DXY are intersected before daily transformations. "
            "The live gauge is 63D PC1 explained variance, supported by the three "
            "20D pairwise correlations. It is descriptive and not causal attribution."
        )
    except Exception as exc:
        st.warning(
            "Market Linkage readiness is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ── Fixed-contract SOFR Futures Strip audit ──
    try:
        from config.tickers import SOFR_CONTRACT_CONFIG as _SFR_CONTRACTS
        from data.policy_futures_loader import load_policy_futures as _load_fixed_sfr
        from models.policy_futures_strip import build_sofr_strip_snapshot as _build_sfr_strip
        _sfr_raw = _load_fixed_sfr(include_future=True)
        _sfr_prod = _load_fixed_sfr()
        _sfr_snap = _build_sfr_strip(_sfr_prod, ctx.df)
        _sfr_rows = []
        _table = _sfr_snap.get("strip_table")
        for _code, _cfg in _SFR_CONTRACTS.items():
            _series = pd.to_numeric(_sfr_raw.get(_code), errors="coerce").dropna() if _code in _sfr_raw else pd.Series(dtype=float)
            _latest_rate = None
            if isinstance(_table, pd.DataFrame) and not _table.empty:
                _match = _table.loc[_table["ticker"] == _code]
                if not _match.empty:
                    _latest_rate = _match.iloc[0]["implied_rate_pct"]
            _sfr_rows.append({
                "Contract": _cfg["contract_label"],
                "Bloomberg ticker": _code,
                "Source observations": int(len(_series)),
                "First source date": str(_series.index.min().date()) if len(_series) else "—",
                "Latest source date": str(_series.index.max().date()) if len(_series) else "—",
                "Latest implied rate (%)": _latest_rate,
                "Status": "Ready" if len(_series) else "Missing data",
            })
        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "SOFR Futures Strip &amp; Calendar Spreads — source and alignment audit</div>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            pd.DataFrame(_sfr_rows).style.format({
                "Latest implied rate (%)": "{:.3f}",
            }, na_rep="—").map(_status_color, subset=["Status"]),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            f"Model status: {_sfr_snap.get('status', 'Missing data')} · common observations: "
            f"{_sfr_snap.get('aligned_observations', 0)} · common first date: "
            f"{_sfr_snap.get('common_first_date', '—')} · model date: "
            f"{_sfr_snap.get('model_date', '—')}. Each contract is loaded from its own "
            "Date + Price BQL pair in DATA.xlsx / Policy_Futures and joined by Date. "
            "No row-position merge, forward fill, interpolation or zero substitution. "
            "The fixed contract list must be rolled manually when the front contract expires."
        )
    except Exception as exc:
        st.warning(
            "Fixed-contract SOFR futures readiness is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ==================================================================
    # 2e. ANALYTICAL MODEL READINESS
    # ==================================================================
    st.markdown(
        "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Live analytical model readiness</div>",
        unsafe_allow_html=True,
    )
    live_models = [
        {"Model": "Policy & Short Rates",
         "Required": "Confirmed SOFR / EFFR / IORB / TGCR / BGCR / GCF / TPR inputs",
         "Status": "Live",
         "Notes": "Live spot-rate, spread and funding-pressure monitor. The generic "
                  "policy-futures strip is a separate live module; the meeting-by-meeting "
                  "FOMC path remains unimplemented."},
        {"Model": "SOFR Futures Strip & Calendar Spreads",
         "Required": "Eight fixed quarterly SFR contracts in Policy_Futures",
         "Status": "Live",
         "Notes": "Actual SEP 26 through JUN 28 contract strip using 100 − price, "
                  "1D/5D/1M changes, calendar spreads and terminal diagnostics. "
                  "Not a meeting-by-meeting FOMC probability model."},
        {"Model": "Market Linkage & Correlations",
         "Required": "SPX + UST 10Y + DXY (fully aligned)",
         "Status": "Live",
         "Notes": "Reference-pack-style 63D PC1 explained-variance gauge plus three "
                  "20D pairwise correlations. Descriptive co-movement only; not causal "
                  "attribution, fair value or forecast."},
        {"Model": "Sector Rotation & Breadth Monitor",
         "Required": "11 S&P 500 sector indices + SPX + SPX_Sector_Weights (all available)",
         "Status": "Live",
         "Notes": "Descriptive monitor for the 11 sectors. Absolute + relative "
                  "performance, breadth, dispersion, rotation quadrants, weight "
                  "context. NOT causal attribution or official SPX return "
                  "attribution. ETF proxies excluded from production."},
        {"Model": "Sector Contribution Estimate",
         "Required": "11 sector indices + SPX + periodic start weights (all available)",
         "Status": "Live",
         "Notes": "Start-period periodic weight × sector simple return with an "
                  "explicit residual versus actual SPX. Approximation only; not "
                  "official index-provider attribution."},
        {"Model": "SPX FY1 Earnings & Valuation",
         "Required": "SPX Index + BEST_EPS with BEST_FPERIOD_OVERRIDE=1FY",
         "Status": "Live",
         "Notes": "Weekly exact-date monitor. Implied FY1 P/E and exact log identity "
                  "decomposition into FY1 EPS growth and multiple change. A separate "
                  "26-week OLS diagnostic is descriptive and not the reference pack's "
                  "3-year daily model."},
        {"Model": "FX Rate Differential Monitor",
         "Required": "FX spot + 2Y/10Y nominal + 10Y real differentials (all available)",
         "Status": "Live",
         "Notes": "Descriptive monitor for EURUSD/USDJPY/GBPUSD/AUDUSD. "
                  "Fully aligned spot and yield differentials. "
                  "Not causal attribution, fair value, or forecast."},
    ]
    st.dataframe(pd.DataFrame(live_models).style.map(_status_color, subset=["Status"]),
                 hide_index=True, use_container_width=True)

    st.markdown(
        "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Future model readiness</div>",
        unsafe_allow_html=True,
    )
    future_models = [
        {"Model": "FOMC implied policy path",
         "Required": "Actual contract codes/months, FOMC calendar and meeting-path methodology",
         "Status": "Not implemented",
         "Notes": "The fixed quarterly contract strip is Live, but meeting probabilities still require "
                  "the FOMC calendar and a day-weighted meeting-month methodology."},
        {"Model": "FX regression attribution",
         "Required": "Regression methodology, coefficient stability tests, residual diagnostics",
         "Status": "Not implemented",
         "Notes": "Requires methodology design. do_not_fake=True."},
        {"Model": "FX fair-value / forecast model",
         "Required": "Equilibrium framework, forecasting methodology",
         "Status": "Not implemented",
         "Notes": "do_not_fake=True."},
        {"Model": "Official SPX sector attribution",
         "Required": "Daily-weight methodology, divisor-consistent index treatment, or "
                     "official contribution data",
         "Status": "Not implemented",
         "Notes": "Requires additional methodology or data source. do_not_fake=True."},
        {"Model": "Forward estimate vs realized EPS",
         "Required": "Confirmed realized/trailing EPS series with comparable period definition",
         "Status": "Missing data",
         "Notes": "FY1 BEST_EPS is confirmed and live. Realized/trailing EPS is not supplied, "
                  "so forecast-versus-realized analysis remains blocked."},
    ]
    st.dataframe(pd.DataFrame(future_models).style.map(_status_color, subset=["Status"]),
                 hide_index=True, use_container_width=True)
    st.caption("'Not implemented' = data available but model not built. "
               "'Missing data' = required fields not confirmed in DATA.xlsx.")

    # ── FX Rate Differential Monitor readiness ──
    try:
        from models.fx_rate_differential import available_fx_pairs, FX_PAIR_CONFIG
        from config.tickers import TICKERS as _T
        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "FX Rate Differential Monitor — pair readiness</div>",
            unsafe_allow_html=True,
        )
        avail_fx = available_fx_pairs(ctx.df)
        fx_rows = []
        for pair, cfg in FX_PAIR_CONFIG.items():
            r = avail_fx[pair]
            b, q = cfg["base_country"], cfg["quote_country"]
            fx_rows.append({
                "Pair": pair,
                "Spot": _T.get(cfg["spot_key"], "—"),
                f"{b} 2Y": _T.get(f"{b}_2Y", "—"),
                f"{q} 2Y": _T.get(f"{q}_2Y", "—"),
                f"{b} 10Y": _T.get(f"{b}_10Y", "—"),
                f"{q} 10Y": _T.get(f"{q}_10Y", "—"),
                f"{b} real10Y": _T.get(f"{b}_real_10y", "—"),
                f"{q} real10Y": _T.get(f"{q}_real_10y", "—"),
                "Missing": ", ".join(r.get("missing", [])) or "—",
                "Aligned obs": r.get("aligned_obs", 0),
                "First date": str(r.get("common_first_date", "—")),
                "Latest date": str(r.get("common_latest_date", "—")),
                "63D ready": "✓" if r.get("enough_history") else "✗",
                "Status": r.get("status", "—"),
            })
        st.dataframe(pd.DataFrame(fx_rows).style.map(_status_color, subset=["Status"]),
                     hide_index=True, use_container_width=True)
    except Exception as exc:
        st.warning(
            f"FX readiness table is unavailable because the model audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ── Sector Rotation & Breadth Monitor readiness ──
    try:
        from models.sector_rotation import (
            available_sector_inputs, build_sector_snapshot,
            WEIGHT_SUM_TOLERANCE,
        )
        from data.external_loaders import load_spx_sector_weights
        from config.tickers import SPX_SECTOR_CONFIG as _SSC
        _weights = load_spx_sector_weights()
        _snap = build_sector_snapshot(ctx.df, _weights)
        _avail = available_sector_inputs(ctx.df, _weights)

        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Sector Rotation &amp; Breadth Monitor — inputs</div>",
            unsafe_allow_html=True,
        )
        sec_rows = []
        for key, cfg in _SSC.items():
            info = _avail["sectors"].get(key, {})
            sec_rows.append({
                "Sector": cfg["display_name"],
                "Ticker": cfg["ticker"],
                "First date": str(info.get("first_date", "—")),
                "Latest date": str(info.get("latest_date", "—")),
                "Obs": info.get("n_obs", 0),
                "Status": "Ready" if info.get("available") else "Missing",
            })
        st.dataframe(pd.DataFrame(sec_rows).style.map(_status_color, subset=["Status"]),
                     hide_index=True, use_container_width=True)
        st.caption(
            f"Sector-only common date: {_snap.get('sector_only_date', '—')} · "
            f"Relative-to-SPX common date: {_snap.get('relative_model_date', '—')} · "
            f"Weight date: {_snap.get('weight_date', '—')} · "
            f"Sector-only obs: {_snap.get('sector_only_obs', 0)} · "
            f"Relative obs: {_snap.get('relative_obs', 0)}"
        )

        # Weight audit
        st.markdown(
            "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "SPX_Sector_Weights audit</div>",
            unsafe_allow_html=True,
        )
        if _weights is not None and not _weights.empty:
            _raw_weights = load_spx_sector_weights(include_future=True)
            weight_cols_present = [
                cfg["weight_column"] for cfg in _SSC.values()
                if cfg["weight_column"] in _weights.columns
            ]
            missing_wcols = [
                cfg["weight_column"] for cfg in _SSC.values()
                if cfg["weight_column"] not in _weights.columns
            ]
            latest = (
                _weights[weight_cols_present].iloc[-1]
                if weight_cols_present else pd.Series(dtype=float)
            )
            latest_sum = float(latest.sum(min_count=1)) if len(latest) else float("nan")
            sums = (
                _weights[weight_cols_present].sum(axis=1, min_count=1)
                if weight_cols_present else pd.Series(dtype=float)
            )
            outside = sums[(sums - 100).abs() > WEIGHT_SUM_TOLERANCE]
            raw_rows = len(_raw_weights) if _raw_weights is not None else len(_weights)
            future_rows = max(0, raw_rows - len(_weights))
            status = "Out of tolerance" if len(outside) or missing_wcols else "OK"
            w_audit = pd.DataFrame([{
                "Sheet": "SPX_Sector_Weights",
                "Raw rows": raw_rows,
                "Eligible rows": len(_weights),
                "Future rows": future_rows,
                "First eligible date": str(_weights.index[0].date()),
                "Latest eligible date": str(_weights.index[-1].date()),
                "Latest weight sum (%)": f"{latest_sum:.2f}",
                "Valid sector cols": len(weight_cols_present),
                "Missing cols": ", ".join(missing_wcols) or "—",
                "Rows outside tolerance": len(outside),
                "Dates outside tolerance": ", ".join(
                    str(d.date()) for d in outside.index[:12]
                ) or "—",
                "Sum tolerance": f"±{WEIGHT_SUM_TOLERANCE}pp",
                "Status": status,
            }])
            st.dataframe(
                w_audit.style.map(_status_color, subset=["Status"]),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "Weights are not normalised by the application. Sector ETF proxy "
                "columns (XLC/XLY/XLP/XLE/XLV/XLI/XLB/XLRE/XLU) are excluded "
                "from the production sector model."
            )
        else:
            st.warning("SPX_Sector_Weights sheet is unavailable.")
    except Exception as exc:
        st.warning(
            f"Sector readiness table is unavailable because the model audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ── Sector Contribution Estimate audit ──
    try:
        from models.sector_contribution import build_sector_contribution_summary
        from data.external_loaders import load_spx_sector_weights as _load_sc_weights
        _sc_summary = build_sector_contribution_summary(
            ctx.df, _load_sc_weights(), horizons=(1, 5, 20, 63)
        )
        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Sector Contribution Estimate — reconciliation audit</div>",
            unsafe_allow_html=True,
        )
        if not _sc_summary.empty:
            _sc_display = _sc_summary.rename(columns={
                "horizon": "Window",
                "start_date": "Start date",
                "end_date": "End date",
                "weight_date": "Weight date",
                "weight_age_days": "Weight age (days)",
                "weight_sum_pct": "Weight sum (%)",
                "actual_spx_return_pct": "Actual SPX return (%)",
                "estimated_spx_return_pct": "Estimated return (%)",
                "residual_pp": "Residual (pp)",
                "status": "Status",
            })
            _sc_display["Window"] = _sc_display["Window"].map(lambda v: f"{int(v)}D")
            st.dataframe(
                _sc_display.style.format({
                    "Weight sum (%)": "{:.2f}",
                    "Actual SPX return (%)": "{:+.2f}",
                    "Estimated return (%)": "{:+.2f}",
                    "Residual (pp)": "{:+.3f}",
                }, na_rep="—").map(_status_color, subset=["Status"]),
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "Estimate = latest periodic weight available on or before the "
                "window start date × sector simple return. Weights are not "
                "normalised. Residual = actual SPX return − estimated return. "
                "This is not official attribution."
            )
        else:
            st.warning("Sector contribution reconciliation audit is unavailable.")
    except Exception as exc:
        st.warning(
            f"Sector contribution audit is unavailable because the model audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

    # ── SPX FY1 Earnings & Valuation audit ──
    try:
        from data.equity_earnings_loader import load_equity_earnings_data
        from models.earnings_valuation import (
            EPS_FIELD_METADATA, build_earnings_valuation_snapshot,
            build_global_earnings_overview,
        )
        _earn_data = load_equity_earnings_data()
        _earn_snap = build_earnings_valuation_snapshot(_earn_data)
        _earn_global = build_global_earnings_overview(_earn_data, horizon=13)
        st.markdown(
            "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "SPX FY1 Earnings &amp; Valuation — source and alignment audit</div>",
            unsafe_allow_html=True,
        )
        _earn_rows = pd.DataFrame([{
            "Model": "SPX FY1 Earnings & Valuation",
            "EPS field": EPS_FIELD_METADATA["field"],
            "Forecast override": EPS_FIELD_METADATA["forecast_period_override"],
            "EPS frequency": EPS_FIELD_METADATA["frequency"],
            "Common observations": _earn_snap.get("aligned_observations", 0),
            "First common date": str(_earn_snap.get("first_date") or "—"),
            "Latest common date": str(_earn_snap.get("model_date") or "—"),
            "Regression status": _earn_snap.get("regression_status", "—"),
            "Status": _earn_snap.get("status", "Missing data"),
        }])
        st.dataframe(
            _earn_rows.style.map(_status_color, subset=["Status"]),
            hide_index=True, use_container_width=True,
        )
        _ready_count = int((_earn_global["status"] == "Ready").sum()) if not _earn_global.empty else 0
        _missing_names = (
            _earn_global.loc[_earn_global["status"] != "Ready", "index"].tolist()
            if not _earn_global.empty else []
        )
        st.caption(
            f"Global exact-date overview: {_ready_count}/{len(_earn_global)} requested indices Ready. "
            f"Non-Ready: {', '.join(_missing_names) or 'none'}. "
            "China is explicitly requested as CSIA500 Index (CSI A500) and the additional "
            "US index as DJI Index. The existing XIN9I / FTSE China A50 series is not relabelled. "
            "No EPS or price values are forward-filled. The implied FY1 P/E is calculated "
            "as index level ÷ FY1 EPS; it is not a Bloomberg-supplied P/E field."
        )

        from models.sector_rotation import build_spx_dispersion_index
        _requested_rows = []
        _dspx_series = build_spx_dispersion_index(ctx.df)
        _dspx_present = not _dspx_series.empty
        _dspx_latest = float(_dspx_series.iloc[-1]) if _dspx_present else None
        _dspx_date = _dspx_series.index[-1].date() if _dspx_present else None

        def _earnings_requested_row(code, label, requested_ticker):
            row = _earn_global.loc[_earn_global["code"] == code]
            if row.empty:
                return {
                    "Requested series": label, "Bloomberg ticker": requested_ticker,
                    "Workbook ticker": "—", "Required workbook location": "Equity_Prices + Equity_EPS",
                    "Latest common date": "—", "Latest value": "—",
                    "Status": "Missing data", "Substitution used": "No",
                }
            item = row.iloc[0]
            return {
                "Requested series": label,
                "Bloomberg ticker": requested_ticker,
                "Workbook ticker": item.get("workbook_ticker") or "—",
                "Required workbook location": "Equity_Prices + Equity_EPS",
                "Latest common date": str(item.get("model_date") or "—"),
                "Latest value": (
                    f"Index {item.get('price'):,.2f} · FY1 EPS {item.get('eps_fy1'):,.2f} · "
                    f"P/E {item.get('fy1_pe'):.2f}x"
                    if item.get("status") == "Ready" else "—"
                ),
                "Status": "Available" if item.get("status") == "Ready" else item.get("status", "Missing data"),
                "Substitution used": "No",
            }

        _requested_rows.append({
            "Requested series": "Cboe S&P 500 Dispersion Index",
            "Bloomberg ticker": "DSPX INDEX",
            "Workbook ticker": "DSPX Index" if _dspx_present else "—",
            "Required workbook location": "Sheet1",
            "Latest common date": str(_dspx_date or "—"),
            "Latest value": f"{_dspx_latest:.2f}" if _dspx_present else "—",
            "Status": "Available" if _dspx_present else "Missing data",
            "Substitution used": "No",
        })
        _requested_rows.append(_earnings_requested_row(
            "CSI_A500", "CSI A500 cash index + FY1 EPS", "CSIA500 INDEX"
        ))
        _requested_rows.append(_earnings_requested_row(
            "DJI", "Dow Jones Industrial Average + FY1 EPS", "DJI INDEX"
        ))
        st.markdown(
            "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Requested reference-pack additions</div>",
            unsafe_allow_html=True,
        )
        st.dataframe(
            pd.DataFrame(_requested_rows).style.map(_status_color, subset=["Status"]),
            hide_index=True, use_container_width=True,
        )
    except Exception as exc:
        st.warning(
            "SPX earnings/valuation audit is unavailable because the audit failed. "
            f"({type(exc).__name__}: {str(exc)[:120]})"
        )

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
            "Weekly H.4.1 series (reserve balances / CB liquidity swaps) are observed on Wednesdays; "
            "the z-score is computed on those true observations and forward-"
            "filled at most 'Max ffill' business days.")

    render_section_footer(page)
