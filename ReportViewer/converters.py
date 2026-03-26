"""
Converter registry for ReportViewer.

To add a new converter:
  1. Implement a convert_file(input_path, output_path) function in csv_to_html/<name>.py
  2. Import it here and add it to AVAILABLE_CONVERTERS.
"""

from csv_to_html.kisler import convert_file as _kistler_convert
from csv_to_html.helium import convert_file as _helium_convert
from csv_to_html.press import convert_file as _press_convert
from csv_to_html.adj import convert_file as _adj_convert

AVAILABLE_CONVERTERS: dict = {
    "KISTLER": _kistler_convert,
    "HMI-HELIUM": _helium_convert,
    "HMI-PRESS": _press_convert,
  "ADJ": _adj_convert,
}

DEFAULT_CONVERTER_NAME: str = "KISTLER"
