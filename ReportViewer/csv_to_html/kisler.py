#!/usr/bin/env python3
"""
Kisler maXYmos NC CSV to HTML converter.
Converts Part Protocol CSV files to a styled HTML report with an interactive graph.
Usage:
    python kisler_csv_to_html.py <input.csv> [output.html]
    python kisler_csv_to_html.py <folder>   (converts all CSV files in folder tree)
"""

import sys
import csv
from pathlib import Path
from html import escape


# ---------------------------------------------------------------------------
# CSV PARSING
# ---------------------------------------------------------------------------


def read_csv_rows(filepath):
    """Read all rows from the semicolon-delimited CSV."""
    rows = []
    with open(filepath, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        for row in reader:
            rows.append(row)
    return rows


def split_sections(rows):
    """
    Split the flat row list into named sections using the Index/Line header map
    found near the top of the file (the two rows that start with 'Index' and 'Line').

    The 'Index' row lists section names in column order.
    The 'Line' row lists the 1-based CSV line number where each section starts.

    Falls back to scanning for known section-name cells if the header map is absent.
    Returns an ordered list of (section_name, [rows]) tuples.
    """
    # --- Try to find the Index / Line header rows ---
    index_row = None
    line_row  = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "Index":
            index_row = row
            if i + 1 < len(rows) and rows[i + 1] and rows[i + 1][0].strip() == "Line":
                line_row = rows[i + 1]
            break

    if index_row and line_row:
        # Build {1-based-line-number: section_name} from the two rows.
        # Column 0 is the label ("Index"/"Line") itself; skip it.
        section_starts = {}   # line_no (int) -> section_name (str)
        for col in range(1, min(len(index_row), len(line_row))):
            name = index_row[col].strip()
            lno  = line_row[col].strip()
            if name and lno:
                try:
                    section_starts[int(lno)] = name
                except ValueError:
                    pass

        # Walk every row by its 1-based position and emit section boundaries
        sections   = []
        cur_name   = "Header"
        cur_rows   = []
        for lineno, row in enumerate(rows, start=1):
            if lineno in section_starts:
                if cur_rows or cur_name != "Header":
                    sections.append((cur_name, cur_rows))
                cur_name = section_starts[lineno]
                cur_rows = []
                # The section-name row itself is the header — skip adding it as data
                continue
            cur_rows.append(row)
        if cur_rows:
            sections.append((cur_name, cur_rows))

        # "Measuring points" is the data-row block that immediately follows
        # "Measuring curve" in the Index/Line map — merge them so the parser
        # sees meta + column header + units + data all in one section.
        merged = []
        i = 0
        while i < len(sections):
            name, s_rows = sections[i]
            if name == "Measuring curve" and i + 1 < len(sections) \
                    and sections[i + 1][0] == "Measuring points":
                merged.append(("Measuring curve", s_rows + sections[i + 1][1]))
                i += 2
            else:
                merged.append((name, s_rows))
                i += 1
        return merged

    # --- Fallback: scan for known section-name cells ---
    SECTION_HEADERS = {
        "Part protocol", "Result information",
        "Process values - curve related", "Process values - EO related",
        "Process values - EO related curve 2", "Evaluation objects settings",
        "Switch signal settings", "Device information", "Servo",
        "Channel-X settings", "Channel-Y settings", "Cycle control settings",
        "Evaluation settings", "Trigger Y settings", "Block settings",
        "Measuring curve", "Measuring points", "Sequence Editor", "Sequence",
    }
    sections   = []
    cur_name   = "Header"
    cur_rows   = []
    for row in rows:
        if not row:
            cur_rows.append(row)
            continue
        cell = row[0].strip()
        if cell in SECTION_HEADERS:
            if cur_rows or cur_name != "Header":
                sections.append((cur_name, cur_rows))
            cur_name = cell
            cur_rows = []
        else:
            cur_rows.append(row)
    if cur_rows:
        sections.append((cur_name, cur_rows))
    return sections


# ---------------------------------------------------------------------------
# MEASURING CURVE DATA EXTRACTION
# ---------------------------------------------------------------------------

def parse_measuring_curve(rows):
    """
    Measuring curve section layout (relative to section start):
        meta rows   – Number of measuring points, Ref. Graph on, Curve segment, ...
        empty lines
        col headers – Time ; X(ABSOLUTE) ; Y ; X(ABSOLUTE) ; X2(ABSOLUTE) ; Y2 ; X2(ABSOLUTE)
        empty line
        units       – s ; mm ; kN ; mm ; mm ; mm ; mm
        data rows   – 0.0001 ; 72.976 ; -0.00068 ; ...

    Returns:
        meta    – dict with num_points, ref_graph, etc.
        series  – list of dicts {time, x, y}
        headers – column name list
        units   – unit string list
    """
    meta = {}
    headers = []
    units = []
    series = []

    # --- locate header row (first row whose col-0 is "Time") ---
    header_idx = None
    for i, row in enumerate(rows):
        if row and row[0].strip() == "Time":
            header_idx = i
            headers = [c.strip() for c in row]
            break

    if header_idx is None:
        return meta, series, headers, units

    # --- units row: first non-empty row after the header ---
    units_idx = None
    for i in range(header_idx + 1, len(rows)):
        if rows[i] and any(c.strip() for c in rows[i]):
            units = [c.strip() for c in rows[i]]
            units_idx = i
            break

    # --- data rows: every row after units_idx that parses as floats ---
    data_start = (units_idx + 1) if units_idx is not None else (header_idx + 1)
    for row in rows[data_start:]:
        if not row or not row[0].strip():
            continue
        try:
            t = float(row[0].replace(",", "."))
            x = float(row[1].replace(",", ".")) if len(row) > 1 and row[1].strip() else None
            y = float(row[2].replace(",", ".")) if len(row) > 2 and row[2].strip() else None
            series.append({"time": t, "x": x, "y": y})
        except (ValueError, IndexError):
            pass

    # --- meta rows: everything before the header ---
    for row in rows[:header_idx]:
        if not row or not row[0].strip():
            continue
        key = row[0].strip()
        if key.startswith("Number of measuring points"):
            meta["num_points"] = row[1].strip() if len(row) > 1 else ""
        elif key.startswith("Ref. Graph on"):
            meta["ref_graph"] = row[1].strip() if len(row) > 1 else ""
        elif key.startswith("Curve segment"):
            meta.setdefault("curve_segments", []).append([c.strip() for c in row[1:]])

    return meta, series, headers, units


def parse_eo_settings(sections):
    """
    Parse Evaluation objects settings section.
    The section trigger row (which starts with the section name) is consumed as
    the section delimiter — so rows here start directly with EO data rows.

    Known header (from the CSV section trigger row):
      col 0  = EO name  (EO-01 … EO-10)
      col 1  = Reaction  (UNI-BOX, OFF, …)
      col 2  = X reference
      col 3  = Y-Reference
      col 4  = XMin
      col 5  = XMax
      col 6  = YMin
      col 7  = YMax
      col 8  = Entry
      col 9  = Exit
      col 10 = Curve part
      col 11 = Catch zone X
      col 12 = Catch zone Y
      col 13 = EO Name
      col 14 = Description
      col 15 = Re-entry ignored
      col 16 = Generate statistics
      col 17 = X-Hysteresis
      col 18 = Y-Hysteresis
      … (further columns less relevant for display)

    Returns list of dicts for ALL EOs (including OFF), plus box geometry for chart.
    """
    HDR = [
        "EO", "Reaction", "X reference", "Y-Reference",
        "XMin", "XMax", "YMin", "YMax",
        "Entry", "Exit", "Curve part",
        "Catch zone X", "Catch zone Y",
        "EO Name", "Description",
        "Re-entry ignored", "Generate statistics",
        "X-Hysteresis", "Y-Hysteresis",
        "Down sampling rate",
    ]

    eos = []
    for name, rows in sections:
        if name == "Evaluation objects settings":
            for row in rows:
                if not row or not row[0].strip().startswith("EO-"):
                    continue
                d = {}
                for i, h in enumerate(HDR):
                    d[h] = row[i].strip() if i < len(row) else ""
                # Box geometry as floats for chart
                for key in ("XMin", "XMax", "YMin", "YMax"):
                    try:
                        d[key + "_f"] = float(d[key].replace(",", "."))
                    except (ValueError, AttributeError):
                        d[key + "_f"] = None
                eos.append(d)
    return eos


def parse_eo_boxes(sections):
    """Return chart-annotation box dicts derived from parse_eo_settings."""
    boxes = []
    for eo in parse_eo_settings(sections):
        if eo.get("Reaction", "OFF").upper() in ("OFF", "NONE", ""):
            continue
        boxes.append({
            "name":    eo["EO"],
            "reaction": eo["Reaction"],
            "xmin":    eo["XMin_f"],
            "xmax":    eo["XMax_f"],
            "ymin":    eo["YMin_f"],
            "ymax":    eo["YMax_f"],
        })
    return boxes


def parse_eo_results(sections):
    """Extract EO result rows from 'Process values - EO related'."""
    results = []
    for name, rows in sections:
        if name == "Process values - EO related":
            # The first non-empty row that has "Result" in position 1 is the header.
            # But the section trigger row itself (starting with the section name) was
            # consumed as the section delimiter, so within `rows` we only have rows AFTER it.
            # The first data row is the units row (starts with empty cell).
            # EO rows start with "EO-xx".
            # We build a synthetic header: ["EO", "Result", "Entry", "Exit", ...]
            # by looking for the units row index; the header is implied from the section name row
            # which we no longer have — so we hard-code the known header.
            HEADER = [
                "EO", "Result", "Entry", "Exit",
                "XMIN-X", "XMIN-Y", "XMAX-X", "XMAX-Y",
                "YMIN-Y", "YMIN-X", "YMAX-Y", "YMAX-X",
                "Calculated result", "NOK cause",
                "Violation X", "Violation Y",
                "Ref X", "Ref Y", "X at Delta-Y",
                "Entry-X", "Entry-Y", "Exit-X", "Exit-Y",
            ]
            for row in rows:
                if not row:
                    continue
                if row[0].strip().startswith("EO-"):
                    d = {}
                    for i, hdr in enumerate(HEADER):
                        d[hdr] = row[i].strip() if i < len(row) else ""
                    results.append(d)
    return results


# ---------------------------------------------------------------------------
# HTML GENERATION HELPERS
# ---------------------------------------------------------------------------

def result_badge(result_str):
    r = result_str.strip().upper()
    if r == "OK":
        return '<span class="badge ok">OK</span>'
    elif r == "NOK":
        return '<span class="badge nok">NOK</span>'
    elif r == "NONE":
        return '<span class="badge none">—</span>'
    return f'<span class="badge">{escape(result_str)}</span>'


def rows_to_table(rows, max_cols=None, highlight_col=None):
    """Render a list of rows to an HTML table."""
    if not any(r for r in rows):
        return ""
    html = ['<table>']
    for row in rows:
        if not row or all(c.strip() == "" for c in row):
            continue
        cells = row if max_cols is None else row[:max_cols]
        # Pad
        html.append("<tr>")
        for i, cell in enumerate(cells):
            cell_s = cell.strip()
            cls = ""
            if highlight_col is not None and i == highlight_col:
                up = cell_s.upper()
                if up == "OK":
                    cls = ' class="ok"'
                elif up == "NOK":
                    cls = ' class="nok"'
            html.append(f"<td{cls}>{escape(cell_s)}</td>")
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html)


