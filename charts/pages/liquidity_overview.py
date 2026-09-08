"""
charts/pages/liquidity_overview.py
==================================
Section 00 — Liquidity Overview. Wraps the existing render_index_page /
render_summary_panel (untouched) inside the new PDF-style shell.

The Composite Liquidity Index computation is NOT modified in Phase 1. This
module only adds the header, KPI strip, explanation box and footer around it.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.i18n import current_language, localized_bucket, localized_regime, tr
from config.theme import section_color

from charts.common import (
    render_page_header, render_kpi_strip,
    render_explanation_box, render_section_footer,
)
from charts.liquidity import (
    render_driver_cards,
    render_index_page,
    render_latest_official_move,
)
from charts.funding import render_xccy_summary
from index.components import BUCKETS
from index.composite import HEADLINE_REQUIRED_BUCKETS
from index.methodology import INDEX_METHODOLOGY

from ._context import PageContext

logger = logging.getLogger(__name__)


def render(ctx: PageContext) -> None:
    language = current_language()
    page = get_page("liquidity")
    color = section_color(page["color_key"])

    r = ctx.index_result
    published = r.headline_index.dropna()
    published_date = published.index[-1] if len(published) else None
    preliminary_date = r.preliminary_date
    raw_latest_date = ctx.df.index.max() if len(ctx.df) else None
    latest = (published_date.strftime("%b %d, %Y").upper()
              if published_date is not None else "—")
    viewing = (
        f"{ctx.start_date.strftime('%b %Y').upper()} → "
        f"{ctx.end_date.strftime('%b %Y').upper()} · "
        f"{tr('raw workbook latest', '原始工作簿最新日期', language)} "
        f"{raw_latest_date.date() if raw_latest_date is not None else '—'}"
    )
    render_page_header(page, latest_date=latest, viewing=viewing)

    regime = getattr(r, "latest_regime", "—")

    def _fmt_change(v, unit="pts"):
        if v is None or pd.isna(v):
            return "—"
        return f"{v:+.1f} {unit}"

    changes = r.changes() if callable(getattr(r, "changes", None)) else {}
    kpi_cards = [
        {"label": tr("Composite Liquidity Index", "综合流动性指数", language),
         "value": f"{r.latest:.1f}" if pd.notna(r.latest) else "—",
         "sub": (f"{tr('Official', '正式值', language)} {published_date.date()} · "
                 f"{tr('regime', '状态', language)}: {localized_regime(regime, language)}"
                 if published_date is not None else tr("No complete date available", "暂无完整日期", language)),
         "accent": color},
        {"label": tr("1-week change", "1周变化", language),
         "value": _fmt_change(changes.get("1w")),
         "sub": tr("vs 5 business days ago", "相对5个工作日前", language)},
        {"label": tr("1-month change", "1个月变化", language),
         "value": _fmt_change(changes.get("1m")),
         "sub": tr("vs 21 business days ago", "相对21个工作日前", language)},
        {"label": tr("3-month change", "3个月变化", language),
         "value": _fmt_change(changes.get("3m")),
         "sub": tr("vs 63 business days ago", "相对63个工作日前", language)},
    ]
    render_kpi_strip(kpi_cards)

    if preliminary_date is not None and pd.notna(r.preliminary_latest):
        buckets = int(r.available_bucket_count.loc[preliminary_date])
        components = int(r.available_component_count.loc[preliminary_date])
        target_value = r.normal_component_target.loc[preliminary_date]
        target = int(target_value) if pd.notna(target_value) else None
        target_text = str(target) if target is not None else "unavailable"
        missing_bucket_labels = [
            localized_bucket(BUCKETS[bucket]["label"], language)
            for bucket in BUCKETS
            if bucket not in r.sub_indices.columns
            or pd.isna(r.sub_indices.at[preliminary_date, bucket])
        ]
        missing_bucket_text = (
            ", ".join(missing_bucket_labels) if missing_bucket_labels else "none"
        )
        if language == "zh":
            st.warning(
                f"初步值 {preliminary_date.date()}：{r.preliminary_latest:.1f} "
                f"（{buckets}/{HEADLINE_REQUIRED_BUCKETS} 个板块，{components} 个有效组件；"
                f"正常覆盖门槛为 {target_text}）。在数据覆盖完整前，该读数不进入正式标题、"
                f"市场状态、涨跌幅或贡献计算。缺失的合格板块：{missing_bucket_text}。"
                "由于诊断权重经过重新归一化，该初步值不能与正式值直接比较；两者差额不能解释为市场涨跌。"
            )
        else:
            st.warning(
                f"Preliminary {preliminary_date.date()}: {r.preliminary_latest:.1f} "
                f"({buckets}/{HEADLINE_REQUIRED_BUCKETS} buckets, {components} live "
                f"components; normal coverage target {target_text}). It is excluded from "
                "the official headline, regime, changes and contribution calculations until "
                f"coverage is complete. Missing qualifying bucket(s): {missing_bucket_text}. "
                "This partial estimate is not comparable with the official level because "
                "diagnostic weights are renormalised; do not interpret their difference as a market move."
            )

    if language == "zh":
        render_explanation_box(
            "版本与日期",
            f"<b>方法版本：</b>{INDEX_METHODOLOGY['version']}，启用完整日期正式值规则。"
            f"<b>正式模型日期：</b>{published_date.date() if published_date is not None else '—'}。"
            f"<b>初步模型日期：</b>{preliminary_date.date() if preliminary_date is not None else '—'}。"
            f"<b>原始工作簿最新行：</b>{raw_latest_date.date() if raw_latest_date is not None else '—'}。"
        )
        st.caption(
            "z-score 公式和板块权重未改变。方法 v0.4 只调整正式值选择：最近一个覆盖完整的日期才是正式值；"
            "更晚但不完整的读数保持为初步值，不能改写正式涨跌。"
        )
    else:
        render_explanation_box(
            "Version and dates",
            f"<b>Methodology:</b> {INDEX_METHODOLOGY['version']} — complete-date headline rule active. "
            f"<b>Official model date:</b> {published_date.date() if published_date is not None else '—'}. "
            f"<b>Preliminary model date:</b> {preliminary_date.date() if preliminary_date is not None else '—'}. "
            f"<b>Raw workbook latest row:</b> {raw_latest_date.date() if raw_latest_date is not None else '—'}. "
        )
        st.caption(
            "The z-score formula and bucket weights are unchanged. Methodology v0.4 changes "
            "headline selection: only the most recent fully covered date is official; later "
            "partial observations remain preliminary and cannot rewrite headline changes."
        )

    render_explanation_box(
        tr("What this section shows", "本页说明", language),
        tr(
            "A raw-indicator liquidity gauge, z-scored across five buckets (money-market funding, dollar funding, credit, central-bank reserves, market liquidity) and rescaled so <b>50 = neutral</b> and higher = looser. The headline automatically steps back to the latest fully covered date. The panels below decompose that official reading into bucket and component contributions, benchmark it against Bloomberg FCI and the Chicago Fed NFCI, and expose the full methodology audit trail. The <b>Export to Excel</b> button ships a multi-sheet workbook of index, buckets, components, contributions, reconciliation, forward-fill audit and methodology parameters.",
            "这是一个由原始指标构成的流动性温度计。五个板块经过滚动 z-score 标准化后合成，<b>50 = 中性</b>，数值越高代表越宽松。正式标题会自动退回最近一个覆盖完整的日期。下方把正式读数拆成板块和组件贡献，并与 Bloomberg FCI、Chicago Fed NFCI 对照，同时保留完整的方法审计轨迹。<b>导出 Excel</b> 会生成包含指数、板块、组件、贡献、对账、向前填充审计和方法参数的多工作表文件。",
            language,
        ),
    )

    # The research-pack shell above already renders level and horizon changes.
    # Keep only the contributor cards here so the four headline KPIs appear
    # exactly once on the page.
    render_driver_cards(r)
    render_latest_official_move(r)
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
    render_index_page(
        ctx.df, ctx.dff, r, ctx.audit_bundle,
        export_bytes=ctx.export_builder,
        export_name=ctx.export_name,
    )

    # ── Compact XCCY basis summary; full 5×2 history is on FX 07. ──
    try:
        render_xccy_summary(ctx.dff)
    except Exception as exc:
        logger.exception("Failed to render the Liquidity XCCY summary")
        st.warning(
            "Dollar-funding / XCCY summary is unavailable because the audit "
            f"failed ({type(exc).__name__}). This does not mean the source "
            "series are zero or absent."
        )

    # ── CLI Rolling Correlations (only if target data exists) ──
    try:
        from models.cli_correlations import available_targets, build_all_correlations, CORR_TARGETS
        targets = available_targets(ctx.df)
        if targets:
            import plotly.graph_objects as go
            from config.theme import BG, GRID, TEXT_DIM

            st.markdown(
                "<div style='margin:1.2rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "CLI rolling correlations (20-day)</div>",
                unsafe_allow_html=True,
            )

            corrs = build_all_correlations(ctx.df, r.index, window=20)
            if corrs:
                COLORS = {"SPX": "#3b82f6", "HSI": "#ef4444", "BTC": "#f97316"}
                fig = go.Figure()
                for key, series in corrs.items():
                    label = CORR_TARGETS[key]["label"]
                    fig.add_trace(go.Scatter(
                        x=series.index, y=series, mode="lines",
                        line=dict(color=COLORS.get(key, "#888"), width=1.4),
                        name=f"CLI vs {label}",
                    ))
                fig.add_hline(y=0, line=dict(color="#333", width=0.5, dash="dot"))
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                    font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
                    height=300, showlegend=True,
                    legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
                    margin=dict(l=50, r=20, t=30, b=25),
                    yaxis=dict(title="Correlation", gridcolor=GRID, range=[-1, 1]),
                    xaxis=dict(showgrid=False),
                )
                st.plotly_chart(fig, use_container_width=True, key="cli_corrs",
                                config={"displayModeBar": False})

                # Show which targets are live vs missing
                live_keys = list(corrs.keys())
                all_keys = list(CORR_TARGETS.keys())
                missing_keys = [k for k in all_keys if k not in live_keys]
                cap_parts = [
                    "20-day rolling correlation between CLI level changes and "
                    "asset log returns. Positive = asset tends to rise when "
                    "liquidity loosens.",
                ]
                if missing_keys:
                    missing_labels = [CORR_TARGETS[k]["label"] for k in missing_keys]
                    cap_parts.append(
                        f"Not shown (data missing): {', '.join(missing_labels)}. "
                        "Add tickers to DATA.xlsx to enable.")
                st.caption(" ".join(cap_parts))
        else:
            # Data missing — show honest status
            from charts.common import render_missing_data_warning
            render_missing_data_warning(
                required=["HSI INDEX (Hang Seng)", "XBTUSD BGN Curncy (Bitcoin)"],
                missing=["HSI INDEX", "XBTUSD / BTC price"],
                message=(
                    "<b>CLI rolling correlations</b> are not shown because "
                    "neither HSI nor Bitcoin price data is in DATA.xlsx. "
                    "Add these tickers to the Bloomberg BDH pull to enable "
                    "the correlation charts."
                ),
            )
    except Exception as exc:
        logger.exception("Failed to render CLI rolling correlations")
        st.warning(
            "CLI rolling correlations are unavailable because their calculation "
            f"failed ({type(exc).__name__}). No missing result was replaced with "
            "zero or a proxy."
        )

    # ── Q-list Answering Panel ──
    try:
        from models.qlist import build_qlist

        st.markdown(
            "<div style='margin:1.4rem 0 0.3rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Dashboard Q&amp;A</div>",
            unsafe_allow_html=True,
        )

        qlist = build_qlist(ctx.df, r, r.index)

        STATUS_COLORS_Q = {
            "real_data": "#5fb04f", "partial": "#d99830", "data_missing": "#d04848",
        }

        for qa in qlist:
            sc = STATUS_COLORS_Q.get(qa.data_status, "#666")
            with st.expander(f"❓ {qa.question}", expanded=False):
                st.markdown(
                    f"<div style='font-size:13px;color:#fff;font-weight:700;"
                    f"margin-bottom:6px;'>{qa.answer}</div>"
                    f"<div style='font-size:10px;color:#888;margin-bottom:4px;'>"
                    f"Evidence: <code>{qa.evidence}</code></div>"
                    f"<div style='display:inline-block;padding:2px 8px;"
                    f"border:1px solid {sc}55;color:{sc};border-radius:3px;"
                    f"font-size:9px;font-weight:700;text-transform:uppercase;'>"
                    f"{qa.data_status.replace('_', ' ')}</div>",
                    unsafe_allow_html=True,
                )
                if qa.details:
                    for d in qa.details:
                        st.markdown(f"<div style='font-size:11px;color:#aaa;"
                                    f"margin-left:12px;'>• {d}</div>",
                                    unsafe_allow_html=True)
    except Exception as exc:
        logger.exception("Failed to render dashboard Q&A")
        st.warning(
            "Dashboard Q&A is unavailable because its evidence build failed "
            f"({type(exc).__name__}). The analytical panels above are unaffected."
        )

    render_section_footer(page)
