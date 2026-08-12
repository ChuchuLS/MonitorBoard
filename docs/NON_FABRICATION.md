# Non-Fabrication Policy

This document is the highest-priority constraint for the project.

## Rule

Do not fabricate anything. This applies to every page, model, chart, table,
KPI, label, status, ticker, data source, methodology note, current reading,
and roadmap item.

## Specific known cases

### FDTRFTRL INDEX
Fed Funds Target Rate Lower Bound. NOT: RRP, ON RRP usage, RRP take-up,
RRP award rate. Labelled only as "Fed target lower bound".

### TOMOTCSO INDEX
Possibly ON RRP offering rate — NEEDS CONFIRMATION. Not used in production
models until confirmed.

### RRPQTOON / RRPQONAR INDEX
Candidate RRP-related series — NEEDS CONFIRMATION. Not used in production
models until field meanings are verified from the Bloomberg description.

### Sector ETF proxies (XLC, XLY, etc.)
NOT true SPX sector indices. If used, must be labelled as "ETF proxy".

### Policy futures
The live SOFR strip uses eight actual quarterly SFR contracts from the
`Policy_Futures` worksheet and converts price to implied rate with `100 - price`.
It may show contract-month rates and calendar spreads. It must not be described
as a meeting-by-meeting FOMC path or probability distribution because the FOMC
calendar and day-weighted meeting-month methodology are not supplied. Legacy
FF1/SFR1/SER1 generic ranks may remain in raw inventory but are not the
production strip.

## Traceability

Every chart and table must be traceable to a real column in DATA.xlsx,
a documented formula, or a clearly marked missing-data / roadmap item.
Correctness is more important than completeness.
