#!/usr/bin/env python3
"""
Qt viewer for KISTLER CSV reports.

Features:
- Recursively scans a selected KISTLER directory for CSV files
- Lists discovered CSV files with filtering
- Converts selected CSV to HTML using the built-in csv_to_html.kisler module
- Displays generated HTML in an embedded browser
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

from converters import AVAILABLE_CONVERTERS, DEFAULT_CONVERTER_NAME

BUILT_IN_CONVERTER_SETTING = "built-in:csv_to_html.kisler.convert_file"


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
        except Exception:
            qt_web = None
    except Exception as pyqt_exc:
        last_error = pyqt_exc
        try:
            from PySide6 import QtCore as qt_core
            from PySide6 import QtGui as qt_gui
            from PySide6 import QtWidgets as qt_widgets
            try:
                from PySide6 import QtWebEngineWidgets as qt_web
            except Exception:
                qt_web = None
        except Exception as pyside_exc:
            last_error = pyside_exc
            raise ImportError(
                "Neither PySide6 nor PyQt6 is available. "
                "Install one of: 'pip install PySide6' or 'pip install PyQt6'."
            ) from last_error

    return {
        "QBrush": qt_gui.QBrush,
        "QColor": qt_gui.QColor,
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
    }


QT = load_qt_bindings()
QBrush = QT["QBrush"]
QColor = QT["QColor"]
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
        self.converter_name = self._load_saved_converter_name()
        self.generated_dir = Path(tempfile.gettempdir()) / "kistler_report_viewer_html"
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

        self.dir_edit = QLineEdit()

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
        else:
            self.web_view = QTextBrowser()
            self.web_view.setOpenExternalLinks(True)
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

        kistler_group = QGroupBox("KISTLER")
        group_layout = QVBoxLayout()

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Folder:"))

        self.settings_dir_edit = QLineEdit()
        self.settings_dir_edit.setPlaceholderText("Choose default KISTLER folder path")
        folder_row.addWidget(self.settings_dir_edit, 1)

        settings_browse_btn = QPushButton("Browse...")
        settings_browse_btn.clicked.connect(self.on_settings_browse)
        folder_row.addWidget(settings_browse_btn)

        save_btn = QPushButton("Save As Default")
        save_btn.clicked.connect(self.on_save_settings)
        folder_row.addWidget(save_btn)

        group_layout.addLayout(folder_row)

        converter_row = QHBoxLayout()
        converter_row.addWidget(QLabel("CSV to HTML:"))
        self.settings_converter_combo = QComboBox()
        self.settings_converter_combo.addItems(list(AVAILABLE_CONVERTERS.keys()))
        self.settings_converter_combo.setCurrentText(self.converter_name)
        converter_row.addWidget(self.settings_converter_combo, 1)
        group_layout.addLayout(converter_row)

        kistler_group.setLayout(group_layout)
        layout.addWidget(kistler_group)

        hint = QLabel(f"Settings file: {self.settings_path.name}")
        layout.addWidget(hint)
        layout.addStretch(1)

        return settings

    def _set_initial_directory(self) -> None:
        saved_dir = self._load_saved_kistler_folder()
        if saved_dir is not None and saved_dir.exists() and saved_dir.is_dir():
            initial = saved_dir
        else:
            initial = self.default_csv_root if self.default_csv_root.exists() else self.base_dir
        self._save_settings(initial)
        self.dir_edit.setText(str(initial))
        self.settings_dir_edit.setText(str(initial))
        self.settings_converter_combo.setCurrentText(self.converter_name)
        self.refresh_csv_list()

    def on_browse(self) -> None:
        start_dir = self.dir_edit.text().strip() or str(self.base_dir)
        selected = QFileDialog.getExistingDirectory(self, "Select KISTLER CSV Root", start_dir)
        if not selected:
            return
        self.dir_edit.setText(selected)
        self.settings_dir_edit.setText(selected)
        self.refresh_csv_list()

    def on_settings_browse(self) -> None:
        start_dir = self.settings_dir_edit.text().strip() or str(self.default_csv_root)
        selected = QFileDialog.getExistingDirectory(self, "Select default KISTLER folder", start_dir)
        if not selected:
            return
        self.settings_dir_edit.setText(selected)

    def on_save_settings(self) -> None:
        selected = self.settings_dir_edit.text().strip()
        if not selected:
            self._show_warning("Please choose a KISTLER folder in Settings.")
            return

        selected_path = Path(selected)
        if not selected_path.exists() or not selected_path.is_dir():
            self._show_warning(f"Folder does not exist: {selected_path}")
            return

        converter_name = self.settings_converter_combo.currentText().strip()
        if converter_name not in AVAILABLE_CONVERTERS:
            self._show_warning(f"Unsupported CSV to HTML converter: {converter_name}")
            return

        self.dir_edit.setText(str(selected_path))
        self.converter_name = converter_name
        self.convert_file = self._get_converter_callable(converter_name)
        self._save_settings(selected_path)
        self.statusBar().showMessage(f"Saved KISTLER folder setting: {selected_path}", 5000)
        self.refresh_csv_list()

    def refresh_csv_list(self) -> None:
        root_text = self.dir_edit.text().strip()
        if not root_text:
            self._show_warning("Please choose a folder first.")
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

        column_visibility = self.saved_ui_state.get("column_visibility", {})
        if isinstance(column_visibility, dict):
            for column in range(self.csv_tree.columnCount()):
                is_visible = column_visibility.get(str(column), True)
                self.csv_tree.setColumnHidden(column, not is_visible)

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

    def _load_saved_kistler_folder(self) -> Path | None:
        payload = self._load_settings_payload()
        if not payload:
            return None

        configured = str(payload.get("kistler_folder", "")).strip()
        if not configured:
            return None
        return Path(configured)

    def _load_saved_converter_name(self) -> str:
        payload = self._load_settings_payload()
        if not payload:
            return DEFAULT_CONVERTER_NAME

        configured_name = str(payload.get("converter_name", "")).strip()
        if configured_name in AVAILABLE_CONVERTERS:
            return configured_name

        configured_script = str(payload.get("converter_script", "")).strip()
        if configured_script == BUILT_IN_CONVERTER_SETTING:
            return DEFAULT_CONVERTER_NAME

        return DEFAULT_CONVERTER_NAME

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

    def _save_settings(self, folder: Path) -> None:
        payload = self._load_settings_payload()
        payload["kistler_folder"] = str(folder)
        payload["converter_name"] = self.converter_name
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
        payload["ui_state"] = {
            "window": {
                "width": self.width(),
                "height": self.height(),
            },
            "splitter_sizes": self.main_splitter.sizes(),
            "column_widths": {
                str(column): self.csv_tree.columnWidth(column)
                for column in range(self.csv_tree.columnCount())
            },
            "column_visibility": {
                str(column): not self.csv_tree.isColumnHidden(column)
                for column in range(self.csv_tree.columnCount())
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
