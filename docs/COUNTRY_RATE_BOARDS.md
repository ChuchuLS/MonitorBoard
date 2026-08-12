# Country Rate Boards methodology

## Status

Live in Streamlit section **04b** for:

- United States
- Germany
- Japan
- United Kingdom
- Canada
- Australia
- Switzerland

The boards are descriptive sovereign-curve monitors. The nominal board is live
for all seven countries. Exact-tenor real-rate / inflation-compensation
attribution is live for the United States, Germany, Japan, United Kingdom,
Canada and Australia. Switzerland is explicitly unavailable because the
workbook has no confirmed Swiss real-yield series. The app does not use the
reference pack's euro-area proxy.

These are not policy forecasts, trade recommendations, or causal models.

## Inputs

Each country requires the canonical `DATA.xlsx / Sheet1` series for:

- 2Y nominal government yield
- 5Y nominal government yield
- 10Y nominal government yield
- 30Y nominal government yield

Ticker selection comes only from `config/tickers.py`.

The real/inflation extension additionally requires a same-tenor,
same-market inflation-linked government yield. Supported exact tenors are:

| Country | Exact tenors |
|---|---|
| United States | 5Y, 10Y, 30Y |
| Germany | 10Y |
| Japan | 5Y, 10Y |
| United Kingdom | 5Y, 10Y, 30Y |
| Canada | 5Y, 10Y, 30Y |
| Australia | 5Y, 10Y |
| Switzerland | Unavailable |

## Common-calendar rule

For an individual country, all four tenors are aligned first and rows with any
missing tenor are removed. Levels, yield changes and curve slopes are then
calculated from that single aligned observation calendar.

The application does not:

- forward-fill yields;
- interpolate missing observations;
- subtract independently dated latest values;
- replace a missing tenor with a proxy or zero.

The real/inflation extension applies the same rule separately to each exact
tenor. Nominal and real yields are joined on their common observation dates.
It does not substitute a real-yield or inflation series from another country.

Cross-country overview rankings use a stricter calendar shared by all 28
country-tenor series, so every displayed country is compared on the same end
date and the same observation intervals.

## Calculations

Yield changes are expressed in basis points:

`change = 100 × (latest yield − yield h common observations earlier)`

The six displayed curve slopes are:

- 2s5s
- 2s10s
- 2s30s
- 5s10s
- 5s30s
- 10s30s

Each slope is:

`100 × (back-tenor yield − front-tenor yield)`

The one-year percentile is the empirical rank of the latest value within up to
252 common observations. It is descriptive and is not an overbought/oversold
signal.

The 20-observation curve-move description uses a project diagnostic threshold
of ±5 bp:

- both 2Y and 10Y above +5 bp: both yields rose;
- both below −5 bp: both yields fell;
- otherwise: mixed or limited level movement;
- 2s10s change above +5 bp: steepening;
- below −5 bp: flattening;
- otherwise: limited shape change.

The threshold is disclosed and is not presented as an industry standard.

## Real-rate / inflation-compensation attribution

For a supported country and exact tenor:

`inflation compensation = nominal government yield - real government yield`

Rolling attribution is calculated over 10 common observations:

`nominal change = real contribution + inflation-compensation contribution`

The arithmetic residual must be zero apart from floating-point rounding. The
inflation-compensation leg includes breakeven inflation and instrument-specific
risk/liquidity premia; it is not presented as a pure expected-inflation forecast.

## Current workbook diagnostics

Individual board dates:

| Country | Aligned observations | Latest common date |
|---|---:|---|
| United States | 2,853 | 2026-08-10 |
| Germany | 2,844 | 2026-08-10 |
| Japan | 2,848 | 2026-08-10 |
| United Kingdom | 2,840 | 2026-08-10 |
| Canada | 2,851 | 2026-08-10 |
| Australia | 2,478 | 2026-08-11 |
| Switzerland | 2,798 | 2026-08-10 |

The seven-country common comparison calendar contains **2,409 observations**
and ends on **2026-08-10**.

These dates and values are derived from the current workbook and will change
when `DATA.xlsx` is updated.
