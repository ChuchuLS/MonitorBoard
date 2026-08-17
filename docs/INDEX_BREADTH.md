# Global Index Trend & Market Breadth

Section 06c sits immediately before Global FY1 Earnings & Valuation.

## What is live from the current workbook

- Selectable cash-index close from `Equity_Prices`.
- 50-day and 200-day moving averages when the selected index has enough actual
  daily closes.
- 100-week moving average only after at least 100 observed weekly closes exist.

The workbook currently contains about one year of the requested cash-index
prices, so the 100-week average is unavailable. The application does not shorten
the window or backfill an earlier level.

## Missing constituent-level breadth inputs

The reference screenshots additionally require the following series for each
index:

- advancers minus decliners;
- percentage of constituents making new 52-week highs and lows;
- percentage of constituents above their 50DMA and 200DMA;
- percentage of constituents with 14-day RSI above 70 and below 30;
- an index-specific put/call ratio where one is actually supplied.

These cannot be calculated from an index-level close. The existing 11 SPX
sector indices are not a substitute for S&P 500 constituent breadth and are not
used as one.

## Optional `Index_Breadth` sheet contract

The loader accepts one row per Date + Code with these columns:

`Date`, `Code`, `Advance_Decline`, `New_52W_Highs_Pct`,
`New_52W_Lows_Pct`, `Above_50DMA_Pct`, `Above_200DMA_Pct`,
`RSI14_Above70_Pct`, `RSI14_Below30_Pct`, `Index_Put_Call_Ratio`.

Missing columns or dates remain missing. No value is forward-filled,
interpolated, replaced with zero, or borrowed from another index.
