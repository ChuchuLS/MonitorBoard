# Market Linkage & Correlations

## Status

**Live descriptive monitor.** The separate PCA regime page remains
**Experimental**.

## Production universe

| Asset | Bloomberg series | Daily transformation |
|---|---|---|
| SPX | `SPX INDEX` | log return, percent |
| UST 10Y | `USGG10YR INDEX` | yield change, basis points |
| DXY | `DXY CURNCY` | log return, percent |
| BCOM | `BCOM INDEX` | log return, percent |
| US HY OAS | `LF98OAS INDEX` | spread change, basis points |

The five level series are intersected on one common observation calendar before
any daily transformation is calculated. Consequently, every pairwise
correlation covers identical start and end timestamps.

## Outputs

- Current five-by-five correlation matrix.
- Rolling correlations for all ten unique pairs.
- Mean absolute pair correlation and maximum absolute pair correlation.
- Latest common-calendar moves over 1, 5, 20 and 63 observations.
- Strongest positive and strongest negative current pair.

## Interpretation limits

Correlation measures co-movement. It does not establish causality, identify
fair value, predict future returns or constitute a trading recommendation.
Mean absolute correlation is a compact integration diagnostic, not a systemic
risk score.

The `05c Market Linkage PCA` page is a separate experimental model and is not
used to generate the live 05b current reading.
