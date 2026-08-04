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

---

## Quick start (run on your own computer)

You need Python 3.10+ installed. Then, from a terminal in this folder:

```bash
pip install -r requirements.txt
streamlit run app.py
```

A browser tab opens with the dashboard. That's it.

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

---

## Sections

Navigation is registry-driven from `config/pages.py`. The Contents landing
page mirrors the front matter of an institutional chart pack.

| No. | Section                         | Status               | Data source | What it shows |
|----:|:--------------------------------|:---------------------|:------------|:--------------|
| 00  | Liquidity Overview              | **Live**             | DATA.xlsx | Composite Liquidity Index (v0.3) with bucket & component contributions, benchmark validation, methodology audit, one-click Excel export. |
| 01  | Policy & Short Rates            | Partial              | DATA.xlsx | SOFR / EFFR / IORB spots, funding pressure, money-market plumbing. No FOMC path (requires meeting-dated futures). |
| 02  | Rate Decomposition              | **Live**             | DATA.xlsx / Sheet1 | US curve complex, selectable-tenor rolling rate attribution, and 2s10s curve decomposition using breakeven identity. |
| 02b | Rates Complex PCA               | Experimental         | DATA.xlsx / Sheet1 FICC columns | Within-rates PCA on 10Y / 2s10s / BE / real / MOVE. NOT the PDF-style decomposition. |
| 03  | Curve Regimes                   | **Live**             | DATA.xlsx / Sheet1 | 7-regime classification across nominal / real / inflation curves and six tenor pairs. |
| 04  | Global Rates                    | **Live**             | DATA.xlsx / Sheet1 | Normalized global 10Y overlay, global curve snapshots, 2s10s slope ranking (US/DE/JP/UK/CA/AU/CH). |
| 05  | Cross-Asset Regime Timeline     | **Live**             | DATA.xlsx / Sheet1 cross-asset columns | 8-regime directional classification using vol-scaled signals (20D change ÷ 21D vol). |
| 05b | Market Linkage & Correlations   | Experimental         | DATA.xlsx / Sheet1 cross-asset columns | PCA-based 4-regime relative classification. Different model from 05. |
| 06  | Sector Rotation & Breadth       | **Live**             | DATA.xlsx / Sheet1 + SPX_Sector_Weights | 11 S&P 500 sector indices + SPX. Absolute + SPX-relative performance, breadth, cross-sectional dispersion, rotation quadrants, sector-weight context. Descriptive, not causal attribution or official SPX return attribution. ETF proxies excluded from production. |
| 07  | FX Rate Differential Monitor    | **Live**             | DATA.xlsx / Sheet1 | EURUSD / USDJPY / GBPUSD / AUDUSD — fully aligned spot, 2Y nominal, 10Y nominal, and 10Y real differentials. Descriptive, not causal attribution or fair value. |
| 07b | FX Complex PCA                  | Experimental         | DATA.xlsx / Sheet1 FX/FICC columns | DXY / EM FX / USDJPY basis PCA. Experimental — separate from the live rate-differential monitor. |
| 08  | Data Quality & Methodology      | **Live**             | DATA.xlsx (all sections) | Source-of-truth trust chain, ticker coverage, scoring-sheet audit, methodology. |
| A1  | Global Scoring (Appendix)       | **Live**             | DATA.xlsx / scoring sheets | Cross-sectional macro + market scoring: 10 rates, 17 equities. Standalone appendix. |
| 09  | Model Roadmap & Content Gap     | **Live**             | DATA.xlsx (all sections) | Content gap analysis vs reference PDF — what is implemented, missing, and next. |

### Implemented now
- Composite Liquidity Index (**v0.3, unchanged**): five buckets, coverage gate,
  weekly true-observation z-scoring, methodology versioning, legacy reconciliation,
  component contributions, forward-fill audit, multi-sheet Excel export.
- PDF-style 8-regime directional Cross-Asset Timeline (SPX / UST 10Y / DXY,
  vol-scaled 20D/21D signals by default).
- Global Scoring appendix (rates + equity cross-sectional ranking).
- DATA.xlsx workbook-section audit across Sheet1 and scoring sheets.
- Sector Rotation & Breadth monitor using 11 S&P 500 sector indices, SPX and
  periodic sector weights, with common-calendar returns and dynamic breadth
  denominators.
- PDF-style research-pack shell with per-section colours, page registry, and
  honest status classification.

