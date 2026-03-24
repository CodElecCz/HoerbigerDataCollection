#!/usr/bin/env python3
"""
Qt viewer for KISTLER CSV reports.

Features:
- Recursively scans a selected KISTLER directory for CSV files
- Lists discovered CSV files with filtering
- Converts selected CSV to HTML using csv_to_html/kisler.py
- Displays generated HTML in an embedded browser
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Callable


def load_qt_bindings():
    """Load Qt classes from PySide6 or PyQt6 at runtime."""
    last_error = None
    for binding in ("PySide6", "PyQt6"):
        try:
            qt_core = importlib.import_module(f"{binding}.QtCore")
            qt_widgets = importlib.import_module(f"{binding}.QtWidgets")
            qt_web = importlib.import_module(f"{binding}.QtWebEngineWidgets")
            return {
                "Qt": qt_core.Qt,
                "QUrl": qt_core.QUrl,
                "QApplication": qt_widgets.QApplication,
                "QFileDialog": qt_widgets.QFileDialog,
                "QHBoxLayout": qt_widgets.QHBoxLayout,
                "QLabel": qt_widgets.QLabel,
                "QLineEdit": qt_widgets.QLineEdit,
                "QMainWindow": qt_widgets.QMainWindow,
                "QMessageBox": qt_widgets.QMessageBox,
                "QPushButton": qt_widgets.QPushButton,
                "QSplitter": qt_widgets.QSplitter,
                "QStatusBar": qt_widgets.QStatusBar,
                "QTabWidget": qt_widgets.QTabWidget,
                "QTreeWidget": qt_widgets.QTreeWidget,
                "QTreeWidgetItem": qt_widgets.QTreeWidgetItem,
                "QVBoxLayout": qt_widgets.QVBoxLayout,
                "QWidget": qt_widgets.QWidget,
                "QWebEngineView": qt_web.QWebEngineView,
            }
        except Exception as exc:
            last_error = exc
    raise ImportError(
        "Neither PySide6 nor PyQt6 with QtWebEngine is available. "
        "Install one of: 'pip install PySide6' or 'pip install PyQt6 PyQt6-WebEngine'."
    ) from last_error


QT = load_qt_bindings()
Qt = QT["Qt"]
QUrl = QT["QUrl"]
QApplication = QT["QApplication"]
QFileDialog = QT["QFileDialog"]
QHBoxLayout = QT["QHBoxLayout"]
QLabel = QT["QLabel"]
QLineEdit = QT["QLineEdit"]
QMainWindow = QT["QMainWindow"]
QMessageBox = QT["QMessageBox"]
QPushButton = QT["QPushButton"]
QSplitter = QT["QSplitter"]
QStatusBar = QT["QStatusBar"]
QTabWidget = QT["QTabWidget"]
QTreeWidget = QT["QTreeWidget"]
QTreeWidgetItem = QT["QTreeWidgetItem"]
QVBoxLayout = QT["QVBoxLayout"]
QWidget = QT["QWidget"]
QWebEngineView = QT["QWebEngineView"]


def load_converter(converter_path: Path) -> Callable:
    """Load convert_file from the CSV-to-HTML converter script."""
    if not converter_path.exists():
        raise FileNotFoundError(f"Converter script not found: {converter_path}")

    spec = importlib.util.spec_from_file_location("kistler_csv_to_html", converter_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load converter module from {converter_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "convert_file"):
        raise AttributeError("Converter script does not define convert_file")

    return module.convert_file


class KistlerReportViewer(QMainWindow):
    ROLE_PATH = Qt.ItemDataRole.UserRole
    ROLE_MTIME = Qt.ItemDataRole.UserRole + 1

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Report Viewer")
        self.resize(1400, 850)

        self.base_dir = Path(__file__).resolve().parent
        self.default_csv_root = (self.base_dir.parent / "Stations" / "KISLER").resolve()
        self.default_converter_path = self.base_dir / "csv_to_html" / "kisler.py"
        self.settings_path = self.base_dir / "report_viewer_settings.json"
        self.converter_path = self._load_saved_converter_path() or self.default_converter_path

        self.generated_dir = Path(tempfile.gettempdir()) / "kistler_report_viewer_html"
        self.generated_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.convert_file = load_converter(self.converter_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Initialization Error",
                f"Failed to load converter:\n{exc}",
            )
            raise

        self._build_ui()
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

    def _create_viewer_tab(self) -> QWidget:
        viewer = QWidget(self)
        layout = QVBoxLayout(viewer)

        # Path is managed in Settings; keep this internal field for refresh logic.
        self.dir_edit = QLineEdit()

        controls = QHBoxLayout()
        controls.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_csv_list)
        controls.addWidget(refresh_btn)

        layout.addLayout(controls)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Type to filter by file name or folder")
        self.filter_edit.textChanged.connect(self.apply_filter)
        filter_row.addWidget(self.filter_edit, 1)
        layout.addLayout(filter_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.csv_tree = QTreeWidget()
        self.csv_tree.setHeaderHidden(True)
        self.csv_tree.itemSelectionChanged.connect(self.preview_selected)
        splitter.addWidget(self.csv_tree)

        self.web_view = QWebEngineView()
        splitter.addWidget(self.web_view)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 970])

        layout.addWidget(splitter, 1)
        return viewer

    def _create_settings_tab(self) -> QWidget:
        settings = QWidget(self)
        layout = QVBoxLayout(settings)

        title = QLabel("Default Settings")
        layout.addWidget(title)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("KISTLER Folder:"))

        self.settings_dir_edit = QLineEdit()
        self.settings_dir_edit.setPlaceholderText("Choose default KISTLER folder path")
        folder_row.addWidget(self.settings_dir_edit, 1)

        settings_browse_btn = QPushButton("Browse...")
        settings_browse_btn.clicked.connect(self.on_settings_browse)
        folder_row.addWidget(settings_browse_btn)

        save_btn = QPushButton("Save As Default")
        save_btn.clicked.connect(self.on_save_settings)
        folder_row.addWidget(save_btn)

        layout.addLayout(folder_row)

        converter_row = QHBoxLayout()
        converter_row.addWidget(QLabel("CSV to HTML Script:"))

        self.settings_converter_edit = QLineEdit()
        self.settings_converter_edit.setPlaceholderText("Choose kisler.py converter script path")
        converter_row.addWidget(self.settings_converter_edit, 1)

        converter_browse_btn = QPushButton("Browse...")
        converter_browse_btn.clicked.connect(self.on_converter_browse)
        converter_row.addWidget(converter_browse_btn)

        layout.addLayout(converter_row)

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
        self._save_settings(initial, self.converter_path)
        self.dir_edit.setText(str(initial))
        self.settings_dir_edit.setText(str(initial))
        self.settings_converter_edit.setText(str(self.converter_path))
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

        converter_text = self.settings_converter_edit.text().strip()
        if not converter_text:
            self._show_warning("Please choose a CSV to HTML converter script in Settings.")
            return

        converter_path = Path(converter_text)
        if not converter_path.exists() or not converter_path.is_file():
            self._show_warning(f"Converter script does not exist: {converter_path}")
            return

        try:
            convert_file = load_converter(converter_path)
        except Exception as exc:
            self._show_error(f"Failed to load converter script:\n{exc}")
            return

        self.dir_edit.setText(str(selected_path))
        self.convert_file = convert_file
        self.converter_path = converter_path
        self._save_settings(selected_path, converter_path)
        self.statusBar().showMessage(f"Saved KISTLER folder setting: {selected_path}", 5000)
        self.refresh_csv_list()

    def on_converter_browse(self) -> None:
        start_file = self.settings_converter_edit.text().strip() or str(self.default_converter_path)
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV to HTML converter script",
            start_file,
            "Python Files (*.py);;All Files (*)",
        )
        if not selected:
            return
        self.settings_converter_edit.setText(selected)

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

            file_item = QTreeWidgetItem([rel.parts[-1]])
            file_item.setData(0, self.ROLE_PATH, str(csv_file))
            file_item.setData(0, self.ROLE_MTIME, mtime)
            file_item.setToolTip(0, str(csv_file))
            parent.addChild(file_item)

        self._sort_tree_by_mtime(self.csv_tree.invisibleRootItem())

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
            self.web_view.load(QUrl.fromLocalFile(str(out_path)))
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

    def _load_saved_converter_path(self) -> Path | None:
        payload = self._load_settings_payload()
        if not payload:
            return None

        configured = str(payload.get("converter_script", "")).strip()
        if not configured:
            return None
        return Path(configured)

    def _load_settings_payload(self) -> dict:
        if not self.settings_path.exists():
            return {}

        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

        return payload if isinstance(payload, dict) else {}

    def _save_settings(self, folder: Path, converter_path: Path) -> None:
        payload = {
            "kistler_folder": str(folder),
            "converter_script": str(converter_path),
        }
        try:
            self.settings_path.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self._show_warning(f"Failed to save settings file:\n{exc}")

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
