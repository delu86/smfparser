"""The standard SMF record header shared by all record types."""

from __future__ import annotations

from typing import Any

from .. import decoders as d

# SMFxxFLG bit: record uses the extended header with subsystem ID and subtype.
FLAG_SUBTYPES = 0x40

HEADER_SCHEMA: dict[str, str] = {
    "source_file": "string",
    "record_offset": "Int64",
    "smf_datetime": "datetime64[us]",
    "smf_type": "Int64",
    "smf_subtype": "Int64",
    "smf_sid": "string",
    "smf_ssi": "string",
    "smf_flag": "Int64",
}


def record_type(rec: bytes) -> int:
    return rec[5] if len(rec) > 5 else -1


def record_subtype(rec: bytes) -> int | None:
    """Subtype, or None if the record doesn't carry one."""
    if len(rec) < 24 or not rec[4] & FLAG_SUBTYPES:
        return None
    return d.uint(rec[22:24])


def parse_header(rec: bytes, codepage: str, source_file: str, offset: int) -> dict[str, Any]:
    has_sub = bool(rec[4] & FLAG_SUBTYPES) and len(rec) >= 24
    return {
        "source_file": source_file,
        "record_offset": offset,
        "smf_datetime": d.smf_datetime(rec[6:10], rec[10:14]),
        "smf_type": rec[5],
        "smf_subtype": d.uint(rec[22:24]) if has_sub else None,
        "smf_sid": d.ebcdic(rec[14:18], codepage),
        "smf_ssi": d.ebcdic(rec[18:22], codepage) if has_sub else None,
        "smf_flag": rec[4],
    }
