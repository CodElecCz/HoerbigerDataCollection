#!/usr/bin/env python3
"""ADJ CSV to HTML converter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

from .adj_styles import CSS


JS_TOGGLE = """
(function() {
    var PREFIX = 'adj_card_';

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

function copyMeasurementCsv(button) {
    var sourceId = button.getAttribute('data-source-id');
    var statusId = button.getAttribute('data-status-id');
    if (!sourceId) return;

    var src = document.getElementById(sourceId);
    var status = statusId ? document.getElementById(statusId) : null;
    if (!src) return;

    var text = src.value || '';

    function setStatus(message, ok) {
        if (!status) return;
        status.textContent = message;
        status.className = ok ? 'copy-status ok' : 'copy-status fail';
        if (ok) {
            console.log('[MeasurementCopy] success: ' + message);
        } else {
            console.error('[MeasurementCopy] failure: ' + message);
        }
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
            .then(function() { setStatus('Copied to clipboard', true); })
            .catch(function() { fallbackCopy(); });
        return;
    }

    fallbackCopy();

    function fallbackCopy() {
        src.style.display = 'block';
        src.select();
        src.setSelectionRange(0, src.value.length);
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        src.style.display = 'none';
        setStatus(ok ? 'Copied to clipboard' : 'Copy failed', ok);
    }
}
"""


@dataclass
class AdjTable:
    headers: list[str]
    units: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class AdjSection:
    name: str
    kv_rows: list[tuple[str, list[str]]] = field(default_factory=list)
    tables: list[AdjTable] = field(default_factory=list)


def _read_rows(csv_path: Path) -> list[list[str]]:
    def split_line(raw: str) -> list[str]:
        # Keep semicolons inside bracketed unit tokens as part of the same cell.
        cells: list[str] = []
        chunk: list[str] = []
        bracket_depth = 0
        for ch in raw:
            if ch == "[":
                bracket_depth += 1
            elif ch == "]" and bracket_depth > 0:
                bracket_depth -= 1

            if ch == ";" and bracket_depth == 0:
                cells.append("".join(chunk).strip())
                chunk = []
                continue
            chunk.append(ch)

        cells.append("".join(chunk).strip())
        return cells

    rows: list[list[str]] = []
    for line in csv_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        cells = split_line(line)
        while cells and not cells[-1]:
            cells.pop()
        rows.append(cells)
    return rows


def _parse_sections(rows: list[list[str]]) -> list[AdjSection]:
    sections: list[AdjSection] = []
    current_name = "General"
    bucket: list[list[str]] = []

    def flush_section() -> None:
        if not bucket and current_name == "General":
            return
        sections.append(_parse_single_section(current_name, bucket))

    for row in rows:
        first = row[0] if row else ""
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
    for cell in row:
        token = cell.strip()
        if not token:
            continue
        if not (token.startswith("[") and token.endswith("]")):
            return False
    return True


def _parse_single_section(name: str, rows: list[list[str]]) -> AdjSection:
    section = AdjSection(name=name)
    if not rows:
        return section

    # ADJ measurement block is a simple table: header row, unit row, then values.
    if name.lower() == "measurement" and len(rows) >= 1:
        table = AdjTable(headers=[h.strip() for h in rows[0]])
        data_start = 1
        if len(rows) > 1 and _looks_like_units_row(rows[1]):
            table.units = [u.strip() for u in rows[1]]
            data_start = 2

        for row in rows[data_start:]:
            if any(cell.strip() for cell in row):
                table.rows.append([cell.strip() for cell in row])

        section.tables.append(table)
        return section

    for row in rows:
        key = row[0].strip() if row else ""
        vals = [cell.strip() for cell in row[1:] if cell.strip()]
        if key:
            section.kv_rows.append((key, vals))

    return section


def _parse_float(value: str) -> float | None:
    v = value.strip()
    if not v:
        return None
    if v.lower() in {"nan", "inf", "-inf"}:
        return None
    v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _normalize_result(value: str) -> tuple[str, str]:
    v = value.strip().upper()
    if v in {"OK", "PASS", "TRUE"}:
        return "OK", "ok"
    if v in {"NOK", "FAIL", "FALSE"}:
        return "NOK", "nok"
    if v in {"ERROR", "ERR"}:
        return "ERROR", "error"
    if v in {"", "-", "NONE"}:
        return "-", "none"
    return value.strip(), "none"


def _badge_from_value(value: str) -> str:
    label, css = _normalize_result(value)
    return f'<span class="badge {css}">{escape(label)}</span>'


def _render_kv_table(rows: list[tuple[str, list[str]]]) -> str:
    def render_named_subtable(key: str, values: list[str]) -> str:
        if " - " not in key or "/" not in key or len(values) <= 1:
            return ""

        _, suffix = key.split(" - ", 1)
        labels = [part.strip() for part in suffix.split("/") if part.strip()]
        width = max(len(labels), len(values))
        if width == 0:
            return ""

        headers = []
        cells = []
        for idx in range(width):
            header = labels[idx] if idx < len(labels) else f"Value {idx + 1}"
            cell = values[idx] if idx < len(values) else ""
            headers.append(f"<th>{escape(header)}</th>")
            cells.append(f"<td>{escape(cell or '-')}</td>")

        return (
            '<table class="kv-sub">'
            f"<tr>{''.join(headers)}</tr>"
            f"<tr>{''.join(cells)}</tr>"
            "</table>"
        )

    def format_values(key: str, values: list[str]) -> str:
        key_l = key.lower()
        subtable_html = render_named_subtable(key, values)
        if subtable_html:
            return subtable_html

        if ("power supply" in key_l or ("voltage" in key_l and "current" in key_l)) and len(values) >= 2:
            return f"{values[0]} V / {values[1]} A"

        if "aeff" in key_l and "target" in key_l and "offset" in key_l and "min" in key_l and "max" in key_l and len(values) >= 5:
            return (
                f"Target: {values[0]} / Offset: {values[1]} / Min: {values[2]} / "
                f"Max: {values[3]} / Offset Max: {values[4]}"
            )

        return " / ".join(values) if values else ""

    html = ['<table class="kv">', '<tr><th>Field</th><th>Value</th></tr>']
    for key, values in rows:
        is_compound_row = " - " in key and "/" in key and len(values) > 1
        key_label = key.split(" - ", 1)[0].strip() if is_compound_row else key
        val_str = format_values(key, values)
        lower_key = key.lower()
        if lower_key in {"result", "test result"}:
            val_html = _badge_from_value(val_str)
        elif val_str.startswith('<table class="kv-sub">'):
            val_html = val_str
        else:
            val_html = escape(val_str)
        html.append(f"<tr><th>{escape(key_label)}</th><td>{val_html}</td></tr>")
    html.append("</table>")
    return "".join(html)


def _render_header_split_tables(rows: list[tuple[str, list[str]]]) -> str:
    left_rows: list[tuple[str, list[str]]] = []
    right_rows: list[tuple[str, list[str]]] = []

    for key, values in rows:
        if key.lower().startswith("sdm"):
            right_rows.append((key, values))
        else:
            left_rows.append((key, values))

    left_html = _render_kv_table(left_rows) if left_rows else "<p><em>No data.</em></p>"
    right_html = _render_kv_table(right_rows) if right_rows else "<p><em>No SDM data.</em></p>"

    return (
        '<div class="header-split">'
        f'<div class="header-split-col">{left_html}</div>'
        f'<div class="header-split-col">{right_html}</div>'
        "</div>"
    )


def _render_table(table: AdjTable) -> str:
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
            html.append(f"<td>{escape(value)}</td>")
        html.append("</tr>")

    html.append("</table>")
    return "".join(html)


def _csv_escape(value: str) -> str:
    if any(ch in value for ch in [';', '"', '\n', '\r']):
        return '"' + value.replace('"', '""') + '"'
    return value


def _build_measurement_section_csv(table: AdjTable) -> str:
    lines: list[str] = ["[Measurement]"]
    lines.append(";".join(_csv_escape(h) for h in table.headers))

    if table.units:
        unit_width = max(len(table.units), len(table.headers))
        unit_cells = [table.units[idx] if idx < len(table.units) else "" for idx in range(unit_width)]
        lines.append(";".join(_csv_escape(u) for u in unit_cells))

    width = len(table.headers)
    for row in table.rows:
        cells = [row[idx] if idx < len(row) else "" for idx in range(width)]
        lines.append(";".join(_csv_escape(c) for c in cells))

    return "\n".join(lines) + "\n"


def _render_measurement_overview(table: AdjTable, csv_name: str) -> str:
    sample_count = len(table.rows)

    header_cells = "".join(f"<th>{escape(h)}</th>" for h in table.headers)
    units_cells = "".join(
        f"<td>{escape(table.units[idx] if idx < len(table.units) else '')}</td>" for idx in range(len(table.headers))
    )

    measurement_csv = _build_measurement_section_csv(table)
    source_key = "".join(ch if ch.isalnum() else "_" for ch in Path(csv_name).stem)
    source_id = f"measurement_csv_{source_key}"
    status_id = f"measurement_status_{source_key}"

    return (
        '<div class="measurement-overview">'
        f'<div class="measurement-samples">Number Of Samples: <strong>{sample_count}</strong></div>'
        '<table class="measurement-header-only">'
        f"<tr>{header_cells}</tr>"
        f"<tr>{units_cells}</tr>"
        "</table>"
        '<div class="measurement-actions">'
        '<a class="btn-copy" href="https://reportviewer.local/copy-measurement">Copy data to Clipboard</a>'
        f'<span id="{escape(status_id)}" class="copy-status"></span>'
        "</div>"
        f'<textarea id="{escape(source_id)}" class="measurement-csv-source" aria-hidden="true">{escape(measurement_csv)}</textarea>'
        "</div>"
    )


def _card(title: str, body_html: str, collapsed: bool = False) -> str:
    c_cls = " collapsed" if collapsed else ""
    b_cls = " hidden" if collapsed else ""
    return (
        '<div class="card">'
        f'<div class="card-header{c_cls}"><span>{escape(title)}</span><span class="toggle-icon">&#9660;</span></div>'
        f'<div class="card-body{b_cls}">{body_html}</div>'
        "</div>"
    )


def _section_lookup(sections: list[AdjSection], name: str) -> AdjSection | None:
    for section in sections:
        if section.name.lower() == name.lower():
            return section
    return None


def _header_value(section: AdjSection | None, key: str, default: str = "") -> str:
    if section is None:
        return default
    key_low = key.lower()
    for row_key, values in section.kv_rows:
        if row_key.lower() == key_low:
            return values[0] if values else default
    return default


def _header_aeff_target_value(section: AdjSection | None) -> float | None:
    if section is None:
        return None
    for row_key, values in section.kv_rows:
        if row_key.lower().startswith("aeff - target"):
            if not values:
                return None
            return _parse_float(values[0])
    return None


def _filename_result(csv_name: str) -> str:
    stem = Path(csv_name).stem
    parts = stem.split("_")
    if parts:
        return parts[-1].strip()
    return ""


def _extract_aeff_series(measurement: AdjSection | None) -> tuple[list[dict], str, str]:
    if measurement is None or not measurement.tables:
        return [], "[s]", "[mm2]"

    table = measurement.tables[0]
    lower_headers = [h.lower() for h in table.headers]

    def col_idx(name: str) -> int:
        try:
            return lower_headers.index(name.lower())
        except ValueError:
            return -1

    time_idx = col_idx("Time")
    calc_idx = col_idx("Aeff Calc Actual")
    meas_idx = col_idx("Aeff Meas Actual")
    target_final_idx = col_idx("Aeff Target")
    target_step_idx = col_idx("Aeff Target Step")
    position_idx = col_idx("Position")

    if min(time_idx, calc_idx, meas_idx) < 0:
        return [], "[s]", "[mm2]"

    if target_final_idx < 0 and target_step_idx < 0:
        return [], "[s]", "[mm2]"

    series: list[dict] = []
    max_required_idx = max(time_idx, calc_idx, meas_idx)
    for row in table.rows:
        if len(row) <= max_required_idx:
            continue

        t = _parse_float(row[time_idx])
        calc = _parse_float(row[calc_idx])
        meas = _parse_float(row[meas_idx])
        target_final = _parse_float(row[target_final_idx]) if target_final_idx >= 0 else None
        target_step = _parse_float(row[target_step_idx]) if target_step_idx >= 0 else None
        position = _parse_float(row[position_idx]) if position_idx >= 0 and len(row) > position_idx else None
        if t is None:
            continue

        series.append(
            {
                "time": t,
                "calc": calc,
                "meas": meas,
                "target_final": target_final,
                "target_step": target_step,
                "position": position,
            }
        )

    x_unit = table.units[time_idx] if time_idx < len(table.units) and table.units[time_idx] else "[s]"
    y_unit = table.units[calc_idx] if calc_idx < len(table.units) and table.units[calc_idx] else "[mm2]"
    return series, x_unit, y_unit


def _build_aeff_chart_html(series: list[dict], x_unit: str, y_unit: str, header_aeff_target: float | None = None) -> str:
    points_calc = [p for p in series if p["calc"] is not None]
    points_meas = [p for p in series if p["meas"] is not None]
    points_target_final = [p for p in series if p["target_final"] is not None]
    points_target_step = [p for p in series if p["target_step"] is not None]
    points_position = [p for p in series if p["position"] is not None]

    if not points_calc and not points_meas:
        return "<p><em>No Aeff measurement data found.</em></p>"

    all_x = [p["time"] for p in series if p["time"] is not None]
    all_y_left = []
    all_y_left.extend(p["calc"] for p in points_calc)
    all_y_left.extend(p["meas"] for p in points_meas)
    all_y_left.extend(p["target_final"] for p in points_target_final)
    all_y_left.extend(p["target_step"] for p in points_target_step)

    if not all_x or not all_y_left:
        return "<p><em>No plottable Aeff data found.</em></p>"

    x_min = min(all_x)
    x_max = max(all_x)
    y_min = min(all_y_left)
    y_max = max(all_y_left)

    if header_aeff_target is not None:
        y_min = header_aeff_target - 1.0
        if y_max <= y_min:
            y_max = y_min + 1.0

    x_pad = (x_max - x_min) * 0.03 or 1.0
    x_min -= x_pad
    x_max += x_pad
    y_pad = (y_max - y_min) * 0.12 or 0.5
    if header_aeff_target is None:
        y_min -= y_pad
    y_max += y_pad

    pos_min = min((p["position"] for p in points_position), default=None)
    pos_max = max((p["position"] for p in points_position), default=None)
    if pos_min is not None and pos_max is not None and pos_max == pos_min:
        pos_max = pos_min + 1.0

    svg_width = 1020
    svg_height = 460
    margin_left = 72
    margin_right = 88
    margin_top = 18
    margin_bottom = 90
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

    def scale_y_clamped(value: float) -> float:
        if value < y_min:
            return scale_y(y_min)
        if value > y_max:
            return scale_y(y_max)
        return scale_y(value)

    def scale_y_right(value: float) -> float:
        if pos_min is None or pos_max is None or pos_max == pos_min:
            return margin_top + plot_height / 2
        return margin_top + plot_height - ((value - pos_min) / (pos_max - pos_min)) * plot_height

    calc_points = " ".join(f"{scale_x(p['time']):.2f},{scale_y_clamped(p['calc']):.2f}" for p in points_calc)
    meas_points = " ".join(f"{scale_x(p['time']):.2f},{scale_y_clamped(p['meas']):.2f}" for p in points_meas)
    target_final_points = " ".join(
        f"{scale_x(p['time']):.2f},{scale_y_clamped(p['target_final']):.2f}" for p in points_target_final
    )
    target_step_points = " ".join(
        f"{scale_x(p['time']):.2f},{scale_y_clamped(p['target_step']):.2f}" for p in points_target_step
    )
    position_points = " ".join(
        f"{scale_x(p['time']):.2f},{scale_y_right(p['position']):.2f}" for p in points_position
    )

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
            f'<text x="{px:.2f}" y="{svg_height - 34}" class="chart-axis-text" text-anchor="middle">{escape(f"{x_val:.2f}")}</text>'
        )
        grid_parts.append(
            f'<line x1="{margin_left}" y1="{py:.2f}" x2="{margin_left + plot_width}" y2="{py:.2f}" stroke="#d8dee6" stroke-width="1" />'
        )
        grid_parts.append(
            f'<text x="{margin_left - 10}" y="{py + 4:.2f}" class="chart-axis-text" text-anchor="end">{escape(f"{y_val:.3f}")}</text>'
        )
        if pos_min is not None and pos_max is not None:
            pos_val = pos_min + (pos_max - pos_min) * ratio
            grid_parts.append(
                f'<text x="{margin_left + plot_width + 12}" y="{py + 4:.2f}" class="chart-axis-text" text-anchor="start">{escape(f"{pos_val:.3f}")}</text>'
            )

    position_legend = ""
    position_polyline = ""
    right_axis_line = ""
    right_axis_title = ""
    if points_position:
        position_legend = '<div class="chart-legend-item"><span class="chart-legend-swatch position"></span><span>Position [mm] (right axis)</span></div>'
        position_polyline = f'<polyline fill="none" stroke="#7a4b2a" stroke-width="1.8" points="{position_points}" />'
        right_axis_line = f'<line x1="{margin_left + plot_width}" y1="{margin_top}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.1" />'
        right_axis_title = f'<text x="{svg_width - 20}" y="{margin_top + plot_height / 2:.2f}" class="chart-axis-title" text-anchor="middle" transform="rotate(90 {svg_width - 20} {margin_top + plot_height / 2:.2f})">Position [mm]</text>'

    return f"""
<div class="chart-container">
  <div class="chart-legend">
    <div class="chart-legend-item"><span class="chart-legend-swatch calc"></span><span>Aeff Calc Actual</span></div>
    <div class="chart-legend-item"><span class="chart-legend-swatch meas"></span><span>Aeff Meas Actual</span></div>
        <div class="chart-legend-item"><span class="chart-legend-swatch target-final"></span><span>Aeff Target (final required)</span></div>
        <div class="chart-legend-item"><span class="chart-legend-swatch target-step"></span><span>Aeff Target Step (current step required)</span></div>
        {position_legend}
  </div>
  <svg class="chart-svg" viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="none" role="img" aria-label="Aeff time chart">
    <rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#ffffff" />
    <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#cfd8e3" stroke-width="1" />
    {''.join(grid_parts)}
    <polyline fill="none" stroke="#0f6cc2" stroke-width="2" points="{calc_points}" />
    <polyline fill="none" stroke="#18a06c" stroke-width="2" points="{meas_points}" />
    <polyline fill="none" stroke="#c68500" stroke-width="2" stroke-dasharray="7 5" points="{target_final_points}" />
    <polyline fill="none" stroke="#8c4d15" stroke-width="2" stroke-dasharray="2 4" points="{target_step_points}" />
        {position_polyline}
    <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.4" />
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.4" />
        {right_axis_line}
    <text x="{margin_left + plot_width / 2:.2f}" y="{svg_height - 10}" class="chart-axis-title" text-anchor="middle">Time {escape(x_unit)}</text>
    <text x="18" y="{margin_top + plot_height / 2:.2f}" class="chart-axis-title" text-anchor="middle" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})">Aeff {escape(y_unit)}</text>
        {right_axis_title}
  </svg>
