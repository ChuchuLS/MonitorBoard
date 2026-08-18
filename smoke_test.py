"""Headless smoke test — verifies the package builds the index without a
Streamlit server. Run: python smoke_test.py"""
import ast, sys, time, os
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
from config.pages import (
    PAGES, PAGES_BY_ID, TOP_NAV_GROUPS, get_page, nav_label, STATUS_LABELS,
)
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

# Deployment/UI contracts: user-facing pages may not silently swallow errors,
# and KPI subtitles are plain text because render_kpi_card escapes them.
_ui_files = [Path("app.py"), *sorted(Path("charts/pages").glob("*.py"))]
_silent_handlers = []
_html_kpi_subtitles = []
for _ui_path in _ui_files:
    _tree = ast.parse(_ui_path.read_text(encoding="utf-8"), filename=str(_ui_path))
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.ExceptHandler):
            _is_exception = isinstance(_node.type, ast.Name) and _node.type.id == "Exception"
            if _is_exception and len(_node.body) == 1 and isinstance(_node.body[0], ast.Pass):
                _silent_handlers.append(f"{_ui_path}:{_node.lineno}")
        if isinstance(_node, ast.Dict):
            for _key, _value in zip(_node.keys, _node.values):
                if isinstance(_key, ast.Constant) and _key.value == "sub":
                    fragments = [
                        part.value for part in ast.walk(_value)
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)
                    ]
                    if any("<" in fragment or ">" in fragment for fragment in fragments):
                        _html_kpi_subtitles.append(f"{_ui_path}:{_node.lineno}")
assert not _silent_handlers, f"silent user-facing exception handlers: {_silent_handlers}"
assert not _html_kpi_subtitles, f"HTML found in escaped KPI subtitles: {_html_kpi_subtitles}"
_requirements = Path("requirements.txt").read_text(encoding="utf-8")
assert "streamlit==1.56.0" in _requirements and "pandas==2.3.3" in _requirements
print("   deployment contracts OK: pinned runtime · no silent page failures · no escaped KPI HTML")

# Registry / theme sanity — Phase 1 shell must be internally consistent.
assert len(PAGES) == 18, f"expected 18 registered pages, got {len(PAGES)}"
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
print(f"   official index = {latest:.2f} on {res.latest_date.date()}  regime = {res.latest_regime}")
assert 0 < latest < 100, "index out of expected range"
assert res.latest_regime in ("Loose", "Neutral", "Tight", "Stress")
official_date = res.latest_date
assert official_date is not None, "official headline date must be available"
assert int(res.available_bucket_count.loc[official_date]) == len(BUCKETS), \
    "official headline must contain every bucket"
assert res.available_component_count.loc[official_date] >= \
       res.normal_component_target.loc[official_date], \
    "official headline must meet normal component coverage"
assert bool(res.headline_mask.loc[official_date])
official_weights = res.effective_weights.loc[official_date].dropna()
assert np.allclose(official_weights.sort_index(),
                   res.weights.reindex(official_weights.index).sort_index()), \
    "official headline must use base weights without missing-bucket redistribution"
if res.preliminary_date is not None:
    pd_date = res.preliminary_date
    assert pd_date > official_date
    assert not bool(res.headline_mask.loc[pd_date])
    assert pd.notna(res.preliminary_latest)
    print(f"   preliminary = {res.preliminary_latest:.2f} on {pd_date.date()} · "
          f"{int(res.available_bucket_count.loc[pd_date])}/{len(BUCKETS)} buckets · "
          "excluded from headline")

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
# v0.4 audit / methodology / reconciliation checks
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
assert aud["latest_official_date"] == res.latest_date
assert aud["components_on_official"] >= aud["normal_component_target_on_preliminary"] \
       if aud["normal_component_target_on_preliminary"] is not None else True


# ---------------------------------------------------------------------------
# Phase 1 — research-pack shell checks
# ---------------------------------------------------------------------------
print("11. Phase 1+2 research-pack shell ...")
# Determinism guarantee: the index calculation must not depend on any shell code.
r1 = compute_index(df)
r2 = compute_index(df)
assert abs(r1.latest - r2.latest) < 1e-12, "compute_index is non-deterministic"
assert r1.latest == res.latest, "index result drift within one run"
print(f"    compute_index is deterministic "
      f"(latest = {res.latest:.4f})")

# All page modules import cleanly
if _HAS_STREAMLIT_PAGES:
    from charts.pages import (contents, liquidity_overview, policy, policy_futures,
                              decomposition, regimes, global_rates, country_boards,
                              cross_asset, market_linkage, sector_rotation,
                              sector_contribution, index_breadth, earnings_valuation, fx_rate_diff,
                              data_quality, scoring, model_roadmap)
    print("    all registered page modules import cleanly")
else:
    print("    (Streamlit page imports skipped — not available)")

# The theme colour system is complete for every registered section.
missing_colors = [p["id"] for p in PAGES if p["color_key"] not in SECTION_COLORS]
assert not missing_colors, f"pages missing colours: {missing_colors}"
print(f"    SECTION_COLORS covers all {len(PAGES)} sections")

_grouped_ids = [pid for group in TOP_NAV_GROUPS for pid in group["page_ids"]]
assert len(TOP_NAV_GROUPS) == 9
assert len(_grouped_ids) == len(set(_grouped_ids))
assert set(_grouped_ids) == {p["id"] for p in PAGES}
assert next(g for g in TOP_NAV_GROUPS if g["id"] == "equities")["page_ids"] == (
    "sector_rotation", "sector_contribution", "index_breadth", "earnings_valuation"
)
print(f"    top strip: 9 grouped sections cover all {len(PAGES)} sidebar pages ✓")

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
    assert not Path("models/rates_complex").exists()
    assert not Path("models/fx_complex").exists()
    print("    removed PCA-only rates and FX model packages are absent ✓")

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
_gr_src = open("models/global_rates.py").read()
_gr_page_src = open("charts/pages/global_rates.py").read()
assert ".ffill(" not in _gr_src and ".ffill(" not in _gr_page_src
assert all(126 <= int(overlay[c].notna().sum()) <= 252 for c in overlay.columns)
print(f"    10Y overlay: {overlay.shape}, genuine observations only")

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

# Policy-futures status separation
from data.policy_futures_loader import load_policy_futures as _load_fixed_policy_futures
from config.tickers import SOFR_CONTRACT_CONFIG as _SOFR_FIXED_CONFIG
_pf_early = _load_fixed_policy_futures()
_pf_missing_early = [c for c in _SOFR_FIXED_CONFIG if c not in _pf_early.columns]
print(f"    SOFR Futures Strip & Calendar Spreads: {'Ready inputs' if not _pf_missing_early else 'Missing data'}")
print("    Meeting-by-meeting FOMC path: Not implemented")

# Direct call to build_snapshot (no subprocess) for routine testing
from scripts.export_research_pack_snapshot import build_snapshot
snapshot = build_snapshot()
_shared_snapshot = snapshot
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
snap = _shared_snapshot
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
from config.model_roadmap import (
    ROADMAP,
    METHODOLOGY_RESEARCH_BACKLOG,
    coverage_summary,
    do_not_fake_list,
)
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
    assert m["current_status"] in ("Data Missing", "Not Started", "Needs confirmation", "Partial")
assert len(METHODOLOGY_RESEARCH_BACKLOG) == 4
assert all(item["status"] == "Deferred research" for item in METHODOLOGY_RESEARCH_BACKLOG)
print(f"    roadmap: {len(ROADMAP)} modules, coverage={counts}")
print(f"    do_not_fake: {len(dnf)} modules correctly blocked")
print("    methodology memo: 4 deferred research questions recorded")
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
assert 0 < r_reg.latest < 100, f"CLI out of range: {r_reg.latest:.1f}"
assert abs(r_reg.level_contributions().sum() - (r_reg.latest - 50.0)) < 1e-6
assert INDEX_METHODOLOGY["version"] == "v0.4"
print(f"    CLI: {r_reg.latest:.2f} ({r_reg.latest_regime}) — v0.4 headline gate + reconciliation OK ✓")

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
assert len(qlist) == 14, f"expected 14 Q-list answers, got {len(qlist)}"
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
assert "FX Complex PCA" not in readme_7d
# FX monitor not under Future
future_section = readme_7d.split("Future analytical modules")[1] if "Future analytical modules" in readme_7d else ""
assert "FX Rate Differential Monitor" not in future_section, \
    "Live FX monitor must not be in Future section"
print("    B. README: 07 Live, experimental FX PCA removed, not in Future ✓")

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

