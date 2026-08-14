"""Fixed-contract Three-Month SOFR futures strip and calendar spreads.

This model uses the eight actual Bloomberg contract tickers in the
``Policy_Futures`` worksheet.  It is a contract-month strip, not a
meeting-by-meeting FOMC probability model.
"""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from config.tickers import SOFR_CONTRACT_CONFIG, TICKERS

DEFAULT_HORIZONS = (1, 5, 20)
DEFAULT_MIN_OBSERVATIONS = 21
CURVE_COMPARISON_HORIZONS = {"Current": 0, "1W ago": 5, "1M ago": 20}


def _asof_ts(asof) -> pd.Timestamp | None:
    return None if asof is None else pd.Timestamp(asof)


def contract_codes() -> list[str]:
    return list(SOFR_CONTRACT_CONFIG)


def build_sofr_contract_price_frame(
    futures_df: pd.DataFrame,
    asof=None,
    require_all: bool = True,
) -> pd.DataFrame:
    """Return fixed-contract prices on one exact common source calendar."""
    if futures_df is None or futures_df.empty:
        return pd.DataFrame(columns=contract_codes(), dtype=float)
    present = [c for c in contract_codes() if c in futures_df.columns]
    if require_all and len(present) != len(contract_codes()):
        return pd.DataFrame(columns=contract_codes(), dtype=float)
    if not present:
        return pd.DataFrame(dtype=float)
    frame = futures_df[present].apply(pd.to_numeric, errors="coerce").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    cutoff = _asof_ts(asof)
    if cutoff is not None:
        frame = frame.loc[:cutoff]
    return frame.dropna(how="any" if require_all else "all")


def build_sofr_implied_rate_frame(
    futures_df: pd.DataFrame,
    asof=None,
    require_all: bool = True,
) -> pd.DataFrame:
    prices = build_sofr_contract_price_frame(futures_df, asof, require_all)
    return prices if prices.empty else 100.0 - prices


def assess_sofr_strip(
    futures_df: pd.DataFrame,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    asof=None,
) -> dict:
    missing = [
        code for code in contract_codes()
        if futures_df is None or code not in futures_df.columns
        or pd.to_numeric(futures_df[code], errors="coerce").dropna().empty
    ]
    if len(missing) == len(contract_codes()):
        status = "Missing data"
    elif missing:
        status = "Partial"
    else:
        status = "Ready"
    frame = build_sofr_implied_rate_frame(futures_df, asof, require_all=not missing)
    enough = len(frame) >= int(min_observations)
    if status == "Ready" and not enough:
        status = "Partial"
    return {
        "status": status,
        "missing": missing,
        "aligned_observations": int(len(frame)),
        "common_first_date": frame.index.min().date() if len(frame) else None,
        "model_date": frame.index.max().date() if len(frame) else None,
        "enough_history": enough,
    }


def _change_bp(series: pd.Series, horizon: int) -> float | None:
    h = int(horizon)
    if h <= 0 or len(series) <= h:
        return None
    return float(100.0 * (series.iloc[-1] - series.iloc[-h - 1]))


def build_sofr_strip_table(
    futures_df: pd.DataFrame,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    asof=None,
) -> pd.DataFrame:
    prices = build_sofr_contract_price_frame(futures_df, asof)
    rates = build_sofr_implied_rate_frame(futures_df, asof)
    if prices.empty or rates.empty:
        return pd.DataFrame()
    horizons = tuple(dict.fromkeys(int(h) for h in horizons if int(h) > 0))
    rows = []
    for sequence, code in enumerate(contract_codes(), 1):
        cfg = SOFR_CONTRACT_CONFIG[code]
        row = {
            "sequence": sequence,
            "ticker": code,
            "contract_label": cfg["contract_label"],
            "contract_month": cfg["contract_month"],
            "price": float(prices[code].iloc[-1]),
            "implied_rate_pct": float(rates[code].iloc[-1]),
            "model_date": rates.index[-1].date(),
        }
        for h in horizons:
            row[f"change_{h}d_bp"] = _change_bp(rates[code], h)
        rows.append(row)
    return pd.DataFrame(rows)


