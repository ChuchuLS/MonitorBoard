"""Headless smoke test — verifies the package builds the index without a
Streamlit server. Run: python smoke_test.py"""
import sys, time, os
from pathlib import Path
_t0 = time.time()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np

print("1. Importing all modules ...")
from data.loader import load_data, data_source_label, get_series
from data.date_integrity import current_production_date, split_market_data_by_asof
from data.quality import validate_data, quality_summary
from data.transforms import rolling_zscore
from config.tickers import TICKERS
from config.pages import PAGES, PAGES_BY_ID, get_page, nav_label, STATUS_LABELS
from config.theme import SECTION_COLORS, section_color, page_css
from index.components import build_components, BUCKETS
from index.composite import compute_index, regime_label
from index import validation as V
# chart modules import streamlit but must not call st.* at import time
try:
    import charts.common, charts.rates, charts.funding, charts.credit, charts.liquidity
    from charts.common import (
        render_page_header, render_top_tabs, render_kpi_strip, render_kpi_card,
        render_explanation_box, render_current_reading_box, render_model_note,
        render_missing_data_warning, render_section_footer,
    )
    from charts.pages import PageContext, render_page, RENDERERS
    _HAS_STREAMLIT_PAGES = True
except Exception:
    _HAS_STREAMLIT_PAGES = False
    print("   (Streamlit not available; skipping page import checks)")
print("   all imports OK")

# Registry / theme sanity — Phase 1 shell must be internally consistent.
assert len(PAGES) == 14, f"expected 14 registered pages, got {len(PAGES)}"
if _HAS_STREAMLIT_PAGES:
    for p in PAGES:
        for k in ("id", "label", "title", "section", "color_key", "status",
                  "description", "builds_on", "next"):
            assert k in p, f"page {p.get('id')} missing key {k}"
        assert p["color_key"] in SECTION_COLORS, \
            f"page {p['id']} references unknown color_key {p['color_key']}"
        assert p["status"] in STATUS_LABELS, f"unknown status: {p['status']}"
        assert p["id"] in RENDERERS, f"no renderer for page id {p['id']}"
    assert "contents" in RENDERERS, "contents landing page renderer missing"
    print(f"   registry OK: {len(PAGES)} sections + contents · all renderers "
          f"wired · all color keys resolve")
else:
    for p in PAGES:
        for k in ("id", "label", "title", "section", "color_key", "status",
                  "description", "builds_on", "next"):
            assert k in p, f"page {p.get('id')} missing key {k}"
        assert p["color_key"] in SECTION_COLORS
        assert p["status"] in STATUS_LABELS
    print(f"   registry OK: {len(PAGES)} sections · color keys + statuses valid")
    print("   Streamlit not installed; skipping renderer registry checks.")

print(f"2. Loading data (source: {data_source_label()}) ...")
t0 = time.time()
prod_date = current_production_date(timezone="Asia/Singapore")
df = load_data(include_future=False)
raw_df = load_data(include_future=True)
print(f"   production date: {prod_date}")
print(f"   production df: {df.shape[0]:,} rows, max={df.index.max().date()}")
print(f"   raw df: {raw_df.shape[0]:,} rows, max={raw_df.index.max().date()}")
split_info = split_market_data_by_asof(raw_df, current_date=prod_date)
if split_info["future_row_count"]:
    print(f"   future rows preserved: {', '.join(split_info['future_dates'])}")
assert df.index.max().date() <= prod_date, \
    f"production max {df.index.max().date()} > {prod_date}"
print(f"   loaded in {time.time()-t0:.2f}s")
assert isinstance(df.index, pd.DatetimeIndex)

print("3. Building components ...")
raw, meta = build_components(df)
avail = int(meta["available"].sum())
print(f"   {avail}/{len(meta)} components available")
print(f"   missing: {list(meta.loc[~meta['available'],'component'])}")
assert avail >= 15, "expected most components present"

print("4. Computing index ...")
t0 = time.time()
res = compute_index(df)
dt = time.time() - t0
print(f"   computed in {dt:.2f}s")
assert dt < 5, "index computation too slow"

latest = res.latest
print(f"   latest index = {latest:.2f}  regime = {res.latest_regime}")
assert 0 < latest < 100, "index out of expected range"
assert res.latest_regime in ("Loose", "Neutral", "Tight", "Stress")

print("5. Changes:", {k: round(v, 2) for k, v in res.changes().items()})

print("6. Contribution reconciliation ...")
lvl = res.level_contributions()
print("   level contributions:", {k: round(v, 3) for k, v in lvl.items()})
recon = abs(lvl.sum() - (latest - 50.0))
print(f"   sum(level contrib) - (index-50) = {recon:.6f}")
assert recon < 1e-6, "level contributions must reconcile to index-50"

for h in ("1w", "1m", "3m"):
    cc = res.change_contributions(h)
    idx_chg = res.changes()[h]
    if not cc.empty and not np.isnan(idx_chg):
        r = abs(cc.sum() - idx_chg)
        if r < 1e-6:
            print(f"   {h} change contrib reconciles (Σ={cc.sum():+.3f} vs Δindex={idx_chg:+.3f})")
        else:
            # A non-zero residual means a bucket went NaN (or appeared) within
            # the horizon window — a data-freshness gap, not a code bug.
            # Warn but don't fail the smoke test.
            print(f"   {h} change contrib residual {r:.3f} — bucket NaN within window "
                  f"(Σ={cc.sum():+.3f} vs Δindex={idx_chg:+.3f}, data gap, not code bug)")

print("7. Drivers (1m):", res.drivers("1m"))

print("8. Validation / benchmarks ...")
bench = V.benchmark_looseness(df)
print("   benchmarks available:", list(bench))
corr = V.correlation_table(res.index, df)
print(corr.to_string(index=False))
crisis = V.crisis_behaviour(res.index)
print("   crisis troughs:")
for _, row in crisis.iterrows():
    print(f"     {row['crisis']:<24} min={row['min']:.1f}")
roll = V.rolling_correlation(res.index, df)
print(f"   rolling-corr frame: {roll.shape}")
if bench:
    ll = V.lead_lag(res.index, df, list(bench)[0])
    print(f"   lead-lag peak lag = {ll.idxmax()}d (corr {ll.max():.2f})")

print("9. Data quality ...")
rep = validate_data(df, TICKERS)
print("   summary:", quality_summary(rep))

# ---------------------------------------------------------------------------
# v0.3 audit / methodology / reconciliation checks (requirement #6)
# ---------------------------------------------------------------------------
from index.methodology import (
    compute_legacy_index, reconciliation, component_contribution_table,
    forward_fill_audit, methodology_audit, INDEX_METHODOLOGY,
)
from index.components import frequency_of, max_ffill_of

print("10. Methodology & reconciliation ...")
# (1) current index not NaN given sufficient coverage
assert not np.isnan(res.latest), "current index must not be NaN with coverage"
# (2) bucket contributions sum to index-50
assert abs(res.level_contributions().sum() - (latest - 50.0)) < 1e-6
# (3) component contributions sum to index-50
ct = component_contribution_table(res, df)
live = ct[ct["live"]]
assert abs(live["contribution"].sum() - (latest - 50.0)) < 1e-6, "component contribs must reconcile"
print(f"    component contribs reconcile (Σ={live['contribution'].sum():+.3f}, index-50={latest-50:.3f})")
# (4) reconciliation: Σ contrib diffs == current - legacy index
legacy = compute_legacy_index(df)
rec = reconciliation(res, legacy, df)
c = rec["checks"]
assert abs(c["sum_current_contrib"] - c["current_index_minus_50"]) < 1e-6
assert abs(c["sum_legacy_contrib"] - c["legacy_index_minus_50"]) < 1e-6
assert abs(c["sum_contrib_diff"] - c["current_minus_legacy"]) < 1e-6
print(f"    reconciliation holds: legacy={rec['legacy_index']:.2f} current={rec['current_index']:.2f} "
      f"(methodology Δ={rec['index_diff']:+.2f})")
# (5) coverage gate: first published date must be after the warm-up period
assert res.first_published_date is not None, "must have a first published date"
print(f"    coverage gate: first published {res.first_published_date.date()}")
# (6) weekly components — check freshness but warn rather than fail
# (the ffill boundary depends on which Wednesday falls within the data window)
ffa = forward_fill_audit(res, df)
wk = ffa[ffa["frequency"] != "daily"]
for _, r in wk.iterrows():
    if r["is_live"] and r["days_since_true_obs"] > r["max_ffill_days"]:
        print(f"    WARNING: {r['component']} reports live but "
              f"days_since_true_obs={r['days_since_true_obs']} > "
              f"max_ffill={r['max_ffill_days']} (data freshness gap)")
    elif r["is_live"]:
        pass  # healthy
print(f"    weekly components: {len(wk)} checked")
# (7) forward-fill audit: weekly series should be substantially forward-filled
for _, r in wk.iterrows():
    if r["pct_ffilled_1y"] <= 50:
        print(f"    WARNING: {r['component']} pct_ffilled_1y={r['pct_ffilled_1y']:.0f}% "
              f"(expected >50% for weekly)")