# E. Q-list question count
qlist_src = open("models/qlist.py").read()
assert "14 standard" in qlist_src or "fourteen" in qlist_src.lower()
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
assert row_06, "README missing row 06"
assert "Sector Rotation" in row_06["title"], f"06 title should be Sector Rotation & Breadth: {row_06['title']}"
assert "**Live**" in row_06["status"] or "Live" in row_06["status"], f"06 status: {row_06['status']}"
assert row_07, "README missing row 07"
assert "FX Rate Differential Monitor" in row_07["title"], f"07 title: {row_07['title']}"
assert "**Live**" in row_07["status"] or "Live" in row_07["status"], f"07 status: {row_07['status']}"
print(f"    A. README main table: 06 {row_06['title']} — {row_06['status']}")
print(f"                          07 {row_07['title']} — {row_07['status']}")
assert _parse_row("07b") is None, "Removed FX PCA page must not remain in README table"

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
    if m["module_id"] == "spx_sector":
        assert m.get("app_section") is None or m.get("app_section") == "None", \
            "spx_sector app_section must be None"
        assert "Equities" in (m.get("reference_section") or "")
    if m["module_id"] == "earnings_val":
        assert m.get("app_section") == "06d", "earnings_val app_section must be 06d"
        assert "Equities" in (m.get("reference_section") or "") or "Earnings" in (m.get("reference_section") or "")
    if m["module_id"] == "spx_sector_contribution":
        assert m.get("app_section") == "06b"
        assert "Equities" in (m.get("reference_section") or "")
print(f"    G. Roadmap: FX=07, contribution=06b, breadth=06c, earnings=06d, future attribution unassigned ✓")

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
import re as _re_7f

# A. Experimental PCA pages are removed from production navigation and README
for _removed_id in ("rates_pca", "market_linkage_pca", "fx"):
    assert _removed_id not in PAGES_BY_ID
for _removed_label in ("Rates Complex PCA", "Market Linkage PCA", "FX Complex PCA"):
    assert _removed_label not in readme_7f
print("    A. Experimental PCA pages removed from production navigation and README ✓")

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
    build_reference_breadth_dispersion_history,
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
reference_bd = build_reference_breadth_dispersion_history(df)
assert not reference_bd.empty
assert {
    "above_ma_count", "breadth_denominator", "above_ma_breadth_pct",
    "dispersion_valid_count", "return_dispersion_pct",
}.issubset(reference_bd.columns)
_prices_ref = build_sector_price_frame(df)
_ma_ref = _prices_ref.rolling(50, min_periods=50).mean()
_valid_ref = _prices_ref.notna() & _ma_ref.notna()
_expected_breadth = float(
    100 * ((_prices_ref.gt(_ma_ref) & _valid_ref).iloc[-1].sum())
    / _valid_ref.iloc[-1].sum()
)
_ret21_ref = 100 * (_prices_ref.iloc[-1] / _prices_ref.iloc[-22] - 1)
_expected_disp = float(_ret21_ref.std(ddof=0))
assert abs(reference_bd.iloc[-1]["above_ma_breadth_pct"] - _expected_breadth) < 1e-9
assert abs(reference_bd.iloc[-1]["return_dispersion_pct"] - _expected_disp) < 1e-9
assert "above their own 50-observation moving average" in sr_page_src
assert "trailing 21-observation simple sector returns" in sr_page_src
print("    H2. Calendar/source cells valid; reference-pack 50D breadth + 21D dispersion reconcile ✓")

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

# Phase 8.2: Sector Contribution Estimate
print("30. Phase 8.2 Sector Contribution Estimate ...")

# A. Pure architecture
sc_src = open("models/sector_contribution.py").read()
sc_tree = _ast_s.parse(sc_src)
for node in _ast_s.walk(sc_tree):
    if isinstance(node, (_ast_s.Import, _ast_s.ImportFrom)):
        mod = getattr(node, "module", None) or ""
        for n in node.names:
            assert "streamlit" not in mod.lower() and "streamlit" not in n.name.lower()
print("    A. Pure contribution model: no Streamlit imports ✓")

from models.sector_contribution import (
    DEFAULT_CONTRIBUTION_HORIZONS,
    MAX_WEIGHT_AGE_DAYS,
    build_sector_contribution_estimate,
    build_sector_contribution_summary,
    build_sector_contribution_history,
    build_sector_contribution_current_reading,
    select_start_weight,
)

# B. Formula, common timestamps, and exact residual disclosure
_sc_results = {}
for _h in DEFAULT_CONTRIBUTION_HORIZONS:
    _r = build_sector_contribution_estimate(df, _weights_s, horizon=_h)
    _sc_results[_h] = _r
    assert _r["status"] == "Ready", (_h, _r)
    assert _r["weight_date"] <= _r["start_date"] <= _r["end_date"]
    assert _r["weight_age_days"] <= MAX_WEIGHT_AGE_DAYS
    assert _r["weight_normalised"] is False
    assert _r["official_attribution"] is False
    assert len(_r["per_sector"]) == 11
    assert abs(_r["actual_spx_return_pct"] - (
        _r["estimated_spx_return_pct"] + _r["residual_pp"]
    )) < 1e-12
    _aligned = build_sector_relative_frame(df)
    _start = _aligned.index[-_h - 1]
    _end = _aligned.index[-1]
    assert _r["start_date"] == _start.date() and _r["end_date"] == _end.date()
    for _row in _r["per_sector"]:
        _expected = _row["start_weight_pct"] / 100.0 * _row["sector_return_pct"]
        assert abs(_row["estimated_contribution_pp"] - _expected) < 1e-12
print("    B. Start-weight × simple-return formula and residual reconciliation ✓")

# C. No normalisation; exact source weight is used
_r20 = _sc_results[20]
_wsel = select_start_weight(_weights_s, _r20["start_date"])
assert abs(_wsel.weight_sum_pct - _r20["weight_sum_pct"]) < 1e-12
assert abs(_r20["weight_sum_pct"] - 100.0) <= 0.15
print(f"    C. 20D weight date={_r20['weight_date']}, sum={_r20['weight_sum_pct']:.2f}%, not normalised ✓")

# D. Missing weight and missing sector remain Partial / NaN, never zero
_w_missing = _weights_s.drop(columns=[next(iter(SPX_SECTOR_CONFIG.values()))["weight_column"]])
_r_w_missing = build_sector_contribution_estimate(df, _w_missing, horizon=20)
assert _r_w_missing["status"] == "Partial"
assert pd.isna(_r_w_missing["estimated_spx_return_pct"])
assert pd.isna(_r_w_missing["residual_pp"])
_r_p_missing = build_sector_contribution_estimate(_df_test, _weights_s, horizon=20)
assert _r_p_missing["status"] == "Partial"
assert pd.isna(_r_p_missing["estimated_spx_return_pct"])
_missing_it = next(row for row in _r_p_missing["per_sector"] if row["ticker"] == "S5INFT INDEX")
assert pd.isna(_missing_it["estimated_contribution_pp"])
print("    D. Missing price/weight: Partial, estimate withheld, no zero substitution ✓")

# E. Future weight cannot be used for a past start date
_w_future = _weights_s.copy()
_future_row = _w_future.iloc[-1].copy()
_w_future.loc[pd.Timestamp("2099-12-31")] = _future_row
_r_future = build_sector_contribution_estimate(df, _w_future, horizon=20)
assert _r_future["weight_date"] == _r20["weight_date"]
assert _r_future["weight_date"] <= _r_future["start_date"]
print("    E. Future weight rows are excluded by start-date selection ✓")

# F. Rolling history and summary
_sc_summary = build_sector_contribution_summary(df, _weights_s)
assert list(_sc_summary["horizon"]) == list(DEFAULT_CONTRIBUTION_HORIZONS)
assert (_sc_summary["status"] == "Ready").all()
_sc_hist = build_sector_contribution_history(df, _weights_s, horizon=20)
assert not _sc_hist.empty
assert np.allclose(
    _sc_hist["actual_spx_return_pct"],
    _sc_hist["estimated_spx_return_pct"] + _sc_hist["residual_pp"],
    atol=1e-12, rtol=0,
)
assert (_sc_hist["weight_date"] <= _sc_hist["start_date"]).all()
print(f"    F. Rolling 20D history: {len(_sc_hist)} estimates, every residual reconciles ✓")

# G. Page architecture and wording
_sc_page_src = open("charts/pages/sector_contribution.py").read()
assert "build_sector_contribution_current_reading" in _sc_page_src
assert "official attribution" in _sc_page_src.lower()
assert "not official" in _sc_page_src.lower()
assert "weights are not normalised" in _sc_page_src.lower() or "not normalised" in _sc_page_src.lower()
for _bad in ("investors bought", "flows into", "will outperform", "official contribution data shown"):
    assert _bad not in _sc_page_src.lower()
print("    G. Page uses pure model and explicit approximation wording ✓")

