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
                       "and component contributions, benchmark validation, "
                       "methodology audit, and a compact XCCY basis summary.",
        "builds_on": None,
        "next": "policy",
    },
    {
        "id": "policy",
        "label": "Policy",
        "title": "Policy & Short Rates",
        "section": "01",
        "color_key": "policy",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Live confirmed policy and funding-plumbing monitor: "
                       "SOFR / EFFR / IORB, TGCR / BGCR / GCF / Tri-Party spreads, "
                       "funding-pressure diagnostics and weekly H.4.1 context. "
                       "The fixed-contract SOFR futures strip is a separate live page; a "
                       "meeting-by-meeting FOMC path remains unimplemented.",
        "builds_on": "liquidity",
        "next": "policy_futures",
    },
    {
        "id": "policy_futures",
        "label": "Futures Strip",
        "title": "SOFR Futures Strip & Calendar Spreads",
        "section": "01b",
        "color_key": "policy",
        "status": "live",
        "data_source": "policy_futures_sheet",
        "description": "Eight fixed quarterly Three-Month SOFR contracts from SEP 26 "
                       "through JUN 28. Shows implied rates, 1D/5D/1M changes, 3M/6M/12M "
                       "calendar spreads, terminal-rate diagnostics and the strip curve. "
                       "Contract-month specific, but not a meeting-by-meeting FOMC path.",
        "builds_on": "policy",
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
                       "2s10s slope ranking across seven markets: US, DE, JP, UK, "
                       "CA, AU and CH.",
        "builds_on": "regimes",
        "next": "country_boards",
    },
    {
        "id": "country_boards",
        "label": "Country Boards",
        "title": "Country Rate Boards",
        "section": "04b",
        "color_key": "global_rates",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Fully aligned 2Y / 5Y / 10Y / 30Y nominal sovereign curve "
                       "boards for US, DE, JP, UK, CA, AU and CH. Shows yield levels, "
                       "common-calendar changes, curve slopes, percentiles and a "
                       "descriptive curve-move reading. No forward-fill or forecast claim.",
        "builds_on": "global_rates",
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
        "builds_on": "country_boards",
        "next": "market_linkage",
    },
    {
        "id": "market_linkage",
        "label": "Linkage",
        "title": "Market Linkage & Correlations",
        "section": "05b",
        "color_key": "cross_asset",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "PDF-aligned one-trade linkage gauge for SPX / UST 10Y / DXY. "
                       "Shows rolling PC1 explained variance and the three underlying "
                       "pairwise correlations. No regime label, causal attribution, or forecast.",
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
        "next": "sector_contribution",
    },
    {
        "id": "sector_contribution",
        "label": "Sector Est.",
        "title": "Sector Contribution Estimate",
        "section": "06b",
        "color_key": "cross_asset",
        "status": "live",
        "data_source": "sheet1_market",
        "description": "Approximate SPX sector return contribution using the latest "
                       "periodic sector weights available on or before each return "
                       "window start date. Explicit residual reconciliation. Not "
                       "official index-provider attribution.",
        "builds_on": "sector_rotation",
        "next": "earnings_valuation",
    },
    {
        "id": "earnings_valuation",
        "label": "Earnings",
        "title": "SPX FY1 Earnings & Valuation",
        "section": "06c",
        "color_key": "cross_asset",
        "status": "live",
        "data_source": "scoring_sheets",
        "description": "SPX Index level, confirmed weekly FY1 consensus EPS (BEST_EPS with 1FY override), implied FY1 P/E, exact log-return decomposition into earnings growth and multiple change, plus a clearly labelled weekly OLS diagnostic. Not fair value or a forecast.",
        "builds_on": "sector_contribution",
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
        "description": "Pair-specific FX monitor for EURUSD, USDJPY, GBPUSD and AUDUSD "
                       "against 2Y/10Y nominal and 10Y real yield differentials, plus "
                       "the full 3M/12M cross-currency basis dashboard. Not causal attribution or fair value.",
        "builds_on": "earnings_valuation",
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
        "builds_on": "fx_rate_diff",
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
        "role": "Main market data: liquidity, rates, credit, cross-asset, sectors, FX and XCCY inputs",
        "source_of_truth": True,
        "pages": [
            "liquidity", "policy", "decomposition", "regimes",
            "global_rates", "country_boards", "cross_asset", "market_linkage",
            "sector_rotation", "sector_contribution",
            "fx_rate_diff",
        ],
    },
    "policy_futures_sheet": {
        "file": "data/DATA.xlsx",
        "sheet": "Policy_Futures",
        "role": "Eight fixed quarterly Three-Month SOFR contract Date + Price BQL blocks",
        "source_of_truth": True,
        "pages": ["policy_futures"],
    },
    "scoring_sheets": {
        "file": "data/DATA.xlsx",
        "sheet": "Macro_GDP / Macro_CPI / Macro_Fiscal / Rates_10Y / Equity_*",
        "role": "Global scoring model sheets (macro + market factors)",
        "source_of_truth": True,
        "pages": ["earnings_valuation", "scoring"],
    },
}