def kv_section_to_table(rows):
    """Render key-value style rows to a two-column table."""
    html = ['<table class="kv">']
    for row in rows:
        if not row or all(c.strip() == "" for c in row):
            continue
        key = row[0].strip()
        vals = [c.strip() for c in row[1:] if c.strip()]
        val_str = " &nbsp; ".join(escape(v) for v in vals)
        html.append(f"<tr><th>{escape(key)}</th><td>{val_str}</td></tr>")
    html.append("</table>")
    return "\n".join(html)


# ---------------------------------------------------------------------------
# CHART (inline SVG)
# ---------------------------------------------------------------------------

def build_chart_html(series, eo_boxes, eo_results, x_unit="mm", y_unit="kN"):
        """
        Build a self-contained SVG chart block.
        X-axis = X(ABSOLUTE) position (x_unit)
        Y-axis = Force (y_unit)
        EO boxes drawn directly in position/force space.
        """
        data_points = [
                {"x": p["x"], "y": p["y"]}
                for p in series
                if p.get("x") is not None and p.get("y") is not None
        ]
        if not data_points:
                return "<p><em>No measuring curve data found.</em></p>"

        xs = [p["x"] for p in data_points]
        ys = [p["y"] for p in data_points]

        x_min = min(xs)
        x_max = max(xs)
        x_pad = (x_max - x_min) * 0.03 or 0.5
        y_min = min(ys)
        y_max = max(ys)
        y_pad = (y_max - y_min) * 0.08 or 0.05

        x_min -= x_pad
        x_max += x_pad
        y_min -= y_pad
        y_max += y_pad

        svg_width = 980
        svg_height = 420
        margin_left = 72
        margin_right = 24
        margin_top = 18
        margin_bottom = 56
        plot_width = svg_width - margin_left - margin_right
        plot_height = svg_height - margin_top - margin_bottom

        def scale_x(value):
                if x_max == x_min:
                        return margin_left + plot_width / 2
                return margin_left + ((value - x_min) / (x_max - x_min)) * plot_width

        def scale_y(value):
                if y_max == y_min:
                        return margin_top + plot_height / 2
                return margin_top + plot_height - ((value - y_min) / (y_max - y_min)) * plot_height

        line_points = " ".join(f"{scale_x(p['x']):.2f},{scale_y(p['y']):.2f}" for p in data_points)

        grid_parts = []
        tick_count = 6
        for index in range(tick_count + 1):
                ratio = index / tick_count
                px = margin_left + plot_width * ratio
                py = margin_top + plot_height * (1 - ratio)
                x_val = x_min + (x_max - x_min) * ratio
                y_val = y_min + (y_max - y_min) * ratio

                grid_parts.append(
                        f'<line x1="{px:.2f}" y1="{margin_top}" x2="{px:.2f}" y2="{margin_top + plot_height}" '
                        'stroke="#d8dee6" stroke-width="1" />'
                )
                grid_parts.append(
                        f'<text x="{px:.2f}" y="{svg_height - 18}" class="chart-axis-text" text-anchor="middle">{escape(f"{x_val:.4f}")}</text>'
                )

                grid_parts.append(
                        f'<line x1="{margin_left}" y1="{py:.2f}" x2="{margin_left + plot_width}" y2="{py:.2f}" '
                        'stroke="#d8dee6" stroke-width="1" />'
                )
                grid_parts.append(
                        f'<text x="{margin_left - 10}" y="{py + 4:.2f}" class="chart-axis-text" text-anchor="end">{escape(f"{y_val:.5f}")}</text>'
                )

        band_colors = ["rgba(255,165,0,0.15)", "rgba(0,128,255,0.15)", "rgba(0,200,100,0.15)"]
        border_colors = ["rgba(255,140,0,0.95)", "rgba(0,100,200,0.95)", "rgba(0,160,80,0.95)"]
        box_parts = []
        legend_parts = [
                '<div class="chart-legend-item"><span class="chart-legend-swatch curve"></span><span>Force vs Position</span></div>'
        ]

        for index, box in enumerate(eo_boxes):
                xmin = box.get("xmin")
                xmax = box.get("xmax")
                ymin = box.get("ymin")
                ymax = box.get("ymax")
                if None in (xmin, xmax, ymin, ymax):
                        continue

                fill = band_colors[index % len(band_colors)]
                stroke = border_colors[index % len(border_colors)]
                left = scale_x(min(xmin, xmax))
                right = scale_x(max(xmin, xmax))
                top = scale_y(max(ymin, ymax))
                bottom = scale_y(min(ymin, ymax))
                width = max(right - left, 1)
                height = max(bottom - top, 1)

                label = box.get("name", "")
                result = next((r.get("Result", "") for r in eo_results if r.get("EO", "") == label), "")
                box_label = escape(f"{label} {result}".strip())

                box_parts.append(
                        f'<rect x="{left:.2f}" y="{top:.2f}" width="{width:.2f}" height="{height:.2f}" '
                        f'fill="{fill}" stroke="{stroke}" stroke-width="2" rx="3" />'
                )
                if box_label:
                        box_parts.append(
                                f'<text x="{left + 6:.2f}" y="{max(top + 14, margin_top + 14):.2f}" class="chart-box-label" fill="{stroke}">{box_label}</text>'
                        )

                legend_parts.append(
                        f'<div class="chart-legend-item"><span class="chart-legend-swatch" style="background:{fill}; border-color:{stroke};"></span><span>{box_label or escape(label)}</span></div>'
                )

        html = f"""
<div class="chart-container">
    <div class="chart-legend">{''.join(legend_parts)}</div>
    <svg class="chart-svg" viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="none" role="img" aria-label="Measuring curve chart">
        <rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#ffffff" />
        <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#cfd8e3" stroke-width="1" />
        {''.join(grid_parts)}
        {''.join(box_parts)}
        <polyline fill="none" stroke="#007acc" stroke-width="2" points="{line_points}" />
        <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.4" />
        <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.4" />
        <text x="{margin_left + plot_width / 2:.2f}" y="{svg_height - 4}" class="chart-axis-title" text-anchor="middle">Position ({escape(x_unit)})</text>
        <text x="18" y="{margin_top + plot_height / 2:.2f}" class="chart-axis-title" text-anchor="middle" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})">Force ({escape(y_unit)})</text>
    </svg>
</div>
"""
        return html


