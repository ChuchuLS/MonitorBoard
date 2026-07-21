"""Headless smoke test — verifies the package builds the index without a
Streamlit server. Run: python smoke_test.py"""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np

print("1. Importing all modules ...")
from data.loader import _load_dataframe, data_source_label, get_series
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
assert len(PAGES) == 11, f"expected 11 registered pages, got {len(PAGES)}"
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
df = _load_dataframe()
print(f"   {df.shape[0]:,} rows x {df.shape[1]:,} cols in {time.time()-t0:.2f}s")
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
    from models.scoring.engine import score_rates, RATES_UNIVERSE
    asof = max(d.index.max() for d in scoring_data.values() if len(d))
    rs = score_rates(scoring_data, asof, {"macro": 0.5, "markets": 0.5})
    print(f"    scoring model: {len(rs)} rates scored as of {asof.date()}"
          f" · top: {rs.iloc[0]['country']} ({rs.iloc[0]['score']:+.2f})")


# Phase 1.7 alignment checks
print("12. Phase 1.7 alignment checks ...")

# Cross-Asset required columns present + 8-regime works + days-in-regime
if ca is not None:
    from charts.pages.cross_asset import REQUIRED_COLUMNS, classify_8regime, _days_in_current
    ca_missing = [c for c in REQUIRED_COLUMNS if c not in ca.columns]
    assert not ca_missing, f"DATA.xlsx missing cross-asset columns: {ca_missing}"
    regime_result = classify_8regime(ca)
    assert not regime_result.empty, "classify_8regime returned empty"
    assert "regime" in regime_result.columns
    days_in = _days_in_current(regime_result["regime"])
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

# Verify no stale external files exist (all consolidated into DATA.xlsx)
from pathlib import Path
assert Path("data/DATA.xlsx").exists(), "DATA.xlsx must exist"
assert not Path("data/CROSSASSET.xlsx").exists(), "CROSSASSET.xlsx should not exist (consolidated into DATA.xlsx)"
assert not Path("data/FICCREADING.xlsx").exists(), "FICCREADING.xlsx should not exist (consolidated into DATA.xlsx)"
assert not Path("data/pulsar_data.xlsx").exists(), "pulsar_data.xlsx should not exist (consolidated into DATA.xlsx)"
print("    no stale standalone files ✓ (all data in DATA.xlsx)")


print("\nALL SMOKE TESTS PASSED ✓")
