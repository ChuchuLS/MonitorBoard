"""
models/scoring/engine.py
=======================
Global Rates & Equity cross-sectional scoring model.

Extracted from the Pulsar/CTA Dashboard. Pure math — no Streamlit.
Scores 10 sovereign bond markets and 18 requested equity indices on macro + market
factors, producing a cross-sectional z-score ranking.
"""

from datetime import date, datetime
from pathlib import Path
import numpy as np
import pandas as pd

# UNIVERSES & MAPPINGS
# ============================================================

# Rates dashboard: 10 sovereign bond markets
RATES_UNIVERSE = [
    ("FR", "France"),
    ("JP", "Japan"),
    ("GB", "UK"),
    ("ES", "Spain"),
    ("IT", "Italy"),
    ("US", "United States"),
    ("CA", "Canada"),
    ("KR", "S. Korea"),
    ("AU", "Australia"),
    ("DE", "Germany"),
]
RATES_CODES = [c for c, _ in RATES_UNIVERSE]

# Equity dashboard: 18 requested indices. SMI and AEX were removed by user
# request. FTSE China A50 is not relabelled; the China row now uses the
# independently supplied CSI A500 series. Nifty 50 and VN30 use their own
# confirmed DATA.xlsx price, EPS and country-macro inputs; no FCI proxy is used.
EQUITY_UNIVERSE = [
    ("PT1",  "S&P/TSX",        "Canada"),
    ("NQ1",  "Nasdaq 100",     "USA"),
    ("KM1",  "KOSPI",          "S. Korea"),
    ("XP1",  "ASX",            "Australia"),
    ("HI1",  "Hang Seng",      "Hong Kong"),
    ("CSI_A500", "CSI A500",   "China"),
    ("NIFTY50", "Nifty 50",    "India"),
    ("VN30",  "VN30",           "Vietnam"),
    ("ES1",  "S&P 500",        "USA"),
    ("DJI",  "Dow Jones Industrial Average", "USA"),
    ("RTY1", "Russell 2000",   "USA"),
    ("Z 1",  "FTSE 100",       "UK"),
    ("CF1",  "CAC 40",         "France"),
    ("ST1",  "FTSE MIB",       "Italy"),
    ("NK1",  "Nikkei 225",     "Japan"),
    ("VG1",  "Euro Stoxx 50",  "Eurozone"),
    ("IB1",  "IBEX 35",        "Spain"),
    ("GX1",  "DAX",            "Germany"),
]
EQUITY_CODES = [c for c, _, _ in EQUITY_UNIVERSE]
EQUITY_META = {c: (n, r) for c, n, r in EQUITY_UNIVERSE}

# Each equity index → its macro country (for GDP/CPI/Fiscal lookup)
INDEX_TO_COUNTRY = {
    "PT1": "CA", "NQ1": "US", "KM1": "KR", "XP1": "AU",
    "HI1": "HK", "CSI_A500": "CN", "NIFTY50": "IN", "VN30": "VN",
    "ES1": "US", "DJI": "US", "RTY1": "US", "Z 1": "GB", "CF1": "FR",
    "ST1": "IT", "NK1": "JP", "VG1": "EZ", "IB1": "ES", "GX1": "DE",
}

# FCI is retained as a separate context panel only. These are the four exact
# series supplied in DATA.xlsx / Equity_FCI. They are deliberately not mapped
# onto individual equity indices and do not enter the Equity Score or ranking.
FCI_CONTEXT_META = {
    "NQ1": {"region": "USA", "ticker": "BFCIUS Index"},
    "XU1": {"region": "China", "ticker": "CHBGFCI INDEX"},
    "Z 1": {"region": "UK", "ticker": "BFCIGB INDEX"},
    "VG1": {"region": "Eurozone", "ticker": "BFCIEU INDEX"},
}

# Each equity index → its Citi ToT currency ticker
INDEX_TO_TOT_TICKER = {
    "PT1": "CTOTCAD Index", "NQ1": "CTOTUSD Index", "KM1": "CTOTKRW Index",
    "XP1": "CTOTAUD Index", "HI1": "CTOTHKD Index", "CSI_A500": "CTOTCNY Index",
    "NIFTY50": "CTOTINR Index", "VN30": "CTOTVND Index",
    "ES1": "CTOTUSD Index", "DJI": "CTOTUSD Index", "RTY1": "CTOTUSD Index",
    "Z 1": "CTOTGBP Index", "CF1": "CTOTEUR Index",
    "ST1": "CTOTEUR Index", "NK1": "CTOTJPY Index", "VG1": "CTOTEUR Index",
    "IB1": "CTOTEUR Index", "GX1": "CTOTEUR Index",
}

