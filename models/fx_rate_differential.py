"""
models/fx_rate_differential.py — Phase 7.1C
===========================================
FX rate-differential monitor. Descriptive, not causal.

CRITICAL RULES:
- All production analytics use a FULLY ALIGNED frame with ALL four columns.
- Missing inputs are never displayed as zero.
- Snapshot and availability use the SAME readiness assessment.
- change_window is genuinely calculated, not hardcoded.
"""
from __future__ import annotations
import numpy as np, pandas as pd
from config.tickers import TICKERS

FX_PAIR_CONFIG = {
    "EURUSD": {"spot_key": "EURUSD", "base_country": "DE", "quote_country": "US",
               "differential_direction": "DE minus US", "spot_convention": "USD per EUR"},
    "USDJPY": {"spot_key": "USDJPY", "base_country": "US", "quote_country": "JP",
               "differential_direction": "US minus JP", "spot_convention": "JPY per USD"},
    "GBPUSD": {"spot_key": "GBPUSD", "base_country": "UK", "quote_country": "US",
               "differential_direction": "UK minus US", "spot_convention": "USD per GBP"},
    "AUDUSD": {"spot_key": "AUDUSD", "base_country": "AU", "quote_country": "US",
               "differential_direction": "AU minus US", "spot_convention": "USD per AUD"},
}

REQUIRED_ANALYTICAL_COLUMNS = ["spot", "nom_2y_diff", "nom_10y_diff", "real_10y_diff"]
FLAT_FX_THRESHOLD = 0.25
FLAT_DIFF_THRESHOLD = 5.0

ALIGNMENT_METRIC_MAP = {
    "2Y Nominal": "alignment_nom_2y_diff",
    "10Y Nominal": "alignment_nom_10y_diff",
    "10Y Real": "alignment_real_10y_diff",
}

def _get(df, ticker_key):
    tick = TICKERS.get(ticker_key)
    if not tick: return None
    for c in df.columns:
        if c.upper().strip() == tick.upper().strip():
            s = df[c].dropna()
            return s if len(s) > 0 else None
    return None

def _yield_key(country, tenor):
    return f"{country}_real_10y" if tenor == "real_10y" else f"{country}_{tenor}"

# ── Raw field dates (before alignment) ──
def _raw_field_dates(df, pair):
    cfg = FX_PAIR_CONFIG[pair]; b, q = cfg["base_country"], cfg["quote_country"]
    info = {}
    spot = _get(df, cfg["spot_key"])
    info["spot"] = spot.index[-1].date() if spot is not None else None
    for label, bt, qt in [("2y_diff", "2Y", "2Y"), ("10y_diff", "10Y", "10Y"),
                           ("real_10y_diff", "real_10y", "real_10y")]:
        yb, yq = _get(df, _yield_key(b, bt)), _get(df, _yield_key(q, qt))
        info[label] = min(yb.index[-1].date(), yq.index[-1].date()) if yb is not None and yq is not None else None
    return info

# ── Build the FULLY ALIGNED frame ──
def build_fx_pair_data(df, pair, asof=None):
    """Returns a frame with ALL four analytical columns aligned. No NaN."""
    cfg = FX_PAIR_CONFIG[pair]; b, q = cfg["base_country"], cfg["quote_country"]
    spot = _get(df, cfg["spot_key"])
    if spot is None: return pd.DataFrame()
    raw = pd.DataFrame({"spot": spot})
    for label, bt, qt in [("nom_2y_diff", "2Y", "2Y"), ("nom_10y_diff", "10Y", "10Y"),
                           ("real_10y_diff", "real_10y", "real_10y")]:
        yb, yq = _get(df, _yield_key(b, bt)), _get(df, _yield_key(q, qt))
        if yb is not None and yq is not None:
            raw[label] = 100 * (yb - yq)
    present = [c for c in REQUIRED_ANALYTICAL_COLUMNS if c in raw.columns]
    if set(present) != set(REQUIRED_ANALYTICAL_COLUMNS):
        return pd.DataFrame()  # incomplete — cannot build production frame
    aligned = raw[REQUIRED_ANALYTICAL_COLUMNS].dropna()
    if asof: aligned = aligned.loc[:pd.Timestamp(asof)]
    if aligned.empty: return pd.DataFrame()
    # Daily changes AFTER alignment
    aligned["fx_log_return_1d"] = 100 * np.log(aligned["spot"]).diff()
    for col in ["nom_2y_diff", "nom_10y_diff", "real_10y_diff"]:
        aligned[f"{col}_change_1d"] = aligned[col].diff()
    return aligned

