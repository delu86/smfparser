import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from smfbuild import block, cics_entry, cics_record, e, record_body, u, with_rdw

from smfparser.config import from_dict
from smfparser.pipeline import Pipeline
from smfparser.reader import read_records
from smfparser.records.type110 import CicsMonitoringParser, Dictionary
from smfparser.registry import ParseContext, ParserOptions

CTX = ParseContext("test.smf", 99)
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "smf_files" / "xcsmfp02.smfcics.d261026.t111500"
SAMPLE_DICT = ROOT / "smf_files" / "dictionary.bin"

ENTRIES = [
    cics_entry("DFHTASK", "C", "001", 4, 1, 0, "TRAN"),
    cics_entry("DFHCICS", "T", "005", 8, 2, 4, "START"),
    cics_entry("DFHCICS", "T", "006", 8, 3, 12, "STOP"),
    cics_entry("DFHCICS", "P", "031", 4, 4, 20, "TRANNUM"),
    cics_entry("DFHTASK", "C", "098", 8, 5, 24, "NETUOWSX"),
    cics_entry("DFHTASK", "A", "164", 8, 6, 32, "TRANFLAG"),
    cics_entry("DFHTERM", "A", "165", 4, 7, 0xFFFF, "TERMINFO"),  # excluded by the MCT
    cics_entry("DFHTASK", "S", "008", 12, 8, 40, "USRCPUT"),
    cics_entry("DFHFILE", "A", "036", 4, 9, 56, "FCGETCT"),  # 52..56 unused
    cics_entry("DFHTERM", "S", "009", 12, 10, 60, "TCIOWTT"),
]
CONNECTORS = [1, 2, 3, 4, 5, 6, 8, 9, 10]
RECORD_LENGTH = 72

START = 0xE37CBD144F1F2818  # 2026-10-26 10:10:02.794482 UTC
STOP = 0xE37CBD144FCD8382  # 2026-10-26 10:10:02.797272 UTC


def dictionary_record() -> bytes:
    return cics_record(1, b"".join(ENTRIES), 26, len(ENTRIES))


def transaction(tran: str = "TG@2", flag: int = 0x8080804001800000, cpu: int = 0x15E5B6, dispatches: int = 11,
                fcget: int = 2) -> bytes:
    data = bytearray(RECORD_LENGTH)
    data[0:4] = e(tran, 4)
    data[4:12] = u(START, 8)
    data[12:20] = u(STOP, 8)
    data[20:24] = bytes.fromhex("0072549C")
    data[24:32] = bytes.fromhex("7cbd144f20220001")
    data[32:40] = u(flag, 8)
    data[40:52] = u(cpu, 8) + b"\x00" + u(dispatches, 3)
    data[56:60] = u(fcget, 4)
    data[60:72] = u(1000 * 4096, 8) + b"\x00" + u(1, 3)  # 1 ms terminal I/O wait
    return bytes(data)


def performance_record(*transactions: bytes, connectors: list[int] = CONNECTORS, **kw) -> bytes:
    return cics_record(3, b"".join(transactions), RECORD_LENGTH, len(transactions), connectors=connectors, **kw)


@pytest.fixture
def dict_file(tmp_path):
    path = tmp_path / "dictionary.bin"
    path.write_bytes(dictionary_record())
    return path


def parser(dict_file, **options):
    return CicsMonitoringParser(ParserOptions({"dictionary": str(dict_file), **options}))


def test_dictionary_entries(dict_file):
    dic = Dictionary.load(dict_file)
    assert dic.applid == "CICSA001" and len(dic.entries) == 10
    assert [f.column for f in dic.fields] == [
        "tran_001", "start_005", "stop_006", "trannum_031", "netuowsx_098", "tranflag_164", "usrcput_008",
        "fcgetct_036", "tciowtt_009"]
    assert dic.connectors == b"".join(u(c, 2) for c in CONNECTORS)
    assert dic.record_length == RECORD_LENGTH


def test_spanned_dictionary_loads(tmp_path):
    body = record_body(dictionary_record())
    path = tmp_path / "dict.bin"
    path.write_bytes(block(with_rdw(body[:100], seg=1), with_rdw(body[100:200], seg=3)) + block(
        with_rdw(body[200:], seg=2)))
    assert Dictionary.load(path) == Dictionary.from_record(dictionary_record())


