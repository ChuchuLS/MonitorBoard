# Rates & Liquidity Research Pack

A daily macro / liquidity research pack built as a dark-theme Streamlit app.
The reference PDF is used as a **content and model benchmark** — the goal is
to build equivalent analytical depth inside the dashboard, not to generate PDF
files. The anchor model is a **Composite Liquidity Index** built from raw market
indicators. Around that anchor sit research chapters covering rates, curves,
global yields, cross-asset regimes, and macro scoring.

> **Phase 1** delivered the research-pack shell.
> **Phase 2** implemented Rate Decomposition, Curve Regimes, and Global Rates.
> **Phase 3** added the daily summary, data dependency map, and export tools.
> **Phase 5** added the content gap analysis (Section 09 · Model Roadmap).
>
> HTML export is a side utility, not the main roadmap. The main roadmap is
> building PDF-like research content — section by section, model by model —
> inside the Streamlit app.
>
> **Ticker correction:** FARWCBLS INDEX is Central Bank Liquidity Swaps (H.4.1),
> not Fed repo or SRF usage. The CLI numerical history was preserved when the
> label was corrected. See `docs/NON_FABRICATION.md`.
>
> **Calendar correction:** the 39 fields added from `DATA-NEW(1).xlsx` were
> rebuilt by exact joins to each Bloomberg output block's own Date column. No
> inferred day shift or row-position merge is used. See
> `docs/CALENDAR_CORRECTION_2026-08-03.md`.
>
---

## Quick start (run on your own computer)

You need Python 3.10+ installed. Then, from a terminal in this folder:

```bash
pip install -r requirements.txt
streamlit run app.py
```

A browser tab opens with the dashboard. That's it.

The production dependency set is pinned in `requirements.txt`. The repository
tests that same set on Python 3.12 and 3.14 before deployment. Do not upgrade an
individual package in isolation; update the pins together with the smoke tests.

## Updating the market data

`DATA.xlsx` is the **source of truth** — it's the only file you edit. The
`latest.parquet` next to it is a **derived cache** that the app rebuilds
**automatically** whenever the Excel changes, so the workflow is simply:

1. Replace `data/DATA.xlsx` with your refreshed Bloomberg pull.
2. Commit & push it (and let Streamlit Cloud redeploy), or just re-run locally.

On the next start the app hashes `DATA.xlsx` (SHA-256), compares it to the hash
recorded in `latest.parquet.meta.json`, and if they differ — or the parquet is
missing — it rebuilds the cache from the Excel on the spot, then loads it. If the
cache can't be built for any reason (e.g. a read-only filesystem), it falls back
to reading `DATA.xlsx` directly so the dashboard always runs. A content hash is
used rather than a file timestamp because mtimes are unreliable after a git
checkout or Cloud redeploy.

You can confirm what happened any time on the **Data Quality & Methodology**
page (Section 08), which shows the source file, the cache status, the latest
data date, and the exact index methodology version + hash.

> Running `python scripts/build_parquet.py` is optional — it just pre-warms the
> cache locally and also writes the `metadata.csv` / `ticker_map.csv` inspection
> sidecars. You never need it for the app to see new data.

> **Tip:** don't commit the derived files. The included `.gitignore` already
> excludes `latest.parquet`, its `.meta.json`, and the CSV sidecars so that only
> `DATA.xlsx` travels in version control.

