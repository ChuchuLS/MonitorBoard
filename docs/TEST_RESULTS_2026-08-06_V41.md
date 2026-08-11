# Version 41 — Fixed-Contract SOFR Strip Test Results

## Data source

- Workbook: `data/DATA.xlsx`
- New worksheet: `Policy_Futures`
- Contracts: `SFRU6`, `SFRZ6`, `SFRH7`, `SFRM7`, `SFRU7`, `SFRZ7`, `SFRH8`, `SFRM8`
- Each contract is loaded from its own Bloomberg BQL Date + Price pair.
- No row-position merge, forward fill, interpolation, or zero substitution.

## Current fixed-contract strip

- Common model date: 2026-08-06
- Common observations: 1,379
- EFFR used for context: 3.630% on 2026-08-04
- SOFR spot used for context: 3.660% on 2026-08-04
- Terminal contract: JUN 27
- Terminal implied rate: 4.100%
- EFFR-to-terminal gap: +47.0 bp
- Terminal to +3 months: -3.5 bp
- Terminal to +6 months: -9.0 bp
- Terminal to +12 months: -13.0 bp

## Verification

- Eight fixed contract tickers present.
- Implied rate exactly reconciles to `100 - price`.
- 1D, 5D and 1M changes use one common contract calendar.
- 3M, 6M and 12M calendar-spread matrix reconciles to contract-rate differences.
- Missing one fixed contract changes model status to `Partial` and withholds the production strip.
- Page, Data Quality, Roadmap, Q-list, JSON snapshot, README and static HTML use the fixed-contract model.
- Meeting-by-meeting FOMC path remains unimplemented and is not inferred.

## Full regression tests

```text
python -m compileall -q .
PASS

PYTHONUNBUFFERED=1 python smoke_test.py
ALL SMOKE TESTS PASSED
Elapsed: 31.7s

FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
ALL EXPORT TESTS PASSED
Total elapsed: 28.17s
```

## Existing model regression state

- Composite Liquidity Index: 50.92, Neutral, latest 2026-08-06.
- Policy funding pressure: +0.09, Normal, six spreads, model date 2026-08-04.
- Market linkage PC1 explained variance: 62.6%, 2Y percentile 88.
- Sector, FX, country rates, earnings, XCCY and export tests all passed.