# ---------------------------------------------------------------------------
# MAIN HTML BUILDER
# ---------------------------------------------------------------------------

from .kisler_styles import CSS

JS_TOGGLE = """
(function() {
    var PREFIX = 'kistler_card_';

    function cardTitle(hdr) {
        var s = hdr.querySelector('span');
        return s ? s.textContent : hdr.textContent;
    }

    function saveState(title, collapsed) {
        try { localStorage.setItem(PREFIX + title, collapsed ? '1' : '0'); } catch(e) {}
    }

    function restoreStates() {
        document.querySelectorAll('.card-header').forEach(function(hdr) {
            var saved;
            try { saved = localStorage.getItem(PREFIX + cardTitle(hdr)); } catch(e) { return; }
            if (saved === null) return;
            var body = hdr.nextElementSibling;
            if (saved === '1') {
                hdr.classList.add('collapsed');
                body.classList.add('hidden');
            } else {
                hdr.classList.remove('collapsed');
                body.classList.remove('hidden');
            }
        });
    }

    document.querySelectorAll('.card-header').forEach(function(hdr) {
        hdr.addEventListener('click', function() {
            var body = hdr.nextElementSibling;
            body.classList.toggle('hidden');
            hdr.classList.toggle('collapsed');
            saveState(cardTitle(hdr), hdr.classList.contains('collapsed'));
        });
    });

    restoreStates();
})();
"""


