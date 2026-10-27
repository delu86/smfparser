import csv
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from smfbuild import type113_record
from test_type30 import epv_mismatches

from smfparser.reader import read_records
from smfparser.pipeline import to_frame
from smfparser.records.type113 import GENERATIONS, Type113Parser
from smfparser.registry import ParseContext, ParserOptions
from smfparser.views import render

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


def view_rows(rows: list[dict], name: str) -> list[dict]:
    """Rows of the named view, with `rows` loaded into an in-memory SQLite smf113_1."""
    p = Type113Parser()
    [view] = [v for v in p.views() if v.name == name]
    with sqlite3.connect(":memory:") as conn:
        to_frame(rows, p.schemas()["smf113_1"]).to_sql("smf113_1", conn, index=False)
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(render(view, "sqlite"))]


def z15_record(cpu: int, extended: dict[int, int]) -> dict:
    counters = {1: [1_000, 400, 6, 0, 4, 0], 2: [0, 100], 4: [extended.get(128 + i, 0) for i in range(160)]}
    [(_, row)] = parse(type113_record(cpu=cpu, counters=counters))
    return row


def test_cpu_metrics_view():
    # 10 L1 misses (basic_2 + basic_4): 5 from L2, 2 from L3, 1 each from L4 local, L4 remote and memory.
    row = z15_record(3, {133: 5, 144: 2, 147: 1, 153: 1, 145: 1})
    [m] = view_rows([row], "cpu_metrics")
    assert (m["system"], m["cpu_id"], m["cpu_type"], m["machine_type"], m["counter_version"]) == (
        "SYSA", 3, "zIIP", "8561", 6)
    assert m["cpi"] == pytest.approx(2.5) and m["prbstate"] == pytest.approx(25)
    assert m["l1mp"] == pytest.approx(2.5)
    assert (m["l2p"], m["l3p"], m["l4lp"], m["l4rp"], m["memp"]) == pytest.approx((50, 20, 10, 10, 10))
    assert m["rni"] == pytest.approx(2.9 * (0.45 * 20 + 1.5 * 10 + 3.2 * 10 + 6.5 * 10) / 100)
    assert m["lparcpu"] == pytest.approx(100 * 1000 / 5200e6 / 600)


def test_cpu_type_metrics_view_sums_counters():
    rows = [z15_record(3, {133: 10}), z15_record(4, {144: 10})]
    [m] = view_rows(rows, "cpu_type_metrics")
    assert (m["cpu_type"], m["cpus"], m["cycles"], m["instructions"]) == ("zIIP", 2, 2000, 800)
    assert (m["l2p"], m["l3p"], m["cpi"]) == pytest.approx((50, 50, 2.5))


def test_unknown_generation_has_no_sourcing():
    row = z15_record(3, {133: 10}) | {"smf113_1_ctrversion2": 3}  # zEC12
    [m] = view_rows([row], "cpu_metrics")
    assert m["cpi"] == pytest.approx(2.5) and m["l2p"] is None and m["rni"] is None


def test_generations_list_every_counter_once():
    for gen in GENERATIONS.values():
        counters = [n for group in gen[1:6] for n in group]
        assert len(counters) == len(set(counters)) and all(128 <= n <= 287 for n in counters)


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


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample dump not available")
def test_sample_l1_sourcing_adds_up():
    """On the sample's z15, the L1 misses sourced from L2, L3, L4 and memory add up to all of them."""
    p = Type113Parser()
    rows = [row for rec, offset in read_records(SAMPLE) if rec[5] == 113 and rec[23] == 1
            for _, row in p.parse(rec, ParseContext(str(SAMPLE), offset))]
    for name in ("cpu_metrics", "cpu_type_metrics"):
        for m in view_rows(rows, name):
            assert m["l2p"] + m["l3p"] + m["l4lp"] + m["l4rp"] + m["memp"] == pytest.approx(100, abs=0.05)
            assert 0.4 < m["rni"] < 2 and 1 < m["cpi"] < 3
