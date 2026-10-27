import csv
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from smfbuild import type113_record
from test_type30 import epv_mismatches

from smfparser.reader import read_records
from smfparser.records.type113 import Type113Parser
from smfparser.registry import ParseContext, ParserOptions

CTX = ParseContext("test.smf", 99)


def parse(rec, parser=None, **options):
    return list((parser or Type113Parser(ParserOptions(options))).parse(rec, CTX))


@pytest.mark.parametrize("subtype", [1, 2])
def test_row(subtype):
    [(table, row)] = parse(type113_record(subtype=subtype))
    assert table == f"smf113_{subtype}"
    assert list(row) == list(Type113Parser().schemas()[table])
    p = f"smf113_{subtype}_"
    assert (row["smf_sid"], row["smf_ssi"], row["smf113pnm"], row["smf113jbn"]) == ("SYSA", "HIS", "HIS", "HIS")
    assert row["smf113rst"] == datetime(2026, 10, 8, 19, 3, 55, 140000)
    # TOD times are shifted from UTC to the record's local time (+2 h).
    assert row["smf113intervalstart"] == datetime(2026, 10, 9, 10, 50)
    assert row["smf113intervalend"] == datetime(2026, 10, 9, 11, 0)
    assert row[p + "ctm"] == datetime(2026, 10, 9, 11, 0, 0, 6359)
    assert row[p + "cts"] == datetime(2026, 10, 8, 19, 3, 55)
    assert (row[p + "cpuid"], row["cpu_type"], row["duration_sec"]) == (3, "zIIP", 600.0)
    assert (row[p + "machtype"], row[p + "machmodel"], row[p + "machseqcode"]) == ("8561", "T01", "0000000000033A28")
    assert [row[f"basic_{i}"] for i in range(6)] == [100, 50, 1, 2, 3, 4]
    assert (row["problem_32"], row["problem_33"], row["problem_34"]) == (40, 20, None)
    assert [row[f"crypto_{i}"] for i in range(64, 84)] == list(range(20))
    assert row["extended_128"] == row["extended_287"] == 7
    assert row["mtdiag_448"] is None


def test_subtype_fields():
    [(_, one)] = parse(type113_record(subtype=1))
    assert (one["smf113_1_cpuspeed"], one["smf113_1_ctrversion2"], one["smf113_1_coreid"]) == (5200, 6, 1)
    [(_, two)] = parse(type113_record(subtype=2))
    assert (two["smf113_2_cpsp"], two["smf113_2_ctrvn2"], two["smf113_2_cf"]) == (5200, 6, 0x4000)


def test_short_counters_and_mt_diagnostic_set():
    rec = type113_record(counters={6: [9, 8], 1: [1, 2, 3, 4, 5, 6]}, long_counters=False)
    [(_, row)] = parse(rec)
    assert (row["mtdiag_448"], row["mtdiag_449"], row["basic_5"]) == (9, 8, 6)
    assert row["crypto_64"] is None and row["extended_128"] is None


def test_counters_table(caplog):
    rec = type113_record(counters={1: [1, 2], 5: [11, 12], 4: list(range(170))})
    with caplog.at_level(logging.WARNING):
        out = parse(rec, counters=True)
    assert "170 extended counters, only the first 160" in caplog.text
    counters = [r for table, r in out if table == "smf113_1_counters"]
    assert len(counters) == 2 + 2 + 170
    assert all(list(r) == list(Type113Parser(ParserOptions({"counters": True})).schemas()["smf113_1_counters"])
               for r in counters)
    by_set = {(r["counter_set"], r["counter_index"]): r for r in counters}
    assert by_set[("basic", 1)]["counter_number"] == 1 and by_set[("basic", 1)]["counter_value"] == 2
    assert by_set[("zos", 0)]["counter_number"] is None and by_set[("zos", 0)]["counter_value"] == 11
    assert by_set[("extended", 169)]["counter_number"] == 297  # past the columns, still in this table
    assert (counters[0]["cpu_id"], counters[0]["cpu_type"]) == (3, "zIIP")


def test_utc_offset_reused_for_a_late_record():
    p = Type113Parser()
    parse(type113_record(), p)
    late = bytearray(type113_record(interval_end=datetime(2026, 10, 9, 8, 40)))  # written 20 minutes late
    late[6:10] = type113_record()[6:10]
    [(_, row)] = parse(bytes(late), p)
    assert row["smf113intervalend"] == datetime(2026, 10, 9, 10, 40)
    # Without a known offset the gap is floored to quarter hours.
    [(_, alone)] = parse(bytes(late))
    assert alone["smf113intervalend"] == datetime(2026, 10, 9, 10, 40) + timedelta(minutes=15)


def test_other_subtypes_rejected():
    rec = bytearray(type113_record())
    rec[22:24] = (3).to_bytes(2, "big")
    with pytest.raises(ValueError, match="subtype 3"):
        parse(bytes(rec))


ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "smf_files" / "xcsmfp02.smfaltro.d261026.t170005"
EPV_DIR = ROOT / "smf_files" / "epv_files"  # EPV's export of the same dump
EPV_SETS = {"Basic": "basic", "Problem": "problem", "Crypto": "crypto", "Extend": "extended"}


def epv_column(col: str, subtype: int, ours: pd.DataFrame) -> pd.Series | None:
    """Our column for EPV's column `col`, or None if we have no counterpart."""
    derived = {"DURTIME": ours.duration_sec, "SMFTIME": ours.smf_datetime, "SYSTEM": ours.smf_sid,
               f"SMF113_{subtype}_CpuProcClass": ours.cpu_type.replace("CP", "Standard CP")}
    if col in derived:
        return derived[col]
    prefix = f"SMF113_{subtype}_CR_"
    if col.startswith(prefix):
        kind, number = col[len(prefix):].split("_")
        return ours[f"{EPV_SETS[kind]}_{number}"]
    return ours.get(col.lower())


@pytest.mark.skipif(not (SAMPLE.exists() and EPV_DIR.exists()), reason="sample dump or EPV export not available")
@pytest.mark.parametrize("subtype", [1, 2])
def test_sample_type113_epv(subtype):
    """Every type 113 record of the sample dump, checked against EPV's EPV113_<subtype>_HDCap."""
    p = Type113Parser()
    rows = [row for rec, offset in read_records(SAMPLE) if rec[5] == 113
            for table, row in p.parse(rec, ParseContext(str(SAMPLE), offset)) if table == f"smf113_{subtype}"]
    ours = pd.DataFrame(rows)
    name = f"EPV113_{subtype}_HDCap"
    names = (EPV_DIR / f"{name}.HDR").read_text(encoding="latin1").splitlines()[0].split("\t")[1:]
    epv = pd.read_csv(EPV_DIR / f"{name}.TXT", sep="\t", header=None, names=names, dtype=str,
                      keep_default_na=False, quoting=csv.QUOTE_NONE, encoding="latin1")
    assert len(epv) == len(ours) == 11
    if subtype == 1:  # EPV writes the subtype 1 CPU ID in hex, the subtype 2 one in decimal
        epv["SMF113_1_CpuId"] = epv["SMF113_1_CpuId"].map(lambda v: str(int(v, 16)))
    checked, bad = 0, {}
    for col in names:
        o = epv_column(col, subtype, ours)
        if o is None:
            continue
        checked += 1
        if col == "DURTIME" and subtype == 2:
            assert (epv[col] == "").all()  # EPV leaves it blank for subtype 2
            continue
        if n := epv_mismatches(epv[col], o):
            bad[col] = n
    assert bad == {}
    assert checked == len(names) - 1  # all but DumpTime