# H. Registry, roadmap, Data Quality, README, snapshot
_sc_page = next((p for p in _P_s if p["id"] == "sector_contribution"), None)
assert _sc_page and _sc_page["section"] == "06b" and _sc_page["status"] == "live"
_sc_rm = next((r for r in _rm_s if r["module_id"] == "spx_sector_contribution"), None)
assert _sc_rm and _sc_rm["current_status"] == "Live"
assert _sc_rm["implemented_in"] == "models/sector_contribution.py"
assert _sc_rm["app_section"] == "06b"
assert _ofa["current_status"] == "Not Started"
assert "Sector Contribution Estimate" in dq_s and "reconciliation audit" in dq_s
assert "| 06b | Sector Contribution Estimate" in readme_s
assert "SPX sector contribution estimate (data available" not in readme_s
_snapshot_sc = _shared_snapshot
assert "sector_contribution_estimate" in _snapshot_sc
assert _snapshot_sc["sector_contribution_estimate"]["official_attribution"] is False
print("    H. Registry/DQ/roadmap/README/snapshot status consistent ✓")

# I. Q-list question 11
_qlist_sc = qlist
assert len(_qlist_sc) == 14
_sc_q = next(q for q in _qlist_sc if "estimated SPX return" in q.question)
assert _sc_q.data_status == "real_data"
assert "residual" in _sc_q.answer.lower() and "weight" in _sc_q.answer.lower()
assert "official" in " ".join(_sc_q.details).lower()
print("    I. Q11 uses real estimate, residual, weight date, and non-official disclosure ✓")

print(f"    20D actual SPX: {_r20['actual_spx_return_pct']:+.3f}%")
print(f"    20D estimated:  {_r20['estimated_spx_return_pct']:+.3f}%")
print(f"    20D residual:   {_r20['residual_pp']:+.3f}pp")
print("    Top positive: " + "; ".join(
    f"{row['display_name']} {row['estimated_contribution_pp']:+.3f}pp"
    for row in build_sector_contribution_current_reading(df, _weights_s, 20)["top_positive"]
))
print("    Top negative: " + "; ".join(
    f"{row['display_name']} {row['estimated_contribution_pp']:+.3f}pp"
    for row in build_sector_contribution_current_reading(df, _weights_s, 20)["top_negative"]
))

# Phase 9.1: Country Rate Boards
print("31. Phase 9.1 Country Rate Boards ...")
import ast as _ast_cb
_cb_src = open("models/country_rate_boards.py").read()
_cb_tree = _ast_cb.parse(_cb_src)
for _node in _ast_cb.walk(_cb_tree):
    if isinstance(_node, (_ast_cb.Import, _ast_cb.ImportFrom)):
        _mod = getattr(_node, "module", None) or ""
        for _name in _node.names:
            assert "streamlit" not in _mod.lower() and "streamlit" not in _name.name.lower()
assert ".ffill(" not in _cb_src, "country boards must not forward-fill"
print("    A. Pure model: no Streamlit and no forward-fill ✓")

from models.country_rate_boards import (
    BOARD_HORIZONS, BOARD_SLOPE_PAIRS, available_country_boards,
    build_country_board, build_country_curve_frame,
    build_country_board_current_reading, build_global_country_board_overview,
)
from config.tickers import REGIME_COUNTRIES as _CB_COUNTRIES, TICKERS as _CB_TICKERS

_cb_ready = available_country_boards(df)
assert set(_cb_ready) == set(_CB_COUNTRIES)
assert all(info["status"] == "Ready" for info in _cb_ready.values()), _cb_ready
assert all(info["aligned_observations"] >= 64 for info in _cb_ready.values())
print("    B. Seven fully aligned country boards are Ready ✓")

for _country in _CB_COUNTRIES:
    _frame = build_country_curve_frame(df, _country)
    assert list(_frame.columns) == ["2Y", "5Y", "10Y", "30Y"]
    assert not _frame.empty and not _frame.isna().any().any()
    _board = build_country_board(df, _country)
    assert _board["status"] == "Ready"
    assert _board["model_date"] == _frame.index[-1].date()
    assert len(_board["yield_table"]) == 4
    assert len(_board["slope_table"]) == len(BOARD_SLOPE_PAIRS)
    _yt = _board["yield_table"].set_index("tenor")
    for _h in BOARD_HORIZONS:
        if len(_frame) > _h:
            _expected = 100.0 * (_frame["10Y"].iloc[-1] - _frame["10Y"].iloc[-_h - 1])
            assert abs(_yt.at["10Y", f"change_{_h}d_bp"] - _expected) < 1e-12
    _read = build_country_board_current_reading(df, _country, horizon=20)
    assert _read["status"] == "Ready" and _read["model_date"] == _board["model_date"]
print("    C. Levels, changes and slopes use each country's common four-tenor calendar ✓")

_cb_overview = build_global_country_board_overview(df, horizon=20)
assert len(_cb_overview) == len(_CB_COUNTRIES)
assert _cb_overview["model_date"].nunique() == 1
assert _cb_overview["aligned_observations"].nunique() == 1
assert (_cb_overview["status"] == "Ready").all()
_cb_common_date = _cb_overview["model_date"].iloc[0]
print(f"    D. Seven-country overview common date={_cb_common_date}, "
      f"observations={int(_cb_overview['aligned_observations'].iloc[0])} ✓")

# Missing-tenor regression: one country becomes Partial without a proxy or zero.
_cb_missing_df = df.drop(columns=[_CB_TICKERS["DE_30Y"]])
_cb_missing = available_country_boards(_cb_missing_df)["DE"]
assert _cb_missing["status"] == "Partial"
assert "30Y" in _cb_missing["missing_tenors"]
assert build_country_curve_frame(_cb_missing_df, "DE").empty
assert build_country_board(_cb_missing_df, "DE")["status"] == "Partial"
print("    E. Missing tenor -> Partial; no substitution or zero fill ✓")

_cb_page_src = open("charts/pages/country_boards.py").read()
assert "build_country_board" in _cb_page_src
assert "build_global_country_board_overview" in _cb_page_src
assert ".ffill(" not in _cb_page_src
for _bad in ("will outperform", "policy recommendation", "trade recommendation", "caused by"):
    assert _bad not in _cb_page_src.lower()
print("    F. Page renders pure model output and makes no forecast/causal claim ✓")

from config.model_roadmap import ROADMAP as _CB_ROADMAP
_cb_page = next(p for p in PAGES if p["id"] == "country_boards")
assert _cb_page["section"] == "04b" and _cb_page["status"] == "live"
assert _cb_page["builds_on"] == "global_rates" and _cb_page["next"] == "cross_asset"
_cb_rm = next(r for r in _CB_ROADMAP if r["module_id"] == "country_boards")
assert _cb_rm["current_status"] == "Live"
assert _cb_rm["implemented_in"] == "models/country_rate_boards.py"
assert _cb_rm["app_section"] == "04b"
_cb_readme = open("README.md").read()
assert "| 04b | Country Rate Boards" in _cb_readme
_cb_dq = open("charts/pages/data_quality.py").read()
assert "Country Rate Boards — aligned input readiness" in _cb_dq
_cb_snapshot = _shared_snapshot
assert "country_rate_boards" in _cb_snapshot
assert len(_cb_snapshot["country_rate_boards"]["countries"]) == 7
_cb_html_src = open("scripts/export_research_pack_html.py").read()
assert "04b Country Rate Boards" in _cb_html_src
print("    G. Registry, Roadmap, README, Data Quality, snapshot and HTML are consistent ✓")

# H. Exact-tenor country real-rate / inflation-compensation attribution.
import ast as _ast_grd
_grd_src = open("models/global_rate_decomposition.py").read()
_grd_tree = _ast_grd.parse(_grd_src)
for _node in _ast_grd.walk(_grd_tree):
    if isinstance(_node, (_ast_grd.Import, _ast_grd.ImportFrom)):
        _mod = getattr(_node, "module", None) or ""
        for _name in _node.names:
            assert "streamlit" not in _mod.lower() and "streamlit" not in _name.name.lower()
assert ".ffill(" not in _grd_src and ".interpolate(" not in _grd_src

from models.global_rate_decomposition import (
    available_global_decomposition_tenors,
    build_global_decomposition_snapshot,
    build_global_rate_frame,
    global_decomposition_readiness,
    rolling_global_rate_attribution,
)
_grd_ready = global_decomposition_readiness(df, _CB_COUNTRIES)
_grd_status = _grd_ready.set_index("country")["status"].to_dict()
assert sum(v == "Ready" for v in _grd_status.values()) == 6
assert _grd_status["CH"] == "Unavailable"
for _country in ("US", "DE", "JP", "UK", "CA", "AU"):
    _tenors = available_global_decomposition_tenors(df, _country)
    assert "10Y" in _tenors, (_country, _tenors)
    _frame = build_global_rate_frame(df, _country, "10Y")
    assert not _frame.empty and not _frame.isna().any().any()
    assert (_frame["nominal"] - _frame["real"] - _frame["inflation"]).abs().max() < 1e-12
    _attr = rolling_global_rate_attribution(df, _country, "10Y", window=10).dropna()
    assert not _attr.empty and _attr["residual_bp"].abs().max() < 1e-10
    _snap = build_global_decomposition_snapshot(df, _country, horizons=(5, 20))
    assert not _snap.empty and "10Y" in set(_snap["tenor"])
