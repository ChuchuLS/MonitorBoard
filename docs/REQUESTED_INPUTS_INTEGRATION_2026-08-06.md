# Requested Reference-Pack Inputs — v42

Date: 2026-08-06

## Source workbook

`data/DATA.xlsx` was replaced with the user-supplied `DATA(2).xlsx`.

The integration preserves the workbook's independent source calendars:

- `DSPX Index` in `Sheet1` on the Sheet1 daily date axis.
- `CSIA500 Index` price in `Equity_Prices` and FY1 EPS in the independent
  `Equity_EPS` Date/value block.
- `DJI Index` price in `Equity_Prices` and FY1 EPS in the independent
  `Equity_EPS` Date/value block.
- Eight fixed quarterly SFR contracts remain in `Policy_Futures`.

No price or EPS series is forward-filled, interpolated, replaced with zero, or
substituted with another index.

## Cboe DSPX

- Status: Ready
- Production ticker: `DSPX INDEX` (workbook label `DSPX Index`)
- Latest eligible observation: 2026-08-05
- Latest value: 40.55

The Sector Rotation & Breadth page now:

- overlays DSPX on a separate right-hand axis;
- shows the latest DSPX level/date in the KPI strip and Current Reading;
- keeps realised 21-observation sector-return dispersion conceptually and
  visually separate from forward-looking implied dispersion;
- never synthesises DSPX from realised sector returns.

## CSI A500

- Workbook ticker: `CSIA500 Index`
- Internal model code: `CSI_A500`
- Status: Ready
- Exact common price/EPS model date: 2026-07-31
- Index level on common date: 5,629.73
- FY1 consensus EPS: 329.9704
- Implied FY1 P/E: 17.06x
- 13-week exact log decomposition:
  - index return: -4.92%
  - FY1 EPS growth: +25.60%
  - implied P/E change: -30.52%

The loader resolves the blank short-code row from the ticker row. Existing
`XIN9I Index` / FTSE China A50 data remain separate and are not relabelled.

## Dow Jones Industrial Average

- Workbook ticker: `DJI Index`
- Internal model code: `DJI`
- Status: Ready
- Exact common price/EPS model date: 2026-07-31
- Index level on common date: 52,485.03
- FY1 consensus EPS: 2,449.8363
- Implied FY1 P/E: 21.42x
- 13-week exact log decomposition:
  - index return: +5.96%
  - FY1 EPS growth: +6.22%
  - implied P/E change: -0.26%

## Export and audit integration

- Data Quality reports all three requested inputs as Available with dates and
  current values.
- `data/snapshot.json` contains `cboe_dspx` and
  `requested_equity_earnings_rows`.
- The static HTML Data Quality page audits DSPX, CSI A500, and DJI availability.
- README no longer lists these inputs as missing.