def card(title, body_html, collapsed=False):
    c_cls = " collapsed" if collapsed else ""
    b_cls = " hidden" if collapsed else ""
    return f"""
<div class="card">
  <div class="card-header{c_cls}">
    <span>{escape(title)}</span>
    <span class="toggle-icon">&#9660;</span>
  </div>
  <div class="card-body{b_cls}">
    {body_html}
  </div>
</div>"""


# Step-type icon map
SEQ_ICONS = {
    "MOTION":        "🔵",
    "MEASURE":       "📏",
    "OUTPUT":        "🔌",
    "INPUT":         "🎛️",
    "TIMER":         "⏱️",
    "HOME_POSITION": "🏠",
    "SEQUENCE_END":  "🔚",
    "LABEL":         "🏷️",
}

# MOTION / HOME_POSITION — settings are 4-cell groups: key ; value ; unit ; source
# source is always "User" — we skip it but consume it
MOTION_UNIT_KEYS = {
    "Position", "SPEED", "Max. force", "Min. force", "Force",
    "Tara. position", "Deformation", "Timeout",
}


def _parse_motion_settings(cells):
    """
    Parse MOTION / HOME_POSITION setting cells.
    Groups of 4: key ; value ; unit ; source  (source = "User", skipped)
    Boolean/enum pairs (no unit, no source): key ; value
    Returns list of (key, value, unit) tuples.
    """
    result = []
    i = 0
    while i < len(cells):
        key = cells[i].strip()
        if not key:
            i += 1
            continue
        val  = cells[i + 1].strip() if i + 1 < len(cells) else ""
        unit = cells[i + 2].strip() if i + 2 < len(cells) else ""
        src  = cells[i + 3].strip() if i + 3 < len(cells) else ""
        if key in MOTION_UNIT_KEYS and unit and src == "User":
            result.append((key, val, unit))
            i += 4
        else:
            # boolean / enum pair (no unit cell)
            result.append((key, val, ""))
            i += 2
    return result


