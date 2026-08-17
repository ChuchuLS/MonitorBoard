# Existing CTA / Global Score — Backtest Page and Offline Report

The fixed-specification results are displayed on the A2 CTA Score Backtest page.
The same period tables can also be generated as a standalone HTML/CSV report with:

```text
python scripts/run_cta_score_backtest.py
```

## Test design

- Weekly, non-overlapping rebalance observations.
- Board default 50/50 pillar weights.
- Top three minus bottom three cross-sectional outcome.
- Full 90-calendar-day factor lookback before the first eligible signal.
- Equity: next-week cash-index price return.
- Rates: minus next-week 10Y yield change in basis points, used only as a
  bond-direction proxy because sovereign total-return indices are not supplied.
- Equity Macro = equal-weighted GDP, inverted CPI, fiscal balance and
  terms-of-trade momentum. At the Board default, each contributes 12.5% of the
  total score; EPS contributes 50%.
- FCI is retained as separate context only. It is not mapped to indices and has
  no effect on scores, ranking eligibility or backtest results.
- Equity rows marked Partial or Missing data are excluded.
- No future-dated row enters signal construction.
- Gross results; no transaction-cost assumption is invented.

## Important limitations

`Rates_10Y`, `Equity_ToT`, and `Equity_EPS` begin on 2026-02-16. After enforcing
the required 90-day factor history, only a short weekly evaluation window
remains. The workbook also contains revised macro observations rather than a
vintage database showing exactly what was known on every historical date.

The output is therefore a preliminary historical signal check. It is not a
statistically validated strategy, an investable rates P&L, or evidence that the
score will perform in the future.
