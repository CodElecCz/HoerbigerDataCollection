"""CSS styles for the Kistler CSV → HTML report."""

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    background: #f0f2f5;
    color: #222;
}
.page-wrapper {
    max-width: 1200px;
    margin: 24px auto;
    padding: 0 16px 40px;
}
header {
    background: linear-gradient(135deg, #1a3a5c 0%, #2d6a9f 100%);
    color: #fff;
    padding: 20px 28px;
    border-radius: 8px 8px 0 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
}
header h1 { font-size: 1.4em; letter-spacing: 0.5px; }
header .meta { font-size: 12px; opacity: 0.85; text-align: right; }
.result-banner {
    padding: 10px 28px;
    font-size: 1.1em;
    font-weight: bold;
    letter-spacing: 0.5px;
}
.result-banner.ok  { background: #d4edda; color: #155724; border-left: 6px solid #28a745; }
.result-banner.nok { background: #f8d7da; color: #721c24; border-left: 6px solid #dc3545; }
.card {
    background: #fff;
    border-radius: 6px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    margin-top: 16px;
    overflow: hidden;
}
.card-header {
    background: #2d6a9f;
    color: #fff;
    padding: 8px 16px;
    font-size: 1em;
    font-weight: 600;
    cursor: pointer;
    user-select: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.card-header:hover { background: #245a8a; }
.card-header .toggle-icon { font-size: 16px; transition: transform 0.2s; }
.card-header.collapsed .toggle-icon { transform: rotate(-90deg); }
.card-body { padding: 12px 16px; }
.card-body.hidden { display: none; }

table {
    border-collapse: collapse;
    width: 100%;
    font-size: 12px;
}
th, td {
    border: 1px solid #dee2e6;
    padding: 5px 9px;
    text-align: left;
    vertical-align: top;
    word-break: break-word;
}
th { background: #e8f0fb; font-weight: 600; white-space: nowrap; }
tr:nth-child(even) td { background: #f8f9fa; }
table.kv th { width: 260px; background: #f0f4fa; }
table.kv td { color: #0056b3; }

.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
}
.badge.ok   { background: #28a745; color: #fff; }
.badge.nok  { background: #dc3545; color: #fff; }
.badge.none { background: #adb5bd; color: #fff; }

td.ok  { color: #155724; font-weight: bold; }
td.nok { color: #721c24; font-weight: bold; }

.chart-container {
    position: relative;
    height: 460px;
    padding: 8px 0;
}
.chart-svg {
    display: block;
    width: 100%;
    height: 100%;
}
.chart-axis-text {
    fill: #51606f;
    font-size: 10px;
    font-family: 'Segoe UI', Arial, sans-serif;
}
.chart-axis-title {
    fill: #22313f;
    font-size: 12px;
    font-weight: 600;
    font-family: 'Segoe UI', Arial, sans-serif;
}
.chart-box-label {
    font-size: 11px;
    font-weight: 700;
    font-family: 'Segoe UI', Arial, sans-serif;
}
.chart-legend {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
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
    border: 2px solid transparent;
    border-radius: 3px;
    background: #dbeafe;
}
.chart-legend-swatch.curve {
    background: #007acc;
    border-color: #007acc;
}

.two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}
@media (max-width: 700px) { .two-col { grid-template-columns: 1fr; } }

.eo-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    padding: 4px 0;
}
.eo-card {
    border: 1px solid #dee2e6;
    border-radius: 6px;
    padding: 8px 14px;
    min-width: 200px;
    flex: 1 1 200px;
    background: #fafbfc;
}
.eo-card.ok  { border-left: 4px solid #28a745; }
.eo-card.nok { border-left: 4px solid #dc3545; }
.eo-card.none { border-left: 4px solid #adb5bd; }
.eo-card h3 { font-size: 12px; margin-bottom: 6px; }
.eo-card .kv-item { display: flex; justify-content: space-between; font-size: 11px; padding: 1px 0; }
.eo-card .kv-item span:last-child { font-weight: bold; color: #333; }

.seq-editor { display: flex; flex-direction: column; gap: 3px; padding: 4px 0; }
.seq-group {
    margin-top: 10px;
    margin-bottom: 2px;
}
.seq-group-name {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #2d6a9f;
    border-bottom: 2px solid #2d6a9f;
    padding-bottom: 2px;
    display: inline-block;
}
.seq-step {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    border-radius: 4px;
    background: #f8f9fa;
    border-left: 3px solid #dee2e6;
    font-size: 12px;
    flex-wrap: wrap;
}
.seq-step:hover { background: #eef4fb; }
.seq-num {
    font-size: 10px;
    color: #aaa;
    min-width: 18px;
    text-align: right;
    flex-shrink: 0;
}
.seq-icon { font-size: 14px; flex-shrink: 0; }
.seq-type { font-weight: 600; min-width: 110px; color: #1a3a5c; flex-shrink: 0; }
.seq-pills { display: flex; flex-wrap: wrap; gap: 4px; }
.seq-pill {
    background: #e8f0fb;
    border: 1px solid #c8d8f0;
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 11px;
    white-space: nowrap;
}
.seq-key { color: #555; margin-right: 3px; }
.seq-key::after { content: ':'; }
.seq-unit { color: #888; font-size: 10px; margin-left: 1px; }
/* Per-type left-border colors */
.seq-motion        { border-left-color: #0078d4; }
.seq-home_position { border-left-color: #6f42c1; }
.seq-measure       { border-left-color: #28a745; background: #f0faf3; }
.seq-output        { border-left-color: #fd7e14; }
.seq-input         { border-left-color: #20c997; }
.seq-timer         { border-left-color: #ffc107; }
.seq-end           { border-left-color: #dc3545; background: #fff5f5; }
.seq-label         { border-left-color: #adb5bd; background: #f8f9fa; font-style: italic; }
"""