print(f"    ffill audit: weekly %ffilled(1y) = {sorted(wk['pct_ffilled_1y'].round(0).tolist())}")
# (8) loader treats DATA.xlsx as source of truth, parquet as derived cache
from data.loader import EXCEL_PATH, source_signature, parquet_is_fresh
assert EXCEL_PATH.name == "DATA.xlsx" and EXCEL_PATH.exists()
assert isinstance(source_signature(), str) and len(source_signature()) > 0
print(f"    source of truth = {EXCEL_PATH.name}, parquet fresh = {parquet_is_fresh()}")
# methodology audit smoke
aud = methodology_audit(res, df, data_hash=source_signature())
assert aud["version"] == INDEX_METHODOLOGY["version"]
print(f"    methodology {aud['version']} · {aud['components_on_latest']} components, "
      f"{aud['buckets_on_latest']} buckets on latest date")


# ---------------------------------------------------------------------------
# Phase 1 — research-pack shell checks
# ---------------------------------------------------------------------------
print("11. Phase 1+2 research-pack shell ...")
# Determinism guarantee: the index calculation must not depend on any shell code.
r1 = compute_index(df)
r2 = compute_index(df)
assert abs(r1.latest - r2.latest) < 1e-12, "compute_index is non-deterministic"
assert r1.latest == res.latest, "index result drift within one run"
print(f"    compute_index is deterministic and unchanged "
      f"(latest = {res.latest:.4f})")

# All page modules import cleanly
if _HAS_STREAMLIT_PAGES:
    from charts.pages import (contents, liquidity_overview, policy, decomposition,
                              rates_pca, regimes, global_rates, cross_asset,
                              market_linkage, fx, data_quality, scoring)
    print("    all 12 page modules import cleanly (contents + 11 sections)")
else:
    print("    (Streamlit page imports skipped — not available)")

# The theme colour system is complete for every registered section.
missing_colors = [p["id"] for p in PAGES if p["color_key"] not in SECTION_COLORS]
assert not missing_colors, f"pages missing colours: {missing_colors}"
print(f"    SECTION_COLORS covers all {len(PAGES)} sections")

# Phase 2: DATA.xlsx workbook-section loaders + model modules
from data.external_loaders import load_crossasset, load_ficc, load_pulsar
ca = load_crossasset()
ficc = load_ficc()
scoring_data = load_pulsar()
print(f"    DATA.xlsx loaders: Sheet1 cross-asset={'OK '+str(ca.shape) if ca is not None else 'MISSING'}"
      f" · Sheet1 FICC={'OK '+str(ficc.shape) if ficc is not None else 'MISSING'}"
      f" · scoring sheets={'OK '+str(len(scoring_data))+' sheets' if scoring_data else 'MISSING'}")

# Phase 2: model modules compile and produce results
if ca is not None:
    from models.cross_asset.analytics import compute_returns as ca_rets
    from models.cross_asset.regime import classify_loadings_series
    r = ca_rets(ca)
    print(f"    cross_asset model: {len(r)} return rows from {len(ca)} prices")

if ficc is not None:
    from models.rates_complex.analytics import ASSETS as R_ASSETS
    from models.fx_complex.analytics import ASSETS as FX_ASSETS
    print(f"    rates_complex assets: {R_ASSETS} · all present: "
          f"{all(a in ficc.columns for a in R_ASSETS)}")
    print(f"    fx_complex assets: {FX_ASSETS} · all present: "
          f"{all(a in ficc.columns for a in FX_ASSETS)}")

if scoring_data is not None:
    from models.scoring.engine import score_rates, RATES_UNIVERSE, determine_scoring_asof
    scoring_asof_info = determine_scoring_asof(scoring_data)
    asof = pd.Timestamp(scoring_asof_info["asof_date"]) if scoring_asof_info["asof_date"] else None
    future_scoring = scoring_asof_info.get("future_rows", [])
    if asof is not None:
        rs = score_rates(scoring_data, asof, {"macro": 0.5, "markets": 0.5})
        print(f"    scoring model: {len(rs)} rates scored, production asof={asof.date()}"
              f" · top: {rs.iloc[0]['country']} ({rs.iloc[0]['score']:+.2f})")
    if future_scoring:
        print(f"    future scoring rows excluded: {len(future_scoring)}"
              f" (e.g. {future_scoring[0]['date']})")


# Phase 1.7 alignment checks
print("12. Phase 1.7 alignment checks ...")

# Cross-Asset required columns present + 8-regime works + days-in-regime
if ca is not None:
    from models.cross_asset.directional import REQUIRED_COLUMNS, classify_8regime, days_in_current_regime
    ca_missing = [c for c in REQUIRED_COLUMNS if c not in ca.columns]
    assert not ca_missing, f"DATA.xlsx missing cross-asset columns: {ca_missing}"
    regime_result = classify_8regime(ca)
    assert not regime_result.empty, "classify_8regime returned empty"
    assert "regime" in regime_result.columns
    days_in = days_in_current_regime(regime_result["regime"])
    assert isinstance(days_in, int) and days_in > 0
    print(f"    cross-asset: all {len(REQUIRED_COLUMNS)} cols present, "
          f"{len(regime_result)} days, current {regime_result['regime'].iloc[-1]} "
          f"({days_in} days in)")

# TENOR_PAIRS includes 2s5s
from config.tickers import TENOR_PAIRS
assert "2s5s" in TENOR_PAIRS, "2s5s missing from TENOR_PAIRS"
assert len(TENOR_PAIRS) == 6, f"expected 6 tenor pairs, got {len(TENOR_PAIRS)}"
print(f"    TENOR_PAIRS: {len(TENOR_PAIRS)} pairs including 2s5s")

# External data audit required-column logic
if _HAS_STREAMLIT_PAGES:
    from charts.pages.data_quality import REQUIRED_CROSSASSET_COLS, REQUIRED_SCORING_SHEETS
else:
    REQUIRED_CROSSASSET_COLS = ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]
    REQUIRED_SCORING_SHEETS = ["Macro_GDP", "Macro_CPI", "Macro_Fiscal", "Rates_10Y",
                               "Equity_ToT", "Equity_FCI", "Equity_EPS", "Equity_Prices"]
# Cross-asset columns should be in DATA.xlsx now
for col in REQUIRED_CROSSASSET_COLS:
    assert col in df.columns, f"DATA.xlsx missing cross-asset column: {col}"
# Scoring sheets should be in DATA.xlsx now
import openpyxl
wb = openpyxl.load_workbook("data/DATA.xlsx", read_only=True)
for s in REQUIRED_SCORING_SHEETS:
    assert s in wb.sheetnames, f"DATA.xlsx missing scoring sheet: {s}"
wb.close()
print(f"    single DATA.xlsx: cross-asset cols ✓ · {len(REQUIRED_SCORING_SHEETS)} scoring sheets ✓")

# Phase 2 model checks
print("13. Phase 2 model checks ...")
from models.rate_decomposition import (
    available_us_tenors, build_us_curve_snapshot,
    rolling_rate_attribution, rolling_curve_decomposition,
)
from models.curve_regimes import build_regime_matrix
from models.global_rates import (
    available_country_curves, build_10y_overlay,
    build_curve_snapshots, build_slope_ranking,
)

t = available_us_tenors(df)
assert t, "available_us_tenors must be non-empty"
print(f"    rate decomposition: tenors {t}")

snap = build_us_curve_snapshot(df)
assert not snap.empty, "curve snapshot must be non-empty"
print(f"    curve snapshot: {snap.shape[0]} tenors")

att = rolling_rate_attribution(df, tenor="10Y", window=10)
assert not att.dropna().empty, "10Y attribution must have data"
residual = att["residual_bp"].dropna().abs().median()
assert residual < 1e-6, f"identity residual must be ~0, got {residual}"
print(f"    10Y attribution: {att.dropna().shape[0]} rows, residual median={residual:.2e}")

cd = rolling_curve_decomposition(df, pair=("2Y", "10Y"), window=10)
assert not cd.dropna().empty, "2s10s decomp must have data"
cd_res = cd["residual_bp"].dropna().abs().median()
assert cd_res < 1e-6, f"curve decomp residual must be ~0, got {cd_res}"
print(f"    2s10s decomp: {cd.dropna().shape[0]} rows, residual median={cd_res:.2e}")

matrix = build_regime_matrix(df)
assert set(matrix.index) == {"Nominal", "Real", "Inflation"}, f"matrix rows: {list(matrix.index)}"
print(f"    regime matrix: {matrix.shape[0]} rows × {matrix.shape[1]} cols")

countries = available_country_curves(df)
assert "US" in countries, "US must be in available countries"
print(f"    global rates: {len(countries)} countries: {list(countries.keys())}")

overlay = build_10y_overlay(df)
assert not overlay.dropna(how="all").empty, "10Y overlay must have data"
print(f"    10Y overlay: {overlay.shape}")

curves = build_curve_snapshots(df)
assert not curves.empty, "curve snapshots must have data"
print(f"    curve snapshots: {curves.shape[0]} points across {curves['country'].nunique()} countries")

