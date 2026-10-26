"""SMF type 110 subtype 1: CICS monitoring, performance class (one row per transaction).

A monitoring record is the SMF header, a self-defining section with two triplets (product section
at 28, data section at 36) and the product section, which describes the data: its class (1
dictionary, 3 performance, 4 exception, 5 transaction resource, 6 identity), the list of field
connectors present in each performance record, and where the fixed-length performance records
start.

Performance records are not self-describing: their layout comes from a dictionary (class 1)
record, whose entries give each field's owner, type, id, length, connector, offset and informal
name (nickname). The MCT can exclude fields, so the layout can differ from one region to another.
Phase 1 reads one dictionary from a file (records.110.dictionary) and applies it to every region;
a record whose connector list differs from the dictionary's is rejected.

Field types: A binary count, C EBCDIC text, T 8-byte STCK timestamp (UTC), P packed decimal,
S 12-byte clock (8-byte STCK-format duration + flag byte + 24-bit count).
"""

from __future__ import annotations

import logging
import struct
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .. import decoders as d
from ..layout import occurrences, triplet
from ..reader import read_records
from ..registry import ParseContext, ParserOptions, RecordParser, register
from .header import HEADER_SCHEMA, parse_header, record_subtype, record_type

log = logging.getLogger(__name__)

# Offsets from the start of the record (RDW included).
PRODUCT_TRIPLET = 28

# Offsets within the product section.
PS_SMFMNRVN = 0  # CICS version, X'0730'
PS_SMFMNPRN = 2  # generic APPLID
PS_SMFMNSPN = 10  # specific APPLID
PS_CLASS = 22  # SMFMNCL
PS_CONNECTORS = 24  # triplet: field connectors present in each performance record
PS_RECORDS = 32  # triplet: performance records (dictionary entries in a class 1 record)
PS_TIME_ADJUST = 72  # local time minus UTC, 8-byte signed STCK units
PS_SMFMNJBN = 82  # region job name
PS_SMFMNRSD = 90  # region (job) start date and time
PS_SMFMNRST = 94
PS_SMFMNUIF = 98  # region user ID
PS_SMFMNPDN = 106  # MVS level

CLASS_DICTIONARY = 1
CLASS_PERFORMANCE = 3

DICT_ENTRY_LENGTH = 26
EXCLUDED = 0xFFFF  # dictionary offset of a field excluded by the MCT

# Bit-flag fields; TRANFLAG does not fit Int64, so they are all kept as hex.
FLAG_FIELDS = frozenset({"TRANFLAG", "OTRANFLG", "TASKFLAG", "TERMINFO"})
# Character fields that hold binary data, kept as hex (IBM fields and Omegamon user fields).
HEX_FIELDS = frozenset({
    "NETUOWSX", "TRNGRPID", "RRMSURID", "OTSTID", "OMEGDB2", "CANMQ", "CANPROD1", "CANRES01",
})

TABLE = "smf110_1"

PRODUCT_SCHEMA: dict[str, str] = {
    "smfmnrvn": "string",
    "smfmnprn": "string",
    "smfmnspn": "string",
    "smfmnjbn": "string",
    "smfmnuif": "string",
    "smfmnpdn": "string",
    "smfmnrst": "datetime64[us]",
    "transaction_index": "Int64",
}
DERIVED_SCHEMA: dict[str, str] = {"elapsed": "Float64", "internal_response": "Float64"}


@dataclass(frozen=True)
class DictEntry:
    owner: str  # CMODNAME, e.g. DFHTASK
    kind: str  # CMODTYPE: A, C, T, P or S
    ident: str  # CMODIDNT digits, e.g. 001
    length: int
    connector: int
    offset: int
    nickname: str  # CMODHEAD, e.g. TRAN

    @property
    def included(self) -> bool:
        return self.offset != EXCLUDED

    @property
    def column(self) -> str:
        return f"{self.nickname.lower()}_{self.ident}"


