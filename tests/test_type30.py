from datetime import date, datetime

import pytest
from smfbuild import type30_record

from smfparser.registry import ParseContext, ParserOptions
from smfparser.records.type30 import Type30Parser

CTX = ParseContext("test.smf", 1234)


def parse(rec, **options):
    return list(Type30Parser(ParserOptions(options)).parse(rec, CTX))


def test_flat_row_for_subtype():
    [(table, row)] = parse(type30_record(subtype=4, accounting=["ACCT1", "DEPT"]))
    assert table == "smf30_4"
    assert row["source_file"] == "test.smf" and row["record_offset"] == 1234
    assert row["smf_datetime"] == datetime(2026, 10, 9, 10, 0, 1)
    assert (row["smf_type"], row["smf_subtype"], row["smf_sid"], row["smf_ssi"]) == (30, 4, "SYSA", "JES2")
    assert (row["smf30syn"], row["smf30osl"], row["smf30rvn"]) == ("SY1", "SP7.2.5", "05")
    assert (row["smf30jbn"], row["smf30pgm"], row["smf30stm"], row["smf30jnm"]) == ("MYJOB", "IEFBR14", "STEP1", "JOB00042")
    assert row["smf30cls"] == "A" and row["smf30stn"] == 1
    assert row["smf30sit"] == datetime(2026, 10, 9, 10, 0, 0)
    assert row["smf30ast"] == datetime(2026, 10, 9, 10, 0, 0, 500000)
    assert row["smf30rst"] == datetime(2026, 10, 8, 23, 59, 59, 900000)
    assert row["smf30ret"] == datetime(2026, 10, 9, 0, 0, 0, 100000)
    assert row["smf30usr"] == "PROGRAMMER"
    assert row["smf30cpt"] == 1.51 and row["smf30cps"] == 0.04
    assert row["smf30tfl"] == 0x8000
    assert row["smf30idt"] is None and row["smf30ist"] is None
    assert row["smf30_highest_task_cpu_program"] == "IEFBR14"
    assert (row["smf30srv"], row["smf30wlm"], row["smf30scn"]) == (48, "BATCH", "BTHIGH")
    assert row["smf30act"] == "ACCT1,DEPT"


def test_missing_sections_give_none():
    [(_, row)] = parse(type30_record())
    assert row["smf30tep"] is None  # I/O section absent
    assert row["smf30pgi"] is None  # storage section absent
    assert row["smf30pdm"] is None  # operator section absent
    assert row["smf30act"] is None


def test_short_section_fields_are_none():
    [(_, row)] = parse(type30_record(ident_length=150))
    assert row["smf30cl8"] == "A"  # ends at 148
    assert row["smf30iss"] is None  # 148..156 beyond the section
    assert row["smf30cor"] is None


def test_columns_match_schema():
    parser = Type30Parser()
    [(table, row)] = parse(type30_record(subtype=5))
    assert list(row) == list(parser.schemas()[table])


def test_excp_child_rows_only_when_enabled():
    rec = type30_record(excp=[("SYSUT1", 10), ("SYSUT2", 20)])
    assert [t for t, _ in parse(rec)] == ["smf30_4"]
    out = parse(rec, excp=True)
    assert [t for t, _ in out] == ["smf30_4", "smf30_excp", "smf30_excp"]
    excp = [r for t, r in out if t == "smf30_excp"]
    assert [(r["smf30ddn"], r["smf30blk"], r["excp_index"]) for r in excp] == [("SYSUT1", 10, 0), ("SYSUT2", 20, 1)]
    assert excp[0]["smf30jbn"] == "MYJOB" and excp[0]["record_offset"] == 1234
    assert list(excp[0]) == list(Type30Parser(ParserOptions({"excp": True})).schemas()["smf30_excp"])


def test_unknown_subtype_raises():
    with pytest.raises(ValueError, match="subtype 9"):
        parse(type30_record(subtype=9))


def test_record_date_carried():
    [(_, row)] = parse(type30_record(d=date(2025, 3, 1)))
    assert row["smf30std"] == date(2025, 3, 1)
