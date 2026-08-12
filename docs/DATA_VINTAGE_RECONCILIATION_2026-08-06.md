# DATA.xlsx vintage reconciliation — 2026-08-06

## Purpose

The workbook supplied on 2026-08-06 contains two different data vintages:

- **A:ES** — the established core market-data block, genuinely refreshed to the
  new workbook date.
- **ET:GF** — the 39-series block previously added from the separate Bloomberg
  spills for FX spot, S&P 500 sectors, sector ETFs, policy futures and Swiss
  yields.

The second block did not pass the source-date audit in the uploaded workbook.
This note records the deterministic reconciliation applied before production use.

## Audit result

For every populated date row in the last verified ET:GF block:

- same-date comparison against the uploaded ET:GF block: **0 exact matches**;
- comparison against the uploaded values labelled **10 calendar days later**:
  **715 exact matches out of 715 populated rows**;
- value mismatches under that +10-day label relationship: **0**.

This demonstrates that the uploaded ET:GF block reproduced the already-verified
values under dates shifted exactly ten calendar days later. It does **not**
establish that new market observations existed for those later dates.

## Production treatment

The reconciled workbook therefore:

1. preserves the uploaded **A:ES** core block without changing its refreshed
   values;
2. restores **ET:GF** from the last verified exact-date workbook;
3. preserves the remaining workbook sheets from the uploaded refresh;
4. applies no interpolation, forward fill, zero substitution or inferred
   calendar shift;
5. does not claim fresh ET:GF observations beyond the last verified source date.

## Verification

- Core A:ES values versus the uploaded workbook: **0 mismatched rows**.
- Reconciled ET:GF values versus the last verified workbook: **0 mismatched
  rows**.
- FX, S&P sector, SFR and Swiss-yield groups contain no weekend observations
  after reconciliation.

The machine-readable audit is stored in:

`docs/DATA_VINTAGE_RECONCILIATION_AUDIT_2026-08-06.json`

## Operational requirement

Future Bloomberg refreshes should retain each spill's own Date output and join
blocks by that Date. A block whose values duplicate an earlier vintage under a
systematic date offset must be quarantined until the source Date mapping is
verified.
