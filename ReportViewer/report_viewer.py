#!/usr/bin/env python3
"""
Qt viewer for station CSV reports.

Features:
- Recursively scans a selected station directory for CSV files
- Lists discovered CSV files with filtering
- Converts selected CSV to HTML using built-in station converters
- Displays generated HTML in an embedded browser
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from converters import AVAILABLE_CONVERTERS, DEFAULT_CONVERTER_NAME

BUILT_IN_CONVERTER_SETTING = "built-in:converters.AVAILABLE_CONVERTERS"
PROFILE_COUNT = 5
DEFAULT_STATION_FOLDERS = {
    "KISTLER": "KISLER",
    "HMI-HELIUM": "HMI-HELIUM/Reports",
    "HMI-PRESS": "HMI-PRESS/Reports",
    "ADJ": "ADJ",
}


def get_app_base_dir() -> Path:
    """Return writable app directory (source folder or EXE folder)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_qt_bindings():
    """Load Qt classes from PyQt6 first, then PySide6 as fallback."""
    last_error = None
    try:
        from PyQt6 import QtCore as qt_core
        from PyQt6 import QtGui as qt_gui
        from PyQt6 import QtWidgets as qt_widgets
        try:
            from PyQt6 import QtWebEngineWidgets as qt_web
            from PyQt6 import QtWebEngineCore as qt_web_core
        except Exception:
            qt_web = None
            qt_web_core = None
    except Exception as pyqt_exc:
        last_error = pyqt_exc
        try:
            from PySide6 import QtCore as qt_core
            from PySide6 import QtGui as qt_gui
            from PySide6 import QtWidgets as qt_widgets
            try:
                from PySide6 import QtWebEngineWidgets as qt_web
                from PySide6 import QtWebEngineCore as qt_web_core
            except Exception:
                qt_web = None
                qt_web_core = None
        except Exception as pyside_exc:
            last_error = pyside_exc
            raise ImportError(
                "Neither PySide6 nor PyQt6 is available. "
                "Install one of: 'pip install PySide6' or 'pip install PyQt6'."
            ) from last_error

    return {
        "QBrush": qt_gui.QBrush,
        "QColor": qt_gui.QColor,
        "QDesktopServices": qt_gui.QDesktopServices,
        "Qt": qt_core.Qt,
        "QUrl": qt_core.QUrl,
        "QApplication": qt_widgets.QApplication,
        "QAbstractItemView": qt_widgets.QAbstractItemView,
        "QComboBox": qt_widgets.QComboBox,
        "QFileDialog": qt_widgets.QFileDialog,
        "QGroupBox": qt_widgets.QGroupBox,
        "QHeaderView": qt_widgets.QHeaderView,
        "QHBoxLayout": qt_widgets.QHBoxLayout,
        "QLabel": qt_widgets.QLabel,
        "QLineEdit": qt_widgets.QLineEdit,
        "QMainWindow": qt_widgets.QMainWindow,
        "QMenu": qt_widgets.QMenu,
        "QMessageBox": qt_widgets.QMessageBox,
        "QPushButton": qt_widgets.QPushButton,
        "QSplitter": qt_widgets.QSplitter,
        "QStatusBar": qt_widgets.QStatusBar,
        "QTabWidget": qt_widgets.QTabWidget,
        "QTextBrowser": qt_widgets.QTextBrowser,
        "QTreeWidget": qt_widgets.QTreeWidget,
        "QTreeWidgetItem": qt_widgets.QTreeWidgetItem,
        "QVBoxLayout": qt_widgets.QVBoxLayout,
        "QWidget": qt_widgets.QWidget,
        "QWebEngineView": qt_web.QWebEngineView if qt_web is not None else None,
        "QWebEnginePage": qt_web_core.QWebEnginePage if qt_web_core is not None else None,
    }


QT = load_qt_bindings()
QBrush = QT["QBrush"]
QColor = QT["QColor"]
QDesktopServices = QT["QDesktopServices"]
Qt = QT["Qt"]
QUrl = QT["QUrl"]
QApplication = QT["QApplication"]
QAbstractItemView = QT["QAbstractItemView"]
QComboBox = QT["QComboBox"]
QFileDialog = QT["QFileDialog"]
QGroupBox = QT["QGroupBox"]
QHeaderView = QT["QHeaderView"]
QHBoxLayout = QT["QHBoxLayout"]
QLabel = QT["QLabel"]
QLineEdit = QT["QLineEdit"]
QMainWindow = QT["QMainWindow"]
QMenu = QT["QMenu"]
QMessageBox = QT["QMessageBox"]
QPushButton = QT["QPushButton"]
QSplitter = QT["QSplitter"]
QStatusBar = QT["QStatusBar"]
QTabWidget = QT["QTabWidget"]
QTextBrowser = QT["QTextBrowser"]
QTreeWidget = QT["QTreeWidget"]
QTreeWidgetItem = QT["QTreeWidgetItem"]
QVBoxLayout = QT["QVBoxLayout"]
QWidget = QT["QWidget"]
QWebEngineView = QT["QWebEngineView"]
QWebEnginePage = QT["QWebEnginePage"]