@dataclass(frozen=True)
class Dictionary:
    applid: str  # specific APPLID of the region that wrote it
    entries: tuple[DictEntry, ...]

    @property
    def fields(self) -> tuple[DictEntry, ...]:
        """Fields present in performance records, in record order."""
        return tuple(sorted((e for e in self.entries if e.included), key=lambda e: e.offset))

    @property
    def connectors(self) -> bytes:
        """The connector list a matching performance record carries."""
        return b"".join(e.connector.to_bytes(2, "big") for e in self.entries if e.included)

    @property
    def record_length(self) -> int:
        return max((e.offset + e.length for e in self.entries if e.included), default=0)

    @classmethod
    def from_record(cls, rec: bytes, codepage: str = d.DEFAULT_CODEPAGE) -> Dictionary:
        ps = triplet(rec, PRODUCT_TRIPLET).offset
        if record_type(rec) != 110 or record_subtype(rec) != 1 or ps == 0:
            raise ValueError("not an SMF 110 subtype 1 record")
        if d.uint(rec[ps + PS_CLASS : ps + PS_CLASS + 2]) != CLASS_DICTIONARY:
            raise ValueError("not a CICS monitoring dictionary (class 1) record")
        entries = []
        for pos in occurrences(rec, triplet(rec, ps + PS_RECORDS)):
            b = rec[pos : pos + DICT_ENTRY_LENGTH]
            entries.append(DictEntry(
                owner=d.ebcdic(b[0:8], codepage).strip(),
                kind=d.ebcdic(b[8:9], codepage),
                ident=d.ebcdic(b[9:12], codepage),
                length=d.uint(b[12:14]),
                connector=d.uint(b[14:16]),
                offset=d.uint(b[16:18]),
                nickname=d.ebcdic(b[18:26], codepage).strip(),
            ))
        if not entries:
            raise ValueError("dictionary record has no entries")
        return cls(d.ebcdic(rec[ps + PS_SMFMNSPN : ps + PS_SMFMNSPN + 8], codepage).strip(), tuple(entries))

    @classmethod
    def load(cls, path: str | Path, codepage: str = d.DEFAULT_CODEPAGE) -> Dictionary:
        """The first dictionary record in an SMF file (blocked or RDW-only, spanned or not)."""
        for rec, _ in read_records(path):
            if record_type(rec) != 110 or record_subtype(rec) != 1:
                continue
            ps = triplet(rec, PRODUCT_TRIPLET).offset
            if ps and d.uint(rec[ps + PS_CLASS : ps + PS_CLASS + 2]) == CLASS_DICTIONARY:
                return cls.from_record(rec, codepage)
        raise ValueError(f"{path}: no SMF 110 dictionary record found")


def _seconds(value: int) -> float:
    return value / 4_096_000_000  # STCK-format duration: bit 51 = 1 microsecond


# EBCDIC control characters (x'00'-x'3F', x'FF') become blanks, as in EPV: user fields such as
# CDNUSER1 mix text with binary data.
_BLANK_CONTROLS = bytes(0x40 if b < 0x40 or b == 0xFF else b for b in range(256))


def _text(b: bytes, codepage: str) -> str | None:
    return b.translate(_BLANK_CONTROLS).strip(b"\x40").decode(codepage) or None


def _tod(value: int) -> datetime | None:
    return d.TOD_EPOCH + timedelta(microseconds=value >> 12) if value else None


class _Decoder:
    """Decodes a whole performance record with one struct unpack plus a converter per value."""

    def __init__(self, dictionary: Dictionary, codepage: str, hex_fields: frozenset[str]) -> None:
        fmt = [">"]
        self.columns: list[str] = []
        self.converters: list[Callable[[Any], Any]] = []
        self.schema: dict[str, str] = {}
        self.tod_columns: list[str] = []
        pos = 0
        for e in dictionary.fields:
            if e.offset < pos:
                raise ValueError(f"dictionary field {e.column} overlaps the previous field")
            if e.offset > pos:
                fmt.append(f"{e.offset - pos}x")
            pos = e.offset + e.length
            if e.kind == "S" and e.length == 12:
                fmt.append("QI")
                self._add(e.column, _seconds, "Float64")
                self._add(f"{e.column}_count", lambda v: v & 0xFFFFFF, "Int64")
            elif e.kind == "T" and e.length == 8:
                fmt.append("Q")
                self._add(e.column, _tod, "datetime64[us]")
                self.tod_columns.append(e.column)
            elif e.kind == "P":
                fmt.append(f"{e.length}s")
                self._add(e.column, d.packed, "Int64")
            elif e.kind == "A" and e.nickname not in FLAG_FIELDS:
                fmt.append(f"{e.length}s")
                self._add(e.column, d.uint, "Int64")
            elif e.kind == "C" and e.nickname not in hex_fields:
                fmt.append(f"{e.length}s")
                self._add(e.column, lambda b, cp=codepage: _text(b, cp), "string")
            else:  # flags, binary character fields and anything unexpected
                fmt.append(f"{e.length}s")
                self._add(e.column, lambda b: b.hex() if b.strip(b"\x00") else None, "string")
        self.struct = struct.Struct("".join(fmt))
        cols = {e.column: e for e in dictionary.fields}
        start, stop = cols.get("start_005"), cols.get("stop_006")
        self.elapsed = (start.column, stop.column) if start and stop and start.kind == stop.kind == "T" else None
        tc_wait = cols.get("tciowtt_009")
        self.terminal_wait = tc_wait.column if tc_wait and tc_wait.kind == "S" else None

    def _add(self, column: str, conv: Callable[[Any], Any], dtype: str) -> None:
        self.columns.append(column)
        self.converters.append(conv)
        self.schema[column] = dtype

    def decode(self, rec: bytes, pos: int, adjust: timedelta | None) -> dict[str, Any]:
        values = self.struct.unpack_from(rec, pos)
        row = {c: f(v) for c, f, v in zip(self.columns, self.converters, values)}
        if self.elapsed:
            start, stop = row[self.elapsed[0]], row[self.elapsed[1]]
            row["elapsed"] = (stop - start).total_seconds() if start and stop else None
        else:
            row["elapsed"] = None
        # Internal response time: elapsed minus terminal I/O wait (as EPV's INTRESPDUR).
        wait = row[self.terminal_wait] if self.terminal_wait else None
        row["internal_response"] = row["elapsed"] - wait if row["elapsed"] is not None and wait is not None else None
        if adjust:
            for c in self.tod_columns:
                if row[c] is not None:
                    row[c] += adjust
        return row


