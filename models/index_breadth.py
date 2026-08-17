"""Index trend and optional constituent-breadth calculations."""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.index_breadth_loader import BREADTH_METRICS


def build_index_trend(prices: pd.DataFrame, code: str, frequency: str = "Daily") -> pd.DataFrame:
    if not isinstance(prices, pd.DataFrame) or code not in prices.columns:
        return pd.DataFrame(columns=["price", "ma_50d", "ma_200d", "ma_100w"])
    price = pd.to_numeric(prices[code], errors="coerce").dropna().sort_index()
    price = price[~price.index.duplicated(keep="last")]
    if price.empty:
        return pd.DataFrame(columns=["price", "ma_50d", "ma_200d", "ma_100w"])

    daily = pd.DataFrame({
        "price": price,
        "ma_50d": price.rolling(50, min_periods=50).mean(),
        "ma_200d": price.rolling(200, min_periods=200).mean(),
    })
    weekly_price = price.resample("W-FRI").last().dropna()
    weekly_100 = weekly_price.rolling(100, min_periods=100).mean().rename("ma_100w")

    if str(frequency).lower().startswith("week"):
        frame = daily.resample("W-FRI").last().dropna(subset=["price"])
        frame = frame.join(weekly_100, how="left")
        return frame

    # The weekly moving average is kept only on its observed week-end dates;
    # it is not forward-filled across daily rows.
    return daily.join(weekly_100, how="outer").sort_index()


def select_index_breadth(breadth: pd.DataFrame, code: str, frequency: str = "Daily") -> pd.DataFrame:
    if not isinstance(breadth, pd.DataFrame) or breadth.empty:
        return pd.DataFrame(columns=list(BREADTH_METRICS))
    if not isinstance(breadth.index, pd.MultiIndex) or code not in breadth.index.get_level_values("code"):
        return pd.DataFrame(columns=list(BREADTH_METRICS))
    frame = breadth.xs(code, level="code").sort_index().copy()
    if str(frequency).lower().startswith("week"):
        frame = frame.resample("W-FRI").last().dropna(how="all")
    return frame


def _last(series: pd.Series):
    valid = pd.to_numeric(series, errors="coerce").dropna()
    return float(valid.iloc[-1]) if len(valid) else np.nan


def build_index_breadth_snapshot(
    prices: pd.DataFrame,
    breadth: pd.DataFrame,
    code: str,
    frequency: str = "Daily",
) -> dict:
    trend = build_index_trend(prices, code, frequency)
    metrics = select_index_breadth(breadth, code, frequency)
    missing = [label for key, label in BREADTH_METRICS.items()
               if key not in metrics.columns or metrics[key].dropna().empty]
    weekly_obs = 0
    if isinstance(prices, pd.DataFrame) and code in prices.columns:
        weekly_obs = int(
            pd.to_numeric(prices[code], errors="coerce").dropna()
            .resample("W-FRI").last().dropna().shape[0]
        )
    latest_date = trend["price"].dropna().index.max() if not trend.empty else None
    return {
        "status": "Ready" if not missing else "Partial",
        "code": code,
        "frequency": frequency,
        "model_date": latest_date.date() if latest_date is not None else None,
        "trend": trend,
        "breadth": metrics,
        "price": _last(trend["price"]) if not trend.empty else np.nan,
        "ma_50d": _last(trend["ma_50d"]) if not trend.empty else np.nan,
        "ma_200d": _last(trend["ma_200d"]) if not trend.empty else np.nan,
        "ma_100w": _last(trend["ma_100w"]) if not trend.empty else np.nan,
        "weekly_observations": weekly_obs,
        "missing_metrics": missing,
    }
