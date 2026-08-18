"""
index/composite.py
==================
Constructs the Composite Liquidity Index from the raw components.

Pipeline
--------
1. For each component: multiply by its direction (looser = higher), then take a
   rolling z-score (with a low-variation guard) -> ``z_scores`` frame.
2. Sub-index per bucket = mean of that bucket's available component z-scores,
   but ONLY on days the bucket has at least ``min_per_bucket`` live components.
   (A single fragile series must not *be* a bucket — that was the source of the
   2016-2018 spikes, when money-market = EFFR-IORB alone.)
3. Composite z = weighted average of the sub-indices, with weights renormalised
   across whichever buckets qualify that day. The renormalised (effective)
   weights are exposed so the concentration is transparent.
4. Rescale: ``liquidity_index = 50 + 10 * composite_z`` (50 neutral).
5. ANALYTICAL COVERAGE GATE: a date enters the historical analytical series if
   it has >= ``min_buckets`` qualifying buckets and >= ``min_components``
   contributing components, and is past the rolling-z warm-up.
6. OFFICIAL HEADLINE GATE: the headline uses the most recent date on which all
   five buckets qualify and the live-component count is at least its trailing
   normal level. A later analytical observation is exposed as preliminary and
   never drives the official level, changes, regime, or contributions.
7. Regime label, period changes, and an additive bucket contribution
   decomposition (terms sum exactly to index-50, so the decomposition always
   reconciles).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data.transforms import (
    rolling_zscore, lowfreq_zscore, OBS_WINDOW_BY_FREQ,
    Z_WINDOW, Z_MIN_PERIODS, Z_CLIP, Z_MIN_UNIQUE,
)
from index.components import (
    BUCKETS, DIRECTION, BUCKET_OF, build_components, max_ffill_of,
    frequency_of, observation_mode_of, observation_weekday_of,
)

# Index scaling
INDEX_CENTER = 50.0
INDEX_SCALE = 10.0

# Regime thresholds. Higher = looser.
REGIME_THRESHOLDS = [(60.0, "Loose"), (45.0, "Neutral"), (35.0, "Tight")]

# Headline change horizons in business days
HORIZONS = {"1w": 5, "1m": 21, "3m": 63}

# -------------------- Coverage / reliability rules --------------------------
# A bucket needs at least this many live components before its sub-index counts.
# Stops a lone, possibly-flat series from carrying a full bucket weight.
MIN_COMPONENTS_PER_BUCKET = 2
# A date is only published if at least this many buckets qualify ...
MIN_AVAILABLE_BUCKETS = 3
# ... and at least this many components (within qualifying buckets) contribute.
MIN_AVAILABLE_COMPONENTS = 8
# After the index first becomes computable, skip this many business days so the
# rolling z-scores are past their warm-up before we publish.
WARMUP_DAYS_AFTER_FIRST_VALID = 126
# The official headline must contain every configured bucket.  This prevents a
# missing bucket from being silently redistributed over the remaining buckets.
HEADLINE_REQUIRED_BUCKETS = len(BUCKETS)
# "Normal" live-component coverage is the trailing median on dates where all
# buckets qualify.  A rolling, data-derived target adapts when the production
# component universe genuinely changes without hard-coding today's count.
HEADLINE_COMPONENT_LOOKBACK = 63


def regime_label(value: float) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "n/a"
    for cutoff, label in REGIME_THRESHOLDS:
        if value >= cutoff:
            return label
    return "Stress"


@dataclass
class IndexResult:
    """Everything the dashboard needs to render the index, in one object."""
    index: pd.Series             # analytical history (broad coverage gate)
    headline_index: pd.Series    # OFFICIAL series (all buckets + normal coverage)
    raw_index: pd.Series         # index before the coverage/warm-up mask (diagnostics)
    composite_z: pd.Series       # weighted-average z (raw_index = 50 + 10*z)
    sub_indices: pd.DataFrame    # date x bucket sub-index z-scores (min_per_bucket applied)
    z_scores: pd.DataFrame       # date x component direction-adjusted z-scores
    bucket_terms: pd.DataFrame   # date x bucket additive contributions to (raw_index-50)
    component_terms: pd.DataFrame  # date x component additive contributions to (raw_index-50)
    weights: pd.Series           # base bucket weights (normalised over buckets seen)
    effective_weights: pd.DataFrame  # date x bucket renormalised weights actually used
    components_by_bucket: pd.DataFrame  # date x bucket live-component counts
    available_component_count: pd.Series  # contributing components per day
    available_bucket_count: pd.Series     # qualifying buckets per day
    coverage_ok: pd.Series       # bool: meets min bucket/component rules
    published_mask: pd.Series    # bool: coverage_ok AND past warm-up
    complete_coverage_ok: pd.Series  # bool: all buckets + normal component count
    headline_mask: pd.Series     # bool: complete_coverage_ok AND past warm-up
    normal_component_target: pd.Series  # trailing normal live-component count
    meta: pd.DataFrame           # per-component availability metadata
    first_valid_date: pd.Timestamp | None = None      # first computable date
    first_published_date: pd.Timestamp | None = None  # first reliable/published date
    first_headline_date: pd.Timestamp | None = None   # first fully-covered date

    # ------- convenience accessors (operate on the OFFICIAL headline) --------
    @property
    def latest_date(self) -> pd.Timestamp | None:
        s = self.headline_index.dropna()
        return s.index[-1] if len(s) else None

    @property
    def latest(self) -> float:
        s = self.headline_index.dropna()
        return float(s.iloc[-1]) if len(s) else float("nan")

    @property
    def latest_regime(self) -> str:
        return regime_label(self.latest)

    @property
    def preliminary_index(self) -> pd.Series:
        """Analytical observations later than the latest official headline."""
        s = self.index.dropna()
        if s.empty:
            return s
        latest_official = self.latest_date
        return s if latest_official is None else s.loc[s.index > latest_official]

    @property
    def preliminary_date(self) -> pd.Timestamp | None:
        s = self.preliminary_index
        return s.index[-1] if len(s) else None

    @property
    def preliminary_latest(self) -> float:
        s = self.preliminary_index
        return float(s.iloc[-1]) if len(s) else float("nan")

    @property
    def preliminary_regime(self) -> str:
        return regime_label(self.preliminary_latest)

    def _horizon_dates(self, horizon: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """Official latest date and latest official date on/before the target B-day."""
        s = self.headline_index.dropna()
        if s.empty:
            return None
        latest = s.index[-1]
        target = latest - pd.tseries.offsets.BusinessDay(HORIZONS[horizon])
        prior = s.loc[:target]
        if prior.empty:
            return None
        return latest, prior.index[-1]

    def changes(self) -> dict[str, float]:
        out = {}
        for name in HORIZONS:
            dates = self._horizon_dates(name)
            out[name] = (float(self.headline_index.loc[dates[0]]
                               - self.headline_index.loc[dates[1]])
                         if dates is not None else float("nan"))
        return out

    def _terms_on_published(self, terms: pd.DataFrame) -> pd.DataFrame:
        """Restrict a terms frame to the published index dates, so contribution
        differences reconcile exactly to the published index changes regardless of
        any unpublished/low-frequency rows elsewhere in the frame."""
        if terms is None or terms.empty:
            return pd.DataFrame()
        pub = self.headline_index.dropna().index
        return terms.reindex(pub)

    def level_contributions(self) -> pd.Series:
        terms = self._terms_on_published(self.bucket_terms).dropna(how="all")
        return terms.iloc[-1] if len(terms) else pd.Series(dtype=float)

    def change_contributions(self, horizon: str = "1m") -> pd.Series:
        terms = self._terms_on_published(self.bucket_terms).dropna(how="all")
        dates = self._horizon_dates(horizon)
        if terms.empty or dates is None:
            return pd.Series(dtype=float)
        return terms.loc[dates[0]] - terms.loc[dates[1]]

    def drivers(self, horizon: str = "1m") -> tuple[str, str]:
        contrib = self.change_contributions(horizon)
        if contrib.empty or contrib.isna().all():
            return ("n/a", "n/a")
        easing_lbl = BUCKETS.get(contrib.idxmax(), {}).get("label", contrib.idxmax())
        tight_lbl = BUCKETS.get(contrib.idxmin(), {}).get("label", contrib.idxmin())
        return (easing_lbl, tight_lbl)

    def coverage_frame(self) -> pd.DataFrame:
        """Tidy frame for the coverage diagnostic chart."""
        return pd.DataFrame({
            "components": self.available_component_count,
            "buckets": self.available_bucket_count,
        })

    def component_level_contributions(self) -> pd.Series:
        """Latest contribution of each component to (index - 50), index points."""
        terms = self._terms_on_published(self.component_terms).dropna(how="all")
        return terms.iloc[-1] if len(terms) else pd.Series(dtype=float)

    def component_change_contributions(self, horizon: str = "1m") -> pd.Series:
        """Each component's contribution to the index change over ``horizon``."""
        terms = self._terms_on_published(self.component_terms).dropna(how="all")
        dates = self._horizon_dates(horizon)
        if terms.empty or dates is None:
            return pd.Series(dtype=float)
        return terms.loc[dates[0]] - terms.loc[dates[1]]


