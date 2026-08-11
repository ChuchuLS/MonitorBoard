# Rates Monitor v40 — test results

## Commands

```bash
python -m compileall -q .
PYTHONUNBUFFERED=1 python smoke_test.py
FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
```

## Results

- Compile: passed.
- Headless smoke test: `ALL SMOKE TESTS PASSED`, elapsed 33.2 seconds.
- Export integration: `ALL EXPORT TESTS PASSED`, elapsed 25.63 seconds.
- Snapshot: 16 registered pages; CLI 54.31.
- Lightweight HTML: 23,680 characters.
- Full inline Plotly HTML: 4,896,708 characters.

## Key production diagnostics

- Composite Liquidity Index: **54.3098**, Neutral, published 2026-08-05.
- Policy pressure: **+0.09**, Normal, six confirmed spreads.
- SFR generic strip: Ready, 687 aligned observations, model date 2026-07-24.
- Market linkage: **62.6%** PC1 explained variance, two-year percentile 88.
- Sector reference breadth: **54.5%** above own 50-observation average.
- Sector 21-observation dispersion: **4.01pp**.
- FX pairs: all four Ready under the verified common-date calendar.
- XCCY basis: five currencies × two tenors Ready.
- CSI A500, DJI and DSPX: correctly reported Missing; no proxy used.

## Data-vintage gate

- Core A:ES mismatch rows versus uploaded workbook: **0**.
- Corrected ET:GF mismatch rows versus prior verified workbook: **0**.
- Uploaded ET:GF exact matches at same dates: **0**.
- Uploaded ET:GF exact matches at prior date +10 calendar days: **715/715**.
- Weekend observations after correction: zero for FX, S&P sectors, SFR and
  Swiss-yield groups.

## Environment note

`pyarrow` is not installed in the test runtime, so the loader correctly fell
back to `DATA.xlsx`. `requirements.txt` includes pyarrow for deployed cache use.
