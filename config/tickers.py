"""
config/tickers.py
=================
Single source of truth for *what data the dashboard knows about*.

`TICKERS` maps a stable internal key (e.g. "SOFR") to the exact Bloomberg
column name as it appears in DATA.xlsx / latest.parquet. Everything downstream
references the key, never the raw Bloomberg string, so a vendor renaming a
ticker only needs a one-line change here.

MOVE and VIX are included when present in DATA.xlsx. The index engine and
Data Quality page still handle missing optional volatility fields gracefully
if future workbooks omit them.
"""

from __future__ import annotations

TICKERS: dict[str, str] = {
    # --- Curve slopes — 2s10s ---------------------------------------------
    "US_2s10s": "USYC2Y10 INDEX",
    "DE_2s10s": "DEYC2Y10 INDEX",
    "JP_2s10s": "JPYC2Y10 INDEX",
    "AU_2s10s": "AUYC2Y10 INDEX",
    "UK_2s10s": "UKYC2Y10 INDEX",
    "CA_2s10s": "CAYC2Y10 INDEX",
    # --- Curve slopes — 5s30s ---------------------------------------------
    "US_5s30s": "USYC5Y30 INDEX",
    "DE_5s30s": "DE020510 INDEX",
    "JP_5s30s": "JPYC1030 INDEX",
    "AU_5s30s": "AD020510 INDEX",
    "UK_5s30s": "UK020510 INDEX",
    "CA_5s30s": "CB020510 INDEX",
    # --- Real rates — 10Y --------------------------------------------------
    "US_real_10y": "GTII10 GOVT",
    "CA_real_10y": "GTCADII10Y GOVT",
    "DE_real_10y": "GTDEMII10Y GOVT",
    "UK_real_10y": "GTGBPII10Y GOVT",
    "JP_real_10y": "GTJPYII10Y GOVT",
    "AU_real_10y": "GTAUDII10YR GOVT",
    # --- Real rates — full term structure ---------------------------------
    "US_real_5y":  "GTII5 GOVT",       "US_real_30y": "GTII30 GOVT",
    "UK_real_5y":  "GTGBPII5Y GOVT",   "UK_real_30y": "GTGBPII30Y GOVT",
    "DE_real_3y":  "GTDEMII3Y GOVT",   "DE_real_7y":  "GTDEMII7Y GOVT",
    "DE_real_25y": "GTDEMII25Y GOVT",
    "JP_real_5y":  "GTJPYII5Y GOVT",   "JP_real_7y":  "GTJPYII7Y GOVT",
    "AU_real_5y":  "GTAUDII5YR GOVT",
    "CA_real_5y":  "GTCADII5Y GOVT",   "CA_real_30y": "GTCADII30Y GOVT",
    # --- Money-market funding rates ---------------------------------------
    "SOFR": "SOFRRATE INDEX",
    "IORB": "IRRBIOER INDEX",
    "EFFR": "FEDL01 INDEX",
    "GCF":  "UREPGATO INDEX",
    "TGCR": "TGCRRATE INDEX",
    "FED_TARGET_LOWER": "FDTRFTRL INDEX",   # Fed funds target rate lower bound (NOT RRP usage)
    "BGCR": "USBGRATE INDEX",
    "TPR":  "UREPTATO INDEX",
    # --- XCCY basis swaps (3M) --------------------------------------------
    "XCCY_EUR": "EUXOQQC CURNCY",
    "XCCY_GBP": "BPXOQQC CURNCY",
    "XCCY_JPY": "JYBSS3M CURNCY",
    "XCCY_CAD": "CDXOQQC CURNCY",
    "XCCY_AUD": "ADBSQQC CURNCY",
    # --- XCCY basis swaps (12M) -------------------------------------------
    "XCCY12_EUR": "EUXOQQ1 CURNCY",
    "XCCY12_GBP": "BPXOQQ1 CURNCY",
    "XCCY12_JPY": "JYBSS12M CURNCY",
    "XCCY12_CAD": "CDXOQQ1 CURNCY",
    "XCCY12_AUD": "ADBSQQ1 CURNCY",
    # --- Credit ------------------------------------------------------------
    "IG_OAS":     "LUACOAS INDEX",
    "HY_OAS":     "LF98OAS INDEX",
    "EMBI":       "JPEIGLSP INDEX",
    "CDS_BOFA":   "BOFA CDS USD SR 5Y D14 CORP",
    "CDS_CITI":   "CITIB CDS USD SR 5Y D14 CORP",
    "CDS_JPM":    "JPMCC CDS USD SR 5Y D14 CORP",
    "CDS_GS":     "GS CDS USD SR 5Y D14 CORP",
    "CDS_UBS":    "UBS AG CDS EUR SR 5Y D14 CORP",
    "CDS_DB_SR":  "DB CDS EUR SR 5Y D14 CORP",
    "CDS_DB_SUB": "DB CDS EUR SUB 5Y D14 CORP",
    # --- Nominal yields (regime classification) ---------------------------
    "US_2Y":  "USGG2YR INDEX",  "US_5Y":  "USGG5YR INDEX",
    "US_10Y": "USGG10YR INDEX", "US_30Y": "USGG30YR INDEX",
    "DE_2Y":  "GDBR2 INDEX",    "DE_5Y":  "GDBR5 INDEX",
    "DE_10Y": "GDBR10 INDEX",   "DE_30Y": "GDBR30 INDEX",
    "JP_2Y":  "GJGB2 INDEX",    "JP_5Y":  "GJGB5 INDEX",
    "JP_10Y": "GJGB10 INDEX",   "JP_30Y": "GJGB30 INDEX",
    "UK_2Y":  "GUKG2 INDEX",    "UK_5Y":  "GUKG5 INDEX",
    "UK_10Y": "GUKG10 INDEX",   "UK_30Y": "GUKG30 INDEX",
    "CA_2Y":  "GCAN2YR INDEX",  "CA_5Y":  "GCAN5YR INDEX",
    "CA_10Y": "GCAN10YR INDEX", "CA_30Y": "GCAN30YR INDEX",
    "AU_2Y":  "GACGB2 INDEX",   "AU_5Y":  "GACGB5 INDEX",
    "AU_10Y": "GACGB10 INDEX",  "AU_30Y": "GACGB30 INDEX",
    # --- Inflation expectations -------------------------------------------
    "BE_2Y":  "USGGBE02 INDEX", "BE_5Y":  "USGGBE05 INDEX",
    "BE_10Y": "USGGBE10 INDEX", "BE_20Y": "USGGBE20 INDEX",
    "BE_30Y": "USGGBE30 INDEX",
    "ZCIS_1Y":  "USSWIT1 CURNCY",  "ZCIS_2Y":  "USSWIT2 CURNCY",
    "ZCIS_3Y":  "USSWIT3 CURNCY",  "ZCIS_4Y":  "USSWIT4 CURNCY",
    "ZCIS_5Y":  "USSWIT5 CURNCY",  "ZCIS_7Y":  "USSWIT7 CURNCY",
    "ZCIS_10Y": "USSWIT10 CURNCY", "ZCIS_20Y": "USSWIT20 CURNCY",
    "ZCIS_30Y": "USSWIT30 CURNCY",
    "INFL_5Y5Y": "FWISUS55 INDEX",
    # --- Money-market additions / overnight composite ---------------------
    "USRG_1T":   "USRG1T CURNCY",
    # --- Central bank / reserve liquidity ---------------------------------
    "FED_RESERVES": "FARBRBFB INDEX",   # Reserve Balances with Fed Reserve Banks (H.4.1, USD millions, weekly)
    "CENTRAL_BANK_LIQUIDITY_SWAPS": "FARWCBLS INDEX",  # Central Bank Liquidity Swaps (H.4.1, USD millions, weekly) — NOT repo/SRF
    # --- Cross-asset / FICC (merged from CROSSASSET + FICCREADING) --------
    "SPX":       "SPX INDEX",          # S&P 500
    "DXY":       "DXY CURNCY",         # Dollar index
    "BCOM":      "BCOM INDEX",         # Bloomberg commodity index
    "SPW":       "SPW INDEX",          # S&P 500 equal-weight
    "VIX":       "VIX INDEX",          # CBOE VIX
    "FXJPEMCS":  "FXJPEMCS INDEX",     # EM FX index
    "HG1":       "HG1 COMDTY",        # Copper front month
    "CL1":       "CL1 COMDTY",        # WTI crude front month
    "GC1":       "GC1 COMDTY",        # Gold front month
    "S1":        "S 1 COMDTY",        # Soybean front month
    "MOVE_IDX":  "MOVE INDEX",         # ICE BofA MOVE (rates vol)
    "USGGT10Y":  "USGGT10Y INDEX",    # US 10Y real yield (TIPS)
    # --- Financial-conditions benchmarks (NOT index components) -----------
    "FCI_BBG":  "BFCIUS INDEX",
    "FCI_NFCI": "NFCIINDX INDEX",
    # --- Credit indices (CDX / iTraxx) ------------------------------------
    "CDX_IG":       "IBOXUMAE CBBT CURNCY",
    "CDX_HY":       "IBOXHYAE CBIN CURNCY",
    "CDX_EM":       "IBOXUMSE CURNCY",
    "ITRX_EUROPE":  "ITRXEBE CBBT CURNCY",
    "ITRX_XOVER":   "ITRXEXE CBBT CURNCY",
    "ITRX_SR_FIN":  "ITRXESE CBBT CURNCY",
    "ITRX_SUB_FIN": "ITRXEUE CBBT CURNCY",
    "ITRX_JAPAN":   "ITRXAJE CBIN CURNCY",
    "ITRX_ASIA_XJ": "ITRXAGE CBBT CURNCY",
    "ITRX_AUS":     "ITRXAAE CBBT CURNCY",
    # --- Market liquidity / volatility ------------------------------------
    "UST_LIQ":  "GVLQUSD INDEX",   # Bloomberg US govt liquidity (higher = worse)
    "SWAP_10Y": "USSFCT10 CURNCY", # 10Y USD swap spread
    "MOVE":     "MOVE INDEX",      # ICE BofA MOVE — now in DATA.xlsx
    "VIX":      "VIX INDEX",       # CBOE VIX — now in DATA.xlsx
    # --- Mortgage ----------------------------------------------------------
    "MTG_30Y": "APORF30Y INDEX",
    # --- FX spot (from merged data) ----------------------------------------
    "EURUSD":  "EURUSD BGN CURNCY",
    "USDJPY":  "USDJPY BGN CURNCY",
    "GBPUSD":  "GBPUSD BGN CURNCY",
    "AUDUSD":  "AUDUSD BGN CURNCY",
    # --- Correlation targets (registered for CLI rolling corrs) ------------
    "HSI":     "HSI INDEX",           # Hang Seng — NOT YET IN DATA.xlsx
    "BTC":     "XBTUSD BGN CURNCY",   # Bitcoin — NOT YET IN DATA.xlsx
    # --- Switzerland nominal curve ------------------------------------------
    "CH_2Y":  "GSWISS02 INDEX",
    "CH_5Y":  "GSWISS05 INDEX",
    "CH_10Y": "GSWISS10 INDEX",
    "CH_30Y": "GSWISS30 INDEX",
}


