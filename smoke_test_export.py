"""Optional export integration test — run separately from routine smoke tests.

Usage:
    python smoke_test_export.py
    FULL_EXPORT_SMOKE=1 python smoke_test_export.py
"""
import sys, os, time, subprocess
from pathlib import Path
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_t0 = time.time()

print("=== EXPORT INTEGRATION TEST ===\n")

# 1. Snapshot command-line entry
print("1. Snapshot CLI entry point ...")
result = subprocess.run(["python", "scripts/export_research_pack_snapshot.py"],
                        capture_output=True, text=True, timeout=120)
assert result.returncode == 0, f"snapshot script failed: {result.stderr[:400]}"
assert Path("data/snapshot.json").exists()
import json
snap_data = json.loads(Path("data/snapshot.json").read_text())
assert "index" in snap_data and "pages" in snap_data
print(f"   snapshot.json: index={snap_data['index']['level']}, {len(snap_data['pages'])} pages ✓")

# 2. Lightweight HTML export (plotly_mode=none)
print("\n2. Lightweight HTML export (plotly_mode=none) ...")
t_light = time.time()
from scripts.export_research_pack_html import build_html
html_str, filename = build_html(include_plotlyjs=False, plotly_mode="none")
elapsed_light = time.time() - t_light
assert len(html_str) > 1000
assert "Plotly.newPlot" not in html_str, "lightweight mode must not embed Plotly JS"
assert "<script>" not in html_str.split("</head>")[0], "lightweight mode must not include Plotly JS"
print(f"   lightweight: {len(html_str):,} chars in {elapsed_light:.2f}s ✓")

# 3. Complete PDF export
print("\n3. Complete linked PDF export ...")
from scripts.export_research_pack_pdf import build_pdf
pdf_bytes, pdf_name = build_pdf()
assert pdf_bytes.startswith(b"%PDF-"), "PDF signature missing"
assert len(pdf_bytes) > 50_000, "PDF export is unexpectedly small"
assert pdf_name.startswith("rates_liquidity_board_") and pdf_name.endswith(".pdf")
try:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf_bytes))
    assert len(reader.pages) == 2 + len(snap_data["pages"]), \
        "PDF must contain cover + contents + every registered Board page"
    assert reader.outline, "PDF bookmarks are missing"
    print(f"   PDF: {len(reader.pages)} pages, {len(pdf_bytes):,} bytes, bookmarks present ✓")
except ImportError:
    print(f"   PDF: {len(pdf_bytes):,} bytes ✓ (pypdf structure check skipped)")

# 4. Full inline Plotly export (opt-in via env var)
if os.environ.get("FULL_EXPORT_SMOKE") == "1":
    print("\n4. FULL inline Plotly HTML export ...")
    # Run the heavy inline build in a fresh process. Reusing the process after
    # lightweight mode can leave Plotly/module-level render state in a slow or
    # non-deterministic state in some headless environments.
    t_full = time.time()
    full_code = (
        "from scripts.export_research_pack_html import build_html; "
        "h, f = build_html(include_plotlyjs=True, plotly_mode='inline'); "
        "assert len(h) > 1000000 and 'Plotly.newPlot' in h; "
        "print(len(h))"
    )
    full_result = subprocess.run(
        ["python", "-c", full_code], capture_output=True, text=True, timeout=120
    )
    assert full_result.returncode == 0, full_result.stderr[:500]
    full_len = int(full_result.stdout.strip().splitlines()[-1])
    elapsed_full = time.time() - t_full
    print(f"   full: {full_len:,} chars in {elapsed_full:.2f}s ✓")
else:
    print("\n4. FULL inline Plotly test SKIPPED (set FULL_EXPORT_SMOKE=1 to enable)")

print(f"\nALL EXPORT TESTS PASSED ✓")
print(f"Total elapsed: {time.time() - _t0:.2f}s")
