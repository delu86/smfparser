"""CSV, JSON and Excel writers."""

from __future__ import annotations

import logging

import pandas as pd

from .base import Writer

log = logging.getLogger(__name__)

EXCEL_MAX_ROWS = 1_048_575  # one row is the header


class CsvWriter(Writer):
    """One <table>.csv per table in `dir`; existing files are overwritten."""

    def __init__(self, options, resolve) -> None:
        super().__init__(options, resolve)
        self.dir = self.path("dir")
        self.dir.mkdir(parents=True, exist_ok=True)
        self._started: set[str] = set()

    def write(self, table: str, df: pd.DataFrame) -> None:
        first = table not in self._started
        self._started.add(table)
        df.to_csv(
            self.dir / f"{table}.csv",
            mode="w" if first else "a",
            header=first,
            index=False,
            sep=self.options.get("sep", ","),
            encoding=self.options.get("encoding", "utf-8"),
        )


class JsonWriter(Writer):
    """One file per table in `dir`: JSON Lines (<table>.jsonl, default) or a JSON array."""

    def __init__(self, options, resolve) -> None:
        super().__init__(options, resolve)
        self.dir = self.path("dir")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lines = bool(options.get("lines", True))
        self._started: set[str] = set()
        self._frames: dict[str, list[pd.DataFrame]] = {}

    def write(self, table: str, df: pd.DataFrame) -> None:
        if not self.lines:
            self._frames.setdefault(table, []).append(df)
            return
        first = table not in self._started
        self._started.add(table)
        with open(self.dir / f"{table}.jsonl", "w" if first else "a", encoding="utf-8") as f:
            text = df.to_json(orient="records", lines=True, date_format="iso")
            f.write(text if text.endswith("\n") else text + "\n")

    def close(self) -> None:
        for table, frames in self._frames.items():
            pd.concat(frames, ignore_index=True).to_json(
                self.dir / f"{table}.json", orient="records", date_format="iso", indent=self.options.get("indent")
            )


class ExcelWriter(Writer):
    """One workbook at `path`, one sheet per table. Rows are buffered until close."""

    def __init__(self, options, resolve) -> None:
        super().__init__(options, resolve)
        self.file = self.path("path")
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self._frames: dict[str, list[pd.DataFrame]] = {}

    def write(self, table: str, df: pd.DataFrame) -> None:
        self._frames.setdefault(table, []).append(df)

    def close(self) -> None:
        if not self._frames:
            return
        with pd.ExcelWriter(self.file, engine="openpyxl") as xw:
            for table, frames in self._frames.items():
                df = pd.concat(frames, ignore_index=True)
                if len(df) > EXCEL_MAX_ROWS:
                    log.warning("%s: %d rows exceed the Excel sheet limit; truncated to %d",
                                table, len(df), EXCEL_MAX_ROWS)
                    df = df.iloc[:EXCEL_MAX_ROWS]
                df.to_excel(xw, sheet_name=table[:31], index=False)
