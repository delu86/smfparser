from datetime import date, datetime

import pytest
from smfbuild import e, ext_section, type14_record, u

from smfparser.records.type14 import Type14Parser, Type15Parser, disp, dsorg, recfm
from smfparser.registry import ParseContext, ParserOptions

CTX = ParseContext("test.smf", 99)


def parse(rec, cls=Type14Parser, **options):
    return list(cls(ParserOptions(options)).parse(rec, CTX))


def test_dasd_row():
    [(table, row)] = parse(type14_record())
    assert table == "smf14"
    assert (row["smf_type"], row["smf_subtype"], row["smf_sid"]) == (14, None, "SYSA")
    assert row["smf_datetime"] == datetime(2026, 10, 9, 10, 0, 1)
    assert (row["smf14jbn"], row["smf14tioe5"], row["jfcbdsnm"]) == ("MYJOB", "SYSUT1", "USER.TEST.DATA")
    assert row["smf14rst"] == datetime(2026, 10, 8, 23, 59, 59, 900000)
    assert row["smf14opd"] == date(2026, 10, 9) and row["smf14ope"] == datetime(2026, 10, 9, 10, 0, 0)
    assert row["jfcbcrdt"] == date(2026, 10, 9) and row["jfcbxpdt"] is None
    assert (row["jfclrecl"], row["jfcblksi"], row["jfcbnvol"], row["jfcbvol1"]) == (80, 27920, 1, "VOL001")
    assert (row["smf14sdc"], row["smf14nuc"], row["smf14suc"]) == (28, 1, 24)
    assert (row["smf14ntu"], row["smf14ntr"]) == (0x00050100, 3)
    assert row["smf14dcbbl"] is None and row["smf14dssno"] is None  # tape-only fields
    assert (row["dsorg"], row["recfm"], row["disp"]) == ("PS", "FB", "SHR")
    assert (row["excp_total"], row["nta_total"], row["volsers"]) == (12, 150, "VOL001")
    assert (row["smf14mcn"], row["smf14dcn"], row["smf14scn"]) == ("MCSTD", "DCSTD", "SCSTD")
    assert (row["smf14spn"], row["smf14pgn"], row["smf14jobid"], row["smf14plxid"]) == (
        "STEP1", "IEBGENER", "JOB00042", "PLEX1")
    assert row["smf14ioreq"] is None  # no Hiperbatch section
    assert row["smf14drd"] is None and row["smf14cmptype"] is None  # sections not present


def test_tape_row():
    rec = type14_record(dasd=False, volumes=[("T00001", 40, 1), ("T00002", 2, 1)])
    [(_, row)] = parse(rec)
    assert (row["smf14dcbbl"], row["smf14dssno"]) == (777, "VOL001")
    assert row["smf14ntu"] is None and row["nta_total"] is None
    assert (row["excp_total"], row["volsers"]) == (42, "T00001,T00002")


def test_type15_uses_same_layout():
    [(table, row)] = parse(type14_record(rtype=15), Type15Parser)
    assert table == "smf15" and row["smf_type"] == 15 and row["disp"] == "NEW"
    assert list(row) == list(Type15Parser().schemas()["smf15"])
    assert Type15Parser().schemas()["smf15"] == Type14Parser().schemas()["smf14"]


@pytest.mark.parametrize("dasd", [True, False])
def test_columns_match_schema(dasd):
    [(table, row)] = parse(type14_record(dasd=dasd, hiperbatch=True))
    assert list(row) == list(Type14Parser().schemas()[table])


def test_hiperbatch_and_extended_sections():
    ext = [
        ext_section(1, bytes([0x40, 0]) + u(100, 8) + u(400, 8) + u(1000, 8) + u(4000, 8) + u(56632, 4)
                    + u(36, 2) + bytes(36) + bytes([3])),
        ext_section(5, u(0xE000, 2) + u(27920, 8) + bytes([0, 0, 1]) + e("ALIAS.NAME", 44) + bytes(9)),
        ext_section(6, b"".join(u(n, 4) for n in (15, 11, 1, 0, 1, 0, 1, 0))),
        ext_section(8, bytes([0xC0, 0x20, 0, 0, 0x80, 0x04]) + bytes(18)),
        ext_section(99, b"unknown"),  # skipped
    ]
    [(_, row)] = parse(type14_record(hiperbatch=True, extended=ext))
    assert (row["smf14ioreq"], row["smf14chits"], row["smf14cios"]) == (10, 7, 2)
    assert (row["smf14cdl"], row["smf14udl"], row["smf14cis"], row["smf14cmptype"]) == (100, 400, 56632, 3)
    assert (row["smf14lbs"], row["smf14dsver"], row["smf14ali"]) == (27920, 1, "ALIAS.NAME")
    assert (row["smf14drd"], row["smf14drdh"], row["smf14mrd"]) == (15, 11, 1)
    assert (row["smf14rfg0"], row["smf14rfg1"], row["smf14rasdata0"], row["smf14rasdata1"]) == (0xC0, 0x20, 0x80, 0x04)
    assert row["smf14spn"] is None  # no step section in this record


def test_ucb_rows_only_when_enabled():
    rec = type14_record(volumes=[("VOL001", 5, 15), ("VOL002", 7, 30)])
    assert [t for t, _ in parse(rec)] == ["smf14"]
    out = parse(rec, ucb=True)
    assert [t for t, _ in out] == ["smf14", "smf14_ucb", "smf14_ucb"]
    ucbs = [r for t, r in out if t == "smf14_ucb"]
    assert [(r["ucb_index"], r["smf14srtev"], r["smf14excp"], r["smf14nta"]) for r in ucbs] == [
        (0, "VOL001", 5, 15), (1, "VOL002", 7, 30)]
    assert ucbs[0]["smf14ucbdv"] == 0x1234 and ucbs[0]["smf14srtef"] is None
    assert ucbs[1]["jfcbdsnm"] == "USER.TEST.DATA" and ucbs[1]["record_offset"] == 99
    assert list(ucbs[0]) == list(Type14Parser(ParserOptions({"ucb": True})).schemas()["smf14_ucb"])


def test_short_record_raises():
    with pytest.raises(ValueError, match="too short"):
        parse(type14_record()[:200])


def test_derived_codes():
    assert [dsorg(v) for v in (0x4000, 0x0200, 0x2000, 0x4100, 0x0008, 0)] == ["PS", "PO", "DA", "PSU", "AM", None]
    assert [recfm(v) for v in (0x90, 0x50, 0x58, 0x54, 0xC0, 0x80, 0x92, 0)] == [
        "FB", "VB", "VBS", "VBA", "U", "F", "FBM", None]
    assert [disp(v) for v in (0xC0, 0x80, 0x40, 0x48, 0x00, None)] == ["NEW", "MOD", "OLD", "SHR", None, None]