# RRP candidates — NOT confirmed, do not use in production models
RRP_CANDIDATES = {
    "TOMOTCSO INDEX": {
        "status": "needs_confirmation",
        "possible_use": "possible ON RRP offering-rate related series",
        "allowed_in_production": False,
    },
    "RRPQTOON INDEX": {
        "status": "needs_confirmation",
        "possible_use": "candidate RRP-related series",
        "allowed_in_production": False,
    },
    "RRPQONAR INDEX": {
        "status": "needs_confirmation",
        "possible_use": "candidate RRP-related series",
        "allowed_in_production": False,
    },
}

# S&P 500 sector indices (available, not yet in models)
SPX_SECTOR_TICKERS = {
    "S5INFT": "S5INFT INDEX",   "S5FINL": "S5FINL INDEX",
    "S5TELS": "S5TELS INDEX",   "S5COND": "S5COND INDEX",
    "S5HLTH": "S5HLTH INDEX",   "S5INDU": "S5INDU INDEX",
    "S5CONS": "S5CONS INDEX",   "S5ENRS": "S5ENRS INDEX",
    "S5UTIL": "S5UTIL INDEX",   "S5RLST": "S5RLST INDEX",
    "S5MATR": "S5MATR INDEX",
}

# ── SPX 11-sector production configuration ──
# Single canonical mapping used throughout the sector monitor.
SPX_SECTOR_CONFIG = {
    "communication_services":  {"ticker": "S5TELS INDEX", "display_name": "Communication Services",
                                 "weight_column": "SPX_WEIGHT_COMM_SERVICES"},
    "consumer_discretionary":  {"ticker": "S5COND INDEX", "display_name": "Consumer Discretionary",
                                 "weight_column": "SPX_WEIGHT_CONSUMER_DISCRETIONARY"},
    "consumer_staples":        {"ticker": "S5CONS INDEX", "display_name": "Consumer Staples",
                                 "weight_column": "SPX_WEIGHT_CONSUMER_STAPLES"},
    "energy":                  {"ticker": "S5ENRS INDEX", "display_name": "Energy",
                                 "weight_column": "SPX_WEIGHT_ENERGY"},
    "financials":              {"ticker": "S5FINL INDEX", "display_name": "Financials",
                                 "weight_column": "SPX_WEIGHT_FINANCIALS"},
    "health_care":             {"ticker": "S5HLTH INDEX", "display_name": "Health Care",
                                 "weight_column": "SPX_WEIGHT_HEALTH_CARE"},
    "industrials":             {"ticker": "S5INDU INDEX", "display_name": "Industrials",
                                 "weight_column": "SPX_WEIGHT_INDUSTRIALS"},
    "information_technology":  {"ticker": "S5INFT INDEX", "display_name": "Information Technology",
                                 "weight_column": "SPX_WEIGHT_INFO_TECH"},
    "materials":               {"ticker": "S5MATR INDEX", "display_name": "Materials",
                                 "weight_column": "SPX_WEIGHT_MATERIALS"},
    "real_estate":             {"ticker": "S5RLST INDEX", "display_name": "Real Estate",
                                 "weight_column": "SPX_WEIGHT_REAL_ESTATE"},
    "utilities":               {"ticker": "S5UTIL INDEX", "display_name": "Utilities",
                                 "weight_column": "SPX_WEIGHT_UTILITIES"},
}