### Experimental (from market-reading integration)
- **Rates Complex PCA** (02b) — within-rates PCA regime, NOT the decomposition.
- **Market Linkage** (05b) — PCA-based 4-regime model, separate from the
  directional 8-regime timeline.
- **FX Complex PCA** (07b) — DXY / EM FX / basis PCA, NOT rate-differential FX.

### Partially implemented
- **Policy & Short Rates** — spot rates live; FOMC path intentionally not built.

### Previously scaffold — now implemented
- **Rate Decomposition** (02) — now live with US curve complex + attribution.
- **Curve Regimes** (03) — now live with 6-pair regime matrix.
- **Global Rates** (04) — now live with 7-country overlay (incl. Switzerland) + slope ranking.

### Data files
| File | Contents | Source of truth |
|:-----|:---------|:---------------|
| `data/DATA.xlsx` | Single workbook: Sheet1 = daily market data (188 cols); scoring sheets = Macro_GDP, Macro_CPI, Macro_Fiscal, Rates_10Y, Equity_ToT, Equity_FCI, Equity_EPS, Equity_Prices | Yes — the only file you manually update |
| `data/latest.parquet` | Derived cache of Sheet1 | No — auto-rebuilt, not committed |


### Added-data calendar lineage

The added FX, sector, policy-futures and Switzerland-yield blocks are joined to
`Sheet1` by the Date column emitted by their own Bloomberg spill. Sector weights
use the Date column in `SPX_Sector_Weights`. The application does not shift
weekend labels or merge these blocks by row position. Calendar profiles and the
SPX parent/sector range test are shown on **Data Quality & Methodology**. Full
correction details are recorded in
`docs/CALENDAR_CORRECTION_2026-08-03.md` and the workbook's `Merge_Log` sheet.

### Research pack structure

**Core live pages** — fully implemented on real data, tested:
- 00 Liquidity Overview (Composite Liquidity Index v0.3)
- 01 Policy & Short Rates (spot rates + funding plumbing)
- 02 Rate Decomposition (breakeven identity: nominal = real + inflation)
- 03 Curve Regimes (7-regime classification, 6 tenor pairs)
- 04 Global Rates (7-country overlay (incl. Switzerland) + slope ranking)
- 05 Cross-Asset Regime Timeline (8-regime vol-scaled directional)
- 06 Sector Rotation & Breadth (11 S&P 500 sectors + SPX — descriptive, not attribution)
- 07 FX Rate Differential Monitor (EURUSD / USDJPY / GBPUSD / AUDUSD — descriptive, not causal)
- 08 Data Quality & Methodology (workbook audit + dependency map)

**Experimental pages** — working models from market-reading integration,
labelled as experimental, not part of the PDF-style core:
- 02b Rates Complex PCA (within-rates PCA regime)
- 05b Market Linkage & Correlations (PCA 4-regime, 63D/20D)
- 07b FX Complex PCA (DXY / EM FX / basis PCA)

**Appendix:**
- A1 Global Scoring (cross-sectional macro + market ranking)

**Future analytical modules not yet implemented** — the app intentionally does
NOT fake these. Future analytical modules may require additional methodology,
metadata, testing, or data.

- FOMC implied policy path (generic futures available, meeting calendar + methodology needed)
- SOFR futures strip (generic prices available, contract metadata needed)
- FX regression attribution (descriptive monitor is live; regression methodology not designed)
- FX fair-value / forecast model (equilibrium framework not designed)
- SPX sector contribution estimate (data available; approximation methodology + residual reconciliation required)
- Official SPX sector attribution (daily-weight methodology or official contribution data required)
- Earnings vs valuation (EPS fields not confirmed)

---

## Static research-pack export

Two command-line scripts generate offline exports from DATA.xlsx:

```bash
python scripts/export_research_pack_snapshot.py   # → data/snapshot.json
python scripts/export_research_pack_html.py       # → reports/research_pack_<YYYYMMDD>.html
```

The HTML report is a standalone offline file — all CSS and Plotly JS are embedded
inline, so it can be opened locally without internet access. Use your browser's
Print → Save as PDF for a PDF version.

The snapshot includes the page registry and key implemented outputs.
The static HTML export currently covers a subset of the Streamlit models.
Missing export coverage must not be interpreted as missing source data or
an unimplemented Streamlit model. Future automated PDF generation is a
planned enhancement.

The Streamlit app also offers lazy download buttons on the **Contents** page,
inside the "Export research pack" expander.

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
    rates.py, funding.py, credit.py, liquidity.py
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