# Each rates country → its Citi ToT currency
RATES_TO_TOT_TICKER = {
    "FR": "CTOTEUR Index", "JP": "CTOTJPY Index", "GB": "CTOTGBP Index",
    "ES": "CTOTEUR Index", "IT": "CTOTEUR Index", "US": "CTOTUSD Index",
    "CA": "CTOTCAD Index", "KR": "CTOTKRW Index", "AU": "CTOTAUD Index",
    "DE": "CTOTEUR Index",
}


# ============================================================
# LOADER
# ============================================================
_MACRO_TICKER_CODE_ALIASES = {
    "VEGDQYOYINDEX": "VN",
    "IGQREGDYINDEX": "IN",
    "VNCPIYOYINDEX": "VN",
    "INFUTOTYINDEX": "IN",
    "EHBBINYINDEX": "IN",
    "EHBBVNINDEX": "VN",
}


def _normalise_token(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def _parse_country_macro_sheet(xlsx_path: str, sheet_name: str) -> pd.DataFrame:
    """Parse country macro panels, including confirmed blank-header additions.

    Most columns use the shared Date column in A. DATA(7) supplies Vietnam
    fiscal data as an independent Date/value spill; that source calendar is
    preserved rather than aligned by row position. Ticker aliases are limited
    to the exact India/Vietnam rows present in the workbook.
    """
    try:
        raw = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None)
    except Exception:
        return pd.DataFrame()
    if raw.empty or raw.shape[0] < 6 or raw.shape[1] < 2:
        return pd.DataFrame()

    shared_dates = pd.to_datetime(raw.iloc[5:, 0], errors="coerce")
    series = {}
    for value_col in range(1, raw.shape[1]):
        ticker = raw.iloc[4, value_col] if raw.shape[0] > 4 else None
        alias = _MACRO_TICKER_CODE_ALIASES.get(_normalise_token(ticker))
        raw_code = raw.iloc[3, value_col] if raw.shape[0] > 3 else None
        code = alias or ("" if raw_code is None or pd.isna(raw_code) else str(raw_code).strip())
        if not code or code.lower().startswith("unnamed") or code == "Date":
            continue

        dates = shared_dates
        if value_col > 1:
            prior = raw.iloc[5:, value_col - 1]
            true_date_count = sum(
                isinstance(value, (date, datetime, pd.Timestamp, np.datetime64))
                for value in prior
                if value is not None and not pd.isna(value)
            )
            prior_ticker = raw.iloc[4, value_col - 1] if raw.shape[0] > 4 else None
            if true_date_count >= 2 and (prior_ticker is None or pd.isna(prior_ticker)):
                dates = pd.to_datetime(prior, errors="coerce")

        values = pd.to_numeric(raw.iloc[5:, value_col], errors="coerce")
        s = pd.Series(values.to_numpy(), index=dates, name=code)
        s = s[~s.index.isna()].dropna().sort_index()
        s = s[~s.index.duplicated(keep="last")]
        if not s.empty:
            series[code] = s
    return pd.concat(series, axis=1).sort_index() if series else pd.DataFrame()


