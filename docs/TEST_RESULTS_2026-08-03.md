# Verification results — 2026-08-03

## Commands

```bash
python -m compileall -q .
PYTHONUNBUFFERED=1 python smoke_test.py
FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
```

## Results

- Python compilation: passed.
- Main smoke test: `ALL SMOKE TESTS PASSED`.
- Export integration test: `ALL EXPORT TESTS PASSED`.
- Composite Liquidity Index: 52.13, Neutral; numerical regression unchanged.
- Policy funding pressure: -0.15, Normal; model date 2026-07-23.
- FX models: all four pairs Ready on the corrected source calendar.
- Sector model: Ready; 11 configured sectors; common sector/SPX date 2026-07-23.
- Sector/SPX return intervals: zero mismatched intervals.
- Calendar audits: no weekend observations for corrected FX, sector, policy-futures or Switzerland-yield groups.
- Parent/sector range tests: passed for 1, 5, 20 and 63 observations.
- Added-data source/date comparison: zero mismatches across 39 corrected columns.
- Latest sector weight date: 2026-07-23; latest sum: 100.00%.

The current execution environment did not have `pyarrow`, so the loader correctly
fell back to `DATA.xlsx`. `pyarrow` remains listed in `requirements.txt` for the
deployed parquet-cache path.
