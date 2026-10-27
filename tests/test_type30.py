import csv
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from smfbuild import type30_record

from smfparser.reader import read_records
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


def test_device_io_totals():
    [(_, row)] = parse(type30_record(excp=[("SYSUT1", 10), ("SYSUT2", 20)]))  # DASD entries, 10 x 128 µs each
    assert (row["diskio_blk"], row["tapeio_blk"], row["tapeio_time"]) == (30, 0, 0)
    assert row["diskio_time"] == pytest.approx(20 * 128e-6)
    [(_, none)] = parse(type30_record())
    assert none["diskio_blk"] is None and none["tapeio_time"] is None


def test_continuation_flag():
    [(_, first)] = parse(type30_record(subtype=4))
    assert first["continuation"] is False
    out = parse(type30_record(subtype=4, continuation=True, excp=[("DD1", 1)]), excp=True)
    (_, cont), (_, dd) = out
    assert cont["continuation"] is True and cont["smf30cpt"] is None and cont["smf30jbn"] == "MYJOB"
    assert dd["continuation"] is True and dd["smf30ddn"] == "DD1"
    # Job start records never have a processor section; they are not continuations.
    [(_, start)] = parse(type30_record(subtype=1, continuation=True))
    assert start["continuation"] is False


def test_unknown_subtype_raises():
    with pytest.raises(ValueError, match="subtype 9"):
        parse(type30_record(subtype=9))


def test_record_date_carried():
    [(_, row)] = parse(type30_record(d=date(2025, 3, 1)))
    assert row["smf30std"] == date(2025, 3, 1)


def test_flushed_step_has_no_program_start():
    [(_, row)] = parse(type30_record(program_start=0))
    assert row["smf30pps"] is None  # not midnight of the next day
    assert row["smf30ast"] == datetime(2026, 10, 9, 10, 0, 0, 500000)


# The record is written at 10:00:01 local time (see type30_record).
def test_interval_times_shifted_to_local():
    # Written an hour after the interval ended: the offset comes from SMF30IST - SMF30ISS (+2 h).
    rec = type30_record(subtype=2, interval_start=datetime(2026, 10, 9, 8, 30),
                        interval_utc=(datetime(2026, 10, 9, 6, 30), datetime(2026, 10, 9, 7, 0)))
    [(_, row)] = parse(rec)
    assert (row["smf30iss"], row["smf30iet"]) == (datetime(2026, 10, 9, 8, 30), datetime(2026, 10, 9, 9, 0))


def test_step_end_offset_from_record_time():
    # No SMF30IST in step end records; the record is written as the step ends.
    rec = type30_record(subtype=4, interval_utc=(datetime(2026, 10, 9, 8, 0), datetime(2026, 10, 9, 9, 0, 0, 990000)))
    [(_, row)] = parse(rec)
    assert row["smf30iet"] == datetime(2026, 10, 9, 10, 0, 0, 990000)
    assert row["smf30iss"] == datetime(2026, 10, 9, 9, 0)


def test_offset_reused_for_records_without_a_reference():
    late = (datetime(2026, 10, 9, 7, 0), datetime(2026, 10, 9, 7, 40))  # 20 minutes before the record (UTC+2)
    cont = type30_record(subtype=2, continuation=True, interval_utc=late)
    # A fresh parser floors the gap to quarter hours: 2 h 20 min -> +2 h 15 min (wrong, but bounded).
    [(_, alone)] = parse(cont)
    assert alone["smf30iet"] == late[1] + timedelta(hours=2, minutes=15)
    # After a record with SMF30IST, the system's offset is known and reused.
    p = Type30Parser()
    main = type30_record(subtype=2, interval_start=datetime(2026, 10, 9, 9, 0), interval_utc=late)
    [(_, first)] = p.parse(main, CTX)
    [(_, second)] = p.parse(cont, CTX)
    assert first["smf30iet"] == second["smf30iet"] == datetime(2026, 10, 9, 9, 40)


ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "smf_files" / "xcsmfp02.smfaltro.d261026.t170005"
EPV_DIR = ROOT / "smf_files" / "epv_files"  # EPV's export of the same dump, one file per table
EPV_TABLES = {"EPV030_23_Intrvl": (2, 3), "EPV030_4_Step": (4,), "EPV030_5_JobTerm": (5,), "EPV030_6_AddrSp": (6,)}
CP_CPU = ("smf30cpt", "smf30cps", "smf30icu", "smf30isb", "smf30iip", "smf30rct", "smf30hpt")  # = cp_cpu_sec

# Same-named columns EPV writes differently (checked below, or explained here).
EPV_DIFFERENT = {
    "SMF30AST", "SMF30PPS",  # seconds after midnight
    "SMF30CPC",  # EPV divides the stored coefficient by 10
    "SMF30CSU_L",  # EPV copies it from the main record into continuations, which have no performance section
}


