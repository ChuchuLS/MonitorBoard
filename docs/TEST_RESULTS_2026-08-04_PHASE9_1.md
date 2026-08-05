# Phase 9.1 test results — Country Rate Boards

Date: 2026-08-04

## Commands

```bash
python -m compileall -q .
PYTHONUNBUFFERED=1 python smoke_test.py
FULL_EXPORT_SMOKE=1 PYTHONUNBUFFERED=1 python smoke_test_export.py
```

## Results

- `ALL SMOKE TESTS PASSED ✓`
- Routine smoke elapsed: approximately 25 seconds
- `ALL EXPORT TESTS PASSED ✓`
- Export integration elapsed: approximately 18 seconds

## Country-board checks

- Pure model imports without Streamlit.
- No forward-fill is used.
- Seven country boards are Ready.
- Every board aligns 2Y / 5Y / 10Y / 30Y before calculating changes.
- Yield and slope changes reconcile to direct common-calendar calculations.
- Cross-country overview uses one common 28-series calendar.
- Missing one tenor changes that country to Partial.
- Missing tenors are not replaced with zero or a proxy.
- Page wording contains no forecast, causal or trade claim.
- Registry, Roadmap, README, Data Quality, JSON snapshot and static HTML are consistent.

## Seven-country common overview

Common date: `2026-07-23`

| Country | 10Y | 20D 10Y change | 2s10s | 20D 2s10s change |
|---|---:|---:|---:|---:|
| US | 4.693% | +30.1 bp | +34.6 bp | +7.7 bp |
| DE | 3.203% | +34.5 bp | +31.8 bp | −1.2 bp |
| JP | 2.790% | +15.7 bp | +128.8 bp | +7.2 bp |
| UK | 5.102% | +40.3 bp | +61.4 bp | +3.0 bp |
| CA | 3.642% | +25.9 bp | +68.8 bp | +5.5 bp |
| AU | 4.991% | +26.3 bp | +37.9 bp | +7.2 bp |
| CH | 0.532% | +26.2 bp | +27.0 bp | +3.2 bp |

Existing CLI, Policy, FX, Sector Rotation, Sector Contribution, Scoring and
export tests remained unchanged and passed.