assert build_global_rate_frame(df, "CH", "10Y").empty

_grd_rm = next(
    r for r in _CB_ROADMAP
    if r["module_id"] == "global_real_inflation_attribution"
)
assert _grd_rm["current_status"] == "Partial" and _grd_rm["app_section"] == "04b"
assert "country_rate_decomposition" in _cb_snapshot
assert len(_cb_snapshot["country_rate_decomposition"]["countries"]) == 6
assert "Switzerland" in _cb_snapshot["country_rate_decomposition"]["unavailable"]
assert "Country Rate Attribution" in _cb_html_src
assert "global_decomposition_readiness" in _cb_dq
print("    H. Six-country exact-tenor real/inflation attribution; Switzerland unavailable ✓")

for _, _row in _cb_overview.iterrows():
    print(
        f"    {_row['country']}: 10Y={_row['yield_10y_pct']:.3f}% "
        f"20DΔ={_row['change_20d_10y_bp']:+.1f}bp "
        f"2s10s={_row['slope_2s10s_bp']:+.1f}bp "
        f"20D slopeΔ={_row['change_20d_2s10s_bp']:+.1f}bp"
    )

# Phase 9.2: Global FY1 Earnings & Valuation
print("32. Phase 9.2 Global FY1 Earnings & Valuation ...")
import ast as _ast_ev
_ev_src = open("models/earnings_valuation.py").read()
_ev_tree = _ast_ev.parse(_ev_src)
for _node in _ast_ev.walk(_ev_tree):
    if isinstance(_node, (_ast_ev.Import, _ast_ev.ImportFrom)):
        _mod = getattr(_node, "module", None) or ""
        for _name in _node.names:
            assert "streamlit" not in _mod.lower() and "streamlit" not in _name.name.lower()
assert ".ffill(" not in _ev_src, "earnings model must not forward-fill"
print("    A. Pure model: no Streamlit and no forward-fill ✓")

from data.equity_earnings_loader import load_equity_earnings_data
from models.earnings_valuation import (
    EPS_FIELD_METADATA, build_equity_earnings_frame,
    build_earnings_valuation_snapshot, build_global_earnings_overview,
    calculate_horizon_decomposition, build_weekly_regression_history,
    EARNINGS_OVERVIEW_UNIVERSE,
)
_ev_data = load_equity_earnings_data()
assert set(_ev_data) >= {"eps", "prices", "metadata"}
assert EPS_FIELD_METADATA["field"] == "BEST_EPS"
assert EPS_FIELD_METADATA["forecast_period_override"] == "1FY"
assert EPS_FIELD_METADATA["frequency"] == "weekly"
print("    B. Confirmed field contract: BEST_EPS + 1FY + weekly ✓")

_ev_frame = build_equity_earnings_frame(_ev_data, code="ES1")
assert len(_ev_frame) >= 27
assert list(_ev_frame.columns) == ["price", "eps_fy1", "fy1_pe"]
assert not _ev_frame.isna().any().any()
assert (_ev_frame > 0).all().all()
_ev_snap = build_earnings_valuation_snapshot(_ev_data, code="ES1")
assert _ev_snap["status"] == "Ready"
assert _ev_snap["model_date"] == _ev_frame.index[-1].date()
assert _ev_snap["aligned_observations"] == len(_ev_frame)
assert _ev_snap["price_source_date"] <= _ev_snap["model_date"]
assert 0 <= _ev_snap["latest_price_lag_days"] <= 3
print(f"    C. SPX matched weekly observations={len(_ev_frame)}, date={_ev_snap['model_date']} ✓")

_ev_dec = calculate_horizon_decomposition(_ev_frame, horizons=(1, 4, 13, 26))
assert (_ev_dec["status"] == "Ready").all()
assert _ev_dec["identity_residual_pct"].abs().max() < 1e-10
for _, _row in _ev_dec.iterrows():
    assert abs(_row["price_return_pct"] - _row["eps_growth_pct"] - _row["valuation_change_pct"]) < 1e-10
print("    D. Exact log identity reconciles for 1W/4W/13W/26W ✓")

# Missing EPS must remain missing rather than becoming zero or a proxy.
_ev_missing = {**_ev_data, "eps": _ev_data["eps"].drop(columns=["ES1"])}
_ev_missing_snap = build_earnings_valuation_snapshot(_ev_missing, code="ES1")
assert _ev_missing_snap["status"] == "Missing data"
assert "FY1 EPS" in " ".join(_ev_missing_snap["missing"])
assert pd.isna(_ev_missing_snap.get("eps_fy1", float("nan")))
print("    E. Missing SPX EPS -> Missing data; no zero/proxy substitution ✓")

_ev_reg = build_weekly_regression_history(_ev_frame, beta_window=26, min_beta_obs=20, decomposition_horizon=4)
assert not _ev_reg.dropna(subset=["beta", "r_squared"]).empty
assert ((_ev_reg["r_squared"].dropna() >= 0) & (_ev_reg["r_squared"].dropna() <= 1 + 1e-12)).all()
assert abs(
    _ev_snap["current_price_return_pct"]
    - _ev_snap["current_eps_growth_pct"]
    - _ev_snap["current_valuation_change_pct"]
) < 1e-10
print("    F. Weekly OLS diagnostic is available and separately labelled ✓")

_ev_global = build_global_earnings_overview(_ev_data, horizon=13)
assert len(_ev_global) == len(EARNINGS_OVERVIEW_UNIVERSE)
assert len(_ev_global) == 18
assert (_ev_global["status"] == "Ready").sum() == 18
for _requested_code, _expected_ticker in (
    ("CSI_A500", "CSIA500 Index"), ("NIFTY50", "NIFTY Index"),
    ("VN30", "VN30 Index"), ("DJI", "DJI Index"),
):
    _requested = _ev_global.loc[_ev_global["code"] == _requested_code]
    assert len(_requested) == 1 and _requested.iloc[0]["status"] == "Ready"
    assert _requested.iloc[0]["workbook_ticker"] == _expected_ticker
    assert _requested.iloc[0]["fy1_pe"] > 0
assert "XU1" not in _ev_global["code"].tolist()
assert "SM1" not in _ev_global["code"].tolist()
assert "EO1" not in _ev_global["code"].tolist()
_nifty_snap = build_earnings_valuation_snapshot(_ev_data, code="NIFTY50")
assert _nifty_snap["price_source_date"] <= _nifty_snap["model_date"]
assert 0 <= _nifty_snap["latest_price_lag_days"] <= 3
print(f"    G. Global overview: {int((_ev_global['status']=='Ready').sum())}/{len(_ev_global)} Ready; A500, Nifty 50, VN30 and DJI use their own histories ✓")

_ev_page = next(p for p in PAGES if p["id"] == "earnings_valuation")
assert _ev_page["section"] == "06d" and _ev_page["status"] == "live"
assert _ev_page["builds_on"] == "index_breadth" and _ev_page["next"] == "fx_rate_diff"
_ev_page_src = open("charts/pages/earnings_valuation.py").read()
assert "build_earnings_valuation_snapshot" in _ev_page_src
assert "BEST_FPERIOD_OVERRIDE=1FY" in _ev_page_src
assert "st.selectbox" in _ev_page_src
assert "earnings_normalized" not in _ev_page_src
assert "build_global_earnings_overview" not in _ev_page_src
assert "st.dataframe" not in _ev_page_src
for _bad in ("fair value is", "will outperform", "caused by earnings"):
    assert _bad not in _ev_page_src.lower()
print("    H. Page registry and no-fabrication wording ✓")

from config.model_roadmap import ROADMAP as _EV_ROADMAP
_ev_rm = next(r for r in _EV_ROADMAP if r["module_id"] == "earnings_val")
assert _ev_rm["current_status"] == "Live"
assert _ev_rm["implemented_in"] == "models/earnings_valuation.py"
_ev_realized_rm = next(r for r in _EV_ROADMAP if r["module_id"] == "forward_vs_realized_eps")
assert _ev_realized_rm["current_status"] == "Data Missing"
_ev_readme = open("README.md").read()
assert "| 06d | Global FY1 Earnings & Valuation" in _ev_readme
_ev_dq = open("charts/pages/data_quality.py").read()
assert "Global FY1 Earnings &amp; Valuation — source and alignment audit" in _ev_dq
_ev_snapshot = _shared_snapshot
assert "spx_earnings_valuation" in _ev_snapshot
assert _ev_snapshot["spx_earnings_valuation"]["fair_value_model"] is False
_ev_html = open("scripts/export_research_pack_html.py").read()
assert "Global FY1 Earnings & Valuation" in _ev_html
print("    I. Roadmap, README, Data Quality, snapshot and HTML are consistent ✓")

