# Rates & Liquidity Research Pack

A daily macro / liquidity research pack built as a dark-theme Streamlit app.
The anchor model is a **Composite Liquidity Index** built from raw market
indicators that tells you, at a glance, whether financial-market liquidity is
loose or tight, whether it is improving or deteriorating, and which part of the
market is driving the move. Around that anchor sit seven research chapters in
Contents-page reading order — Policy & Short Rates, Rate Decomposition, Curve
Regimes, Global Rates, Cross-Asset Regimes, FX, and Data Quality & Methodology.

> The dashboard is being evolved from a tool-shaped page-per-view app into a
> research-pack shell. **Phase 1 (this release)** delivers the shell —
> registry-driven navigation, PDF-style page headers, KPI strips, section
> colours, missing-data warnings, and scaffolds for the pages that require
> more data. **Phase 2** will fill in the scaffolds.

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
page (Section 07), which shows the source file, the cache status, the latest
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
| 02  | Rate Decomposition              | Scaffold             | DATA.xlsx | Framework for nominal = real + inflation decomposition. Data-availability check + inflation curve previews. |
| 02b | Rates Complex PCA               | Experimental         | DATA.xlsx / Sheet1 FICC columns | Within-rates PCA on 10Y / 2s10s / BE / real / MOVE. NOT the PDF-style decomposition. |
| 03  | Curve Regimes                   | Scaffold             | DATA.xlsx | Six-regime classifier framework + tenor-pair coverage. |
| 04  | Global Rates                    | Scaffold             | DATA.xlsx | Country-coverage matrix for G10 curves. |
| 05  | Cross-Asset Regime Timeline     | **Live**             | DATA.xlsx / Sheet1 cross-asset columns | 8-regime directional classification using vol-scaled signals (20D change ÷ 21D vol). |
| 05b | Market Linkage & Correlations   | Experimental         | DATA.xlsx / Sheet1 cross-asset columns | PCA-based 4-regime relative classification. Different model from 05. |
| 06  | FX Complex PCA                  | Experimental         | DATA.xlsx / Sheet1 FX/FICC columns | DXY / EM FX / USDJPY basis PCA. NOT the rate-differential FX model. |
| 07  | Data Quality & Methodology      | **Live**             | DATA.xlsx (all sections) | Source-of-truth trust chain, ticker coverage, scoring-sheet audit, methodology. |
| A1  | Global Scoring (Appendix)       | **Live**             | DATA.xlsx / scoring sheets | Cross-sectional macro + market scoring: 10 rates, 17 equities. Standalone appendix. |

### Implemented now
- Composite Liquidity Index (**v0.3, unchanged**): five buckets, coverage gate,
  weekly true-observation z-scoring, methodology versioning, legacy reconciliation,
  component contributions, forward-fill audit, multi-sheet Excel export.
- PDF-style 8-regime directional Cross-Asset Timeline (SPX / UST 10Y / DXY,
  vol-scaled 20D/21D signals by default).
- Global Scoring appendix (rates + equity cross-sectional ranking).
- DATA.xlsx workbook-section audit across Sheet1 and scoring sheets.
- PDF-style research-pack shell with per-section colours, page registry, and
  honest status classification.

### Experimental (from market-reading integration)
- **Rates Complex PCA** (02b) — within-rates PCA regime, NOT the decomposition.
- **Market Linkage** (05b) — PCA-based 4-regime model, separate from the
  directional 8-regime timeline.
- **FX Complex PCA** (06) — DXY / EM FX / basis PCA, NOT rate-differential FX.

### Partially implemented
- **Policy & Short Rates** — spot rates live; FOMC path intentionally not built.

### Scaffold — build next
- **Rate Decomposition** (02) — the true nominal = real + inflation engine.
- **Curve Regimes** (03) — multi-pair regime matrix.
- **Global Rates** (04) — cross-country overlays.

### Data files
| File | Contents | Source of truth |
|:-----|:---------|:---------------|
| `data/DATA.xlsx` | Single workbook: Sheet1 = daily market data (148 cols); scoring sheets = Macro_GDP, Macro_CPI, Macro_Fiscal, Rates_10Y, Equity_ToT, Equity_FCI, Equity_EPS, Equity_Prices | Yes — the only file you manually update |
| `data/latest.parquet` | Derived cache of Sheet1 | No — auto-rebuilt, not committed |

---
---

## The Composite Liquidity Index — methodology (v0.3)

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
| Central bank / reserves | 20% | Fed reserve balances, Fed repo/SRF usage |
| Market liquidity / vol | 10% | UST liquidity index, swap spread, (MOVE, VIX if present) |

**2. Direction adjustment.** Each indicator is multiplied by ±1 *before*
z-scoring so that **higher always means looser** (e.g. HY OAS gets −1; reserves +1).

**3. Z-scoring.** Each adjusted indicator becomes a rolling z-score —
`window = 1260` (~5y), `min_periods = 504` (~2y), clipped to `[-3, 3]`. A
**low-variation guard** sets the z to NaN whenever the trailing window holds fewer
than 20 distinct values, so a near-flat series (e.g. EFFR−IORB before 2019) can't
turn a 1bp move into a fake ±3σ spike. The whole index runs on a **business-day
grid**, so stray weekend prints in the raw feed can't create inconsistent coverage.

**3a. Weekly / low-frequency series (new in v0.3).** Fed reserves and repo are
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
