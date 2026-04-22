#!/usr/bin/env python3
"""EOL CSV to HTML converter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

from .eol_styles import CSS


FORMATTER_VERSION = "v2"


JS_TOGGLE = """
(function() {
    var PREFIX = 'eol_card_';

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
class EolTable:
    headers: list[str]
    units: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class EolSection:
    name: str
    kv_rows: list[tuple[str, list[str]]] = field(default_factory=list)
    tables: list[EolTable] = field(default_factory=list)


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


def _parse_sections(rows: list[list[str]]) -> list[EolSection]:
    sections: list[EolSection] = []
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
    if not row or not any(cell.strip() for cell in row):
        return False
    unit_like = 0
    data_like = 0
    for cell in row:
        token = cell.strip()
        if not token or token == "-":
            continue
        # Accept common unit formatting issues from exports (e.g. missing closing ']')
        if token.startswith("[") or token.endswith("]"):
            unit_like += 1
            continue
        if _parse_float(token) is not None:
            data_like += 1
            continue
        return False
    return unit_like > 0 and unit_like >= data_like


def _is_table_section(name: str) -> bool:
    lname = name.lower()
    return lname in {"results", "measurement", "measuerement"} or lname.endswith("- measurement")


def _parse_single_section(name: str, rows: list[list[str]]) -> EolSection:
    section = EolSection(name=name)
    if not rows:
        return section

    if _is_table_section(name):
        table = EolTable(headers=[header.strip() for header in rows[0]])
        data_start = 1
        if len(rows) > 1 and _looks_like_units_row(rows[1]):
            table.units = [unit.strip() for unit in rows[1]]
            data_start = 2
        for row in rows[data_start:]:
            if any(cell.strip() for cell in row):
                table.rows.append([cell.strip() for cell in row])
        section.tables.append(table)
        return section

    for row in rows:
        key = row[0].strip() if row else ""
        values = [cell.strip() for cell in row[1:] if cell.strip()]
        if key:
            section.kv_rows.append((key, values))
    return section


def _parse_float(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    value = value.replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _normalize_result(value: str) -> tuple[str, str]:
    token = value.strip().upper()
    if token in {"OK", "PASS", "TRUE"}:
        return "OK", "ok"
    if token in {"NOK", "FAIL", "FALSE"}:
        return "NOK", "nok"
    if token in {"ERROR", "ERR"}:
        return "ERROR", "error"
    if token in {"", "-", "NONE"}:
        return "-", "none"
    return value.strip(), "none"


def _badge_from_value(value: str) -> str:
    label, css = _normalize_result(value)
    return f'<span class="badge {css}">{escape(label)}</span>'


def _filename_result(csv_name: str) -> str:
    parts = Path(csv_name).stem.split("_")
    return parts[-1].strip() if parts else ""


def _section_lookup(sections: list[EolSection], *names: str) -> EolSection | None:
    wanted = {name.lower() for name in names}
    for section in sections:
        if section.name.lower() in wanted:
            return section
    return None


def _header_value(section: EolSection | None, key: str, default: str = "") -> str:
    if section is None:
        return default
    for row_key, values in section.kv_rows:
        if row_key.lower() == key.lower():
            return values[0] if values else default
    return default


def _header_multiline_text(header: str) -> str:
    parts = []
    for part in header.split():
        lower = part.lower()
        if lower == "mean":
            parts.append("[Mean]")
        elif lower == "stddev":
            parts.append("[StdDev]")
        else:
            parts.append(part)
    if len(parts) <= 1:
        return escape(parts[0] if parts else header)
    return f"{escape(parts[0])}<br>{escape(' '.join(parts[1:]))}"


def _format_unit_display(value: str) -> str:
    token = value.strip()
    if not token:
        return value
    return token.replace("mm2", "mm²").replace("m3", "m³")


def _parse_flow_range_entry(value: str) -> tuple[str, str] | None:
    token = value.strip()
    if not token or " - " not in token:
        return None
    range_key, mapped_value = token.split(" - ", 1)
    range_key = range_key.strip()
    mapped_value = mapped_value.strip()
    if not range_key or not mapped_value:
        return None
    return range_key, mapped_value


def _flow_range_key_label(key: str) -> str:
    base = key.split(" - ", 1)[0].strip()
    if "[" in base and "]" in base:
        base = base.split("[", 1)[0].strip()
    return base


def _flow_range_unit_from_key(key: str) -> str:
    if "[" not in key or "]" not in key:
        return ""
    return key[key.find("["):key.find("]") + 1].strip()


def _flow_range_cell_value(value: str, unit: str) -> str:
    token = value.strip()
    if not token:
        return "-"
    return token


def _flow_range_unit(header_section: EolSection | None) -> str:
    if header_section is None:
        return ""
    for row_key, _ in header_section.kv_rows:
        if row_key.lower().strip().startswith("flow range"):
            return _flow_range_unit_from_key(row_key)
    return ""


def _flow_range_mapping(header_section: EolSection | None) -> dict[str, str]:
    if header_section is None:
        return {}

    mapping: dict[str, str] = {}
    for row_key, values in header_section.kv_rows:
        if not row_key.lower().strip().startswith("flow range"):
            continue
        if " - " in row_key and "/" in row_key and values:
            base, suffix = row_key.split(" - ", 1)
            unit = _flow_range_unit_from_key(base)
            labels = [part.strip() for part in suffix.split("/") if part.strip()]
            for idx, value in enumerate(values):
                range_key = labels[idx] if idx < len(labels) else str(idx)
                mapping[range_key] = _flow_range_cell_value(value, unit)
            break
        for value in values:
            parsed = _parse_flow_range_entry(value)
            if parsed is None:
                continue
            range_key, mapped_value = parsed
            mapping[range_key] = mapped_value
        break
    return mapping


def _format_flow_range_value(raw_value: str, header_section: EolSection | None) -> str:
    token = raw_value.strip()
    if not token:
        return raw_value
    return _flow_range_mapping(header_section).get(token, raw_value)


def _render_kv_table(rows: list[tuple[str, list[str]]]) -> str:
    def render_named_subtable(key: str, values: list[str]) -> str:
        if key.lower().strip().startswith("flow range") and values:
            headers = []
            unit_cells = []
            cells = []
            unit = _flow_range_unit_from_key(key)
            labels: list[str] = []
            if " - " in key and "/" in key:
                _, suffix = key.split(" - ", 1)
                labels = [part.strip() for part in suffix.split("/") if part.strip()]
            for idx, value in enumerate(values):
                parsed = _parse_flow_range_entry(value)
                if parsed is not None:
                    header, cell = parsed
                else:
                    header = labels[idx] if idx < len(labels) else str(idx)
                    cell = _flow_range_cell_value(value, unit)
                headers.append(f"<th>{escape(header)}</th>")
                unit_cells.append(f"<td>{escape(_format_unit_display(unit))}</td>")
                cells.append(f"<td>{escape(cell)}</td>")
            unit_row = f"<tr>{''.join(unit_cells)}</tr>" if unit else ""
            return '<table class="kv-sub">' f"<tr>{''.join(headers)}</tr>" f"{unit_row}" f"<tr>{''.join(cells)}</tr>" "</table>"
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
        return '<table class="kv-sub">' f"<tr>{''.join(headers)}</tr>" f"<tr>{''.join(cells)}</tr>" "</table>"

    html = ['<table class="kv">', '<tr><th>Field</th><th>Value</th></tr>']
    for key, values in rows:
        subtable_html = render_named_subtable(key, values)
        joined = " / ".join(values) if values else ""
        val_html = _badge_from_value(joined) if key.lower() in {"result", "test result"} else escape(joined)
        is_compound_row = " - " in key and "/" in key and len(values) > 1
        key_label = _flow_range_key_label(key) if key.lower().strip().startswith("flow range") else (key.split(" - ", 1)[0].strip() if is_compound_row else key)
        if subtable_html:
            val_html = subtable_html
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
    return '<div class="header-split">' f"<div>{left_html}</div>" f"<div>{right_html}</div>" "</div>"


def _render_table(table: EolTable) -> str:
    html = ["<table>", "<tr>"]
    for header in table.headers:
        html.append(f"<th>{_header_multiline_text(header)}</th>")
    html.append("</tr>")
    if table.units:
        html.append("<tr>")
        for idx in range(len(table.headers)):
            unit = table.units[idx] if idx < len(table.units) else ""
            html.append(f"<td>{escape(_format_unit_display(unit))}</td>")
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


def _render_results_table(table: EolTable, header_section: EolSection | None = None) -> str:
    def normalize_header(value: str) -> str:
        return " ".join(value.strip().lower().split())

    lower_headers = [normalize_header(header) for header in table.headers]

    def idx_of(name: str) -> int:
        target = normalize_header(name)
        for idx, header in enumerate(lower_headers):
            if header == target:
                return idx
        return -1

    def idx_of_any(*names: str) -> int:
        for name in names:
            idx = idx_of(name)
            if idx >= 0:
                return idx
        return -1

    idx_mean = idx_of("Aeff Mean")
    idx_min = idx_of_any("Limit Min - Aeff Mean", "Aeff Min")
    idx_max = idx_of_any("Limit Max - Aeff Mean", "Aeff Max")
    idx_stddev = idx_of("Aeff StdDev")
    idx_stddev_max = idx_of_any("Limit Max - Aeff StdDev", "Aeff StdDev Max")
    idx_pressure_out = idx_of("Pressure Out")
    idx_pressure_s3_mean = idx_of("Pressure S3 Mean")
    idx_pressure_s3_min = idx_of("Limit Min - Pressure S3 Mean")
    idx_pressure_s3_max = idx_of("Limit Max - Pressure S3 Mean")
    idx_pressure_s3_stddev = idx_of("Pressure S3 StdDev")
    idx_pressure_s3_stddev_max = idx_of("Limit Max - Pressure S3 StdDev")
    idx_pressure_s4_mean = idx_of("Pressure S4 Mean")
    idx_pressure_s4_min = idx_of("Limit Min - Pressure S4 Mean")
    idx_pressure_s4_max = idx_of("Limit Max - Pressure S4 Mean")
    idx_pressure_s4_stddev = idx_of("Pressure S4 StdDev")
    idx_pressure_s4_stddev_max = idx_of("Limit Max - Pressure S4 StdDev")
    idx_flow_range = idx_of("Flow Range")

    limit_col_indices = {idx for idx, header in enumerate(lower_headers) if header.startswith("limit ")}
    display_indices = [idx for idx in range(len(table.headers)) if idx not in limit_col_indices]

    def value_at(row: list[str], index: int) -> str:
        if index < 0 or index >= len(row):
            return ""
        return row[index]

    def value_at_shifted(row: list[str], index: int) -> str:
        if idx_flow_range >= 0 and index >= idx_flow_range:
            return value_at(row, index - 1)
        return value_at(row, index)

    def parse_num(text: str) -> float | None:
        return _parse_float(text)

    def score_alignment(row: list[str], getter: callable) -> int:
        score = 0
        aeff_min = parse_num(getter(row, idx_min))
        aeff_max = parse_num(getter(row, idx_max))
        s3_min = parse_num(getter(row, idx_pressure_s3_min))
        s3_max = parse_num(getter(row, idx_pressure_s3_max))
        s4_min = parse_num(getter(row, idx_pressure_s4_min))
        s4_max = parse_num(getter(row, idx_pressure_s4_max))
        if aeff_min is not None and aeff_max is not None and aeff_min <= aeff_max:
            score += 1
        if s3_min is not None and s3_max is not None and s3_min <= s3_max:
            score += 1
        if s4_min is not None and s4_max is not None and s4_min <= s4_max:
            score += 1
        return score

    html = ["<table>", "<tr>"]
    for idx in display_indices:
        html.append(f"<th>{_header_multiline_text(table.headers[idx])}</th>")
    html.append("</tr>")

    if table.units:
        html.append("<tr>")
        for idx in display_indices:
            unit = table.units[idx] if idx < len(table.units) else ""
            if idx == idx_flow_range:
                unit = _flow_range_unit(header_section) or unit
            html.append(f"<td>{escape(_format_unit_display(unit))}</td>")
        html.append("</tr>")

    for row in table.rows:
        use_shifted = False
        has_new_limit_headers = min(idx_pressure_s3_min, idx_pressure_s3_max, idx_pressure_s4_min, idx_pressure_s4_max) >= 0
        if idx_flow_range >= 0 and len(row) == len(table.headers) and has_new_limit_headers:
            direct_score = score_alignment(row, value_at)
            shifted_score = score_alignment(row, value_at_shifted)
            use_shifted = shifted_score > direct_score

        row_get = value_at_shifted if use_shifted else value_at

        def row_num(index: int) -> float | None:
            return parse_num(row_get(row, index))

        mean_value = row_num(idx_mean)
        min_value = row_num(idx_min)
        max_value = row_num(idx_max)
        stddev_value = row_num(idx_stddev)
        stddev_max_value = row_num(idx_stddev_max)
        s3_mean_value = row_num(idx_pressure_s3_mean)
        s3_min_value = row_num(idx_pressure_s3_min)
        s3_max_value = row_num(idx_pressure_s3_max)
        s3_stddev_value = row_num(idx_pressure_s3_stddev)
        s3_stddev_max_value = row_num(idx_pressure_s3_stddev_max)
        s4_mean_value = row_num(idx_pressure_s4_mean)
        s4_min_value = row_num(idx_pressure_s4_min)
        s4_max_value = row_num(idx_pressure_s4_max)
        s4_stddev_value = row_num(idx_pressure_s4_stddev)
        s4_stddev_max_value = row_num(idx_pressure_s4_stddev_max)
        pressure_out_value = row_num(idx_pressure_out)

        aeff_mean_ok = mean_value is not None and min_value is not None and max_value is not None and min_value <= mean_value <= max_value
        aeff_stddev_ok = stddev_value is not None and stddev_max_value is not None and stddev_value <= stddev_max_value
        s3_mean_ok = s3_mean_value is not None and s3_min_value is not None and s3_max_value is not None and s3_min_value <= s3_mean_value <= s3_max_value
        s3_stddev_ok = s3_stddev_value is not None and s3_stddev_max_value is not None and s3_stddev_value <= s3_stddev_max_value
        s4_eval_allowed = not (pressure_out_value is not None and pressure_out_value <= 0)
        s4_mean_ok = s4_eval_allowed and s4_mean_value is not None and s4_min_value is not None and s4_max_value is not None and s4_min_value <= s4_mean_value <= s4_max_value
        s4_stddev_ok = s4_eval_allowed and s4_stddev_value is not None and s4_stddev_max_value is not None and s4_stddev_value <= s4_stddev_max_value

        class_by_idx: dict[int, str] = {}
        if min_value is not None and max_value is not None and mean_value is not None:
            class_by_idx[idx_mean] = "check-ok" if aeff_mean_ok else "check-nok"
        if stddev_max_value is not None and stddev_value is not None:
            class_by_idx[idx_stddev] = "check-ok" if aeff_stddev_ok else "check-nok"
        if s3_min_value is not None and s3_max_value is not None and s3_mean_value is not None:
            class_by_idx[idx_pressure_s3_mean] = "check-ok" if s3_mean_ok else "check-nok"
        if s3_stddev_max_value is not None and s3_stddev_value is not None:
            class_by_idx[idx_pressure_s3_stddev] = "check-ok" if s3_stddev_ok else "check-nok"
        if s4_eval_allowed and s4_min_value is not None and s4_max_value is not None and s4_mean_value is not None:
            class_by_idx[idx_pressure_s4_mean] = "check-ok" if s4_mean_ok else "check-nok"
        if s4_eval_allowed and s4_stddev_max_value is not None and s4_stddev_value is not None:
            class_by_idx[idx_pressure_s4_stddev] = "check-ok" if s4_stddev_ok else "check-nok"

        html.append("<tr>")
        for idx in display_indices:
            value = row_get(row, idx)
            if idx == idx_flow_range:
                value = _format_flow_range_value(value, header_section)
            css_class = class_by_idx.get(idx)
            class_attr = f' class="{css_class}"' if css_class else ""
            html.append(f"<td{class_attr}>{escape(value)}</td>")
        html.append("</tr>")

    html.append("</table>")
    return "".join(html)


def _extract_results_by_step(results: EolSection | None) -> tuple[dict[int, list[str]], list[str], list[str]]:
    if results is None or not results.tables:
        return {}, [], []
    table = results.tables[0]
    step_idx = -1
    for idx, name in enumerate(table.headers):
        if name.strip().lower() == "step":
            step_idx = idx
            break
    if step_idx < 0:
        return {}, table.headers, table.units
    by_step: dict[int, list[str]] = {}
    for row in table.rows:
        if len(row) <= step_idx:
            continue
        try:
            step = int(float(row[step_idx].replace(",", ".")))
        except ValueError:
            continue
        by_step[step] = row
    return by_step, table.headers, table.units


def _extract_aeff_by_step(measurement: EolSection | None) -> tuple[dict[int, list[tuple[float, float, float | None]]], str, str, str]:
    if measurement is None or not measurement.tables:
        return {}, "[s]", "[mm2]", "[bar]"
    table = measurement.tables[0]
    lower_headers = [header.lower() for header in table.headers]

    def col_idx(name: str) -> int:
        try:
            return lower_headers.index(name.lower())
        except ValueError:
            return -1

    step_idx = col_idx("step")
    time_idx = col_idx("time")
    aeff_idx = col_idx("aeff")
    pressure_s3_idx = col_idx("pressure s3")
    if min(step_idx, time_idx, aeff_idx) < 0:
        return {}, "[s]", "[mm2]", "[bar]"

    by_step: dict[int, list[tuple[float, float, float | None]]] = {}
    for row in table.rows:
        if len(row) <= max(step_idx, time_idx, aeff_idx):
            continue
        try:
            step = int(float(row[step_idx].strip().replace(",", ".")))
        except ValueError:
            continue
        time_value = _parse_float(row[time_idx])
        aeff_value = _parse_float(row[aeff_idx])
        p3_value = _parse_float(row[pressure_s3_idx]) if pressure_s3_idx >= 0 and len(row) > pressure_s3_idx else None
        if time_value is None or aeff_value is None:
            continue
        by_step.setdefault(step, []).append((time_value, aeff_value, p3_value))

    for points in by_step.values():
        points.sort(key=lambda item: item[0])

    x_unit = table.units[time_idx] if time_idx < len(table.units) and table.units[time_idx] else "[s]"
    y_unit = table.units[aeff_idx] if aeff_idx < len(table.units) and table.units[aeff_idx] else "[mm2]"
    p3_unit = table.units[pressure_s3_idx] if pressure_s3_idx >= 0 and pressure_s3_idx < len(table.units) and table.units[pressure_s3_idx] else "[bar]"
    return by_step, x_unit, y_unit, p3_unit


def _build_step_chart(
    points: list[tuple[float, float, float | None]],
    x_unit: str,
    y_unit: str,
    p3_unit: str,
    aeff_limit_min: float | None = None,
    aeff_limit_max: float | None = None,
    s3_limit_min: float | None = None,
    s3_limit_max: float | None = None,
) -> str:
    if not points:
        return "<p><em>No Aeff data for this step.</em></p>"

    all_x = [point[0] for point in points]
    all_y = [point[1] for point in points]
    p3_points = [(point[0], point[2]) for point in points if point[2] is not None]
    x_min, x_max = min(all_x), max(all_x)

    # Expand y-range to include Aeff limits so limit lines are always visible
    y_candidates = list(all_y)
    if aeff_limit_min is not None:
        y_candidates.append(aeff_limit_min)
    if aeff_limit_max is not None:
        y_candidates.append(aeff_limit_max)
    y_min, y_max = min(y_candidates), max(y_candidates)

    p3_min = min((point[1] for point in p3_points), default=None)
    p3_max = max((point[1] for point in p3_points), default=None)
    # Expand p3 range to include S3 limits
    if p3_points:
        p3_candidates = [v for _, v in p3_points]
        if s3_limit_min is not None:
            p3_candidates.append(s3_limit_min)
        if s3_limit_max is not None:
            p3_candidates.append(s3_limit_max)
        p3_min = min(p3_candidates)
        p3_max = max(p3_candidates)

    if x_max == x_min:
        x_max = x_min + 1.0
    if y_max == y_min:
        y_max = y_min + 1.0
    if p3_min is not None and p3_max is not None and p3_max == p3_min:
        p3_max = p3_min + 1.0

    x_pad = (x_max - x_min) * 0.03
    y_pad = (y_max - y_min) * 0.12
    x_min -= x_pad
    x_max += x_pad
    y_min -= y_pad
    y_max += y_pad

    svg_width = 940
    svg_height = 300
    margin_left = 68
    margin_right = 78
    margin_top = 14
    margin_bottom = 56
    plot_width = svg_width - margin_left - margin_right
    plot_height = svg_height - margin_top - margin_bottom

    def sx(value: float) -> float:
        return margin_left + ((value - x_min) / (x_max - x_min)) * plot_width

    def sy(value: float) -> float:
        return margin_top + plot_height - ((value - y_min) / (y_max - y_min)) * plot_height

    def sy_right(value: float) -> float:
        if p3_min is None or p3_max is None:
            return margin_top + plot_height / 2
        return margin_top + plot_height - ((value - p3_min) / (p3_max - p3_min)) * plot_height

    aeff_poly = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y, _ in points)
    p3_poly = " ".join(f"{sx(x):.2f},{sy_right(v):.2f}" for x, v in p3_points)

    grid_parts: list[str] = []
    tick_count = 6
    for idx in range(tick_count + 1):
        ratio = idx / tick_count
        px = margin_left + plot_width * ratio
        py = margin_top + plot_height * (1 - ratio)
        x_value = x_min + (x_max - x_min) * ratio
        y_value = y_min + (y_max - y_min) * ratio
        grid_parts.append(f'<line x1="{px:.2f}" y1="{margin_top}" x2="{px:.2f}" y2="{margin_top + plot_height}" stroke="#d8dee6" stroke-width="1" />')
        grid_parts.append(f'<line x1="{margin_left}" y1="{py:.2f}" x2="{margin_left + plot_width}" y2="{py:.2f}" stroke="#d8dee6" stroke-width="1" />')
        grid_parts.append(f'<text x="{px:.2f}" y="{svg_height - 28}" class="axis-text" text-anchor="middle">{escape(f"{x_value:.2f}")}</text>')
        grid_parts.append(f'<text x="{margin_left - 10}" y="{py + 4:.2f}" class="axis-text" text-anchor="end">{escape(f"{y_value:.3f}")}</text>')
        if p3_min is not None and p3_max is not None:
            p3_value = p3_min + (p3_max - p3_min) * ratio
            grid_parts.append(f'<text x="{margin_left + plot_width + 10}" y="{py + 4:.2f}" class="axis-text" text-anchor="start">{escape(f"{p3_value:.3f}")}</text>')

    p3_polyline = ""
    right_axis = ""
    right_axis_title = ""
    if p3_points:
        p3_polyline = f'<polyline fill="none" stroke="#b04f00" stroke-width="1.9" points="{p3_poly}" />'
        right_axis = f'<line x1="{margin_left + plot_width}" y1="{margin_top}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.1" />'
        right_axis_title = f'<text x="{svg_width - 16}" y="{margin_top + plot_height / 2:.2f}" class="axis-title" text-anchor="middle" transform="rotate(90 {svg_width - 16} {margin_top + plot_height / 2:.2f})">Pressure S3 {escape(_format_unit_display(p3_unit))}</text>'

    # Aeff limit lines (left axis)
    aeff_limit_lines: list[str] = []
    if aeff_limit_min is not None:
        yp = sy(aeff_limit_min)
        if margin_top <= yp <= margin_top + plot_height:
            aeff_limit_lines.append(
                f'<line x1="{margin_left}" y1="{yp:.2f}" x2="{margin_left + plot_width}" y2="{yp:.2f}" stroke="#0f6cc2" stroke-width="1.5" stroke-dasharray="6 3" />'
                f'<text x="{margin_left + 4}" y="{yp - 3:.2f}" class="axis-text" fill="#0f6cc2">Min {escape(f"{aeff_limit_min:.3f}")}</text>'
            )
    if aeff_limit_max is not None:
        yp = sy(aeff_limit_max)
        if margin_top <= yp <= margin_top + plot_height:
            aeff_limit_lines.append(
                f'<line x1="{margin_left}" y1="{yp:.2f}" x2="{margin_left + plot_width}" y2="{yp:.2f}" stroke="#0f6cc2" stroke-width="1.5" stroke-dasharray="6 3" />'
                f'<text x="{margin_left + 4}" y="{yp - 3:.2f}" class="axis-text" fill="#0f6cc2">Max {escape(f"{aeff_limit_max:.3f}")}</text>'
            )

    # S3 limit lines (right axis)
    s3_limit_lines: list[str] = []
    if p3_points and p3_min is not None and p3_max is not None:
        if s3_limit_min is not None:
            yp = sy_right(s3_limit_min)
            if margin_top <= yp <= margin_top + plot_height:
                s3_limit_lines.append(
                    f'<line x1="{margin_left}" y1="{yp:.2f}" x2="{margin_left + plot_width}" y2="{yp:.2f}" stroke="#b04f00" stroke-width="1.5" stroke-dasharray="3 4" />'
                    f'<text x="{margin_left + plot_width - 4}" y="{yp - 3:.2f}" class="axis-text" fill="#b04f00" text-anchor="end">S3 Min {escape(f"{s3_limit_min:.3f}")}</text>'
                )
        if s3_limit_max is not None:
            yp = sy_right(s3_limit_max)
            if margin_top <= yp <= margin_top + plot_height:
                s3_limit_lines.append(
                    f'<line x1="{margin_left}" y1="{yp:.2f}" x2="{margin_left + plot_width}" y2="{yp:.2f}" stroke="#b04f00" stroke-width="1.5" stroke-dasharray="3 4" />'
                    f'<text x="{margin_left + plot_width - 4}" y="{yp - 3:.2f}" class="axis-text" fill="#b04f00" text-anchor="end">S3 Max {escape(f"{s3_limit_max:.3f}")}</text>'
                )

    legend_limit_items = ""
    if aeff_limit_min is not None or aeff_limit_max is not None:
        legend_limit_items += '<div class="step-legend-item"><span style="display:inline-block;width:18px;height:0;border-top:2px dashed #0f6cc2;vertical-align:middle"></span>&nbsp;<span>Aeff Min/Max</span></div>'
    if s3_limit_min is not None or s3_limit_max is not None:
        legend_limit_items += '<div class="step-legend-item"><span style="display:inline-block;width:18px;height:0;border-top:2px dashed #b04f00;vertical-align:middle"></span>&nbsp;<span>S3 Min/Max</span></div>'

    return f"""
<div class="step-chart">
  <div class="step-legend">
    <div class="step-legend-item"><span class="step-legend-swatch aeff"></span><span>Aeff</span></div>
    <div class="step-legend-item"><span class="step-legend-swatch p3"></span><span>Pressure S3 (right axis)</span></div>
    {legend_limit_items}
  </div>
  <svg viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="none" role="img" aria-label="Aeff time chart">
    <rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#ffffff" />
    <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#cfd8e3" stroke-width="1" />
    {''.join(grid_parts)}
    {''.join(aeff_limit_lines)}
    {''.join(s3_limit_lines)}
    <polyline fill="none" stroke="#0f6cc2" stroke-width="2" points="{aeff_poly}" />
    {p3_polyline}
    <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.3" />
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.3" />
    {right_axis}
    <text x="{margin_left + plot_width / 2:.2f}" y="{svg_height - 8}" class="axis-title" text-anchor="middle">Time {escape(_format_unit_display(x_unit))}</text>
    <text x="18" y="{margin_top + plot_height / 2:.2f}" class="axis-title" text-anchor="middle" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})">Aeff {escape(_format_unit_display(y_unit))}</text>
    {right_axis_title}
  </svg>
</div>
"""


def _render_step_result_row(step: int, headers: list[str], units: list[str], row: list[str] | None, header_section: EolSection | None = None) -> str:
    if not headers:
        return "<p><em>No [Results] table found.</em></p>"
    if row is None:
        return f"<p><em>No [Results] row found for step {step}.</em></p>"

    def normalize_header(value: str) -> str:
        return " ".join(value.strip().lower().split())

    lower_headers = [normalize_header(header) for header in headers]

    def idx_of(name: str) -> int:
        target = normalize_header(name)
        for idx, header in enumerate(lower_headers):
            if header == target:
                return idx
        return -1

    def idx_of_any(*names: str) -> int:
        for name in names:
            idx = idx_of(name)
            if idx >= 0:
                return idx
        return -1

    def value_at(index: int) -> str:
        if index < 0 or index >= len(row):
            return ""
        return row[index]

    def unit_at(index: int) -> str:
        if index < 0 or index >= len(units):
            return ""
        return _format_unit_display(units[index])

    def get_header_value(key: str) -> str:
        """Get a value from the Header section, handling keys with units in brackets."""
        if header_section is None:
            return ""
        key_lower = key.lower().strip()
        for k, values in header_section.kv_rows:
            k_lower = k.lower().strip()
            # Remove content in brackets for comparison
            k_base = k_lower.split('[')[0].strip()
            key_base = key_lower.split('[')[0].strip()
            if k_base == key_base:
                return values[0] if values else ""
        return ""

    idx_min = idx_of_any("Limit Min - Aeff Mean", "Aeff Min")
    idx_max = idx_of_any("Limit Max - Aeff Mean", "Aeff Max")
    idx_mean = idx_of("Aeff Mean")
    idx_stddev = idx_of("Aeff StdDev")
    idx_stddev_max = idx_of_any("Limit Max - Aeff StdDev", "Aeff StdDev Max")
    idx_pressure_in = idx_of("Pressure In")
    idx_pressure_s3_mean = idx_of("Pressure S3 Mean")
    idx_pressure_s3_stddev = idx_of("Pressure S3 StdDev")
    idx_pressure_out = idx_of("Pressure Out")
    idx_pressure_s4_mean = idx_of("Pressure S4 Mean")
    idx_pressure_s4_stddev = idx_of("Pressure S4 StdDev")
    idx_pressure_s3_min = idx_of("Limit Min - Pressure S3 Mean")
    idx_pressure_s3_max = idx_of("Limit Max - Pressure S3 Mean")
    idx_pressure_s3_stddev_max = idx_of("Limit Max - Pressure S3 StdDev")
    idx_pressure_s4_min = idx_of("Limit Min - Pressure S4 Mean")
    idx_pressure_s4_max = idx_of("Limit Max - Pressure S4 Mean")
    idx_pressure_s4_stddev_max = idx_of("Limit Max - Pressure S4 StdDev")
    idx_flow_range = idx_of("Flow Range")

    def value_at_shifted(index: int) -> str:
        # Some EOL exports omit Flow Range in data rows but keep an extra trailing result code.
        # In that case, columns from Flow Range onward are shifted left by one.
        if idx_flow_range >= 0 and index >= idx_flow_range:
            return value_at(index - 1)
        return value_at(index)

    def _score_limit_alignment(get_value: callable) -> int:
        score = 0
        aeff_min = _parse_float(get_value(idx_min))
        aeff_max = _parse_float(get_value(idx_max))
        s3_min = _parse_float(get_value(idx_pressure_s3_min))
        s3_max = _parse_float(get_value(idx_pressure_s3_max))
        s4_min = _parse_float(get_value(idx_pressure_s4_min))
        s4_max = _parse_float(get_value(idx_pressure_s4_max))
        if aeff_min is not None and aeff_max is not None and aeff_min <= aeff_max:
            score += 1
        if s3_min is not None and s3_max is not None and s3_min <= s3_max:
            score += 1
        if s4_min is not None and s4_max is not None and s4_min <= s4_max:
            score += 1
        return score

    use_shifted_limit_columns = False
    has_new_limit_headers = min(idx_pressure_s3_min, idx_pressure_s3_max, idx_pressure_s4_min, idx_pressure_s4_max) >= 0
    if idx_flow_range >= 0 and len(row) == len(headers) and has_new_limit_headers:
        direct_score = _score_limit_alignment(value_at)
        shifted_score = _score_limit_alignment(value_at_shifted)
        use_shifted_limit_columns = shifted_score > direct_score

    def value_at_mapped(index: int) -> str:
        if use_shifted_limit_columns:
            return value_at_shifted(index)
        return value_at(index)

    def parse_num(index: int) -> float | None:
        return _parse_float(value_at_mapped(index))

    mean_value = parse_num(idx_mean)
    min_value = parse_num(idx_min)
    max_value = parse_num(idx_max)
    stddev_value = parse_num(idx_stddev)
    stddev_max_value = parse_num(idx_stddev_max)

    mean_ok = mean_value is not None and min_value is not None and max_value is not None and min_value <= mean_value <= max_value
    stddev_ok = stddev_value is not None and stddev_max_value is not None and stddev_value <= stddev_max_value

    pressure_in_value = parse_num(idx_pressure_in)
    pressure_in_dev_str = get_header_value("Pressure In Dev")
    pressure_in_dev_value = _parse_float(pressure_in_dev_str)
    pressure_s3_mean_value = parse_num(idx_pressure_s3_mean)
    pressure_s3_stddev_value = parse_num(idx_pressure_s3_stddev)
    pressure_out_value = parse_num(idx_pressure_out)
    pressure_out_dev_str = get_header_value("Pressure Out Dev")
    pressure_out_dev_value = _parse_float(pressure_out_dev_str)
    pressure_s4_mean_value = parse_num(idx_pressure_s4_mean)
    pressure_s4_stddev_value = parse_num(idx_pressure_s4_stddev)

    s3_min_from_results = parse_num(idx_pressure_s3_min)
    s3_max_from_results = parse_num(idx_pressure_s3_max)
    s3_stddev_max_from_results = parse_num(idx_pressure_s3_stddev_max)
    s4_min_from_results = parse_num(idx_pressure_s4_min)
    s4_max_from_results = parse_num(idx_pressure_s4_max)
    s4_stddev_max_from_results = parse_num(idx_pressure_s4_stddev_max)

    s3_limits_from_results = (
        pressure_s3_mean_value is not None
        and s3_min_from_results is not None
        and s3_max_from_results is not None
    )
    s4_limits_from_results = (
        pressure_s4_mean_value is not None
        and s4_min_from_results is not None
        and s4_max_from_results is not None
    )

    s3_limits_from_header = (
        pressure_in_value is not None
        and pressure_in_dev_value is not None
        and pressure_s3_mean_value is not None
        and pressure_in_value > 0
    )
    s4_limits_from_header = (
        pressure_out_value is not None
        and pressure_out_dev_value is not None
        and pressure_s4_mean_value is not None
        and pressure_out_value > 0
    )

    s3_has_limits = s3_limits_from_results or s3_limits_from_header
    s4_eval_allowed = not (pressure_out_value is not None and pressure_out_value <= 0)
    s4_has_limits = s4_eval_allowed and (s4_limits_from_results or s4_limits_from_header)

    s3_min = s3_min_from_results if s3_limits_from_results else ((pressure_in_value - pressure_in_dev_value) if s3_limits_from_header else None)
    s3_max = s3_max_from_results if s3_limits_from_results else ((pressure_in_value + pressure_in_dev_value) if s3_limits_from_header else None)
    s4_min = s4_min_from_results if s4_limits_from_results else ((pressure_out_value - pressure_out_dev_value) if s4_limits_from_header else None)
    s4_max = s4_max_from_results if s4_limits_from_results else ((pressure_out_value + pressure_out_dev_value) if s4_limits_from_header else None)

    s3_ok = s3_has_limits and s3_min is not None and s3_max is not None and s3_min <= pressure_s3_mean_value <= s3_max
    s4_ok = s4_has_limits and s4_min is not None and s4_max is not None and s4_min <= pressure_s4_mean_value <= s4_max

    s3_stddev_has_limit = pressure_s3_stddev_value is not None and s3_stddev_max_from_results is not None
    s4_stddev_has_limit = s4_eval_allowed and pressure_s4_stddev_value is not None and s4_stddev_max_from_results is not None
    s3_stddev_ok = s3_stddev_has_limit and pressure_s3_stddev_value <= s3_stddev_max_from_results
    s4_stddev_ok = s4_stddev_has_limit and pressure_s4_stddev_value <= s4_stddev_max_from_results

    mean_result_badge = _badge_from_value("OK" if mean_ok else "NOK")
    stddev_result_badge = _badge_from_value("OK" if stddev_ok else "NOK")
    s3_result_badge = _badge_from_value("OK" if s3_ok else "NOK") if s3_has_limits else _badge_from_value("-")
    s4_result_badge = _badge_from_value("OK" if s4_ok else "NOK") if s4_has_limits else _badge_from_value("-")
    s3_stddev_result_badge = _badge_from_value("OK" if s3_stddev_ok else "NOK") if s3_stddev_has_limit else _badge_from_value("-")
    s4_stddev_result_badge = _badge_from_value("OK" if s4_stddev_ok else "NOK") if s4_stddev_has_limit else _badge_from_value("-")

    limit_col_indices = {idx for idx, header in enumerate(lower_headers) if header.startswith("limit ")}
    display_indices = [idx for idx in range(len(headers)) if idx not in limit_col_indices]

    first_table_class_by_idx: dict[int, str] = {}
    if mean_value is not None and min_value is not None and max_value is not None:
        first_table_class_by_idx[idx_mean] = "check-ok" if mean_ok else "check-nok"
    if stddev_value is not None and stddev_max_value is not None:
        first_table_class_by_idx[idx_stddev] = "check-ok" if stddev_ok else "check-nok"
    if pressure_s3_mean_value is not None and s3_min is not None and s3_max is not None:
        first_table_class_by_idx[idx_pressure_s3_mean] = "check-ok" if s3_ok else "check-nok"
    if pressure_s3_stddev_value is not None and s3_stddev_max_from_results is not None:
        first_table_class_by_idx[idx_pressure_s3_stddev] = "check-ok" if s3_stddev_ok else "check-nok"
    if s4_eval_allowed and pressure_s4_mean_value is not None and s4_min is not None and s4_max is not None:
        first_table_class_by_idx[idx_pressure_s4_mean] = "check-ok" if s4_ok else "check-nok"
    if s4_eval_allowed and pressure_s4_stddev_value is not None and s4_stddev_max_from_results is not None:
        first_table_class_by_idx[idx_pressure_s4_stddev] = "check-ok" if s4_stddev_ok else "check-nok"

    html = ['<div class="step-summary">', "<table>", "<tr>"]
    for idx in display_indices:
        header = headers[idx]
        html.append(f"<th>{_header_multiline_text(header)}</th>")
    html.append("</tr>")

    if units:
        html.append("<tr>")
        for idx in display_indices:
            unit = units[idx] if idx < len(units) else ""
            if idx == idx_flow_range:
                unit = _flow_range_unit(header_section) or unit
            html.append(f"<td>{escape(_format_unit_display(unit))}</td>")
        html.append("</tr>")

    html.append("<tr>")
    for idx in display_indices:
        value = value_at_mapped(idx)
        if idx == idx_flow_range:
            value = _format_flow_range_value(value, header_section)
        css_class = first_table_class_by_idx.get(idx)
        class_attr = f' class="{css_class}"' if css_class else ""
        html.append(f"<td{class_attr}>{escape(value)}</td>")
    html.append("</tr>")
    html.append("</table>")

    mean_col: list[str] = []
    stddev_col: list[str] = []

    # --- Aeff Mean (left) ---
    mean_col.append('<table class="aeff-summary">')
    mean_col.append("<tr><th>Aeff [Mean]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
    mean_col.append(
        "<tr>"
        f"<td>{escape(unit_at(idx_mean))}</td>"
        f"<td>{escape(unit_at(idx_min))}</td>"
        f"<td>{escape(unit_at(idx_max))}</td>"
        "<td></td>"
        "</tr>"
    )
    mean_col.append(
        "<tr>"
        f"<td>{escape(value_at_mapped(idx_mean))}</td>"
        f"<td>{escape(value_at_mapped(idx_min))}</td>"
        f"<td>{escape(value_at_mapped(idx_max))}</td>"
        f"<td>{mean_result_badge}</td>"
        "</tr>"
    )
    mean_col.append("</table>")

    # --- Aeff StdDev (right) ---
    stddev_col.append('<table class="aeff-summary">')
    stddev_col.append("<tr><th>Aeff [StdDev]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
    stddev_col.append(
        "<tr>"
        f"<td>{escape(unit_at(idx_stddev))}</td>"
        "<td></td>"
        f"<td>{escape(unit_at(idx_stddev_max))}</td>"
        "<td></td>"
        "</tr>"
    )
    stddev_col.append(
        "<tr>"
        f"<td>{escape(value_at_mapped(idx_stddev))}</td>"
        "<td>-</td>"
        f"<td>{escape(value_at_mapped(idx_stddev_max))}</td>"
        f"<td>{stddev_result_badge}</td>"
        "</tr>"
    )
    stddev_col.append("</table>")

    # --- Pressure S3 Mean (left) ---
    if s3_has_limits:
        pressure_unit = unit_at(idx_pressure_s3_mean) or unit_at(idx_pressure_in)
        s3_min_unit = unit_at(idx_pressure_s3_min) or unit_at(idx_pressure_in)
        s3_max_unit = unit_at(idx_pressure_s3_max) or unit_at(idx_pressure_in)
        mean_col.append('<table class="aeff-summary">')
        mean_col.append("<tr><th>Pressure S3 [Mean]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
        mean_col.append(
            "<tr>"
            f"<td>{escape(pressure_unit)}</td>"
            f"<td>{escape(s3_min_unit)}</td>"
            f"<td>{escape(s3_max_unit)}</td>"
            "<td></td>"
            "</tr>"
        )
        mean_col.append(
            "<tr>"
            f"<td>{escape(value_at_mapped(idx_pressure_s3_mean))}</td>"
            f"<td>{escape(f'{s3_min:.3f}' if s3_min is not None else '')}</td>"
            f"<td>{escape(f'{s3_max:.3f}' if s3_max is not None else '')}</td>"
            f"<td>{s3_result_badge}</td>"
            "</tr>"
        )
        mean_col.append("</table>")

    # --- Pressure S3 StdDev (right) ---
    if s3_stddev_has_limit:
        s3_stddev_unit = unit_at(idx_pressure_s3_stddev)
        s3_stddev_max_unit = unit_at(idx_pressure_s3_stddev_max) or s3_stddev_unit
        stddev_col.append('<table class="aeff-summary">')
        stddev_col.append("<tr><th>Pressure S3 [StdDev]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
        stddev_col.append(
            "<tr>"
            f"<td>{escape(s3_stddev_unit)}</td>"
            "<td></td>"
            f"<td>{escape(s3_stddev_max_unit)}</td>"
            "<td></td>"
            "</tr>"
        )
        stddev_col.append(
            "<tr>"
            f"<td>{escape(value_at_mapped(idx_pressure_s3_stddev))}</td>"
            "<td>-</td>"
            f"<td>{escape(value_at_mapped(idx_pressure_s3_stddev_max))}</td>"
            f"<td>{s3_stddev_result_badge}</td>"
            "</tr>"
        )
        stddev_col.append("</table>")

    # --- Pressure S4 Mean (left) ---
    if s4_has_limits:
        pressure_unit = unit_at(idx_pressure_s4_mean) or unit_at(idx_pressure_out)
        s4_min_unit = unit_at(idx_pressure_s4_min) or unit_at(idx_pressure_out)
        s4_max_unit = unit_at(idx_pressure_s4_max) or unit_at(idx_pressure_out)
        mean_col.append('<table class="aeff-summary">')
        mean_col.append("<tr><th>Pressure S4 [Mean]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
        mean_col.append(
            "<tr>"
            f"<td>{escape(pressure_unit)}</td>"
            f"<td>{escape(s4_min_unit)}</td>"
            f"<td>{escape(s4_max_unit)}</td>"
            "<td></td>"
            "</tr>"
        )
        mean_col.append(
            "<tr>"
            f"<td>{escape(value_at_mapped(idx_pressure_s4_mean))}</td>"
            f"<td>{escape(f'{s4_min:.3f}' if s4_min is not None else '')}</td>"
            f"<td>{escape(f'{s4_max:.3f}' if s4_max is not None else '')}</td>"
            f"<td>{s4_result_badge}</td>"
            "</tr>"
        )
        mean_col.append("</table>")

    # --- Pressure S4 StdDev (right) ---
    if s4_stddev_has_limit:
        s4_stddev_unit = unit_at(idx_pressure_s4_stddev)
        s4_stddev_max_unit = unit_at(idx_pressure_s4_stddev_max) or s4_stddev_unit
        stddev_col.append('<table class="aeff-summary">')
        stddev_col.append("<tr><th>Pressure S4 [StdDev]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
        stddev_col.append(
            "<tr>"
            f"<td>{escape(s4_stddev_unit)}</td>"
            "<td></td>"
            f"<td>{escape(s4_stddev_max_unit)}</td>"
            "<td></td>"
            "</tr>"
        )
        stddev_col.append(
            "<tr>"
            f"<td>{escape(value_at_mapped(idx_pressure_s4_stddev))}</td>"
            "<td>-</td>"
            f"<td>{escape(value_at_mapped(idx_pressure_s4_stddev_max))}</td>"
            f"<td>{s4_stddev_result_badge}</td>"
            "</tr>"
        )
        stddev_col.append("</table>")

    html.append('<div class="aeff-checks">')
    html.append('<div class="aeff-checks-col">')
    html.extend(mean_col)
    html.append("</div>")
    html.append('<div class="aeff-checks-col">')
    html.extend(stddev_col)
    html.append("</div>")
    html.append("</div>")  # aeff-checks
    html.append("</div>")
    return "".join(html), min_value, max_value, s3_min, s3_max


def _render_uv_kv_table(rows: list[tuple[str, list[str]]], table_class: str = "") -> str:
    """Renders kv rows as Parameter / Unit / Value."""

    def split_parameter_and_unit(key: str) -> tuple[str, str]:
        token = key.strip()
        if token.endswith("]") and "[" in token:
            start = token.rfind("[")
            if start >= 0 and start < len(token) - 1:
                parameter = token[:start].strip()
                unit = token[start:].strip()
                return parameter or token, unit
        return token, ""

    class_attr = f' class="{escape(table_class)}"' if table_class else ""
    html = [f"<table{class_attr}>", "<tr><th>Parameter</th><th>Unit</th><th>Value</th></tr>"]
    for key, values in rows:
        parameter, key_unit = split_parameter_and_unit(key)
        unit = values[0] if len(values) > 1 else key_unit
        value = values[1] if len(values) > 1 else (values[0] if values else "")
        html.append(
            f"<tr><th>{escape(parameter)}</th><td>{escape(_format_unit_display(unit))}</td><td>{escape(value)}</td></tr>"
        )
    html.append("</table>")
    return "".join(html)


def _kv_first_unit_value(section: EolSection, key: str) -> tuple[str, str]:
    """Returns (unit, value) for the first kv row matching key where values=[unit, num]."""
    for k, values in section.kv_rows:
        if k.lower() == key.lower():
            if len(values) >= 2:
                return values[0], values[1]
            if len(values) == 1:
                return "", values[0]
    return "", ""


def _extract_leak_flow_data(measurement: EolSection) -> tuple[list[tuple[float, float]], str, str]:
    """Returns (points, time_unit, flow_unit) from [Leakage - Measurement] table."""
    if not measurement.tables:
        return [], "[s]", "[mg/h]"
    table = measurement.tables[0]
    time_idx = -1
    leak_flow_idx = -1
    for i, h in enumerate(table.headers):
        if h.lower() == "time" and time_idx < 0:
            time_idx = i
    for i, (h, u) in enumerate(zip(table.headers, table.units if table.units else [])):
        if h.lower() == "leak flow" and "[mg/h]" in u.lower():
            leak_flow_idx = i
            break
    if time_idx < 0 or leak_flow_idx < 0:
        return [], "[s]", "[mg/h]"
    x_unit = table.units[time_idx] if time_idx < len(table.units) else "[s]"
    y_unit = table.units[leak_flow_idx] if leak_flow_idx < len(table.units) else "[mg/h]"
    points: list[tuple[float, float]] = []
    for row in table.rows:
        if len(row) <= max(time_idx, leak_flow_idx):
            continue
        t = _parse_float(row[time_idx])
        f = _parse_float(row[leak_flow_idx])
        if t is not None and f is not None:
            points.append((t, f))
    points.sort(key=lambda p: p[0])
    return points, x_unit, y_unit


def _build_leak_flow_chart(
    points: list[tuple[float, float]],
    x_unit: str,
    y_unit: str,
    limit_min: float | None,
    limit_max: float | None,
) -> str:
    if not points:
        return "<p><em>No Leak Flow measurement data found.</em></p>"

    all_x = [p[0] for p in points]
    all_y = [p[1] for p in points]
    y_vals = list(all_y)
    if limit_min is not None:
        y_vals.append(limit_min)
    if limit_max is not None:
        y_vals.append(limit_max)

    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(y_vals), max(y_vals)

    if x_max == x_min:
        x_max = x_min + 1.0
    if y_max == y_min:
        y_max = y_min + 1.0

    x_pad = (x_max - x_min) * 0.03
    y_pad = (y_max - y_min) * 0.12
    x_min -= x_pad
    x_max += x_pad
    y_min -= y_pad
    y_max += y_pad

    svg_width = 940
    svg_height = 300
    margin_left = 68
    margin_right = 24
    margin_top = 14
    margin_bottom = 56
    plot_width = svg_width - margin_left - margin_right
    plot_height = svg_height - margin_top - margin_bottom

    def sx(v: float) -> float:
        return margin_left + ((v - x_min) / (x_max - x_min)) * plot_width

    def sy(v: float) -> float:
        return margin_top + plot_height - ((v - y_min) / (y_max - y_min)) * plot_height

    data_poly = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in points)

    grid_parts: list[str] = []
    for idx in range(7):
        ratio = idx / 6
        px = margin_left + plot_width * ratio
        py = margin_top + plot_height * (1 - ratio)
        xv = x_min + (x_max - x_min) * ratio
        yv = y_min + (y_max - y_min) * ratio
        grid_parts.append(f'<line x1="{px:.2f}" y1="{margin_top}" x2="{px:.2f}" y2="{margin_top + plot_height}" stroke="#d8dee6" stroke-width="1" />')
        grid_parts.append(f'<line x1="{margin_left}" y1="{py:.2f}" x2="{margin_left + plot_width}" y2="{py:.2f}" stroke="#d8dee6" stroke-width="1" />')
        grid_parts.append(f'<text x="{px:.2f}" y="{svg_height - 28}" class="axis-text" text-anchor="middle">{escape(f"{xv:.2f}")}</text>')
        grid_parts.append(f'<text x="{margin_left - 10}" y="{py + 4:.2f}" class="axis-text" text-anchor="end">{escape(f"{yv:.3f}")}</text>')

    limit_lines: list[str] = []
    if limit_min is not None:
        y_px = sy(limit_min)
        limit_lines.append(f'<line x1="{margin_left}" y1="{y_px:.2f}" x2="{margin_left + plot_width}" y2="{y_px:.2f}" stroke="#28a745" stroke-width="1.5" stroke-dasharray="6 3" />')
        limit_lines.append(f'<text x="{margin_left + 4}" y="{y_px - 4:.2f}" class="axis-text" fill="#28a745">Min {escape(f"{limit_min:.3f}")}</text>')
    if limit_max is not None:
        y_px = sy(limit_max)
        limit_lines.append(f'<line x1="{margin_left}" y1="{y_px:.2f}" x2="{margin_left + plot_width}" y2="{y_px:.2f}" stroke="#dc3545" stroke-width="1.5" stroke-dasharray="6 3" />')
        limit_lines.append(f'<text x="{margin_left + 4}" y="{y_px - 4:.2f}" class="axis-text" fill="#dc3545">Max {escape(f"{limit_max:.3f}")}</text>')

    legend_items = '<div class="step-legend-item"><span class="step-legend-swatch leak-flow"></span><span>Leak Flow</span></div>'
    if limit_min is not None:
        legend_items += '<div class="step-legend-item"><span style="display:inline-block;width:18px;height:0;border-top:2px dashed #28a745;vertical-align:middle"></span><span>&nbsp;Min limit</span></div>'
    if limit_max is not None:
        legend_items += '<div class="step-legend-item"><span style="display:inline-block;width:18px;height:0;border-top:2px dashed #dc3545;vertical-align:middle"></span><span>&nbsp;Max limit</span></div>'

    return f"""
<div class="step-chart">
  <div class="step-legend">
    {legend_items}
  </div>
  <svg viewBox="0 0 {svg_width} {svg_height}" preserveAspectRatio="none" role="img" aria-label="Leak Flow time chart">
    <rect x="0" y="0" width="{svg_width}" height="{svg_height}" fill="#ffffff" />
    <rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}" fill="#fbfcfe" stroke="#cfd8e3" stroke-width="1" />
    {''.join(grid_parts)}
    {''.join(limit_lines)}
    <polyline fill="none" stroke="#0a9367" stroke-width="2" points="{data_poly}" />
    <line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.3" />
    <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#5b6570" stroke-width="1.3" />
    <text x="{margin_left + plot_width / 2:.2f}" y="{svg_height - 8}" class="axis-title" text-anchor="middle">Time {escape(_format_unit_display(x_unit))}</text>
    <text x="18" y="{margin_top + plot_height / 2:.2f}" class="axis-title" text-anchor="middle" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})">Leak Flow {escape(_format_unit_display(y_unit))}</text>
  </svg>
</div>
"""


def _render_leakage_limit_checks(leakage: EolSection, leakage_results: EolSection) -> str:
    min_unit, min_val = _kv_first_unit_value(leakage, "Leak Flow Min")
    max_unit, max_val = _kv_first_unit_value(leakage, "Leak Flow Max")
    stddev_max_unit, stddev_max_val = _kv_first_unit_value(leakage, "Leak Flow StdDev Max")
    mean_unit, mean_val = _kv_first_unit_value(leakage_results, "Leak Flow Mean")
    stddev_unit, stddev_val = _kv_first_unit_value(leakage_results, "Leak Flow StdDev")

    mean_f = _parse_float(mean_val)
    min_f = _parse_float(min_val)
    max_f = _parse_float(max_val)
    stddev_f = _parse_float(stddev_val)
    stddev_max_f = _parse_float(stddev_max_val)

    mean_ok = mean_f is not None and min_f is not None and max_f is not None and min_f <= mean_f <= max_f
    stddev_ok = stddev_f is not None and stddev_max_f is not None and stddev_f <= stddev_max_f

    mean_badge = _badge_from_value("OK" if mean_ok else "NOK")
    stddev_badge = _badge_from_value("OK" if stddev_ok else "NOK")

    mean_col: list[str] = []
    stddev_col: list[str] = []

    mean_col.append('<table class="aeff-summary">')
    mean_col.append("<tr><th>Leak Flow [Mean]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
    mean_col.append(
        "<tr>"
        f"<td>{escape(mean_unit)}</td>"
        f"<td>{escape(min_unit)}</td>"
        f"<td>{escape(max_unit)}</td>"
        "<td></td>"
        "</tr>"
    )
    mean_col.append(
        "<tr>"
        f"<td>{escape(mean_val)}</td>"
        f"<td>{escape(min_val)}</td>"
        f"<td>{escape(max_val)}</td>"
        f"<td>{mean_badge}</td>"
        "</tr>"
    )
    mean_col.append("</table>")

    stddev_col.append('<table class="aeff-summary">')
    stddev_col.append("<tr><th>Leak Flow [StdDev]</th><th>Min</th><th>Max</th><th>Result</th></tr>")
    stddev_col.append(
        "<tr>"
        f"<td>{escape(stddev_unit)}</td>"
        "<td></td>"
        f"<td>{escape(stddev_max_unit)}</td>"
        "<td></td>"
        "</tr>"
    )
    stddev_col.append(
        "<tr>"
        f"<td>{escape(stddev_val)}</td>"
        "<td>-</td>"
        f"<td>{escape(stddev_max_val)}</td>"
        f"<td>{stddev_badge}</td>"
        "</tr>"
    )
    stddev_col.append("</table>")

    html = ['<div class="aeff-checks">']
    html.append('<div class="aeff-checks-col">')
    html.extend(mean_col)
    html.append("</div>")
    html.append('<div class="aeff-checks-col">')
    html.extend(stddev_col)
    html.append("</div>")
    html.append("</div>")
    return "".join(html)


def _card(title: str, body_html: str, collapsed: bool = False) -> str:
    c_cls = " collapsed" if collapsed else ""
    b_cls = " hidden" if collapsed else ""
    return '<div class="card">' f'<div class="card-header{c_cls}"><span>{escape(title)}</span><span class="toggle-icon">&#9660;</span></div>' f'<div class="card-body{b_cls}">{body_html}</div>' "</div>"


def rows_to_html(sections: list[EolSection], csv_name: str) -> str:
    header = _section_lookup(sections, "Header")
    conditions = _section_lookup(sections, "Conditions")
    results = _section_lookup(sections, "Results")
    measurement = _section_lookup(sections, "Measurement", "Measuerement")
    leakage = _section_lookup(sections, "Leakage")
    leakage_results = _section_lookup(sections, "Leakage - Results")
    leakage_measurement = _section_lookup(sections, "Leakage - Measurement")

    recipe = _header_value(header, "Recipe")
    test_dt = _header_value(header, "Date Time")
    gen_dt = test_dt or datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    station_name = _header_value(header, "Station Name") or _header_value(header, "Station") or "EOL"
    recipe_name = recipe or "-"
    file_report_name = csv_name

    filename_result = _filename_result(csv_name)
    result_label, badge_class = _normalize_result(filename_result)
    result_class = badge_class if badge_class in {"ok", "nok", "error"} else "unknown"

    results_by_step, result_headers, result_units = _extract_results_by_step(results)
    aeff_by_step, x_unit, y_unit, p3_unit = _extract_aeff_by_step(measurement)

    cards: list[str] = []
    if header and header.kv_rows:
        cards.append(_card("Header", _render_header_split_tables(header.kv_rows), collapsed=False))
    if conditions and conditions.kv_rows:
        cards.append(_card("Conditions", _render_uv_kv_table(conditions.kv_rows, table_class="compact-table"), collapsed=True))
    if results and results.tables:
        cards.append(_card("Results", _render_results_table(results.tables[0], header), collapsed=True))

    if not aeff_by_step:
        cards.append(_card("Measurement Time Graph", "<p><em>No step-based Aeff measurement data found.</em></p>", collapsed=False))
    else:
        for step in sorted(aeff_by_step):
            summary, aeff_lmin, aeff_lmax, s3_lmin, s3_lmax = _render_step_result_row(step, result_headers, result_units, results_by_step.get(step), header)
            chart = _build_step_chart(aeff_by_step[step], x_unit, y_unit, p3_unit, aeff_lmin, aeff_lmax, s3_lmin, s3_lmax)
            cards.append(_card(f"Measurement Time Graph - Step {step}", f'<div class="step-color">Step {step}</div>{summary}{chart}', collapsed=False))

    if leakage or leakage_results or leakage_measurement:
        body: list[str] = []
        if (leakage and leakage.kv_rows) or (leakage_results and leakage_results.kv_rows):
            left_html = "<p><em>No conditions data.</em></p>"
            right_html = "<p><em>No results data.</em></p>"
            if leakage and leakage.kv_rows:
                left_html = '<p class="subsection-label">Conditions</p>' + _render_uv_kv_table(leakage.kv_rows)
            if leakage_results and leakage_results.kv_rows:
                right_html = '<p class="subsection-label">Results</p>' + _render_uv_kv_table(leakage_results.kv_rows)
            body.append('<div class="header-split">' f"<div>{left_html}</div>" f"<div>{right_html}</div>" "</div>")
        if leakage is not None and leakage_results is not None:
            body.append(_render_leakage_limit_checks(leakage, leakage_results))
        if leakage_measurement and leakage_measurement.tables:
            leak_points, leak_x_unit, leak_y_unit = _extract_leak_flow_data(leakage_measurement)
            limit_min: float | None = None
            limit_max: float | None = None
            if leakage is not None:
                _, min_str = _kv_first_unit_value(leakage, "Leak Flow Min")
                _, max_str = _kv_first_unit_value(leakage, "Leak Flow Max")
                limit_min = _parse_float(min_str)
                limit_max = _parse_float(max_str)
            body.append(_build_leak_flow_chart(leak_points, leak_x_unit, leak_y_unit, limit_min, limit_max))
        cards.append(_card("Leakage", "".join(body)))

    title = "Part Protocol Report"
    return f"""<!doctype html>
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
    <div class=\"report-meta\">
      <div>Date time: {escape(gen_dt)}</div>
      <div>File report name: {escape(file_report_name)}</div>
    </div>
  </div>
  <div class=\"result-bar {result_class}\">Result: {escape(result_label or 'UNKNOWN')}</div>
  {''.join(cards)}
    <div class="footer">Generated by eol_csv_to_html.py ({FORMATTER_VERSION})</div>
</div>
<script>
{JS_TOGGLE}
</script>
</body>
</html>"""


def _detect_report_version(sections: list[EolSection]) -> str:
    header = _section_lookup(sections, "Header")
    version = _header_value(header, "Report Version", default="").strip().lower()
    return version


def _convert_with_current_formatter(csv_path: Path, output_path: Path, sections: list[EolSection]) -> Path:
    html = rows_to_html(sections, csv_path.name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def convert_file(csv_path, output_path=None):
    csv_path = Path(csv_path)
    output_path = csv_path.with_suffix(".html") if output_path is None else Path(output_path)
    rows = _read_rows(csv_path)
    sections = _parse_sections(rows)

    report_version = _detect_report_version(sections)

    # Current formatter is the v2 formatter and remains default for empty/missing version.
    if not report_version or report_version.startswith("v2"):
        return _convert_with_current_formatter(csv_path, output_path, sections)

    # v3.0 hook: route to updated converter once available.
    if report_version.startswith("v3"):
        try:
            from .eol_v3 import convert_file as _eol_v3_convert  # type: ignore

            return _eol_v3_convert(csv_path, output_path)
        except Exception:
            # Fallback keeps conversion working until eol_v3 is introduced.
            return _convert_with_current_formatter(csv_path, output_path, sections)

    # Unknown versions fallback to current formatter.
    return _convert_with_current_formatter(csv_path, output_path, sections)