def build_sofr_curve_comparison(
    futures_df: pd.DataFrame,
    asof=None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return current, 1-week and 1-month curves on exact common dates.

    One week and one month are defined as 5 and 20 common trading observations.
    The function does not forward-fill, interpolate, or mix dates across contracts.
    """
    rates = build_sofr_implied_rate_frame(futures_df, asof=asof, require_all=True)
    labels = [SOFR_CONTRACT_CONFIG[code]["contract_label"] for code in contract_codes()]
    comparison = pd.DataFrame(index=pd.Index(labels, name="contract_label"), dtype=float)
    dates: dict[str, object] = {}
    for label, horizon in CURVE_COMPARISON_HORIZONS.items():
        if len(rates) <= horizon:
            comparison[label] = np.nan
            dates[label] = None
            continue
        row = rates.iloc[-horizon - 1]
        comparison[label] = [float(row[code]) for code in contract_codes()]
        dates[label] = rates.index[-horizon - 1].date()
    return comparison, dates


def build_calendar_spread_matrix(strip_table: pd.DataFrame) -> pd.DataFrame:
    """Far-contract implied rate minus row-contract rate, in basis points."""
    if strip_table is None or strip_table.empty:
        return pd.DataFrame()
    rates = strip_table.set_index("sequence")["implied_rate_pct"]
    labels = strip_table.set_index("sequence")["contract_label"]
    rows = []
    for seq in rates.index:
        row = {"Contract": labels.loc[seq]}
        for label, offset in (("3M", 1), ("6M", 2), ("12M", 4)):
            target = seq + offset
            row[label] = (
                float(100.0 * (rates.loc[target] - rates.loc[seq]))
                if target in rates.index else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)


def _spot_on_or_before(market_df: pd.DataFrame, ticker: str, model_date) -> tuple[float | None, object | None]:
    if market_df is None or ticker not in market_df.columns or model_date is None:
        return None, None
    s = pd.to_numeric(market_df[ticker], errors="coerce").dropna().sort_index()
    s = s.loc[:pd.Timestamp(model_date)]
    if s.empty:
        return None, None
    return float(s.iloc[-1]), s.index[-1].date()


def determine_terminal(strip_table: pd.DataFrame, baseline_rate_pct: float | None) -> dict:
    """Select first peak or trough according to the larger priced move from spot."""
    empty = {
        "direction": "Unavailable", "terminal_rate_pct": None,
        "terminal_contract": None, "terminal_sequence": None,
        "terminal_gap_bp": None,
    }
    if strip_table is None or strip_table.empty or baseline_rate_pct is None:
        return empty
    rates = strip_table["implied_rate_pct"].astype(float)
    max_gap = float((rates.max() - baseline_rate_pct) * 100.0)
    min_gap = float((rates.min() - baseline_rate_pct) * 100.0)
    if max_gap >= abs(min_gap):
        extreme = rates.max(); direction = "Higher rates priced"
    else:
        extreme = rates.min(); direction = "Lower rates priced"
    first = strip_table.loc[np.isclose(rates, extreme)].iloc[0]
    return {
        "direction": direction,
        "terminal_rate_pct": float(first["implied_rate_pct"]),
        "terminal_contract": first["contract_label"],
        "terminal_sequence": int(first["sequence"]),
        "terminal_gap_bp": float((first["implied_rate_pct"] - baseline_rate_pct) * 100.0),
    }


def build_terminal_spreads(strip_table: pd.DataFrame, terminal: dict) -> dict:
    result = {"terminal_to_3m_bp": None, "terminal_to_6m_bp": None, "terminal_to_12m_bp": None,
              "contract_3m": None, "contract_6m": None, "contract_12m": None}
    if strip_table is None or strip_table.empty or not terminal.get("terminal_sequence"):
        return result
    base_seq = int(terminal["terminal_sequence"])
    base_rate = float(terminal["terminal_rate_pct"])
    indexed = strip_table.set_index("sequence")
    for key, label, offset in (("terminal_to_3m_bp", "contract_3m", 1),
                               ("terminal_to_6m_bp", "contract_6m", 2),
                               ("terminal_to_12m_bp", "contract_12m", 4)):
        target = base_seq + offset
        if target in indexed.index:
            result[key] = float(100.0 * (indexed.loc[target, "implied_rate_pct"] - base_rate))
            result[label] = indexed.loc[target, "contract_label"]
    return result


def build_sofr_strip_snapshot(
    futures_df: pd.DataFrame,
    market_df: pd.DataFrame | None = None,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    asof=None,
) -> dict:
    readiness = assess_sofr_strip(futures_df, asof=asof)
    result = {
        **readiness,
        "strip_table": pd.DataFrame(),
        "calendar_spread_matrix": pd.DataFrame(),
        "price_history": pd.DataFrame(),
        "implied_rate_history": pd.DataFrame(),
        "curve_comparison": pd.DataFrame(),
        "curve_comparison_dates": {},
        "effr_pct": None, "effr_date": None,
        "sofr_pct": None, "sofr_date": None,
        "terminal": determine_terminal(pd.DataFrame(), None),
        "terminal_spreads": build_terminal_spreads(pd.DataFrame(), {}),
    }
    if readiness["status"] != "Ready":
        return result
    table = build_sofr_strip_table(futures_df, horizons=horizons, asof=asof)
    prices = build_sofr_contract_price_frame(futures_df, asof)
    rates = build_sofr_implied_rate_frame(futures_df, asof)
    curve_comparison, curve_comparison_dates = build_sofr_curve_comparison(
        futures_df, asof=asof
    )
    effr, effr_date = _spot_on_or_before(market_df, TICKERS["EFFR"], readiness["model_date"])
    sofr, sofr_date = _spot_on_or_before(market_df, TICKERS["SOFR"], readiness["model_date"])
    terminal = determine_terminal(table, effr)
    result.update({
        "strip_table": table,
        "calendar_spread_matrix": build_calendar_spread_matrix(table),
        "price_history": prices,
        "implied_rate_history": rates,
        "curve_comparison": curve_comparison,
        "curve_comparison_dates": curve_comparison_dates,
        "effr_pct": effr, "effr_date": effr_date,
        "sofr_pct": sofr, "sofr_date": sofr_date,
        "terminal": terminal,
        "terminal_spreads": build_terminal_spreads(table, terminal),
    })
    return result


def build_sofr_strip_current_reading(
    futures_df: pd.DataFrame,
    market_df: pd.DataFrame | None = None,
    asof=None,
) -> dict:
    snap = build_sofr_strip_snapshot(futures_df, market_df, asof=asof)
    reading = {
        "status": snap["status"], "model_date": snap.get("model_date"),
        "summary": "Insufficient data.",
        "limitations": (
            "This is a fixed quarterly Three-Month SOFR contract strip. It is not a "
            "meeting-by-meeting FOMC probability distribution. The contract list is "
            "static and must be rolled when the front contract expires."
        ),
    }
    if snap["status"] != "Ready":
        return reading
    terminal = snap["terminal"]
    reading["summary"] = (
        f"The strip peaks at {terminal['terminal_rate_pct']:.3f}% in "
        f"{terminal['terminal_contract']} ({terminal['terminal_gap_bp']:+.1f} bp "
        f"versus EFFR) as of {snap['model_date']}. The curve then prices "
        f"{snap['terminal_spreads'].get('terminal_to_12m_bp'):+.1f} bp from the "
        f"terminal contract to the available 12-month point."
        if snap['terminal_spreads'].get('terminal_to_12m_bp') is not None else
        f"The strip terminal is {terminal['terminal_rate_pct']:.3f}% in "
        f"{terminal['terminal_contract']} as of {snap['model_date']}."
    )
    return reading