def test_transaction_rows(dict_file):
    p = parser(dict_file)
    rows = list(p.parse(performance_record(transaction(), transaction("CPIH", fcget=7)), CTX))
    assert [t for t, _ in rows] == ["smf110_1", "smf110_1"]
    row = rows[0][1]
    assert list(row) == list(p.schemas()["smf110_1"])
    assert (row["smf_type"], row["smf_subtype"], row["smf_ssi"]) == (110, 1, "CICS")
    assert (row["smfmnrvn"], row["smfmnprn"], row["smfmnspn"], row["smfmnjbn"], row["smfmnuif"], row["smfmnpdn"]) == (
        "0730", "CICSA001", "CICSA001", "CICSJOB", "CICSUSR", "SP7.2.5")
    assert row["smfmnrst"] == datetime(2026, 10, 26, 1, 0, 0)
    assert row["transaction_index"] == 0 and rows[1][1]["transaction_index"] == 1
    assert row["tran_001"] == "TG@2" and rows[1][1]["tran_001"] == "CPIH"
    # STCK in UTC, shifted by the product-section local time adjustment (1 hour)
    assert row["start_005"] == datetime(2026, 10, 26, 11, 10, 2, 794482)
    assert row["stop_006"] == datetime(2026, 10, 26, 11, 10, 2, 797272)
    assert row["elapsed"] == pytest.approx(0.00279, abs=1e-6)
    assert row["tciowtt_009"] == pytest.approx(0.001) and row["tciowtt_009_count"] == 1
    assert row["internal_response"] == pytest.approx(0.00179, abs=1e-6)
    assert row["trannum_031"] == 72549
    assert row["netuowsx_098"] == "7cbd144f20220001"
    assert row["tranflag_164"] == "8080804001800000"
    assert row["usrcput_008"] == pytest.approx(0.00035035693359375)
    assert row["usrcput_008_count"] == 11
    assert (row["fcgetct_036"], rows[1][1]["fcgetct_036"]) == (2, 7)
    assert "terminfo_165" not in row


def test_utc_times_when_local_time_disabled(dict_file):
    [(_, row)] = parser(dict_file, local_time=False).parse(performance_record(transaction()), CTX)
    assert row["start_005"] == datetime(2026, 10, 26, 10, 10, 2, 794482)


def test_blank_text_and_zero_binary_are_null(dict_file):
    tx = bytearray(transaction())
    tx[0:4] = b"\x00\x00\x00\x00"
    tx[24:32] = bytes(8)
    tx[4:12] = bytes(8)
    [(_, row)] = parser(dict_file).parse(performance_record(bytes(tx)), CTX)
    assert row["tran_001"] is None and row["netuowsx_098"] is None
    assert row["start_005"] is None and row["elapsed"] is None


def test_extra_hex_fields_option(dict_file):
    [(_, row)] = parser(dict_file, hex=["tran"]).parse(performance_record(transaction()), CTX)
    assert row["tran_001"] == "e3c77cf2"


def test_connector_mismatch_raises(dict_file):
    with pytest.raises(ValueError, match="connectors differ"):
        list(parser(dict_file).parse(performance_record(transaction(), connectors=[1, 2, 3]), CTX))


def test_other_classes_yield_nothing(dict_file):
    assert list(parser(dict_file).parse(dictionary_record(), CTX)) == []


def test_without_dictionary_nothing_is_emitted():
    p = CicsMonitoringParser()
    assert p.schemas() == {}
    assert list(p.parse(performance_record(transaction()), CTX)) == []


def test_pipeline_resolves_dictionary_relative_to_config(tmp_path, dict_file):
    dump = tmp_path / "cics.smf"
    dump.write_bytes(block(performance_record(transaction(), transaction())))
    cfg = from_dict({
        "input": {"files": ["cics.smf"]},
        "records": {110: {"dictionary": "dictionary.bin"}},
        "output": {"targets": [{"type": "csv", "dir": "out"}]},
    }, base_dir=tmp_path)
    stats = Pipeline(cfg).run()
    assert stats.rows["smf110_1"] == 2 and not stats.failed
    header = (tmp_path / "out" / "smf110_1.csv").read_text().splitlines()[0]
    assert "usrcput_008_count" in header


EPV_DIR = ROOT / "smf_files" / "epv_files" / "SMF.xcsmfp02.smfcics.d261026.t111500.261026_115439"