### Deploying to share a link
Push the folder to GitHub and point [Streamlit Community Cloud](https://share.streamlit.io)
at `app.py`. To password-protect it, add a secret named `app_password` in the
app settings — the login gate turns on automatically. With no secret set, the
app is open (handy for local use).

Every push and pull request runs `.github/workflows/ci.yml`: source compilation,
the model/data smoke suite, Excel/HTML/PDF/CTA export integration, and a real
Streamlit runtime check of Contents plus A2 CTA Backtest. A failed check should
be fixed before the Streamlit deployment is treated as production-ready.

---

## Sections

Navigation is registry-driven from `config/pages.py`. The Contents landing
page mirrors the front matter of an institutional chart pack.

| No. | Section                         | Status               | Data source | What it shows |
|----:|:--------------------------------|:---------------------|:------------|:--------------|
| 00  | Liquidity Overview              | **Live**             | DATA.xlsx | Composite Liquidity Index (v0.3) with bucket & component contributions, benchmark validation, methodology audit, one-click Excel export, and a compact latest-value XCCY basis summary. |
| 01  | Policy & Short Rates            | **Live**             | DATA.xlsx | Confirmed SOFR / EFFR / IORB and repo-rate spreads, funding-pressure diagnostics, and weekly H.4.1 context. The fixed-contract SOFR strip is a separate live page; the meeting-by-meeting FOMC path remains unimplemented. |
| 01b | SOFR Futures Strip & Calendar Spreads | **Live** | DATA.xlsx / Policy_Futures | Eight fixed quarterly SFR contracts from Sep 2026 through Jun 2028. Shows implied rates, 1D/5D/1M changes, 3M/6M/12M calendar spreads and terminal diagnostics. Not a meeting-by-meeting FOMC probability model. |
| 02  | Rate Decomposition              | **Live**             | DATA.xlsx / Sheet1 | US curve complex, selectable-tenor rolling rate attribution, and 2s10s curve decomposition using breakeven identity. |
| 03  | Curve Regimes                   | **Live**             | DATA.xlsx / Sheet1 | 7-regime classification across nominal / real / inflation curves and six tenor pairs. |
| 04  | Global Rates                    | **Live**             | DATA.xlsx / Sheet1 | Normalized global 10Y overlay using genuine observations only, global curve snapshots, and 2s10s slope ranking (US/DE/JP/UK/CA/AU/CH). |
| 04b | Country Rate Boards             | **Live / partial real-rate coverage** | DATA.xlsx / Sheet1 | Fully aligned 2Y/5Y/10Y/30Y nominal boards for seven countries, plus exact-tenor nominal/real/inflation-compensation attribution for US/DE/JP/UK/CA/AU. Switzerland is explicitly unavailable because no confirmed real-yield input is present. |
| 05  | Cross-Asset Regime Timeline     | **Live**             | DATA.xlsx / Sheet1 cross-asset columns | 8-regime directional classification using vol-scaled signals (20D change ÷ 21D vol). |
| 05b | Market Linkage & Correlations   | **Live**             | DATA.xlsx / Sheet1 | Reference-pack-style one-trade gauge: 63D PC1 explained variance across SPX / UST 10Y / DXY, plus the three 20D pairwise correlations. Descriptive, not causal. |
| 06  | Sector Rotation & Breadth       | **Live**             | DATA.xlsx / Sheet1 + SPX_Sector_Weights | 11 S&P 500 sector indices + SPX. Main breadth and dispersion panels reproduce the reference-pack definitions: share above each sector's own 50-observation average and cross-sectional standard deviation of trailing 21-observation returns. Also includes relative performance, rotation quadrants and sector-weight context. Optional Cboe DSPX overlay activates only when DSPX INDEX is present. |
| 06b | Sector Contribution Estimate     | **Live**             | DATA.xlsx / Sheet1 + SPX_Sector_Weights | Start-period periodic weight × sector simple return, with an explicit residual versus actual SPX. Transparent approximation only; not official index-provider attribution. |
| 06c | Global Index Trend & Market Breadth | **Partial**        | DATA.xlsx / Equity_Prices + optional Index_Breadth | One index dropdown controls the price-trend and breadth monitor. Real 50D/200D moving averages activate when history permits; constituent-level advance–decline, 52-week high/low, MA breadth, RSI breadth and put/call panels remain missing until their own source fields are supplied. |
| 06d | Global FY1 Earnings & Valuation  | **Live**             | DATA.xlsx / Equity_EPS + Equity_Prices | One index dropdown controls the rolling exact-return decomposition and implied FY1 P/E chart. Each index uses its own BEST_EPS 1FY and cash-index price; missing inputs remain missing. |
| 07  | FX Rate Differential Monitor    | **Live**             | DATA.xlsx / Sheet1 | EURUSD / USDJPY / GBPUSD / AUDUSD rate-differential monitor plus the full EUR / JPY / AUD / GBP / CAD 3M and 12M cross-currency basis dashboard. Descriptive, not causal attribution or fair value. |
| 08  | Data Quality & Methodology      | **Live**             | DATA.xlsx (all sections) | Source-of-truth trust chain, ticker coverage, scoring-sheet audit, methodology. |
| A1  | Global Scoring (Appendix)       | **Live** | DATA.xlsx / scoring sheets | Cross-sectional scoring for 10 rates and 18 requested equities. Equity ranking uses four-factor Macro + EPS; regional FCI is context only. |
| A2  | CTA Score Backtest              | **Partial — limited sample** | DATA.xlsx / scoring sheets | Fixed weekly Top 3 minus Bottom 3 evaluation for Equity and Rates Scores. Shows all usable periods and limitations; it is not validated strategy P&L. |
| 09  | Model Roadmap & Content Gap     | **Live**             | DATA.xlsx (all sections) | Content gap analysis vs reference PDF — what is implemented, missing, and next. |

### Implemented now
- Composite Liquidity Index (**v0.3, unchanged**): five buckets, coverage gate,
  weekly true-observation z-scoring, methodology versioning, legacy reconciliation,
  component contributions, forward-fill audit, multi-sheet Excel export.
- PDF-style 8-regime directional Cross-Asset Timeline (SPX / UST 10Y / DXY,
  vol-scaled 20D/21D signals by default).
- Market Linkage & Correlations monitor using one fully aligned calendar for
  SPX / UST 10Y / DXY. The main line is the rolling 63D share of standardized
  variance explained by PC1, with the three 20D pairwise correlations below.
  This matches the reference chart pack's one-trade gauge structure.
  Methodology: `docs/MARKET_LINKAGE.md`.
- SOFR Futures Strip & Calendar Spreads using eight fixed quarterly contracts (`SFRU6` through `SFRM8`). Each contract keeps its own Bloomberg Date output; the model joins by Date, converts price with `100 - price`, and calculates 3M/6M/12M forward calendar spreads. It is not a meeting-by-meeting FOMC path.
- Global Scoring appendix (rates + equity cross-sectional ranking), plus a
  dedicated A2 CTA Score Backtest page and downloadable offline report generated
  by `scripts/run_cta_score_backtest.py`. The fixed specification requires a full 90-day factor
  lookback, excludes future rows and Partial equity scores, and reports gross
  results without invented transaction costs. Because high-frequency scoring
  inputs begin on 2026-02-16 and macro vintages are not archived, the output is
  explicitly a limited-sample signal check rather than strategy validation.
  Equity Macro uses GDP, inverted CPI, fiscal balance and terms-of-trade
  momentum only. At the default 50% Macro / 50% EPS weights, each Macro factor
  contributes 12.5% of the total score. The four supplied regional FCI series
  remain visible as raw context but are not mapped to indices and contribute 0%.
- Global Index Trend & Market Breadth (06c) before Earnings. Each selector row
  uses its own cash-index history for price and moving averages. The current
  workbook does not contain constituent breadth inputs, so advance–decline,
  52-week high/low, 50D/200D coverage, RSI breadth and index put/call panels are
  explicitly Partial rather than reconstructed from sectors, ETFs or proxies.
- DATA.xlsx workbook-section audit across Sheet1 and scoring sheets.
- Country Rate Boards for US / DE / JP / UK / CA / AU / CH using fully aligned
  2Y / 5Y / 10Y / 30Y nominal observations, with yield changes, curve slopes
  and empirical percentiles. The same page adds exact-date real-rate and
  inflation-compensation attribution for US / DE / JP / UK / CA / AU using
  same-tenor government yields. Switzerland remains unavailable; no euro-area
  or other-market proxy is substituted.
- Sector Rotation & Breadth monitor using 11 S&P 500 sector indices, SPX and
  periodic sector weights. Its primary panels follow the reference chart pack:
  share above each sector's own 50-observation moving average and
  cross-sectional standard deviation of trailing 21-observation sector
  returns. Supplementary return breadth and rotation diagnostics remain
  separately labelled.
- Sector Contribution Estimate using the latest periodic weight available on or
  before each return-window start date multiplied by sector simple returns, with
  the residual versus actual SPX shown explicitly. This is not official attribution.
  Methodology: `docs/SECTOR_CONTRIBUTION_ESTIMATE.md`.
- Global FY1 Earnings & Valuation monitor using the user-confirmed Bloomberg
  `BEST_EPS` field with `BEST_FPERIOD_OVERRIDE=1FY` at weekly frequency. It
  matches each EPS source date backward to the latest observed cash-index close
  within three calendar days, without forward-fill, interpolation, or proxies. It
  calculates implied FY1 P/E and the exact additive log identity: index return =
  FY1 EPS growth + P/E change. A separate 26-week OLS diagnostic is descriptive
  and is not the reference pack's 3-year daily regression.
- PDF-style research-pack shell with per-section colours, page registry, and
  honest status classification.

### Previously scaffold — now implemented
- **Rate Decomposition** (02) — now live with US curve complex + attribution.
- **Curve Regimes** (03) — now live with 6-pair regime matrix.
- **Global Rates** (04) — now live with a no-fill 7-country overlay (incl. Switzerland) + slope ranking.
- **Country Rate Boards** (04b) — live fully aligned four-tenor nominal boards for all seven countries, with partial exact-tenor real/inflation coverage for six countries.

### Data files
| File | Contents | Source of truth |
|:-----|:---------|:---------------|
| `data/DATA.xlsx` | Single workbook: Sheet1 = daily market data (189 cols, including DSPX); scoring sheets = Macro_GDP, Macro_CPI, Macro_Fiscal, Rates_10Y, Equity_ToT, Equity_FCI, Equity_EPS, Equity_Prices | Yes — the only file you manually update |
| `data/latest.parquet` | Derived cache of Sheet1 | No — auto-rebuilt, not committed |


### Added-data calendar lineage

The added FX, sector, policy-futures and Switzerland-yield blocks are joined to
`Sheet1` by the Date column emitted by their own Bloomberg spill. Sector weights
use the Date column in `SPX_Sector_Weights`. The application does not shift
weekend labels or merge these blocks by row position. Calendar profiles and the
SPX parent/sector range test are shown on **Data Quality & Methodology**.

For the 2026-08-06 refresh, the core A:ES block was accepted as the new vintage,
The current workbook refresh restores normal Monday–Friday calendars for the
expanded Sheet1 series and adds an independently dated `Policy_Futures` worksheet.
The fixed-contract loader joins every SFR contract by its own source Date column;
no row-position merge or inferred calendar shift is used. See
`docs/POLICY_FUTURES_FIXED_STRIP.md`.

### Research pack structure

**Core live pages** — fully implemented on real data, tested:
- 00 Liquidity Overview (Composite Liquidity Index v0.3)
- 01 Policy & Short Rates (spot rates + funding plumbing)
- 01b SOFR Futures Strip & Calendar Spreads (eight fixed quarterly contracts; not an FOMC probability path)
- 02 Rate Decomposition (breakeven identity: nominal = real + inflation)
- 03 Curve Regimes (7-regime classification, 6 tenor pairs)
- 04 Global Rates (no-fill 7-country overlay (incl. Switzerland) + slope ranking)
- 04b Country Rate Boards (fully aligned nominal boards + exact-tenor real/inflation attribution where available)
- 05 Cross-Asset Regime Timeline (8-regime vol-scaled directional)
- 05b Market Linkage & Correlations (SPX / UST 10Y / DXY one-trade gauge + pairwise correlations)
- 06 Sector Rotation & Breadth (11 S&P 500 sectors + SPX — descriptive, not attribution)
- 06b Sector Contribution Estimate (periodic start weights × sector simple returns, explicit residual; not official attribution)
- 06c Global Index Trend & Market Breadth (selectable real price trend; constituent breadth inputs explicitly Partial)
- 06d Global FY1 Earnings & Valuation (single index dropdown; BEST_EPS 1FY, implied P/E, exact weekly decomposition)
- 07 FX Rate Differential Monitor (EURUSD / USDJPY / GBPUSD / AUDUSD + full 3M/12M XCCY basis dashboard)
- 08 Data Quality & Methodology (workbook audit + dependency map)

**Appendix:**
- A1 Global Scoring (cross-sectional macro + market ranking)
- A2 CTA Score Backtest (live page, Partial because history is limited and rates are not investable P&L)

**Future analytical modules not yet implemented** — the app intentionally does
NOT fake these. Future analytical modules may require additional methodology,
metadata, testing, or data.

**Requested reference-pack inputs now available in DATA.xlsx:**
- `DSPX INDEX` — Cboe S&P 500 Dispersion Index in `Sheet1`; overlaid on a separate axis from realised 21-observation sector-return dispersion.
- `CSIA500 INDEX` — CSI A500 cash-index price and BEST_EPS/1FY history in `Equity_Prices` and `Equity_EPS`. Existing XIN9I / FTSE China A50 data remain separate and are not relabelled.
- `NIFTY INDEX` — Nifty 50 cash-index price and BEST_EPS/1FY history in `Equity_Prices` and `Equity_EPS`. Its own India GDP, CPI, fiscal and terms-of-trade inputs are used in the common four-factor Equity Macro score; FCI is not required for any index ranking.
- `VN30 INDEX` — VN30 cash-index price and BEST_EPS/1FY history in `Equity_Prices` and `Equity_EPS`. Its own Vietnam GDP, CPI, fiscal and terms-of-trade inputs are used in the common four-factor Equity Macro score; FCI is not required for any index ranking.
- `DJI INDEX` — Dow Jones Industrial Average cash-index price and BEST_EPS/1FY history in `Equity_Prices` and `Equity_EPS`.

- FOMC implied policy path (fixed contract months are now available; the FOMC calendar, day-weighted meeting-month method and probability framework are still needed)
- FX regression attribution (descriptive monitor is live; regression methodology not designed)
- FX fair-value / forecast model (equilibrium framework not designed)
- Official SPX sector attribution (daily-weight methodology or official contribution data required)
- Forward estimate vs realized EPS (realized/trailing EPS field and period definition not supplied)

**Deferred methodology research memo:** Section 09 records four questions for a
later empirical review: bucket-weight calibration, regime-threshold calibration,
missing-bucket weight treatment, and historical-event validation. They are
research reminders only; recording them does not change the live model.

---

## One-click PDF and static research-pack export

The Streamlit sidebar includes **Export Board to PDF**. It downloads a complete
16:9 research pack generated from the current `DATA.xlsx` vintage, rather than
printing only the page currently open. The PDF includes:

- a cover and linked contents page;
- one page for every registered Board page;
- PDF bookmarks, top-section navigation and previous/next links;
- current tables and vector charts generated from the production models;
- explicit unavailable/partial states when verified inputs are missing.

The PDF is cached by the `DATA.xlsx` content hash and production date, so a data
update automatically invalidates the prior export. It can also be built from the
command line:

```bash
python scripts/export_research_pack_pdf.py  # → output/pdf/rates_liquidity_board_<YYYYMMDD>.pdf
```

Two command-line scripts generate offline exports from DATA.xlsx:

```bash
python scripts/export_research_pack_snapshot.py   # → data/snapshot.json
python scripts/export_research_pack_html.py       # → reports/research_pack_<YYYYMMDD>.html
```

The HTML report is a standalone offline file — all CSS and Plotly JS are embedded
inline, so it can be opened locally without internet access.

The snapshot includes the page registry and key implemented outputs.
The static HTML export currently covers a subset of the Streamlit models.
Missing export coverage must not be interpreted as missing source data or
an unimplemented Streamlit model. The automated PDF export is separate and
covers every registered Board page.

The PDF download is always visible in the Streamlit sidebar and is repeated on
the **Contents** page inside the "Export research pack" expander.

---

## The Composite Liquidity Index — methodology (v0.3)

---

**Reading it:** higher = looser, **50 = neutral**, ≥60 Loose, <45 Tight, <35 Stress.
The live methodology version, parameters, data hash, and coverage are shown in the
**Methodology & audit trail** panel on the index page (single source of truth:
`index/methodology.py::INDEX_METHODOLOGY`).

It is built from *raw* indicators — Bloomberg FCI and Chicago Fed NFCI are used
**only as benchmarks**, never as inputs.

**1. Indicators, grouped into five buckets**

| Bucket | Weight | Example indicators |
|---|---|---|
| Money-market funding | 30% | SOFR−IORB, EFFR−IORB, SOFR−EFFR, TGCR/BGCR−IORB |
| Dollar funding / XCCY | 20% | EUR/JPY/GBP/AUD/CAD 3M basis |
| Credit liquidity | 20% | IG & HY OAS, EMBI, iTraxx, bank CDS, mortgage spread |
| Central bank / reserves | 20% | Reserve balances (H.4.1), central bank liquidity swaps (H.4.1) |
| Market liquidity / vol | 10% | UST liquidity index, swap spread, (MOVE, VIX if present) |

**2. Direction adjustment.** Each indicator is multiplied by ±1 *before*
z-scoring so that **higher always means looser** (e.g. HY OAS gets −1; reserves +1).

**3. Z-scoring.** Each adjusted indicator becomes a rolling z-score —
`window = 1260` (~5y), `min_periods = 504` (~2y), clipped to `[-3, 3]`. A
**low-variation guard** sets the z to NaN whenever the trailing window holds fewer
than 20 distinct values, so a near-flat series (e.g. EFFR−IORB before 2019) can't
turn a 1bp move into a fake ±3σ spike. The whole index runs on a **business-day
grid**, so stray weekend prints in the raw feed can't create inconsistent coverage.

**3a. Weekly / low-frequency series (new in v0.3).** Reserve balances with Federal Reserve Banks and Central Bank Liquidity Swaps (H.4.1) are
reported **weekly on Wednesdays** but arrive as daily-repeated values in
`DATA.xlsx`. Treating every repeated row as a fresh print deflates their variance
and defeats the forward-fill cap. Instead each component carries metadata
(`frequency`, `max_ffill_days`, `observation_mode`) and weekly series use
`observation_mode = "weekday"`: the z-score is computed on the **true Wednesday
observations** (over a frequency-appropriate ~5y window of weekly prints) and then
the **z-score** — not the raw value — is forward-filled onto the daily grid for at
most `max_ffill_days` (10) business days. Beyond that the component goes
not-live until the next real observation, so a frozen weekly value can't stay live
forever. (`change_dates` compression is available only as a fallback; it would
wrongly drop legitimately-unchanged weeks, so it is not the default.) The
**Forward-Fill Audit** table reports, per component, the latest true observation,
days since, live/stale status with reason, and the % of the last year that was
forward-filled (~80% for weekly series, as expected).

**4. Sub-index & composite.** Each bucket's sub-index is the mean of its live
component z-scores, but a bucket only counts on days it has **≥2 live components**.
The composite is the weighted average over qualifying buckets; weights renormalise
across whichever buckets have data, and the **effective weights are charted** so
concentration is transparent.

**5. Scaling.** `liquidity_index = 50 + 10 × composite_z`.

**6. Coverage gate.** A date is **published** only with **≥3 qualifying buckets**
and **≥8 contributing components**, past the rolling-z warm-up (126 business days).
With the current data the index is computable from 2016 but reliable/published from
**2019-08-19**, when the SOFR plumbing begins and a third well-populated bucket
exists. (Earlier dates are NaN, which is what removed the 2016–2018 oscillations.)

**7. Contribution decomposition (bucket and component).** Bucket contributions sum
*exactly* to `index − 50`; **component** contributions also sum to `index − 50` via
`contribution_i = 10 · effective_weight_b · z_i / n_live_in_bucket_b`. Both level
and 1w/1m/3m change contributions reconcile to the published index change. The
**Component Contributions** section ranks the top easing/tightening drivers and
lists every excluded component with a reason (Missing data / Stale (capped
forward-fill) / Failed low-unique-observation guard / Bucket has <2 live components
/ Coverage gate / Insufficient rolling history).

**8. Methodology versioning & reconciliation (new in v0.3).** The index carries a
formal version. The **Index Methodology Reconciliation** section recomputes a
**legacy** index (no coverage gate, no min-2-per-bucket, no low-unique guard,
unlimited forward-fill, daily treatment of weekly data) on the *same* latest data
and shows the legacy-vs-current difference per bucket — so you can tell whether a
headline move came from **market data** or from **methodology**. The reconciliation
identities (`Σ current contribs = current−50`, `Σ legacy = legacy−50`,
`Σ diffs = current − legacy`) are asserted in the smoke test.

**9. Validation.** Correlation table, rolling 1y correlation, crisis-window check
(Sep-2019 repo, COVID, 2022 QT, Mar-2023 banks), and a lead-lag cross-correlation.
Run `python scripts/diagnose_spikes.py` for the coverage/spike diagnostic and
`python smoke_test.py` for the full reconciliation/audit checks.

---

## Project structure

```
rates_monitor/
  app.py                 # layout + page routing only
  config/
    tickers.py           # internal-key -> Bloomberg-ticker map + tenor configs
    theme.py             # OFR dark palette, regime/bucket colours, CSS, layout
  data/
    loader.py            # hash-based auto-rebuild of the cache, Excel fallback
    transforms.py        # rolling z-score (window/min_periods/clip)
    quality.py           # validate_data / staleness report
    DATA.xlsx            # raw Bloomberg pull — SOURCE OF TRUTH (the file you edit)
    latest.parquet       # derived cache, rebuilt automatically when Excel changes
    latest.parquet.meta.json  # records source hash + shape for staleness checks
    metadata.csv         # optional per-column profile (build_parquet.py only)
    ticker_map.csv       # optional key -> ticker map (build_parquet.py only)
  charts/
    common.py            # auto-scaling y-axis helper + shared chart primitives
    pages/                # registry-driven Streamlit research pages
      global_rates.py, country_boards.py, sector_rotation.py, ...
    rates.py, funding.py, credit.py, liquidity.py
  models/
    country_rate_boards.py  # aligned seven-country nominal curve boards
    sector_rotation.py, sector_contribution.py, fx_rate_differential.py, ...
  index/
    components.py        # buckets, indicators, directions, builders
    composite.py         # z-score -> sub-index -> weighted index + contributions
    validation.py        # benchmark correlations / crisis check / lead-lag
  scripts/
    build_parquet.py     # DATA.xlsx -> latest.parquet + metadata + ticker_map
  smoke_test.py          # headless check: imports, index, reconciliation
```

**Robustness:** every series is fetched through `get_series`, which returns an
empty series for any missing ticker. Charts and the index simply skip absent
inputs and surface a warning rather than crashing — e.g. MOVE and VIX are not in
the current dataset, so they're listed in Data Quality and excluded from the
market-liquidity bucket automatically.

**Y-axis:** the real-rate / breakeven curves auto-scale to the visible data
(`charts/common.py:autoscale_range`) and only pull zero into view when the
series actually crosses or hugs zero — no more hard-coded `[-1, 3]`.
