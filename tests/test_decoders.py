from datetime import date, datetime

import pytest

from smfparser import decoders as d


def test_ebcdic_strips_blanks_and_nulls():
    assert d.ebcdic(bytes.fromhex("c1c2c34040")) == "ABC"
    assert d.ebcdic(b"\x00" * 8) == ""


@pytest.mark.parametrize(
    "hexstr, expected",
    [("123C", 123), ("123D", -123), ("0000000F", 0), ("0126282F", 126282), ("12", None), ("1A3C", None)],
)
def test_packed(hexstr, expected):
    assert d.packed(bytes.fromhex(hexstr)) == expected


def test_smf_date():
    assert d.smf_date(bytes.fromhex("0126282F")) == date(2026, 10, 9)
    assert d.smf_date(bytes.fromhex("0099001F")) == date(1999, 1, 1)
    assert d.smf_date(bytes.fromhex("0000000F")) is None
    assert d.smf_date(bytes.fromhex("0126400F")) is None  # day 400


def test_smf_datetime():
    assert d.smf_datetime(bytes.fromhex("00393919"), bytes.fromhex("0126282F")) == datetime(2026, 10, 9, 10, 25, 1, 690000)


def test_stck():
    # 2026-10-09 TOD value seen in sample data, decoded to microsecond precision
    ts = d.stck(bytes.fromhex("e36745e647065c41"))
    assert ts.date() == date(2026, 10, 9)
    assert d.stck(b"\x00" * 8) is None
    one_second = (1_000_000 << 12).to_bytes(8, "big")
    assert d.stck(one_second) == datetime(1900, 1, 1, 0, 0, 1)


def test_units():
    assert d.hundredths(b"\x00\x00\x00\x97") == 1.51
    assert d.units_128us(b"\x00\x00\x00\x07") == pytest.approx(0.000896)
