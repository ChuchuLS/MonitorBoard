#!/usr/bin/env python3
"""Build a self-contained, reference-style PDF export of MonitorBoard.

The export deliberately reuses the production models and DATA.xlsx.  It never
fills missing observations, invents unavailable outputs, or screenshots a
single Streamlit view.  The resulting 16:9 document contains a cover, linked
contents, one page for every registered Board page, PDF bookmarks, top-section
navigation, and previous/next links.
"""
from __future__ import annotations

import io
import math
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from config.model_roadmap import ROADMAP
from config.pages import PAGES, STATUS_LABELS
from config.theme import SECTION_COLORS
from data.loader import latest_valid_date, load_data, source_signature
from index.composite import compute_index


PAGE_SIZE = (1440.0, 810.0)
PAGE_W, PAGE_H = PAGE_SIZE
MARGIN_X = 60.0

BG = "#050505"
PANEL = "#0d0d0d"
PANEL_2 = "#111111"
WHITE = "#f0f0f0"
TEXT = "#c7c7c7"
DIM = "#838383"
GRID = "#242424"
ORANGE = "#ff8a00"
GREEN = "#00d07a"
RED = "#e85d5d"
AMBER = "#f0c000"

SERIES_COLORS = [
    "#35bdf4", "#ff8a00", "#00d07a", "#b184ff", "#f0c000",
    "#ff7357", "#e51c73", "#9bd62a", "#8fb8ff", "#d99830",
]

GROUPS = [
    ("00", "LIQUIDITY", "#5fb04f", "liquidity"),
    ("01", "POLICY", "#ff8a00", "policy"),
    ("02", "DECOMP", "#35bdf4", "decomposition"),
    ("03", "REGIMES", "#f0c000", "regimes"),
    ("04", "GLOBAL", "#00d07a", "global_rates"),
    ("05", "CROSS-ASSET", "#b184ff", "cross_asset"),
    ("06", "EQUITIES", "#ff7357", "sector_rotation"),
    ("07", "FX", "#e51c73", "fx_rate_diff"),
    ("A", "APPENDIX", "#9aa0a6", "data_quality"),
]


def _hex(value: str):
    from reportlab.lib.colors import HexColor
    return HexColor(value)


def _ascii(value) -> str:
    """Keep Helvetica-safe text and normalize typographic punctuation."""
    if value is None:
        return "-"
    text = str(value)
    replacements = {
        "\u2212": "-", "\u2013": "-", "\u2014": "-", "\u2011": "-",
        "\u2192": "->", "\u2190": "<-", "\u00b7": " | ", "\u2022": "-",
        "\u0394": "chg", "\u00d7": "x", "\u2026": "...", "\u2248": "~",
        "\u2265": ">=", "\u2264": "<=", "\u03c3": "sigma", "\u00b1": "+/-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text or "-"


def _fmt(value, spec: str = ".2f", suffix: str = "") -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value):{spec}}{suffix}"
    except (TypeError, ValueError):
        return _ascii(value)


def _short(value, limit: int = 44) -> str:
    text = _ascii(value).replace("\n", " ")
    return text if len(text) <= limit else text[: max(1, limit - 3)] + "..."


def _page_group(page: dict) -> str:
    section = str(page.get("section", ""))
    if section.startswith(("08", "09", "A")):
        return "A"
    return section[:2]


def _page_color(page: dict) -> str:
    return SECTION_COLORS.get(page.get("color_key"), DIM)


