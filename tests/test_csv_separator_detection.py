"""
Regression test for GitHub #52 — CSV separator auto-detection.

European-locale Excel exports use `;` as the CSV delimiter because `,`
is the decimal separator in those locales. OpenALAQS historically
hardcoded `,` everywhere, silently producing single-column DataFrames
for `;`-delimited files.

Fix: `csv_interface.detect_separator()` sniffs the file and returns
the detected delimiter. All 4 user-facing CSV input paths
(movements/meteo/emissions/ADS-B) route through it.
"""

import os
import tempfile
from pathlib import Path

import pandas as pd


class TestIssue52DetectSeparator:
    """Unit tests for the detect_separator helper."""

    def _write(self, content: str) -> str:
        """Write content to a tmp file, return path. Caller must unlink."""
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        Path(path).write_text(content, encoding="utf-8")
        return path

    def test_detects_comma(self):
        from open_alaqs.core.tools.csv_interface import detect_separator

        path = self._write("a,b,c\n1,2,3\n4,5,6\n")
        try:
            assert detect_separator(path) == ","
        finally:
            os.unlink(path)

    def test_detects_semicolon(self):
        from open_alaqs.core.tools.csv_interface import detect_separator

        path = self._write("a;b;c\n1;2;3\n4;5;6\n")
        try:
            assert detect_separator(path) == ";"
        finally:
            os.unlink(path)

    def test_detects_tab(self):
        from open_alaqs.core.tools.csv_interface import detect_separator

        path = self._write("a\tb\tc\n1\t2\t3\n4\t5\t6\n")
        try:
            assert detect_separator(path) == "\t"
        finally:
            os.unlink(path)

    def test_empty_file_defaults_to_comma(self):
        from open_alaqs.core.tools.csv_interface import detect_separator

        path = self._write("")
        try:
            assert detect_separator(path) == ","
        finally:
            os.unlink(path)

    def test_single_column_defaults_to_comma(self):
        """File with no separator at all → default to comma."""
        from open_alaqs.core.tools.csv_interface import detect_separator

        path = self._write("header\nrow1\nrow2\n")
        try:
            assert detect_separator(path) == ","
        finally:
            os.unlink(path)

    def test_european_decimal_comma_still_detected_as_semicolon(self):
        """European-locale Excel: `;` delimiter with `,` as decimal separator.
        Sniffer must return `;`, not `,`."""
        from open_alaqs.core.tools.csv_interface import detect_separator

        path = self._write("Name;Height;Speed\nG1;30,3;15,5\nG2;12,0;8,0\n")
        try:
            assert detect_separator(path) == ";"
        finally:
            os.unlink(path)


class TestIssue52ReadCsvUsesAutoDetect:
    """Verify csv_interface.read_csv() uses the auto-detected separator."""

    def _write(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        Path(path).write_text(content, encoding="utf-8")
        return path

    def test_read_csv_handles_comma(self):
        from open_alaqs.core.tools.csv_interface import read_csv

        path = self._write("a,b,c\n1,2,3\n")
        try:
            rows = read_csv(path)
            assert rows == [["a", "b", "c"], ["1", "2", "3"]]
        finally:
            os.unlink(path)

    def test_read_csv_handles_semicolon(self):
        """Before fix: this returned [[\"a;b;c\"], [\"1;2;3\"]] — one col!"""
        from open_alaqs.core.tools.csv_interface import read_csv

        path = self._write("a;b;c\n1;2;3\n")
        try:
            rows = read_csv(path)
            assert rows == [["a", "b", "c"], ["1", "2", "3"]]
        finally:
            os.unlink(path)


class TestIssue52AdsbHandlesSemicolon:
    """ADS-B CSV parsing must handle `;` delimiter via auto-detect."""

    def _write(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        Path(path).write_text(content, encoding="utf-8")
        return path

    def test_detect_separator_handles_adsb_semicolon(self):
        """The auto-detect helper must correctly identify `;` on a
        representative ADS-B file. This is the building block that
        ads_b.validate_adsb_file and import_adsb_file both use."""
        from open_alaqs.core.tools.csv_interface import detect_separator

        content = (
            "flight_id;timestamp;lat;lon;altitude;type;power_setting;fuel_flow\n"
            "F001;2024-01-01T00:00:00;52.0;4.0;1000;arrival;0.50;0.5\n"
            "F001;2024-01-01T00:00:01;52.01;4.01;1100;arrival;0.55;0.55\n"
        )
        path = self._write(content)
        try:
            assert detect_separator(path) == ";"
            # And confirm pandas can actually parse it with that sep
            df = pd.read_csv(path, sep=";")
            assert list(df.columns) == [
                "flight_id",
                "timestamp",
                "lat",
                "lon",
                "altitude",
                "type",
                "power_setting",
                "fuel_flow",
            ]
            assert len(df) == 2
        finally:
            os.unlink(path)
