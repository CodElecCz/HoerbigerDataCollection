"""CSS styles for EOL CSV to HTML report."""

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

td.check-ok {
    background: #dff3e5 !important;
}

td.check-nok {
    background: #f7d9dd !important;
}

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
@media (max-width: 980px) {
    .header-split {
        grid-template-columns: 1fr;
    }
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

.aeff-checks {
    margin-top: 10px;
    display: flex;
    flex-direction: row;
    gap: 16px;
    flex-wrap: wrap;
}
.aeff-checks-col {
    flex: 1 1 220px;
    min-width: 200px;
    max-width: 480px;
}
table.aeff-summary {
    table-layout: fixed;
    width: 100%;
    font-size: 12px;
    margin-top: 6px;
}
table.aeff-summary th,
table.aeff-summary td {
    padding: 3px 6px;
    width: 25%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.step-summary {
    margin-bottom: 10px;
}
.step-legend {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 8px;
    font-size: 12px;
}
.step-legend-item {
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
.step-legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 2px solid transparent;
}
.step-legend-swatch.aeff {
    background: #0f6cc2;
    border-color: #0f6cc2;
}
.step-legend-swatch.p3 {
    background: #b04f00;
    border-color: #b04f00;
}
.step-legend-swatch.leak-flow {
    background: #0a9367;
    border-color: #0a9367;
}
.subsection-label {
    font-size: 11px;
    font-weight: 700;
    color: #1f6f96;
    margin-top: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.step-chart {
    border: 1px solid #d5dde6;
    border-radius: 4px;
    padding: 8px;
    background: #fbfcfe;
}
.step-chart svg {
    width: 100%;
    height: 280px;
    display: block;
}
.axis-text {
    fill: #51606f;
    font-size: 10px;
    font-family: Segoe UI, Arial, sans-serif;
}
.axis-title {
    fill: #22313f;
    font-size: 12px;
    font-weight: 600;
    font-family: Segoe UI, Arial, sans-serif;
}
.step-color {
    color: #0f6cc2;
    font-weight: 600;
}
"""