def _parse_input_settings(cells):
    """
    INPUT row after col2 (code):
      signal_name ; LEVEL ; HIGH/LOW ; Timeout ; value ; unit ; Text ; text_val ; Error on timeout ; state
    """
    result = []
    if len(cells) > 0:
        result.append(("Signal", cells[0].strip(), ""))
    if len(cells) > 2:
        result.append((cells[1].strip(), cells[2].strip(), ""))   # LEVEL: HIGH
    if len(cells) > 5 and cells[3].strip() == "Timeout":
        result.append(("Timeout", cells[4].strip(), cells[5].strip()))
    if len(cells) > 7 and cells[6].strip() == "Text":
        if cells[7].strip():
            result.append(("Text", cells[7].strip(), ""))
    if len(cells) > 9 and cells[8].strip() == "Error on timeout":
        result.append(("Error on timeout", cells[9].strip(), ""))
    return result


def _pills_html(settings):
    """Render a list of (key, value, unit) as HTML pill spans."""
    out = ""
    for key, val, unit in settings:
        if not key and not val:
            continue
        val_str = escape(val)
        if unit:
            val_str += f" <span class='seq-unit'>{escape(unit)}</span>"
        if key:
            out += f'<span class="seq-pill"><span class="seq-key">{escape(key)}</span>{val_str}</span>'
        else:
            out += f'<span class="seq-pill">{val_str}</span>'
    return out


def render_sequence(rows):
    """
    Render Sequence Editor rows as a structured step list.

    Row layout (semicolon-separated columns):
      col 0  – group name ("Main", "Sub.1", …) or empty for continuation steps
      col 1  – step type label ("Motion", "Measure", "Output", …)
      col 2  – step type code  ("MOTION", "MEASURE", "OUTPUT", …)
      col 3+ – step-type-specific parameters
    """
    if not rows:
        return "<p><em>No sequence data.</em></p>"

    data = [r for r in rows if r and any(c.strip() for c in r)]
    if not data:
        return "<p><em>No sequence data.</em></p>"

    html = ['<div class="seq-editor">']
    current_group = None
    step_num = 0

    for row in data:
        group   = row[0].strip() if len(row) > 0 else ""
        s_label = row[1].strip() if len(row) > 1 else ""
        s_code  = row[2].strip() if len(row) > 2 else ""
        params  = row[3:] if len(row) > 3 else []
        cells   = [c.strip() for c in params]

        # ── Group header ────────────────────────────────────────────────
        if group and group != current_group:
            current_group = group
            step_num = 0
            html.append(
                f'<div class="seq-group">'
                f'<span class="seq-group-name">▶ {escape(group)}</span>'
                f'</div>'
            )

        # ── Skip pure label / sub-sequence placeholders ──────────────────
        if s_code == "LABEL":
            # Only show if it carries a meaningful label name (not just "1")
            lbl = cells[0] if cells else ""
            num = cells[1] if len(cells) > 1 else ""
            if lbl and lbl != "1":
                html.append(
                    f'<div class="seq-step seq-label">'
                    f'<span class="seq-icon">{SEQ_ICONS["LABEL"]}</span>'
                    f'<span class="seq-type">{escape(s_label)}</span>'
                    f'<span class="seq-pills">'
                    f'<span class="seq-pill">{escape(lbl)}'
                    f'{(" — " + escape(num)) if num and num != "1" else ""}'
                    f'</span></span></div>'
                )
            continue

        if s_code == "SEQUENCE_END":
            html.append(
                f'<div class="seq-step seq-end">'
                f'<span class="seq-icon">{SEQ_ICONS["SEQUENCE_END"]}</span>'
                f'<span class="seq-type">{escape(s_label)}</span>'
                f'</div>'
            )
            continue

        step_num += 1
        icon = SEQ_ICONS.get(s_code, "⚙️")

        # ── Per-type setting parsing ──────────────────────────────────────
        if s_code in ("MOTION", "HOME_POSITION"):
            settings = _parse_motion_settings(cells)
            # Filter out verbose/uninteresting flags for cleaner display
            HIDE_KEYS = {
                "Tara", "Deformation", "Stop on external signal", "Condition",
                "Enable Passive Deformation Compensation", "Used force sensor",
                "Reload UVT", "Block motion control",
            }
            show = [(k, v, u) for k, v, u in settings if k not in HIDE_KEYS]
            pills = _pills_html(show)

        elif s_code == "MEASURE":
            action = cells[0] if cells else ""
            extra  = cells[1] if len(cells) > 1 else ""
            settings = [("", action, "")]
            if extra:
                settings.append(("", extra, ""))
            pills = _pills_html(settings)

        elif s_code == "OUTPUT":
            # Value ; bit-pattern
            val = cells[1] if len(cells) > 1 else (cells[0] if cells else "")
            pills = _pills_html([("Value", val, "")])

        elif s_code == "INPUT":
            pills = _pills_html(_parse_input_settings(cells))

        elif s_code == "TIMER":
            # value ; unit ; source
            val  = cells[0] if cells else ""
            unit = cells[1] if len(cells) > 1 else ""
            pills = _pills_html([("Duration", val, unit)])

        else:
            # Generic fallback: show all non-empty cells as plain pills
            pills = "".join(
                f'<span class="seq-pill">{escape(c)}</span>'
                for c in cells if c
            )

        step_cls = f"seq-step seq-{s_code.lower()}"
        html.append(
            f'<div class="{step_cls}">'
            f'<span class="seq-num">{step_num}</span>'
            f'<span class="seq-icon">{icon}</span>'
            f'<span class="seq-type">{escape(s_label) or escape(s_code)}</span>'
            f'<span class="seq-pills">{pills}</span>'
            f'</div>'
        )

    html.append('</div>')
    return "\n".join(html)