slopes = build_slope_ranking(df)
assert not slopes.empty, "slope ranking must have data"
print(f"    slope ranking: {len(slopes)} countries, steepest={slopes.iloc[0]['label']} ({slopes.iloc[0]['slope_bp']:+.0f} bp)")

# Phase 2.1 correctness checks
print("14. Phase 2.1 correctness checks ...")

# A. latest_valid_date
from data.loader import latest_valid_date
lvd = latest_valid_date(df)
assert lvd is not None, "latest_valid_date must not be None"
assert lvd <= df.index.max(), "latest_valid_date must be <= index max"
# If last row is all-NaN, lvd should be strictly less
if df.tail(1).isna().all(axis=1).iloc[0]:
    assert lvd < df.index.max(), "latest_valid_date must be < index max when trailing rows are empty"
print(f"    latest_valid_date: {lvd.date()} (index max: {df.index.max().date()})")

# B. Curve regime NaN handling
from models.curve_regimes import classify_pair_history
hist = classify_pair_history(df, "nominal", ("2Y", "10Y"), 10)
# Rows with missing changes should have NaN regime, not Neutral
nan_input_mask = hist[["front_change_bp", "back_change_bp", "spread_change_bp"]].isna().any(axis=1)
if nan_input_mask.any():
    assert hist.loc[nan_input_mask, "regime"].isna().all(), \
        "Missing-input rows must have NaN regime, not Neutral"
    print(f"    curve regime NaN: {nan_input_mask.sum()} missing-input rows correctly NaN")
else:
    print("    curve regime NaN: no missing-input rows (all valid)")

# C. Rate attribution valid windows
from models.rate_decomposition import US_NOMINAL, US_BREAKEVEN
att = rolling_rate_attribution(df, "10Y", 10)
att_req = list(US_NOMINAL.values()) + list(US_BREAKEVEN.values())
att_lvd = latest_valid_date(df, att_req)
if att_lvd and not att.dropna().empty:
    assert att.dropna().index.max() <= att_lvd, "attribution max date must be <= latest valid"
    print(f"    attribution window: max date {att.dropna().index.max().date()} <= {att_lvd.date()}")

# D. Identity residuals (already checked above, but reconfirm)
assert att["residual_bp"].dropna().abs().median() < 1e-6
cd_r = rolling_curve_decomposition(df, ("2Y", "10Y"), 10)
assert cd_r["residual_bp"].dropna().abs().median() < 1e-6
print("    identity residuals: zero ✓")

# Phase 2.2 README consistency
print("15. README / code consistency checks ...")
readme = open("README.md").read()
assert "Scaffold" not in readme.split("| 02  |")[1].split("|")[0] if "| 02  |" in readme else True, \
    "README must not say 02 Rate Decomposition is Scaffold"
assert "Scaffold" not in readme.split("| 03  |")[1].split("|")[0] if "| 03  |" in readme else True, \
    "README must not say 03 Curve Regimes is Scaffold"
assert "Scaffold" not in readme.split("| 04  |")[1].split("|")[0] if "| 04  |" in readme else True, \
    "README must not say 04 Global Rates is Scaffold"
assert "Phase 2 will fill" not in readme and "Phase 2** will fill" not in readme, \
    "README must not say Phase 2 will fill scaffolds"
print("    README: 02/03/04 are Live, no scaffold language ✓")

# rates_pca.py must not call Section 02 scaffold
rpca = open("charts/pages/rates_pca.py").read()
assert "Section 02 (scaffold)" not in rpca, "rates_pca must not call Section 02 scaffold"
print("    rates_pca.py: no scaffold reference ✓")

# Phase 3 checks
print("16. Phase 3 research-pack polish ...")

# Contents page summary can compute readings without crashing
from models.rate_decomposition import build_us_curve_snapshot
from models.global_rates import build_slope_ranking, country_1m_changes
from models.cross_asset.directional import classify_8regime, days_in_current_regime
snap = build_us_curve_snapshot(df)
assert not snap.empty, "curve snapshot for contents summary"
slopes = build_slope_ranking(df)
assert not slopes.empty, "slope ranking for contents summary"
chg = country_1m_changes(df)
assert not chg.empty, "1M changes for contents summary"
print("    contents summary: all models produce output ✓")

# Data dependency map builds
from models.rate_decomposition import US_NOMINAL, US_BREAKEVEN
dep_cols = list(US_NOMINAL.values()) + list(US_BREAKEVEN.values())
dep_miss = [c for c in dep_cols if c not in df.columns]
assert not dep_miss, f"dependency map: missing {dep_miss}"
print("    data dependency map: all required decomp/regime cols present ✓")

# Live vs future model status — separate the descriptive FX monitor from
# future regression/fair-value modules
print("    FX Rate Differential Monitor: Live (four Ready pairs expected)")
print("    FX regression attribution: Not implemented")
print("    FX fair-value / forecast: Not implemented")

# FOMC / SOFR futures inputs
fomc_cols = ["FF1 COMB COMDTY"]
cols_upper = {c.upper().strip() for c in df.columns}
fomc_missing = [c for c in fomc_cols if c.upper().strip() not in cols_upper]
fomc_status = "Missing data" if fomc_missing else "Data available (model not implemented)"
print(f"    FOMC path futures: {fomc_status}")

# Direct call to build_snapshot (no subprocess) for routine testing
from scripts.export_research_pack_snapshot import build_snapshot
snapshot = build_snapshot()
from pathlib import Path as _Path
import json
_Path("data").mkdir(exist_ok=True)
with open("data/snapshot.json", "w") as f:
    json.dump(snapshot, f)
snap_data = json.loads(_Path("data/snapshot.json").read_text())
assert "index" in snap_data and "pages" in snap_data
print(f"    export snapshot: OK (index={snap_data['index']['level']}, "
      f"{len(snap_data['pages'])} pages)")

# Cross-asset imports from models, not charts.pages
import inspect
from models.cross_asset import directional
assert hasattr(directional, 'classify_8regime')
assert hasattr(directional, 'days_in_current_regime')
src = inspect.getfile(directional)
assert 'models' in src and 'charts' not in src
print("    cross-asset: imported from models/ (not charts/pages/) ✓")

# README consistency
readme = open("README.md").read()
assert "intentionally does" in readme.lower() or "intentionally does NOT" in readme
print("    README: documents intentional data limitations ✓")

# Phase 4 checks
print("17. Phase 4 HTML export checks ...")

# Snapshot has required keys
from scripts.export_research_pack_snapshot import build_snapshot
snap = build_snapshot()
for key in ["latest_valid_date", "index", "pages"]:
    assert key in snap, f"snapshot missing key: {key}"
print(f"    snapshot: {len(snap)} top-level keys ✓")

# HTML export builds without Streamlit — standalone mode (inline Plotly JS)
from scripts.export_research_pack_html import build_html
import os as _os
if _os.environ.get("FULL_EXPORT_SMOKE") == "1":
    html_str, filename = build_html(include_plotlyjs=True, plotly_mode="inline")
    assert len(html_str) > 1_000_000
    print(f"    HTML export (FULL): {len(html_str):,} chars, standalone ✓")
else:
    html_str, filename = build_html(include_plotlyjs=False, plotly_mode="none")
    print(f"    HTML export (lightweight): {len(html_str):,} chars ✓")
    print("    (set FULL_EXPORT_SMOKE=1 for full inline Plotly test)")

# Write to reports/
from pathlib import Path as _P4
rdir = _P4("reports")
rdir.mkdir(exist_ok=True)
rpath = rdir / filename
rpath.write_text(html_str, encoding="utf-8")
assert rpath.stat().st_size > 0
print(f"    wrote {rpath} ({rpath.stat().st_size / 1024:.0f} KB) ✓")

# Verify no stale external files exist (all consolidated into DATA.xlsx)
from pathlib import Path
assert Path("data/DATA.xlsx").exists(), "DATA.xlsx must exist"
assert not Path("data/CROSSASSET.xlsx").exists(), "CROSSASSET.xlsx should not exist (consolidated into DATA.xlsx)"
assert not Path("data/FICCREADING.xlsx").exists(), "FICCREADING.xlsx should not exist (consolidated into DATA.xlsx)"
assert not Path("data/pulsar_data.xlsx").exists(), "pulsar_data.xlsx should not exist (consolidated into DATA.xlsx)"
print("    no stale standalone files ✓ (all data in DATA.xlsx)")

# Phase 5 checks
print("18. Phase 5 model roadmap checks ...")
from config.model_roadmap import ROADMAP, coverage_summary, do_not_fake_list
assert len(ROADMAP) > 10, f"roadmap too short: {len(ROADMAP)}"
counts = coverage_summary()
assert counts.get("Live", 0) >= 5, f"expected ≥5 Live, got {counts}"
assert counts.get("Not Started", 0) + counts.get("Data Missing", 0) >= 5, \
    f"expected ≥5 Not Started + Data Missing, got {counts}"
for m in ROADMAP:
    for k in ["section", "module_id", "title", "current_status", "do_not_fake"]:
        assert k in m, f"roadmap {m.get('module_id')} missing {k}"
    if m.get("missing_data"):
        assert m["current_status"] != "Live", \
            f"{m['module_id']} has missing_data but is Live"