@register
class CicsMonitoringParser(RecordParser):
    record_type = 110

    def __init__(self, options: ParserOptions | None = None) -> None:
        super().__init__(options)
        path = self.options.path("dictionary")
        self.dictionary = Dictionary.load(path) if path else None
        self.local_time = bool(self.options.get("local_time", True))
        self.hex_fields = HEX_FIELDS | {str(n).upper() for n in self.options.get("hex", []) or []}
        self._decoders: dict[str, _Decoder] = {}
        self._warned = False
        self._skipped_classes: set[int] = set()

    def _decoder(self, codepage: str) -> _Decoder:
        dec = self._decoders.get(codepage)
        if dec is None:
            assert self.dictionary is not None
            dec = self._decoders[codepage] = _Decoder(self.dictionary, codepage, self.hex_fields)
        return dec

    def schemas(self) -> dict[str, dict[str, str]]:
        if self.dictionary is None:
            return {}
        schema = dict(HEADER_SCHEMA)
        schema.update(PRODUCT_SCHEMA)
        schema.update(self._decoder(d.DEFAULT_CODEPAGE).schema)
        schema.update(DERIVED_SCHEMA)
        return {TABLE: schema}

    def parse(self, rec: bytes, ctx: ParseContext) -> Iterator[tuple[str, dict[str, Any]]]:
        if record_subtype(rec) != 1:
            return
        if self.dictionary is None:
            if not self._warned:
                log.warning("SMF 110 records skipped: no CICS dictionary configured (records.110.dictionary)")
                self._warned = True
            return
        ps = triplet(rec, PRODUCT_TRIPLET).offset
        if ps == 0 or ps + PS_SMFMNPDN + 8 > len(rec):
            raise ValueError("product section missing or short")
        cls = d.uint(rec[ps + PS_CLASS : ps + PS_CLASS + 2])
        if cls != CLASS_PERFORMANCE:
            if cls not in self._skipped_classes:
                log.debug("SMF 110 subtype 1 class %d records are not parsed", cls)
                self._skipped_classes.add(cls)
            return

        conn = triplet(rec, ps + PS_CONNECTORS)
        if rec[conn.offset : conn.offset + conn.length * conn.count] != self.dictionary.connectors:
            raise ValueError("field connectors differ from the dictionary (region with another MCT?)")
        recs = triplet(rec, ps + PS_RECORDS)
        if recs.length != self.dictionary.record_length:
            raise ValueError(f"performance record length {recs.length}, dictionary says "
                             f"{self.dictionary.record_length}")

        cp = ctx.codepage
        base = parse_header(rec, cp, ctx.source_file, ctx.offset)
        base["smfmnrvn"] = rec[ps + PS_SMFMNRVN : ps + PS_SMFMNRVN + 2].hex()
        for col, at in (("smfmnprn", PS_SMFMNPRN), ("smfmnspn", PS_SMFMNSPN), ("smfmnjbn", PS_SMFMNJBN),
                        ("smfmnuif", PS_SMFMNUIF), ("smfmnpdn", PS_SMFMNPDN)):
            base[col] = d.ebcdic(rec[ps + at : ps + at + 8], cp).strip() or None
        base["smfmnrst"] = d.smf_datetime(rec[ps + PS_SMFMNRST : ps + PS_SMFMNRST + 4],
                                          rec[ps + PS_SMFMNRSD : ps + PS_SMFMNRSD + 4])
        adjust = None
        if self.local_time:
            units = d.sint(rec[ps + PS_TIME_ADJUST : ps + PS_TIME_ADJUST + 8])
            adjust = timedelta(microseconds=units >> 12) if units else None

        dec = self._decoder(cp)
        for i, pos in enumerate(occurrences(rec, recs)):
            row = dict(base)
            row["transaction_index"] = i
            row.update(dec.decode(rec, pos, adjust))
            yield TABLE, row
