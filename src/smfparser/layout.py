"""Declarative description of SMF record sections and their decoding.

Offsets are relative to the start of the section. Self-defining sections are located through
triplets (4-byte offset, 2-byte length, 2-byte count) whose offsets are measured from the start
of the record including the RDW.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from . import decoders as d

# Field kinds -> (decoder, pandas dtype). Decoders get (bytes, codepage).
KINDS: dict[str, tuple[Callable[[bytes, str], Any], str]] = {
    "char": (lambda b, cp: d.ebcdic(b, cp), "string"),
    "uint": (lambda b, cp: d.uint(b), "Int64"),
    "sint": (lambda b, cp: d.sint(b), "Int64"),
    "packed": (lambda b, cp: d.packed(b), "Int64"),
    "date": (lambda b, cp: d.smf_date(b), "datetime64[us]"),
    # seconds, from hundredths of a second / 128-microsecond units
    "sec100": (lambda b, cp: d.hundredths(b), "Float64"),
    "sec128us": (lambda b, cp: d.units_128us(b), "Float64"),
    # hundredths of a second since midnight; combined with Field.date into a datetime
    "time": (lambda b, cp: d.time_of_day(b), "datetime64[us]"),
    "tod": (lambda b, cp: d.stck(b), "datetime64[us]"),
}


@dataclass(frozen=True)
class Field:
    name: str
    offset: int
    length: int
    kind: str = "uint"
    # For kind="time": name of the "date" field (same section) giving the day.
    date: str | None = None
    # For kind="time": a datetime field this time cannot precede; if it does, the time is
    # taken to be on the following day (e.g. allocation start after a midnight crossing).
    not_before: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: unknown field kind {self.kind!r}")
        if self.kind == "time" and self.date is None:
            raise ValueError(f"{self.name}: time fields need a date field")

    @property
    def column(self) -> str:
        return self.name.lower()

    @property
    def dtype(self) -> str:
        return KINDS[self.kind][1]


@dataclass(frozen=True)
class Section:
    """A fixed-layout section. Fields past the section's actual length decode to None."""

    name: str
    fields: tuple[Field, ...]
    _by_name: dict[str, Field] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_name", {f.name: f for f in self.fields})

    def schema(self) -> dict[str, str]:
        return {f.column: f.dtype for f in self.fields}

    def empty(self) -> dict[str, Any]:
        return {f.column: None for f in self.fields}

    def decode(self, buf: bytes, start: int, length: int, codepage: str) -> dict[str, Any]:
        end = min(start + length, len(buf))
        row: dict[str, Any] = {}
        for f in self.fields:
            lo = start + f.offset
            hi = lo + f.length
            row[f.column] = KINDS[f.kind][0](buf[lo:hi], codepage) if hi <= end else None
        # Resolve times of day to datetimes once all dates are known.
        for f in self.fields:
            if f.kind != "time" or row[f.column] is None:
                continue
            day = row[self._by_name[f.date].column]
            if day is None:
                row[f.column] = None
                continue
            ts = datetime(day.year, day.month, day.day) + row[f.column]
            floor = row.get(f.not_before.lower()) if f.not_before else None
            if isinstance(floor, datetime) and ts < floor:
                ts += timedelta(days=1)
            row[f.column] = ts
        return row


@dataclass(frozen=True)
class Triplet:
    offset: int
    length: int
    count: int


def triplet(buf: bytes, at: int) -> Triplet:
    """Read an offset(4)/length(2)/count(2) triplet; zero if outside the record."""
    if at + 8 > len(buf):
        return Triplet(0, 0, 0)
    return Triplet(d.uint(buf[at : at + 4]), d.uint(buf[at + 4 : at + 6]), d.uint(buf[at + 6 : at + 8]))


def occurrences(buf: bytes, t: Triplet) -> Iterator[int]:
    """Start offsets of each occurrence of a fixed-length section described by a triplet."""
    if t.count == 0 or t.length == 0:
        return
    for i in range(t.count):
        start = t.offset + i * t.length
        if start + t.length > len(buf):
            return
        yield start
