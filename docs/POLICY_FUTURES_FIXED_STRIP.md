# Fixed-Contract SOFR Futures Strip & Calendar Spreads

## Scope

The live `01b` page uses eight actual quarterly Three-Month SOFR futures from
`DATA.xlsx / Policy_Futures`:

- `SFRU6 COMB Comdty` — Sep 2026
- `SFRZ6 COMB Comdty` — Dec 2026
- `SFRH7 COMB Comdty` — Mar 2027
- `SFRM7 COMB Comdty` — Jun 2027
- `SFRU7 COMB Comdty` — Sep 2027
- `SFRZ7 COMB Comdty` — Dec 2027
- `SFRH8 COMB Comdty` — Mar 2028
- `SFRM8 COMB Comdty` — Jun 2028

Each contract is stored as its own Bloomberg BQL `Date + Price` pair. The loader
joins contracts by those Date values. It never aligns by row position and never
forward-fills, interpolates, or substitutes zero for missing observations.

## Formulae

- Implied reference rate (%) = `100 - futures price`
- 1D / 5D / 1M changes are changes in implied rate, expressed in basis points.
- `1M` is defined as 20 common trading observations.
- Calendar spread = farther-contract implied rate minus row-contract implied
  rate, in basis points.
- Matrix horizons use the quarterly sequence:
  - 3M = one contract forward
  - 6M = two contracts forward
  - 12M = four contracts forward

## Terminal diagnostic

The terminal diagnostic selects the first strip peak when the larger move from
current EFFR is upward, or the first trough when the larger move is downward.
The displayed EFFR-to-terminal gap is:

`100 × (terminal implied rate - current EFFR)`

This is a descriptive strip diagnostic, not a policy-decision probability.

## Limitations and maintenance

- The page is not a meeting-by-meeting FOMC path.
- It does not calculate hold/hike/cut probabilities.
- FOMC meeting dates, month-day weighting, and probability methodology are not
  supplied.
- The fixed contract list must be rolled manually when the front contract
  expires.
- Last-trade dates are not inferred.