def compute_index(
    df: pd.DataFrame,
    weights: dict[str, float] | None = None,
    z_window: int = Z_WINDOW,
    z_min_periods: int = Z_MIN_PERIODS,
    z_clip: float = Z_CLIP,
    z_min_unique: int | None = Z_MIN_UNIQUE,
    min_per_bucket: int = MIN_COMPONENTS_PER_BUCKET,
    min_buckets: int = MIN_AVAILABLE_BUCKETS,
    min_components: int = MIN_AVAILABLE_COMPONENTS,
    warmup_days: int = WARMUP_DAYS_AFTER_FIRST_VALID,
    lowfreq_handling: bool = True,
    ffill_cap: str = "by_freq",
) -> IndexResult:
    """Build the Composite Liquidity Index from the price panel.

    ``lowfreq_handling`` (True) z-scores weekly/low-frequency components on their
    true observations; set False to treat every daily row as a fresh print (the
    legacy behaviour). ``ffill_cap`` is "by_freq" (per-component caps) or "none"
    (unlimited forward-fill, legacy).
    """
    # 1. Raw components + availability metadata.
    raw, meta = build_components(df)

    # 2. Direction-adjust then z-score each available component. Daily series use
    #    a daily rolling window; weekly/low-frequency series are standardised on
    #    their true observations (e.g. Wednesdays) and the z is forward-filled.
    daily_grid = None
    if raw:
        lo = min(s.index.min() for s in raw.values())
        hi = max(s.index.max() for s in raw.values())
        daily_grid = pd.date_range(lo, hi, freq="B")
    cap_daily = (lambda cid: max_ffill_of(cid)) if ffill_cap == "by_freq" else (lambda cid: None)

    z_cols: dict[str, pd.Series] = {}
    for comp_id, series in raw.items():
        adjusted = series * DIRECTION[comp_id]   # looser = higher
        mode = observation_mode_of(comp_id)
        if lowfreq_handling and mode != "daily":
            win, minp = OBS_WINDOW_BY_FREQ.get(frequency_of(comp_id), (Z_WINDOW, Z_MIN_PERIODS))
            z_cols[comp_id] = lowfreq_zscore(
                adjusted, daily_grid, mode, observation_weekday_of(comp_id),
                window=win, min_periods=minp, clip=z_clip, min_unique=z_min_unique,
                max_ffill=max_ffill_of(comp_id),
            )
        else:
            z_cols[comp_id] = rolling_zscore(
                adjusted, window=z_window, min_periods=z_min_periods, clip=z_clip,
                min_unique=z_min_unique, max_ffill=cap_daily(comp_id),
            )
    z_scores = pd.DataFrame(z_cols).sort_index() if z_cols else pd.DataFrame()
    # Pin the whole index to a business-day grid. Some raw Bloomberg series carry
    # stray weekend timestamps; without this, daily components would get z-scores
    # on Sat/Sun while weekly components (already on a B-day grid) are NaN there,
    # giving inconsistent bucket coverage on weekends and breaking the change
    # reconciliation (the row-counted "1w ago" could land on a weekend).
    if not z_scores.empty and daily_grid is not None:
        z_scores = z_scores.reindex(daily_grid)

    if z_scores.empty:
        empty = pd.Series(dtype=float)
        empty_df = pd.DataFrame()
        return IndexResult(
            index=empty, headline_index=empty, raw_index=empty,
            composite_z=empty, sub_indices=empty_df, z_scores=z_scores,
            bucket_terms=empty_df, component_terms=empty_df,
            weights=pd.Series(dtype=float), effective_weights=empty_df,
            components_by_bucket=empty_df, available_component_count=empty,
            available_bucket_count=empty, coverage_ok=empty,
            published_mask=empty, complete_coverage_ok=empty,
            headline_mask=empty, normal_component_target=empty, meta=meta,
        )

    # 3. Per-bucket live-component counts and sub-index (with min_per_bucket).
    sub_data: dict[str, pd.Series] = {}
    count_data: dict[str, pd.Series] = {}
    for bucket in BUCKETS:
        members = [c for c in z_scores.columns if BUCKET_OF[c] == bucket]
        if not members:
            count_data[bucket] = pd.Series(0, index=z_scores.index)
            continue
        member_z = z_scores[members]
        cnt = member_z.notna().sum(axis=1)
        count_data[bucket] = cnt
        # Sub-index only on days the bucket has >= min_per_bucket live components.
        sub_data[bucket] = member_z.mean(axis=1, skipna=True).where(cnt >= min_per_bucket)
    components_by_bucket = pd.DataFrame(count_data).sort_index()
    sub_indices = pd.DataFrame(sub_data).sort_index() if sub_data else pd.DataFrame()

    # 4. Weighted composite with per-row weight renormalisation over QUALIFYING
    #    buckets (those with a non-NaN sub-index that day).
    base_weights = {b: BUCKETS[b]["weight"] for b in BUCKETS}
    if weights:
        base_weights.update(weights)
    w = pd.Series(base_weights)
    w = w[[b for b in w.index if b in sub_indices.columns]]
    w = w / w.sum() if w.sum() else w

    avail = sub_indices[w.index].notna()                 # qualifying buckets per day
    row_w = avail.mul(w, axis=1).sum(axis=1).replace(0.0, np.nan)
    effective_weights = avail.mul(w, axis=1).div(row_w, axis=0)   # rows sum to 1.0

    # Additive bucket terms: 10 * eff_weight_b * sub_b. Sum -> raw_index - 50.
    bucket_terms = INDEX_SCALE * sub_indices[w.index].mul(effective_weights)
    raw_index = INDEX_CENTER + bucket_terms.sum(axis=1, min_count=1)
    composite_z = (raw_index - INDEX_CENTER) / INDEX_SCALE

    # Component-level additive terms (requirement #3):
    #   term_i = 10 * eff_weight_b * z_i / n_live_in_bucket_b
    # so terms sum within a bucket to bucket_term_b, and across all to raw_index-50.
    comp_cols: dict[str, pd.Series] = {}
    for comp_id in z_scores.columns:
        b = BUCKET_OF[comp_id]
        if b not in effective_weights.columns:
            continue
        n_live = components_by_bucket[b].replace(0, np.nan)
        comp_cols[comp_id] = INDEX_SCALE * effective_weights[b] * z_scores[comp_id] / n_live
    component_terms = pd.DataFrame(comp_cols).sort_index() if comp_cols else pd.DataFrame()

    # 5. Coverage diagnostics + publication gate.
    available_bucket_count = avail.sum(axis=1)
    # Components that actually contribute = those in qualifying buckets.
    contributing = pd.Series(0, index=z_scores.index)
    for bucket in avail.columns:
        members = [c for c in z_scores.columns if BUCKET_OF[c] == bucket]
        if members:
            contributing = contributing.add(
                z_scores[members].notna().sum(axis=1).where(avail[bucket], 0),
                fill_value=0)
    available_component_count = contributing.astype(int)

    coverage_ok = (available_bucket_count >= min_buckets) & \
                  (available_component_count >= min_components)

    # Warm-up: skip the first warmup_days business days after the index is first
    # computable, so the rolling z-scores are mature before we publish.
    computable = raw_index.notna()
    first_valid_date = raw_index.index[computable.argmax()] if computable.any() else None
    if first_valid_date is not None and warmup_days > 0:
        warmup_cutoff = first_valid_date + pd.tseries.offsets.BusinessDay(warmup_days)
        warmup_ok = pd.Series(raw_index.index >= warmup_cutoff, index=raw_index.index)
    else:
        warmup_ok = pd.Series(True, index=raw_index.index)

    published_mask = coverage_ok.reindex(raw_index.index, fill_value=False) & warmup_ok
    index = raw_index.where(published_mask)
    published = index.dropna()
    first_published_date = published.index[0] if len(published) else None

    # 6. Official headline gate.  The component target is based only on prior
    # fully-covered dates, so an abnormally sparse current row cannot lower its
    # own hurdle.  The first fully-covered date falls back to its own count.
    all_buckets = available_bucket_count.eq(HEADLINE_REQUIRED_BUCKETS)
    complete_counts = available_component_count.where(all_buckets)
    normal_component_target = (
        complete_counts.shift(1)
        .rolling(HEADLINE_COMPONENT_LOOKBACK, min_periods=1)
        .median()
        .apply(np.ceil)
        .fillna(complete_counts)
    )
    complete_coverage_ok = (
        all_buckets
        & normal_component_target.notna()
        & available_component_count.ge(normal_component_target)
    )
    headline_mask = complete_coverage_ok.reindex(raw_index.index, fill_value=False) & warmup_ok
    headline_index = raw_index.where(headline_mask)
    headline = headline_index.dropna()
    first_headline_date = headline.index[0] if len(headline) else None

    return IndexResult(
        index=index,
        headline_index=headline_index,
        raw_index=raw_index,
        composite_z=composite_z,
        sub_indices=sub_indices,
        z_scores=z_scores,
        bucket_terms=bucket_terms,
        component_terms=component_terms,
        weights=w,
        effective_weights=effective_weights,
        components_by_bucket=components_by_bucket,
        available_component_count=available_component_count,
        available_bucket_count=available_bucket_count,
        coverage_ok=coverage_ok,
        published_mask=published_mask,
        complete_coverage_ok=complete_coverage_ok,
        headline_mask=headline_mask,
        normal_component_target=normal_component_target,
        meta=meta,
        first_valid_date=first_valid_date,
        first_published_date=first_published_date,
        first_headline_date=first_headline_date,
    )
