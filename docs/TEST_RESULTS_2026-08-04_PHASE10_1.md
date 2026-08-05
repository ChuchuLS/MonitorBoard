# Phase 10.1 Test Results — Policy Futures Generic Strip

Date: 2026-08-04

## Scope

Implemented a live continuous-contract monitor for:

- `FF1 / FF2 / FF3 COMB COMDTY`
- `SER1 / SER2 / SER3 COMB COMDTY`
- `SFR1 / SFR2 / SFR3 COMB COMDTY`

The model converts price to implied reference rate using `100 - price`, aligns
all three generic ranks within each family before calculating changes, and does
not infer contract months, FOMC outcomes, or meeting probabilities.

## Current workbook diagnostics

| Family | Model date | Common observations | Front implied rate | Third implied rate | Rank 3 − Rank 1 | Front − spot reference |
|---|---:|---:|---:|---:|---:|---:|
| FF | 2026-07-24 | 687 | 3.632% | 3.805% | +17.3 bp | +0.5 bp |
| SER | 2026-07-24 | 687 | 3.625% | 3.825% | +20.0 bp | -1.5 bp |
| SFR | 2026-07-24 | 687 | 3.700% | 4.165% | +46.5 bp | +6.0 bp |

The spot-reference comparison uses the latest date common to the front generic
and EFFR/SOFR. It is descriptive and is not a meeting-path calculation.

## Regression checks

- Exactly three configured contract families and three ranks per family.
- Price-to-rate identity reconciles exactly: `implied rate = 100 - price`.
- Family calculations use a common three-rank calendar.
- Missing one generic rank changes the family status to `Partial`.
- No missing observation is forward-filled, interpolated, or replaced by zero.
- Arbitrary observation windows are calculated from the aligned family frame.
- Front-to-third slope reconciles to the latest rank-3 minus rank-1 implied rate.
- Front-minus-spot comparisons use common dates.
- Pure model has no Streamlit import.
- Page, Data Quality, Roadmap, README, Q-list, JSON snapshot, and static HTML are consistent.
- Meeting-by-meeting FOMC path remains separately unimplemented.

## Commands

```text
python -m compileall -q .
PYTHONUNBUFFERED=1 python smoke_test.py
FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
```

## Results

```text
ALL SMOKE TESTS PASSED
Elapsed: 29.8s
```

```text
snapshot.json: index=52.13, 19 pages
lightweight HTML: 24,504 chars
full inline Plotly HTML: 4,897,417 chars
ALL EXPORT TESTS PASSED
```

The full inline export test runs in a fresh subprocess to avoid non-deterministic
Plotly render state after lightweight mode in some headless environments.