def _read_sheet_pandas(xlsx_path: str, sheet_name: str, header_row: int = 4) -> pd.DataFrame:
    """Read a BDH-style scoring sheet using pandas (much faster than openpyxl).
    header_row is 0-indexed for pandas (row 4 in Excel = header=3 in pandas).
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Could not infer format")
            df = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=header_row - 1)
    except Exception:
        return pd.DataFrame()

    if df.empty or df.shape[1] < 2:
        return pd.DataFrame()

    # First column is dates
    date_col = df.columns[0]
    import warnings as _w
    with _w.catch_warnings():
        _w.filterwarnings("ignore", message="Could not infer format")
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])

    # Drop any column literally named "Date" (BDH interleaved date columns)
    data_cols = [c for c in df.columns[1:] if str(c).strip() != "Date" and not str(c).startswith("Unnamed")]
    df = df[[date_col] + data_cols]

    # Rename columns to stripped strings
    df.columns = ["date"] + [str(c).strip() for c in data_cols]
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]

    # Convert to numeric
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    return df


def read_sheet(xlsx_path: str, sheet_name: str, header_row: int = 4) -> pd.DataFrame:
    """Backward-compatible wrapper."""
    return _read_sheet_pandas(xlsx_path, sheet_name, header_row)


def load_all(xlsx_path: str) -> dict:
    """Load all 8 scoring sheets."""
    sheets = {
        "gdp": "Macro_GDP", "cpi": "Macro_CPI",
        "fiscal": "Macro_Fiscal", "y10y": "Rates_10Y",
        "tot": "Equity_ToT", "fci": "Equity_FCI",
        "eps": "Equity_EPS", "px": "Equity_Prices",
    }
    result = {}
    for key, name in sheets.items():
        result[key] = (
            _parse_country_macro_sheet(xlsx_path, name)
            if key in {"gdp", "cpi", "fiscal"}
            else _read_sheet_pandas(xlsx_path, name)
        )
    # Equity_EPS contains independent Date/value spills and the newly supplied
    # A500 / DJI / Nifty 50 / VN30 blocks have blank short-code headers. Reuse
    # the production parser so those exact ticker-identified rows enter Scoring
    # without relabelling another market or aligning EPS dates by row position.
    try:
        from data.equity_earnings_loader import _parse_eps_sheet, _parse_price_sheet
        eps, _ = _parse_eps_sheet(Path(xlsx_path))
        prices, _ = _parse_price_sheet(Path(xlsx_path))
        if not eps.empty:
            result["eps"] = eps
        if not prices.empty:
            result["px"] = prices
    except Exception:
        # Keep the generic sheet reads. Missing requested tickers remain NaN and
        # are surfaced as incomplete rather than substituted.
        pass
    return result


# ============================================================
# FACTOR MATH HELPERS
# ============================================================
def latest(df: pd.DataFrame, asof: pd.Timestamp) -> pd.Series:
    """Latest available value per column on or before asof."""
    sub = df.loc[:asof].ffill()
    if len(sub) == 0:
        return pd.Series(dtype=float)
    return sub.iloc[-1]


def value_n_days_ago(df: pd.DataFrame, asof: pd.Timestamp, days: int) -> pd.Series:
    sub = df.loc[:asof].ffill()
    if len(sub) == 0:
        return pd.Series(dtype=float)
    target = asof - pd.Timedelta(days=days)
    if len(sub.loc[:target]) > 0:
        return sub.loc[:target].iloc[-1]
    return sub.iloc[0]


def pct_change(df: pd.DataFrame, asof: pd.Timestamp, days: int) -> pd.Series:
    last = latest(df, asof)
    base = value_n_days_ago(df, asof, days)
    return (last / base - 1) * 100


def build_equity_fci_context(data: dict, asof: pd.Timestamp) -> pd.DataFrame:
    """Return the supplied regional FCI series as non-scoring context.

    Each series keeps its own latest observation date on or before ``asof``.
    No country/index mapping, proxy, fill across series, z-score or ranking is
    applied.
    """
    frame = (data or {}).get("fci")
    rows = []
    for code, meta in FCI_CONTEXT_META.items():
        series = pd.Series(dtype=float)
        if frame is not None and not frame.empty and code in frame.columns:
            series = pd.to_numeric(frame.loc[:asof, code], errors="coerce").dropna()
        rows.append({
            "region": meta["region"],
            "ticker": meta["ticker"],
            "latest_value": float(series.iloc[-1]) if not series.empty else np.nan,
            "source_date": series.index[-1].date() if not series.empty else None,
            "status": "Available" if not series.empty else "Missing data",
        })
    return pd.DataFrame(rows)


def diff_n_days(df: pd.DataFrame, asof: pd.Timestamp, days: int) -> pd.Series:
    """Absolute (not %) change over n days. For yields, ToT etc."""
    last = latest(df, asof)
    base = value_n_days_ago(df, asof, days)
    return last - base


def realized_vol(df: pd.DataFrame, asof: pd.Timestamp, window: int = 30) -> pd.Series:
    """Annualized rolling std of daily log returns."""
    sub = df.loc[:asof].ffill()
    if len(sub) < 2:
        return pd.Series(index=df.columns, dtype=float)
    rets = np.log(sub).diff()
    tail = rets.tail(window)
    return tail.std() * np.sqrt(252) * 100


def zscore(series: pd.Series, codes: list, sign: int = 1) -> pd.Series:
    """Cross-sectional z-score over the given universe; sign flips direction."""
    s = series.reindex(codes).astype(float)
    mu = s.mean(skipna=True)
    sd = s.std(ddof=0, skipna=True)
    if sd == 0 or np.isnan(sd):
        return s * 0
    return sign * (s - mu) / sd


# ============================================================
# RATES SCORING
# ============================================================
def score_rates(data: dict, asof: pd.Timestamp, weights: dict) -> pd.DataFrame:
    """
    Replicate the Pulsar Rates dashboard:
    Macro pillar = mean(GDP_z, CPI_z (inverted), Budget_z)
    Markets pillar = mean(Momentum_z, Carry_z, RealYield_z)
    Score = mean(Macro, Markets)
    """
    gdp_v    = latest(data["gdp"],    asof)
    cpi_v    = latest(data["cpi"],    asof)
    fiscal_v = latest(data["fiscal"], asof)
    y10y_v   = latest(data["y10y"],   asof)
    y10y_3m  = value_n_days_ago(data["y10y"], asof, 90)

    # Build factor frames per country (only rates universe)
    z_gdp    = zscore(gdp_v,    RATES_CODES, +1)   # higher GDP = good for govt
    z_cpi    = zscore(cpi_v,    RATES_CODES, -1)   # lower inflation = good for bonds
    z_budget = zscore(fiscal_v, RATES_CODES, +1)   # less deficit (less negative) = good
    macro    = pd.concat([z_gdp, z_cpi, z_budget], axis=1).mean(axis=1)

    # 3M yield change: bonds rally when yields FALL → lower change = positive
    z_mom    = zscore(y10y_v - y10y_3m, RATES_CODES, -1)
    z_carry  = zscore(y10y_v,            RATES_CODES, +1)   # higher carry = good
    # Real yield = nominal − CPI
    real_y   = y10y_v - cpi_v
    z_realy  = zscore(real_y,            RATES_CODES, +1)
    markets  = pd.concat([z_mom, z_carry, z_realy], axis=1).mean(axis=1)

    # Weighted composite
    wsum = sum(weights.values())
    wn = {k: v / wsum for k, v in weights.items()}
    score = macro * wn["macro"] + markets * wn["markets"]

    out = pd.DataFrame({
        "gdp_z":    z_gdp,
        "cpi_z":    z_cpi,
        "budget_z": z_budget,
        "macro":    macro,
        "mom_z":    z_mom,
        "carry_z":  z_carry,
        "realy_z":  z_realy,
        "markets":  markets,
        "score":    score,
    }).round(2)
    out.index.name = "code"
    out["country"] = [dict(RATES_UNIVERSE)[c] for c in out.index]
    out["incomplete"] = pd.concat([macro, markets], axis=1).isna().any(axis=1)
    return out.sort_values("score", ascending=False, na_position="last")


# ============================================================
# EQUITY SCORING
# ============================================================
def score_equity(data: dict, asof: pd.Timestamp, weights: dict) -> pd.DataFrame:
    """
    Pulsar Equity dashboard:
    Macro pillar = mean(Growth_z, Inflation_z (inv), Deficit_z, ToT_z)
    Then composite score = weighted blend of macro + EPS revisions.
    FCI is a separate context series and never enters this calculation.
    Plus performance and vol columns.
    """
    gdp_v    = latest(data["gdp"],    asof)
    cpi_v    = latest(data["cpi"],    asof)
    fiscal_v = latest(data["fiscal"], asof)
    tot_v    = latest(data["tot"],    asof)
    tot_3m   = value_n_days_ago(data["tot"], asof, 90)

    # Map each index to its country macro values
    def by_index(country_series: pd.Series) -> pd.Series:
        out = {}
        for code in EQUITY_CODES:
            country = INDEX_TO_COUNTRY[code]
            out[code] = country_series.get(country, np.nan)
        return pd.Series(out)

    growth     = by_index(gdp_v)
    inflation  = by_index(cpi_v)
    deficit    = by_index(fiscal_v)

    # ToT: 3M change in the index's currency ToT
    def tot_for_index(asof_series, three_m_series):
        out_now, out_then = {}, {}
        for code in EQUITY_CODES:
            t = INDEX_TO_TOT_TICKER.get(code)
            out_now[code]  = asof_series.get(t, np.nan)
            out_then[code] = three_m_series.get(t, np.nan)
        return pd.Series(out_now), pd.Series(out_then)
    tot_now, tot_then = tot_for_index(tot_v, tot_3m)
    tot_mom = tot_now - tot_then  # absolute change in ToT index

    # EPS Δ: 3M % change in FY1 EPS estimate
    eps_v   = latest(data["eps"], asof)
    eps_3m  = value_n_days_ago(data["eps"], asof, 90)
    eps_chg = (eps_v / eps_3m - 1) * 100
    # Align to equity universe (eps frame columns are already index codes)
    eps_delta = eps_chg.reindex(EQUITY_CODES)

    # Z-scores on equity universe
    z_growth = zscore(growth,    EQUITY_CODES, +1)
    z_infl   = zscore(inflation, EQUITY_CODES, -1)
    z_def    = zscore(deficit,   EQUITY_CODES, +1)
    z_tot    = zscore(tot_mom,   EQUITY_CODES, +1)

    macro_factors = pd.DataFrame({
        "GDP": z_growth,
        "CPI": z_infl,
        "Fiscal": z_def,
        "ToT": z_tot,
    })
    macro_factor_count = macro_factors.notna().sum(axis=1)
    macro = macro_factors.mean(axis=1)

    # EPS as separate factor (z-scored across the panel)
    z_eps = zscore(eps_delta, EQUITY_CODES, +1)

    # Weighted composite
    wsum = sum(weights.values())
    wn = {k: v / wsum for k, v in weights.items()}
    score = macro * wn["macro"] + z_eps * wn["eps"]

    # Performance and vol (cosmetic columns)
    p5d = pct_change(data["px"], asof, 7).reindex(EQUITY_CODES)
    p1m = pct_change(data["px"], asof, 30).reindex(EQUITY_CODES)
    p3m = pct_change(data["px"], asof, 90).reindex(EQUITY_CODES)
    vol = realized_vol(data["px"], asof, 30).reindex(EQUITY_CODES)

    out = pd.DataFrame({
        "growth_z": z_growth,
        "infl_z":   z_infl,
        "def_z":    z_def,
        "tot_z":    z_tot,
        "macro_factor_count": macro_factor_count,
        "macro":    macro,
        "eps_delta": eps_delta,
        "score":    score,
        "p5d": p5d,
        "p1m": p1m,
        "p3m": p3m,
        "vol": vol,
    }).round(2)
    out.index.name = "code"
    out["name"]   = [EQUITY_META[c][0] for c in out.index]
    out["region"] = [EQUITY_META[c][1] for c in out.index]
    required_factors = macro_factors.assign(EPS=z_eps)
    out["missing_factors"] = [
        ", ".join(required_factors.columns[required_factors.loc[code].isna()].tolist())
        for code in out.index
    ]
    out["status"] = np.where(
        out["score"].isna(),
        "Missing data",
        np.where((macro_factor_count == len(macro_factors.columns)) & z_eps.notna(),
                 "Ready", "Partial"),
    )
    out["rank_eligible"] = out["status"].eq("Ready")
    out["incomplete"] = ~out["rank_eligible"]
    status_order = out["status"].map({"Ready": 0, "Partial": 1, "Missing data": 2})
    out = out.assign(_status_order=status_order)
    return out.sort_values(
        ["_status_order", "score"], ascending=[True, False], na_position="last"
    ).drop(columns="_status_order")


# ============================================================
# RENDERING (Pulsar HTML style)
# ============================================================


def determine_scoring_asof(data: dict, current_date=None) -> dict:
    """Determine the production scoring as-of date.
    Excludes future-dated rows from the production date.
    Returns {asof_date, future_rows: [{sheet, date, ...}]}."""
    from data.date_integrity import current_production_date
    cd = current_production_date(current_date)

    future_rows = []
    latest_eligible = None

    for key, df in (data or {}).items():
        if df is None or df.empty:
            continue
        for d in df.index:
            dd = d.date() if hasattr(d, 'date') else d
            if dd > cd:
                future_rows.append({
                    "sheet": key, "date": str(dd),
                    "cols_with_data": int(df.loc[d].notna().sum()),
                    "status": "Needs classification",
                })
            else:
                if latest_eligible is None or dd > latest_eligible:
                    latest_eligible = dd

    return {
        "asof_date": latest_eligible,
        "future_rows": future_rows,
        "current_date": cd,
    }