def extract_measurement_section_csv(csv_path: Path) -> str | None:
    lines = csv_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    collected: list[str] = []
    in_measurement = False

    for raw in lines:
        stripped = raw.strip()
        if not in_measurement:
            if stripped.lower() == "[measurement]":
                in_measurement = True
                collected.append("[Measurement]")
            continue

        # A new section marker is a single token like [Results], not a row like [s];[mm2];...
        if ";" not in stripped and stripped.startswith("[") and stripped.endswith("]") and stripped.lower() != "[measurement]":
            break

        if stripped:
            collected.append(raw.strip())

    if not collected:
        return None
    return "\n".join(collected) + "\n"


def is_export_measurement_url(url_text: str) -> bool:
    parsed = urlparse(url_text)
    if parsed.scheme == "reportviewer" and parsed.netloc == "export-measurement":
        return True
    if parsed.scheme in {"http", "https"} and parsed.netloc == "reportviewer.local" and parsed.path == "/export-measurement":
        return True
    return False


def is_copy_measurement_url(url_text: str) -> bool:
    parsed = urlparse(url_text)
    if parsed.scheme in {"http", "https"} and parsed.netloc == "reportviewer.local" and parsed.path == "/copy-measurement":
        return True
    return False


if QWebEnginePage is not None:
    class ReportWebPage(QWebEnginePage):
        def __init__(self, export_callback, parent=None) -> None:
            super().__init__(parent)
            self._export_callback = export_callback

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
            if is_export_measurement_url(url.toString()):
                self._export_callback()
                return False
            if is_copy_measurement_url(url.toString()):
                self._export_callback(copy_only=True)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        def javaScriptConsoleMessage(self, level, message, line_number, source_id):  # noqa: N802
            print(f"[WebConsole] {message} ({source_id}:{line_number})")
            super().javaScriptConsoleMessage(level, message, line_number, source_id)


