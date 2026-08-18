"""
index/methodology.py
====================
Versioning, audit trail, and reconciliation for the Composite Liquidity Index
(requirements #1-#5). Everything here is data-side (no Streamlit); charts/ renders
the returned frames.

  * INDEX_METHODOLOGY        - single source of truth for the version + params,
                               assembled from the live constants so it can't drift.
  * methodology_audit()      - version params + runtime state (data hash, latest
                               date, components/buckets live on the latest date).
  * compute_legacy_index()   - the previous ("legacy") methodology, for an
                               apples-to-apples methodology reconciliation.
  * reconciliation()         - legacy vs current index + bucket decomposition,
                               with the exact reconciliation identities.
  * component_contribution_table() - per-component contribution to (index-50),
                               with raw/adjusted value, z, weight, change terms,
                               and an explicit live/excluded reason.
  * forward_fill_audit()     - per-component freshness / staleness / ffill report.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from data.transforms import (
    Z_WINDOW, Z_MIN_PERIODS, Z_CLIP, Z_MIN_UNIQUE, OBS_WINDOW_BY_FREQ,
    true_observations,
)
from index.components import (
    BUCKETS, COMPONENTS, BUCKET_OF, LABEL_OF, DIRECTION, build_components,
    frequency_of, max_ffill_of, observation_mode_of, observation_weekday_of,
    component_ticker,
)
from index.composite import (
    IndexResult, compute_index, INDEX_SCALE, INDEX_CENTER, HORIZONS,
    MIN_AVAILABLE_BUCKETS, MIN_AVAILABLE_COMPONENTS, MIN_COMPONENTS_PER_BUCKET,
    WARMUP_DAYS_AFTER_FIRST_VALID, HEADLINE_REQUIRED_BUCKETS,
    HEADLINE_COMPONENT_LOOKBACK,
)

# ---------------------------------------------------------------------------
# 1. Methodology version (single source of truth)
# ---------------------------------------------------------------------------
INDEX_VERSION = "v0.4"

INDEX_METHODOLOGY: dict = {
    "version": INDEX_VERSION,
    "description": "Rolling z-score composite liquidity index with a fully-covered "
                   "official headline and explicitly preliminary later observations",
    "z_window": Z_WINDOW,
    "z_min_periods": Z_MIN_PERIODS,
    "z_clip": Z_CLIP,
    "z_min_unique": Z_MIN_UNIQUE,
    "min_available_buckets": MIN_AVAILABLE_BUCKETS,
    "min_available_components": MIN_AVAILABLE_COMPONENTS,
    "min_components_per_bucket": MIN_COMPONENTS_PER_BUCKET,
    "warmup_days_after_first_valid": WARMUP_DAYS_AFTER_FIRST_VALID,
    "headline_required_buckets": HEADLINE_REQUIRED_BUCKETS,
    "headline_component_lookback": HEADLINE_COMPONENT_LOOKBACK,
    "headline_component_rule": (
        "live components >= trailing median on prior all-bucket dates"
    ),
    "preliminary_rule": (
        "later analytical observations never drive official level, regime, changes, or contributions"
    ),
    "bucket_weights": {b: BUCKETS[b]["weight"] for b in BUCKETS},
    "ticker_corrections": [
        {
            "date": "2026-07",
            "component": "cb_liquidity_swaps (was cb_repo)",
            "ticker": "FARWCBLS INDEX",
            "previous_label": "Fed repo / SRF usage",
            "confirmed_label": "Central Bank Liquidity Swaps (Federal Reserve H.4.1)",
            "action": "Relabelled without changing historical numerical values. "
                      "Component role, direction, and weight remain subject to methodology review.",
        },
    ],
}

# Legacy methodology = the rules in force before v0.3: rolling z + bucket mean +
# renormalised weights, but NO low-variation guard, NO min-2-per-bucket, NO
# coverage gate / warm-up, unlimited forward-fill, daily treatment of weekly data.
LEGACY_VERSION = "v0.2 (legacy)"


def methodology_audit(result: IndexResult, df: pd.DataFrame,
                      data_hash: str | None = None) -> dict:
    """Version params + runtime state for the audit-trail panel."""
    latest = df.index.max() if len(df) else None
    def _at(series: pd.Series) -> int:
        if series is None or series.empty:
            return 0
        if latest is not None and latest in series.index:
            return int(series.loc[latest])
        return int(series.dropna().iloc[-1]) if series.notna().any() else 0
    official_date = result.latest_date
    preliminary_date = result.preliminary_date

    def _at_date(series: pd.Series, date) -> int | None:
        if date is None or series is None or series.empty or date not in series.index:
            return None
        value = series.loc[date]
        return int(value) if pd.notna(value) else None

    analytical = result.index.dropna()
    return {
        **INDEX_METHODOLOGY,
        "data_hash": data_hash or "n/a",
        "latest_data_date": latest,
        "latest_published_date": official_date,
        "latest_official_date": official_date,
        "latest_analytical_date": analytical.index[-1] if len(analytical) else None,
        "latest_preliminary_date": preliminary_date,
        "first_published_date": result.first_published_date,
        "first_official_date": result.first_headline_date,
        "components_on_latest": _at(result.available_component_count),
        "buckets_on_latest": _at(result.available_bucket_count),
        "components_on_official": _at_date(result.available_component_count, official_date),
        "buckets_on_official": _at_date(result.available_bucket_count, official_date),
        "components_on_preliminary": _at_date(result.available_component_count, preliminary_date),
        "buckets_on_preliminary": _at_date(result.available_bucket_count, preliminary_date),
        "normal_component_target_on_preliminary": _at_date(
            result.normal_component_target, preliminary_date
        ),
        "latest_index": result.latest,
        "latest_regime": result.latest_regime,
        "preliminary_index": (result.preliminary_latest
                              if pd.notna(result.preliminary_latest) else None),
        "preliminary_regime": result.preliminary_regime,
    }


# ---------------------------------------------------------------------------
# 2. Legacy index + reconciliation
# ---------------------------------------------------------------------------
def compute_legacy_index(df: pd.DataFrame) -> IndexResult:
    """Reproduce the pre-v0.3 methodology for reconciliation."""
    return compute_index(
        df,
        z_min_unique=None,            # no low-variation guard
        min_per_bucket=1,             # single-component buckets allowed
        min_buckets=1,                # no coverage gate
        min_components=1,
        warmup_days=0,                # no warm-up filter
        lowfreq_handling=False,       # weekly series treated as daily
        ffill_cap="none",             # unlimited forward-fill
    )


def _value_at(series: pd.Series, date) -> float:
    if series is None or series.empty or date not in series.index:
        return float("nan")
    return float(series.loc[date])


def reconciliation(current: IndexResult, legacy: IndexResult,
                   df: pd.DataFrame) -> dict:
    """Legacy vs current at the latest published date, with bucket decomposition.

    Returns a dict with headline numbers, a per-bucket DataFrame, and the three
    reconciliation identities (which should each hold to ~1e-9).
    """
    if current.headline_index.dropna().empty:
        return {}
    date = current.headline_index.dropna().index[-1]

    cur_idx = _value_at(current.headline_index, date)
    leg_idx = _value_at(legacy.index, date)
    if np.isnan(leg_idx):
        leg_idx = _value_at(legacy.raw_index, date)
    cur_z = _value_at(current.composite_z, date)
    leg_z = _value_at(legacy.composite_z, date)

    rows = []
    for b in BUCKETS:
        rows.append({
            "bucket": b,
            "bucket_label": BUCKETS[b]["label"],
            "legacy_sub": _value_at(legacy.sub_indices.get(b, pd.Series(dtype=float)), date)
                          if b in legacy.sub_indices.columns else np.nan,
            "current_sub": _value_at(current.sub_indices.get(b, pd.Series(dtype=float)), date)
                           if b in current.sub_indices.columns else np.nan,
            "legacy_eff_w": _value_at(legacy.effective_weights.get(b, pd.Series(dtype=float)), date)
                            if b in legacy.effective_weights.columns else np.nan,
            "current_eff_w": _value_at(current.effective_weights.get(b, pd.Series(dtype=float)), date)
                             if b in current.effective_weights.columns else np.nan,
            "legacy_contrib": _value_at(legacy.bucket_terms.get(b, pd.Series(dtype=float)), date)
                              if b in legacy.bucket_terms.columns else np.nan,
            "current_contrib": _value_at(current.bucket_terms.get(b, pd.Series(dtype=float)), date)
                               if b in current.bucket_terms.columns else np.nan,
        })
    table = pd.DataFrame(rows)
    table["contrib_diff"] = (table["current_contrib"].fillna(0)
                             - table["legacy_contrib"].fillna(0))

    checks = {
        "sum_current_contrib": float(table["current_contrib"].sum()),
        "current_index_minus_50": cur_idx - INDEX_CENTER,
        "sum_legacy_contrib": float(table["legacy_contrib"].sum()),
        "legacy_index_minus_50": leg_idx - INDEX_CENTER,
        "sum_contrib_diff": float(table["contrib_diff"].sum()),
        "current_minus_legacy": cur_idx - leg_idx,
    }
    return {
        "date": date,
        "legacy_index": leg_idx,
        "current_index": cur_idx,
        "index_diff": cur_idx - leg_idx,
        "legacy_z": leg_z,
        "current_z": cur_z,
        "z_diff": cur_z - leg_z,
        "table": table,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# 3 & 4. Component contributions + status/reason
# ---------------------------------------------------------------------------
def _component_status(comp_id: str, result: IndexResult, raw: dict[str, pd.Series],
                      df: pd.DataFrame, asof=None) -> tuple[bool, str]:
    """(is_live_on_latest, reason). Reason explains exclusion when not live.

    ``asof`` defaults to the latest raw workbook row for freshness audits.  A
    published-index caller should pass the latest published date explicitly so
    contribution rows reconcile to the same date as the displayed index.
    """
    latest = pd.Timestamp(asof) if asof is not None else df.index.max()
    if comp_id not in raw or raw[comp_id].dropna().empty:
        return False, "Missing data"

    z = result.z_scores[comp_id] if comp_id in result.z_scores.columns else pd.Series(dtype=float)
    z_latest = z.reindex([latest]).iloc[0] if latest in z.index else (
        z.dropna().iloc[-1] if z.notna().any() else np.nan)
    bucket = BUCKET_OF[comp_id]

    if not np.isnan(z_latest):
        # z exists; is it actually contributing?
        n_live = (result.components_by_bucket[bucket].reindex([latest]).iloc[0]
                  if latest in result.components_by_bucket.index else np.nan)
        if not np.isnan(n_live) and n_live < MIN_COMPONENTS_PER_BUCKET:
            return False, f"Bucket has <{MIN_COMPONENTS_PER_BUCKET} live components"
        if latest in result.published_mask.index and not bool(result.published_mask.loc[latest]):
            return False, "Coverage gate"
        return True, "Live"

    # z is NaN on the latest date — diagnose why.
    adjusted = (raw[comp_id] * DIRECTION[comp_id]).sort_index()
    mode = observation_mode_of(comp_id)
    obs = true_observations(adjusted, mode, observation_weekday_of(comp_id))
    # Staleness: last true observation older than the ffill cap?
    if not obs.empty:
        last_obs = obs.index[-1]
        bdays_since = len(pd.bdate_range(last_obs, latest)) - 1
        if bdays_since > max_ffill_of(comp_id):
            return False, "Stale (capped forward-fill)"
    # History vs low-variation guard, judged on the relevant cadence.
    win, minp = (OBS_WINDOW_BY_FREQ.get(frequency_of(comp_id), (Z_WINDOW, Z_MIN_PERIODS))
                 if mode != "daily" else (Z_WINDOW, Z_MIN_PERIODS))
    series = obs if mode != "daily" else adjusted.dropna()
    if len(series) < minp:
        return False, "Insufficient rolling history"
    tail = series.iloc[-win:]
    if tail.nunique() < (Z_MIN_UNIQUE or 0):
        return False, "Failed low-unique-observation guard"
    return False, "Not live (NaN)"


def component_contribution_table(result: IndexResult, df: pd.DataFrame) -> pd.DataFrame:
    """One row per DEFINED component with its latest contribution + change terms
    and a live/excluded reason. Live components' contributions sum to index-50."""
    raw, _ = build_components(df)
    published = result.headline_index.dropna()
    latest = published.index[-1] if len(published) else df.index.max()

    level = result.component_level_contributions()
    chg = {h: result.component_change_contributions(h) for h in HORIZONS}

    rows = []
    for comp_id, label, bucket, direction, spec in COMPONENTS:
        live, reason = _component_status(comp_id, result, raw, df, asof=latest)
        rseries = raw.get(comp_id, pd.Series(dtype=float)).dropna().sort_index()
        raw_asof = rseries.loc[:latest]
        raw_latest = float(raw_asof.iloc[-1]) if not raw_asof.empty else np.nan
        z = result.z_scores[comp_id] if comp_id in result.z_scores.columns else pd.Series(dtype=float)
        z_latest = (z.reindex([latest]).iloc[0] if latest in z.index
                    else (z.dropna().iloc[-1] if z.notna().any() else np.nan))
        eff_w = np.nan
        if bucket in result.effective_weights.columns and latest in result.effective_weights.index:
            eff_w = float(result.effective_weights[bucket].loc[latest])
        rows.append({
            "component": comp_id,
            "name": label,
            "ticker": component_ticker(comp_id),
            "bucket": BUCKETS[bucket]["label"],
            "raw_latest": raw_latest,
            "adjusted_latest": raw_latest * direction if not np.isnan(raw_latest) else np.nan,
            "z": z_latest,
            "eff_weight": eff_w,
            "contribution": float(level.get(comp_id, np.nan)) if len(level) else np.nan,
            "chg_1w": float(chg["1w"].get(comp_id, np.nan)) if len(chg["1w"]) else np.nan,
            "chg_1m": float(chg["1m"].get(comp_id, np.nan)) if len(chg["1m"]) else np.nan,
            "chg_3m": float(chg["3m"].get(comp_id, np.nan)) if len(chg["3m"]) else np.nan,
            "live": live,
            "status": reason,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Forward-fill audit
# ---------------------------------------------------------------------------
def forward_fill_audit(result: IndexResult, df: pd.DataFrame) -> pd.DataFrame:
    """Per-component freshness/staleness report (requirement #5)."""
    raw, _ = build_components(df)
    latest = df.index.max()
    one_year_ago = latest - pd.Timedelta(days=365)
    bgrid_1y = pd.bdate_range(one_year_ago, latest)

    rows = []
    for comp_id, label, bucket, direction, spec in COMPONENTS:
        freq = frequency_of(comp_id)
        maxff = max_ffill_of(comp_id)
        mode = observation_mode_of(comp_id)
        rseries = raw.get(comp_id, pd.Series(dtype=float)).dropna().sort_index()
        if rseries.empty:
            rows.append({
                "component": comp_id, "name": label, "frequency": freq,
                "max_ffill_days": maxff, "latest_raw_obs": None,
                "latest_true_obs": None, "days_since_true_obs": np.nan,
                "is_live": False, "reason": "Missing data",
                "stale_days_1y": np.nan, "pct_ffilled_1y": np.nan,
            })
            continue
        adjusted = (rseries * direction)
        obs = true_observations(adjusted, mode, observation_weekday_of(comp_id))
        latest_raw = rseries.index[-1]
        latest_true = obs.index[-1] if not obs.empty else latest_raw
        days_since = len(pd.bdate_range(latest_true, latest)) - 1

        live, reason = _component_status(comp_id, result, raw, df)
        # Live-z mask over the last year; stale = business day with no live z.
        z = result.z_scores[comp_id] if comp_id in result.z_scores.columns else pd.Series(dtype=float)
        z_1y = z.reindex(bgrid_1y)
        stale_days = int(z_1y.isna().sum())
        # % of last-year business days that were forward-filled (not true obs).
        true_in_1y = obs.index.intersection(bgrid_1y)
        pct_ffilled = 100.0 * (1 - len(true_in_1y) / max(len(bgrid_1y), 1))

        rows.append({
            "component": comp_id, "name": label, "frequency": freq,
            "max_ffill_days": maxff, "latest_raw_obs": latest_raw.date(),
            "latest_true_obs": latest_true.date(),
            "days_since_true_obs": int(days_since),
            "is_live": live, "reason": "" if live else reason,
            "stale_days_1y": stale_days,
            "pct_ffilled_1y": round(pct_ffilled, 1),
        })
    return pd.DataFrame(rows)
