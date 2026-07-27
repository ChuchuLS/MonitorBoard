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

    return snap


if __name__ == "__main__":
    snapshot = build_snapshot()
    out_path = Path("data/snapshot.json")
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2, default=str)
    print(f"Wrote {out_path}")
    print(json.dumps(snapshot, indent=2, default=str)[:2000])