# ── Shared readiness assessment ──
def assess_fx_pair_readiness(df, pair, correlation_window=63, asof=None):
    """Single source of truth for pair readiness."""
    raw_dates = _raw_field_dates(df, pair)
    missing_fields = [k for k, v in raw_dates.items() if v is None]
    cfg = FX_PAIR_CONFIG[pair]

    if raw_dates["spot"] is None:
        return {"status": "Missing data", "missing": missing_fields,
                "aligned_obs": 0, "common_first_date": None, "common_latest_date": None,
                "enough_history": False, "raw_dates": raw_dates}

    if missing_fields:
        return {"status": "Partial", "missing": missing_fields,
                "aligned_obs": 0, "common_first_date": None, "common_latest_date": None,
                "enough_history": False, "raw_dates": raw_dates,
                "reason": f"Missing: {', '.join(missing_fields)}"}

    aligned = build_fx_pair_data(df, pair, asof)
    if aligned.empty:
        return {"status": "Partial", "missing": [],
                "aligned_obs": 0, "common_first_date": None, "common_latest_date": None,
                "enough_history": False, "raw_dates": raw_dates,
                "reason": "No common aligned observations"}

    n = len(aligned)
    enough = n >= correlation_window + 1
    return {
        "status": "Ready" if enough else "Partial",
        "missing": [],
        "aligned_obs": n,
        "common_first_date": aligned.index[0].date(),
        "common_latest_date": aligned.index[-1].date(),
        "enough_history": enough,
        "raw_dates": raw_dates,
        "reason": None if enough else f"Only {n} aligned obs (need {correlation_window+1})",
    }

# ── Horizon metrics (arbitrary window) ──
def _horizon_metrics(aligned, horizons):
    """Calculate FX returns and differential changes for given horizons."""
    m = {}
    for n in horizons:
        if len(aligned) > n:
            m[f"fx_return_{n}d_pct"] = float(100 * np.log(aligned["spot"].iloc[-1] / aligned["spot"].iloc[-n-1]))
            for col in ["nom_2y_diff", "nom_10y_diff", "real_10y_diff"]:
                if col in aligned.columns:
                    m[f"{col}_chg_{n}d_bp"] = float(aligned[col].iloc[-1] - aligned[col].iloc[-n-1])
        else:
            m[f"fx_return_{n}d_pct"] = np.nan
            for col in ["nom_2y_diff", "nom_10y_diff", "real_10y_diff"]:
                m[f"{col}_chg_{n}d_bp"] = np.nan
    return m

# ── Snapshot ──
def build_fx_pair_snapshot(df, pair, asof=None, horizons=(1,5,20,63)):
    readiness = assess_fx_pair_readiness(df, pair, asof=asof)
    if readiness["status"] in ("Missing data", "Partial"):
        return {**readiness, "pair": pair}

    aligned = build_fx_pair_data(df, pair, asof)
    cfg = FX_PAIR_CONFIG[pair]
    snap = {
        "pair": pair, **readiness,
        "spot": float(aligned["spot"].iloc[-1]),
        "spot_convention": cfg["spot_convention"],
        "differential_direction": cfg["differential_direction"],
        "model_date": readiness["common_latest_date"],
    }
    for col in ["nom_2y_diff", "nom_10y_diff", "real_10y_diff"]:
        snap[f"{col}_bp"] = float(aligned[col].iloc[-1])
    snap.update(_horizon_metrics(aligned, horizons))
    return snap

# ── Rolling correlations ──
def build_fx_rolling_correlations(df, pair, correlation_window=63, asof=None):
    aligned = build_fx_pair_data(df, pair, asof)
    if aligned.empty or len(aligned) < correlation_window + 1:
        return pd.DataFrame()
    out = pd.DataFrame(index=aligned.index)
    fx_ret = aligned["fx_log_return_1d"]
    for col, out_col in [("nom_2y_diff_change_1d", "corr_fx_2y"),
                          ("nom_10y_diff_change_1d", "corr_fx_10y"),
                          ("real_10y_diff_change_1d", "corr_fx_real10y")]:
        if col in aligned.columns:
            out[out_col] = fx_ret.rolling(correlation_window).corr(aligned[col])
    return out

