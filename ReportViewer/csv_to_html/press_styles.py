"""CSS styles for HMI-PRESS CSV to HTML report."""

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 13px;
    background: #edf1f5;
    color: #1d2a35;
}
.page {
    max-width: 1200px;
    margin: 22px auto;
    padding: 0 14px 34px;
}
.report-header {
    background: linear-gradient(135deg, #0f4c6f 0%, #1f7a66 100%);
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
    width: 280px;
    background: #f0f6fb;
}
.table-title {
    margin-top: 10px;
    margin-bottom: 4px;
    color: #2f495c;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
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

.footer {
    text-align: center;
    color: #8d98a5;
    margin-top: 20px;
    font-size: 11px;
}
"""
