#!/usr/bin/env python3
"""HMI-PRESS CSV to HTML converter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path

from .press_styles import CSS


JS_TOGGLE = """
(function() {
    var PREFIX = 'press_card_';

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
class PressTable:
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class PressSection:
    name: str
    kv_rows: list[tuple[str, str]] = field(default_factory=list)
    tables: list[PressTable] = field(default_factory=list)


def _read_rows(csv_path: Path) -> list[list[str]]:
    def trim_tail(cells: list[str]) -> list[str]:
        while cells and not cells[-1]:
            cells.pop()
        return cells

    rows: list[list[str]] = []
    for line in csv_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(trim_tail([cell.strip() for cell in line.split(";")]))
    return rows


def _parse_sections(rows: list[list[str]]) -> list[PressSection]:
    sections: list[PressSection] = []
    current_name = "General"
    bucket: list[list[str]] = []

    def flush_section() -> None:
        if not bucket and current_name == "General":
            return
        sections.append(_parse_single_section(current_name, bucket))

    for row in rows:
        first = row[0] if row else ""
        if first.startswith("[") and first.endswith("]") and len(first) > 2:
            flush_section()
            current_name = first[1:-1].strip()
            bucket = []
            continue
        bucket.append(row)

    flush_section()
    return sections


def _parse_single_section(name: str, rows: list[list[str]]) -> PressSection:
    section = PressSection(name=name)
    i = 0
    while i < len(rows):
        row = rows[i]
        head = row[0].strip() if row else ""

        if head.lower() == "$table":
            headers = rows[i + 1] if i + 1 < len(rows) else []
            table = PressTable(headers=headers)
            i += 2
            while i < len(rows):
                candidate = rows[i]
                token = candidate[0].strip().lower() if candidate else ""
                if token.startswith("$") and token != "$table":
                    break
                if token == "$table":
                    break
                if any(cell.strip() for cell in candidate):
                    table.rows.append(candidate)
                i += 1
            section.tables.append(table)
            continue

        key = row[0].strip() if row else ""
        val = row[1].strip() if len(row) > 1 else ""
        if key:
            section.kv_rows.append((key, val))
        i += 1

    return section


def _badge_from_value(value: str) -> str:
    label, css = _normalize_result(value)
    return f'<span class="badge {css}">{escape(label)}</span>'


def _normalize_result(value: str) -> tuple[str, str]:
    v = value.strip().upper()

    # Numeric mapping requested for HMI-PRESS:
    # 0 -> -, 1 -> OK, 2 -> NOK, 3 -> ERROR
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


def _cell_html(value: str, header: str) -> str:
    if not value.strip():
        return ""
    h = header.strip().lower()
    if h == "result":
        return _badge_from_value(value)
    return escape(value)


def _render_kv_table(rows: list[tuple[str, str]]) -> str:
    html = ['<table class="kv">', '<tr><th>Field</th><th>Value</th></tr>']
    for key, val in rows:
        html.append(f"<tr><th>{escape(key)}</th><td>{escape(val)}</td></tr>")
    html.append("</table>")
    return "".join(html)


def _render_data_table(table: PressTable) -> str:
    headers = table.headers or []
    html = ["<table>"]
    if headers:
        html.append("<tr>")
        for h in headers:
            html.append(f"<th>{escape(h)}</th>")
        html.append("</tr>")

    for row in table.rows:
        if not any(c.strip() for c in row):
            continue
        html.append("<tr>")
        width = max(len(headers), len(row))
        for idx in range(width):
            value = row[idx].strip() if idx < len(row) else ""
            header = headers[idx] if idx < len(headers) else ""
            html.append(f"<td>{_cell_html(value, header)}</td>")
        html.append("</tr>")

    html.append("</table>")
    return "".join(html)


def _card(title: str, body_html: str, collapsed: bool = False) -> str:
    c_cls = " collapsed" if collapsed else ""
    b_cls = " hidden" if collapsed else ""
    return (
        '<div class="card">'
        f'<div class="card-header{c_cls}"><span>{escape(title)}</span><span class="toggle-icon">&#9660;</span></div>'
        f'<div class="card-body{b_cls}">{body_html}</div>'
        "</div>"
    )


def _top_info(sections: list[PressSection], csv_name: str) -> tuple[str, str, str, str]:
    header_data = {}
    for s in sections:
        if s.name.lower() == "header":
            header_data = {k: v for k, v in s.kv_rows}
            break

    recipe = header_data.get("Recipe", "")
    sn = header_data.get("SN", "")
    result = header_data.get("Test Result", "") or header_data.get("Result", "")
    dt = f"{header_data.get('Report Date', '')} {header_data.get('Report Time', '')}".strip()
    if not dt:
        dt = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    title = f"HMI-PRESS Report - {csv_name}"
    subtitle = recipe if recipe else "HMI-PRESS CSV report"
    meta = f"SN: {sn} | Generated: {dt}" if sn else f"Generated: {dt}"
    return title, subtitle, meta, result


def rows_to_html(sections: list[PressSection], csv_name: str) -> str:
    title, subtitle, meta, result = _top_info(sections, csv_name)
    result_label, badge_class = _normalize_result(result)
    result_class = badge_class if badge_class in {"ok", "nok", "error"} else "unknown"

    body_parts: list[str] = []
    for section in sections:
        content: list[str] = []
        if section.kv_rows:
            content.append(_render_kv_table(section.kv_rows))
        for idx, table in enumerate(section.tables, start=1):
            if section.name.lower() == "results":
                table_title = "Measurements"
            elif section.name.lower() == "conveyor" and idx == 1:
                table_title = "STATIONS RESULT"
            else:
                table_title = f"Table {idx}"
            content.append(f'<div class="table-title">{escape(table_title)}</div>')
            content.append(_render_data_table(table))

        if not content:
            content.append("<p><em>No data in section.</em></p>")

        collapsed = section.name.lower() not in {"header", "conveyor", "results"}
        body_parts.append(_card(section.name, "".join(content), collapsed=collapsed))

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
  {''.join(body_parts)}
  <div class=\"footer\">Generated by press_csv_to_html.py</div>
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
