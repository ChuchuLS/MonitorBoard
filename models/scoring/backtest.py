"""Point-in-time-safe evaluation for the existing cross-sectional score.

The workbook does not contain unrevised macro vintages or investable sovereign
bond total-return indices.  This module therefore provides an honest signal
evaluation, not a claim of a production trading strategy:

* equity outcome = next-period cash-index price return;
* rates outcome = minus the next-period 10Y yield change in basis points;
* signals are formed only from rows dated on or before the signal date;
* a full 90-calendar-day factor lookback is required before a period is used;
* results are gross of costs and exclude equity rows not marked ``Ready``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from models.scoring.engine import score_equity, score_rates


MIN_FACTOR_LOOKBACK_DAYS = 90


@dataclass(frozen=True)
class BacktestConfig:
    rebalance: str = "weekly"
    top_n: int = 3
    min_factor_lookback_days: int = MIN_FACTOR_LOOKBACK_DAYS
    equity_weights: tuple[tuple[str, float], ...] = (("macro", 0.5), ("eps", 0.5))
    rates_weights: tuple[tuple[str, float], ...] = (("macro", 0.5), ("markets", 0.5))


def _period_ends(index: pd.Index, rebalance: str) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(index).dropna().sort_values().unique()
    if not len(dates):
        return pd.DatetimeIndex([])
    period = dates.to_period("W-FRI" if rebalance == "weekly" else "M")
    grouped = pd.DataFrame({"date": dates, "period": period}).groupby("period")["date"].max()
    return pd.DatetimeIndex(grouped.to_numpy())


def _first_valid_signal_date(data: dict, kind: str, lookback_days: int) -> pd.Timestamp | None:
    lookback_sheets = ("tot", "eps") if kind == "equity" else ("y10y",)
    starts = []
    for key in lookback_sheets:
        frame = data.get(key)
        if frame is None or frame.empty:
            return None
        starts.append(pd.Timestamp(frame.index.min()))
    return max(starts) + pd.Timedelta(days=lookback_days)


def _values_on_or_before(frame: pd.DataFrame, when: pd.Timestamp) -> pd.Series:
    eligible = frame.loc[frame.index <= when]
    if eligible.empty:
        return pd.Series(index=frame.columns, dtype=float)
    return eligible.ffill().iloc[-1]


def _ranked_frame(scores: pd.DataFrame, outcome: pd.Series, kind: str) -> pd.DataFrame:
    if scores.empty:
        return pd.DataFrame()
    eligible = scores.copy()
    if kind == "equity":
        eligible = eligible.loc[eligible["rank_eligible"].astype(bool)]
    eligible = eligible.loc[eligible["score"].notna()].copy()
    eligible["outcome"] = outcome.reindex(eligible.index)
    eligible = eligible.dropna(subset=["outcome"])
    eligible = eligible.assign(code=eligible.index.astype(str)).reset_index(drop=True)
    return eligible.sort_values(["score", "code"], ascending=[False, True])


def _spearman_rank_correlation(left: pd.Series, right: pd.Series) -> float:
    """Return Spearman's rho without pandas' optional SciPy dependency.

    Spearman correlation is the ordinary Pearson correlation of the two
    average-rank series.  Ranking first keeps tie handling equivalent to
    ``Series.corr(..., method="spearman")`` while allowing the dashboard to
    run in the lean Streamlit deployment environment.
    """
    pair = pd.concat(
        [pd.to_numeric(left, errors="coerce"), pd.to_numeric(right, errors="coerce")],
        axis=1,
    ).dropna()
    if len(pair) < 2:
        return np.nan
    left_rank = pair.iloc[:, 0].rank(method="average")
    right_rank = pair.iloc[:, 1].rank(method="average")
    correlation = left_rank.corr(right_rank, method="pearson")
    return float(correlation) if pd.notna(correlation) else np.nan


def run_score_backtest(data: dict, kind: str, config: BacktestConfig | None = None) -> pd.DataFrame:
    """Run a non-overlapping weekly or monthly score evaluation.

    ``kind`` is ``equity`` or ``rates``.  Each row represents one signal date
    and the immediately following rebalance observation.  No observation after
    the signal date enters score construction.
    """
    if kind not in {"equity", "rates"}:
        raise ValueError("kind must be 'equity' or 'rates'")
    cfg = config or BacktestConfig()
    if cfg.rebalance not in {"weekly", "monthly"}:
        raise ValueError("rebalance must be 'weekly' or 'monthly'")
    if cfg.top_n < 1:
        raise ValueError("top_n must be positive")

    source = data.get("px" if kind == "equity" else "y10y")
    if source is None or source.empty:
        return pd.DataFrame()
    from data.date_integrity import current_production_date
    production_date = pd.Timestamp(current_production_date())
    source = source.loc[pd.DatetimeIndex(source.index) <= production_date]
    if source.empty:
        return pd.DataFrame()
    first_signal = _first_valid_signal_date(
        data, kind, cfg.min_factor_lookback_days
    )
    if first_signal is None:
        return pd.DataFrame()

    dates = _period_ends(source.index, cfg.rebalance)
    rows = []
    for signal_date, outcome_date in zip(dates[:-1], dates[1:]):
        signal_date = pd.Timestamp(signal_date)
        outcome_date = pd.Timestamp(outcome_date)
        if signal_date < first_signal:
            continue
        # A weekly holiday gap is legitimate; a larger gap indicates an
        # incomplete source segment and is not treated as a one-week outcome.
        if cfg.rebalance == "weekly" and (outcome_date - signal_date).days > 10:
            continue

        start = _values_on_or_before(source, signal_date)
        end = _values_on_or_before(source, outcome_date)
        if kind == "equity":
            outcome = (end / start - 1.0) * 100.0
            scores = score_equity(data, signal_date, dict(cfg.equity_weights))
            unit = "%"
        else:
            outcome = -(end - start) * 100.0
            scores = score_rates(data, signal_date, dict(cfg.rates_weights))
            unit = "bp"

        ranked = _ranked_frame(scores, outcome, kind)
        if len(ranked) < cfg.top_n * 2:
            continue
        top = ranked.head(cfg.top_n)
        bottom = ranked.tail(cfg.top_n)
        top_value = float(top["outcome"].mean())
        bottom_value = float(bottom["outcome"].mean())
        rank_ic = _spearman_rank_correlation(ranked["score"], ranked["outcome"])
        rows.append({
            "market": kind,
            "signal_date": signal_date,
            "outcome_date": outcome_date,
            "n_assets": int(len(ranked)),
            "top_codes": ", ".join(top["code"]),
            "bottom_codes": ", ".join(bottom["code"]),
            "top_outcome": top_value,
            "bottom_outcome": bottom_value,
            "top_minus_bottom": top_value - bottom_value,
            "rank_ic": float(rank_ic) if pd.notna(rank_ic) else np.nan,
            "outcome_unit": unit,
        })
    return pd.DataFrame(rows)


def summarize_score_backtest(periods: pd.DataFrame, config: BacktestConfig | None = None) -> dict:
    cfg = config or BacktestConfig()
    if periods.empty:
        return {
            "status": "Missing data",
            "periods": 0,
            "rebalance": cfg.rebalance,
            "top_n": cfg.top_n,
        }
    spread = pd.to_numeric(periods["top_minus_bottom"], errors="coerce")
    ic = pd.to_numeric(periods["rank_ic"], errors="coerce")
    return {
        "status": "Limited sample" if len(periods) < 26 else "Available",
        "periods": int(len(periods)),
        "rebalance": cfg.rebalance,
        "top_n": cfg.top_n,
        "first_signal_date": periods["signal_date"].min().date(),
        "last_outcome_date": periods["outcome_date"].max().date(),
        "average_top_minus_bottom": float(spread.mean()),
        "median_top_minus_bottom": float(spread.median()),
        "hit_rate_pct": float((spread > 0).mean() * 100.0),
        "mean_rank_ic": float(ic.mean()),
        "outcome_unit": str(periods["outcome_unit"].iloc[0]),
        "costs_included": False,
        "macro_vintage_safe": False,
    }


def build_score_backtest(data: dict, config: BacktestConfig | None = None) -> dict:
    cfg = config or BacktestConfig()
    equity = run_score_backtest(data, "equity", cfg)
    rates = run_score_backtest(data, "rates", cfg)
    return {
        "config": cfg,
        "equity_periods": equity,
        "rates_periods": rates,
        "equity_summary": summarize_score_backtest(equity, cfg),
        "rates_summary": summarize_score_backtest(rates, cfg),
    }
