"""Read -> filter -> parse -> chunked DataFrames -> writers."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .config import Config
from .reader import ReaderStats, read_records
from .records.header import record_subtype, record_type
from .registry import ParseContext, ParserOptions, RecordParser, supported_types
from .writers import Writer, create_writer

log = logging.getLogger(__name__)


@dataclass
class RunStats:
    read: Counter = field(default_factory=Counter)  # (type, subtype) -> records
    kept: Counter = field(default_factory=Counter)
    failed: Counter = field(default_factory=Counter)
    unsupported: Counter = field(default_factory=Counter)  # type -> records kept by filter, no parser
    rows: Counter = field(default_factory=Counter)  # table -> rows written
    reader: ReaderStats = field(default_factory=ReaderStats)


def to_frame(rows: list[dict[str, Any]], schema: dict[str, str]) -> pd.DataFrame:
    """Build a DataFrame with the table's fixed columns and dtypes."""
    df = pd.DataFrame.from_records(rows, columns=list(schema))
    for col, dtype in schema.items():
        if dtype.startswith("datetime64"):
            df[col] = pd.to_datetime(df[col]).astype(dtype)
            continue
        try:
            df[col] = df[col].astype(dtype)
        except (OverflowError, TypeError, ValueError):
            log.warning("column %s does not fit %s; stored as float", col, dtype)
            df[col] = df[col].astype("Float64")
    return df


class Pipeline:
    def __init__(self, config: Config, writers: list[Writer] | None = None) -> None:
        self.config = config
        self.parsers: dict[int, RecordParser] = {
            rtype: cls(ParserOptions(config.record_options.get(rtype, {})))
            for rtype, cls in supported_types().items()
        }
        self.schemas: dict[str, dict[str, str]] = {}
        for parser in self.parsers.values():
            self.schemas.update(parser.schemas())
        self.writers = writers if writers is not None else [create_writer(t, config) for t in config.targets]
        self.stats = RunStats()
        self._buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def run(self, paths: list[Path] | None = None) -> RunStats:
        try:
            for path in paths if paths is not None else self.config.input_paths():
                self.process_file(path)
            for table in list(self._buffers):
                self._flush(table)
        finally:
            for w in self.writers:
                w.close()
        return self.stats

    def process_file(self, path: Path) -> None:
        log.info("reading %s", path)
        name = str(path)
        flt, chunk = self.config.filter, self.config.chunk_rows
        for rec, offset in read_records(path, self.stats.reader):
            rtype, subtype = record_type(rec), record_subtype(rec)
            key = (rtype, subtype)
            self.stats.read[key] += 1
            if not flt.keep(rtype, subtype):
                continue
            parser = self.parsers.get(rtype)
            if parser is None:
                self.stats.unsupported[rtype] += 1
                continue
            try:
                out = list(parser.parse(rec, ParseContext(name, offset, self.config.codepage)))
            except Exception as e:  # one bad record must not stop the run
                self.stats.failed[key] += 1
                log.warning("%s offset %d: type %s subtype %s not parsed: %s", name, offset, rtype, subtype, e)
                continue
            self.stats.kept[key] += 1
            for table, row in out:
                buf = self._buffers[table]
                buf.append(row)
                if len(buf) >= chunk:
                    self._flush(table)

    def _flush(self, table: str) -> None:
        rows = self._buffers.pop(table, [])
        if not rows:
            return
        df = to_frame(rows, self.schemas[table])
        for w in self.writers:
            w.write(table, df)
        self.stats.rows[table] += len(df)


def run(config: Config, paths: list[Path] | None = None) -> RunStats:
    return Pipeline(config).run(paths)