SPX_SECTOR_ETF_PROXY_METADATA = {
    "allowed_in_production": False,
    "reason": ("ETF proxies (XLC/XLY/XLP/XLE/XLV/XLI/XLB/XLRE/XLU) are excluded "
               "from the production sector model. The S5xxx sector indices are the "
               "canonical production input."),
}

# Sector ETF proxies — NOT true SPX sector indices, label as proxy only
SPX_SECTOR_ETF_PROXIES = {
    "XLC": "XLC US EQUITY",   "XLY": "XLY US EQUITY",
    "XLP": "XLP US EQUITY",   "XLE": "XLE US EQUITY",
    "XLV": "XLV US EQUITY",   "XLI": "XLI US EQUITY",
    "XLB": "XLB US EQUITY",   "XLRE": "XLRE US EQUITY",
    "XLU": "XLU US EQUITY",
}

# Policy futures — generic continuous series available in DATA.xlsx.
# These are rolling rank series, not fixed expiries.  The production generic
# strip may convert price to an implied reference rate, but it must not infer a
# meeting-by-meeting FOMC path without actual contract-month metadata.
POLICY_FUTURES_TICKERS = {
    "FF1": "FF1 COMB COMDTY",   "FF2": "FF2 COMB COMDTY",   "FF3": "FF3 COMB COMDTY",
    "SFR1": "SFR1 COMB COMDTY", "SFR2": "SFR2 COMB COMDTY", "SFR3": "SFR3 COMB COMDTY",
    "SER1": "SER1 COMB COMDTY", "SER2": "SER2 COMB COMDTY", "SER3": "SER3 COMB COMDTY",
}

