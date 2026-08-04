# Added-data calendar correction — 2026-08-03

## Scope

This correction rebuilds the 39 fields that were added from `DATA-NEW(1).xlsx`
to `data/DATA.xlsx`. It does not change the Composite Liquidity Index formula,
Policy model, Rates models, FX formulas, or Sector formulas.

## Evidence from the source workbook

`DATA-NEW(1).xlsx` contains separate Bloomberg output blocks with their own Date
columns:

1. `Sheet1!A:A` is the Date column for the 37-series spill in `B:AL`.
2. `Sheet1!AO:AO` is the Date column for the Switzerland 10Y/30Y spill in
   `AP:AQ`.
3. The `spx index weight` worksheet contains its own Date column for sector
   weights.

The first Bloomberg request row contains duplicate XLV and XLB identifiers.
Bloomberg returned unique series in its spill. For that reason, the 37 returned
value columns were mapped by the actual spill order to the 37 canonical project
columns; the duplicate visible request labels were not used as a second ticker
registry.

## Correction method

- Joined each source block to `DATA.xlsx / Sheet1` by its own exact Date value.
- Did not join by row position.
- Did not apply a blanket `+1 day`, `-1 day`, timezone shift, or inferred trading
  date.
- Preserved missing observations as missing.
- Did not forward-fill, interpolate, replace missing values with zero, or use ETF
  proxies as sector-index substitutes.
- Refreshed `SPX_Sector_Weights` from the source weight worksheet using its own
  Date column.

## Corrected groups

- RRP candidate fields
- EURUSD, USDJPY, GBPUSD and AUDUSD spot
- 11 S&P 500 sector indices
- sector ETF proxy inventory fields
- FF, SFR and SER generic futures
- Switzerland 2Y, 5Y, 10Y and 30Y yields
- S&P 500 sector weights

## Verification results

After correction:

- The 39 added project columns match their source spills on exact dates with zero
  value/date mismatches.
- FX spot, sector indices, policy futures and Switzerland yields contain no
  Saturday or Sunday observations.
- The sector-only and sector-plus-SPX common model dates are both 2026-07-23 for
  the current workbook.
- The SPX parent return lies between the minimum and maximum sector return over
  identical 1-, 5-, 20- and 63-observation windows.
- The latest eligible sector-weight row is 2026-07-23 and sums to 100.00%.
- FX pair models remain Ready after rebuilding on the corrected source calendar.

## Audit fingerprints

- Source `DATA-NEW(1).xlsx` SHA-256:
  `c331cd6c19166268a28a1e9344c065c45488f2b10897fdd5e327e63f1b798277`
- Corrected `data/DATA.xlsx` SHA-256 at delivery:
  `c52641e7e2328a67e87a0732e3e44eb7bace383129ab34fe1fc6a041ca6bbb83`

The corrected workbook also contains the correction record in `Merge_Log`.
A machine-readable verification record is available at
`docs/CALENDAR_CORRECTION_AUDIT.json`.