# ── Linkage table ──
def build_fx_linkage_table(df, pair, correlation_window=63, change_window=20, asof=None):
    aligned = build_fx_pair_data(df, pair, asof)
    if aligned.empty: return pd.DataFrame()
    corrs = build_fx_rolling_correlations(df, pair, correlation_window, asof)
    corr_map = {"nom_2y_diff": "corr_fx_2y", "nom_10y_diff": "corr_fx_10y",
                "real_10y_diff": "corr_fx_real10y"}
    rows = []
    for col, label in [("nom_2y_diff", "2Y Nominal Diff"), ("nom_10y_diff", "10Y Nominal Diff"),
                        ("real_10y_diff", "10Y Real Diff")]:
        if col not in aligned.columns: continue
        latest = float(aligned[col].iloc[-1]); lvd = aligned.index[-1].date()
        chgs = {}
        for n, lbl in [(1,"1D"),(5,"5D"),(change_window,f"{change_window}D"),(63,"63D")]:
            chgs[f"{lbl} Δ (bp)"] = round(float(aligned[col].iloc[-1]-aligned[col].iloc[-n-1]),1) if len(aligned)>n else np.nan
        cc = corr_map.get(col)
        lc = float(corrs[cc].dropna().iloc[-1]) if cc and not corrs.empty and cc in corrs.columns and corrs[cc].dropna().shape[0] else np.nan
        rows.append({"Metric": label, "Latest (bp)": round(latest,1), "Valid date": lvd,
                     **chgs, f"{correlation_window}D corr": round(lc,3) if pd.notna(lc) else np.nan})
    return pd.DataFrame(rows)

# ── Alignment classification ──
def _classify_alignment(fx_ret, diff_chg):
    if pd.isna(fx_ret) or pd.isna(diff_chg): return "Inconclusive"
    if abs(fx_ret) < FLAT_FX_THRESHOLD or abs(diff_chg) < FLAT_DIFF_THRESHOLD:
        return "Flat / inconclusive"
    return "Aligned" if (fx_ret > 0) == (diff_chg > 0) else "Divergent"

# ── Current reading ──
def build_fx_current_reading(df, pair, correlation_window=63, change_window=20, asof=None):
    snap = build_fx_pair_snapshot(df, pair, asof, horizons=(1,5,change_window,63))
    if snap.get("status") in ("Missing data", "Partial"):
        return snap
    reading = {**snap}
    fx_key = f"fx_return_{change_window}d_pct"
    fx_ret = snap.get(fx_key, np.nan)
    for dk in ["nom_2y_diff", "nom_10y_diff", "real_10y_diff"]:
        chg = snap.get(f"{dk}_chg_{change_window}d_bp", np.nan)
        reading[f"alignment_{dk}"] = _classify_alignment(fx_ret, chg)
    # Strongest linkage
    corrs = build_fx_rolling_correlations(df, pair, correlation_window, asof)
    if not corrs.empty:
        latest = corrs.iloc[-1].dropna()
        if len(latest):
            best_col = latest.abs().idxmax()
            label_map = {"corr_fx_2y": "2Y Nominal", "corr_fx_10y": "10Y Nominal",
                         "corr_fx_real10y": "10Y Real"}
            reading["strongest_corr_metric"] = label_map.get(best_col, best_col)
            reading["strongest_corr_value"] = float(latest[best_col])
    return reading

# ── Availability ──
def available_fx_pairs(df, correlation_window=63):
    return {pair: assess_fx_pair_readiness(df, pair, correlation_window)
            for pair in FX_PAIR_CONFIG}

# ── All-pair overview ──
def build_all_fx_snapshots(df, asof=None):
    rows = []
    for pair in FX_PAIR_CONFIG:
        snap = build_fx_pair_snapshot(df, pair, asof)
        reading = build_fx_current_reading(df, pair, asof=asof)
        def _fmt(v, fmt="+.1f", suffix=""): return f"{v:{fmt}}{suffix}" if pd.notna(v) else "—"
        rows.append({
            "Pair": pair, "Spot": _fmt(snap.get("spot"), ".4f"),
            "20D ret (%)": _fmt(snap.get("fx_return_20d_pct"), "+.2f"),
            "2Y diff (bp)": _fmt(snap.get("nom_2y_diff_bp"), "+.0f"),
            "10Y diff (bp)": _fmt(snap.get("nom_10y_diff_bp"), "+.0f"),
            "10Y real (bp)": _fmt(snap.get("real_10y_diff_bp"), "+.0f"),
            "Strongest": f"{reading.get('strongest_corr_metric','—')} ({reading.get('strongest_corr_value',0):+.3f})" if reading.get("strongest_corr_metric") else "—",
            "Model date": str(snap.get("common_latest_date") or snap.get("model_date") or "—"),
            "Obs": snap.get("aligned_obs", 0),
            "Status": snap.get("status", "—"),
        })
    return pd.DataFrame(rows)