POLICY_FUTURES_CONFIG = {
    "FF": {
        "display_name": "30-Day Federal Funds Futures",
        "reference_rate_label": "Monthly average daily EFFR",
        "reference_period": "Contract delivery month",
        "quote_conversion": "Implied reference rate (%) = 100 − futures price",
        "bloomberg_root": "FF Comdty",
        "source_documentation": "CME/CBOT Rulebook Chapter 22 — 30-Day Federal Funds Futures",
        "spot_reference_key": "EFFR",
        "generic_tickers": {
            1: POLICY_FUTURES_TICKERS["FF1"],
            2: POLICY_FUTURES_TICKERS["FF2"],
            3: POLICY_FUTURES_TICKERS["FF3"],
        },
    },
    "SER": {
        "display_name": "1-Month SOFR Futures",
        "reference_rate_label": "Monthly average daily SOFR",
        "reference_period": "Contract delivery month",
        "quote_conversion": "Implied reference rate (%) = 100 − futures price",
        "bloomberg_root": "SER Comdty",
        "source_documentation": "CME Group — Understanding SOFR Futures / vendor-code table",
        "spot_reference_key": "SOFR",
        "generic_tickers": {
            1: POLICY_FUTURES_TICKERS["SER1"],
            2: POLICY_FUTURES_TICKERS["SER2"],
            3: POLICY_FUTURES_TICKERS["SER3"],
        },
    },
    "SFR": {
        "display_name": "3-Month SOFR Futures",
        "reference_rate_label": "Compounded SOFR reference-quarter rate",
        "reference_period": "Three-month reference quarter",
        "quote_conversion": "Implied reference rate (%) = 100 − futures price",
        "bloomberg_root": "SFR Comdty",
        "source_documentation": "CME Group — Three-Month SOFR Futures Rates and Future SOFR Levels",
        "spot_reference_key": "SOFR",
        "generic_tickers": {
            1: POLICY_FUTURES_TICKERS["SFR1"],
            2: POLICY_FUTURES_TICKERS["SFR2"],
            3: POLICY_FUTURES_TICKERS["SFR3"],
        },
    },
}

