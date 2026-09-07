"""Streamlit runtime smoke test for the two highest-risk entry points.

Run after installing requirements.txt.  Importing app.py loads the complete
renderer registry; the second run exercises the CTA page that previously
failed when pandas attempted to import SciPy for Spearman correlation.
"""
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parent


def _assert_clean(app: AppTest, stage: str) -> None:
    if app.exception:
        details = " | ".join(str(item.value) for item in app.exception)
        raise AssertionError(f"{stage} raised Streamlit exceptions: {details}")


print("=== STREAMLIT RUNTIME TEST ===")
at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
at.run(timeout=180)
_assert_clean(at, "Contents page")
print("1. Contents page + full renderer import registry ✓")

expected_groups = ["Overview", "Macro & Rates", "Cross-Asset", "Equities", "Research & Data"]
assert [item.label for item in at.sidebar.expander] == expected_groups, \
    "Sidebar navigation groups did not render in the intended order"
assert not at.sidebar.radio, "Legacy flat sidebar radio should be removed"
lookback = next((widget for widget in at.sidebar.selectbox
                 if widget.key == "lookback_preset"), None)
assert lookback is not None and lookback.value == "3Y", \
    "Compact Lookback selector was not rendered"
sidebar_markup = " ".join(str(item.value) for item in at.sidebar.markdown)
for text in ("Raw data", "Official model", "Pending", "buckets", "live"):
    assert text in sidebar_markup, f"Sidebar status is missing: {text}"
print("   grouped navigation + exact Raw/Official/Pending status ✓")

# The current workbook has a later partial analytical observation.  It must be
# visible as preliminary rather than replacing the official headline.
assert any("Preliminary" in str(item.value) for item in at.markdown), \
    "Contents page did not label the later partial liquidity reading"

language = next((widget for widget in at.sidebar.selectbox
                 if widget.key == "ui_language_choice"), None)
assert language is not None and language.value == "English", \
    "Bilingual selector did not default to English"
language.set_value("中文").run(timeout=180)
_assert_clean(at, "Chinese Contents page")
assert [item.label for item in at.sidebar.expander] == [
    "总览", "宏观与利率", "跨资产", "股票", "研究与数据",
], "Chinese navigation groups did not render"
page_markup = " ".join(str(item.value) for item in at.markdown)
assert "研究总览" in page_markup and "今日看板状态" in page_markup, \
    "Chinese Contents header or dashboard state is missing"
pdf_buttons = at.get("download_button")
assert any("英文" in widget.label for widget in pdf_buttons), \
    "PDF export must remain explicitly English-only in Chinese UI"
print("   Chinese UI toggle + English-only PDF contract ✓")

nav = next((widget for widget in at.sidebar.button
            if widget.key == "sidebar_nav_liquidity"), None)
assert nav is not None, "Grouped sidebar Liquidity navigation was not rendered"
nav.click().run(timeout=180)
_assert_clean(at, "00 Liquidity page")
assert any("初步值" in str(item.value) for item in at.warning), \
    "Chinese Liquidity page did not show the preliminary coverage warning"
liquidity_markup = " ".join(str(item.value) for item in at.markdown)
for text in ("流动性概览", "综合流动性指数", "最新正式变动", "覆盖与可靠性"):
    assert text in liquidity_markup, f"Chinese Liquidity rendering is missing: {text}"
print("2. Liquidity official/preliminary rendering ✓")

nav = next((widget for widget in at.sidebar.button
            if widget.key == "sidebar_nav_scoring_backtest"), None)
assert nav is not None, "Grouped sidebar CTA Backtest navigation was not rendered"
nav.click().run(timeout=180)
_assert_clean(at, "A2 CTA Backtest page")
assert any("CTA 评分回测" in str(item.value) for item in at.markdown), \
    "Chinese CTA Backtest page header was not rendered"
print("3. A2 CTA Backtest page ✓")
print("ALL STREAMLIT RUNTIME TESTS PASSED ✓")