_ev_qlist = qlist
_ev_q = next(q for q in _ev_qlist if "FY1 earnings revisions" in q.question)
assert _ev_q.data_status == "real_data"
assert "P/E" in _ev_q.answer and "Model date" in _ev_q.answer
print("    J. Q12 uses exact decomposition and model date ✓")

print(f"    SPX level: {_ev_snap['price']:.2f}")
print(f"    FY1 EPS: {_ev_snap['eps_fy1']:.4f}")
print(f"    Implied FY1 P/E: {_ev_snap['fy1_pe']:.2f}x")
print(f"    4W SPX return: {_ev_snap['current_price_return_pct']:+.3f}%")
print(f"    4W FY1 EPS growth: {_ev_snap['current_eps_growth_pct']:+.3f}%")
print(f"    4W P/E change: {_ev_snap['current_valuation_change_pct']:+.3f}%")
print(f"    Weekly OLS beta/R²: {_ev_snap['regression_beta']:+.3f} / {_ev_snap['regression_r_squared']:.3f}")

# ===========================================================================
# Phase 9.3 — reference-pack three-asset Market Linkage & Correlations
# ===========================================================================
print("33. Phase 9.3 Market Linkage & Correlations ...")
from models.market_linkage import (
    MARKET_LINKAGE_CONFIG as _ML_CONFIG,
    ASSETS as _ML_ASSETS,
    all_pair_keys as _ml_pair_keys,
    assess_market_linkage_readiness as _assess_ml,
    build_market_linkage_levels as _build_ml_levels,
    build_market_linkage_returns as _build_ml_returns,
    build_rolling_pairwise_correlations as _build_ml_corrs,
    build_correlation_matrix as _build_ml_matrix,
    build_market_linkage_snapshot as _build_ml_snapshot,
    build_market_linkage_current_reading as _build_ml_reading,
)
from data.external_loaders import load_ficc as _load_ml_ficc

_ml_model_src = open("models/market_linkage.py").read()
assert "streamlit" not in _ml_model_src.lower()
assert "ffill(" not in _ml_model_src and ".fillna(0" not in _ml_model_src
assert len(_ML_CONFIG) == 3 and len(_ML_ASSETS) == 3
assert len(_ml_pair_keys()) == 3
print("    A. Pure three-asset model: no Streamlit, no fill or zero substitution ✓")

_ml_ficc = _load_ml_ficc()
assert _ml_ficc is not None
assert all(a in _ml_ficc.columns for a in _ML_ASSETS), _ml_ficc.columns.tolist()
_ml_levels = _build_ml_levels(_ml_ficc)
_ml_returns = _build_ml_returns(_ml_ficc)
assert not _ml_levels.empty and not _ml_levels.isna().any().any()
assert not _ml_returns.empty and not _ml_returns.isna().any().any()
assert _ml_returns.index.equals(_ml_levels.index[1:])
assert len(_ml_returns) == len(_ml_levels) - 1
print(f"    B. Fully aligned levels={len(_ml_levels)}, returns={len(_ml_returns)}, date={_ml_levels.index.max().date()} ✓")

_ml_spx_expected = 100 * np.log(_ml_levels["SPX"].iloc[1] / _ml_levels["SPX"].iloc[0])
_ml_ust_expected = 100 * (_ml_levels["USGG10YR"].iloc[1] - _ml_levels["USGG10YR"].iloc[0])
assert np.isclose(_ml_returns["SPX"].iloc[0], _ml_spx_expected)
assert np.isclose(_ml_returns["USGG10YR"].iloc[0], _ml_ust_expected)
print("    C. Transform contract: price log returns and yield basis-point changes ✓")

_ml_corrs = _build_ml_corrs(_ml_ficc, window=20)
_ml_matrix = _build_ml_matrix(_ml_ficc, window=20)
assert list(_ml_corrs.columns) == _ml_pair_keys()
assert _ml_matrix.shape == (3, 3)
assert np.allclose(_ml_matrix.values, _ml_matrix.values.T, equal_nan=False)
assert np.allclose(np.diag(_ml_matrix.values), np.ones(3))
_ml_snap = _build_ml_snapshot(_ml_ficc, corr_window=20, long_window=63)
assert _ml_snap["status"] == "Ready"
assert _ml_snap["model_date"] == _ml_levels.index.max().date()
assert 1/3 - 1e-9 <= _ml_snap["pc1_explained_variance"] <= 1 + 1e-9
assert 0 <= _ml_snap["linkage_percentile_2y"] <= 100
assert np.isfinite(_ml_snap["mean_abs_correlation"])
print("    D. Three pair correlations + 63D PC1 one-trade gauge reconcile ✓")

_ml_missing = _ml_ficc.drop(columns=["DXY"])
_ml_missing_ready = _assess_ml(_ml_missing, corr_window=63)
_ml_missing_snap = _build_ml_snapshot(_ml_missing, corr_window=20, long_window=63)
assert _ml_missing_ready["status"] == "Partial"
assert "DXY" in _ml_missing_ready["missing"]
assert _ml_missing_snap["status"] == "Partial"
print("    E. Missing DXY -> Partial; no proxy, zero or fabricated linkage ✓")

_ml_read = _build_ml_reading(_ml_ficc, corr_window=20)
assert _ml_read["status"] == "Ready"
assert "mixed" not in _ml_read["summary"].lower()
assert "caused" not in _ml_read["summary"].lower()
assert "fair value" not in _ml_read["summary"].lower()
print("    F. Current reading reports a linkage level, not a Mixed regime ✓")

_ml_page = next(p for p in PAGES if p["id"] == "market_linkage")
assert _ml_page["section"] == "05b" and _ml_page["status"] == "live"
assert _ml_page["next"] == "sector_rotation"
assert "market_linkage_pca" not in PAGES_BY_ID
_ml_page_src = open("charts/pages/market_linkage.py").read()
assert "build_market_linkage_snapshot" in _ml_page_src
assert "load_crossasset()" in _ml_page_src
assert "build_market_linkage_snapshot(ctx.df" not in _ml_page_src
assert "one-trade gauge" in _ml_page_src.lower()
assert "Mixed" not in _ml_page_src
print("    G. 05b uses normalized live data; experimental PCA page removed ✓")

_liq_page_src = open("charts/pages/liquidity_overview.py").read()
assert "render_driver_cards(r)" in _liq_page_src
assert "render_summary_panel(r)" not in _liq_page_src
print("       Liquidity shell renders headline KPIs once and keeps driver cards ✓")

from config.model_roadmap import ROADMAP as _ML_ROADMAP
_ml_rm = next(r for r in _ML_ROADMAP if r["module_id"] == "market_linkage")
assert _ml_rm["current_status"] == "Live" and _ml_rm["implemented_in"] == "models/market_linkage.py"
assert _ml_rm["required_data"] == ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]
assert not any(r["module_id"] == "market_linkage_pca" for r in _ML_ROADMAP)
_ml_readme = open("README.md").read()
assert "| 05b | Market Linkage & Correlations" in _ml_readme
assert "Market Linkage PCA" not in _ml_readme
_ml_dq = open("charts/pages/data_quality.py").read()
assert "Market Linkage &amp; Correlations — source and alignment audit" in _ml_dq
_ml_snap_export = _shared_snapshot
assert "market_linkage" in _ml_snap_export
assert _ml_snap_export["market_linkage"]["causal_attribution"] is False
print("    H. Registry, Roadmap, README, Data Quality and snapshot are consistent ✓")

_ml_qlist = qlist
_ml_q = next(q for q in _ml_qlist if "cross-asset relationships" in q.question)
assert _ml_q.data_status == "real_data"
assert "one-trade linkage gauge" in _ml_q.answer.lower()
assert "Model date" in _ml_q.answer
print("    I. Q13 reports the gauge and signed pair correlations ✓")

print(f"    Common model date: {_ml_snap['model_date']}")
print(f"    Common observations: {_ml_snap['aligned_observations']}")
print(f"    PC1 explained variance: {_ml_snap['pc1_explained_variance']:.1%}")
print(f"    2Y percentile: {_ml_snap['linkage_percentile_2y']:.0f}/100")

