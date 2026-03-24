#!/usr/bin/env python3
"""
Qt viewer for KISTLER CSV reports.

Features:
- Recursively scans a selected KISTLER directory for CSV files
- Lists discovered CSV files with filtering
- Converts selected CSV to HTML using KISTLER/kisler_csv_to_html.py
- Displays generated HTML in an embedded browser
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
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
                "QListWidget": qt_widgets.QListWidget,
                "QListWidgetItem": qt_widgets.QListWidgetItem,
                "QMainWindow": qt_widgets.QMainWindow,
                "QMessageBox": qt_widgets.QMessageBox,
                "QPushButton": qt_widgets.QPushButton,
                "QSplitter": qt_widgets.QSplitter,
                "QStatusBar": qt_widgets.QStatusBar,
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
QListWidget = QT["QListWidget"]
QListWidgetItem = QT["QListWidgetItem"]
QMainWindow = QT["QMainWindow"]
QMessageBox = QT["QMessageBox"]
QPushButton = QT["QPushButton"]
QSplitter = QT["QSplitter"]
QStatusBar = QT["QStatusBar"]
QVBoxLayout = QT["QVBoxLayout"]
QWidget = QT["QWidget"]
QWebEngineView = QT["QWebEngineView"]


def load_converter(converter_path: Path) -> Callable:
    """Load convert_file from KISTLER converter script."""
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
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KISTLER CSV Report Viewer")
        self.resize(1400, 850)

        self.base_dir = Path(__file__).resolve().parent
        self.default_csv_root = (self.base_dir.parent / "Stations" / "KISLER").resolve()
        self.converter_path = self.base_dir / "KISTLER" / "kisler_csv_to_html.py"

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
        layout = QVBoxLayout(root)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("KISTLER Folder:"))

        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("Select a folder containing KISTLER CSV files")
        controls.addWidget(self.dir_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.on_browse)
        controls.addWidget(browse_btn)

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

        self.csv_list = QListWidget()
        self.csv_list.itemSelectionChanged.connect(self.preview_selected)
        splitter.addWidget(self.csv_list)

        self.web_view = QWebEngineView()
        splitter.addWidget(self.web_view)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 970])

        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar(self))

    def _set_initial_directory(self) -> None:
        initial = self.default_csv_root if self.default_csv_root.exists() else self.base_dir
        self.dir_edit.setText(str(initial))
        self.refresh_csv_list()

    def on_browse(self) -> None:
        start_dir = self.dir_edit.text().strip() or str(self.base_dir)
        selected = QFileDialog.getExistingDirectory(self, "Select KISTLER CSV Root", start_dir)
        if not selected:
            return
        self.dir_edit.setText(selected)
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

        files = sorted(root.rglob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)

        self.csv_list.clear()
        if not files:
            self.statusBar().showMessage(f"No CSV files found under {root}", 6000)
            self.web_view.setHtml("<h3>No CSV files found.</h3>")
            return

        for csv_file in files:
            rel = csv_file.relative_to(root)
            item = QListWidgetItem(str(rel))
            item.setData(Qt.ItemDataRole.UserRole, str(csv_file))
            item.setToolTip(str(csv_file))
            self.csv_list.addItem(item)

        self.apply_filter(self.filter_edit.text())
        self.statusBar().showMessage(f"Found {len(files)} CSV files in {root}", 5000)

        if self.csv_list.count() > 0:
            self.csv_list.setCurrentRow(0)

    def apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        visible = 0
        for i in range(self.csv_list.count()):
            item = self.csv_list.item(i)
            haystack = item.text().lower()
            hide = bool(needle) and needle not in haystack
            item.setHidden(hide)
            if not hide:
                visible += 1

        self.statusBar().showMessage(f"Visible files: {visible}", 3000)

    def preview_selected(self) -> None:
        item = self.csv_list.currentItem()
        if item is None or item.isHidden():
            return

        csv_path = Path(item.data(Qt.ItemDataRole.UserRole))
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

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "KISTLER Viewer", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "KISTLER Viewer", message)


def main() -> int:
    app = QApplication(sys.argv)
    window = KistlerReportViewer()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
