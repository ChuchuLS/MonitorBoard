"""
config/pages.py
===============
Single source of truth for the research-pack navigation. Every part of the
shell reads from PAGES: sidebar radio, top-tabs strip, page header, section
footer, and the Contents page.

Phase 1.5 cleanup: pages are classified honestly as:
  - "live"      : fully implemented on real data, model matches its stated purpose
  - "partial"   : implemented but missing some intended features / data
  - "scaffold"  : structural page + honest missing-data warning
  - "requires"  : blocked pending additional Bloomberg fields
  - "experimental" : integrated from external repo, working but not the
                     PDF-reference model — labelled as PCA / interim

Data source tags tell the Data Quality page and each page header which
DATA.xlsx workbook section drives the section.
"""

from __future__ import annotations

PAGES: list[dict] = [
    {
        "id": "liquidity",
        "label": "Liquidity",
        "title": "Liquidity Overview",
        "section": "00",
        "color_key": "liquidity",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Composite Liquidity Index — five-bucket, coverage-gated "
                       "rolling z-score gauge (higher = looser). Includes bucket "
                       "and component contributions, benchmark validation, and "
                       "methodology audit.",
        "builds_on": None,
        "next": "policy",
    },
    {
        "id": "policy",
        "label": "Policy",
        "title": "Policy & Short Rates",
        "section": "01",
        "color_key": "policy",
        "status": "partial",
        "data_source": "sheet1_market",
        "description": "Fed policy rates, SOFR/EFFR/IORB plumbing and spreads, "
                       "funding-market pressure indicators. FOMC path and SOFR "
                       "futures strip pending meeting-dated futures data.",
        "builds_on": "liquidity",
        "next": "decomposition",
    },
    {
        "id": "decomposition",
        "label": "Decomp",
        "title": "Rate Decomposition",
        "section": "02",
        "color_key": "decomposition",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Decompose nominal yield moves into real-rate and inflation "
                       "components (identity form via TIPS breakevens or swap form "
                       "via ZCIS with residual). US curve complex + rolling rate attribution + "
                       "2s10s curve decomposition. Uses breakeven identity.",
        "builds_on": "policy",
        "next": "regimes",
    },
    {
        "id": "regimes",
        "label": "Regimes",
        "title": "Curve Regimes",
        "section": "03",
        "color_key": "regimes",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "7-regime classification (bull/bear × steepener/flattener/twist/neutral) across "
                       "nominal, real, and inflation curves on 6 tenor pairs.",
        "builds_on": "decomposition",
        "next": "global_rates",
    },
    {
        "id": "global_rates",
        "label": "Global",
        "title": "Global Rates",
        "section": "04",
        "color_key": "global_rates",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Global 10Y normalized overlay, yield curve snapshots, and "
                       "2s10s slope ranking across US, DE, JP, UK, CA, AU, CH. "
                       "",
        "builds_on": "regimes",
        "next": "cross_asset",
    },
    {
        "id": "cross_asset",
        "label": "Cross-Asset",
        "title": "Cross-Asset Regime Timeline",
        "section": "05",
        "color_key": "cross_asset",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "8-regime directional classification using SPX / UST 10Y / "
                       "DXY vol-scaled signals: 20D change ÷ 21D trailing "
                       "volatility. The sign of each signal determines UP/DOWN. "
                       "Uses DATA.xlsx / Sheet1 cross-asset columns (SPX, USGG10YR, DXY).",
        "builds_on": "global_rates",
        "next": "market_linkage",
    },
    {
        "id": "market_linkage",
        "label": "Linkage",
        "title": "Market Linkage & Correlations",
        "section": "05b",
        "color_key": "cross_asset",
        "status": "experimental",
        "data_source": "sheet1_market",
        "description": "PCA-based dominant-theme extraction on SPX / UST 10Y / DXY. "
                       "Rolling correlations, PC1 loadings and explained variance, "
                       "4-regime relative classification. Experimental — not the "
                       "same model as the 8-regime directional timeline.",
        "builds_on": "cross_asset",
        "next": "sector_rotation",
    },
    {
        "id": "sector_rotation",
        "label": "Sectors",
        "title": "Sector Rotation & Breadth",
        "section": "06",
        "color_key": "cross_asset",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Descriptive monitor for the 11 S&P 500 sector indices: "
                       "absolute and relative performance vs SPX, breadth, "
                       "cross-sectional dispersion, rotation quadrants, and "
                       "sector-weight context. Not causal attribution or "
                       "official SPX return attribution. ETF proxies are "
                       "excluded from the production model.",
        "builds_on": "market_linkage",
        "next": "fx_rate_diff",
    },
    {
        "id": "fx_rate_diff",
        "label": "FX Rates",
        "title": "FX Rate Differential Monitor",
        "section": "07",
        "color_key": "fx",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Descriptive FX rate-differential monitor for EURUSD, USDJPY, "
                       "GBPUSD, AUDUSD against 2Y/10Y nominal and 10Y real yield "
                       "differentials. Not causal attribution or fair value.",
        "builds_on": "sector_rotation",
        "next": "fx",
    },
    {
        "id": "fx",
        "label": "FX PCA",
        "title": "FX Complex PCA",
        "section": "07b",
        "color_key": "fx",
        "status": "experimental",
        "data_source": "sheet1_market",
        "description": "PCA-based regime classification on DXY / EM FX / USDJPY "
                       "12M xccy basis. Experimental — separate from the live "
                       "FX rate-differential monitor.",
        "builds_on": "fx_rate_diff",
        "next": "data_quality",
    },
    {
        "id": "data_quality",
        "label": "Data",
        "title": "Data Quality & Methodology",
        "section": "08",
        "color_key": "data_quality",
        "status": "live",
        "data_source": "all",
        "description": "Source-of-truth trust chain for DATA.xlsx workbook "
                       "sections, ticker coverage, scoring-sheet audit, "
                       "forward-fill audit, and Composite Liquidity Index "
                       "methodology.",
        "builds_on": "fx",
        "next": "scoring",
    },
    {
        "id": "scoring",
        "label": "Scoring",
        "title": "Global Scoring (Appendix)",
        "section": "A1",
        "color_key": "scoring",
        "status": "live",
        "data_source": "scoring_sheets",
        "description": "Cross-sectional macro + market scoring model for 10 "
                       "sovereign bond markets and 17 equity index futures. "
                       "Appendix — standalone model. Uses DATA.xlsx / scoring sheets.",
        "builds_on": "data_quality",
        "next": "model_roadmap",
    },
    {
        "id": "model_roadmap",
        "label": "Roadmap",
        "title": "Model Roadmap & Content Gap",
        "section": "09",
        "color_key": "data_quality",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Content gap analysis vs the reference PDF. Shows what "
                       "is implemented, what is missing, what data is needed, "
                       "and what should be built next.",
        "builds_on": "scoring",
        "next": None,
    },
]

