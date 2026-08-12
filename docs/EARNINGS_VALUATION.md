# SPX FY1 Earnings & Valuation

## Confirmed Bloomberg source

The user confirmed the EPS pull with the following Bloomberg Excel formula on
2026-08-04:

```text
=@BDH(B$5,"BEST_EPS",TODAY()-730,TODAY(),
      "BEST_FPERIOD_OVERRIDE=1FY","Per=W","Dir=V","Dt",
      "cols=2;rows=104")
```

Production meaning used by the application:

- Field: `BEST_EPS`
- Forecast-period override: `1FY`
- Frequency: weekly
- Direction: vertical
- Output: Date + FY1 consensus EPS estimate level

The application does **not** relabel this series as blended-forward-12-month,
trailing, or realised EPS.

## Main model

For SPX, the application intersects `Equity_EPS` and `Equity_Prices` on exact
common dates. It does not forward-fill either input.

```text
Implied FY1 P/E = SPX Index level / FY1 EPS
```

The primary decomposition is an exact additive log identity:

```text
SPX log return = FY1 EPS log growth + implied FY1 P/E log change
```

The reported identity residual should be numerical rounding only.

## Weekly OLS diagnostic

A separate diagnostic estimates a rolling single-factor OLS beta from weekly
SPX log returns and weekly FY1 EPS log changes. The default window is 26 common
weekly changes, with a 20-observation minimum.

The fitted earnings component and regression residual are descriptive model
outputs. They are not causal attribution, fair value, or a forecast. The
available common history is much shorter and lower-frequency than the
reference chart pack's 3-year daily regression, so the two models are not
presented as equivalent.

## Missing scope

A forward-estimate-versus-realised-EPS chart is not implemented because the
workbook does not contain a confirmed realised or trailing EPS series with a
comparable period definition.
