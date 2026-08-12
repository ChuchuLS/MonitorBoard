# Feedback implementation — 2026-08-06

Basis:

- user feedback in `1.docx`;
- reference structure and definitions in `Capital_Flows_Daily_Chart_Pack_2026_07_21(1).pdf`;
- refreshed `DATA.xlsx`, reconciled under the source-date gate described in
  `docs/DATA_VINTAGE_RECONCILIATION_2026-08-06.md`.

## 1. Composite Liquidity Index value changed

The formula remains **Composite Liquidity Index v0.3**. No weight, sign,
z-score window, coverage threshold or rescaling formula was changed.

Observed values:

- previous verified project latest: **52.1272 on 2026-07-27**;
- reconciled refreshed project latest: **54.3098 on 2026-08-05**;
- same-date comparison on 2026-07-24:
  - previous workbook: **53.5932**;
  - refreshed core workbook: **49.5682**.

The same-date difference is a data-vintage and coverage effect. On 2026-07-24,
the previous workbook had no valid values for the five money-market spread
components. The refreshed core workbook contains SOFR−IORB, EFFR−IORB,
SOFR−EFFR, TGCR−IORB and BGCR−IORB for that date. The money-market bucket then
entered the published composite instead of the remaining buckets being
renormalised across the available set. Its 2026-07-24 bucket term was
**−2.9471 index points**.

The Liquidity page now shows the methodology version, source hash, published
model date, raw workbook date and reconciliation gap, and explicitly states
that source-data revisions can change recent values without a formula change.

## 2. Futures strip should use SFR Comdty

Implemented. The live page is now **SOFR Futures Generic Strip** and uses only:

- SFR1 COMB COMDTY
- SFR2 COMB COMDTY
- SFR3 COMB COMDTY

The production chart, Data Quality audit, Q-list and documentation no longer
combine FF/SER with the requested strip. Values remain labelled as generic
ranks, not fixed expiries or FOMC meeting dates.

## 3. Rates PCA lacked clear meaning

Removed from production and deleted from the project, including the standalone
page and PCA-only model package. It is not shown in navigation, Contents,
Roadmap or README.

## 4a. Add current-state labels to regime colour-block hover

Implemented. Hovering a regime ribbon block now shows:

- date;
- `Current state: <regime>`;
- spread level where applicable.

## 4b. Replace Mixed-heavy linkage output with a common-movement line

Implemented in **05b · Market Linkage & Correlations**, following the reference
pack's page-21 structure:

- main line: rolling 63-observation PC1 explained variance across SPX, UST 10Y
  and DXY;
- lower panel: the three rolling 20-observation pairwise correlations;
- no categorical Mixed label.

Current result:

- model date: **2026-08-05**;
- common observations: **2,753**;
- PC1 explained variance: **62.6%**;
- trailing two-year percentile: **88/100**.

## 5. Overlay Cboe S&P 500 Dispersion Index

The Sector page supports an optional source series named `DSPX INDEX` and uses
a separate y-axis because implied and realised dispersion are not the same
measure. The refreshed workbook does not contain that series, so the app shows
an explicit Missing-data caption and does not synthesize or proxy it.

The primary Sector Breadth & Dispersion panels were also realigned to page 23
of the reference pack:

- breadth = share of valid sectors above their own 50-observation moving
  average;
- dispersion = population standard deviation of trailing 21-observation sector
  simple returns.

Current result as of 2026-07-23:

- breadth: **54.5%**; one-year percentile **32**;
- 21-observation dispersion: **4.01pp**; one-year percentile **60**.

The former positive-return and SPX-outperformance breadth measures remain only
as supplementary diagnostics in a collapsed expander.

## 6. China should use CSI A500; add DJI for the US

Implemented as explicit requested rows:

- China: `CSI A500 INDEX`;
- additional US index: `DJI INDEX`.

Neither ticker is present in both `Equity_Prices` and `Equity_EPS` in the
refreshed workbook. They therefore display `Missing data`. Existing FTSE China
A50 / XIN9I data are not renamed or substituted.

## 7. FX PCA produced too many Mixed readings

Removed from production and deleted from the project. The live FX section now
contains:

- EURUSD, USDJPY, GBPUSD and AUDUSD rate-differential monitors;
- the full EUR/JPY/AUD/GBP/CAD 3M and 12M cross-currency-basis dashboard.

No FX PCA or Mixed FX regime remains.

## Updated DATA.xlsx reconciliation

The refreshed workbook's established A:ES block was preserved exactly. The
ET:GF added-data block failed the date-vintage audit: all **715** populated
verified rows were reproduced under labels shifted exactly **+10 calendar
days**, with zero same-date matches. ET:GF was therefore restored from the last
verified exact-date version. No future values, interpolation, forward fill,
zero substitution or inferred day shift were accepted.

See:

- `docs/DATA_VINTAGE_RECONCILIATION_2026-08-06.md`
- `docs/DATA_VINTAGE_RECONCILIATION_AUDIT_2026-08-06.json`
