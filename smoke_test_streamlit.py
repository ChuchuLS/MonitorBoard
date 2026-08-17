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

nav = next((widget for widget in at.sidebar.radio if widget.key == "nav_page"), None)
assert nav is not None, "Sidebar SECTION navigation was not rendered"
nav.set_value("A2 · CTA Backtest").run(timeout=180)
_assert_clean(at, "A2 CTA Backtest page")
assert any("CTA Score Backtest" in str(item.value) for item in at.markdown), \
    "CTA Backtest page header was not rendered"
print("2. A2 CTA Backtest page ✓")
print("ALL STREAMLIT RUNTIME TESTS PASSED ✓")
