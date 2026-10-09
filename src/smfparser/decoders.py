"""Decoders for the primitive data formats found in SMF records.

All multi-byte binary values on z/OS are big-endian. Text is EBCDIC.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

DEFAULT_CODEPAGE = "cp037"

# z/OS TOD clock epoch; bit 51 of the 64-bit TOD value ticks once per microsecond.
TOD_EPOCH = datetime(1900, 1, 1)


def ebcdic(b: bytes, codepage: str = DEFAULT_CODEPAGE) -> str:
    """EBCDIC text with trailing blanks and binary zeros removed."""
    return b.decode(codepage, errors="replace").rstrip(" \x00")


def uint(b: bytes) -> int:
    return int.from_bytes(b, "big", signed=False)


def sint(b: bytes) -> int:
    return int.from_bytes(b, "big", signed=True)


def packed(b: bytes) -> int | None:
    """Packed decimal (BCD with a trailing sign nibble). None if malformed."""
    digits = 0
    for byte in b[:-1]:
        hi, lo = byte >> 4, byte & 0x0F
        if hi > 9 or lo > 9:
            return None
        digits = digits * 100 + hi * 10 + lo
    last = b[-1]
    hi, sign = last >> 4, last & 0x0F
    if hi > 9 or sign < 0x0A:
        return None
    digits = digits * 10 + hi
    return -digits if sign in (0x0B, 0x0D) else digits


def smf_date(b: bytes) -> date | None:
    """SMF date in packed 0cyydddF form (c=0 -> 19xx, c=1 -> 20xx). None for zero/invalid."""
    value = packed(b)
    if not value:
        return None
    century, rest = divmod(value, 100000)
    year, day = divmod(rest, 1000)
    if day < 1 or day > 366:
        return None
    try:
        return date(1900 + century * 100 + year, 1, 1) + timedelta(days=day - 1)
    except ValueError:
        return None


def hundredths(b: bytes) -> float:
    """Binary count of hundredths of a second, as seconds."""
    return uint(b) / 100


def units_128us(b: bytes) -> float:
    """Binary count of 128-microsecond units, as seconds."""
    return uint(b) * 128e-6


def time_of_day(b: bytes) -> timedelta:
    """Hundredths of a second since midnight, as an offset from midnight."""
    return timedelta(milliseconds=uint(b) * 10)


def smf_datetime(time_b: bytes, date_b: bytes) -> datetime | None:
    """Combine an SMF time (hundredths since midnight) with an SMF packed date."""
    d = smf_date(date_b)
    if d is None:
        return None
    return datetime(d.year, d.month, d.day) + time_of_day(time_b)


def stck(b: bytes) -> datetime | None:
    """8-byte STCK TOD clock value as a naive datetime (UTC unless the field says otherwise)."""
    value = uint(b[:8])
    if value == 0:
        return None
    return TOD_EPOCH + timedelta(microseconds=value >> 12)