class KistlerReportViewer(QMainWindow):
    ROLE_PATH = Qt.ItemDataRole.UserRole
    ROLE_MTIME = Qt.ItemDataRole.UserRole + 1
    COL_TIME = 0
    COL_STATION = 1
    COL_PROGRAM = 2
    COL_SERIAL = 3
    COL_RESULT = 4
    COL_FILENAME = 5

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Report Viewer")
        self.resize(1400, 850)
        self.uses_webengine = QWebEngineView is not None

        self.base_dir = get_app_base_dir()
        self.default_csv_root = (self.base_dir.parent / "Stations" / "KISLER").resolve()
        self.settings_path = self.base_dir / "ReportViewer.Settings.json"
        self.saved_ui_state = self._load_saved_ui_state()
        self.ui_state_applied = False
        self._capture_layout_on_refresh = True
        self._profile_column_widths: dict = {
            int(k): v
            for k, v in self.saved_ui_state.get("column_widths_by_profile", {}).items()
            if isinstance(v, dict)
        }
        self._profile_column_visibility: dict = {
            int(k): v
            for k, v in self.saved_ui_state.get("column_visibility_by_profile", {}).items()
            if isinstance(v, dict)
        }
        self._profile_column_order: dict = {
            int(k): v
            for k, v in self.saved_ui_state.get("column_order_by_profile", {}).items()
            if isinstance(v, list)
        }
        self.profiles = self._load_saved_profiles()
        self.active_profile_index = self._load_saved_active_profile_index()
        active_profile = self.profiles[self.active_profile_index]
        self.converter_name = active_profile["converter_name"]
        self.generated_dir = Path(tempfile.gettempdir()) / "report_viewer_html"
        self.generated_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.convert_file = self._get_converter_callable(self.converter_name)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to load internal converter:\n{exc}",
            )
            raise

        self.current_csv_path: Path | None = None
        self._build_ui()
        self._restore_window_state()
        self._set_initial_directory()

    def _build_ui(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        tabs = QTabWidget()
        tabs.addTab(self._create_viewer_tab(), "Viewer")
        tabs.addTab(self._create_settings_tab(), "Settings")
        root_layout.addWidget(tabs)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar(self))
        if not self.uses_webengine:
            self.statusBar().showMessage(
                "QtWebEngine is unavailable; using basic HTML preview mode.",
                8000,
            )

    def _create_viewer_tab(self) -> QWidget:
        viewer = QWidget(self)
        layout = QVBoxLayout(viewer)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Section:"))
        self.viewer_profile_combo = QComboBox()
        self.viewer_profile_combo.currentIndexChanged.connect(self.on_viewer_profile_changed)
        top_row.addWidget(self.viewer_profile_combo, 0)
        top_row.addWidget(QLabel("Folder:"))
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        top_row.addWidget(self.dir_edit, 1)
        layout.addLayout(top_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Type to filter by file name or folder")
        self.filter_edit.textChanged.connect(self.apply_filter)
        filter_row.addWidget(self.filter_edit, 1)
        left_layout.addLayout(filter_row)

        self.csv_tree = QTreeWidget()
        self.csv_tree.setColumnCount(6)
        self.csv_tree.setHeaderLabels(
            [
                "Time",
                "Station",
                "Program",
                "SN",
                "Result",
                "File name",
            ]
        )
        self.csv_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.csv_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.csv_tree.setAllColumnsShowFocus(True)
        self.csv_tree.setAlternatingRowColors(True)
        self.csv_tree.setStyleSheet(
            """
            QTreeWidget {
                alternate-background-color: #f7f9fc;
            }
            QTreeWidget::item {
                padding: 3px 2px;
            }
            QTreeWidget::item:selected,
            QTreeWidget::item:selected:active,
            QTreeWidget::item:selected:!active {
                background-color: #1f6feb;
                color: #ffffff;
                border: 1px solid #0f4fb8;
            }
            """
        )
        header = self.csv_tree.header()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setResizeContentsPrecision(-1)
        header.setStretchLastSection(False)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self.on_header_context_menu)
        self.csv_tree.itemSelectionChanged.connect(self.preview_selected)
        left_layout.addWidget(self.csv_tree, 1)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_csv_list)
        refresh_row.addWidget(refresh_btn)
        left_layout.addLayout(refresh_row)

        splitter.addWidget(left_panel)

        if self.uses_webengine:
            self.web_view = QWebEngineView()
            if QWebEnginePage is not None:
                self.web_page = ReportWebPage(self.export_current_measurement_csv, self.web_view)
                self.web_view.setPage(self.web_page)
        else:
            self.web_view = QTextBrowser()
            self.web_view.setOpenExternalLinks(False)
            self.web_view.anchorClicked.connect(self.on_textbrowser_link_clicked)
        splitter.addWidget(self.web_view)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([760, 640])
        self.main_splitter = splitter

        layout.addWidget(splitter, 1)
        return viewer

    def _create_settings_tab(self) -> QWidget:
        settings = QWidget(self)
        layout = QVBoxLayout(settings)

        self.settings_name_edits = []
        self.settings_dir_edits = []
        self.settings_converter_combos = []

        for idx in range(PROFILE_COUNT):
            group = QGroupBox(f"Section {idx + 1}")
            group_layout = QVBoxLayout()

            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("Name:"))
            name_edit = QLineEdit()
            name_edit.setPlaceholderText(f"Section {idx + 1}")
            name_row.addWidget(name_edit, 1)
            group_layout.addLayout(name_row)

            folder_row = QHBoxLayout()
            folder_row.addWidget(QLabel("Folder:"))
            dir_edit = QLineEdit()
            dir_edit.setPlaceholderText("Choose folder path")
            folder_row.addWidget(dir_edit, 1)

            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda checked=False, i=idx: self.on_settings_browse(i))
            folder_row.addWidget(browse_btn)
            group_layout.addLayout(folder_row)

            converter_row = QHBoxLayout()
            converter_row.addWidget(QLabel("CSV to HTML:"))
            converter_combo = QComboBox()
            converter_combo.addItems(list(AVAILABLE_CONVERTERS.keys()))
            converter_row.addWidget(converter_combo, 1)
            group_layout.addLayout(converter_row)

            group.setLayout(group_layout)
            layout.addWidget(group)

            self.settings_name_edits.append(name_edit)
            self.settings_dir_edits.append(dir_edit)
            self.settings_converter_combos.append(converter_combo)

        save_btn = QPushButton("Save Sections")
        save_btn.clicked.connect(self.on_save_settings)
        layout.addWidget(save_btn)

        hint = QLabel(f"Settings file: {self.settings_path.name}")
        layout.addWidget(hint)
        layout.addStretch(1)

        return settings

    def _set_initial_directory(self) -> None:
        if not self.profiles:
            self.profiles = self._default_profiles()

        self._sync_settings_form_with_profiles()
        self._refresh_viewer_profile_combo()
        self._apply_active_profile(refresh=True)
        self._save_settings()

    def _default_profiles(self) -> list[dict[str, str]]:
        default_folder = self._default_root_for_converter(DEFAULT_CONVERTER_NAME)
        profiles: list[dict[str, str]] = []
        for idx in range(PROFILE_COUNT):
            profiles.append(
                {
                    "name": f"Section {idx + 1}",
                    "folder": str(default_folder) if idx == 0 else "",
                    "converter_name": DEFAULT_CONVERTER_NAME,
                }
            )
        return profiles

    def _default_root_for_converter(self, converter_name: str) -> Path:
        station_relative = DEFAULT_STATION_FOLDERS.get(converter_name, "")
        if station_relative:
            candidate = (self.base_dir.parent / "Stations" / Path(station_relative)).resolve()
            if candidate.exists():
                return candidate
        if self.default_csv_root.exists():
            return self.default_csv_root
        return self.base_dir

    def _sanitize_profile(self, profile: dict, idx: int) -> dict[str, str]:
        name = str(profile.get("name", "")).strip() or f"Section {idx + 1}"
        folder = str(profile.get("folder", "")).strip()
        converter_name = str(profile.get("converter_name", "")).strip()
        if converter_name not in AVAILABLE_CONVERTERS:
            converter_name = DEFAULT_CONVERTER_NAME
        return {
            "name": name,
            "folder": folder,
            "converter_name": converter_name,
        }

    def _load_saved_profiles(self) -> list[dict[str, str]]:
        payload = self._load_settings_payload()
        defaults = self._default_profiles()
        if not payload:
            return defaults

        raw_profiles = payload.get("profiles")
        profiles: list[dict[str, str]] = []
        if isinstance(raw_profiles, list):
            for idx, raw_profile in enumerate(raw_profiles[:PROFILE_COUNT]):
                if isinstance(raw_profile, dict):
                    profiles.append(self._sanitize_profile(raw_profile, idx))

        if not profiles:
            # Backward compatibility migration from single-folder settings
            legacy_folder = str(payload.get("kistler_folder", "")).strip()
            legacy_converter = str(payload.get("converter_name", "")).strip()
            if legacy_converter not in AVAILABLE_CONVERTERS:
                legacy_converter = DEFAULT_CONVERTER_NAME
            defaults[0] = {
                "name": "Section 1",
                "folder": legacy_folder,
                "converter_name": legacy_converter,
            }
            profiles = defaults

        while len(profiles) < PROFILE_COUNT:
            profiles.append(self._sanitize_profile(defaults[len(profiles)], len(profiles)))

        return profiles

    def _load_saved_active_profile_index(self) -> int:
        payload = self._load_settings_payload()
        raw_idx = payload.get("active_profile_index", 0) if payload else 0
        if isinstance(raw_idx, int) and 0 <= raw_idx < PROFILE_COUNT:
            return raw_idx
        return 0

    def _sync_settings_form_with_profiles(self) -> None:
        for idx in range(PROFILE_COUNT):
            profile = self.profiles[idx]
            self.settings_name_edits[idx].setText(profile["name"])
            self.settings_dir_edits[idx].setText(profile["folder"])
            self.settings_converter_combos[idx].setCurrentText(profile["converter_name"])

    def _refresh_viewer_profile_combo(self) -> None:
        self.viewer_profile_combo.blockSignals(True)
        self.viewer_profile_combo.clear()
        self._combo_to_profile: list = []
        for i, profile in enumerate(self.profiles):
            if profile["folder"].strip():
                self.viewer_profile_combo.addItem(profile["name"])
                self._combo_to_profile.append(i)
        try:
            combo_idx = self._combo_to_profile.index(self.active_profile_index)
        except ValueError:
            combo_idx = 0
        self.viewer_profile_combo.setCurrentIndex(combo_idx)
        self.viewer_profile_combo.blockSignals(False)

    def _apply_active_profile(self, refresh: bool) -> None:
        profile = self.profiles[self.active_profile_index]
        folder = profile["folder"].strip()
        converter_name = profile["converter_name"]

        self.converter_name = converter_name
        self.convert_file = self._get_converter_callable(converter_name)
        self.dir_edit.setText(folder)

        if refresh:
            self.refresh_csv_list()

    def _get_column_widths(self) -> dict:
        return {
            str(c): self.csv_tree.columnWidth(c)
            for c in range(self.csv_tree.columnCount())
        }

    def _apply_column_widths(self, widths: dict) -> None:
        for c in range(self.csv_tree.columnCount()):
            w = widths.get(str(c))
            if isinstance(w, int) and w > 0:
                self.csv_tree.setColumnWidth(c, w)

    def _get_column_visibility(self) -> dict:
        return {
            str(c): not self.csv_tree.isColumnHidden(c)
            for c in range(self.csv_tree.columnCount())
        }

    def _apply_column_visibility(self, visibility: dict) -> None:
        for c in range(self.csv_tree.columnCount()):
            is_visible = visibility.get(str(c), True)
            self.csv_tree.setColumnHidden(c, not is_visible)

    def _get_column_order(self) -> list:
        header = self.csv_tree.header()
        return [header.logicalIndex(v) for v in range(header.count())]

    def _apply_column_order(self, order: list) -> None:
        if not order:
            return
        header = self.csv_tree.header()
        count = header.count()
        for visual, logical in enumerate(order):
            if logical < count:
                current_visual = header.visualIndex(logical)
                if current_visual != visual:
                    header.moveSection(current_visual, visual)

    def on_viewer_profile_changed(self, index: int) -> None:
        if index < 0 or index >= len(getattr(self, "_combo_to_profile", [])):
            return
        self._profile_column_widths[self.active_profile_index] = self._get_column_widths()
        self._profile_column_visibility[self.active_profile_index] = self._get_column_visibility()
        self._profile_column_order[self.active_profile_index] = self._get_column_order()
        profile_index = self._combo_to_profile[index]
        self.active_profile_index = profile_index
        self._capture_layout_on_refresh = False
        try:
            self._apply_active_profile(refresh=True)
        finally:
            self._capture_layout_on_refresh = True
        self._apply_column_order(self._profile_column_order.get(profile_index, []))
        self._apply_column_widths(self._profile_column_widths.get(profile_index, {}))
        self._apply_column_visibility(self._profile_column_visibility.get(profile_index, {}))
        self._save_settings()
        self._save_ui_state()
        self.statusBar().showMessage(f"Switched to {self.profiles[profile_index]['name']}", 3000)

    def on_browse(self) -> None:
        start_dir = self.dir_edit.text().strip() or str(self.base_dir)
        selected = QFileDialog.getExistingDirectory(self, "Select CSV Root Folder", start_dir)
        if not selected:
            return
        self.profiles[self.active_profile_index]["folder"] = selected
        self._sync_settings_form_with_profiles()
        self._apply_active_profile(refresh=False)
        self._save_settings()
        self.refresh_csv_list()

    def on_settings_browse(self, index: int) -> None:
        converter_name = self.settings_converter_combos[index].currentText().strip()
        start_dir = self.settings_dir_edits[index].text().strip() or str(
            self._default_root_for_converter(converter_name)
        )
        selected = QFileDialog.getExistingDirectory(self, "Select default station folder", start_dir)
        if not selected:
            return
        self.settings_dir_edits[index].setText(selected)

    def on_save_settings(self) -> None:
        profiles: list[dict[str, str]] = []
        for idx in range(PROFILE_COUNT):
            name = self.settings_name_edits[idx].text().strip() or f"Section {idx + 1}"
            folder = self.settings_dir_edits[idx].text().strip()
            converter_name = self.settings_converter_combos[idx].currentText().strip()

            if converter_name not in AVAILABLE_CONVERTERS:
                self._show_warning(f"Unsupported CSV to HTML converter in {name}: {converter_name}")
                return

            if folder:
                selected_path = Path(folder)
                if not selected_path.exists() or not selected_path.is_dir():
                    self._show_warning(f"Folder does not exist for {name}: {selected_path}")
                    return

            profiles.append(
                {
                    "name": name,
                    "folder": folder,
                    "converter_name": converter_name,
                }
            )

        self.profiles = profiles
        if self.active_profile_index >= PROFILE_COUNT:
            self.active_profile_index = 0
        self._refresh_viewer_profile_combo()
        self._apply_active_profile(refresh=True)
        self._save_settings()
        self.statusBar().showMessage("Saved section settings.", 5000)

    def refresh_csv_list(self) -> None:
        # Preserve live column layout before clearing/rebuilding the tree.
        if self._capture_layout_on_refresh and self.csv_tree.columnCount() > 0:
            self._profile_column_widths[self.active_profile_index] = self._get_column_widths()
            self._profile_column_visibility[self.active_profile_index] = self._get_column_visibility()
            self._profile_column_order[self.active_profile_index] = self._get_column_order()

        root_text = self.dir_edit.text().strip()
        if not root_text:
            self.csv_tree.clear()
            self.web_view.setHtml("<h3>No folder configured for this section.</h3>")
            self.statusBar().showMessage("No folder configured for selected section.", 5000)
            return

        root = Path(root_text)
        if not root.exists() or not root.is_dir():
            self._show_warning(f"Folder does not exist: {root}")
            return

        files = list(root.rglob("*.csv"))

        self.csv_tree.clear()
        if not files:
            self.statusBar().showMessage(f"No CSV files found under {root}", 6000)
            self.web_view.setHtml("<h3>No CSV files found.</h3>")
            return

        self._populate_tree(root, files)
        self._resize_tree_columns()
        self._apply_saved_widget_sizes()
        self._apply_column_order(self._profile_column_order.get(self.active_profile_index, []))
        self._apply_column_widths(self._profile_column_widths.get(self.active_profile_index, {}))
        self._apply_column_visibility(self._profile_column_visibility.get(self.active_profile_index, {}))

        self.apply_filter(self.filter_edit.text())
        self.statusBar().showMessage(f"Found {len(files)} CSV files in {root}", 5000)

        self._select_first_visible_file()

    def _populate_tree(self, root: Path, files: list[Path]) -> None:
        folder_nodes: dict[tuple[str, ...], QTreeWidgetItem] = {}

        for csv_file in files:
            rel = csv_file.relative_to(root)
            mtime = csv_file.stat().st_mtime
            parent = self.csv_tree.invisibleRootItem()

            for depth in range(1, len(rel.parts)):
                key = tuple(rel.parts[:depth])
                node = folder_nodes.get(key)
                if node is None:
                    node = QTreeWidgetItem([rel.parts[depth - 1]])
                    node.setData(0, self.ROLE_MTIME, mtime)
                    parent.addChild(node)
                    folder_nodes[key] = node
                else:
                    cur = node.data(0, self.ROLE_MTIME) or 0
                    if mtime > cur:
                        node.setData(0, self.ROLE_MTIME, mtime)
                parent = node

            file_item = QTreeWidgetItem([""])
            fields = self._parse_csv_name_fields(csv_file)
            file_item.setText(self.COL_TIME, fields["time"])
            file_item.setText(self.COL_STATION, fields["station"])
            file_item.setText(self.COL_PROGRAM, fields["program"])
            file_item.setText(self.COL_SERIAL, fields["serial"])
            file_item.setText(self.COL_RESULT, fields["result"])
            file_item.setText(self.COL_FILENAME, rel.parts[-1])
            self._apply_result_styling(file_item, fields["result"])
            file_item.setData(0, self.ROLE_PATH, str(csv_file))
            file_item.setData(0, self.ROLE_MTIME, mtime)
            file_item.setToolTip(0, str(csv_file))
            parent.addChild(file_item)

        self._sort_tree_by_mtime(self.csv_tree.invisibleRootItem())

    def _parse_csv_name_fields(self, csv_path: Path) -> dict[str, str]:
        stem = csv_path.stem
        parts = stem.split("_")

        # HMI compact style used by HMI-PRESS and HMI-HELIUM:
        # <station>_YYYY-MM-DD_HH-MM-SS_SERIAL_RESULT
        # Examples: PRESS_..., HELIUM_...
        compact_station = parts[0].upper() if parts else ""
        if len(parts) == 5 and compact_station in {"PRESS", "HELIUM", "ADJ"}:
            return {
                "part": parts[0],
            "station": compact_station,
                "program": "",
                "date_time": f"{parts[1]} {parts[2]}",
                "date": parts[1],
                "time": parts[2],
                "serial": parts[3],
                "result": parts[4],
            }

        if len(parts) < 7:
            return {
                "part": "",
                "station": "",
                "program": "",
                "date_time": "",
                "date": "",
                "time": "",
                "serial": "",
                "result": "",
            }

        station_parts = parts[1:-5]
        date_value = parts[-4]
        time_value = parts[-3]
        return {
            "part": parts[0],
            "station": "_".join(station_parts),
            "program": parts[-5],
            "date_time": f"{date_value} {time_value}",
            "date": date_value,
            "time": time_value,
            "serial": parts[-2],
            "result": parts[-1],
        }

    def _apply_result_styling(self, item: QTreeWidgetItem, result: str) -> None:
        result_upper = result.strip().upper()
        if result_upper == "NOK":
            background = QBrush(QColor("#f8d7da"))
        elif result_upper == "OK":
            background = QBrush(QColor("#d4edda"))
        else:
            return

        for column in range(self.csv_tree.columnCount()):
            item.setBackground(column, background)

    def _sort_tree_by_mtime(self, parent: QTreeWidgetItem) -> None:
        children = [parent.child(i) for i in range(parent.childCount())]
        for child in children:
            self._sort_tree_by_mtime(child)

        children.sort(
            key=lambda item: item.data(0, self.ROLE_MTIME) or 0,
            reverse=True,
        )
        parent.takeChildren()
        if children:
            parent.addChildren(children)

    def _resize_tree_columns(self) -> None:
        header = self.csv_tree.header()
        for column in range(self.csv_tree.columnCount()):
            if column == self.COL_FILENAME:
                continue
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
            self.csv_tree.resizeColumnToContents(column)
        for column in range(self.csv_tree.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

    def _restore_window_state(self) -> None:
        window_state = self.saved_ui_state.get("window", {})
        width = window_state.get("width")
        height = window_state.get("height")
        if isinstance(width, int) and isinstance(height, int):
            self.resize(width, height)

    def _apply_saved_widget_sizes(self) -> None:
        if self.ui_state_applied:
            return

        splitter_sizes = self.saved_ui_state.get("splitter_sizes")
        if isinstance(splitter_sizes, list) and len(splitter_sizes) == 2:
            if all(isinstance(size, int) and size > 0 for size in splitter_sizes):
                self.main_splitter.setSizes(splitter_sizes)

        column_widths = self.saved_ui_state.get("column_widths", {})
        if isinstance(column_widths, dict):
            for column in range(self.csv_tree.columnCount()):
                saved_width = column_widths.get(str(column))
                if isinstance(saved_width, int) and saved_width > 0:
                    self.csv_tree.setColumnWidth(column, saved_width)

        # Per-profile widths override the global defaults
        self._apply_column_widths(self._profile_column_widths.get(self.active_profile_index, {}))

        column_visibility = self.saved_ui_state.get("column_visibility", {})
        if isinstance(column_visibility, dict):
            for column in range(self.csv_tree.columnCount()):
                is_visible = column_visibility.get(str(column), True)
                self.csv_tree.setColumnHidden(column, not is_visible)

        # Per-profile visibility overrides the global defaults
        self._apply_column_visibility(self._profile_column_visibility.get(self.active_profile_index, {}))

        column_order = self.saved_ui_state.get("column_order", [])
        if isinstance(column_order, list):
            self._apply_column_order(column_order)

        # Per-profile order overrides the global defaults
        self._apply_column_order(self._profile_column_order.get(self.active_profile_index, []))

        self.ui_state_applied = True

    def apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        visible_files = 0
        for i in range(self.csv_tree.topLevelItemCount()):
            item = self.csv_tree.topLevelItem(i)
            visible_files += self._apply_filter_to_item(item, needle)

        if needle:
            self.csv_tree.expandAll()
        self.statusBar().showMessage(f"Visible files: {visible_files}", 3000)

    def _apply_filter_to_item(self, item: QTreeWidgetItem, needle: str) -> int:
        file_path = item.data(0, self.ROLE_PATH)
        if file_path:
            haystack = str(file_path).lower()
            visible = needle in haystack if needle else True
            item.setHidden(not visible)
            return 1 if visible else 0

        visible_files = 0
        for i in range(item.childCount()):
            visible_files += self._apply_filter_to_item(item.child(i), needle)

        name_match = needle in item.text(0).lower() if needle else True
        visible = bool(visible_files) or name_match
        item.setHidden(not visible)
        return visible_files

    def _select_first_visible_file(self) -> None:
        first = self._find_first_visible_file(self.csv_tree.invisibleRootItem())
        if first is not None:
            self.csv_tree.setCurrentItem(first)

    def _find_first_visible_file(self, parent: QTreeWidgetItem) -> QTreeWidgetItem | None:
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.isHidden():
                continue
            if child.data(0, self.ROLE_PATH):
                return child
            nested = self._find_first_visible_file(child)
            if nested is not None:
                return nested
        return None

    def preview_selected(self) -> None:
        item = self.csv_tree.currentItem()
        if item is None or item.isHidden():
            return

        csv_value = item.data(0, self.ROLE_PATH)
        if not csv_value:
            return

        csv_path = Path(csv_value)
        if not csv_path.exists():
            self._show_warning(f"Selected file no longer exists: {csv_path}")
            return

        try:
            out_path = self._build_output_path(csv_path)
            self.convert_file(csv_path, out_path)
            self.current_csv_path = csv_path
            if self.uses_webengine:
                self.web_view.load(QUrl.fromLocalFile(str(out_path)))
            else:
                html_text = out_path.read_text(encoding="utf-8", errors="replace")
                self.web_view.setHtml(html_text)
            self.statusBar().showMessage(f"Preview loaded: {csv_path.name}", 4000)
        except Exception as exc:
            self._show_error(f"Failed to generate HTML preview for\n{csv_path}\n\n{exc}")

    def _build_output_path(self, csv_path: Path) -> Path:
        digest = hashlib.sha1(str(csv_path).encode("utf-8")).hexdigest()[:10]
        filename = f"{csv_path.stem}_{digest}.html"
        return self.generated_dir / filename

    def on_textbrowser_link_clicked(self, url) -> None:
        if is_export_measurement_url(url.toString()):
            self.export_current_measurement_csv()
            return
        if is_copy_measurement_url(url.toString()):
            self.export_current_measurement_csv(copy_only=True)
            return
        QDesktopServices.openUrl(url)

    def export_current_measurement_csv(self, copy_only: bool = False) -> None:
        csv_path = self.current_csv_path
        if csv_path is None:
            current_item = self.csv_tree.currentItem()
            if current_item is not None:
                csv_value = current_item.data(0, self.ROLE_PATH)
                if csv_value:
                    csv_path = Path(csv_value)

        if csv_path is None or not csv_path.exists():
            self._show_warning("No active CSV selected for export.")
            return

        try:
            measurement_csv = extract_measurement_section_csv(csv_path)
            if not measurement_csv:
                self._show_warning("No [Measurement] section found in selected CSV.")
                return

            if copy_only:
                QApplication.clipboard().setText(measurement_csv)
                print(f"[MeasurementCopy] success: copied from {csv_path.name}")
                self.statusBar().showMessage("Measurement data copied to clipboard.", 5000)
                return

            output_path = csv_path.with_name(f"{csv_path.stem}_Measurement.csv")
            output_path.write_text(measurement_csv, encoding="utf-8")
            self.statusBar().showMessage(f"Measurement exported: {output_path.name}", 5000)
        except Exception as exc:
            action = "copy Measurement data" if copy_only else "export Measurement CSV"
            self._show_error(f"Failed to {action} for\n{csv_path}\n\n{exc}")

    def _get_converter_callable(self, converter_name: str):
        convert_file = AVAILABLE_CONVERTERS.get(converter_name)
        if convert_file is None:
            raise ValueError(f"Unknown converter: {converter_name}")
        return convert_file

    def _load_saved_ui_state(self) -> dict:
        payload = self._load_settings_payload()
        ui_state = payload.get("ui_state", {}) if payload else {}
        return ui_state if isinstance(ui_state, dict) else {}

    def on_header_context_menu(self, pos) -> None:
        header = self.csv_tree.header()
        menu = QMenu(self)

        for column in range(self.csv_tree.columnCount()):
            column_name = self.csv_tree.headerItem().text(column)
            action = menu.addAction(column_name)
            action.setCheckable(True)
            action.setChecked(not self.csv_tree.isColumnHidden(column))
            action.triggered.connect(lambda checked=False, col=column: self._toggle_column_visibility(col))

        menu.exec(header.mapToGlobal(pos))

    def _toggle_column_visibility(self, column: int) -> None:
        is_hidden = self.csv_tree.isColumnHidden(column)
        self.csv_tree.setColumnHidden(column, not is_hidden)

    def _load_settings_payload(self) -> dict:
        if not self.settings_path.exists():
            return {}

        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        return payload if isinstance(payload, dict) else {}

    def _save_settings(self) -> None:
        payload = self._load_settings_payload()
        payload["profiles"] = self.profiles
        payload["active_profile_index"] = self.active_profile_index

        # Backward-compatible single-profile keys
        active = self.profiles[self.active_profile_index]
        payload["kistler_folder"] = active["folder"]
        payload["converter_name"] = active["converter_name"]
        payload["converter_script"] = BUILT_IN_CONVERTER_SETTING
        try:
            self.settings_path.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self._show_warning(f"Failed to save settings file:\n{exc}")

    def _save_ui_state(self) -> None:
        payload = self._load_settings_payload()
        self._profile_column_widths[self.active_profile_index] = self._get_column_widths()
        self._profile_column_visibility[self.active_profile_index] = self._get_column_visibility()
        self._profile_column_order[self.active_profile_index] = self._get_column_order()
        payload["ui_state"] = {
            "window": {
                "width": self.width(),
                "height": self.height(),
            },
            "splitter_sizes": self.main_splitter.sizes(),
            "column_widths": self._get_column_widths(),
            "column_widths_by_profile": {
                str(k): v for k, v in self._profile_column_widths.items()
            },
            "column_visibility": self._get_column_visibility(),
            "column_visibility_by_profile": {
                str(k): v for k, v in self._profile_column_visibility.items()
            },
            "column_order": self._get_column_order(),
            "column_order_by_profile": {
                str(k): v for k, v in self._profile_column_order.items()
            },
        }
        try:
            self.settings_path.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self._show_warning(f"Failed to save settings file:\n{exc}")

    def closeEvent(self, event) -> None:
        self._save_settings()
        self._save_ui_state()
        super().closeEvent(event)

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Report Viewer", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Report Viewer", message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Report Viewer")
    window = KistlerReportViewer()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