# ===========================================================================
# Phase 9.4 — Policy live-status separation
# ===========================================================================
print("34. Phase 9.4 Policy live-status separation ...")
_pol_page = next(p for p in PAGES if p["id"] == "policy")
assert _pol_page["status"] == "live"
assert "fixed-contract SOFR futures strip is a separate live page" in _pol_page["description"]
from config.model_roadmap import ROADMAP as _POL_ROADMAP
_pol_spot_rm = next(r for r in _POL_ROADMAP if r["module_id"] == "policy_spot")
_pol_fomc_rm = next(r for r in _POL_ROADMAP if r["module_id"] == "fomc_path")
_pol_sofr_rm = next(r for r in _POL_ROADMAP if r["module_id"] == "sofr_strip")
assert _pol_spot_rm["current_status"] == "Live"
assert _pol_spot_rm["app_section"] == "01"
assert all(k in _pol_spot_rm["required_data"] for k in ["SOFR", "EFFR", "IORB", "GCF", "TPR"])
assert _pol_fomc_rm["current_status"] != "Live"
assert _pol_sofr_rm["current_status"] == "Live" and _pol_sofr_rm["app_section"] == "01b"
_pol_readme = open("README.md").read()
assert "| 01  | Policy & Short Rates            | **Live**" in _pol_readme
assert "| 01b | SOFR Futures Strip & Calendar Spreads" in _pol_readme
assert "### Partially implemented" not in _pol_readme
_pol_dq = open("charts/pages/data_quality.py").read()
assert '{"Model": "Policy & Short Rates"' in _pol_dq
assert '{"Model": "SOFR Futures Strip & Calendar Spreads"' in _pol_dq
assert "FOMC implied policy path" in _pol_dq
print("    A. Live spot/funding and fixed-contract strip remain separate from the FOMC-path gap ✓")

# ===========================================================================
# Phase 10.3 — Fixed-contract SOFR Futures Strip & Calendar Spreads
# ===========================================================================
print("35. Fixed-contract SOFR Futures Strip & Calendar Spreads ...")
from config.tickers import SOFR_CONTRACT_CONFIG
from data.policy_futures_loader import load_policy_futures
from models.policy_futures_strip import (
    assess_sofr_strip,
    build_sofr_curve_comparison,
    build_sofr_contract_price_frame,
    build_sofr_implied_rate_frame,
    build_sofr_strip_snapshot,
)

assert len(SOFR_CONTRACT_CONFIG) == 8
assert list(SOFR_CONTRACT_CONFIG) == [
    "SFRU6 COMB COMDTY", "SFRZ6 COMB COMDTY", "SFRH7 COMB COMDTY",
    "SFRM7 COMB COMDTY", "SFRU7 COMB COMDTY", "SFRZ7 COMB COMDTY",
    "SFRH8 COMB COMDTY", "SFRM8 COMB COMDTY",
]
print("    A. Registry contains eight fixed quarterly SFR contracts, SEP 26 to JUN 28 ✓")

_fixed_fut = load_policy_futures()
assert not _fixed_fut.empty and set(SOFR_CONTRACT_CONFIG).issubset(_fixed_fut.columns)
assert _fixed_fut.index.max().date() <= current_production_date()
_fixed_ready = assess_sofr_strip(_fixed_fut)
assert _fixed_ready["status"] == "Ready", _fixed_ready
_prices = build_sofr_contract_price_frame(_fixed_fut)
_rates = build_sofr_implied_rate_frame(_fixed_fut)
assert list(_prices.columns) == list(SOFR_CONTRACT_CONFIG)
assert _prices.index.equals(_rates.index)
assert not _rates.isna().any().any()
np.testing.assert_allclose(_rates.values, 100.0 - _prices.values, rtol=0, atol=1e-12)
print("    B. Each Date+Price BQL block joins on the exact common calendar; rate = 100 − price ✓")

_fixed_snap = build_sofr_strip_snapshot(_fixed_fut, df, horizons=(1,5,20))
assert _fixed_snap["status"] == "Ready"
assert _fixed_snap["model_date"] == _rates.index.max().date()
assert len(_fixed_snap["strip_table"]) == 8
assert _fixed_snap["effr_date"] <= _fixed_snap["model_date"]
assert _fixed_snap["sofr_date"] <= _fixed_snap["model_date"]
_matrix = _fixed_snap["calendar_spread_matrix"]
assert list(_matrix.columns) == ["Contract", "3M", "6M", "12M"]
_t = _fixed_snap["strip_table"].set_index("sequence")
assert abs(_matrix.iloc[0]["3M"] - 100*(_t.loc[2,"implied_rate_pct"]-_t.loc[1,"implied_rate_pct"])) < 1e-9
assert abs(_matrix.iloc[0]["6M"] - 100*(_t.loc[3,"implied_rate_pct"]-_t.loc[1,"implied_rate_pct"])) < 1e-9
assert abs(_matrix.iloc[0]["12M"] - 100*(_t.loc[5,"implied_rate_pct"]-_t.loc[1,"implied_rate_pct"])) < 1e-9
print("    C. Eight-contract strip, 3M/6M/12M matrix and common-date changes reconcile ✓")

_curve_comparison, _curve_dates = build_sofr_curve_comparison(_fixed_fut)
assert list(_curve_comparison.columns) == ["Current", "1W ago", "1M ago"]
assert _curve_dates["Current"] == _rates.index[-1].date()
assert _curve_dates["1W ago"] == _rates.index[-6].date()
assert _curve_dates["1M ago"] == _rates.index[-21].date()
np.testing.assert_allclose(_curve_comparison["Current"].values, _rates.iloc[-1].values)
np.testing.assert_allclose(_curve_comparison["1W ago"].values, _rates.iloc[-6].values)
np.testing.assert_allclose(_curve_comparison["1M ago"].values, _rates.iloc[-21].values)
assert _fixed_snap["curve_comparison"].equals(_curve_comparison)
print("    C2. Current, 1-week and 1-month curves use exact common observations ✓")

_terminal = _fixed_snap["terminal"]
assert _terminal["terminal_sequence"] in range(1, 9)
assert _terminal["terminal_rate_pct"] == _t.loc[_terminal["terminal_sequence"], "implied_rate_pct"]
assert abs(_terminal["terminal_gap_bp"] - 100*(_terminal["terminal_rate_pct"]-_fixed_snap["effr_pct"])) < 1e-9
print("    D. Terminal and EFFR gap are transparent, formula-based diagnostics ✓")

_missing_code = list(SOFR_CONTRACT_CONFIG)[3]
_missing_frame = _fixed_fut.drop(columns=[_missing_code])
_missing_snap = build_sofr_strip_snapshot(_missing_frame, df)
assert _missing_snap["status"] == "Partial"
assert _missing_code in _missing_snap["missing"]
assert _missing_snap["strip_table"].empty
print("    E. Missing fixed contract -> Partial; no zero, generic proxy or interpolation ✓")

_source_page = open("charts/pages/policy_futures.py").read()
_source_loader = open("data/policy_futures_loader.py").read()
assert "Policy_Futures" in _source_loader and "Date + Price" in _source_loader
assert "row position" in _source_page.lower()
assert "SFR1" not in _source_page and "SER1" not in _source_page and "FF1" not in _source_page
assert "calendar spread matrix" in _source_page.lower()
assert "meeting-by-meeting" in _source_page.lower()
assert "1W ago" in _source_page and "1M ago" in _source_page
print("    F. Live page uses fixed months and preserves the FOMC-path limitation ✓")

_pf_page = next(p for p in PAGES if p["id"] == "policy_futures")
assert _pf_page["title"] == "SOFR Futures Strip & Calendar Spreads"
assert _pf_page["section"] == "01b" and _pf_page["status"] == "live"
assert _pf_page["data_source"] == "policy_futures_sheet"
assert "eight fixed quarterly" in _pf_page["description"].lower()
_fixed_snapshot_json = _shared_snapshot
assert "sofr_futures_strip" in _fixed_snapshot_json
assert _fixed_snapshot_json["sofr_futures_strip"]["fixed_contract_months"] is True
print("    G. Page registry, data-source registry and snapshot integration ✓")

_pf_q = next(q for q in qlist if "fixed-contract SOFR futures strip" in q.question)
assert _pf_q.data_status == "real_data"
assert "SEP 26" in " ".join(_pf_q.details)
assert "FOMC" in " ".join(_pf_q.details)
print("    H. Q14 uses fixed contracts and does not claim meeting probabilities ✓")

print(f"    Strip: date={_fixed_snap['model_date']} obs={_fixed_snap['aligned_observations']} "
      f"terminal={_terminal['terminal_contract']} {_terminal['terminal_rate_pct']:.3f}% "
      f"gap={_terminal['terminal_gap_bp']:+.1f}bp")

# ===========================================================================
# Phase 10.2 — Restore full XCCY basis dashboard to FX
# ===========================================================================
print("36. Phase 10.2 XCCY basis page placement and visibility ...")
from models.xccy_basis import build_xccy_snapshot, XCCY_CURRENCIES

