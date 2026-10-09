"""Read SMF records from a binary dump.

Supports the two layouts produced by binary transfers of an SMF dataset (RECFM=VBS):

* blocked: every block starts with a 4-byte BDW, followed by RDW-prefixed segments;
* unblocked: RDW-prefixed segments back to back (BDWs stripped by the transfer).

Spanned records (segment codes 1=first, 3=middle, 2=last) are reassembled. Each yielded
record starts with a rebuilt 4-byte RDW, so field offsets match IBM's documented offsets.
"""

from __future__ import annotations

import logging
import mmap
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SEG_COMPLETE, SEG_FIRST, SEG_LAST, SEG_MIDDLE = 0, 1, 2, 3


@dataclass
class ReaderStats:
    segments: int = 0
    records: int = 0
    orphan_segments: int = 0
    truncated: int = 0


def _rdw(buf, pos: int) -> tuple[int, int] | None:
    """Return (length, segment code) of a plausible RDW at pos, else None."""
    if pos + 4 > len(buf):
        return None
    length = (buf[pos] << 8) | buf[pos + 1]
    seg = buf[pos + 2]
    if length < 4 or buf[pos + 3] != 0 or seg > 3:
        return None
    return length, seg


def _bdw_length(buf, pos: int) -> int:
    if buf[pos] & 0x80:  # extended (large block) BDW: 31-bit length
        return int.from_bytes(buf[pos : pos + 4], "big") & 0x7FFFFFFF
    return (buf[pos] << 8) | buf[pos + 1]


def detect_blocked(buf, probe_blocks: int = 3) -> bool:
    """True if the data starts with BDW blocks whose segments exactly fill each block."""
    pos = 0
    for _ in range(probe_blocks):
        if pos >= len(buf):
            return pos > 0
        if pos + 8 > len(buf) or (not buf[pos] & 0x80 and (buf[pos + 2] or buf[pos + 3])):
            return False
        end = pos + _bdw_length(buf, pos)
        if end < pos + 8:
            return False
        if end > len(buf):  # truncated file: blocked if earlier blocks were consistent
            return pos > 0
        p = pos + 4
        while p < end:
            rdw = _rdw(buf, p)
            if rdw is None:
                return False
            p += rdw[0]
        if p != end:
            return False
        pos = end
    return True


def _segments(buf, blocked: bool, stats: ReaderStats) -> Iterator[tuple[int, int, int]]:
    """Yield (offset, length, segment code) for every RDW segment in the file."""
    pos, size = 0, len(buf)
    if blocked:
        while pos + 4 <= size:
            end = min(pos + _bdw_length(buf, pos), size)
            if end <= pos + 4:
                log.warning("invalid BDW at offset %d, stopping", pos)
                stats.truncated += 1
                return
            p = pos + 4
            while p < end:
                rdw = _rdw(buf, p)
                if rdw is None or p + rdw[0] > end:
                    log.warning("invalid RDW at offset %d, skipping rest of block", p)
                    stats.truncated += 1
                    break
                yield p, rdw[0], rdw[1]
                p += rdw[0]
            pos = end
    else:
        while pos + 4 <= size:
            rdw = _rdw(buf, pos)
            if rdw is None or pos + rdw[0] > size:
                log.warning("invalid RDW at offset %d, stopping", pos)
                stats.truncated += 1
                return
            yield pos, rdw[0], rdw[1]
            pos += rdw[0]


def iter_records(buf, stats: ReaderStats | None = None) -> Iterator[tuple[bytes, int]]:
    """Yield (record, file offset of its first segment) from an in-memory SMF dump."""
    stats = stats if stats is not None else ReaderStats()
    blocked = detect_blocked(buf)
    parts: list[bytes] | None = None
    start = 0
    for off, length, seg in _segments(buf, blocked, stats):
        stats.segments += 1
        data = buf[off + 4 : off + length]
        if seg == SEG_COMPLETE:
            if parts is not None:
                stats.orphan_segments += 1
                parts = None
            yield _with_rdw(data), off
            stats.records += 1
        elif seg == SEG_FIRST:
            if parts is not None:
                log.warning("spanned record at offset %d never completed", start)
                stats.orphan_segments += 1
            parts, start = [data], off
        elif parts is None:
            log.warning("orphan spanned segment at offset %d", off)
            stats.orphan_segments += 1
        else:
            parts.append(data)
            if seg == SEG_LAST:
                yield _with_rdw(b"".join(parts)), start
                stats.records += 1
                parts = None
    if parts is not None:
        log.warning("file ends inside spanned record starting at offset %d", start)
        stats.orphan_segments += 1


def _with_rdw(data: bytes) -> bytes:
    length = min(len(data) + 4, 0xFFFF)
    return length.to_bytes(2, "big") + b"\x00\x00" + bytes(data)


def read_records(path: str | Path, stats: ReaderStats | None = None) -> Iterator[tuple[bytes, int]]:
    """Yield (record, file offset) for every SMF record in the file at path."""
    with open(path, "rb") as f:
        if f.seek(0, 2) == 0:
            return
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            yield from iter_records(mm, stats)
