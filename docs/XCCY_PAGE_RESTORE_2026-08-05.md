# XCCY Page Placement Restoration — 2026-08-05

## Change

The full Cross-Currency Basis Swaps dashboard is restored to **07b · FX Complex PCA**.
It contains the original five-column by two-row layout:

- Top row: EUR, JPY, AUD, GBP and CAD 3M basis
- Bottom row: EUR, JPY, AUD, GBP and CAD 12M basis

The **00 · Liquidity Overview** page now retains a compact latest-value summary
rather than duplicating the ten full historical charts.

## Failure visibility

The prior Liquidity renderer wrapped the full XCCY block in a silent
`except Exception: pass`. A rendering failure could therefore make the entire
module disappear without explanation. The new implementation logs the failure
and shows a visible warning. Missing observations are never represented as zero.

## Data treatment

- Each 3M and 12M series retains its own latest valid observation date.
- No forward fill, interpolation, proxy substitution or zero replacement is used.
- Negative basis is displayed under the existing USD funding-premium convention.
- The charts are descriptive source-series views and do not claim causal flows.
