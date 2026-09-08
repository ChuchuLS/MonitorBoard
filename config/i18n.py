"""Small presentation-only bilingual layer for the Streamlit board.

English remains the source language used by calculations and exports.  The
Chinese option changes labels and explanatory copy only; it never changes a
ticker, model key, dataframe column, calculation, or publication rule.
"""

from __future__ import annotations

from copy import deepcopy


LANG_EN = "en"
LANG_ZH = "zh"
SUPPORTED_LANGUAGES = (LANG_EN, LANG_ZH)


def current_language() -> str:
    """Return the active UI language without making non-Streamlit imports fail."""
    try:
        import streamlit as st
        value = st.session_state.get("ui_language", LANG_EN)
    except Exception:
        value = LANG_EN
    return value if value in SUPPORTED_LANGUAGES else LANG_EN


def tr(english: str, chinese: str, language: str | None = None) -> str:
    """Choose presentation text.  English is the safe fallback."""
    return chinese if (language or current_language()) == LANG_ZH else english


PAGE_ZH: dict[str, dict[str, str]] = {
    "contents": {
        "title": "研究总览",
        "description": "每日宏观与流动性研究看板。",
        "sidebar": "研究总览",
    },
    "liquidity": {
        "title": "流动性概览",
        "description": "综合流动性指数：由五个板块构成，并以数据覆盖门槛控制正式发布。指数采用滚动 z-score 标准化，数值越高代表流动性越宽松；本页同时展示板块与组件贡献、基准验证、方法审计和 XCCY 基差摘要。",
        "sidebar": "流动性概览",
    },
    "policy": {
        "title": "政策与短端利率",
        "description": "跟踪已确认的政策利率和资金市场结构，包括 SOFR、EFFR、IORB、TGCR、BGCR、GCF、三方回购利差、资金压力诊断与每周 H.4.1 背景。",
        "sidebar": "政策与短端利率",
    },
    "policy_futures": {
        "title": "SOFR 期货曲线与跨期价差",
        "description": "展示八个固定季度的三个月 SOFR 合约、隐含利率、1日/5日/1月变化、跨期价差和终端利率诊断；这不是逐次 FOMC 会议路径。",
        "sidebar": "SOFR 期货曲线",
    },
    "decomposition": {
        "title": "利率变动拆解",
        "description": "把名义收益率变动拆为实际利率与通胀补偿，并展示美债曲线、滚动归因及 2s10s 曲线拆解。",
        "sidebar": "利率变动拆解",
    },
    "regimes": {
        "title": "收益率曲线状态",
        "description": "在名义、实际与通胀曲线上，对六组期限组合进行牛/熊市与陡峭化、平坦化、扭曲或中性的七状态分类。",
        "sidebar": "曲线状态",
    },
    "global_rates": {
        "title": "全球利率",
        "description": "展示七个市场的10年期收益率标准化走势、曲线快照和 2s10s 斜率排名；缺失交易日不做向前填充。",
        "sidebar": "全球利率",
    },
    "country_boards": {
        "title": "各国利率看板",
        "description": "对美国、德国、日本、英国、加拿大、澳大利亚和瑞士的 2Y/5Y/10Y/30Y 主权曲线进行同日比较；不使用代理值、向前填充或预测。",
        "sidebar": "各国利率看板",
    },
    "cross_asset": {
        "title": "跨资产状态时间线",
        "description": "使用 SPX、美债10年期与 DXY 的20日变化和21日波动率构建八种方向状态。",
        "sidebar": "跨资产状态",
    },
    "market_linkage": {
        "title": "市场联动与相关性",
        "description": "展示 SPX、美债10年期与 DXY 的滚动 PC1 解释度及三组两两相关性；不提供因果归因或预测。",
        "sidebar": "市场联动",
    },
    "fx_rate_diff": {
        "title": "外汇利差监测",
        "description": "按货币对跟踪 EURUSD、USDJPY、GBPUSD 和 AUDUSD 的利差、现货与相关诊断。",
        "sidebar": "外汇利差",
    },
    "sector_rotation": {
        "title": "行业轮动与广度",
        "description": "描述标普500十一大行业的绝对与相对表现、市场广度、横截面离散度和轮动象限；并非官方指数收益归因。",
        "sidebar": "行业轮动",
    },
    "sector_contribution": {
        "title": "行业贡献估算",
        "description": "使用各收益窗口起点之前最近一期可用行业权重，估算行业对 SPX 收益的贡献，并明确列示残差；并非指数供应商的官方归因。",
        "sidebar": "行业贡献",
    },
    "index_breadth": {
        "title": "全球指数趋势与市场广度",
        "description": "使用各指数自身现货收盘价与可用的 50日、200日和100周均线展示趋势；缺失输入保持缺失。",
        "sidebar": "指数广度",
    },
    "earnings_valuation": {
        "title": "全球 FY1 盈利与估值",
        "description": "按所选指数展示已确认的 FY1 一致预期 EPS、精确收益拆解与隐含 FY1 市盈率；不是公允价值或预测。",
        "sidebar": "盈利与估值",
    },
    "data_quality": {
        "title": "数据质量与方法",
        "description": "审计 DATA.xlsx 的数据来源、日期、覆盖、陈旧度、缺失项和方法参数，形成可追溯的数据可信链。",
        "sidebar": "数据与方法",
    },
    "scoring": {
        "title": "全球评分（附录）",
        "description": "针对10个市场的横截面宏观与市场评分模型；各项输入、权重和缺失状态均明确展示。",
        "sidebar": "全球评分",
    },
    "scoring_backtest": {
        "title": "CTA 评分回测",
        "description": "固定规格的周度 Top 3 减 Bottom 3 信号诊断，包含短样本保护、分期稳定性、逐期剔除和固定参数敏感性测试。",
        "sidebar": "CTA 回测",
    },
    "model_roadmap": {
        "title": "模型路线图与内容缺口",
        "description": "对照参考报告列示已完成、尚缺失、所需数据及后续优先建设内容。",
        "sidebar": "模型路线图",
    },
}