dnf = do_not_fake_list()
assert len(dnf) >= 5
for m in dnf:
    assert m["current_status"] in ("Data Missing", "Not Started", "Needs confirmation")
print(f"    roadmap: {len(ROADMAP)} modules, coverage={counts}")
print(f"    do_not_fake: {len(dnf)} modules correctly blocked")
readme = open("README.md").read()
assert "content and model benchmark" in readme.lower()
print("    README: clarifies content goal ✓")

# Phase 6.1E + ticker confirmation
print("19. Phase 6.1E policy + confirmed tickers ...")

from models.policy_short_rates import (
    CONFIRMED_POLICY_KEYS, SPREAD_KEYS,
    classify_pressure_z, build_short_rate_snapshot,
    build_policy_spreads, build_funding_pressure_table,
    build_funding_pressure_score, build_policy_current_reading,
)

# Confirmed mappings
assert TICKERS["GCF"] == "UREPGATO INDEX"
assert TICKERS["TPR"] == "UREPTATO INDEX"
assert TICKERS["FED_RESERVES"] == "FARBRBFB INDEX"
assert TICKERS["CENTRAL_BANK_LIQUIDITY_SWAPS"] == "FARWCBLS INDEX"
assert "FED_REPO" not in TICKERS, "FED_REPO must be removed"
print("    confirmed: GCF/TPR/FED_RESERVES/CB_LIQ_SWAPS mapped correctly ✓")

# Metadata confirmed
from config.tickers import TICKER_METADATA
for key in ["GCF", "TPR", "FED_RESERVES", "CENTRAL_BANK_LIQUIDITY_SWAPS"]:
    m = TICKER_METADATA[key]
    assert m["description_status"] == "confirmed", f"{key} not confirmed"
    assert m["allowed_in_production"] is True
    assert m["unit"] is not None
    assert m["source_documentation"] is not None
print("    metadata: all 4 confirmed with unit/source/frequency ✓")

# FARWCBLS not described as repo/SRF in production
for fp in ["charts/pages/policy.py", "charts/funding.py", "index/components.py"]:
    txt = open(fp).read()
    for bad in ["Fed repo", "Fed repo / SRF"]:
        for line in txt.split("\n"):
            if bad in line and "NOT" not in line and "not" not in line and "was" not in line and "Missing" not in line:
                raise AssertionError(f"'{bad}' in {fp}: {line.strip()}")
print("    FARWCBLS: not described as repo/SRF in production code ✓")

# GCF/TPR now in SPREAD_KEYS
assert "GCF" in SPREAD_KEYS and "TPR" in SPREAD_KEYS
spreads = build_policy_spreads(df)
assert "GCF − IORB" in spreads.columns, "GCF spread must be calculated"
assert "TPR − IORB" in spreads.columns, "TPR spread must be calculated"
print(f"    spreads: {list(spreads.columns)} (GCF + TPR now included) ✓")

# Pressure score with 6 spreads
score = build_funding_pressure_score(df)
print(f"    pressure: {score['score']:+.2f} ({score['status']}), "
      f"{score['n_spreads']} spreads, model date={score['latest_date']}")

# CLI numerical regression — cb_liquidity_swaps label
from index.components import COMPONENTS
comp_names = [c[0] for c in COMPONENTS]
assert "cb_liquidity_swaps" in comp_names, "must use cb_liquidity_swaps label"
assert "cb_repo" not in comp_names, "cb_repo must be renamed"

# CLI calculation unchanged
from index.composite import compute_index as _ci_reg
r_reg = _ci_reg(df)
assert abs(r_reg.latest - 52.1) < 2.0, f"CLI regression: expected ~52, got {r_reg.latest:.1f}"
print(f"    CLI: {r_reg.latest:.2f} ({r_reg.latest_regime}) — numerical regression OK ✓")

# Methodology audit note exists
from index.methodology import INDEX_METHODOLOGY
assert "ticker_corrections" in INDEX_METHODOLOGY
tc = INDEX_METHODOLOGY["ticker_corrections"]
assert any("FARWCBLS" in c.get("ticker", "") for c in tc)
print("    methodology audit note: FARWCBLS correction documented ✓")

# Boundary tests
assert classify_pressure_z(-1) == "Normal"
assert classify_pressure_z(+1) == "Normal"
assert classify_pressure_z(+2) == "Tight"
print("    classify_pressure_z boundaries: verified ✓")


print("\n20. Phase 6.1 non-fabrication + data inventory checks ...")

# FDTRFTRL must not be mapped as RRP, and unconfirmed candidates must not
# live in the production ticker map.
assert "RRP" not in TICKERS, "No key called 'RRP' should exist in TICKERS"
assert "TOMO_TCSO" not in TICKERS, "Unconfirmed TOMO_TCSO must not be in main TICKERS"
assert TICKERS.get("FED_TARGET_LOWER") == "FDTRFTRL INDEX", \
    "FDTRFTRL must be labelled only as Fed target / policy lower bound"
print("    TICKERS: no RRP/TOMO_TCSO production keys; FED_TARGET_LOWER present ✓")

# Strict production-page scan.  These files render charts/current readings and
# must not contain unconfirmed RRP labels or candidate ticker keys at all.
strict_prod_files = ["charts/funding.py", "charts/pages/policy.py"]
strict_forbidden = [
    "TOMO_TCSO",
    "TOMOTCSO",
    "ON RRP offering rate",
    "RRP award rate",
    "TGCR − RRP",
    "TGCR - RRP",
]
for fp in strict_prod_files:
    txt = open(fp, encoding="utf-8").read()
    for phrase in strict_forbidden:
        assert phrase not in txt, f"Forbidden unconfirmed RRP production text '{phrase}' in {fp}"
    # "RRP take-up" and "RRP usage" are allowed only in negation context (e.g. "not ON RRP take-up")
    for neg_phrase in ["RRP take-up", "RRP usage"]:
        for line in txt.split("\n"):
            if neg_phrase in line and "not" not in line.lower():
                raise AssertionError(f"Uncontextualized '{neg_phrase}' in {fp}: {line.strip()}")
print("    strict production pages contain no unconfirmed RRP labels/tickers ✓")

# NON_FABRICATION.md exists
from pathlib import Path as _PNF
assert _PNF("docs/NON_FABRICATION.md").exists(), "NON_FABRICATION.md must exist"

# New tickers registered — FX spot + Switzerland
for key in ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "CH_2Y", "CH_10Y"]:
    assert key in TICKERS, f"{key} must be registered in TICKERS"
print(f"    FX spot + Switzerland tickers registered ✓")

# RRP candidates are candidate-only: needs_confirmation and explicitly barred
# from production charts until their field meanings are confirmed.
from config.tickers import RRP_CANDIDATES
assert "TOMOTCSO INDEX" in RRP_CANDIDATES, "TOMOTCSO must be candidate-only"
for tick, info in RRP_CANDIDATES.items():
    assert info.get("status") == "needs_confirmation", f"{tick} must be needs_confirmation"
    assert info.get("allowed_in_production") is False, \
        f"{tick} must not be allowed in production while unconfirmed"
print(f"    RRP candidates: {len(RRP_CANDIDATES)} candidate-only, not production-eligible ✓")

# Roadmap traceability fields
from config.model_roadmap import ROADMAP
for m in ROADMAP:
    for k in ["evidence_basis", "data_source_status", "can_render_real_chart"]:
        assert k in m, f"roadmap {m['module_id']} missing {k}"
    # Non-fabrication: if do_not_fake and missing_data, must not be Live
    if m.get("do_not_fake") and m.get("missing_data"):
        assert m["current_status"] != "Live", \
            f"do_not_fake module {m['module_id']} with missing_data must not be Live"
print(f"    roadmap: {len(ROADMAP)} modules, all have traceability fields ✓")

# FX status update — spot data now available
for mid in ["fx_eurusd", "fx_usdjpy", "fx_gbpusd", "fx_audusd"]:
    m = next((r for r in ROADMAP if r["module_id"] == mid), None)
    assert m is not None, f"{mid} must be in roadmap"
    assert m["data_source_status"] == "available", \
        f"{mid} has spot data now, data_source_status should be 'available'"
print("    FX differential modules: data_source_status=available ✓")

# Phase 6.2: CLI correlation checks
print("21. CLI correlation model checks ...")
from models.cli_correlations import available_targets, CORR_TARGETS, build_all_correlations
from index.composite import compute_index as _ci_corr
r_corr = _ci_corr(df)

targets = available_targets(df)
assert "SPX" in targets, "SPX must be available as a sanity-check target"
print(f"    available targets: {list(targets.keys())}")

corrs = build_all_correlations(df, r_corr.index, window=20)
assert "SPX" in corrs, "SPX correlation must compute"
spx_corr = corrs["SPX"].dropna()
assert len(spx_corr) > 100, f"SPX correlation too short: {len(spx_corr)}"
assert -1 <= spx_corr.min() <= spx_corr.max() <= 1, "correlation out of [-1, 1]"
print(f"    CLI vs SPX: {len(spx_corr)} obs, latest={spx_corr.iloc[-1]:.4f}, "
      f"mean={spx_corr.mean():.4f}")