# Countries with full 2/5/10/30 nominal coverage for regime classification
REGIME_COUNTRIES = ("US", "DE", "JP", "UK", "CA", "AU", "CH")

# Tenor configuration for real-rate / inflation curve plots
REAL_RATE_TENORS = {
    "US": [("5Y", 5, "US_real_5y"), ("10Y", 10, "US_real_10y"), ("30Y", 30, "US_real_30y")],
    "UK": [("5Y", 5, "UK_real_5y"), ("10Y", 10, "UK_real_10y"), ("30Y", 30, "UK_real_30y")],
    "DE": [("7Y", 7, "DE_real_7y"), ("10Y", 10, "DE_real_10y"), ("25Y", 25, "DE_real_25y")],
    "JP": [("5Y", 5, "JP_real_5y"), ("7Y", 7, "JP_real_7y"), ("10Y", 10, "JP_real_10y")],
    "AU": [("5Y", 5, "AU_real_5y"), ("10Y", 10, "AU_real_10y")],
    "CA": [("5Y", 5, "CA_real_5y"), ("10Y", 10, "CA_real_10y"), ("30Y", 30, "CA_real_30y")],
}

INFL_BE_TENORS = [
    ("2Y", 2, "BE_2Y"), ("5Y", 5, "BE_5Y"), ("10Y", 10, "BE_10Y"),
    ("20Y", 20, "BE_20Y"), ("30Y", 30, "BE_30Y"),
]
INFL_ZCIS_TENORS = [
    ("1Y", 1, "ZCIS_1Y"), ("2Y", 2, "ZCIS_2Y"), ("3Y", 3, "ZCIS_3Y"),
    ("4Y", 4, "ZCIS_4Y"), ("5Y", 5, "ZCIS_5Y"), ("7Y", 7, "ZCIS_7Y"),
    ("10Y", 10, "ZCIS_10Y"), ("20Y", 20, "ZCIS_20Y"), ("30Y", 30, "ZCIS_30Y"),
]