def render_eo_settings_grid(eo_settings, eo_results):
    """
    Render Evaluation objects settings as a card grid, similar to EO Results.
    Each active EO gets a card; OFF EOs are shown collapsed/greyed.
    eo_results is the list of result dicts (from parse_eo_results) for cross-referencing.
    """
    if not eo_settings:
        return "<p><em>No EO settings found.</em></p>"

    # Build a result lookup: EO name -> result dict
    res_lookup = {r.get("EO", ""): r for r in eo_results}

    # Fields to display prominently (label, key in dict)
    PRIMARY_FIELDS = [
        ("Reaction",     "Reaction"),
        ("X Ref",        "X reference"),
        ("Y Ref",        "Y-Reference"),
        ("XMin",         "XMin"),
        ("XMax",         "XMax"),
        ("YMin",         "YMin"),
        ("YMax",         "YMax"),
        ("Entry",        "Entry"),
        ("Exit",         "Exit"),
        ("Curve part",   "Curve part"),
        ("EO Name",      "EO Name"),
        ("Description",  "Description"),
        ("X-Hysteresis", "X-Hysteresis"),
        ("Y-Hysteresis", "Y-Hysteresis"),
        ("Re-entry ignored",    "Re-entry ignored"),
        ("Generate statistics", "Generate statistics"),
    ]

    parts = []
    for eo in eo_settings:
        nm       = eo.get("EO", "")
        reaction = eo.get("Reaction", "OFF")
        is_off   = reaction.upper() in ("OFF", "NONE", "")

        # Cross-reference result
        res_d    = res_lookup.get(nm, {})
        result   = res_d.get("Result", "")

        if is_off:
            cls = "eo-card none"
            badge = result_badge("None")
        else:
            res_up = result.upper()
            cls    = "eo-card ok" if res_up == "OK" else ("eo-card nok" if res_up == "NOK" else "eo-card")
            badge  = result_badge(result) if result else ""

        items_html = ""
        for label, key in PRIMARY_FIELDS:
            val = eo.get(key, "").strip()
            if not val or val == "-":
                continue
            items_html += (
                f'<div class="kv-item">'
                f'<span>{escape(label)}</span>'
                f'<span>{escape(val)}</span>'
                f'</div>'
            )

        parts.append(
            f'<div class="{cls}">'
            f'<h3>{escape(nm)} — {escape(reaction)} {badge}</h3>'
            f'{items_html}'
            f'</div>'
        )

    return '<div class="eo-grid">' + "".join(parts) + "</div>"


