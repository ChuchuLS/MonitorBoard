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

## Robustness diagnostics

The A2 page keeps the 50/50, Top 3 specification as the only primary result.
It now adds three descriptive checks without selecting a better-looking model:

- **Chronological stability:** the usable observations are split into two
  contiguous halves. Both halves must contain at least four periods. This is a
  time-stability comparison, not a train/test or macro-vintage-safe
  out-of-sample test.
- **Leave-one-period-out stability:** each observed week is removed once and
  the primary average spread is recalculated. This shows whether one week alone
  determines the sign of the reported mean.
- **Fixed sensitivity grid:** the primary 50/50 Top 3 result is shown alongside
  Top 2, Top 4, 40/60 and 60/40 variants. All five are reported together. The
  variants are not searched, ranked or used to change the production Score.

The page requires at least 26 usable periods before the sample is no longer
labelled `Insufficient sample`. Crossing that threshold would still leave the
result `Preliminary only`, because revised macro history and non-investable
rates outcomes remain unresolved.

## Important limitations

`Rates_10Y`, `Equity_ToT`, and `Equity_EPS` begin on 2026-02-16. After enforcing
the required 90-day factor history, only a short weekly evaluation window
remains. The workbook also contains revised macro observations rather than a
vintage database showing exactly what was known on every historical date.

The output is therefore a preliminary historical signal check. It is not a
statistically validated strategy, an investable rates P&L, or evidence that the
score will perform in the future.