# Also add a "rates_pca" page for the within-rates PCA that was misnamed as
# "decomposition" — it moves here as an experimental page.
# Insert it after decomposition in the nav.
_RATES_PCA = {
    "id": "rates_pca",
    "label": "Rates PCA",
    "title": "Rates Complex PCA",
    "section": "02b",
    "color_key": "decomposition",
    "status": "experimental",
    "data_source": "sheet1_market",
    "description": "Within-rates PCA on UST 10Y / 2s10s / 10Y breakeven / "
                   "10Y real yield / MOVE. Experimental — this is a PCA "
                   "regime model, NOT the PDF-style nominal = real + inflation "
                   "decomposition.",
    "builds_on": "decomposition",
    "next": "regimes",
}
# Insert after decomposition
_idx = next(i for i, p in enumerate(PAGES) if p["id"] == "decomposition")
PAGES.insert(_idx + 1, _RATES_PCA)
# Fix linkage: decomposition.next -> rates_pca, rates_pca.next -> regimes
PAGES[_idx]["next"] = "rates_pca"


# Convenience lookups
PAGES_BY_ID: dict[str, dict] = {p["id"]: p for p in PAGES}
PAGE_IDS: list[str] = [p["id"] for p in PAGES]


def get_page(page_id: str) -> dict:
    return PAGES_BY_ID[page_id]


def nav_label(page: dict) -> str:
    return f"{page['section']} · {page['label']}"


STATUS_LABELS = {
    "live":         "Live",
    "partial":      "Partial",
    "scaffold":     "Scaffold — build next",
    "requires":     "Requires data",
    "experimental": "Experimental",
}

STATUS_COLORS = {
    "live":         "#5fb04f",
    "partial":      "#d99830",
    "scaffold":     "#35bdf4",
    "requires":     "#d04848",
    "experimental": "#b184ff",
}


# ---------------------------------------------------------------------------
# Data source registry (requirement #5)
# ---------------------------------------------------------------------------
DATA_SOURCES = {
    "sheet1_market": {
        "file": "data/DATA.xlsx",
        "sheet": "Sheet1",
        "role": "Main market data: liquidity, rates, credit, cross-asset, FICC, FX PCA inputs",
        "source_of_truth": True,
        "pages": [
            "liquidity", "policy", "decomposition", "regimes",
            "global_rates", "cross_asset", "market_linkage",
            "rates_pca", "fx",
        ],
    },
    "scoring_sheets": {
        "file": "data/DATA.xlsx",
        "sheet": "Macro_GDP / Macro_CPI / Macro_Fiscal / Rates_10Y / Equity_*",
        "role": "Global scoring model sheets (macro + market factors)",
        "source_of_truth": True,
        "pages": ["scoring"],
    },
}