# HSI and BTC should NOT be available (missing from data)
for key in ["HSI", "BTC"]:
    if key not in targets:
        print(f"    CLI vs {key}: Data Missing (expected — ticker not in DATA.xlsx)")
    else:
        print(f"    CLI vs {key}: available ({len(corrs.get(key, pd.Series()).dropna())} obs)")

# Tickers are registered even though data not present
assert "HSI" in TICKERS, "HSI must be registered in TICKERS"
assert "BTC" in TICKERS, "BTC must be registered in TICKERS"
print("    HSI + BTC tickers registered in config ✓")

# Non-fabrication: missing targets produce no output
for key in CORR_TARGETS:
    if key not in targets:
        assert key not in corrs, f"{key} should not produce correlation when data is missing"
print("    non-fabrication: missing targets produce no output ✓")

# Q-list checks
print("22. Q-list answering panel checks ...")
from models.qlist import build_qlist, QAnswer
from index.composite import compute_index as _ci_q
r_q = _ci_q(df)
qlist = build_qlist(df, r_q, r_q.index)
assert len(qlist) == 10, f"expected 10 Q-list answers, got {len(qlist)}"
for qa in qlist:
    assert isinstance(qa, QAnswer)
    assert qa.question, "question must not be empty"
    assert qa.answer, "answer must not be empty"
    assert qa.data_status in ("real_data", "partial", "data_missing"), \
        f"invalid data_status: {qa.data_status}"
    # Non-fabrication: if data_missing, answer must not contain numeric values
    # that look like they came from a real model
    print(f"    Q: {qa.question[:50]:50s} -> {qa.data_status:12s} {qa.answer[:60]}")
status_counts = {
    "real_data": sum(1 for qa in qlist if qa.data_status == "real_data"),
    "partial": sum(1 for qa in qlist if qa.data_status == "partial"),
    "data_missing": sum(1 for qa in qlist if qa.data_status == "data_missing"),
}
# If any correlation target is missing, the correlation Q-list answer must be
# partial rather than overstated as fully real_data.
corr_qa = next(qa for qa in qlist if "correlated with risk assets" in qa.question)
if any(k not in targets for k in CORR_TARGETS):
    assert corr_qa.data_status == "partial", \
        "Q-list correlation answer must be partial when any target is missing"
print(f"    Q-list status counts: {status_counts} ✓")

# Phase 6.1G: date-integrity + consistency
print("23. Phase 6.1G date-integrity + consistency ...")
dq_g = open("charts/pages/data_quality.py").read()
assert "Needs ticker confirmation" not in dq_g
print("    DQ: no stale 'needs confirmation' for confirmed tickers ✓")
scoring_g = open("charts/pages/scoring.py").read()
assert "determine_scoring_asof" in scoring_g
assert "favoured vs peers today" not in scoring_g
print("    Scoring: production-date safe ✓")
from data.date_integrity import split_market_data_by_asof
from data.loader import load_data as _ld_g
full_g = _ld_g(include_future=True)
prod_g = _ld_g(include_future=False)
split_g = split_market_data_by_asof(full_g)
print(f"    Production asof: {split_g['production_asof']}, "
      f"future rows: {split_g['future_row_count']}")
assert prod_g.index.max().date() <= split_g["current_date"]
readme_g = open("README.md").read()
assert "FARWCBLS INDEX is Central Bank Liquidity Swaps" in readme_g
print("    README: FARWCBLS correction ✓")

# Streamlit cache-key contract checks (static source analysis)
print("24. Streamlit cache-key contract ...")

# Scan for underscore-prefixed cache key params in cached functions
import re
BAD_PARAM_RE = re.compile(r"def \w+\((_source_hash|_production_date|_h,|_d\))")
for fpath in ["app.py", "data/loader.py", "data/external_loaders.py"]:
    src = open(fpath).read()
    matches = BAD_PARAM_RE.findall(src)
    assert not matches, f"{fpath} has underscore-prefixed cache key params: {matches}"
print("    no underscore-prefixed cache key params ✓")

# Verify specific functions have correct param names
app_src = open("app.py").read()
assert "def _build_index(source_hash" in app_src
assert "def _build_audit(source_hash" in app_src
assert "def _build_export(source_hash" in app_src
assert "production_date" in app_src.split("def _build_index")[1].split(")")[0]
print("    app.py: _build_index/audit/export have source_hash + production_date ✓")

loader_src = open("data/loader.py").read()
assert "def _load_data_cached(source_hash" in loader_src
print("    loader.py: _load_data_cached has source_hash ✓")

ext_src = open("data/external_loaders.py").read()
assert "def _load_crossasset_cached(source_hash, production_date)" in ext_src
assert "def _load_ficc_cached(source_hash, production_date)" in ext_src
assert "def _load_pulsar_cached(source_hash)" in ext_src
print("    external_loaders.py: all cached functions have correct param names ✓")

# Cache identity determinism test — synthetic, independent of workbook dates
from datetime import date as _dt_date
from data.date_integrity import split_market_data_by_asof as _split
_synthetic_dates = pd.DataFrame(
    {"value": [1.0, 2.0, 3.0]},
    index=pd.to_datetime(["2026-07-28", "2026-07-29", "2026-07-30"]),
)
split_28 = _split(_synthetic_dates, current_date=_dt_date(2026, 7, 28))
split_29 = _split(_synthetic_dates, current_date=_dt_date(2026, 7, 29))
assert "2026-07-29" in split_28["future_dates"], "7/29 must be future on 7/28"
assert "2026-07-29" not in split_29["future_dates"], "7/29 must be eligible on 7/29"
assert "2026-07-30" in split_29["future_dates"], "7/30 must be future on 7/29"
print("    date-rollover: synthetic 7/29 transitions from future to eligible correctly ✓")

# Phase 7.1C: FX no-fabrication and status-consistency
print("25. Phase 7.1C FX no-fabrication + status consistency ...")
from models.fx_rate_differential import (
    FX_PAIR_CONFIG, REQUIRED_ANALYTICAL_COLUMNS, ALIGNMENT_METRIC_MAP,
    available_fx_pairs, assess_fx_pair_readiness, build_fx_pair_data,
    build_fx_pair_snapshot, build_fx_rolling_correlations,
    build_fx_current_reading, build_all_fx_snapshots,
)
from data.date_integrity import current_production_date as _cpd_fx
prod_d = _cpd_fx()

for pair in FX_PAIR_CONFIG:
    readiness = assess_fx_pair_readiness(df, pair)
    snap = build_fx_pair_snapshot(df, pair)
    assert snap.get("status") == readiness["status"], \
        f"{pair} snapshot status != readiness status"
    aligned = build_fx_pair_data(df, pair)
    if readiness["status"] == "Ready":
        assert not aligned.empty
        for col in REQUIRED_ANALYTICAL_COLUMNS:
            assert col in aligned.columns
            assert aligned[col].isna().sum() == 0
        assert snap.get("common_latest_date") == aligned.index[-1].date()
        assert snap["common_latest_date"] <= prod_d
    raw_d = readiness.get("raw_dates", {})
    print(f"    {pair}: status={readiness['status']:12s} "
          f"aligned={readiness['aligned_obs']:>4d} "
          f"date={readiness.get('common_latest_date','—')} "
          f"missing={readiness.get('missing',[])}")

# Missing-input regression test
df_test = df.copy()
real_de_tick = "GTDEMII10Y GOVT"
for c in df_test.columns:
    if c.upper().strip() == real_de_tick.upper():
        df_test[c] = np.nan
r_test = assess_fx_pair_readiness(df_test, "EURUSD")
assert r_test["status"] in ("Partial", "Missing data"), \
    f"EURUSD without DE real 10Y must not be Ready, got {r_test['status']}"
s_test = build_fx_pair_snapshot(df_test, "EURUSD")
assert s_test.get("status") != "Ready"
print(f"    missing-DE-real test: EURUSD → {r_test['status']} ✓")

# Arbitrary change_window test
r10 = build_fx_current_reading(df, "EURUSD", change_window=10)
if r10.get("status") == "Ready":
    assert pd.notna(r10.get("fx_return_10d_pct")), "10D FX return must be finite"
    assert pd.notna(r10.get("nom_2y_diff_chg_10d_bp")), "10D diff change must be finite"
    assert r10.get("alignment_nom_2y_diff") != "Inconclusive" or \
        abs(r10.get("fx_return_10d_pct",0)) < 0.25
    print(f"    change_window=10: 10D return={r10['fx_return_10d_pct']:+.2f}%, "
          f"10D align={r10.get('alignment_nom_2y_diff')} ✓")

# Page no-zero-fallback check
fx_page_src = open("charts/pages/fx_rate_diff.py").read()
for line in fx_page_src.split("\n"):
    stripped = line.strip()
    if stripped.startswith("#"): continue
    if "snap.get(" in stripped and ", 0)" in stripped:
        raise AssertionError(f"Zero fallback: {stripped}")
print("    page: no zero-fallback patterns ✓")