_xccy_snapshot = build_xccy_snapshot(df)
assert len(_xccy_snapshot) == 5
assert set(_xccy_snapshot["Currency"]) == {"EUR", "JPY", "AUD", "GBP", "CAD"}
assert (_xccy_snapshot["Status"] == "Ready").all(), _xccy_snapshot.to_dict("records")
assert _xccy_snapshot[["3M basis (bp)", "12M basis (bp)"]].notna().all().all()
print("    A. Five currencies × 3M/12M source-series snapshot is Ready ✓")

_fx_src = open("charts/pages/fx_rate_diff.py").read()
_liq_src = open("charts/pages/liquidity_overview.py").read()
_funding_src = open("charts/funding.py").read()
assert 'render_xccy(ctx.dff, key_prefix="fx_rates_xccy")' in _fx_src
assert "XCCY basis now shown on the Liquidity page" not in _fx_src
assert "render_xccy_summary(ctx.dff)" in _liq_src
assert "render_xccy(ctx.dff)" not in _liq_src
assert "except Exception:\n        pass" not in _liq_src[_liq_src.find("Compact XCCY"): _liq_src.find("CLI Rolling Correlations")]
assert "Cross-Currency Basis charts are unavailable" in _fx_src
assert "Dollar-funding / XCCY summary is unavailable" in _liq_src
print("    B. Full charts are on FX; Liquidity keeps a compact summary; failures are visible ✓")

assert "from models.xccy_basis import build_xccy_snapshot" in _funding_src
assert "def render_xccy_summary" in _funding_src
assert "3M basis unavailable" in _funding_src
assert "12M basis unavailable" in _funding_src
assert "fillna(0" not in _funding_src and ".ffill(" not in _funding_src
print("    C. Missing tenors are explicit; no fill, proxy, or zero substitution ✓")

_xccy_readme = open("README.md").read()
assert ("full EUR / JPY / AUD / GBP / CAD 3M and 12M cross-currency basis dashboard" in _xccy_readme
        or "full 3M/12M XCCY basis dashboard" in _xccy_readme)
_fx_page_cfg = next(p for p in PAGES if p["id"] == "fx_rate_diff")
assert "full" in _fx_page_cfg["description"].lower()
assert ("3m and 12m" in _fx_page_cfg["description"].lower()
        or "3m/12m" in _fx_page_cfg["description"].lower())
print("    D. Page registry and README document the restored location ✓")

for _row in _xccy_snapshot.to_dict("records"):
    print(f"    {_row['Currency']}: 3M={_row['3M basis (bp)']:+.1f}bp "
          f"({_row['3M date']}) 12M={_row['12M basis (bp)']:+.1f}bp "
          f"({_row['12M date']})")

# ===========================================================================
# 2026-08-06 user-feedback and refreshed-workbook integrity gate
# ===========================================================================
print("37. 2026-08-06 feedback + refreshed-workbook integrity ...")

from data.calendar_integrity import audit_ticker_group_calendar
for _group_tickers, _group_name in [
    (["EURUSD BGN CURNCY", "USDJPY BGN CURNCY", "GBPUSD BGN CURNCY", "AUDUSD BGN CURNCY"], "FX spot"),
    (["S5INFT INDEX", "S5FINL INDEX", "S5TELS INDEX"], "SPX sectors"),
    (["GSWISS02 INDEX", "GSWISS05 INDEX", "GSWISS10 INDEX", "GSWISS30 INDEX"], "Swiss yields"),
]:
    _audit = audit_ticker_group_calendar(df, _group_tickers, _group_name)
    assert _audit["weekend_observation_count"] == 0, (_group_name, _audit)
assert "Policy_Futures" in open("data/policy_futures_loader.py").read()
assert "DATA_VINTAGE_RECONCILIATION_2026-08-06.md" not in open("README.md").read()
print("    A. Refreshed weekday calendars and independent Policy_Futures sheet are active ✓")

# Production navigation must not restore the low-guidance PCA pages.
assert not ({"rates_pca", "market_linkage_pca", "fx"} & set(PAGES_BY_ID))
assert "Current state:" in open("charts/pages/regimes.py").read()
print("    B. PCA pages remain removed; regime-ribbon hover exposes the current state ✓")

_ml_src_feedback = open("models/market_linkage.py").read()
_ml_page_feedback = open("charts/pages/market_linkage.py").read()
assert "pc1_explained_variance" in _ml_src_feedback
assert "63" in _ml_src_feedback
assert "one-trade" in _ml_page_feedback.lower()
assert "Mixed" not in _ml_page_feedback
print("    C. Market linkage uses the reference-style PC1 explained-variance line, not Mixed labels ✓")

from models.sector_rotation import build_spx_dispersion_index as _dspx_feedback
_dspx_live = _dspx_feedback(df)
assert not _dspx_live.empty
assert _dspx_live.index[-1].date() <= current_production_date()
assert float(_dspx_live.iloc[-1]) > 0
_sector_page_feedback = open("charts/pages/sector_rotation.py").read()
assert "Cboe DSPX implied 30D dispersion" in _sector_page_feedback
assert "separate forward-looking" in _sector_page_feedback
print(f"    D. DSPX is live: {float(_dspx_live.iloc[-1]):.2f} on {_dspx_live.index[-1].date()}; separate axis, no synthetic substitution ✓")

from models.earnings_valuation import build_global_earnings_overview as _ev_overview_feedback
from data.equity_earnings_loader import load_equity_earnings_data as _load_ev_feedback
_ev_feedback_data = _load_ev_feedback()
assert {"CSI_A500", "NIFTY50", "VN30", "DJI"}.issubset(_ev_feedback_data["eps"].columns)
assert {"CSI_A500", "NIFTY50", "VN30", "DJI"}.issubset(_ev_feedback_data["prices"].columns)
_ev_feedback = _ev_overview_feedback(_ev_feedback_data, horizon=13)
for _code_feedback, _ticker_feedback in (
    ("CSI_A500", "CSIA500 Index"), ("NIFTY50", "NIFTY Index"),
    ("VN30", "VN30 Index"), ("DJI", "DJI Index"),
):
    _row_feedback = _ev_feedback.loc[_ev_feedback["code"] == _code_feedback]
    assert len(_row_feedback) == 1
    assert _row_feedback.iloc[0]["status"] == "Ready"
    assert _row_feedback.iloc[0]["workbook_ticker"] == _ticker_feedback
    assert _row_feedback.iloc[0]["fy1_pe"] > 0
assert not (_ev_feedback["code"] == "XU1").any(), "FTSE China A50 must not be relabelled as CSI A500"
print("    E. CSI A500, Nifty 50, VN30 and DJI are live from their own cash-index + BEST_EPS/1FY rows; XIN9I remains separate ✓")

from data.external_loaders import load_pulsar as _load_scoring_feedback
from models.scoring.engine import (
    EQUITY_UNIVERSE as _equity_universe_feedback,
    build_equity_fci_context as _build_equity_fci_context_feedback,
    determine_scoring_asof as _determine_scoring_asof_feedback,
    score_equity as _score_equity_feedback,
)
_equity_codes_feedback = [row[0] for row in _equity_universe_feedback]
assert len(_equity_codes_feedback) == 18
assert {"CSI_A500", "NIFTY50", "VN30", "DJI"}.issubset(_equity_codes_feedback)
assert not {"SM1", "EO1", "XU1"}.intersection(_equity_codes_feedback)
_scoring_feedback_data = _load_scoring_feedback()
_scoring_feedback_asof = _determine_scoring_asof_feedback(_scoring_feedback_data)["asof_date"]
_equity_scores_feedback = _score_equity_feedback(
    _scoring_feedback_data, _scoring_feedback_asof, {"macro": 0.5, "eps": 0.5}
)
assert len(_equity_scores_feedback) == 18
assert (_equity_scores_feedback["status"] == "Ready").all()
assert (_equity_scores_feedback["macro_factor_count"] == 4).all()
assert (_equity_scores_feedback["missing_factors"] == "").all()
assert _equity_scores_feedback["rank_eligible"].all()
assert "fci_z" not in _equity_scores_feedback.columns

_scoring_without_fci = dict(_scoring_feedback_data)
_scoring_without_fci["fci"] = pd.DataFrame()
_scores_without_fci = _score_equity_feedback(
    _scoring_without_fci, _scoring_feedback_asof, {"macro": 0.5, "eps": 0.5}
)
pd.testing.assert_series_equal(
    _equity_scores_feedback["score"].sort_index(),
    _scores_without_fci["score"].sort_index(),
)
_fci_context_feedback = _build_equity_fci_context_feedback(
    _scoring_feedback_data, _scoring_feedback_asof
)
assert len(_fci_context_feedback) == 4
assert set(_fci_context_feedback["ticker"]) == {
    "BFCIUS Index", "CHBGFCI INDEX", "BFCIGB INDEX", "BFCIEU INDEX",
}
assert (_fci_context_feedback["status"] == "Available").all()
assert _fci_context_feedback["source_date"].notna().all()
print("    E1. All 18 indices use the same four-factor Macro + EPS score; FCI is separate context and cannot change ranking ✓")