SIDEBAR_GROUP_ZH = {
    "overview": "总览",
    "macro_rates": "宏观与利率",
    "cross_asset": "跨资产",
    "equities": "股票",
    "research": "研究与数据",
}


TOP_NAV_ZH = {
    "liquidity": "流动性",
    "policy": "政策",
    "decomposition": "拆解",
    "regimes": "状态",
    "global_rates": "全球利率",
    "cross_asset": "跨资产",
    "equities": "股票",
    "fx": "外汇",
    "appendix": "附录",
}


STATUS_ZH = {
    "live": "已上线",
    "partial": "部分完成",
    "scaffold": "框架页",
    "requires": "需要数据",
    "experimental": "实验性",
}


REGIME_ZH = {
    "Loose": "宽松",
    "Neutral": "中性",
    "Tight": "偏紧",
    "Stress": "压力",
}


CURVE_REGIME_ZH = {
    "Bull Steepener": "牛市陡峭化",
    "Bull Flattener": "牛市平坦化",
    "Bear Steepener": "熊市陡峭化",
    "Bear Flattener": "熊市平坦化",
    "Twist Steepener": "扭曲式陡峭化",
    "Twist Flattener": "扭曲式平坦化",
    "Neutral": "中性",
}


CURVE_TYPE_ZH = {
    "Nominal": "名义",
    "Real": "实际",
    "Inflation": "通胀",
}


BUCKET_ZH = {
    "Money-market funding": "货币市场融资",
    "Dollar funding / XCCY": "美元融资 / XCCY",
    "Dollar funding/XCCY": "美元融资 / XCCY",
    "Credit liquidity": "信用流动性",
    "Central bank / reserves": "央行 / 储备",
    "Central bank/reserves": "央行 / 储备",
    "Market liquidity / vol": "市场流动性 / 波动率",
    "Market liquidity/vol": "市场流动性 / 波动率",
}


def localized_page(page: dict, language: str | None = None) -> dict:
    """Return a localized copy of page metadata; never mutate the registry."""
    language = language or current_language()
    if language != LANG_ZH:
        return page
    translated = deepcopy(page)
    translated.update({
        key: value
        for key, value in PAGE_ZH.get(page.get("id", ""), {}).items()
        if key in {"title", "description"}
    })
    return translated


def localized_bucket(label: str, language: str | None = None) -> str:
    if (language or current_language()) == LANG_ZH:
        return BUCKET_ZH.get(label, label)
    return label


def localized_regime(label: str, language: str | None = None) -> str:
    if (language or current_language()) == LANG_ZH:
        return REGIME_ZH.get(label, label)
    return label


def localized_curve_regime(label: str, language: str | None = None) -> str:
    """Translate a curve-classification output without changing model keys."""
    if (language or current_language()) == LANG_ZH:
        return CURVE_REGIME_ZH.get(label, label)
    return label


def localized_curve_type(label: str, language: str | None = None) -> str:
    """Translate the displayed curve family without changing dataframe keys."""
    if (language or current_language()) == LANG_ZH:
        return CURVE_TYPE_ZH.get(label, label)
    return label