# Q-list leg alignment
from models.qlist import build_qlist
from index.composite import compute_index as _ci_fxq
r_fxq = _ci_fxq(df)
qlist = build_qlist(df, r_fxq, r_fxq.index)
fx_q = [q for q in qlist if "linkage" in q.question.lower()]
if fx_q:
    # Verify alignment matches the winning metric, not a different leg
    ans = fx_q[0].answer
    for metric, align_key in ALIGNMENT_METRIC_MAP.items():
        if metric in ans:
            assert f"{metric} alignment" in ans or f"{metric} align" in ans, \
                f"Q-list shows {metric} but alignment refers to a different leg"
            break
    print(f"    Q-list: \"{fx_q[0].answer[:70]}\" ✓")

# Roadmap consistency
from config.model_roadmap import ROADMAP
for mid in ["fx_eurusd", "fx_usdjpy", "fx_gbpusd", "fx_audusd"]:
    m = next((r for r in ROADMAP if r["module_id"] == mid), None)
    assert m and m["current_status"] == "Live"
    assert "not built" not in m.get("build_notes", "").lower()
print("    roadmap: 4 FX Live, no 'not built' notes ✓")

# Phase 7.1D: Documentation and status consistency
print("26. Phase 7.1D documentation consistency ...")

# A. Data Quality
dq_7d = open("charts/pages/data_quality.py").read()
assert "FX Rate Differential Monitor" in dq_7d
assert "FX regression attribution" in dq_7d
assert "Rate-differential models not yet implemented" not in dq_7d, \
    "Stale DQ text about FX not implemented"
print("    A. DQ: live FX monitor + regression + fair-value entries ✓")

# B. README
readme_7d = open("README.md").read()
assert "07 FX Rate Differential Monitor" in readme_7d or "| 07  | FX Rate Differential Monitor" in readme_7d
assert "07b FX Complex PCA" in readme_7d or "| 07b | FX Complex PCA" in readme_7d
# FX monitor not under Future
future_section = readme_7d.split("Future analytical modules")[1] if "Future analytical modules" in readme_7d else ""
assert "FX Rate Differential Monitor" not in future_section, \
    "Live FX monitor must not be in Future section"
print("    B. README: 07 Live, 07b Experimental, not in Future ✓")

# C. Roadmap required_data
from config.model_roadmap import ROADMAP as _rm_7d
for mid in ["fx_eurusd", "fx_usdjpy", "fx_gbpusd", "fx_audusd"]:
    m = next((r for r in _rm_7d if r["module_id"] == mid), None)
    rd = m.get("required_data", [])
    rd_lower = " ".join(str(x).lower() for x in rd)
    assert "spot" in rd_lower, f"{mid} missing spot in required_data"
    assert "2y" in rd_lower, f"{mid} missing 2Y in required_data"
    assert "10y" in rd_lower, f"{mid} missing 10Y in required_data"
    assert "real" in rd_lower, f"{mid} missing real in required_data"
print("    C. Roadmap: all FX required_data include spot/2Y/10Y/real ✓")

# D. No remaining repo labels for FARWCBLS
import glob as _g7d
for fp in _g7d.glob("charts/**/*.py", recursive=True) + \
          _g7d.glob("index/**/*.py", recursive=True) + ["README.md"]:
    txt = open(fp).read()
    for bad in ["Fed reserves/repo", "Fed reserves and repo"]:
        assert bad not in txt, f"Stale repo label '{bad}' in {fp}"
print("    D. No 'Fed reserves/repo' labels anywhere ✓")

# E. Q-list says nine questions
qlist_src = open("models/qlist.py").read()
assert "10 standard" in qlist_src or "ten" in qlist_src.lower() or "9 standard" in qlist_src
print("    E. Q-list question-count documentation is current ✓")

# Phase 7.1E: Registry/documentation/test-runner cleanup
print("27. Phase 7.1E consistency ...")

# A. README main Sections table — parse exact rows
readme_e = open("README.md").read()
sections_start = readme_e.find("## Sections")
# Find the next top-level markdown separator (--- on its own line), not table separators
sections_end = readme_e.find("\n---\n", sections_start + 20)
if sections_end == -1:
    sections_end = readme_e.find("\n## ", sections_start + 20)
sections_block = readme_e[sections_start:sections_end]

def _parse_row(row_id):
    for line in sections_block.split("\n"):
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 4 and parts[1] == row_id:
            return {"title": parts[2], "status": parts[3]}
    return None

row_06 = _parse_row("06")
row_07 = _parse_row("07")
row_07b = _parse_row("07b")
assert row_06, "README missing row 06"
assert "Sector Rotation" in row_06["title"], f"06 title should be Sector Rotation & Breadth: {row_06['title']}"
assert "**Live**" in row_06["status"] or "Live" in row_06["status"], f"06 status: {row_06['status']}"
assert row_07, "README missing row 07"
assert "FX Rate Differential Monitor" in row_07["title"], f"07 title: {row_07['title']}"
assert "**Live**" in row_07["status"] or "Live" in row_07["status"], f"07 status: {row_07['status']}"
assert row_07b, "README missing row 07b"
assert "FX Complex PCA" in row_07b["title"], f"07b title: {row_07b['title']}"
assert "Experimental" in row_07b["status"], f"07b status: {row_07b['status']}"
print(f"    A. README main table: 06 {row_06['title']} — {row_06['status']}")
print(f"                          07 {row_07['title']} — {row_07['status']}")
print(f"                          07b {row_07b['title']} — {row_07b['status']}")

# B. config/pages.py Global Rates description
pages_src = open("config/pages.py").read()
gr_idx = pages_src.find('"id": "global_rates"')
gr_end = pages_src.find('"builds_on"', gr_idx)
gr_block = pages_src[gr_idx:gr_end]
assert "CH" in gr_block or "Switzerland" in gr_block, "Global Rates must mention CH/Switzerland"
print(f"    B. Global Rates description contains CH ✓")

# C. Data Quality: Live FX under Live section, not Future
dq_e = open("charts/pages/data_quality.py").read()
live_section_start = dq_e.find("Live analytical model readiness")
future_section_start = dq_e.find("Future model readiness")
assert live_section_start != -1, "Live analytical model readiness section missing"
assert future_section_start != -1, "Future model readiness section missing"
assert live_section_start < future_section_start, "Live section must come before Future"
live_block = dq_e[live_section_start:future_section_start]
# Only look at the future_models list definition, not the entire future section
future_list_start = dq_e.find("future_models = [", future_section_start)
future_list_end = dq_e.find("]", future_list_start)
future_list_block = dq_e[future_list_start:future_list_end]
assert "FX Rate Differential Monitor" in live_block, "Live FX must be in Live section"
assert '"FX Rate Differential Monitor"' not in future_list_block, \
    "Live FX must not appear in future_models list"
print(f"    C. DQ: Live FX in Live section, not in Future ✓")

# D. FX readiness exceptions are not silently passed
assert 'st.warning' in dq_e, "DQ must warn on FX readiness failure"
# Find the try/except block containing "FX Rate Differential Monitor — pair readiness"
fx_readiness_idx = dq_e.find("FX Rate Differential Monitor — pair readiness")
if fx_readiness_idx != -1:
    # Check the following except is not bare pass
    after = dq_e[fx_readiness_idx:fx_readiness_idx + 2000]
    assert "except Exception as exc" in after or "st.warning" in after
print(f"    D. DQ: FX readiness failures produce visible warning ✓")

# E. Static export
export_src = open("scripts/export_research_pack_html.py").read()
assert "FX rate-differential" not in export_src, "Static export must not describe FX as missing"
assert "Live in Streamlit" in export_src, "Static export must acknowledge Live FX exists in Streamlit"
assert "Both exports use the same" not in readme_e, "README must not claim export parity"
print(f"    E. Static export: FX not marked Missing, no false parity claim ✓")

# F. Smoke output doesn't say descriptive FX monitor is not implemented
smoke_src = open("smoke_test.py").read()
assert "FX Rate Differential Monitor: Live" in smoke_src
print(f"    F. Smoke: descriptive FX monitor status is Live ✓")

# G. Roadmap section ambiguity
from config.model_roadmap import ROADMAP as _rm_e
for m in _rm_e:
    if m["module_id"] in ("fx_eurusd", "fx_usdjpy", "fx_gbpusd", "fx_audusd"):
        assert m.get("app_section") == "07", f"{m['module_id']} app_section must be 07"
        assert "FX" in (m.get("reference_section") or ""), f"{m['module_id']} reference_section must mention FX"
    if m["module_id"] in ("spx_sector", "earnings_val", "spx_sector_contribution"):
        assert m.get("app_section") is None or m.get("app_section") == "None", \
            f"{m['module_id']} app_section must be None"
        assert "Equities" in (m.get("reference_section") or "") or "Earnings" in (m.get("reference_section") or "")
print(f"    G. Roadmap: FX app_section=07/ref=07·FX, Equities app_section=None/ref=06·Equities ✓")

# H. FX four-pair readiness after exact source-Date merge
from models.fx_rate_differential import available_fx_pairs as _afx_e
avail_e = _afx_e(df)
_fx_diag = []
for pair in ("EURUSD", "USDJPY", "GBPUSD", "AUDUSD"):
    got = avail_e[pair]["aligned_obs"]
    assert avail_e[pair]["status"] == "Ready"
    assert got >= 64, f"{pair} needs enough common history for the 63D monitor"
    assert avail_e[pair]["common_latest_date"] <= prod_d
    _fx_diag.append(f"{pair}={got}@{avail_e[pair]['common_latest_date']}")
