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
import charts.common, charts.rates, charts.funding, charts.credit, charts.liquidity
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip, render_kpi_card,
    render_explanation_box, render_current_reading_box, render_model_note,
    render_missing_data_warning, render_section_footer,
)
from charts.pages import PageContext, render_page, RENDERERS
print("   all imports OK")

# Registry / theme sanity — Phase 1 shell must be internally consistent.
assert len(PAGES) == 11, f"expected 11 registered pages, got {len(PAGES)}"
for p in PAGES:
    for k in ("id", "label", "title", "section", "color_key", "status",
              "description", "builds_on", "next"):
        assert k in p, f"page {p.get('id')} missing key {k}"
    assert p["color_key"] in SECTION_COLORS, \
        f"page {p['id']} references unknown color_key {p['color_key']}"
    assert p["status"] in STATUS_LABELS, f"unknown status: {p['status']}"
    assert p["id"] in RENDERERS, f"no renderer for page id {p['id']}"
# 'Contents' is a renderer but not in PAGES registry (it's the landing).
assert "contents" in RENDERERS, "contents landing page renderer missing"
print(f"   registry OK: {len(PAGES)} sections + contents · all renderers "
      f"wired · all color keys resolve")

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
        assert r < 1e-6, f"{h} change contributions must reconcile ({r})"
        print(f"   {h} change contrib reconciles (Σ={cc.sum():+.3f} vs Δindex={idx_chg:+.3f})")

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
# (5) coverage gate removes low-coverage dates (2016-2018 not published)
assert res.index.loc["2016-01-01":"2018-12-31"].notna().sum() == 0, "low-coverage era must be NaN"
print(f"    coverage gate: 2016-2018 excluded, reliable from {res.first_published_date.date()}")
# (6) weekly components don't stay live beyond max_ffill_days
ffa = forward_fill_audit(res, df)
wk = ffa[ffa["frequency"] != "daily"]
for _, r in wk.iterrows():
    if r["is_live"]:
        assert r["days_since_true_obs"] <= r["max_ffill_days"], \
            f"{r['component']} live beyond max_ffill"
print(f"    weekly freshness OK ({len(wk)} weekly components within ffill cap)")
# (7) forward-fill audit flags weekly series as substantially forward-filled
assert (wk["pct_ffilled_1y"] > 50).all(), "weekly series should be majority forward-filled"
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
from charts.pages import (contents, liquidity_overview, policy, decomposition,
                          rates_pca, regimes, global_rates, cross_asset,
                          market_linkage, fx, data_quality, scoring)
print("    all 12 page modules import cleanly (contents + 11 sections)")

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
from charts.pages.data_quality import REQUIRED_CROSSASSET_COLS, REQUIRED_SCORING_SHEETS
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

# Verify no stale external files exist (all consolidated into DATA.xlsx)
from pathlib import Path
assert Path("data/DATA.xlsx").exists(), "DATA.xlsx must exist"
assert not Path("data/CROSSASSET.xlsx").exists(), "CROSSASSET.xlsx should not exist (consolidated into DATA.xlsx)"
assert not Path("data/FICCREADING.xlsx").exists(), "FICCREADING.xlsx should not exist (consolidated into DATA.xlsx)"
assert not Path("data/pulsar_data.xlsx").exists(), "pulsar_data.xlsx should not exist (consolidated into DATA.xlsx)"
print("    no stale standalone files ✓ (all data in DATA.xlsx)")


print("\nALL SMOKE TESTS PASSED ✓")
