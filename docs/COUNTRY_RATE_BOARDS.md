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

The boards are descriptive nominal sovereign-curve monitors. They are not
policy forecasts, trade recommendations, or causal models.

## Inputs

Each country requires the canonical `DATA.xlsx / Sheet1` series for:

- 2Y nominal government yield
- 5Y nominal government yield
- 10Y nominal government yield
- 30Y nominal government yield

Ticker selection comes only from `config/tickers.py`.

## Common-calendar rule

For an individual country, all four tenors are aligned first and rows with any
missing tenor are removed. Levels, yield changes and curve slopes are then
calculated from that single aligned observation calendar.

The application does not:

- forward-fill yields;
- interpolate missing observations;
- subtract independently dated latest values;
- replace a missing tenor with a proxy or zero.

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

## Current workbook diagnostics

Individual board dates:

| Country | Aligned observations | Latest common date |
|---|---:|---|
| United States | 2,854 | 2026-07-27 |
| Germany | 2,844 | 2026-07-24 |
| Japan | 2,849 | 2026-07-27 |
| United Kingdom | 2,840 | 2026-07-24 |
| Canada | 2,851 | 2026-07-24 |
| Australia | 2,467 | 2026-07-27 |
| Switzerland | 694 | 2026-07-23 |

The seven-country common comparison calendar contains **686 observations** and
ends on **2026-07-23**.

These dates and values are derived from the current workbook and will change
when `DATA.xlsx` is updated.