class PackCanvas:
    def __init__(self, pdf: canvas.Canvas, latest_date, data_hash: str):
        self.c = pdf
        self.latest_date = latest_date
        self.data_hash = data_hash
        self.page_no = 0
        self.current_page: dict | None = None

    def text(self, x, y, value, size=10, color=TEXT, font="Helvetica",
             max_width: float | None = None):
        text = _ascii(value)
        if max_width is not None:
            while text and stringWidth(text, font, size) > max_width:
                text = text[:-1]
            if text != _ascii(value):
                text = text[:-3] + "..." if len(text) > 3 else text
        self.c.setFillColor(_hex(color))
        self.c.setFont(font, size)
        self.c.drawString(x, y, text)

    def text_right(self, x, y, value, size=10, color=TEXT,
                   font="Helvetica"):
        self.c.setFillColor(_hex(color))
        self.c.setFont(font, size)
        self.c.drawRightString(x, y, _ascii(value))

    def rect(self, x, y, w, h, fill=PANEL, stroke=GRID, line=1):
        self.c.setFillColor(_hex(fill))
        self.c.setStrokeColor(_hex(stroke))
        self.c.setLineWidth(line)
        self.c.rect(x, y, w, h, fill=1, stroke=1)

    def begin(self, page: dict):
        self.page_no += 1
        self.current_page = page
        self.c.setFillColor(_hex(BG))
        self.c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        dest = f"page_{page['id']}"
        self.c.bookmarkPage(dest)
        self.c.addOutlineEntry(_ascii(f"{page['section']} {page['title']}"), dest, level=0)

        color = _page_color(page)
        self.text(MARGIN_X, 775, "RATES & LIQUIDITY RESEARCH PACK", 8, color,
                  "Helvetica-Bold")
        self.text_right(PAGE_W - MARGIN_X, 775, "MONITORBOARD DAILY EXPORT", 8,
                        color, "Helvetica-Bold")
        self.text(MARGIN_X, 739, page["title"], 29, WHITE, "Helvetica-Bold")
        self.text(MARGIN_X, 715, page.get("description", ""), 9, DIM,
                  max_width=PAGE_W - 2 * MARGIN_X)
        self.nav(page)

        self.rect(MARGIN_X, 609, PAGE_W - 2 * MARGIN_X, 48, PANEL, color, 1)
        self.c.setFillColor(_hex(color))
        self.c.rect(MARGIN_X, 609, 5, 48, fill=1, stroke=0)
        self.text(MARGIN_X + 15, 638,
                  f"SECTION {page['section']} / CURRENT BOARD MODEL", 8, color,
                  "Helvetica-Bold")
        status = STATUS_LABELS.get(page.get("status"), page.get("status", ""))
        self.text(MARGIN_X + 15, 620,
                  f"STATUS: {status} | SOURCE: {page.get('data_source', 'DATA.xlsx')}",
                  8, TEXT, "Helvetica-Bold")
        return 585.0

    def nav(self, page: dict):
        x = MARGIN_X
        y = 674
        current = _page_group(page)
        self.rect(x, y, 34, 26, PANEL, ORANGE, 0.7)
        self.text(x + 8, y + 9, "HOME", 6.5, ORANGE, "Helvetica-Bold")
        self.c.linkAbsolute("Contents", "contents", Rect=(x, y, x + 34, y + 26))
        x += 40
        for num, label, color, dest in GROUPS:
            w = 48 + max(0, len(label) - 4) * 4.4
            active = current == num
            fill = color if active else PANEL
            fg = BG if active else color
            self.rect(x, y, w, 26, fill, color, 0.8)
            self.text(x + 7, y + 9, f"{num} {label}", 7, fg, "Helvetica-Bold")
            self.c.linkAbsolute(label, f"page_{dest}", Rect=(x, y, x + w, y + 26))
            x += w + 5

    def finish(self, previous_id: str | None, next_id: str | None):
        page = self.current_page or {}
        color = _page_color(page)
        self.c.setStrokeColor(_hex(color))
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN_X, 49, PAGE_W - MARGIN_X, 49)
        self.text(MARGIN_X, 28, "MONITORBOARD | INTERNAL RESEARCH", 7, color,
                  "Helvetica-Bold")
        date_label = self.latest_date.strftime("%B %d, %Y").upper() if self.latest_date else "DATE UNAVAILABLE"
        self.text_right(PAGE_W - MARGIN_X, 28,
                        f"{date_label} | PAGE {self.page_no} | HASH {self.data_hash[:12]}",
                        7, color, "Helvetica-Bold")
        if previous_id:
            self.text(MARGIN_X, 61, "< PREVIOUS", 7, DIM, "Helvetica-Bold")
            self.c.linkAbsolute("Previous", f"page_{previous_id}",
                                Rect=(MARGIN_X, 55, MARGIN_X + 75, 72))
        if next_id:
            self.text_right(PAGE_W - MARGIN_X, 61, "NEXT >", 7, color,
                            "Helvetica-Bold")
            self.c.linkAbsolute("Next", f"page_{next_id}",
                                Rect=(PAGE_W - MARGIN_X - 75, 55,
                                      PAGE_W - MARGIN_X, 72))
        self.c.showPage()

    def kpis(self, cards: list[dict], y=530, x=MARGIN_X,
             width=PAGE_W - 2 * MARGIN_X, height=58):
        if not cards:
            return y
        gap = 10
        w = (width - gap * (len(cards) - 1)) / len(cards)
        for i, card in enumerate(cards):
            cx = x + i * (w + gap)
            accent = card.get("accent", GRID)
            self.rect(cx, y, w, height, PANEL, GRID, 0.7)
            self.c.setFillColor(_hex(accent))
            self.c.rect(cx, y + height - 3, w, 3, fill=1, stroke=0)
            self.text(cx + 12, y + 39, card.get("label", ""), 7, DIM,
                      "Helvetica-Bold", w - 24)
            self.text(cx + 12, y + 18, card.get("value", "-"), 17,
                      card.get("value_color", WHITE), "Helvetica-Bold", w - 24)
            if card.get("sub"):
                self.text(cx + 12, y + 7, card["sub"], 6.5, DIM,
                          max_width=w - 24)
        return y - 16

    def heading(self, x, y, value, color=ORANGE):
        self.text(x, y, value, 9, color, "Helvetica-Bold")
        self.c.setStrokeColor(_hex(color))
        self.c.setLineWidth(0.6)
        self.c.line(x, y - 5, x + 260, y - 5)

    def note(self, x, y, w, h, title, body, color=ORANGE):
        self.rect(x, y, w, h, PANEL, color, 0.8)
        self.c.setFillColor(_hex(color))
        self.c.rect(x, y, 4, h, fill=1, stroke=0)
        self.text(x + 14, y + h - 19, title, 8, color, "Helvetica-Bold")
        words = _ascii(body).split()
        line = ""
        ty = y + h - 38
        for word in words:
            trial = f"{line} {word}".strip()
            if stringWidth(trial, "Helvetica", 8) <= w - 28:
                line = trial
            else:
                self.text(x + 14, ty, line, 8, TEXT)
                ty -= 13
                line = word
                if ty < y + 12:
                    break
        if line and ty >= y + 12:
            self.text(x + 14, ty, line, 8, TEXT)

    def table(self, x, y, w, rows: Iterable, columns: list[tuple],
              max_rows=12, row_h=22, title: str | None = None,
              color=ORANGE):
        """Draw a compact table. columns are (key, label, width_share)."""
        if title:
            self.heading(x, y, title, color)
            y -= 18
        if isinstance(rows, pd.DataFrame):
            records = rows.to_dict("records")
        else:
            records = list(rows or [])
        records = records[:max_rows]
        widths = [w * float(col[2]) for col in columns]
        total = sum(widths) or 1
        widths = [v * w / total for v in widths]
        self.c.setFillColor(_hex(PANEL_2))
        self.c.rect(x, y - row_h, w, row_h, fill=1, stroke=0)
        cx = x
        for (_, label, _), cw in zip(columns, widths):
            self.text(cx + 7, y - 14, label, 7, color, "Helvetica-Bold", cw - 12)
            cx += cw
        y -= row_h
        for ridx, row in enumerate(records):
            if ridx % 2 == 0:
                self.c.setFillColor(_hex(PANEL))
                self.c.rect(x, y - row_h, w, row_h, fill=1, stroke=0)
            self.c.setStrokeColor(_hex(GRID))
            self.c.setLineWidth(0.3)
            self.c.line(x, y - row_h, x + w, y - row_h)
            cx = x
            for cidx, (key, _label, _share) in enumerate(columns):
                value = row.get(key, "-") if isinstance(row, dict) else "-"
                cw = widths[cidx]
                self.text(cx + 7, y - 14, _short(value, 38), 7.5, TEXT,
                          max_width=cw - 12 if cw else 20)
                cx += cw
            y -= row_h
        if not records:
            self.text(x + 7, y - 15, "No verified data available for this table.",
                      8, DIM)
            y -= row_h
        return y

    def line_chart(self, x, y, w, h, frame, title, color=ORANGE,
                   max_series=8, normalize=False, last_n=None):
        self.heading(x, y + h + 18, title, color)
        self.rect(x, y, w, h, BG, GRID, 0.6)
        if isinstance(frame, pd.Series):
            frame = frame.to_frame(frame.name or "Series")
        if frame is None or frame.empty:
            self.text(x + 14, y + h / 2, "No verified observations available.",
                      8, DIM)
            return
        data = frame.copy()
        if last_n:
            data = data.tail(last_n)
        data = data.apply(pd.to_numeric, errors="coerce")
        if normalize:
            for col in data.columns:
                s = data[col].dropna()
                if len(s) and float(s.iloc[0]) != 0:
                    data[col] = 100 * data[col] / float(s.iloc[0])
        cols = [c for c in data.columns if data[c].notna().any()][:max_series]
        if not cols:
            self.text(x + 14, y + h / 2, "No verified observations available.", 8, DIM)
            return
        vals = np.concatenate([data[c].dropna().to_numpy(float) for c in cols])
        lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
        if not np.isfinite(lo) or not np.isfinite(hi):
            return
        if math.isclose(lo, hi):
            lo -= 1.0
            hi += 1.0
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad
        for i in range(4):
            gy = y + 12 + i * (h - 24) / 3
            self.c.setStrokeColor(_hex(GRID))
            self.c.setLineWidth(0.3)
            self.c.line(x + 8, gy, x + w - 8, gy)
            v = lo + i * (hi - lo) / 3
            self.text(x + 10, gy + 3, _fmt(v, ".2f"), 6, DIM)
        n = max(1, len(data) - 1)
        for ci, col in enumerate(cols):
            cval = SERIES_COLORS[ci % len(SERIES_COLORS)]
            self.c.setStrokeColor(_hex(cval))
            self.c.setLineWidth(1.1)
            path = self.c.beginPath()
            pen_down = False
            for idx, value in enumerate(data[col].to_numpy()):
                if pd.isna(value):
                    pen_down = False
                    continue
                px = x + 8 + idx / n * (w - 16)
                py = y + 12 + (float(value) - lo) / (hi - lo) * (h - 24)
                if pen_down:
                    path.lineTo(px, py)
                else:
                    path.moveTo(px, py)
                    pen_down = True
            self.c.drawPath(path, stroke=1, fill=0)
            lx = x + 12 + (ci % 4) * (w - 24) / 4
            ly = y + h - 13 - (ci // 4) * 12
            self.c.setFillColor(_hex(cval))
            self.c.rect(lx, ly - 2, 7, 2, fill=1, stroke=0)
            self.text(lx + 10, ly - 4, _short(col, 18), 6.5, cval, "Helvetica-Bold")


def _cover(p: PackCanvas, index_result):
    p.page_no += 1
    c = p.c
    c.setFillColor(_hex(BG)); c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.bookmarkPage("cover")
    c.addOutlineEntry("Cover", "cover", level=0)
    p.text(MARGIN_X, 748, "MONITORBOARD RESEARCH", 10, ORANGE, "Helvetica-Bold")
    c.setFillColor(_hex(ORANGE)); c.rect(MARGIN_X, 724, 48, 4, fill=1, stroke=0)
    c.setFillColor(_hex(ORANGE)); c.rect(MARGIN_X, 410, 10, 80, fill=1, stroke=0)
    p.text(MARGIN_X + 30, 432, "RATES & LIQUIDITY MODELS", 52, WHITE,
           "Helvetica-Bold")
    latest = p.latest_date.strftime("%B %d, %Y").upper() if p.latest_date else "DATE UNAVAILABLE"
    p.text(MARGIN_X + 30, 365, latest, 28, ORANGE, "Helvetica-Bold")
    p.text(MARGIN_X + 30, 330,
           "CURRENT BOARD MODELS GENERATED FROM VERIFIED DATA.XLSX INPUTS",
           9, TEXT, "Helvetica-Bold")
    p.text(MARGIN_X + 30, 294,
           f"COMPOSITE LIQUIDITY INDEX {_fmt(index_result.latest, '.1f')} | {index_result.latest_regime}",
           12, WHITE, "Helvetica-Bold")
    c.setStrokeColor(_hex(ORANGE)); c.setLineWidth(0.5)
    c.line(MARGIN_X, 145, PAGE_W - MARGIN_X, 145)
    x = MARGIN_X
    for num, label, color, _ in GROUPS:
        p.text(x, 112, num, 7, color, "Helvetica-Bold")
        p.text(x + 18, 112, label, 7, TEXT, "Helvetica-Bold")
        x += 135
    p.text(MARGIN_X, 45, f"DATA HASH {p.data_hash[:16]}", 7, ORANGE,
           "Helvetica-Bold")
    p.text_right(PAGE_W - MARGIN_X, 45, "MONITORBOARD DAILY EXPORT", 7,
                 ORANGE, "Helvetica-Bold")
    c.showPage()


def _contents(p: PackCanvas):
    p.page_no += 1
    c = p.c
    c.setFillColor(_hex(BG)); c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.bookmarkPage("contents")
    c.addOutlineEntry("Contents", "contents", level=0)
    p.text(MARGIN_X, 746, "CONTENTS", 27, ORANGE, "Helvetica-Bold")
    p.text(MARGIN_X, 721,
           "Every row is a link. PDF bookmarks and page navigation are also enabled.",
           9, TEXT)
    y = 676
    col_w = (PAGE_W - 2 * MARGIN_X - 28) / 2
    for idx, page in enumerate(PAGES):
        col = 0 if idx < math.ceil(len(PAGES) / 2) else 1
        row = idx if col == 0 else idx - math.ceil(len(PAGES) / 2)
        x = MARGIN_X + col * (col_w + 28)
        cy = y - row * 62
        color = _page_color(page)
        p.rect(x, cy - 44, col_w, 48, PANEL, GRID, 0.6)
        c.setFillColor(_hex(color)); c.rect(x, cy - 44, 4, 48, fill=1, stroke=0)
        p.text(x + 14, cy - 11, page["section"], 10, color, "Helvetica-Bold")
        p.text(x + 62, cy - 11, page["title"], 10, WHITE, "Helvetica-Bold",
               col_w - 150)
        status = STATUS_LABELS.get(page.get("status"), page.get("status", ""))
        p.text_right(x + col_w - 12, cy - 11, status, 7, color, "Helvetica-Bold")
        p.text(x + 62, cy - 29, page.get("description", ""), 7, DIM,
               max_width=col_w - 82)
        c.linkAbsolute(page["title"], f"page_{page['id']}",
                       Rect=(x, cy - 44, x + col_w, cy + 4))
    c.setStrokeColor(_hex(ORANGE)); c.line(MARGIN_X, 49, PAGE_W - MARGIN_X, 49)
    p.text(MARGIN_X, 28, "MONITORBOARD | LINKED RESEARCH PACK", 7, ORANGE,
           "Helvetica-Bold")
    p.text_right(PAGE_W - MARGIN_X, 28, f"PAGE {p.page_no}", 7, ORANGE,
                 "Helvetica-Bold")
    c.showPage()


def _liquidity(p: PackCanvas, df, r):
    changes = r.changes()
    p.kpis([
        {"label": "COMPOSITE LIQUIDITY", "value": _fmt(r.latest, ".1f"),
         "sub": r.latest_regime, "accent": GREEN},
        {"label": "1 WEEK CHANGE", "value": _fmt(changes.get("1w"), "+.1f", " pts")},
        {"label": "1 MONTH CHANGE", "value": _fmt(changes.get("1m"), "+.1f", " pts")},
        {"label": "3 MONTH CHANGE", "value": _fmt(changes.get("3m"), "+.1f", " pts")},
    ])
    p.line_chart(MARGIN_X, 280, 860, 210, r.index.dropna(),
                 "COMPOSITE LIQUIDITY INDEX - PUBLISHED HISTORY", GREEN,
                 max_series=1, last_n=756)
    rows = []
    try:
        levels = r.level_contributions()
        rows = [{"bucket": k, "contribution": _fmt(v, "+.2f")}
                for k, v in levels.items()]
    except Exception:
        pass
    p.table(960, 472, 420, rows,
            [("bucket", "BUCKET", .65), ("contribution", "CONTRIBUTION", .35)],
            max_rows=8, title="CURRENT BUCKET CONTRIBUTIONS", color=GREEN)
    p.note(960, 280, 420, 140, "MODEL NOTE",
           "Rolling z-score composite across five buckets. 50 is neutral and higher values indicate looser conditions. Publication remains coverage-gated; missing inputs are not replaced with zero.", GREEN)


def _policy(p: PackCanvas, df):
    from models.policy_short_rates import (
        build_funding_pressure_score, build_funding_pressure_table,
        build_policy_spreads, build_short_rate_snapshot,
    )
    pressure = build_funding_pressure_score(df)
    snap = build_short_rate_snapshot(df)
    p.kpis([
        {"label": "FUNDING PRESSURE Z", "value": _fmt(pressure.get("score"), "+.2f"),
         "sub": pressure.get("status", "-"), "accent": ORANGE},
        {"label": "INCLUDED SPREADS", "value": pressure.get("n_spreads", 0)},
        {"label": "LATEST PRESSURE DATE", "value": pressure.get("latest_date", "-")},
        {"label": "DATES ALIGNED", "value": "YES" if pressure.get("dates_aligned") else "NO"},
    ])
    disp = snap.copy()
    if not disp.empty:
        disp["level"] = disp["latest_pct"].map(lambda v: _fmt(v, ".3f", "%"))
        disp["chg"] = disp["1m_change_bp"].map(lambda v: _fmt(v, "+.1f", " bp"))
        disp["date"] = disp["latest_valid_date"].astype(str)
    p.table(MARGIN_X, 474, 650, disp,
            [("indicator", "RATE", .32), ("level", "LEVEL", .20),
             ("chg", "1M CHANGE", .22), ("date", "VALID DATE", .26)],
            max_rows=10, title="CONFIRMED POLICY AND FUNDING RATES", color=ORANGE)
    spreads = build_policy_spreads(df)
    p.line_chart(750, 280, 630, 195, spreads.tail(252),
                 "SPREADS TO IORB - BASIS POINTS", ORANGE, max_series=6)
    ftable = build_funding_pressure_table(df)
    if not ftable.empty:
        ftable = ftable.assign(
            spread=ftable["Latest_bp"].map(lambda v: _fmt(v, "+.1f")),
            z=ftable["ZScore_1Y"].map(lambda v: _fmt(v, "+.2f")),
        )
    p.table(MARGIN_X, 205, 650, ftable,
            [("Indicator", "SPREAD", .42), ("spread", "BP", .18),
             ("z", "1Y Z", .18), ("Status", "STATUS", .22)],
            max_rows=6, title="PRESSURE DIAGNOSTICS", color=ORANGE)


def _policy_futures(p: PackCanvas, df):
    from data.policy_futures_loader import load_policy_futures
    from models.policy_futures_strip import build_sofr_strip_snapshot
    snap = build_sofr_strip_snapshot(load_policy_futures(), df)
    terminal = snap.get("terminal") or {}
    p.kpis([
        {"label": "EFFR", "value": _fmt(snap.get("effr_pct"), ".3f", "%"), "accent": ORANGE},
        {"label": "SOFR", "value": _fmt(snap.get("sofr_pct"), ".3f", "%")},
        {"label": "TERMINAL", "value": _fmt(terminal.get("terminal_rate_pct"), ".3f", "%"),
         "sub": terminal.get("terminal_contract", "-")},
        {"label": "EFFR TO TERMINAL", "value": _fmt(terminal.get("terminal_gap_bp"), "+.1f", " bp")},
    ])
    hist = snap.get("implied_rate_history")
    p.line_chart(MARGIN_X, 280, 810, 210, hist.tail(260) if isinstance(hist, pd.DataFrame) else hist,
                 "FIXED QUARTERLY SOFR IMPLIED RATES", ORANGE, max_series=8)
    table = snap.get("strip_table", pd.DataFrame()).copy()
    if not table.empty:
        table["contract"] = table["contract_label"]
        table["rate"] = table["implied_rate_pct"].map(lambda v: _fmt(v, ".3f", "%"))
        table["d1"] = table["change_1d_bp"].map(lambda v: _fmt(v, "+.1f"))
        table["d20"] = table["change_20d_bp"].map(lambda v: _fmt(v, "+.1f"))
    p.table(910, 478, 470, table,
            [("contract", "CONTRACT", .30), ("rate", "RATE", .26),
             ("d1", "1D BP", .20), ("d20", "20D BP", .24)],
            max_rows=8, title="CURRENT STRIP", color=ORANGE)
    p.note(910, 280, 470, 130, "LIMITATION",
           "These are eight actual fixed quarterly Three-Month SOFR contracts. The page is not a meeting-by-meeting FOMC probability path and must not be read as one.", ORANGE)


def _decomposition(p: PackCanvas, df):
    from models.rate_decomposition import build_us_curve_snapshot
    snap = build_us_curve_snapshot(df)
    ten = snap.loc[snap["tenor"] == "10Y"] if not snap.empty else pd.DataFrame()
    row = ten.iloc[0] if not ten.empty else {}
    p.kpis([
        {"label": "10Y NOMINAL", "value": _fmt(row.get("nominal"), ".2f", "%"), "accent": "#35bdf4"},
        {"label": "10Y REAL", "value": _fmt(row.get("real"), ".2f", "%")},
        {"label": "10Y INFLATION", "value": _fmt(row.get("inflation"), ".2f", "%")},
        {"label": "1M DRIVER", "value": row.get("driver_1m", "-")},
    ])
    disp = snap.copy()
    if not disp.empty:
        for col in ["nominal", "real", "inflation"]:
            disp[col] = disp[col].map(lambda v: _fmt(v, ".2f", "%"))
        for col in ["nominal_1m_change_bp", "real_1m_change_bp", "inflation_1m_change_bp"]:
            disp[col] = disp[col].map(lambda v: _fmt(v, "+.1f", " bp"))
    p.table(MARGIN_X, 478, 850, disp,
            [("tenor", "TENOR", .10), ("nominal", "NOMINAL", .15),
             ("real", "REAL", .15), ("inflation", "INFLATION", .16),
             ("nominal_1m_change_bp", "NOM 1M", .14),
             ("real_1m_change_bp", "REAL 1M", .14),
             ("inflation_1m_change_bp", "INFL 1M", .16)],
            max_rows=6, title="US CURVE COMPLEX", color="#35bdf4")
    p.note(950, 335, 430, 155, "IDENTITY",
           "Nominal yield equals real yield plus inflation compensation at each tenor. The decomposition residual is zero by construction. Inputs are aligned on common dates with no proxy substitution.", "#35bdf4")
    # Plot the four latest components as a compact tenor profile.
    if not snap.empty:
        chart = snap.set_index("tenor")[["nominal", "real", "inflation"]]
        p.line_chart(MARGIN_X, 225, 850, 145, chart, "CURRENT TENOR PROFILE", "#35bdf4")


def _regimes(p: PackCanvas, df):
    from models.curve_regimes import build_regime_matrix, classify_pair_history
    matrix = build_regime_matrix(df, window=10)
    p.kpis([
        {"label": "WINDOW", "value": "10 OBS", "accent": AMBER},
        {"label": "CURVE TYPES", "value": "3"},
        {"label": "TENOR PAIRS", "value": "6"},
        {"label": "CLASSIFICATIONS", "value": "7"},
    ])
    rows = []
    for idx, r in matrix.iterrows():
        item = {"curve": idx}
        item.update({str(k): v for k, v in r.items()})
        rows.append(item)
    cols = [("curve", "CURVE", .13)] + [(c, c.upper(), .145) for c in matrix.columns]
    p.table(MARGIN_X, 474, 900, rows, cols, max_rows=3,
            title="CURRENT REGIME MATRIX", color=AMBER, row_h=36)
    try:
        hist = classify_pair_history(df, "nominal", ("2Y", "10Y"), 10)
        counts = hist["regime"].value_counts().reset_index()
        counts.columns = ["regime", "days"]
    except Exception:
        counts = pd.DataFrame()
    p.table(1010, 474, 370, counts,
            [("regime", "NOMINAL 2S10S", .70), ("days", "DAYS", .30)],
            max_rows=7, title="HISTORY FREQUENCY", color=AMBER)
    p.note(MARGIN_X, 240, 900, 120, "READING RULE",
           "The sign of front-end and back-end changes identifies bull, bear, steepener, flattener, twist or neutral regimes. The labels are descriptive classifications, not forecasts.", AMBER)


def _global_rates(p: PackCanvas, df):
    from models.global_rates import build_10y_overlay, build_slope_ranking, country_1m_changes
    overlay = build_10y_overlay(df)
    slopes = build_slope_ranking(df)
    changes = country_1m_changes(df)
    top = changes.iloc[0] if not changes.empty else {}
    bottom = changes.iloc[-1] if not changes.empty else {}
    p.kpis([
        {"label": "TOP 1M RISER", "value": top.get("label", "-"),
         "sub": _fmt(top.get("change_1m_bp"), "+.1f", " bp"), "accent": GREEN},
        {"label": "TOP 1M FALLER", "value": bottom.get("label", "-"),
         "sub": _fmt(bottom.get("change_1m_bp"), "+.1f", " bp")},
        {"label": "MARKETS", "value": len(slopes)},
        {"label": "FORWARD-FILL", "value": "NONE"},
    ])
    p.line_chart(MARGIN_X, 270, 820, 220, overlay, "GLOBAL 10Y NORMALIZED OVERLAY", GREEN,
                 max_series=7, last_n=258)
    rows = slopes.merge(changes[["country", "change_1m_bp"]], on="country", how="left")
    if not rows.empty:
        rows["yield"] = rows["10Y"].map(lambda v: _fmt(v, ".2f", "%"))
        rows["slope"] = rows["slope_bp"].map(lambda v: _fmt(v, "+.1f", " bp"))
        rows["chg"] = rows["change_1m_bp"].map(lambda v: _fmt(v, "+.1f", " bp"))
    p.table(930, 478, 450, rows,
            [("label", "COUNTRY", .36), ("yield", "10Y", .20),
             ("chg", "1M", .22), ("slope", "2S10S", .22)],
            max_rows=7, title="GLOBAL SNAPSHOT", color=GREEN)
    p.note(930, 270, 450, 120, "DATA INTEGRITY",
           "The overlay draws only genuine observations. Missing market sessions remain missing; no forward-fill is applied.", GREEN)


def _country_boards(p: PackCanvas, df):
    from config.tickers import REGIME_COUNTRIES
    from models.country_rate_boards import build_global_country_board_overview
    from models.global_rate_decomposition import (
        build_global_decomposition_snapshot, global_decomposition_readiness,
    )
    overview = build_global_country_board_overview(df, horizon=20)
    p.kpis([
        {"label": "COMMON MODEL DATE", "value": overview["model_date"].iloc[0] if not overview.empty else "-", "accent": GREEN},
        {"label": "COUNTRIES", "value": len(overview)},
        {"label": "NOMINAL TENORS", "value": "2Y / 5Y / 10Y / 30Y"},
        {"label": "PROXY SERIES", "value": "NONE"},
    ])
    rows = overview.copy()
    if not rows.empty:
        rows["y2"] = rows["yield_2y_pct"].map(lambda v: _fmt(v, ".2f", "%"))
        rows["y10"] = rows["yield_10y_pct"].map(lambda v: _fmt(v, ".2f", "%"))
        rows["y30"] = rows["yield_30y_pct"].map(lambda v: _fmt(v, ".2f", "%"))
        rows["chg"] = rows["change_20d_10y_bp"].map(lambda v: _fmt(v, "+.1f"))
        rows["slope"] = rows["slope_2s10s_bp"].map(lambda v: _fmt(v, "+.1f"))
    p.table(MARGIN_X, 478, 790, rows,
            [("label", "COUNTRY", .28), ("y2", "2Y", .14), ("y10", "10Y", .14),
             ("y30", "30Y", .14), ("chg", "20D 10Y BP", .16),
             ("slope", "2S10S BP", .14)], max_rows=7,
            title="ALIGNED NOMINAL COUNTRY BOARDS", color=GREEN)
    decomp = []
    for country in REGIME_COUNTRIES:
        table = build_global_decomposition_snapshot(df, country, horizons=(20,))
        if table.empty:
            continue
        selected = table.loc[table["tenor"] == "10Y"]
        row = selected.iloc[0] if not selected.empty else table.iloc[0]
        decomp.append({
            "country": row["label"], "tenor": row["tenor"],
            "nom": _fmt(row["nominal_pct"], ".2f", "%"),
            "real": _fmt(row["real_pct"], ".2f", "%"),
            "infl": _fmt(row["inflation_pct"], ".2f", "%"),
        })
    readiness = global_decomposition_readiness(df, REGIME_COUNTRIES)
    unavailable = readiness.loc[readiness["status"] != "Ready", "label"].astype(str).tolist()
    p.table(900, 478, 480, decomp,
            [("country", "COUNTRY", .32), ("tenor", "TENOR", .15),
             ("nom", "NOM", .18), ("real", "REAL", .17), ("infl", "INFL", .18)],
            max_rows=7, title="EXACT-TENOR ATTRIBUTION", color=GREEN)
    p.note(900, 250, 480, 120, "UNAVAILABLE INPUTS",
           "Unavailable: " + (", ".join(unavailable) if unavailable else "None") + ". Same-market, same-tenor real yields are required; no cross-country proxy is used.", GREEN)


def _cross_asset(p: PackCanvas, df):
    from data.external_loaders import load_crossasset
    from models.cross_asset.directional import REGIMES_8, classify_8regime, days_in_current_regime
    result = classify_8regime(load_crossasset())
    last = result.iloc[-1] if not result.empty else {}
    regime = last.get("regime", "-")
    info = REGIMES_8.get(regime, {"label": "Unavailable", "color": DIM})
    p.kpis([
        {"label": "CURRENT REGIME", "value": info.get("label", regime),
         "sub": f"{regime} | {days_in_current_regime(result['regime']) if not result.empty else 0} days",
         "accent": info.get("color", "#b184ff")},
        {"label": "SPX SIGNAL", "value": _fmt(last.get("spx_signal"), "+.2f")},
        {"label": "RATES SIGNAL", "value": _fmt(last.get("rates_signal"), "+.2f")},
        {"label": "DXY SIGNAL", "value": _fmt(last.get("dxy_signal"), "+.2f")},
    ])
    signals = result[["spx_signal", "rates_signal", "dxy_signal"]] if not result.empty else pd.DataFrame()
    p.line_chart(MARGIN_X, 280, 840, 210, signals.tail(252),
                 "VOL-SCALED DIRECTIONAL SIGNALS", "#b184ff", max_series=3)
    freq = result["regime"].value_counts().reindex([f"R{i}" for i in range(1, 9)], fill_value=0)
    rows = [{"regime": k, "label": REGIMES_8[k]["label"], "days": int(v),
             "share": _fmt(100 * v / len(result), ".1f", "%")}
            for k, v in freq.items()] if len(result) else []
    p.table(940, 478, 440, rows,
            [("regime", "ID", .12), ("label", "REGIME", .48),
             ("days", "DAYS", .18), ("share", "SHARE", .22)],
            max_rows=8, title="REGIME FREQUENCY", color="#b184ff")
    p.note(940, 260, 440, 115, "METHOD",
           "20-day change divided by trailing 21-day volatility. The sign of SPX, UST 10Y and DXY signals defines one of eight directional states.", "#b184ff")


def _market_linkage(p: PackCanvas, df):
    from data.external_loaders import load_ficc
    from models.market_linkage import build_market_linkage_snapshot
    snap = build_market_linkage_snapshot(load_ficc(), corr_window=20, long_window=63)
    pos = snap.get("strongest_positive") or {}
    neg = snap.get("strongest_negative") or {}
    p.kpis([
        {"label": "PC1 EXPLAINED VARIANCE", "value": _fmt(100 * snap.get("pc1_explained_variance", np.nan), ".1f", "%"), "accent": "#b184ff"},
        {"label": "2Y PERCENTILE", "value": _fmt(snap.get("linkage_percentile_2y"), ".1f", "%")},
        {"label": "STRONGEST POSITIVE", "value": pos.get("label", "-"), "sub": _fmt(pos.get("correlation"), "+.3f")},
        {"label": "STRONGEST NEGATIVE", "value": neg.get("label", "-"), "sub": _fmt(neg.get("correlation"), "+.3f")},
    ])
    p.line_chart(MARGIN_X, 305, 650, 185, snap.get("linkage_history"),
                 "ROLLING PC1 EXPLAINED VARIANCE", "#b184ff", max_series=1, last_n=504)
    p.line_chart(730, 305, 650, 185, snap.get("correlation_history"),
                 "20D PAIRWISE CORRELATIONS", "#b184ff", max_series=3, last_n=504)
    matrix = snap.get("correlation_matrix", pd.DataFrame())
    rows = []
    if isinstance(matrix, pd.DataFrame) and not matrix.empty:
        for idx, row in matrix.iterrows():
            rows.append({"asset": idx, **{str(k): _fmt(v, "+.3f") for k, v in row.items()}})
    cols = [("asset", "ASSET", .25)] + [(str(c), str(c).upper(), .25) for c in matrix.columns] if isinstance(matrix, pd.DataFrame) else []
    p.table(MARGIN_X, 235, 650, rows, cols or [("asset", "ASSET", 1)], max_rows=3,
            title="LATEST CORRELATION MATRIX", color="#b184ff")
    p.note(730, 125, 650, 110, "INTERPRETATION LIMIT",
           "This is a descriptive one-trade linkage gauge for SPX, UST 10Y and DXY. It is not causal attribution and is not a forecast.", "#b184ff")


def _sector_rotation(p: PackCanvas, df):
    from data.external_loaders import load_spx_sector_weights
    from models.sector_rotation import build_sector_current_reading
    snap = build_sector_current_reading(df, load_spx_sector_weights())
    p.kpis([
        {"label": "POSITIVE BREADTH", "value": _fmt(snap.get("positive_breadth_pct"), ".1f", "%"), "accent": "#ff7357"},
        {"label": "OUTPERFORM BREADTH", "value": _fmt(snap.get("relative_breadth_pct"), ".1f", "%")},
        {"label": "DISPERSION", "value": _fmt(snap.get("dispersion_pct"), ".2f", "%")},
        {"label": "AVAILABLE SECTORS", "value": f"{snap.get('available_sector_count', 0)}/{snap.get('configured_sector_count', 11)}"},
    ])
    per = pd.DataFrame(snap.get("per_sector", []))
    if not per.empty:
        for source, target in [("ret_20d_pct", "abs20"), ("rel_ret_20d_pct", "rel20"),
                               ("rel_ret_63d_pct", "rel63")]:
            per[target] = per[source].map(lambda v: _fmt(v, "+.2f", "%")) if source in per else "-"
        per = per.sort_values("rel_ret_20d_pct", ascending=False)
    p.table(MARGIN_X, 478, 840, per,
            [("display_name", "SECTOR", .38), ("abs20", "20D ABS", .18),
             ("rel20", "20D REL", .18), ("rel63", "63D REL", .18),
             ("quadrant", "QUADRANT", .24)], max_rows=11,
            title="SECTOR ROTATION SNAPSHOT", color="#ff7357")
    qrows = [{"quadrant": k, "count": v} for k, v in (snap.get("quadrant_counts") or {}).items()]
    p.table(950, 478, 430, qrows,
            [("quadrant", "QUADRANT", .72), ("count", "COUNT", .28)],
            max_rows=6, title="ROTATION QUADRANTS", color="#ff7357")
    p.note(950, 260, 430, 120, "LIMITATION",
           "Descriptive monitor using 11 S&P 500 sector indices. Sector weights are context only and must not be described as investor flows or official return attribution.", "#ff7357")


def _sector_contribution(p: PackCanvas, df):
    from data.external_loaders import load_spx_sector_weights
    from models.sector_contribution import build_sector_contribution_summary
    summary = build_sector_contribution_summary(df, load_spx_sector_weights())
    row20 = summary.loc[summary["horizon"] == 20]
    row = row20.iloc[0] if not row20.empty else (summary.iloc[-1] if not summary.empty else {})
    p.kpis([
        {"label": "HORIZON", "value": f"{row.get('horizon', '-')}D", "accent": "#ff7357"},
        {"label": "ACTUAL SPX RETURN", "value": _fmt(row.get("actual_spx_return_pct"), "+.2f", "%")},
        {"label": "ESTIMATED RETURN", "value": _fmt(row.get("estimated_spx_return_pct"), "+.2f", "%")},
        {"label": "RESIDUAL", "value": _fmt(row.get("residual_pp"), "+.3f", " pp")},
    ])
    rows = summary.copy()
    if not rows.empty:
        rows["h"] = rows["horizon"].map(lambda v: f"{int(v)}D")
        rows["actual"] = rows["actual_spx_return_pct"].map(lambda v: _fmt(v, "+.2f", "%"))
        rows["estimated"] = rows["estimated_spx_return_pct"].map(lambda v: _fmt(v, "+.2f", "%"))
        rows["residual"] = rows["residual_pp"].map(lambda v: _fmt(v, "+.3f", " pp"))
        rows["dates"] = rows.apply(lambda r: f"{r['start_date']} to {r['end_date']}", axis=1)
    p.table(MARGIN_X, 470, 870, rows,
            [("h", "HORIZON", .13), ("dates", "PERIOD", .30),
             ("actual", "ACTUAL", .18), ("estimated", "ESTIMATE", .20),
             ("residual", "RESIDUAL", .19)], max_rows=6,
            title="SPX SECTOR CONTRIBUTION RECONCILIATION", color="#ff7357", row_h=34)
    p.note(970, 325, 410, 165, "ESTIMATE - NOT OFFICIAL ATTRIBUTION",
           "The estimate multiplies the latest periodic sector weight available on or before each window start by each sector's simple return. The residual reconciles the estimate to the actual SPX return. This is not divisor-consistent official index-provider attribution.", "#ff7357")


def _earnings(p: PackCanvas, df):
    from data.equity_earnings_loader import load_equity_earnings_data
    from models.earnings_valuation import build_earnings_valuation_snapshot
    snap = build_earnings_valuation_snapshot(load_equity_earnings_data())
    p.kpis([
        {"label": "SPX LEVEL", "value": _fmt(snap.get("price"), ",.2f"), "accent": "#ff7357"},
        {"label": "FY1 EPS", "value": _fmt(snap.get("eps_fy1"), ".2f")},
        {"label": "IMPLIED FY1 P/E", "value": _fmt(snap.get("fy1_pe"), ".2f", "x")},
        {"label": "4W DRIVER", "value": snap.get("current_driver", "-")},
    ])
    frame = snap.get("frame", pd.DataFrame())
    p.line_chart(MARGIN_X, 300, 720, 190,
                 frame[["price", "eps_fy1"]] if isinstance(frame, pd.DataFrame) and not frame.empty else frame,
                 "SPX LEVEL AND FY1 EPS - NORMALIZED", "#ff7357", max_series=2,
                 normalize=True)
    p.line_chart(820, 300, 560, 190,
                 frame["fy1_pe"] if isinstance(frame, pd.DataFrame) and "fy1_pe" in frame else pd.Series(dtype=float),
                 "IMPLIED FY1 P/E", "#ff7357", max_series=1)
    decomp = snap.get("decomposition", pd.DataFrame()).copy()
    if not decomp.empty:
        decomp["h"] = decomp["horizon_weeks"].map(lambda v: f"{int(v)}W")
        for src, tgt in [("price_return_pct", "ret"), ("eps_growth_pct", "eps"),
                         ("valuation_change_pct", "val"), ("identity_residual_pct", "res")]:
            decomp[tgt] = decomp[src].map(lambda v: _fmt(v, "+.2f", "%"))
    p.table(MARGIN_X, 230, 870, decomp,
            [("h", "HORIZON", .12), ("ret", "SPX RETURN", .22),
             ("eps", "EPS GROWTH", .22), ("val", "P/E CHANGE", .22),
             ("res", "RESIDUAL", .22)], max_rows=4,
            title="EXACT LOG-RETURN DECOMPOSITION", color="#ff7357")
    p.note(970, 125, 410, 130, "MODEL LIMIT",
           "FY1 EPS uses BEST_EPS with 1FY override at weekly frequency. The decomposition is an accounting identity. The OLS diagnostic is not fair value and is not a forecast.", "#ff7357")


def _fx(p: PackCanvas, df):
    from models.fx_rate_differential import build_all_fx_snapshots, build_fx_pair_data
    overview = build_all_fx_snapshots(df)
    ready = int((overview["Status"] == "Ready").sum()) if not overview.empty else 0
    p.kpis([
        {"label": "READY PAIRS", "value": f"{ready}/4", "accent": "#e51c73"},
        {"label": "EURUSD", "value": overview.loc[overview["Pair"] == "EURUSD", "Spot"].iloc[0] if ready else "-"},
        {"label": "USDJPY", "value": overview.loc[overview["Pair"] == "USDJPY", "Spot"].iloc[0] if ready else "-"},
        {"label": "MODEL TYPE", "value": "DESCRIPTIVE"},
    ])
    p.table(MARGIN_X, 478, 850, overview,
            [("Pair", "PAIR", .10), ("Spot", "SPOT", .15),
             ("20D ret (%)", "20D RETURN", .15), ("2Y diff (bp)", "2Y DIFF", .15),
             ("10Y diff (bp)", "10Y DIFF", .15), ("10Y real (bp)", "REAL 10Y", .15),
             ("Status", "STATUS", .15)], max_rows=4,
            title="FX RATE-DIFFERENTIAL OVERVIEW", color="#e51c73", row_h=34)
    charts = []
    for pair in ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD"]:
        aligned = build_fx_pair_data(df, pair)
        if not aligned.empty:
            charts.append(aligned["spot"].rename(pair))
    p.line_chart(MARGIN_X, 225, 850, 150,
                 pd.concat(charts, axis=1) if charts else pd.DataFrame(),
                 "FX SPOT - NORMALIZED", "#e51c73", max_series=4,
                 normalize=True, last_n=252)
    p.note(950, 300, 430, 170, "INTERPRETATION LIMIT",
           "Each pair uses fully aligned spot, 2Y nominal, 10Y nominal and 10Y real differentials. Missing inputs are never displayed as zero. Correlations are descriptive and do not establish causality or fair value.", "#e51c73")


def _data_quality(p: PackCanvas, df, r):
    from data.quality import quality_summary, validate_data
    try:
        report = validate_data(df)
        summary = quality_summary(report)
    except Exception:
        summary = {}
    p.kpis([
        {"label": "LATEST VALID DATE", "value": p.latest_date.date() if p.latest_date is not None else "-", "accent": "#9aa0a6"},
        {"label": "ROWS", "value": f"{len(df):,}"},
        {"label": "COLUMNS", "value": f"{df.shape[1]:,}"},
        {"label": "CLI COMPONENTS", "value": f"{int(r.available_component_count.dropna().iloc[-1])}/23"},
    ])
    coverage = []
    for page in PAGES:
        coverage.append({"section": page["section"], "page": page["title"],
                         "status": STATUS_LABELS.get(page["status"], page["status"]),
                         "source": page.get("data_source", "-")})
    p.table(MARGIN_X, 478, 830, coverage,
            [("section", "NO", .10), ("page", "PAGE", .44),
             ("status", "STATUS", .18), ("source", "SOURCE", .28)],
            max_rows=14, title="BOARD COVERAGE", color="#9aa0a6", row_h=22)
    rows = [{"metric": k, "value": v} for k, v in summary.items()] if isinstance(summary, dict) else []
    p.table(930, 478, 450, rows,
            [("metric", "QUALITY METRIC", .62), ("value", "VALUE", .38)],
            max_rows=10, title="DATA QUALITY SUMMARY", color="#9aa0a6")
    p.note(930, 210, 450, 120, "NON-FABRICATION POLICY",
           "No missing observation, ticker, model result or interpretation is invented. Unsupported modules remain unavailable or partial until the required source input and methodology are confirmed.", "#9aa0a6")


def _scoring(p: PackCanvas, df):
    from data.external_loaders import load_pulsar
    from models.scoring.engine import determine_scoring_asof, score_equity, score_rates
    data = load_pulsar()
    info = determine_scoring_asof(data or {})
    asof = pd.Timestamp(info["asof_date"]) if info.get("asof_date") else None
    rates = score_rates(data, asof, {"macro": .5, "markets": .5}) if data and asof is not None else pd.DataFrame()
    equity = score_equity(data, asof, {"macro": .5, "eps": .5}) if data and asof is not None else pd.DataFrame()
    p.kpis([
        {"label": "SCORING AS OF", "value": asof.date() if asof is not None else "-", "accent": "#9aa0a6"},
        {"label": "RATES PANEL", "value": len(rates)},
        {"label": "EQUITY PANEL", "value": len(equity)},
        {"label": "FUTURE ROWS EXCLUDED", "value": len(info.get("future_rows", []))},
    ])
    if not rates.empty:
        rates = rates.assign(
            macro_f=rates["macro"].map(lambda v: _fmt(v, "+.2f")),
            markets_f=rates["markets"].map(lambda v: _fmt(v, "+.2f")),
            score_f=rates["score"].map(lambda v: _fmt(v, "+.2f")),
        )
    p.table(MARGIN_X, 478, 620, rates,
            [("country", "RATES MARKET", .45), ("macro_f", "MACRO", .18),
             ("markets_f", "MARKETS", .18), ("score_f", "SCORE", .19)],
            max_rows=10, title="GLOBAL RATES SCORING - 50/50 WEIGHTS", color="#9aa0a6")
    if not equity.empty:
        equity = equity.assign(
            macro_f=equity["macro"].map(lambda v: _fmt(v, "+.2f")),
            score_f=equity["score"].map(lambda v: _fmt(v, "+.2f")),
            p1m_f=equity["p1m"].map(lambda v: _fmt(v, "+.2f", "%")),
        )
    p.table(720, 478, 660, equity,
            [("name", "EQUITY INDEX", .45), ("macro_f", "MACRO", .17),
             ("score_f", "SCORE", .18), ("p1m_f", "1M", .20)],
            max_rows=12, title="GLOBAL EQUITY SCORING - 50/50 WEIGHTS", color="#9aa0a6")
    p.note(MARGIN_X, 145, 1320, 75, "METHODOLOGY",
           "Scores are cross-sectional relative rankings. The PDF uses the Board defaults: rates 50% macro / 50% markets; equities 50% macro / 50% EPS. Future-dated source rows are excluded.", "#9aa0a6")


def _roadmap(p: PackCanvas, df):
    counts = pd.Series([m.get("current_status", "Unknown") for m in ROADMAP]).value_counts()
    p.kpis([
        {"label": "LIVE MODULES", "value": int(counts.get("Live", 0)), "accent": "#9aa0a6"},
        {"label": "PARTIAL", "value": int(counts.get("Partial", 0))},
        {"label": "DATA MISSING", "value": int(counts.get("Data Missing", 0))},
        {"label": "NOT STARTED", "value": int(counts.get("Not Started", 0))},
    ])
    rows = []
    for m in ROADMAP:
        rows.append({
            "section": m.get("section"), "title": m.get("title"),
            "status": m.get("current_status"),
            "missing": ", ".join(m.get("missing_data") or []) or "-",
        })
    p.table(MARGIN_X, 478, 1320, rows,
            [("section", "SECTION", .08), ("title", "MODULE", .33),
             ("status", "STATUS", .16), ("missing", "CONFIRMED GAP", .43)],
            max_rows=16, title="REFERENCE-PACK CONTENT GAP", color="#9aa0a6", row_h=24)
    p.note(MARGIN_X, 100, 1320, 72, "ROADMAP RULE",
           "This register is descriptive. Missing inputs and methodology remain explicit; the export does not create placeholder charts, proxy tickers, fabricated statuses or unsupported interpretations.", "#9aa0a6")


PAGE_BUILDERS = {
    "liquidity": _liquidity,
    "policy": _policy,
    "policy_futures": _policy_futures,
    "decomposition": _decomposition,
    "regimes": _regimes,
    "global_rates": _global_rates,
    "country_boards": _country_boards,
    "cross_asset": _cross_asset,
    "market_linkage": _market_linkage,
    "sector_rotation": _sector_rotation,
    "sector_contribution": _sector_contribution,
    "earnings_valuation": _earnings,
    "fx_rate_diff": _fx,
    "data_quality": _data_quality,
    "scoring": _scoring,
    "model_roadmap": _roadmap,
}


def build_pdf(df: pd.DataFrame | None = None, index_result=None) -> tuple[bytes, str]:
    """Return ``(pdf_bytes, filename)`` for the current verified Board state."""
    frame = load_data() if df is None else df
    result = compute_index(frame) if index_result is None else index_result
    latest = latest_valid_date(frame)
    sig = source_signature()
    date_str = latest.strftime("%Y%m%d") if latest is not None else "unknown"

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=PAGE_SIZE, pageCompression=1)
    pdf.setTitle(f"Rates & Liquidity Research Pack - {date_str}")
    pdf.setAuthor("MonitorBoard")
    pdf.setCreator("MonitorBoard one-click PDF export")
    pack = PackCanvas(pdf, latest, sig)

    _cover(pack, result)
    _contents(pack)
    for idx, page in enumerate(PAGES):
        pack.begin(page)
        builder = PAGE_BUILDERS.get(page["id"])
        try:
            if builder is None:
                pack.note(MARGIN_X, 340, PAGE_W - 2 * MARGIN_X, 150,
                          "EXPORT UNAVAILABLE",
                          "No PDF renderer is registered for this Board page. The page is retained in the export so the gap remains explicit.",
                          _page_color(page))
            elif page["id"] in {"liquidity", "data_quality"}:
                builder(pack, frame, result)
            else:
                builder(pack, frame)
        except Exception as exc:
            pack.note(MARGIN_X, 340, PAGE_W - 2 * MARGIN_X, 150,
                      "PAGE EXPORT UNAVAILABLE",
                      f"The production page remains in the Board, but its PDF renderer failed with {type(exc).__name__}. No replacement values or charts were inserted.",
                      _page_color(page))
        prev_id = PAGES[idx - 1]["id"] if idx > 0 else None
        next_id = PAGES[idx + 1]["id"] if idx + 1 < len(PAGES) else None
        pack.finish(prev_id, next_id)

    pdf.save()
    return buffer.getvalue(), f"rates_liquidity_board_{date_str}.pdf"


if __name__ == "__main__":
    payload, filename = build_pdf()
    out_dir = Path("output/pdf")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    out_path.write_bytes(payload)
    print(f"Wrote {out_path} ({len(payload) / 1024:.0f} KB)")
