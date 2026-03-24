# KISTLER maXYmos NC Report Viewer

A PyQt6-based desktop application for viewing, filtering, and analyzing KISTLER maXYmos NC machine reports in CSV format.

## Features

### Viewer Tab
- **File Browser**: Recursively scan and display CSV report files from the KISTLER station directory
- **Smart Filtering**: Real-time search and filter reports by filename, station, program, serial number, or result status
- **Metadata Display**: Automatically extract and display key information from CSV filenames:
  - **Date/Time**: Measurement timestamp
  - **Station**: Machine station identifier (e.g., MP-001, MP-003)
  - **Program**: NC program name
  - **SN**: Serial number
  - **Result**: Test result (OK/NOK status)
  - **File name**: Original CSV filename
- **Column Visibility**: Right-click column headers to show/hide columns with persistent state
- **Row Coloring**: Visual indicators for test results (green for OK, light red for NOK)
- **HTML Preview**: Real-time HTML report generation and preview of selected CSV files
- **Measuring Curve Chart**: Inline SVG charts displaying measurement curves without external dependencies
- **Refresh**: One-click refresh to reload the file list and capture newly generated reports

### Settings Tab
- **KISTLER Configuration Section**:
  - **Folder**: Set the default KISTLER CSV root directory
  - **CSV to HTML**: Configure the path to the CSV-to-HTML converter script (kisler.py)
  - **Save as Default**: Persist folder and script paths for the next session

### Persistent Settings
- Window size and position
- Splitter layout proportions
- Column widths
- Column visibility state (per-column hide/show)
- Default KISTLER folder path
- Converter script path

All settings are automatically saved to `ReportViewer.Settings.json` on exit and restored on startup.

## Installation

### Requirements
- Python 3.10+
- PyQt6 6.4+ (or PySide6 6.0+)
- PyQt6-WebEngine (or PySide6 equivalent)

### Setup
```bash
# Install dependencies
pip install PyQt6 PyQt6-WebEngine

# Or use PySide6 instead
pip install PySide6
```

## Usage

### Running the Application
```bash
python ReportViewer/report_viewer.py
```

### Workflow
1. **Select KISTLER Folder** (Viewer Tab):
   - Click "Browse..." to choose the root KISTLER CSV directory
   - The folder tree will populate with all CSV files from subdirectories

2. **Filter Reports**:
   - Type in the filter box to search by filename, station, program, or serial number
   - Matches are displayed in real-time

3. **Manage Columns**:
   - Right-click any column header to view/hide columns
   - Drag column borders to resize
   - Column state is automatically saved

4. **Preview Report**:
   - Click any CSV file in the tree view
   - The HTML preview panel displays the generated report
   - Measuring curves are rendered as interactive SVG charts

5. **Configure Defaults** (Settings Tab):
   - Under KISTLER section, set default folder and converter script paths
   - Click "Save As Default" to persist settings

## Directory Structure

```
HoerbigerDataCollection/
├── README.md                          # This file
├── ReportViewer/
│   ├── report_viewer.py               # Main Qt application
│   ├── ReportViewer.Settings.json     # Persistent UI state & settings
│   ├── README_kistler_qt_viewer.md    # Technical documentation
│   └── csv_to_html/
│       ├── kisler.py                  # CSV-to-HTML converter script
│       └── __pycache__/
└── Stations/
    ├── KISLER/
    │   ├── 2026-02-18/                # Date-based subdirectories
    │   ├── 2026-02-19/
    │   ├── 2026-03-19/
    │   └── ...
    ├── HMI-HELIUM/
    ├── HMI-PRESS/
    │   ├── Logs/
    │   ├── Reports/
    │   └── ...
```

## Settings File Format

The `ReportViewer.Settings.json` file stores:

```json
{
  "kistler_folder": "path/to/KISLER",
  "converter_script": "path/to/kisler.py",
  "ui_state": {
    "window": {
      "width": 1920,
      "height": 1001
    },
    "splitter_sizes": [491, 1382],
    "column_widths": {
      "0": 133,
      "1": 54,
      "2": 62,
      "3": 85,
      "4": 135,
      "5": 0
    },
    "column_visibility": {
      "0": true,
      "1": true,
      "2": true,
      "3": true,
      "4": true,
      "5": false
    }
  }
}
```

## CSV Filename Convention

Report filenames must follow this pattern:
```
Part_<STATION>_<PROGRAM>_<DATE>_<TIME>_<SERIAL>_<RESULT>.csv
```

Example:
```
Part_Press_station_MP-001_2026-03-19_11-05-56__OK.csv
```

Parsed fields:
- **STATION**: `Press_station`
- **PROGRAM**: `MP-001`
- **DATE**: `2026-03-19`
- **TIME**: `11-05-56`
- **SERIAL**: Extracted from filename structure
- **RESULT**: `OK` or `NOK`

## CSV to HTML Conversion

The application uses the `kisler.py` converter script to generate HTML reports from CSV files. The converter:
- Parses semicolon-delimited CSV format
- Extracts measurement data and metadata
- Generates inline SVG measuring curve charts
- Produces self-contained HTML (no external dependencies)

## Keyboard & Mouse Shortcuts

- **right-click on column header**: Show/hide column visibility menu
- **double-click column border**: Auto-fit column width
- **Ctrl+F** (or type in filter box): Filter reports in real-time
- **Refresh button**: Reload file tree

## Troubleshooting

**CSV file not appearing in tree?**
- Ensure the file follows the naming convention: `Part_*_*_*_*_*_*.csv`
- Check that the file is in a date-based subdirectory (e.g., `2026-03-19/`)
- Click the Refresh button to reload the directory

**HTML preview not displaying?**
- Verify the converter script path in Settings
- Check that `kisler.py` is accessible at the configured path
- Ensure the CSV file is in the correct format

**Settings not saved?**
- Confirm write permissions on the ReportViewer directory
- Check that `ReportViewer.Settings.json` is not read-only

## Technical Details

- **Framework**: PyQt6 (or PySide6)
- **Chart Rendering**: Inline SVG (no external Chart.js required)
- **Settings Persistence**: JSON format
- **Multi-threading**: File scanning in background (non-blocking UI)
- **Cross-platform**: Runs on Windows, macOS, Linux

## Author

Hörbiger Data Collection System

## Version

1.0.0 - March 2026