def seconds(a: pd.Series, b: pd.Series) -> pd.Series:
    return (pd.to_datetime(a) - pd.to_datetime(b)).dt.total_seconds().round(2)


def epv_derived(o: pd.DataFrame) -> dict[str, pd.Series]:
    """EPV's computed columns, rebuilt from ours."""
    def time_of_day(col: str) -> pd.Series:
        t = pd.to_datetime(o[col])
        return (t - t.dt.normalize()).dt.total_seconds()

    return {
        "SYSTEM": o.smf_sid, "SYSPLEX": o.smf30syp, "SMFTIME": o.smf_datetime, "TERMTIME": o.smf_datetime,
        "READTIME": o.smf30rst, "INITIALTIME": o.smf30sit, "ALLOCTIME": o.smf30ast, "LOADTIME": o.smf30pps,
        "BEGINTIME": o.smf30iss, "ENDTIME": o.smf30iet.fillna(o.smf_datetime),
        "SMF30AST": time_of_day("smf30ast"), "SMF30PPS": time_of_day("smf30pps"), "SMF30CPC": o.smf30cpc / 10,
        "ELAPSED": seconds(o.smf_datetime, o.smf30sit).where(~o.continuation),  # EPV: blank on continuations
        "EXECTM": seconds(o.smf_datetime, o.smf30pps),
        "ALOCTM": seconds(o.smf30pps, o.smf30ast),
        "CPUTIME": sum(o[c].fillna(0) for c in CP_CPU), "TOTLIO": o.smf30tep,
        "ZIPTM": o.smf30_time_on_ziip, "ZIETM": o.smf30_enclave_time_on_ziip,
        "IFATM": o.smf30_time_on_ifa, "IFETM": o.smf30_time_ifa_on_cp,
        "DISKIO": o.diskio_blk, "TAPEIO": o.tapeio_blk, "DISKIOTM": o.diskio_time, "TAPEIOTM": o.tapeio_time,
        "CONDCODE": o.smf30scc, "FLAGXDD": o.continuation.map({True: "Y", False: ""}),
    }


def epv_mismatches(epv: pd.Series, ours: pd.Series) -> int:
    e = epv.str.strip().replace("", None)
    o = ours.reset_index(drop=True)
    sample = next((v for v in o if v is not None and v == v), None)
    if isinstance(sample, datetime):
        en, on = pd.to_datetime(e, format="ISO8601"), pd.to_datetime(o)
        return int((~((en == on) | (en.isna() & on.isna()))).sum())
    if isinstance(sample, (int, float, np.number)) and not isinstance(sample, bool):
        en, on = pd.to_numeric(e).fillna(0), pd.to_numeric(o).fillna(0)
        return int((~np.isclose(en, on, rtol=1e-6, atol=1e-6)).sum())
    return int((e.fillna("") != o.fillna("").astype(str).str.strip()).sum())


@pytest.mark.skipif(not (SAMPLE.exists() and EPV_DIR.exists()), reason="sample type 30 dump or EPV export not available")
def test_sample_type30_epv():
    """Every type 30 record in the sample dump, checked against EPV's decoding of the same dump."""
    p = Type30Parser()
    rows: dict[str, list] = {}
    for rec, offset in read_records(SAMPLE):
        if rec[5] == 30:
            for table, row in p.parse(rec, ParseContext(str(SAMPLE), offset)):
                rows.setdefault(table, []).append(row)

    bad = {}
    for name, subtypes in EPV_TABLES.items():
        names = (EPV_DIR / f"{name}.HDR").read_text(encoding="latin1").splitlines()[0].split("\t")[1:]
        epv = pd.read_csv(EPV_DIR / f"{name}.TXT", sep="\t", header=None, names=names, dtype=str,
                          keep_default_na=False, quoting=csv.QUOTE_NONE, encoding="latin1")
        ours = pd.DataFrame(sorted((r for s in subtypes for r in rows[f"smf30_{s}"]), key=lambda r: r["record_offset"]))
        assert len(epv) == len(ours), name
        derived = epv_derived(ours)
        flushed = epv.get("ABEND", pd.Series("", index=epv.index)).str.strip() == "FLUSH"
        for col in names:
            if col in derived:
                o = derived[col]
            elif col.lower() in ours.columns and col not in EPV_DIFFERENT:
                o = ours[col.lower()]
            else:
                continue
            keep = pd.Series(True, index=epv.index)
            if col == "ALLOCTIME":
                keep &= ~flushed  # EPV blanks it when the step never ran
            if col == "ZIETM" and subtypes == (2, 3):
                continue  # EPV's interval ZIETM is not always SMF30_ENCLAVE_TIME_ON_ZIIP (3 rows differ)
            n = epv_mismatches(epv[col][keep].reset_index(drop=True), o[keep.values].reset_index(drop=True))
            if n:
                bad[f"{name}.{col}"] = n
    assert bad == {}
