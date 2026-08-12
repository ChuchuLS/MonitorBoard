"""
models/qlist.py
===============
Q-list answering engine. Generates structured answers to the 14 standard
questions using real model outputs. No fabrication — every answer traces
to a specific model function and data column.

If required data is missing, the answer is "Data Missing" with an explanation.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass


@dataclass
class QAnswer:
    """One Q-list answer."""
    question: str
    answer: str
    evidence: str           # which model/function produced this
    data_status: str        # "real_data" | "partial" | "data_missing"
    details: list[str]      # supporting detail lines


def build_qlist(df: pd.DataFrame, index_result, cli_index: pd.Series) -> list[QAnswer]:
    """Build answers to all 14 questions. Returns a list of QAnswer objects."""
    answers = []

    # ── Q1: Is liquidity tightening or loosening? ──
    try:
        changes = index_result.changes() if callable(getattr(index_result, "changes", None)) else {}
        regime = index_result.latest_regime
        level = index_result.latest
        w1 = changes.get("1w", float("nan"))
        m1 = changes.get("1m", float("nan"))
        m3 = changes.get("3m", float("nan"))

        if pd.notna(m1):
            if m1 > 2:
                direction = "Loosening"
            elif m1 < -2:
                direction = "Tightening"
            else:
                direction = "Stable"
        else:
            direction = "Insufficient data"

        answers.append(QAnswer(
            question="Is liquidity tightening or loosening?",
            answer=f"{direction} — CLI at {level:.1f} ({regime}), "
                   f"1M change {m1:+.1f} pts" if pd.notna(m1) else f"{direction}",
            evidence="index.composite.compute_index → changes()",
            data_status="real_data",
            details=[
                f"CLI level: {level:.1f} ({regime})",
                f"1W: {w1:+.1f}" if pd.notna(w1) else "1W: —",
                f"1M: {m1:+.1f}" if pd.notna(m1) else "1M: —",
                f"3M: {m3:+.1f}" if pd.notna(m3) else "3M: —",
            ],
        ))
    except Exception:
        answers.append(QAnswer("Is liquidity tightening or loosening?",
                               "Model error", "—", "data_missing", []))

    # ── Q2: Which bucket is driving the move? ──
    try:
        drivers = index_result.drivers("1m")
        bc = index_result.level_contributions()
        bc_details = [f"{k}: {v:+.2f}" for k, v in bc.items() if pd.notna(v)]

        answers.append(QAnswer(
            question="Which bucket is driving the move?",
            answer=f"Easing: {drivers[0] or '—'} · Tightening: {drivers[1] or '—'}",
            evidence="index.composite.IndexResult.drivers('1m'), level_contributions()",
            data_status="real_data",
            details=bc_details,
        ))
    except Exception:
        answers.append(QAnswer("Which bucket is driving the move?",
                               "Model error", "—", "data_missing", []))

    # ── Q3: Is funding stress elevated? ──
    try:
        from models.policy_short_rates import build_funding_pressure_score
        p = build_funding_pressure_score(df)
        if pd.notna(p["score"]):
            answers.append(QAnswer(
                question="Is funding stress elevated?",
                answer=f"{p['status']} — pressure score {p['score']:+.2f} "
                       f"({p['n_spreads']} spreads)",
                evidence="models.policy_short_rates.build_funding_pressure_score()",
                data_status="real_data",
                details=[
                    f"Average 1Y z-score of SOFR/EFFR/TGCR/BGCR/GCF/TPR vs IORB",
                    f"Thresholds: <−1 Easy · ±1 Normal · +1–2 Tight · >+2 Very tight",
                ],
            ))
        else:
            answers.append(QAnswer("Is funding stress elevated?",
                                   "No data", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("Is funding stress elevated?",
                               "Model not available", "—", "data_missing", []))

    # ── Q4: What is driving the curve? ──
    try:
        from models.rate_decomposition import build_us_curve_snapshot
        snap = build_us_curve_snapshot(df)
        if not snap.empty:
            r10 = snap[snap["tenor"] == "10Y"]
            if not r10.empty:
                row = r10.iloc[0]
                answers.append(QAnswer(
                    question="What is driving the curve — real rates or inflation?",
                    answer=f"10Y 1M driver: {row['driver_1m']} "
                           f"({row['driver_share_1m']:.0%} share). "
                           f"Nominal {row['nominal_1m_change_bp']:+.0f} bp = "
                           f"Real {row['real_1m_change_bp']:+.0f} bp + "
                           f"Inflation {row['inflation_1m_change_bp']:+.0f} bp",
                    evidence="models.rate_decomposition.build_us_curve_snapshot()",
                    data_status="real_data",
                    details=[f"{r['tenor']}: nom {r['nominal_1m_change_bp']:+.0f} "
                             f"= real {r['real_1m_change_bp']:+.0f} + "
                             f"infl {r['inflation_1m_change_bp']:+.0f} ({r['driver_1m']})"
                             for _, r in snap.iterrows()],
                ))
            else:
                answers.append(QAnswer("What is driving the curve?",
                                       "10Y data insufficient", "—", "partial", []))
        else:
            answers.append(QAnswer("What is driving the curve?",
                                   "Decomposition data missing", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("What is driving the curve?",
                               "Model error", "—", "data_missing", []))

    # ── Q5: What is the curve regime? ──
    try:
        from models.curve_regimes import classify_pair_history, days_in_current_regime
        h = classify_pair_history(df, "nominal", ("2Y", "10Y"), 10)
        if not h.empty and h["regime"].dropna().shape[0]:
            reg = h["regime"].dropna().iloc[-1]
            days = days_in_current_regime(h["regime"])
            spread = h["spread"].dropna().iloc[-1] * 100 if h["spread"].dropna().shape[0] else float("nan")
            answers.append(QAnswer(
                question="What is the curve regime (2s10s)?",
                answer=f"{reg} ({days}d), 2s10s at {spread:+.0f} bp" if pd.notna(spread)
                       else f"{reg} ({days}d)" if pd.notna(reg) else "—",
                evidence="models.curve_regimes.classify_pair_history()",
                data_status="real_data",
                details=[f"10D regime window, nominal 2s10s pair"],
            ))
        else:
            answers.append(QAnswer("What is the curve regime?",
                                   "Insufficient data", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("What is the curve regime?",
                               "Model error", "—", "data_missing", []))

    # ── Q6: What is the cross-asset regime? ──
    try:
        from data.external_loaders import load_crossasset
        from models.cross_asset.directional import classify_8regime, REGIMES_8, days_in_current_regime as ca_d
        ca = load_crossasset()
        if ca is not None:
            ca_r = classify_8regime(ca)
            if not ca_r.empty:
                cur = ca_r["regime"].iloc[-1]
                days = ca_d(ca_r["regime"])
                last = ca_r.iloc[-1]
                answers.append(QAnswer(
                    question="What is the cross-asset regime?",
                    answer=f"{REGIMES_8[cur]['label']} ({days}d)",
                    evidence="models.cross_asset.directional.classify_8regime()",
                    data_status="real_data",
                    details=[
                        f"SPX signal: {last['spx_signal']:+.2f}",
                        f"Rates signal: {last['rates_signal']:+.2f}",
                        f"DXY signal: {last['dxy_signal']:+.2f}",
                    ],
                ))
            else:
                answers.append(QAnswer("What is the cross-asset regime?",
                                       "Insufficient data", "—", "data_missing", []))
        else:
            answers.append(QAnswer("What is the cross-asset regime?",
                                   "CROSSASSET data missing", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("What is the cross-asset regime?",
                               "Model error", "—", "data_missing", []))

    # ── Q7: Where is the steepest global curve? ──
    try:
        from models.global_rates import build_slope_ranking, country_1m_changes
        slopes = build_slope_ranking(df)
        chg = country_1m_changes(df)
        if not slopes.empty:
            top = slopes.iloc[0]
            bot = slopes.iloc[-1]
            answers.append(QAnswer(
                question="Where is the steepest / flattest global curve?",
                answer=f"Steepest: {top['label']} ({top['slope_bp']:+.0f} bp) · "
                       f"Flattest: {bot['label']} ({bot['slope_bp']:+.0f} bp)",
                evidence="models.global_rates.build_slope_ranking()",
                data_status="real_data",
                details=[f"{r['label']}: {r['slope_bp']:+.0f} bp"
                         f"{' (INVERTED)' if r['inverted'] else ''}"
                         for _, r in slopes.iterrows()],
            ))
        else:
            answers.append(QAnswer("Where is the steepest global curve?",
                                   "No slope data", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("Where is the steepest global curve?",
                               "Model error", "—", "data_missing", []))

    # ── Q8: Is liquidity correlated with risk assets? ──
    try:
        from models.cli_correlations import build_all_correlations, CORR_TARGETS
        corrs = build_all_correlations(df, cli_index, window=20)
        if corrs:
            lines = []
            for k, s in corrs.items():
                v = s.dropna().iloc[-1] if s.dropna().shape[0] else float("nan")
                label = CORR_TARGETS[k]["label"]
                if pd.notna(v):
                    strength = "strong" if abs(v) > 0.5 else "moderate" if abs(v) > 0.25 else "weak"
                    sign = "positive" if v > 0 else "negative"
                    lines.append(f"CLI vs {label}: {v:+.3f} ({strength} {sign})")
            missing_keys = [k for k in CORR_TARGETS if k not in corrs]
            if missing_keys:
                lines.append(f"Not available: {', '.join(CORR_TARGETS[k]['label'] for k in missing_keys)}")
            if not corrs:
                status = "data_missing"
            elif missing_keys:
                status = "partial"
            else:
                status = "real_data"
            answers.append(QAnswer(
                question="Is liquidity correlated with risk assets?",
                answer="; ".join(lines[:2]) if lines else "No data",
                evidence="models.cli_correlations.build_all_correlations()",
                data_status=status,
                details=lines,
            ))
        else:
            answers.append(QAnswer("Is liquidity correlated with risk assets?",
                                   "No correlation targets available", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("Is liquidity correlated with risk assets?",
                               "Model error", "—", "data_missing", []))

    # ── Q9: Which FX pair has the strongest current rate-differential linkage? ──
    try:
        from models.fx_rate_differential import (
            build_fx_current_reading as _fx_reading, FX_PAIR_CONFIG as _fxcfg,
            ALIGNMENT_METRIC_MAP as _align_map,
        )
        best_pair, best_corr, best_metric = None, 0, None
        details = []
        for pair in _fxcfg:
            reading = _fx_reading(df, pair)
            if reading.get("status") != "Ready":
                details.append(f"{pair}: {reading.get('status', '—')} (excluded)")
                continue
            corr_val = reading.get("strongest_corr_value", 0)
            corr_met = reading.get("strongest_corr_metric", "—")
            # Get alignment for the SAME leg
            align_key = _align_map.get(corr_met, "alignment_nom_2y_diff")
            leg_align = reading.get(align_key, "—")
            model_date = reading.get("common_latest_date") or reading.get("model_date", "—")
            details.append(f"{pair}: {corr_met} ({corr_val:+.3f}), "
                           f"{corr_met} align={leg_align}, date={model_date}")
            if abs(corr_val) > abs(best_corr):
                best_corr = corr_val
                best_pair = pair
                best_metric = corr_met
        if best_pair:
            br = _fx_reading(df, best_pair)
            best_align_key = _align_map.get(best_metric, "alignment_nom_2y_diff")
            best_leg_align = br.get(best_align_key, "—")
            best_date = br.get("common_latest_date") or br.get("model_date", "—")
            answers.append(QAnswer(
                question="Which FX pair has the strongest current rate-differential linkage?",
                answer=f"{best_pair} — {best_metric} linkage {best_corr:+.3f}; "
                       f"current {best_metric} alignment: {best_leg_align}; "
                       f"model date {best_date}",
                evidence="models.fx_rate_differential.build_fx_current_reading()",
                data_status="real_data",
                details=details,
            ))
        else:
            answers.append(QAnswer("Which FX pair has the strongest linkage?",
                                   "No Ready pairs with valid correlations", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer("Which FX pair has the strongest linkage?",
                               "Model error", "—", "data_missing", []))

    # ── Q10: Which SPX sectors rank highest and lowest versus SPX? ──
    try:
        from models.sector_rotation import build_sector_current_reading
        from data.external_loaders import load_spx_sector_weights
        _weights = load_spx_sector_weights()
        _sec = build_sector_current_reading(df, _weights)
        if _sec.get("status") == "Ready":
            top_str = "; ".join(f"{n} ({v:+.2f}pp)" for n, v in _sec.get("top_rel", []))
            bot_str = "; ".join(f"{n} ({v:+.2f}pp)" for n, v in _sec.get("bottom_rel", []))
            rb = _sec.get("relative_breadth_pct")
            answers.append(QAnswer(
                question="Which SPX sectors rank highest and lowest versus SPX?",
                answer=f"Top-ranked 3 on 20D relative performance: {top_str}. Lowest-ranked 3: {bot_str}. "
                       f"SPX-outperform breadth: {_sec.get('outperf_count', 0)}/"
                       f"{_sec.get('positive_denom', 0)} "
                       f"({rb:.0f}%). Model date: {_sec.get('relative_model_date', '—')}.",
                evidence="models.sector_rotation.build_sector_current_reading()",
                data_status="real_data",
                details=[
                    f"Sector-only date: {_sec.get('sector_only_date')}",
                    f"Relative model date: {_sec.get('relative_model_date')}",
                    f"Weight date: {_sec.get('weight_date')}",
                    f"20D positive breadth: {_sec.get('positive_count', 0)}/"
                    f"{_sec.get('positive_denom', 0)}",
                ],
            ))
        else:
            answers.append(QAnswer(
                "Which SPX sectors rank highest and lowest versus SPX?",
                f"Data Missing ({_sec.get('status', 'unknown')})", "—", "data_missing", []))
    except Exception:
        answers.append(QAnswer(
            "Which SPX sectors rank highest and lowest versus SPX?",
            "Model error", "—", "data_missing", []))

    # ── Q11: Which sectors contributed most to the estimated SPX return? ──
    try:
        from models.sector_contribution import build_sector_contribution_current_reading
        from data.external_loaders import load_spx_sector_weights as _load_contrib_weights
        _contrib = build_sector_contribution_current_reading(
            df, _load_contrib_weights(), horizon=20
        )
        if _contrib.get("status") == "Ready":
            pos = "; ".join(
                f"{row['display_name']} ({row['estimated_contribution_pp']:+.3f}pp)"
                for row in _contrib.get("top_positive", [])
            ) or "—"
            neg = "; ".join(
                f"{row['display_name']} ({row['estimated_contribution_pp']:+.3f}pp)"
                for row in _contrib.get("top_negative", [])
            ) or "—"
            answers.append(QAnswer(
                question="Which sectors contributed most to the estimated SPX return?",
                answer=(
                    f"Largest positive 20D estimates: {pos}. Largest negative estimates: {neg}. "
                    f"Actual SPX return {_contrib.get('actual_spx_return_pct'):+.2f}%, "
                    f"estimated {_contrib.get('estimated_spx_return_pct'):+.2f}%, "
                    f"residual {_contrib.get('residual_pp'):+.3f}pp. "
                    f"Window {_contrib.get('start_date')} to {_contrib.get('end_date')}; "
                    f"start weight {_contrib.get('weight_date')}."
                ),
                evidence="models.sector_contribution.build_sector_contribution_current_reading()",
                data_status="real_data",
                details=[
                    "Approximation: start-period periodic weight × sector simple return.",
                    "Residual = actual SPX return − estimated return.",
                    "Not official SPX attribution.",
                ],
            ))
        else:
            answers.append(QAnswer(
                "Which sectors contributed most to the estimated SPX return?",
                f"Data Missing ({_contrib.get('status', 'unknown')})",
                "models.sector_contribution.build_sector_contribution_current_reading()",
                "data_missing",
                _contrib.get("warnings", []),
            ))
    except Exception:
        answers.append(QAnswer(
            "Which sectors contributed most to the estimated SPX return?",
            "Model error", "—", "data_missing", []))

    # ── Q12: Are SPX returns moving with FY1 earnings or valuation? ──
    try:
        from data.equity_earnings_loader import load_equity_earnings_data
        from models.earnings_valuation import build_earnings_current_reading
        _earn = build_earnings_current_reading(load_equity_earnings_data(), code="ES1")
        if _earn.get("status") == "Ready" and pd.notna(_earn.get("current_price_return_pct")):
            answers.append(QAnswer(
                question="Are recent SPX returns driven more by FY1 earnings revisions or valuation multiple changes?",
                answer=(
                    f"Over {_earn.get('decomposition_horizon', 4)} common weekly observations, "
                    f"SPX returned {_earn.get('current_price_return_pct'):+.2f}%; "
                    f"FY1 EPS contributed {_earn.get('current_eps_growth_pct'):+.2f}% and "
                    f"the implied FY1 P/E changed {_earn.get('current_valuation_change_pct'):+.2f}%. "
                    f"Larger component: {_earn.get('current_driver')}. "
                    f"Model date {_earn.get('model_date')}."
                ),
                evidence="models.earnings_valuation.build_earnings_current_reading()",
                data_status="real_data",
                details=[
                    "Exact log identity: SPX return = FY1 EPS growth + implied FY1 P/E change.",
                    "EPS field: BEST_EPS with BEST_FPERIOD_OVERRIDE=1FY; weekly.",
                    f"Identity residual: {_earn.get('current_identity_residual_pct'):+.8f}%.",
                    f"Weekly OLS diagnostic: beta {_earn.get('regression_beta', float('nan')):+.3f}, "
                    f"R² {_earn.get('regression_r_squared', float('nan')):.3f}; descriptive, not causal.",
                ],
            ))
        else:
            answers.append(QAnswer(
                "Are recent SPX returns driven more by FY1 earnings revisions or valuation multiple changes?",
                f"Data Missing ({_earn.get('status', 'unknown')})",
                "models.earnings_valuation.build_earnings_current_reading()",
                "data_missing",
                _earn.get("missing", []),
            ))
    except Exception:
        answers.append(QAnswer(
            "Are recent SPX returns driven more by FY1 earnings revisions or valuation multiple changes?",
            "Model error", "—", "data_missing", []))

    # ── Q13: Which cross-asset relationships are strongest now? ──
    try:
        from data.external_loaders import load_ficc as _load_linkage_ficc
        from models.market_linkage import build_market_linkage_current_reading
        _linkage_frame = _load_linkage_ficc()
        _linkage = (
            build_market_linkage_current_reading(_linkage_frame, corr_window=20)
            if _linkage_frame is not None else {"status": "Missing data"}
        )
        if _linkage.get("status") == "Ready":
            _pos = _linkage.get("strongest_positive") or {}
            _neg = _linkage.get("strongest_negative") or {}
            answers.append(QAnswer(
                question="Which cross-asset relationships are strongest right now?",
                answer=(
                    f"The one-trade linkage gauge is "
                    f"{_linkage.get('pc1_explained_variance', float('nan')):.1%} "
                    f"of total standardized variance (2Y percentile "
                    f"{_linkage.get('linkage_percentile_2y', float('nan')):.0f}/100). "
                    f"Strongest positive 20-observation pair: "
                    f"{_pos.get('label', '—')} ({_pos.get('correlation', float('nan')):+.2f}); "
                    f"strongest negative: {_neg.get('label', '—')} "
                    f"({_neg.get('correlation', float('nan')):+.2f}). "
                    f"Model date {_linkage.get('model_date')}."
                ),
                evidence="models.market_linkage.build_market_linkage_current_reading()",
                data_status="real_data",
                details=[
                    "Universe: SPX, UST 10Y and DXY, aligned before daily transformations.",
                    "All level series are aligned before daily transformations.",
                    "Correlation describes co-movement; it is not causal attribution or a forecast.",
                ],
            ))
        else:
            answers.append(QAnswer(
                "Which cross-asset relationships are strongest right now?",
                f"Data Missing ({_linkage.get('status', 'unknown')})",
                "models.market_linkage.build_market_linkage_current_reading()",
                "data_missing",
                _linkage.get("missing", []),
            ))
    except Exception:
        answers.append(QAnswer(
            "Which cross-asset relationships are strongest right now?",
            "Model error", "—", "data_missing", []))

    # ── Q14: What does the fixed-contract SOFR strip imply? ──
    try:
        from data.policy_futures_loader import load_policy_futures
        from models.policy_futures_strip import build_sofr_strip_snapshot
        _fixed = load_policy_futures()
        _snap = build_sofr_strip_snapshot(_fixed, df)
        _tbl = _snap.get("strip_table")
        if _snap.get("status") == "Ready" and hasattr(_tbl, "empty") and not _tbl.empty:
            _terminal = _snap["terminal"]
            _spreads = _snap["terminal_spreads"]
            answers.append(QAnswer(
                question="What does the fixed-contract SOFR futures strip imply?",
                answer=(
                    f"The strip peaks at {_terminal['terminal_rate_pct']:.3f}% in "
                    f"{_terminal['terminal_contract']}, {_terminal['terminal_gap_bp']:+.1f}bp "
                    f"versus EFFR. Terminal to +12 months is "
                    f"{_spreads.get('terminal_to_12m_bp'):+.1f}bp as of {_snap['model_date']}."
                ),
                evidence="models.policy_futures_strip.build_sofr_strip_snapshot()",
                data_status="real_data",
                details=[
                    "Eight actual quarterly SFR contracts: SEP 26 through JUN 28.",
                    "Implied reference rate = 100 − futures price.",
                    "Each contract uses its own Bloomberg Date output and is joined by Date.",
                    "This is not a meeting-by-meeting FOMC path or probability distribution.",
                ],
            ))
        else:
            answers.append(QAnswer(
                "What does the fixed-contract SOFR futures strip imply?",
                f"Data Missing ({_snap.get('status', 'unknown')})", "—",
                "data_missing", _snap.get("missing", []),
            ))
    except Exception:
        answers.append(QAnswer(
            "What does the fixed-contract SOFR futures strip imply?",
            "Model error", "—", "data_missing", [],
        ))

    return answers
