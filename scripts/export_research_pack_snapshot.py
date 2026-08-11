#!/usr/bin/env python3
"""
scripts/export_research_pack_snapshot.py
========================================
Export a JSON snapshot of today's research-pack state. This will later become
the input for a PDF / HTML report generator.

Usage:
    python scripts/export_research_pack_snapshot.py

Outputs:
    data/snapshot.json

No Streamlit or heavy dependencies required.
"""
import sys, os, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.loader import load_data, latest_valid_date, source_signature
from index.composite import compute_index
from config.pages import PAGES, STATUS_LABELS


def build_snapshot() -> dict:
    df = load_data()
    lvd = latest_valid_date(df)
    r = compute_index(df)
    changes = r.changes() if callable(getattr(r, "changes", None)) else {}

    snap = {
        "latest_valid_date": str(lvd.date()) if lvd else None,
        "data_hash": source_signature()[:16],
        "index": {
            "level": round(float(r.latest), 2) if not __import__("math").isnan(r.latest) else None,
            "regime": r.latest_regime,
            "changes": {k: round(float(v), 2) for k, v in changes.items()
                        if not __import__("math").isnan(v)},
        },
        "pages": [],
    }

    # Page statuses
    for p in PAGES:
        snap["pages"].append({
            "section": p["section"], "id": p["id"],
            "title": p["title"], "status": STATUS_LABELS[p["status"]],
        })

    # Fixed-contract SOFR Futures Strip & Calendar Spreads
    try:
        from data.policy_futures_loader import load_policy_futures
        from models.policy_futures_strip import build_sofr_strip_snapshot
        ps = build_sofr_strip_snapshot(load_policy_futures(), df)
        table = ps.get("strip_table")
        matrix = ps.get("calendar_spread_matrix")
        snap["sofr_futures_strip"] = {
            "status": ps.get("status"),
            "model_date": str(ps.get("model_date")) if ps.get("model_date") else None,
            "aligned_observations": ps.get("aligned_observations"),
            "effr_pct": ps.get("effr_pct"),
            "sofr_pct": ps.get("sofr_pct"),
            "terminal": ps.get("terminal"),
            "terminal_spreads": ps.get("terminal_spreads"),
            "fixed_contract_strip": (
                table[["sequence", "ticker", "contract_label", "price", "implied_rate_pct",
                       "change_1d_bp", "change_5d_bp", "change_20d_bp"]].to_dict(orient="records")
                if hasattr(table, "empty") and not table.empty else []
            ),
            "calendar_spread_matrix": (
                matrix.to_dict(orient="records")
                if hasattr(matrix, "empty") and not matrix.empty else []
            ),
            "fixed_contract_months": True,
            "fomc_meeting_path": False,
        }
    except Exception:
        pass

    # Rate Decomposition
    try:
        from models.rate_decomposition import build_us_curve_snapshot
        cs = build_us_curve_snapshot(df)
        if not cs.empty:
            snap["rate_decomposition"] = cs.to_dict(orient="records")
    except Exception:
        pass

    # Curve Regimes
    try:
        from models.curve_regimes import build_regime_matrix
        m = build_regime_matrix(df)
        if not m.empty:
            snap["curve_regime_matrix"] = m.to_dict()
    except Exception:
        pass

    # Global Rates
    try:
        from models.global_rates import build_slope_ranking, country_1m_changes
        slopes = build_slope_ranking(df)
        if not slopes.empty:
            snap["slope_ranking"] = slopes.to_dict(orient="records")
        chg = country_1m_changes(df)
        if not chg.empty:
            snap["country_1m_changes"] = chg.to_dict(orient="records")
    except Exception:
        pass

    # Country Rate Boards — one shared comparison calendar across all seven countries
    try:
        from models.country_rate_boards import build_global_country_board_overview
        boards = build_global_country_board_overview(df, horizon=20)
        if not boards.empty:
            board_records = []
            for _, row in boards.iterrows():
                board_records.append({
                    "country": str(row["country"]),
                    "label": str(row["label"]),
                    "model_date": str(row["model_date"]),
                    "aligned_observations": int(row["aligned_observations"]),
                    "yield_2y_pct": float(row["yield_2y_pct"]),
                    "yield_10y_pct": float(row["yield_10y_pct"]),
                    "yield_30y_pct": float(row["yield_30y_pct"]),
                    "change_20d_2y_bp": float(row["change_20d_2y_bp"]),
                    "change_20d_10y_bp": float(row["change_20d_10y_bp"]),
                    "slope_2s10s_bp": float(row["slope_2s10s_bp"]),
                    "change_20d_2s10s_bp": float(row["change_20d_2s10s_bp"]),
                    "inverted": bool(row["inverted"]),
                    "status": str(row["status"]),
                })
            snap["country_rate_boards"] = {
                "common_model_date": str(boards["model_date"].iloc[0]),
                "aligned_observations": int(boards["aligned_observations"].iloc[0]),
                "horizon": 20,
                "countries": board_records,
            }
    except Exception:
        pass

    # Cross-Asset
    try:
        from data.external_loaders import load_crossasset
        from models.cross_asset.directional import classify_8regime, REGIMES_8, days_in_current_regime
        ca = load_crossasset()
        if ca is not None:
            res = classify_8regime(ca)
            if not res.empty:
                cur = res["regime"].iloc[-1]
                snap["cross_asset"] = {
                    "regime": cur,
                    "label": REGIMES_8[cur]["label"],
                    "days_in": days_in_current_regime(res["regime"]),
                    "latest": str(res.index.max().date()),
                }
    except Exception:
        pass

    # Five-asset Market Linkage & Correlations
    try:
        from data.external_loaders import load_ficc as _load_linkage_ficc
        from models.market_linkage import build_market_linkage_current_reading
        _ml_frame = _load_linkage_ficc()
        _ml = build_market_linkage_current_reading(_ml_frame, corr_window=20) if _ml_frame is not None else {}
        snap["market_linkage"] = {
            "status": _ml.get("status"),
            "model_date": str(_ml.get("model_date")) if _ml.get("model_date") else None,
            "correlation_window": 20,
            "mean_abs_correlation": _ml.get("mean_abs_correlation"),
            "strongest_positive": _ml.get("strongest_positive"),
            "strongest_negative": _ml.get("strongest_negative"),
            "causal_attribution": False,
            "forecast_model": False,
        }
    except Exception:
        pass

    # Sector contribution estimate (20 common observations)
    try:
        from data.external_loaders import load_spx_sector_weights
        from models.sector_contribution import build_sector_contribution_current_reading
        sc = build_sector_contribution_current_reading(
            df, load_spx_sector_weights(), horizon=20
        )
        snap["sector_contribution_estimate"] = {
            "status": sc.get("status"),
            "horizon": sc.get("horizon"),
            "start_date": str(sc.get("start_date")) if sc.get("start_date") else None,
            "end_date": str(sc.get("end_date")) if sc.get("end_date") else None,
            "weight_date": str(sc.get("weight_date")) if sc.get("weight_date") else None,
            "actual_spx_return_pct": sc.get("actual_spx_return_pct"),
            "estimated_spx_return_pct": sc.get("estimated_spx_return_pct"),
            "residual_pp": sc.get("residual_pp"),
            "top_positive": [
                {"sector": row["display_name"],
                 "estimated_contribution_pp": row["estimated_contribution_pp"]}
                for row in sc.get("top_positive", [])
            ],
            "top_negative": [
                {"sector": row["display_name"],
                 "estimated_contribution_pp": row["estimated_contribution_pp"]}
                for row in sc.get("top_negative", [])
            ],
            "official_attribution": False,
        }
    except Exception:
        pass

    # SPX FY1 Earnings & Valuation — exact weekly identity decomposition
    try:
        from data.equity_earnings_loader import load_equity_earnings_data
        from models.earnings_valuation import (
            build_earnings_current_reading, build_global_earnings_overview,
        )
        _earnings_data = load_equity_earnings_data()
        ev = build_earnings_current_reading(_earnings_data, code="ES1")
        snap["spx_earnings_valuation"] = {
            "status": ev.get("status"),
            "model_date": str(ev.get("model_date")) if ev.get("model_date") else None,
            "aligned_observations": ev.get("aligned_observations"),
            "eps_field": "BEST_EPS",
            "forecast_period_override": "1FY",
            "frequency": "weekly",
            "spx_level": ev.get("price"),
            "fy1_eps": ev.get("eps_fy1"),
            "implied_fy1_pe": ev.get("fy1_pe"),
            "decomposition_horizon_weeks": ev.get("decomposition_horizon"),
            "spx_return_pct": ev.get("current_price_return_pct"),
            "fy1_eps_growth_pct": ev.get("current_eps_growth_pct"),
            "valuation_change_pct": ev.get("current_valuation_change_pct"),
            "identity_residual_pct": ev.get("current_identity_residual_pct"),
            "larger_component": ev.get("current_driver"),
            "weekly_ols_beta": ev.get("regression_beta"),
            "weekly_ols_r_squared": ev.get("regression_r_squared"),
            "fair_value_model": False,
            "forecast_model": False,
        }
        requested = build_global_earnings_overview(_earnings_data, horizon=13)
        requested = requested.loc[requested["code"].isin(["CSI_A500", "DJI"])]
        snap["requested_equity_earnings_rows"] = [
            {
                "code": row["code"],
                "index": row["index"],
                "workbook_ticker": row.get("workbook_ticker"),
                "status": row["status"],
                "model_date": str(row["model_date"]) if row["model_date"] else None,
                "index_level": row["price"],
                "fy1_eps": row["eps_fy1"],
                "implied_fy1_pe": row["fy1_pe"],
                "price_return_13w_pct": row["price_return_13w_pct"],
                "eps_growth_13w_pct": row["eps_growth_13w_pct"],
                "valuation_change_13w_pct": row["valuation_change_13w_pct"],
            }
            for _, row in requested.iterrows()
        ]
    except Exception:
        pass

    try:
        from models.sector_rotation import build_spx_dispersion_index
        dspx = build_spx_dispersion_index(df)
        snap["cboe_dspx"] = {
            "status": "Ready" if len(dspx) else "Missing data",
            "ticker": "DSPX INDEX",
            "model_date": str(dspx.index[-1].date()) if len(dspx) else None,
            "latest_value": float(dspx.iloc[-1]) if len(dspx) else None,
            "synthetic_substitution": False,
        }
    except Exception:
        pass

    return snap


if __name__ == "__main__":
    snapshot = build_snapshot()
    out_path = Path("data/snapshot.json")
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    print(f"Wrote {out_path}")
    print(json.dumps(snapshot, indent=2, default=str)[:2000])