def build_html(filepath, sections):
    sections_dict = {name: rows for name, rows in sections}

    # --- Result information ---
    ri_rows = sections_dict.get("Result information", [])
    info = {}
    for row in ri_rows:
        if row and row[0].strip():
            info[row[0].strip()] = " ".join(c.strip() for c in row[1:] if c.strip())

    date_str = info.get("Date", "")
    time_str = info.get("Time", "")
    prog_name = info.get("Measuring program name", "")
    prog_num = info.get("Measuring program number", "")
    cycle = info.get("Cycle number", "")
    total_result = info.get("Total result", "")
    filename = Path(filepath).name

    # --- Measuring curve ---
    mc_rows = sections_dict.get("Measuring curve", [])
    mc_meta, mc_series, mc_headers, mc_units = parse_measuring_curve(mc_rows)

    # --- EO boxes & results ---
    eo_settings = parse_eo_settings(sections)
    eo_boxes    = parse_eo_boxes(sections)
    eo_results  = parse_eo_results(sections)

    # --- Build result banner ---
    result_upper = total_result.upper()
    banner_cls = "ok" if result_upper == "OK" else "nok"
    banner_html = f'<div class="result-banner {banner_cls}">Total Result: {escape(total_result)}</div>'

    # --- Header ---
    station_name = "KISLER"
    recipe_name = prog_name or "-"
    date_time = f"{date_str} {time_str}".strip() or "-"
    file_report_name = filename

    header_html = f"""<header>
  <div>
    <h1>&#128202; Part Protocol Report</h1>
    <div style="margin-top:6px;opacity:0.9">Station name: {escape(station_name)}</div>
    <div style="margin-top:4px;opacity:0.9">Recipe name: {escape(recipe_name)}</div>
  </div>
  <div class="meta">
    <div>Date time: {escape(date_time)}</div>
    <div style="margin-top:4px">File report name: {escape(file_report_name)}</div>
  </div>
</header>"""

    body_parts = [header_html, banner_html]

    # ---- Result Information card ----
    ri_clean = [r for r in ri_rows if r and r[0].strip()]
    body_parts.append(card("📋 Result Information", kv_section_to_table(ri_clean)))

    # ---- EO Results card ----
    eo_grid_parts = []
    for r in eo_results:
        nm = r.get("EO", "EO")
        res = r.get("Result", "")
        res_up = res.upper()
        cls = "ok" if res_up == "OK" else ("nok" if res_up == "NOK" else "none")
        items_html = ""
        skip_keys = {"EO", "Result"}
        for k, v in r.items():
            if k in skip_keys or not v:
                continue
            items_html += f'<div class="kv-item"><span>{escape(k)}</span><span>{escape(v)}</span></div>'
        eo_grid_parts.append(
            f'<div class="eo-card {cls}"><h3>{escape(nm)} — {result_badge(res)}</h3>{items_html}</div>'
        )
    eo_grid_html = '<div class="eo-grid">' + "".join(eo_grid_parts) + "</div>" if eo_grid_parts else "<p><em>No EO data.</em></p>"
    # ---- Measuring Curve GRAPH card ----
    x_unit = "mm"
    y_unit = "kN"
    if mc_units:
        if len(mc_units) > 1:
            x_unit = mc_units[1] if mc_units[1] else "mm"
        if len(mc_units) > 2:
            y_unit = mc_units[2] if mc_units[2] else "kN"
    chart_html = build_chart_html(mc_series, eo_boxes, eo_results, x_unit=x_unit, y_unit=y_unit)
    pts_info = f'<p style="font-size:11px;color:#666;margin-bottom:8px">Number of data points: <strong>{len(mc_series)}</strong></p>'
    body_parts.append(card("📈 Measuring Curve", pts_info + chart_html))

    body_parts.append(card("🎯 Evaluation Objects — Results", eo_grid_html))

    # ---- Process values - curve related ----
    pv_rows = sections_dict.get("Process values - curve related", [])
    if pv_rows:
        body_parts.append(card("📊 Process Values — Curve Related",
                               rows_to_table(pv_rows), collapsed=False))

    # ---- Evaluation objects settings ----
    if eo_settings:
        body_parts.append(card("⚙️ Evaluation Objects — Settings",
                               render_eo_settings_grid(eo_settings, eo_results),
                               collapsed=True))

    # ---- Device + Servo (two-col) ----
    def _is_real_row(r):
        """Return False for empty rows or rows that are just '-' placeholders."""
        if not r:
            return False
        vals = [c.strip() for c in r]
        return bool(vals[0]) and not all(v in ("-", "") for v in vals)

    dev_rows = sections_dict.get("Device information", [])
    srv_rows = sections_dict.get("Servo", [])
    dev_html = kv_section_to_table([r for r in dev_rows if _is_real_row(r)])
    srv_html = kv_section_to_table([r for r in srv_rows if _is_real_row(r)])
    two_col = f'<div class="two-col"><div>{dev_html}</div><div>{srv_html}</div></div>'
    body_parts.append(card("🖥️ Device & Servo Information", two_col, collapsed=True))

    # ---- Channel-X + Channel-Y (two-col) ----
    def channel_to_table(rows):
        """
        Extract only the primary sensor columns (col0=key, col1=value, col2=unit).
        Skip rows where the value is '-' or empty (extended/secondary sensor placeholders).
        """
        html = ['<table class="kv">']
        for row in rows:
            if not row or not row[0].strip():
                continue
            key = row[0].strip()
            val  = row[1].strip() if len(row) > 1 else ""
            unit = row[2].strip() if len(row) > 2 else ""
            # skip pure placeholder rows
            if val in ("-", "") and unit in ("-", ""):
                continue
            val_str = escape(val)
            if unit and unit != "-":
                val_str += f" <span style='color:#888;font-size:11px'>{escape(unit)}</span>"
            html.append(f"<tr><th>{escape(key)}</th><td>{val_str}</td></tr>")
        html.append("</table>")
        return "\n".join(html)

    cx_rows = sections_dict.get("Channel-X settings", [])
    cy_rows = sections_dict.get("Channel-Y settings", [])
    cx_html = channel_to_table(cx_rows)
    cy_html = channel_to_table(cy_rows)
    two_col2 = f'<div class="two-col"><div><h4 style="margin-bottom:6px">Channel X</h4>{cx_html}</div>' \
               f'<div><h4 style="margin-bottom:6px">Channel Y</h4>{cy_html}</div></div>'
    body_parts.append(card("📡 Channel Settings", two_col2, collapsed=True))

    # ---- Cycle control + Evaluation settings ----
    cc_rows = sections_dict.get("Cycle control settings", [])
    ev_rows = sections_dict.get("Evaluation settings", [])
    cc_html = kv_section_to_table([r for r in cc_rows if r and r[0].strip()])
    ev_html = kv_section_to_table([r for r in ev_rows if r and r[0].strip()])
    two_col3 = f'<div class="two-col"><div><h4 style="margin-bottom:6px">Cycle Control</h4>{cc_html}</div>' \
               f'<div><h4 style="margin-bottom:6px">Evaluation Settings</h4>{ev_html}</div></div>'
    body_parts.append(card("🔄 Cycle & Evaluation Settings", two_col3, collapsed=True))

    # ---- Sequence Editor ----
    seq_rows = sections_dict.get("Sequence Editor", sections_dict.get("Sequence", []))
    if seq_rows:
        body_parts.append(card("🔀 Sequence Editor",
                               render_sequence(seq_rows),
                               collapsed=True))

    # ---- Measuring points raw table ----
    mp_rows = sections_dict.get("Measuring points", [])
    if mp_rows:
        body_parts.append(card("📍 Measuring Points",
                               rows_to_table([r for r in mp_rows if r and any(c.strip() for c in r)]),
                               collapsed=True))

    # ---- Full HTML ----
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Part Report — {escape(filename)}</title>
  <style>
{CSS}
  </style>