# Tenor pairs for slope/regime mode
TENOR_PAIRS = {
    "2s5s":   ("2Y", "5Y"),
    "2s10s":  ("2Y", "10Y"),
    "2s30s":  ("2Y", "30Y"),
    "5s10s":  ("5Y", "10Y"),
    "5s30s":  ("5Y", "30Y"),
    "10s30s": ("10Y", "30Y"),
}

# Credit-index explorer options: label -> (key, unit)
CREDIT_INDICES = {
    "CDX NA IG (price)":         ("CDX_IG",       "price"),
    "CDX NA HY (price)":         ("CDX_HY",       "price"),
    "CDX EM (spread, bp)":       ("CDX_EM",       "spread"),
    "iTraxx Europe Main (bp)":   ("ITRX_EUROPE",  "spread"),
    "iTraxx Crossover (bp)":     ("ITRX_XOVER",   "spread"),
    "iTraxx Sr Financial (bp)":  ("ITRX_SR_FIN",  "spread"),
    "iTraxx Sub Financial (bp)": ("ITRX_SUB_FIN", "spread"),
    "iTraxx Japan (bp)":         ("ITRX_JAPAN",   "spread"),
    "iTraxx Asia ex-Japan (bp)": ("ITRX_ASIA_XJ", "spread"),
    "iTraxx Australia (bp)":     ("ITRX_AUS",     "spread"),
}

# ── Ticker confirmation metadata ──
# Fields whose Bloomberg descriptions / units are NOT yet documented.
# These must NOT appear in production charts until confirmed.
TICKER_METADATA = {
    "GCF": {
        "ticker": "UREPGATO INDEX",
        "display_name": "GCF Repo Average Rate",
        "description_status": "confirmed",
        "allowed_in_production": True,
        "source_documentation": "Bloomberg DES / OFR Short-Term Funding Monitor",
        "unit": "percent",
        "frequency": "daily",
    },
    "TPR": {
        "ticker": "UREPTATO INDEX",
        "display_name": "Tri-Party Repo Average Rate",
        "description_status": "confirmed",
        "allowed_in_production": True,
        "source_documentation": "Bloomberg DES / OFR Short-Term Funding Monitor",
        "unit": "percent",
        "frequency": "daily",
    },
    "FED_RESERVES": {
        "ticker": "FARBRBFB INDEX",
        "display_name": "Reserve Balances with Federal Reserve Banks",
        "description_status": "confirmed",
        "allowed_in_production": True,
        "source_documentation": "Bloomberg DES / Federal Reserve H.4.1",
        "unit": "USD millions",
        "frequency": "weekly",
    },
    "CENTRAL_BANK_LIQUIDITY_SWAPS": {
        "ticker": "FARWCBLS INDEX",
        "display_name": "Central Bank Liquidity Swaps",
        "description_status": "confirmed",
        "allowed_in_production": True,
        "source_documentation": "Bloomberg DES / Federal Reserve H.4.1",
        "unit": "USD millions",
        "frequency": "weekly",
    },
}