</div>
"""


def rows_to_html(sections: list[AdjSection], csv_name: str) -> str:
    header = _section_lookup(sections, "Header")
    results = _section_lookup(sections, "Results")
    measurement = _section_lookup(sections, "Measurement")

    recipe = _header_value(header, "Recipe")
    test_dt = _header_value(header, "Date Time")
    gen_dt = test_dt or datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    station_name = _header_value(header, "Station Name") or _header_value(header, "Station") or "ADJ"
    recipe_name = recipe or "-"
    file_report_name = csv_name

    filename_result = _filename_result(csv_name)
    result_label, badge_class = _normalize_result(filename_result)
    result_class = badge_class if badge_class in {"ok", "nok", "error"} else "unknown"

    title = "Part Protocol Report"

    series, x_unit, y_unit = _extract_aeff_series(measurement)
    header_aeff_target = _header_aeff_target_value(header)
    chart_html = _build_aeff_chart_html(series, x_unit, y_unit, header_aeff_target)

    cards: list[str] = []

    if header and header.kv_rows:
        cards.append(_card("Header", _render_header_split_tables(header.kv_rows), collapsed=False))

    if results and results.kv_rows:
        cards.append(_card("Results", _render_kv_table(results.kv_rows), collapsed=False))

    cards.append(_card("Measurement Time Graph", chart_html, collapsed=False))

    if measurement and measurement.tables:
        cards.append(_card("Measurement Raw Data", _render_measurement_overview(measurement.tables[0], csv_name), collapsed=True))

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
    <h1>&#128202; {escape(title)}</h1>
            <div>Station name: {escape(station_name)}</div>
            <div>Recipe name: {escape(recipe_name)}</div>
    </div>
        <div class="report-meta">
            <div>Date time: {escape(gen_dt)}</div>
            <div>File report name: {escape(file_report_name)}</div>
        </div>
  </div>
  <div class=\"result-bar {result_class}\">Result: {escape(result_label or 'UNKNOWN')}</div>
  {''.join(cards)}
  <div class=\"footer\">Generated by adj_csv_to_html.py</div>
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
