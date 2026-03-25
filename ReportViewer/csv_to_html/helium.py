#!/usr/bin/env python3
"""HMI-HELIUM CSV to HTML converter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

from .helium_styles import CSS


JS_TOGGLE = """
(function() {
    var PREFIX = 'helium_card_';

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


@dataclass
class HeliumTable:
    headers: list[str]
    units: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class HeliumSection:
    name: str
    kv_rows: list[tuple[str, list[str]]] = field(default_factory=list)
    tables: list[HeliumTable] = field(default_factory=list)


def _read_rows(csv_path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in csv_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        cells = [cell.strip() for cell in line.split(";")]
        while cells and not cells[-1]:
            cells.pop()
        rows.append(cells)
    return rows


def _parse_sections(rows: list[list[str]]) -> list[HeliumSection]:
    sections: list[HeliumSection] = []
    current_name = "General"
    bucket: list[list[str]] = []

    def flush_section() -> None:
        if not bucket and current_name == "General":
            return
        sections.append(_parse_single_section(current_name, bucket))

    for row in rows:
        first = row[0] if row else ""
        # Section delimiters are standalone lines like "[Header]".
        # Unit rows in tables (for example "[s];[1.0E-09];...") must stay in-section.
        if len(row) == 1 and first.startswith("[") and first.endswith("]") and len(first) > 2:
            flush_section()
            current_name = first[1:-1].strip()
            bucket = []
            continue
        bucket.append(row)

    flush_section()
    return sections


def _looks_like_units_row(row: list[str]) -> bool:
    if not row or not any(c.strip() for c in row):
        return False
    score = 0
    for cell in row:
        c = cell.strip()
        if not c:
            continue
        if c.startswith("[") and c.endswith("]"):
            score += 1
        elif c == "-":
            score += 1
        else:
            return False
    return score > 0


def _parse_single_section(name: str, rows: list[list[str]]) -> HeliumSection:
    section = HeliumSection(name=name)
    i = 0
    while i < len(rows):
        row = rows[i]
        token = row[0].strip().lower() if row else ""

        if token == "$table":
            headers = rows[i + 1] if i + 1 < len(rows) else []
            table = HeliumTable(headers=[h.strip() for h in headers])
            i += 2

            if i < len(rows) and _looks_like_units_row(rows[i]):
                table.units = [u.strip() for u in rows[i]]
                i += 1

            while i < len(rows):
                nxt = rows[i]
                nxt_token = nxt[0].strip().lower() if nxt else ""
                if nxt_token == "$table":
                    break
                if any(cell.strip() for cell in nxt):
                    table.rows.append([cell.strip() for cell in nxt])
                i += 1

            section.tables.append(table)
            continue

        key = row[0].strip() if row else ""
        vals = [cell.strip() for cell in row[1:] if cell.strip()]
        if key:
            section.kv_rows.append((key, vals))
        i += 1

    return section


def _normalize_result(value: str) -> tuple[str, str]:
    v = value.strip().upper()

    # Numeric mapping used in HMI station reports.
    if v == "0":
        return "-", "none"
    if v == "1":
        return "OK", "ok"
    if v == "2":
        return "NOK", "nok"
    if v == "3":
        return "ERROR", "error"

    if v in {"OK", "PASS", "TRUE"}:
        return "OK", "ok"
    if v in {"NOK", "FAIL", "FALSE"}:
        return "NOK", "nok"
    if v in {"ERROR", "ERR"}:
        return "ERROR", "error"
    if v in {"", "-"}:
        return "-", "none"

    return value.strip(), "none"


def _badge_from_value(value: str) -> str:
    label, css = _normalize_result(value)
    return f'<span class="badge {css}">{escape(label)}</span>'


def _parse_float(text: str) -> float | None:
    t = text.strip()
    if not t:
        return None

    # Keep only numeric front part for values like "17.8 [s]".
    if " " in t:
        t = t.split(" ", 1)[0]

    t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _extract_leakrate_series(sections: list[HeliumSection]) -> tuple[list[dict], str, str]:
    for section in sections:
        if section.name.lower() != "leakrate":
            continue

        for table in section.tables:
            lower_headers = [h.lower() for h in table.headers]
            if "time" not in lower_headers:
                continue

            leak_idx = -1
            for idx, h in enumerate(lower_headers):
                if h == "leakrate" or h.startswith("leakrate"):
                    leak_idx = idx
                    break
            if leak_idx < 0:
                continue

            time_idx = lower_headers.index("time")
            series = []
            for row in table.rows:
                if len(row) <= max(time_idx, leak_idx):
                    continue
                t = _parse_float(row[time_idx])
                leak = _parse_float(row[leak_idx])
                if t is None or leak is None:
                    continue
                series.append({"time": t, "leakrate": leak})

            x_unit = table.units[time_idx] if time_idx < len(table.units) and table.units[time_idx] else "[s]"
            y_unit = table.units[leak_idx] if leak_idx < len(table.units) and table.units[leak_idx] else "[1.0E-09]"
            return series, x_unit, y_unit

    return [], "[s]", "[1.0E-09]"


def _extract_leakrate_markers(sections: list[HeliumSection]) -> list[dict]:
    markers: list[dict] = []
    for section in sections:
        if section.name.lower() != "measurement":
            continue
        for key, values in section.kv_rows:
            if "leakrate" not in key.lower():
                continue

            leak_val = None
            time_val = None
            for value in values:
                v_lower = value.lower()
                if "[s]" in v_lower:
                    time_val = _parse_float(value)
                elif leak_val is None:
                    leak_val = _parse_float(value)

            if leak_val is None or time_val is None:
                continue
            markers.append({"name": key, "time": time_val, "leakrate": leak_val})
    return markers


def _build_leakrate_chart_html(series: list[dict], markers: list[dict], x_unit: str, y_unit: str) -> str:
    if not series:
        return "<p><em>No leakrate time data found.</em></p>"

    xs = [p["time"] for p in series]
    ys = [p["leakrate"] for p in series]
    x_min = min(xs)
    x_max = max(xs)
    y_min = min(ys)
    y_max = max(ys)

    x_pad = (x_max - x_min) * 0.03 or 1.0
    y_pad = (y_max - y_min) * 0.10 or 0.1
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

    def scale_x(value: float) -> float:
        if x_max == x_min:
            return margin_left + plot_width / 2
        return margin_left + ((value - x_min) / (x_max - x_min)) * plot_width

    def scale_y(value: float) -> float:
        if y_max == y_min:
            return margin_top + plot_height / 2
        return margin_top + plot_height - ((value - y_min) / (y_max - y_min)) * plot_height

    line_points = " ".join(f"{scale_x(p['time']):.2f},{scale_y(p['leakrate']):.2f}" for p in series)

    grid_parts: list[str] = []
    tick_count = 6
    for idx in range(tick_count + 1):
        ratio = idx / tick_count
        px = margin_left + plot_width * ratio
        py = margin_top + plot_height * (1 - ratio)
        x_val = x_min + (x_max - x_min) * ratio
        y_val = y_min + (y_max - y_min) * ratio

        grid_parts.append(
            f'<line x1="{px:.2f}" y1="{margin_top}" x2="{px:.2f}" y2="{margin_top + plot_height}" stroke="#d8dee6" stroke-width="1" />'
        )
        grid_parts.append(
            f'<text x="{px:.2f}" y="{svg_height - 18}" class="chart-axis-text" text-anchor="middle">{escape(f"{x_val:.1f}")}</text>'
        )
        grid_parts.append(
            f'<line x1="{margin_left}" y1="{py:.2f}" x2="{margin_left + plot_width}" y2="{py:.2f}" stroke="#d8dee6" stroke-width="1" />'
        )
        grid_parts.append(
            f'<text x="{margin_left - 10}" y="{py + 4:.2f}" class="chart-axis-text" text-anchor="end">{escape(f"{y_val:.4f}")}</text>'
        )

    marker_parts: list[str] = []
    marker_legend = ""
    if markers:
        marker_legend = '<div class="chart-legend-item"><span class="chart-legend-swatch marker"></span><span>Leakrate checkpoints</span></div>'
        for marker in markers:
            px = scale_x(marker["time"])
            py = scale_y(marker["leakrate"])
            lbl = marker["name"]
            marker_parts.append(
                f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="#f2a900" stroke="#c68500" stroke-width="1.2" />'
            )
            marker_parts.append(
                f'<text x="{px + 6:.2f}" y="{py - 6:.2f}" class="chart-point-label" fill="#8a5a00">{escape(lbl)}</text>'
            )

    return f"""
<div class="chart-container">
  <div class="chart-legend">
    <div class="chart-legend-item"><span class="chart-legend-swatch curve"></span><span>Leakrate over time</span></div>
    {marker_legend}
  </div>
  <svg class="chart-svg" viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="none" role="img" aria-label="Leakrate time chart">
    <rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#ffffff" />
    <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#cfd8e3" stroke-width="1" />
    {''.join(grid_parts)}
    <polyline fill="none" stroke="#0f6cc2" stroke-width="2" points="{line_points}" />
    {''.join(marker_parts)}
    <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.4" />
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.4" />
    <text x="{margin_left + plot_width / 2:.2f}" y="{svg_height - 4}" class="chart-axis-title" text-anchor="middle">Time {escape(x_unit)}</text>
    <text x="18" y="{margin_top + plot_height / 2:.2f}" class="chart-axis-title" text-anchor="middle" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})">Leakrate {escape(y_unit)}</text>
  </svg>
</div>
"""


def _card(title: str, body_html: str, collapsed: bool = False) -> str:
    c_cls = " collapsed" if collapsed else ""
    b_cls = " hidden" if collapsed else ""
    return (
        '<div class="card">'
        f'<div class="card-header{c_cls}"><span>{escape(title)}</span><span class="toggle-icon">&#9660;</span></div>'
        f'<div class="card-body{b_cls}">{body_html}</div>'
        "</div>"
    )


def _render_kv_table(rows: list[tuple[str, list[str]]]) -> str:
    html = ['<table class="kv">', '<tr><th>Field</th><th>Value</th></tr>']
    for key, values in rows:
        if not key:
            continue
        val_str = " | ".join(values) if values else ""
        lower_key = key.lower()
        if lower_key.endswith("result") or lower_key == "result":
            val_str_html = _badge_from_value(val_str)
        else:
            val_str_html = escape(val_str)
        html.append(f"<tr><th>{escape(key)}</th><td>{val_str_html}</td></tr>")
    html.append("</table>")
    return "".join(html)


def _table_cell(value: str, header: str) -> str:
    if not value.strip():
        return ""
    if header.strip().lower() == "result":
        return _badge_from_value(value)
    return escape(value)


def _render_table(table: HeliumTable) -> str:
    html = ["<table>", "<tr>"]
    for h in table.headers:
        html.append(f"<th>{escape(h)}</th>")
    html.append("</tr>")

    if table.units:
        html.append("<tr>")
        for unit in table.units:
            html.append(f"<td>{escape(unit)}</td>")
        html.append("</tr>")

    for row in table.rows:
        html.append("<tr>")
        width = max(len(table.headers), len(row))
        for idx in range(width):
            value = row[idx] if idx < len(row) else ""
            header = table.headers[idx] if idx < len(table.headers) else ""
            html.append(f"<td>{_table_cell(value, header)}</td>")
        html.append("</tr>")

    html.append("</table>")
    return "".join(html)


def _section_lookup(sections: list[HeliumSection], name: str) -> HeliumSection | None:
    for section in sections:
        if section.name.lower() == name.lower():
            return section
    return None


def _header_value(section: HeliumSection | None, key: str, default: str = "") -> str:
    if section is None:
        return default
    key_low = key.lower()
    for row_key, values in section.kv_rows:
        if row_key.lower() == key_low:
            return values[0] if values else default
    return default


def rows_to_html(sections: list[HeliumSection], csv_name: str) -> str:
    header = _section_lookup(sections, "Header")
    conveyor = _section_lookup(sections, "Conveyor")
    measurement = _section_lookup(sections, "Measurement")
    results = _section_lookup(sections, "Results")
    leakrate = _section_lookup(sections, "Leakrate")

    recipe = _header_value(header, "Recipe")
    test_result = _header_value(header, "Test Result")
    sn = _header_value(header, "SN")
    report_date = _header_value(header, "Report Date")
    report_time = _header_value(header, "Report Time")
    gen_dt = f"{report_date} {report_time}".strip() or datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    title = f"HMI-HELIUM Report - {csv_name}"
    subtitle = recipe if recipe else "HMI-HELIUM CSV report"
    meta = f"SN: {sn} | Generated: {gen_dt}" if sn else f"Generated: {gen_dt}"

    result_label, badge_class = _normalize_result(test_result)
    result_class = badge_class if badge_class in {"ok", "nok", "error"} else "unknown"

    series, x_unit, y_unit = _extract_leakrate_series(sections)
    markers = _extract_leakrate_markers(sections)
    chart_html = _build_leakrate_chart_html(series, markers, x_unit, y_unit)

    cards: list[str] = []

    # Keep top section order aligned with HMI-PRESS style cards.
    if header and header.kv_rows:
        cards.append(_card("Header", _render_kv_table(header.kv_rows), collapsed=False))

    if conveyor:
        parts = []
        if conveyor.kv_rows:
            parts.append(_render_kv_table(conveyor.kv_rows))
        for table in conveyor.tables:
            parts.append(_render_table(table))
        cards.append(_card("Conveyor", "".join(parts), collapsed=False))

    if results:
        parts = []
        if results.kv_rows:
            parts.append(_render_kv_table(results.kv_rows))
        for table in results.tables:
            parts.append(_render_table(table))
        cards.append(_card("Results", "".join(parts), collapsed=False))

    # Requested: Measurement and Leakrate sections at the end.
    if measurement and measurement.kv_rows:
        cards.append(_card("Measurement", _render_kv_table(measurement.kv_rows), collapsed=True))

    cards.append(_card("Leakrate Time Graph", chart_html, collapsed=True))

    if leakrate:
        parts = []
        if leakrate.kv_rows:
            parts.append(_render_kv_table(leakrate.kv_rows))
        for table in leakrate.tables:
            parts.append(_render_table(table))
        cards.append(_card("Leakrate Raw Data", "".join(parts), collapsed=True))

    html = f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{escape(csv_name)}</title>
  <style>
{CSS}
  </style>
</head>
<body>
<div class=\"page\">
  <div class=\"report-header\">
    <div>
      <h1>{escape(title)}</h1>
      <div>{escape(subtitle)}</div>
    </div>
    <div class=\"report-meta\">{escape(meta)}</div>
  </div>
  <div class=\"result-bar {result_class}\">Result: {escape(result_label or 'UNKNOWN')}</div>
  {''.join(cards)}
  <div class=\"footer\">Generated by helium_csv_to_html.py</div>
</div>
<script>
{JS_TOGGLE}
</script>
</body>
</html>"""
    return html


def convert_file(csv_path, output_path=None):
    csv_path = Path(csv_path)
    if output_path is None:
        output_path = csv_path.with_suffix(".html")
    else:
        output_path = Path(output_path)

    rows = _read_rows(csv_path)
    sections = _parse_sections(rows)
    html = rows_to_html(sections, csv_path.name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