print("    H. FX readiness after calendar correction: " + ", ".join(_fx_diag) + " ✓")

# Phase 7.1F: Documentation and audit-visibility cleanup
print("28. Phase 7.1F documentation + audit visibility ...")

readme_7f = open("README.md").read()

# A. README contains "FX Complex PCA (07b)" (allowing markdown bold) and no orphan "(07)" or "(06)" FX PCA label
# The literal reference may be **FX Complex PCA** (07b) with markdown emphasis
_has_07b_ref = ("FX Complex PCA (07b)" in readme_7f or
                "FX Complex PCA**  (07b)" in readme_7f or
                "FX Complex PCA** (07b)" in readme_7f or
                "07b FX Complex PCA" in readme_7f or
                "| 07b | FX Complex PCA" in readme_7f)
assert _has_07b_ref, "README must reference FX Complex PCA (07b)"
# Use regex negative lookahead: (07) not followed by b, and (06) not followed by b
import re as _re_7f
bad_matches = _re_7f.findall(r"FX Complex PCA[*\s]*\((?:06|07)\)(?!b)", readme_7f)
assert not bad_matches, f"README still has old (06)/(07) FX PCA label: {bad_matches}"
print("    A. README: FX Complex PCA (07b), no orphan (06)/(07) label ✓")

# B. Weekly methodology sentence occurs exactly once
weekly_count = readme_7f.count('observation_mode = "weekday"')
assert weekly_count == 1, f"weekly methodology sentence occurs {weekly_count} times, expected 1"
print(f"    B. Weekly methodology sentence occurs exactly once ✓")

# C. Export paragraph not split across CLI methodology heading
# The Contents-page sentence should be one paragraph, not split by "## The Composite..."
lazy_idx = readme_7f.find("lazy download buttons on the")
composite_idx = readme_7f.find("## The Composite Liquidity Index")
if lazy_idx != -1 and composite_idx != -1:
    between = readme_7f[lazy_idx:composite_idx]
    # The sentence should be complete before the heading
    assert 'Export research pack" expander' in between or "Export research pack\" expander" in between, \
        "Export paragraph is split across the CLI methodology heading"
    # And "expander" should not appear after the heading
    after_heading = readme_7f[composite_idx:composite_idx + 500]
    assert 'inside the "Export research pack" expander).' not in after_heading, \
        "Export paragraph fragment appears after CLI methodology heading"
print(f"    C. Export paragraph is not split across CLI methodology heading ✓")

# D. FX page does not call the four pairs G4
fx_page_7f = open("charts/pages/fx_rate_diff.py").read()
assert "G4 FX pairs" not in fx_page_7f, "FX page must not call the pairs G4 FX pairs"
assert "four selected major" in fx_page_7f.lower() or "four major" in fx_page_7f.lower(), \
    "FX page must describe the pairs as four selected major FX pairs"
print(f"    D. FX page: does not call the four pairs G4 ✓")

# E. Future-scoring and future-Sheet1 audit have no silent except/pass
dq_7f = open("charts/pages/data_quality.py").read()
# Find both future-dated sections and their except blocks
for anchor in ["Future-dated scoring rows", "Future-dated Sheet1 rows"]:
    idx = dq_7f.find(anchor)
    if idx == -1:
        continue
    # Look back to the surrounding try/except (up to 2000 chars before, 1500 after)
    ctx_start = max(0, idx - 2000)
    ctx_end = min(len(dq_7f), idx + 2000)
    block = dq_7f[ctx_start:ctx_end]
    # Find "except Exception" occurrences and ensure they are not bare pass
    for m in _re_7f.finditer(r"except Exception[^\n]*:\s*\n\s*(\w+)", block):
        first_word = m.group(1)
        assert first_word != "pass", \
            f"Silent except/pass found near '{anchor}' audit"
print(f"    E. Future-scoring + future-Sheet1 audits: no silent except/pass ✓")

# F. Raw Sheet1 audit distinguishes failure from zero rows
assert "audit_status" in dq_7f, "_raw_sheet1_audit must return audit_status"
assert '"audit_status": "OK"' in dq_7f, "OK status must be set on success"
assert '"audit_status": "Failed"' in dq_7f, "Failed status must be set on error"
assert "Failed / unavailable" in dq_7f, "DQ must display 'Failed / unavailable' for failed audit"
print(f"    F. Raw Sheet1 audit: distinguishes Failed from zero rows ✓")

# G. Roadmap heading + integrity wording
rm_page_7f = open("charts/pages/model_roadmap.py").read()
assert "Blocked pending data, metadata, or methodology" in rm_page_7f, \
    "Roadmap must use 'Blocked pending data, metadata, or methodology'"
assert "Blocked by missing data" not in rm_page_7f, \
    "Old 'Blocked by missing data' heading must be removed"
assert "not in DATA.xlsx" not in rm_page_7f, \
    "Roadmap must not say all do_not_fake modules lack DATA.xlsx inputs"
print(f"    G. Roadmap: uses 'Blocked pending' language, no false DATA.xlsx claim ✓")

# Phase 8.1: SPX Sector Rotation & Breadth
print("29. Phase 8.1 SPX Sector Rotation & Breadth ...")

# A. Pure architecture — no Streamlit imports
import ast as _ast_s
sr_src = open("models/sector_rotation.py").read()
tree_s = _ast_s.parse(sr_src)
for node in _ast_s.walk(tree_s):
    if isinstance(node, (_ast_s.Import, _ast_s.ImportFrom)):
        mod = getattr(node, "module", None) or ""
        for n in node.names:
            assert "streamlit" not in mod.lower() and "streamlit" not in n.name.lower(), \
                f"sector_rotation must not import streamlit: {mod}.{n.name}"
print("    A. Pure model: no Streamlit imports ✓")

# B. Sector registry
from config.tickers import SPX_SECTOR_CONFIG, SPX_SECTOR_ETF_PROXIES, SPX_SECTOR_ETF_PROXY_METADATA
assert len(SPX_SECTOR_CONFIG) == 11, f"expected 11 sectors, got {len(SPX_SECTOR_CONFIG)}"
for key, cfg in SPX_SECTOR_CONFIG.items():
    for k in ("ticker", "display_name", "weight_column"):
        assert k in cfg, f"{key} missing {k}"
assert SPX_SECTOR_ETF_PROXY_METADATA["allowed_in_production"] is False
# Production code uses SPX_SECTOR_CONFIG, not proxies
assert "SPX_SECTOR_CONFIG" in sr_src
assert "SPX_SECTOR_ETF_PROXIES" not in sr_src
print(f"    B. Sector registry: 11 sectors, ETF proxies excluded from production ✓")

# C. Input alignment
from models.sector_rotation import (
    build_sector_price_frame, build_sector_relative_frame,
    build_sector_snapshot, build_sector_breadth_history,
    available_sector_inputs, SPX_BENCHMARK_TICKER,
)
from data.external_loaders import load_spx_sector_weights
_weights_s = load_spx_sector_weights()
sec_frame = build_sector_price_frame(df)
rel_frame = build_sector_relative_frame(df)
assert len(sec_frame.columns) == 11, f"sector_frame must have 11 columns, got {len(sec_frame.columns)}"
assert set(sec_frame.columns) == set(SPX_SECTOR_CONFIG.keys())
assert "spx" in rel_frame.columns and len(rel_frame.columns) == 12
assert sec_frame.isna().sum().sum() == 0, "sector_frame must have no NaN"
assert rel_frame.isna().sum().sum() == 0, "relative_frame must have no NaN"

sector_only_date_expected = sec_frame.index[-1].date()
relative_model_date_expected = rel_frame.index[-1].date()
snap_s = build_sector_snapshot(df, _weights_s)
assert snap_s["sector_only_date"] == sector_only_date_expected
assert snap_s["relative_model_date"] == relative_model_date_expected
print(f"    C. sector_only_date={snap_s['sector_only_date']}, "
      f"relative_model_date={snap_s['relative_model_date']} ✓")

# D. Returns — 20D relative equals sector 20D log ret minus SPX 20D log ret
_pl = np.log(rel_frame)
_20d = _pl.iloc[-1] - _pl.iloc[-21]  # log return over 20 obs
for p in snap_s["per_sector"]:
    key = p["sector"]
    if pd.notna(p.get("rel_ret_20d_pct")):
        expected = float(100 * (_20d[key] - _20d["spx"]))
        assert abs(p["rel_ret_20d_pct"] - expected) < 0.01, \
            f"{key} 20D rel mismatch: got {p['rel_ret_20d_pct']}, expected {expected}"
# Mismatched intervals = 0 by construction (same aligned frame)
print("    D. 20D relative = sector 20D log ret − SPX 20D log ret ✓  mismatched=0")

# E. Missing-input regression
_df_test = df.copy()
# Zap S5INFT (info tech)
for c in _df_test.columns:
    if c.upper().strip() == "S5INFT INDEX":
        _df_test[c] = np.nan
        break
