# Phase 8.2 verification — 2026-08-04

Commands:

```bash
python -m compileall -q .
PYTHONUNBUFFERED=1 python smoke_test.py
FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
```

Results:

- `ALL SMOKE TESTS PASSED ✓` — 23.1 seconds
- `ALL EXPORT TESTS PASSED ✓` — 17.99 seconds
- Registered Streamlit pages: 15
- Composite Liquidity Index: 52.13, Neutral
- Policy pressure: -0.15, Normal, model date 2026-07-23
- Sector price/SPX common date: 2026-07-23
- Sector weight rows: 37; latest date 2026-07-23

Sector Contribution Estimate, current workbook:

| Window | Actual SPX | Estimated | Residual | Start weight date |
|---:|---:|---:|---:|---|
| 1D | -1.209% | -1.218% | +0.009pp | 2026-06-30 |
| 5D | -1.665% | -1.623% | -0.042pp | 2026-06-30 |
| 20D | +0.681% | +0.595% | +0.086pp | 2026-05-29 |
| 63D | +3.788% | +3.800% | -0.012pp | 2026-03-31 |

Regression gates passed:

- common sector/SPX timestamps;
- start weight selected on or before the return start date;
- no weight normalisation, interpolation, future-weight use, zero substitution,
  or ETF proxy substitution;
- residual reconciles exactly as actual SPX return minus estimated return;
- missing sector or weight input produces `Partial` and withholds the aggregate
  estimate;
- official SPX sector attribution remains `Not Started`.
