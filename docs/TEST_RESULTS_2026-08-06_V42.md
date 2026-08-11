# Rates Monitor v42 — Test Results

Date: 2026-08-06

## Commands

```bash
python -m compileall -q .
PYTHONUNBUFFERED=1 python smoke_test.py
FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
```

## Results

- `compileall`: passed
- Main smoke suite: `ALL SMOKE TESTS PASSED`, 33.0 seconds
- Export integration: `ALL EXPORT TESTS PASSED`, 31.58 seconds
- Snapshot pages: 16
- Lightweight HTML: 24,136 characters
- Full inline Plotly HTML: 4,897,164 characters

## New input checks

- DSPX: Ready, 40.55 on 2026-08-05
- CSI A500: Ready, common Price/EPS date 2026-07-31, implied FY1 P/E 17.06x
- DJI: Ready, common Price/EPS date 2026-07-31, implied FY1 P/E 21.42x
- CSI A500 and DJI are loaded from their own ticker rows; XIN9I is not used as
  a proxy.
- DSPX is displayed on a separate axis from realised sector dispersion; no
  synthetic substitution is permitted.

## Regression checks

- Composite Liquidity Index: 53.4838, Neutral, unchanged methodology
- Policy pressure: +0.09, Normal, six confirmed spreads
- Sector and SPX return calendars remain aligned
- Fixed-contract SFR strip remains Ready
- FX, Country Rate Boards, Earnings, Market Linkage, XCCY and export tests pass
- Missing values are not rendered as zero