</head>
<body>
<div class="page-wrapper">
{"".join(body_parts)}
<p style="text-align:center;color:#aaa;margin-top:28px;font-size:11px">
  Generated by kisler_csv_to_html.py &mdash; {date_str} {time_str}
</p>
</div>
<script>
{JS_TOGGLE}
</script>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def convert_file(csv_path, output_path=None):
    csv_path = Path(csv_path)
    if output_path is None:
        output_path = csv_path.with_suffix(".html")
    else:
        output_path = Path(output_path)

    rows = read_csv_rows(csv_path)
    sections = split_sections(rows)
    html = build_html(csv_path, sections)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✓ {csv_path.name} → {output_path.name}")
    return output_path


def convert_folder(folder_path):
    folder = Path(folder_path)
    csv_files = list(folder.rglob("*.csv"))
    if not csv_files:
        print(f"No CSV files found under {folder}")
        return
    print(f"Converting {len(csv_files)} file(s) in {folder} ...")
    for f in csv_files:
        try:
            convert_file(f)
        except Exception as e:
            print(f"  ✗ {f.name}: {e}")


def find_file(name, search_root=None):
    """
    Find a file by name (or partial name / glob pattern) under search_root.
    Searches cwd if search_root is None.
    Returns a list of matching Path objects.
    """
    root = Path(search_root) if search_root else Path.cwd()
    # exact name match first (recursive)
    matches = list(root.rglob(name))
    if not matches:
        # try as a glob pattern
        matches = list(root.rglob(f"*{name}*"))
    return matches


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = Path(sys.argv[1])

    # 1. Direct hit: absolute path or relative path that exists as-is
    if target.is_dir():
        convert_folder(target)
        return
    if target.is_file():
        out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        convert_file(target, out)
        return

    # 2. Not found directly — search cwd recursively by filename
    print(f"'{target}' not found directly, searching in '{Path.cwd()}' ...")
    matches = find_file(target.name)

    if not matches:
        print(f"Error: no file matching '{target.name}' found under {Path.cwd()}")
        sys.exit(1)

    if len(matches) == 1:
        out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
        convert_file(matches[0], out)
    else:
        print(f"Multiple matches found:")
        for i, m in enumerate(matches):
            print(f"  [{i}] {m}")
        try:
            choice = int(input("Enter number to convert (or -1 to convert all): ").strip())
        except (ValueError, EOFError):
            choice = -1
        if choice == -1:
            for m in matches:
                try:
                    convert_file(m)
                except Exception as e:
                    print(f"  ✗ {m.name}: {e}")
        elif 0 <= choice < len(matches):
            out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
            convert_file(matches[choice], out)
        else:
            print("Invalid choice.")
            sys.exit(1)


if __name__ == "__main__":
    main()