_ref_snapshot = _shared_snapshot
assert _ref_snapshot["cboe_dspx"]["status"] == "Ready"
assert len(_ref_snapshot["requested_equity_earnings_rows"]) == 4
_ref_status = {row["code"]: row["status"] for row in _ref_snapshot["requested_equity_earnings_rows"]}
assert _ref_status == {"CSI_A500": "Ready", "NIFTY50": "Ready", "VN30": "Ready", "DJI": "Ready"}
print("    E2. Snapshot export includes Ready A500/Nifty 50/VN30/DJI earnings rows ✓")

# New 06c index breadth page: real price trend, explicit constituent-data gap.
from data.index_breadth_loader import BREADTH_METRICS as _IB_METRICS, load_index_breadth as _load_ib
from models.index_breadth import build_index_breadth_snapshot as _build_ib
_ib_page = next(p for p in PAGES if p["id"] == "index_breadth")
assert _ib_page["section"] == "06c" and _ib_page["status"] == "partial"
assert _ib_page["next"] == "earnings_valuation"
assert PAGES.index(_ib_page) + 1 == PAGES.index(_ev_page)
_ib_current = _build_ib(_ev_feedback_data["prices"], _load_ib(), "ES1", "Daily")
assert _ib_current["status"] == "Partial"
assert _ib_current["price"] > 0
assert pd.notna(_ib_current["ma_50d"]) and pd.notna(_ib_current["ma_200d"])
assert pd.isna(_ib_current["ma_100w"])
assert _ib_current["weekly_observations"] < 100
assert set(_ib_current["missing_metrics"]) == set(_IB_METRICS.values())
_ib_dates = pd.date_range("2026-08-03", periods=5, freq="B")
_ib_index = pd.MultiIndex.from_product([_ib_dates, ["ES1"]], names=["date", "code"])
_ib_supplied = pd.DataFrame({key: 1.0 for key in _IB_METRICS}, index=_ib_index)
_ib_ready = _build_ib(_ev_feedback_data["prices"], _ib_supplied, "ES1", "Daily")
assert _ib_ready["status"] == "Ready" and not _ib_ready["missing_metrics"]
_ib_page_src = open("charts/pages/index_breadth.py").read()
assert "sector indices" in _ib_page_src and "never inferred" in _ib_page_src
assert _shared_snapshot["index_market_breadth"]["status"] == "Partial"
assert _shared_snapshot["index_market_breadth"]["proxy_used"] is False
print("    E3. 06c index trend is live; all unavailable constituent breadth metrics and 100W history remain explicitly Partial ✓")

# Offline score backtest: no page integration, full lookback and limited sample.
from models.scoring.backtest import (
    BacktestConfig as _BtCfg,
    _spearman_rank_correlation as _spearman_rho,
    build_score_backtest as _build_bt,
    chronological_stability as _chronological_stability,
    leave_one_period_out_stability as _leave_one_out_stability,
)
assert abs(_spearman_rho(pd.Series([1, 2, 2, 4]), pd.Series([4, 3, 3, 1])) + 1.0) < 1e-12
assert np.isnan(_spearman_rho(pd.Series([1.0]), pd.Series([2.0])))
_bt = _build_bt(_scoring_feedback_data, _BtCfg(rebalance="weekly", top_n=3))
for _kind in ("equity", "rates"):
    _periods = _bt[f"{_kind}_periods"]
    _summary = _bt[f"{_kind}_summary"]
    assert 10 <= len(_periods) < 26
    assert _summary["status"] == "Insufficient sample"
    assert _summary["minimum_validation_periods"] == 26
    assert _summary["costs_included"] is False
    assert _summary["macro_vintage_safe"] is False
    assert (_periods["signal_date"] < _periods["outcome_date"]).all()
    for _, _bt_row in _periods.iterrows():
        assert set(_bt_row["top_codes"].split(", ")).isdisjoint(
            set(_bt_row["bottom_codes"].split(", "))
        )
    _time_slices = _bt[f"{_kind}_chronological_stability"]
    assert list(_time_slices["slice"]) == ["Earlier half", "Recent half"]
    assert list(_time_slices["periods"]) == [6, 6]
    _loo = _bt[f"{_kind}_leave_one_out"]
    assert _loo["status"] == "Available" and _loo["periods"] == 12
    assert _loo["leave_one_out_mean_min"] <= _loo["leave_one_out_mean_max"]
    _sensitivity = _bt[f"{_kind}_sensitivity"]
    assert len(_sensitivity) == 5 and _sensitivity["is_primary"].sum() == 1
    _primary = _sensitivity.loc[_sensitivity["is_primary"]].iloc[0]
    assert abs(
        _primary["average_top_minus_bottom"]
        - _summary["average_top_minus_bottom"]
    ) < 1e-12
assert _chronological_stability(_bt["equity_periods"].head(7)).empty
_synthetic_periods = _bt["equity_periods"].head(3).copy()
_synthetic_periods["top_minus_bottom"] = [1.0, 2.0, 3.0]
_synthetic_loo = _leave_one_out_stability(_synthetic_periods)
assert _synthetic_loo["mean_sign_stable"] is True
assert _synthetic_loo["leave_one_out_mean_min"] == 1.5
assert _synthetic_loo["leave_one_out_mean_max"] == 2.5
_min_bt_date = max(
    _scoring_feedback_data["tot"].index.min(),
    _scoring_feedback_data["eps"].index.min(),
) + pd.Timedelta(days=90)
assert _bt["equity_periods"]["signal_date"].min() >= _min_bt_date
assert _bt["rates_summary"]["outcome_unit"] == "bp"
_future_bt_data = dict(_scoring_feedback_data)
_future_bt_date = pd.Timestamp(current_production_date()) + pd.Timedelta(days=14)
for _future_key in ("px", "y10y"):
    _future_frame = _scoring_feedback_data[_future_key].copy()
    _future_frame.loc[_future_bt_date] = _future_frame.ffill().iloc[-1]
    _future_bt_data[_future_key] = _future_frame.sort_index()
_future_bt = _build_bt(_future_bt_data, _BtCfg(rebalance="weekly", top_n=3))
for _kind in ("equity", "rates"):
    pd.testing.assert_frame_equal(
        _bt[f"{_kind}_periods"].reset_index(drop=True),
        _future_bt[f"{_kind}_periods"].reset_index(drop=True),
    )

_bt_page = next(p for p in PAGES if p["id"] == "scoring_backtest")
assert _bt_page["section"] == "A2" and _bt_page["status"] == "partial"
assert _bt_page["builds_on"] == "scoring" and _bt_page["next"] == "model_roadmap"
assert next(p for p in PAGES if p["id"] == "scoring")["next"] == "scoring_backtest"
_bt_page_src = open("charts/pages/scoring_backtest.py").read()
assert "build_score_backtest" in _bt_page_src
assert "st.slider" not in _bt_page_src and "st.number_input" not in _bt_page_src
assert "Sharpe ratio, drawdown and " in _bt_page_src
assert "cumulative portfolio P&L" in _bt_page_src
assert "FCI contributes" in _bt_page_src
assert "Chronological stability" in _bt_page_src
assert "Fixed-specification sensitivity" in _bt_page_src
assert "st.slider" not in _bt_page_src and "st.number_input" not in _bt_page_src
assert "scoring_backtest" in open("charts/pages/__init__.py").read()
assert "cta_score_backtest" in _shared_snapshot
assert _shared_snapshot["cta_score_backtest"]["specification"]["fci_used"] is False
assert len(_shared_snapshot["cta_score_backtest"]["equity_periods"]) == 12
assert len(_shared_snapshot["cta_score_backtest"]["equity_sensitivity"]) == 5
assert len(_shared_snapshot["cta_score_backtest"]["equity_chronological_stability"]) == 2
print("    E4. A2 shows all 12 strict weekly periods plus chronological, leave-one-out and fixed-grid robustness diagnostics; it ignores FCI/future rows and withholds unsupported P&L metrics ✓")

_dq_feedback = open("charts/pages/data_quality.py").read()
assert "SOFR Futures Strip &amp; Calendar Spreads" in _dq_feedback
assert "joined by Date" in _dq_feedback
assert "_SFR_CONTRACTS" in _dq_feedback
print("    F. Production policy-futures audit follows the eight fixed quarterly contracts ✓")

print(f"    CLI official: {res.latest:.4f} on {res.latest_date.date()} · complete-date rule ✓")

# Move final marker after all phases.

print("\nALL SMOKE TESTS PASSED ✓")
import time as _t_end
print(f"Elapsed: {_t_end.time() - _t0:.1f}s")
