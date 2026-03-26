"""CSS styles for ADJ CSV to HTML report."""

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 13px;
    background: #eef1f6;
    color: #1d2833;
}
.page {
    max-width: 1220px;
    margin: 24px auto;
    padding: 0 14px 34px;
}
.report-header {
    background: linear-gradient(135deg, #0f3d59 0%, #2a7d8f 100%);
    color: #ffffff;
    padding: 18px 24px;
    border-radius: 8px 8px 0 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}
.report-header h1 {
    font-size: 1.35em;
    letter-spacing: 0.4px;
}
.report-meta {
    font-size: 12px;
    opacity: 0.9;
    text-align: right;
}
.result-bar {
    padding: 9px 24px;
    font-size: 1.05em;
    font-weight: 700;
    letter-spacing: 0.4px;
}
.result-bar.ok {
    background: #d4edda;
    color: #155724;
    border-left: 6px solid #28a745;
}
.result-bar.nok {
    background: #f8d7da;
    color: #721c24;
    border-left: 6px solid #dc3545;
}
.result-bar.error {
    background: #fde8d9;
    color: #8a3b00;
    border-left: 6px solid #ff8c00;
}
.result-bar.unknown {
    background: #e2e3e5;
    color: #383d41;
    border-left: 6px solid #6c757d;
}
.card {
    background: #ffffff;
    border-radius: 6px;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.11);
    margin-top: 14px;
    overflow: hidden;
}
.card-header {
    background: #1f6f96;
    color: #ffffff;
    padding: 8px 14px;
    font-size: 1em;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.card-header:hover { background: #185a7b; }
.card-header .toggle-icon { font-size: 15px; transition: transform 0.2s; }
.card-header.collapsed .toggle-icon { transform: rotate(-90deg); }
.card-body { padding: 12px 14px; }
.card-body.hidden { display: none; }

table {
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
    margin-top: 8px;
}
th, td {
    border: 1px solid #d5dde6;
    padding: 5px 8px;
    text-align: left;
    vertical-align: top;
    word-break: break-word;
}
th {
    background: #e7f1f9;
    font-weight: 600;
    white-space: nowrap;
}
tr:nth-child(even) td { background: #f8fbfe; }

table.kv th {
    width: 340px;
    background: #f0f6fb;
}

table.kv-sub {
    margin-top: 0;
    width: auto;
    min-width: 360px;
}
table.kv-sub th,
table.kv-sub td {
    padding: 4px 6px;
    font-size: 11px;
}
table.kv-sub th {
    background: #edf3fa;
    text-align: center;
}
table.kv-sub td {
    text-align: center;
}

.header-split {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
}
.header-split-col table.kv {
    margin-top: 0;
}
@media (max-width: 980px) {
    .header-split {
        grid-template-columns: 1fr;
    }
}

.measurement-overview {
    display: grid;
    gap: 10px;
}
.measurement-samples {
    font-size: 13px;
    color: #1f2f3f;
}
table.measurement-header-only {
    margin-top: 0;
}
.measurement-actions {
    display: flex;
    justify-content: flex-start;
    align-items: center;
    gap: 10px;
}
.btn-copy {
    display: inline-block;
    border: 1px solid #1f6f96;
    background: #1f6f96;
    color: #ffffff;
    border-radius: 4px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
}
.btn-copy:hover {
    background: #185a7b;
    border-color: #185a7b;
}
.copy-status {
    font-size: 12px;
    color: #677789;
    min-height: 16px;
}
.copy-status.ok {
    color: #1d7f47;
}
.copy-status.fail {
    color: #b13a3a;
}
.measurement-csv-source {
    display: none;
}

.badge {
    display: inline-block;
    min-width: 34px;
    padding: 2px 8px;
    border-radius: 10px;
    text-align: center;
    font-size: 11px;
    font-weight: 700;
}
.badge.ok { background: #28a745; color: #ffffff; }
.badge.nok { background: #dc3545; color: #ffffff; }
.badge.error { background: #ff8c00; color: #ffffff; }
.badge.none { background: #6c757d; color: #ffffff; }

.chart-container {
    position: relative;
    height: 440px;
    margin-top: 6px;
}
.chart-svg {
    width: 100%;
    height: 100%;
    display: block;
}
.chart-axis-text {
    fill: #51606f;
    font-size: 10px;
    font-family: Segoe UI, Arial, sans-serif;
}
.chart-axis-title {
    fill: #22313f;
    font-size: 12px;
    font-weight: 600;
    font-family: Segoe UI, Arial, sans-serif;
}
.chart-legend {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 8px;
    font-size: 12px;
}
.chart-legend-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.chart-legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 2px solid transparent;
}
.chart-legend-swatch.calc {
    background: #0f6cc2;
    border-color: #0f6cc2;
}
.chart-legend-swatch.meas {
    background: #18a06c;
    border-color: #18a06c;
}
.chart-legend-swatch.target-final {
    background: #f2a900;
    border-color: #c68500;
}
.chart-legend-swatch.target-step {
    background: #cc9158;
    border-color: #8c4d15;
}
.chart-legend-swatch.position {
    background: #b38867;
    border-color: #7a4b2a;
}

.footer {
    text-align: center;
    color: #8d98a5;
    margin-top: 20px;
    font-size: 11px;
}
"""
