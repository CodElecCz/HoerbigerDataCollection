#!/usr/bin/env python3
"""Generic EOL multi-report statistics renderer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from statistics import mean

from .eol import (
    JS_TOGGLE,
    _card,
    _extract_results_by_step,
    _kv_first_unit_value,
    _parse_float,
    _parse_sections,
    _read_rows,
    _section_lookup,
)
from .eol_styles import CSS


FORMATTER_VERSION = "v2"


@dataclass
class StatisticEntry:
    csv_path: Path
    station: str
    serial: str
    date_text: str
    time_text: str
    result: str
    value: float


@dataclass
class MetricValue:
    title: str
    unit: str
    value: float
    result: str


@dataclass
class SectionMetrics:
    title: str
    metrics: list[MetricValue]


@dataclass
class ReportStatisticsData:
    csv_path: Path
    station: str
    serial: str
    date_text: str
    time_text: str
    result: str
    sections: list[SectionMetrics]


@dataclass
class AggregatedMetric:
    title: str
    unit: str
    entries: list[StatisticEntry]


@dataclass
class AggregatedSection:
    title: str
    metrics: list[AggregatedMetric]


def _parse_identity(csv_path: Path) -> tuple[str, str, str, str, str]:
    parts = csv_path.stem.split("_")
    if len(parts) == 5 and parts[0].upper() == "EOL":
        return parts[0].upper(), parts[3], parts[1], parts[2], parts[4].upper()
    return "EOL", "", "", "", ""


def _format_number(value: float) -> str:
    return f"{value:.3f}"


def _result_badge(result: str) -> str:
    token = result.strip().upper()
    badge_class = "none"
    if token == "OK":
        badge_class = "ok"
    elif token == "NOK":
        badge_class = "nok"
    elif token in {"ERROR", "ERR"}:
        badge_class = "error"
    label = token or "-"
    return f'<span class="badge {badge_class}">{escape(label)}</span>'


def _collect_results_metrics(row: list[str], headers: list[str], units: list[str], header_section) -> list[MetricValue]:
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
        return units[index]

    def get_header_value(key: str) -> str:
        if header_section is None:
            return ""
        key_lower = key.lower().strip()
        for row_key, values in header_section.kv_rows:
            row_base = row_key.lower().strip().split("[")[0].strip()
            key_base = key_lower.split("[")[0].strip()
            if row_base == key_base:
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
        if idx_flow_range >= 0 and index >= idx_flow_range:
            return value_at(index - 1)
        return value_at(index)

    def _score_limit_alignment(get_value) -> int:
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

    metrics: list[MetricValue] = []

    mean_value = parse_num(idx_mean)
    min_value = parse_num(idx_min)
    max_value = parse_num(idx_max)
    if mean_value is not None and min_value is not None and max_value is not None:
        mean_ok = min_value <= mean_value <= max_value
        metrics.append(MetricValue("Aeff [Mean]", unit_at(idx_mean), mean_value, "OK" if mean_ok else "NOK"))

    stddev_value = parse_num(idx_stddev)
    stddev_max_value = parse_num(idx_stddev_max)
    if stddev_value is not None and stddev_max_value is not None:
        stddev_ok = stddev_value <= stddev_max_value
        metrics.append(MetricValue("Aeff [StdDev]", unit_at(idx_stddev), stddev_value, "OK" if stddev_ok else "NOK"))

    pressure_in_value = parse_num(idx_pressure_in)
    pressure_s3_mean_value = parse_num(idx_pressure_s3_mean)
    pressure_s3_stddev_value = parse_num(idx_pressure_s3_stddev)
    pressure_out_value = parse_num(idx_pressure_out)
    pressure_s4_mean_value = parse_num(idx_pressure_s4_mean)
    pressure_s4_stddev_value = parse_num(idx_pressure_s4_stddev)
    pressure_in_dev_value = _parse_float(get_header_value("Pressure In Dev"))
    pressure_out_dev_value = _parse_float(get_header_value("Pressure Out Dev"))

    s3_min_from_results = parse_num(idx_pressure_s3_min)
    s3_max_from_results = parse_num(idx_pressure_s3_max)
    s3_stddev_max_from_results = parse_num(idx_pressure_s3_stddev_max)
    s4_min_from_results = parse_num(idx_pressure_s4_min)
    s4_max_from_results = parse_num(idx_pressure_s4_max)
    s4_stddev_max_from_results = parse_num(idx_pressure_s4_stddev_max)

    s3_limits_from_results = (
        pressure_s3_mean_value is not None and s3_min_from_results is not None and s3_max_from_results is not None
    )
    s4_limits_from_results = (
        pressure_s4_mean_value is not None and s4_min_from_results is not None and s4_max_from_results is not None
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

    if pressure_s3_mean_value is not None and s3_has_limits:
        s3_ok = s3_min is not None and s3_max is not None and s3_min <= pressure_s3_mean_value <= s3_max
        metrics.append(
            MetricValue(
                "Pressure S3 [Mean]",
                unit_at(idx_pressure_s3_mean) or unit_at(idx_pressure_in),
                pressure_s3_mean_value,
                "OK" if s3_ok else "NOK",
            )
        )
    if pressure_s3_stddev_value is not None and s3_stddev_max_from_results is not None:
        s3_stddev_ok = pressure_s3_stddev_value <= s3_stddev_max_from_results
        metrics.append(
            MetricValue(
                "Pressure S3 [StdDev]",
                unit_at(idx_pressure_s3_stddev),
                pressure_s3_stddev_value,
                "OK" if s3_stddev_ok else "NOK",
            )
        )
    if pressure_s4_mean_value is not None and s4_has_limits:
        s4_ok = s4_min is not None and s4_max is not None and s4_min <= pressure_s4_mean_value <= s4_max
        metrics.append(
            MetricValue(
                "Pressure S4 [Mean]",
                unit_at(idx_pressure_s4_mean) or unit_at(idx_pressure_out),
                pressure_s4_mean_value,
                "OK" if s4_ok else "NOK",
            )
        )
    if pressure_s4_stddev_value is not None and s4_eval_allowed and s4_stddev_max_from_results is not None:
        s4_stddev_ok = pressure_s4_stddev_value <= s4_stddev_max_from_results
        metrics.append(
            MetricValue(
                "Pressure S4 [StdDev]",
                unit_at(idx_pressure_s4_stddev),
                pressure_s4_stddev_value,
                "OK" if s4_stddev_ok else "NOK",
            )
        )

    return metrics


def _collect_leakage_metrics(leakage, leakage_results) -> list[MetricValue]:
    if leakage is None or leakage_results is None:
        return []

    metrics: list[MetricValue] = []
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

    if mean_f is not None and min_f is not None and max_f is not None:
        mean_ok = min_f <= mean_f <= max_f
        metrics.append(MetricValue("Leak Flow [Mean]", mean_unit or min_unit or max_unit, mean_f, "OK" if mean_ok else "NOK"))
    if stddev_f is not None and stddev_max_f is not None:
        stddev_ok = stddev_f <= stddev_max_f
        metrics.append(MetricValue("Leak Flow [StdDev]", stddev_unit or stddev_max_unit, stddev_f, "OK" if stddev_ok else "NOK"))
    return metrics


def _parse_report_statistics(csv_path: Path) -> ReportStatisticsData:
    sections = _parse_sections(_read_rows(csv_path))
    header = _section_lookup(sections, "Header")
    results = _section_lookup(sections, "Results")
    leakage = _section_lookup(sections, "Leakage")
    leakage_results = _section_lookup(sections, "Leakage - Results")
    station, serial, date_text, time_text, result = _parse_identity(csv_path)

    results_by_step, result_headers, result_units = _extract_results_by_step(results)
    section_list: list[SectionMetrics] = []
    for step in sorted(results_by_step):
        metrics = _collect_results_metrics(results_by_step[step], result_headers, result_units, header)
        if metrics:
            section_list.append(SectionMetrics(f"Measurement Time Graph - Step {step}", metrics))

    leakage_metrics = _collect_leakage_metrics(leakage, leakage_results)
    if leakage_metrics:
        section_list.append(SectionMetrics("Leakage", leakage_metrics))

    return ReportStatisticsData(
        csv_path=csv_path,
        station=station,
        serial=serial,
        date_text=date_text,
        time_text=time_text,
        result=result,
        sections=section_list,
    )


def _aggregate_sections(reports: list[ReportStatisticsData]) -> list[AggregatedSection]:
    if not reports:
        return []

    aggregated_sections: list[AggregatedSection] = []
    template_report = reports[0]
    for template_section in template_report.sections:
        metrics: list[AggregatedMetric] = []
        for template_metric in template_section.metrics:
            entries: list[StatisticEntry] = []
            for report in reports:
                section = next((item for item in report.sections if item.title == template_section.title), None)
                if section is None:
                    continue
                metric = next((item for item in section.metrics if item.title == template_metric.title), None)
                if metric is None:
                    continue
                entries.append(
                    StatisticEntry(
                        csv_path=report.csv_path,
                        station=report.station,
                        serial=report.serial,
                        date_text=report.date_text,
                        time_text=report.time_text,
                        result=metric.result,
                        value=metric.value,
                    )
                )
            if entries:
                metrics.append(AggregatedMetric(template_metric.title, template_metric.unit, entries))
        if metrics:
            aggregated_sections.append(AggregatedSection(template_section.title, metrics))
    return aggregated_sections


def _render_summary_table(metric: AggregatedMetric) -> str:
    values = [entry.value for entry in metric.entries]
    return (
        '<table class="compact-table">'
        '<tr><th>Metric</th><th>Value</th></tr>'
        f'<tr><th>Reports</th><td>{len(metric.entries)}</td></tr>'
        f'<tr><th>Average {escape(metric.unit)}</th><td>{escape(_format_number(mean(values)))}</td></tr>'
        f'<tr><th>Minimum {escape(metric.unit)}</th><td>{escape(_format_number(min(values)))}</td></tr>'
        f'<tr><th>Maximum {escape(metric.unit)}</th><td>{escape(_format_number(max(values)))}</td></tr>'
        '</table>'
    )


def _render_detail_table(metric: AggregatedMetric) -> str:
    rows: list[str] = []
    for entry in sorted(
        metric.entries,
        key=lambda item: (item.date_text, item.time_text, item.serial, item.csv_path.name),
        reverse=True,
    ):
        rows.append(
            "".join(
                [
                    "<tr>",
                    f"<td>{escape(entry.serial)}</td>",
                    f"<td>{escape(entry.date_text)}</td>",
                    f"<td>{escape(entry.time_text)}</td>",
                    f"<td>{escape(_format_number(entry.value))}</td>",
                    f"<td>{_result_badge(entry.result)}</td>",
                    f"<td>{escape(entry.csv_path.name)}</td>",
                    "</tr>",
                ]
            )
        )
    return (
        "<table>"
        "<tr>"
        "<th>SN</th>"
        "<th>Date</th>"
        "<th>Time</th>"
        f"<th>{escape(metric.title)} {escape(metric.unit)}</th>"
        "<th>Result</th>"
        "<th>File</th>"
        "</tr>"
        f"{''.join(rows)}"
        "</table>"
    )


def _render_section(section: AggregatedSection) -> str:
    body: list[str] = []
    for metric in section.metrics:
        body.append(f'<p class="subsection-label">{escape(metric.title)}</p>')
        body.append(_render_summary_table(metric))
        body.append('<div style="height:10px"></div>')
        body.append(_render_detail_table(metric))
    return _card(section.title, "".join(body), collapsed=False)


def _render_html(sections: list[AggregatedSection], file_count: int) -> str:
    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    cards = [_render_section(section) for section in sections]

    return f"""<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>EOL Statistics</title>
  <style>
{CSS}
  </style>
</head>
<body>
<div class=\"page\">
  <div class=\"report-header\">
    <div>
      <h1>&#128202; EOL Statistics Report</h1>
      <div>Station name: EOL</div>
      <div>Scope: Multi-report selection</div>
    </div>
    <div class=\"report-meta\">
      <div>Date time: {escape(generated_at)}</div>
      <div>File report name: {escape(str(file_count))} reports selected</div>
    </div>
  </div>
  <div class=\"result-bar unknown\">Selection: {file_count} report(s)</div>
  {''.join(cards)}
  <div class=\"footer\">Generated by eol_stat.py ({FORMATTER_VERSION})</div>
</div>
<script>
{JS_TOGGLE}
</script>
</body>
</html>"""


def convert_files(csv_paths, output_path=None):
    paths = [Path(csv_path) for csv_path in csv_paths]
    if not paths:
        raise ValueError("No CSV files provided for EOL statistics")

    reports = [_parse_report_statistics(path) for path in paths]
    aggregated_sections = _aggregate_sections(reports)

    first_path = paths[0]
    output = first_path.with_name(f"{first_path.stem}_EolStats.html") if output_path is None else Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_html(aggregated_sections, len(paths)), encoding="utf-8")
    return output