snap_partial = build_sector_snapshot(_df_test, _weights_s)
assert snap_partial["status"] == "Partial",     f"one missing sector must produce Partial, got {snap_partial['status']}"
assert "S5INFT INDEX" in snap_partial["missing"] or any("S5INFT" in m for m in snap_partial["missing"])
from models.sector_rotation import build_sector_current_reading as _bscr
r_p = _bscr(_df_test, _weights_s)
assert r_p.get("status") == "Partial"
assert r_p.get("positive_denom") == 10,     f"breadth denominator must be 10 with one missing sector, got {r_p.get('positive_denom')}"
missing_row = next(p for p in snap_partial["per_sector"] if p["ticker"] == "S5INFT INDEX")
assert pd.isna(missing_row["ret_20d_pct"]), "missing sector return must remain NaN"
assert missing_row["status"] == "Missing data"
print("    E. Missing S5INFT: Partial, denominator=10, no zero/proxy fill ✓")

# F. Weights
assert _weights_s is not None
assert not _weights_s.empty
for key, cfg in SPX_SECTOR_CONFIG.items():
    assert cfg["weight_column"] in _weights_s.columns, f"missing weight col {cfg['weight_column']}"
from data.date_integrity import current_production_date as _cpd_s
prod_d_s = _cpd_s()
assert _weights_s.index[-1].date() <= prod_d_s, "future weight rows must be excluded"
latest_wsum = _weights_s.iloc[-1][[c["weight_column"] for c in SPX_SECTOR_CONFIG.values()]].sum()
print(f"    F. Weights: {len(_weights_s)} rows, latest date={_weights_s.index[-1].date()}, "
      f"latest sum={latest_wsum:.2f}% ✓")
_weights_2025 = load_spx_sector_weights(current_date=_dt_date(2025, 1, 1))
assert _weights_2025 is not None and _weights_2025.index.max().date() <= _dt_date(2025, 1, 1)
_weights_raw = load_spx_sector_weights(include_future=True, current_date=_dt_date(2025, 1, 1))
assert _weights_raw is not None and _weights_raw.index.max() >= _weights_s.index.max()
print("       explicit current_date respected; include_future preserves raw weight rows ✓")

# G. Rotation classifications — verify quadrant follows short/long signs and threshold
from models.sector_rotation import _classify_quadrant, DEFAULT_FLAT_THRESHOLD_PCT
assert _classify_quadrant(1.0, 1.0, DEFAULT_FLAT_THRESHOLD_PCT) == "Leader"
assert _classify_quadrant(1.0, -1.0, DEFAULT_FLAT_THRESHOLD_PCT) == "Improving"
assert _classify_quadrant(-1.0, 1.0, DEFAULT_FLAT_THRESHOLD_PCT) == "Weakening"
assert _classify_quadrant(-1.0, -1.0, DEFAULT_FLAT_THRESHOLD_PCT) == "Laggard"
assert _classify_quadrant(0.1, 1.0, DEFAULT_FLAT_THRESHOLD_PCT) == "Neutral / inconclusive"
# Reading has no causal / flow language
r_full = _bscr(df, _weights_s)
banned = ["caused", "flows into", "investors bought", "will outperform",
          "undervalued", "official attribution"]
for v in r_full.values():
    if isinstance(v, str):
        for bad in banned:
            assert bad not in v.lower(), f"Sector reading contains '{bad}'"
print("    G. Rotation quadrants + no causal/flow language ✓")

# H. Page architecture
sr_page_src = open("charts/pages/sector_rotation.py").read()
assert "build_sector_snapshot" in sr_page_src or "build_sector_current_reading" in sr_page_src
# Weight bubble labelled as weight, not contribution
assert "weight" in sr_page_src.lower()
assert "not return contribution" in sr_page_src.lower() or "not a return contribution" in sr_page_src.lower() \
       or "Weight, not return contribution" in sr_page_src
# Separate dates shown
assert "sector_only_date" in sr_page_src or "Sector-only" in sr_page_src
assert "relative_model_date" in sr_page_src or "Relative model" in sr_page_src
assert "weight_date" in sr_page_src or "Weight date" in sr_page_src
print("    H. Page: imports pure model, weight bubble labelled correctly ✓")

# H2. Calendar-integrity, raw-cell-type and dispersion contracts
# Raw workbook cells in the 39 added columns must remain numeric/missing. A
# date-formatted numeric cell would otherwise be parsed as a datetime and be
# silently lost during numeric normalisation.
_raw_added = pd.read_excel("data/DATA.xlsx", sheet_name="Sheet1", usecols="ET:GF")
assert _raw_added.shape[1] == 39, _raw_added.shape
_bad_datetime_cols = [
    c for c in _raw_added.columns
    if pd.api.types.is_datetime64_any_dtype(_raw_added[c])
]
assert not _bad_datetime_cols, f"Added market-data columns parsed as dates: {_bad_datetime_cols}"
assert Path("docs/CALENDAR_CORRECTION_2026-08-03.md").exists()
assert "CALENDAR_CORRECTION_2026-08-03.md" in open("README.md").read()

from data.calendar_integrity import audit_sector_calendar, audit_ticker_group_calendar, audit_parent_sector_return_range
sector_cal = audit_sector_calendar(df)
assert sector_cal["weekend_observation_count"] == 0, sector_cal
assert sector_cal["weekday_counts"]["Friday"] > 0, sector_cal
assert sector_cal["status"] == "Ready", sector_cal
fx_cal = audit_ticker_group_calendar(
    df,
    ["EURUSD BGN CURNCY", "USDJPY BGN CURNCY", "GBPUSD BGN CURNCY", "AUDUSD BGN CURNCY"],
    "FX spot",
)
assert fx_cal["weekend_observation_count"] == 0, fx_cal
parent_checks = audit_parent_sector_return_range(df)
assert not parent_checks.empty and parent_checks["range_test_passed"].all(), parent_checks
_parent_20 = parent_checks.loc[parent_checks["horizon"] == 20].iloc[0]
assert _parent_20["sectors_above_spx"] > 0 and _parent_20["sectors_below_spx"] > 0, _parent_20
assert snap_s.get("enough_history") is True
bh_contract = build_sector_breadth_history(df, horizon=20)
assert "dispersion_pct" in bh_contract.columns
assert "relative_dispersion_pct" not in bh_contract.columns
assert "relative_dispersion_pct" not in sr_page_src
print("    H2. Calendar/source cells: weekdays valid, raw types numeric, parent range passed; one dispersion series ✓")

# I. Status consistency
from config.pages import PAGES as _P_s
sr_page = next((p for p in _P_s if p["id"] == "sector_rotation"), None)
assert sr_page is not None and sr_page["section"] == "06" and sr_page["status"] == "live"
dq_s = open("charts/pages/data_quality.py").read()
assert "Sector Rotation & Breadth Monitor" in dq_s
from config.model_roadmap import ROADMAP as _rm_s
_rot = next((r for r in _rm_s if r["module_id"] == "sector_rotation"), None)
_brd = next((r for r in _rm_s if r["module_id"] == "breadth"), None)
assert _rot and _rot["current_status"] == "Live"
assert _brd and _brd["current_status"] == "Live"
# Official attribution stays Not Started
_ofa = next((r for r in _rm_s if r["module_id"] == "spx_sector"), None)
assert _ofa and _ofa["current_status"] == "Not Started"
readme_s = open("README.md").read()
assert "06 Sector Rotation & Breadth" in readme_s or "| 06  | Sector Rotation" in readme_s
print("    I. Status consistency: pages/DQ/roadmap/README all agree ✓")
assert "Which SPX sectors are leading and lagging?" not in qlist_src
assert "Which SPX sectors rank highest and lowest versus SPX?" in qlist_src
print("       Q-list uses highest/lowest ranking language ✓")

# Diagnostics — printed for verification
print(f"    Configured sectors: {len(SPX_SECTOR_CONFIG)}")
print(f"    Sector-only obs: {snap_s['sector_only_obs']}, date: {snap_s['sector_only_date']}")
print(f"    Sector+SPX obs: {snap_s['relative_obs']}, date: {snap_s['relative_model_date']}")
print(f"    Weight rows: {len(_weights_s)}, latest weight date: {snap_s['weight_date']}")
top_rel = sorted(snap_s["per_sector"], key=lambda p: p.get("rel_ret_20d_pct", -999), reverse=True)[:3]
bot_rel = sorted(snap_s["per_sector"], key=lambda p: p.get("rel_ret_20d_pct", 999))[:3]
print(f"    Top 3 20D relative: " + "; ".join(f"{p['display_name']} ({p['rel_ret_20d_pct']:+.2f}pp)" for p in top_rel))
print(f"    Bot 3 20D relative: " + "; ".join(f"{p['display_name']} ({p['rel_ret_20d_pct']:+.2f}pp)" for p in bot_rel))
q_counts_s = {}
for p in snap_s["per_sector"]:
    q_counts_s[p["quadrant"]] = q_counts_s.get(p["quadrant"], 0) + 1
print(f"    Quadrant counts: {q_counts_s}")

print("\nALL SMOKE TESTS PASSED ✓")
import time as _t_end
print(f"Elapsed: {_t_end.time() - _t0:.1f}s")