# EPV columns that are not a straight copy of one of ours (EPV name -> our column).
EPV_RENAMED = {
    "CPUTIME": "usrcput_008",
    "ELAPSED": "elapsed",
    "SMFTIME": "smf_datetime",
    "SYSTEM": "smf_sid",
    "SMFMNPRN": "smfmnprn",
    "SMFMNRVN": "smfmnrvn",
    # EPV writes the clock's count, not its time, in these TM columns.
    "WMQGETWT_396TM": "wmqgetwt_396_count",
    "TSIOWTT_011TM": "tsiowtt_011_count",
    "RMIMQM_006TM": "rmimqm_006_count",
}
# Not in this dictionary (EPV leaves them blank), or checked separately below.
EPV_SKIPPED = {"DumpTime", "CLIPADDR_244", "CLIPPORT_330", "J8CPUT_260TM", "J9CPUT_267TM", "OCLIPADR_368",
               "INTRESPDUR", "RSYSID_130"}  # INTRESPDUR is our internal_response


def epv_column(name: str) -> str:
    """EPV column -> ours: X_nnnTM is the clock time, X_nnnCN its count."""
    if name in EPV_RENAMED:
        return EPV_RENAMED[name]
    base = name.lower().removesuffix("tm").removesuffix("cn")
    return base + "_count" if name.endswith("CN") else base


def epv_text(value) -> str:
    # EPV blanks every non-ASCII character; user fields such as CDNUSER1 hold binary bytes that
    # decode to letters like 'ã' (x'46') in the EBCDIC code page.
    return "" if value is None else "".join(c if c.isascii() else " " for c in str(value)).strip()


def epv_mismatches(epv: pd.Series, ours: list) -> int:
    e = epv.str.strip().replace("", None)
    o = pd.Series(ours, index=epv.index, dtype=object)
    sample = next((v for v in ours if v is not None), None)
    if isinstance(sample, datetime):
        same = pd.to_datetime(e) == pd.to_datetime(o)
        return int((~same & ~(e.isna() & o.isna())).sum())
    if isinstance(sample, (int, float)):
        en, on = pd.to_numeric(e).fillna(0), pd.to_numeric(o).fillna(0)
        return int((~np.isclose(en, on, rtol=1e-6, atol=1e-9)).sum())
    return int((e.fillna("") != o.map(epv_text)).sum())


@pytest.mark.skipif(not (SAMPLE.exists() and SAMPLE_DICT.exists()), reason="sample CICS dump not available")
def test_sample_cics_dump():
    """Every transaction in the sample dump, checked against EPV's decoding of the same dump."""
    p = CicsMonitoringParser(ParserOptions({"dictionary": str(SAMPLE_DICT)}))
    rows = (row for rec, offset in read_records(SAMPLE) if rec[5] == 110
            for _, row in p.parse(rec, ParseContext(str(SAMPLE), offset)))
    if not EPV_DIR.exists():
        assert sum(1 for _ in rows) == 265_248
        return

    names = (EPV_DIR / "EPV110_1_TrxAcct.HDR").read_text(encoding="latin1").splitlines()[0].split("\t")[1:]
    compared = [n for n in names if n not in EPV_SKIPPED]
    ours_cols = {n: epv_column(n) for n in compared}
    bad = dict.fromkeys(compared + ["INTRESPDUR", "RSYSID_130"], 0)
    total = 0
    for chunk in pd.read_csv(EPV_DIR / "EPV110_1_TrxAcct.TXT", sep="\t", header=None, names=names, dtype=str,
                             keep_default_na=False, quoting=csv.QUOTE_NONE, encoding="latin1", chunksize=50_000):
        batch = [next(rows) for _ in range(len(chunk))]
        total += len(batch)
        for n in compared:
            bad[n] += epv_mismatches(chunk[n], [r[ours_cols[n]] for r in batch])
        bad["INTRESPDUR"] += epv_mismatches(chunk["INTRESPDUR"], [r["internal_response"] for r in batch])
        # EPV writes RSYSID as hex.
        rsysid = [(r["rsysid_130"] or "").encode("cp037").ljust(4, b"\0").hex() for r in batch]
        bad["RSYSID_130"] += epv_mismatches(chunk["RSYSID_130"], rsysid)
    assert next(rows, None) is None
    assert total == 265_248
    assert {n: k for n, k in bad.items() if k} == {}
