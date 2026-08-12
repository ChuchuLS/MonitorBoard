# Sector Contribution Estimate methodology

## Status

Live approximation in Streamlit section **06b**. This is **not official S&P 500
sector attribution**.

## Inputs

- The 11 canonical S&P 500 sector price indices from `DATA.xlsx / Sheet1`.
- `SPX INDEX` from the same common price calendar.
- Periodic sector weights from `SPX_Sector_Weights`.
- Sector ETF proxies are excluded.

## Calculation

For a selected horizon measured in common observations:

1. Align all 11 sector indices and SPX on identical timestamps.
2. Define the return-window start and end from that aligned calendar.
3. Select the latest sector-weight row dated on or before the start timestamp.
4. Calculate simple arithmetic returns:

   `sector return = 100 × (end price / start price − 1)`

5. Estimate each sector's contribution in percentage points:

   `estimated contribution = start weight / 100 × sector return`

6. Sum all 11 estimated contributions.
7. Disclose the residual:

   `residual = actual SPX return − estimated SPX return`

Weights are not normalised, interpolated, forward-filled, or replaced with
zero. A start-weight row older than 45 calendar days is marked Partial under a
project diagnostic rule.

## Why a residual remains

The source weights are periodic, not daily. The estimate does not reproduce the
index provider's divisor treatment, constituent-level corporate actions,
intra-period weight drift, or official contribution methodology. The residual
is therefore a required output, not an error hidden by rescaling.

## Current workbook diagnostics

As of the common sector/SPX end date `2026-07-23`:

| Window | Start | Start-weight date | Actual SPX | Estimated | Residual |
|---:|---|---|---:|---:|---:|
| 1D | 2026-07-22 | 2026-06-30 | -1.209% | -1.218% | +0.009pp |
| 5D | 2026-07-16 | 2026-06-30 | -1.665% | -1.623% | -0.042pp |
| 20D | 2026-06-24 | 2026-05-29 | +0.681% | +0.595% | +0.086pp |
| 63D | 2026-04-22 | 2026-03-31 | +3.788% | +3.800% | -0.012pp |

These values are derived from the current workbook and will change when
`DATA.xlsx` is updated.
