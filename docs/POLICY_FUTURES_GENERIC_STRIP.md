> **Superseded for production:** this document describes the earlier SFR1–SFR3
> generic-rank monitor. The live 01b page now uses eight fixed quarterly
> contracts from `DATA.xlsx / Policy_Futures`. See
> `docs/POLICY_FUTURES_FIXED_STRIP.md`.

# Policy Futures Generic Strip

## Scope

The live `01b · Policy Futures Generic Strip` page uses the nine generic
continuous futures series already present in `DATA.xlsx / Sheet1`:

- `FF1 / FF2 / FF3 COMB COMDTY` — 30-Day Federal Funds futures.
- `SER1 / SER2 / SER3 COMB COMDTY` — 1-Month SOFR futures.
- `SFR1 / SFR2 / SFR3 COMB COMDTY` — 3-Month SOFR futures.

The page is a descriptive continuous-contract monitor. It is not an
expiry-mapped forward curve, a meeting-by-meeting FOMC path, or a probability
model.

## Confirmed contract interpretation

| Family | Contract | Reference-rate interpretation | Bloomberg generic root |
|---|---|---|---|
| FF | 30-Day Federal Funds futures | Monthly average daily EFFR during the delivery month | `FF Comdty` |
| SER | 1-Month SOFR futures | Monthly average daily SOFR during the delivery month | `SER Comdty` |
| SFR | 3-Month SOFR futures | Compounded daily SOFR over the reference quarter | `SFR Comdty` |

Source documentation recorded in the ticker registry:

- CME/CBOT Rulebook Chapter 22 — 30-Day Federal Funds Futures.
- CME Group — Understanding SOFR Futures and the vendor-code table.
- CME Group — Three-Month SOFR Futures Rates and Future SOFR Levels.

## Quote conversion

All three families are displayed in IMM-index form. The model converts each
price to an implied reference rate using:

```text
implied reference rate (%) = 100 − futures price
```

No convexity adjustment, meeting-day adjustment, or contract-month inference is
applied.

## Calendar and changes

For each family, all three generic ranks are intersected first. Prices, implied
rates, horizon changes, and rank-1-to-rank-3 slopes are then calculated on that
common observation calendar.

The standard changes are 1, 5, 20, and 63 common observations. Missing values
are not forward-filled, interpolated, or replaced with zero.

## Generic-rank limitations

`FF1`, `SER1`, and `SFR1` are rolling front-generic series. Their underlying
contracts change over time. Therefore:

- Rank 1, 2, or 3 is not a fixed expiry.
- Historical discontinuities can include contract-roll effects.
- Rank-to-rank slopes are generic-curve diagnostics, not fixed-calendar spreads.
- The front implied rate minus current EFFR/SOFR is descriptive only.
- The page does not infer the policy rate after any specific FOMC meeting.
- The page does not calculate hike/cut probabilities.

An expiry-mapped FOMC path requires actual contract codes, contract months,
expiry information, and the FOMC calendar.

## Current workbook output

As of the current source workbook:

| Family | Common date | Common observations | Front implied rate | Third implied rate | Rank 3 − Rank 1 |
|---|---:|---:|---:|---:|---:|
| FF | 2026-07-24 | 687 | 3.632% | 3.805% | +17.3 bp |
| SER | 2026-07-24 | 687 | 3.625% | 3.825% | +20.0 bp |
| SFR | 2026-07-24 | 687 | 3.700% | 4.165% | +46.5 bp |

These numbers are derived from the workbook and must not be hardcoded into
production logic.
