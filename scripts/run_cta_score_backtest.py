#!/usr/bin/env python3
"""Generate the offline score-backtest report; nothing is added to Streamlit."""
from __future__ import annotations

import html
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.date_integrity import current_production_date
from data.external_loaders import load_pulsar
from models.scoring.backtest import BacktestConfig, build_score_backtest


def _summary_table(label: str, summary: dict) -> str:
    unit = summary.get("outcome_unit", "")
    avg = summary.get("average_top_minus_bottom")
    med = summary.get("median_top_minus_bottom")
    ic = summary.get("mean_rank_ic")
    rows = [
        ("Status", summary.get("status", "Missing data")),
        ("Usable periods", summary.get("periods", 0)),
        ("Signal window", f"{summary.get('first_signal_date', '—')} → {summary.get('last_outcome_date', '—')}"),
        ("Average Top 3 − Bottom 3", f"{avg:+.3f} {unit}" if avg is not None else "—"),
        ("Median Top 3 − Bottom 3", f"{med:+.3f} {unit}" if med is not None else "—"),
        ("Positive-spread hit rate", f"{summary.get('hit_rate_pct', float('nan')):.1f}%" if avg is not None else "—"),
        ("Mean Spearman rank IC", f"{ic:+.3f}" if ic is not None else "—"),
    ]
    body = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    return f"<section><h2>{html.escape(label)}</h2><table>{body}</table></section>"


def _period_table(periods: pd.DataFrame, unit: str) -> str:
    if periods.empty:
        return "<p>Missing data.</p>"
    view = periods.copy()
    view["signal_date"] = pd.to_datetime(view["signal_date"]).dt.date
    view["outcome_date"] = pd.to_datetime(view["outcome_date"]).dt.date
    cols = [
        "signal_date", "outcome_date", "n_assets", "top_codes", "bottom_codes",
        "top_outcome", "bottom_outcome", "top_minus_bottom", "rank_ic",
    ]
    view = view[cols].rename(columns={
        "signal_date": "Signal date", "outcome_date": "Outcome date",
        "n_assets": "N", "top_codes": "Top 3", "bottom_codes": "Bottom 3",
        "top_outcome": f"Top ({unit})", "bottom_outcome": f"Bottom ({unit})",
        "top_minus_bottom": f"Spread ({unit})", "rank_ic": "Rank IC",
    })
    return view.to_html(index=False, border=0, float_format=lambda x: f"{x:+.3f}")


def build_report(output_dir: Path | None = None) -> tuple[Path, Path, Path]:
    output_dir = output_dir or ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = build_score_backtest(load_pulsar(), BacktestConfig(rebalance="weekly", top_n=3))
    asof = current_production_date().strftime("%Y%m%d")
    equity_csv = output_dir / f"cta_score_backtest_equity_{asof}.csv"
    rates_csv = output_dir / f"cta_score_backtest_rates_{asof}.csv"
    report_path = output_dir / f"cta_score_backtest_{asof}.html"
    result["equity_periods"].to_csv(equity_csv, index=False)
    result["rates_periods"].to_csv(rates_csv, index=False)

    eq = result["equity_summary"]
    rt = result["rates_summary"]
    report = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>CTA Score Backtest</title>
<style>
body{{background:#080b0c;color:#e8edf0;font:14px Inter,Arial,sans-serif;margin:32px auto;max-width:1180px;line-height:1.5}}
h1{{font-size:26px}} h2{{color:#e8b931;margin-top:30px}} h3{{margin-top:28px}}
.note{{border-left:3px solid #d99830;background:#111517;padding:14px 16px;margin:18px 0}}
table{{border-collapse:collapse;width:100%;margin:10px 0 24px}} th,td{{border:1px solid #273036;padding:7px 9px;text-align:left}}
th{{background:#13191c;color:#aab4ba}} td{{font-variant-numeric:tabular-nums}}
</style></head><body>
<h1>Existing CTA / Global Score — Offline Backtest</h1>
<p>Data through {current_production_date().isoformat()}. Weekly, non-overlapping signal evaluation; Top 3 minus Bottom 3; Board default 50/50 weights.</p>
<div class="note"><b>Interpretation limit.</b> The available high-frequency factor history starts on 2026-02-16. After requiring a full 90-calendar-day lookback, only {eq.get('periods', 0)} equity and {rt.get('periods', 0)} rates observations remain. The workbook contains revised macro observations rather than vintage snapshots. This is therefore a preliminary historical signal check, not a statistically validated or deployable strategy backtest.</div>
{_summary_table('Equity score', eq)}
<p>Outcome: next-week cash-index return. Only rows with all four scoring macro factors (GDP, CPI, fiscal and terms of trade) plus EPS and status Ready enter the ranking. FCI is context only and is not used. Gross of costs.</p>
{_summary_table('Rates score', rt)}
<p>Outcome: minus next-week 10Y yield change in basis points, used only as a bond-direction proxy. The workbook does not contain sovereign total-return indices, so this is not portfolio P&amp;L.</p>
<h3>Equity periods</h3>{_period_table(result['equity_periods'], '%')}
<h3>Rates periods</h3>{_period_table(result['rates_periods'], 'bp')}
<div class="note"><b>No-fabrication controls.</b> No forward observation enters signal construction; no missing scoring factor, price, EPS, yield or return is replaced by a proxy or zero; FCI has no effect on the equity signal; no transaction-cost assumption is invented.</div>
</body></html>"""
    report_path.write_text(report, encoding="utf-8")
    return report_path, equity_csv, rates_csv


if __name__ == "__main__":
    paths = build_report()
    for path in paths:
        print(path)
