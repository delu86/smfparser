import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa
from smfbuild import block, header, record_body, type30_record, with_rdw

from smfparser.cli import main
from smfparser.config import from_dict
from smfparser.pipeline import Pipeline

SAMPLE = Path(__file__).resolve().parent.parent / "smf_files" / "xcsmfp02.smfaltro.d261009.t103000"


@pytest.fixture
def smf_file(tmp_path):
    """Blocked dump with type 30 subtypes 1/4/5, a spanned type 30 and an unrelated type 26."""
    other = with_rdw(header(26, None, 0, date(2026, 10, 9)))
    big = record_body(type30_record(subtype=4, jobname="BIGJOB", excp=[(f"DD{i}", i) for i in range(50)]))
    data = block(
        type30_record(subtype=1),
        other,
        type30_record(subtype=4, excp=[("SYSUT1", 5)]),
        with_rdw(big[:600], seg=1),
    ) + block(with_rdw(big[600:], seg=2), type30_record(subtype=5), type30_record(subtype=4, jobname="JOB2", ziip=200, ziip_nf=512))
    path = tmp_path / "dump.smf"
    path.write_bytes(data)
    return path


def make_config(tmp_path, **overrides):
    raw = {
        "input": {"files": ["dump.smf"]},
        "filter": {"include": {30: [4, 5]}},
        "records": {30: {"excp": True}},
        "output": {
            "chunk_rows": 2,  # force several chunks per table
            "targets": [
                {"type": "csv", "dir": "out/csv"},
                {"type": "json", "dir": "out/json"},
                {"type": "excel", "path": "out/smf.xlsx"},
                {"type": "sqlite", "path": "out/smf.db", "if_exists": "replace"},
            ],
        },
    }
    raw.update(overrides)
    return from_dict(raw, base_dir=tmp_path)


def test_end_to_end_outputs(tmp_path, smf_file):
    stats = Pipeline(make_config(tmp_path)).run()
    assert stats.rows == {"smf30_4": 3, "smf30_5": 1, "smf30_excp": 51}
    assert sum(stats.kept.values()) == 4 and not stats.failed

    out = tmp_path / "out"
    csv4 = pd.read_csv(out / "csv" / "smf30_4.csv")
    assert list(csv4["smf30jbn"]) == ["MYJOB", "BIGJOB", "JOB2"]
    assert not (out / "csv" / "smf30_1.csv").exists()

    lines = (out / "json" / "smf30_excp.jsonl").read_text().splitlines()
    assert len(lines) == 51 and json.loads(lines[1])["smf30ddn"] == "DD0"

    xl = pd.read_excel(out / "smf.xlsx", sheet_name=None)
    assert set(xl) == {"smf30_4", "smf30_5", "smf30_excp"} and len(xl["smf30_excp"]) == 51

    engine = sa.create_engine(f"sqlite:///{out / 'smf.db'}")
    db = pd.read_sql("select smf30jbn, smf30cpt, smf30sit from smf30_4", engine)
    assert list(db["smf30jbn"]) == ["MYJOB", "BIGJOB", "JOB2"]
    assert db["smf30cpt"].tolist() == [1.51, 1.51, 1.51]
    engine.dispose()

    # Second run with if_exists=replace must not duplicate rows, and recreates the views.
    Pipeline(make_config(tmp_path)).run()
    engine = sa.create_engine(f"sqlite:///{out / 'smf.db'}")
    assert pd.read_sql("select count(*) n from smf30_4", engine)["n"][0] == 3
    assert pd.read_sql("select count(*) n from steps", engine)["n"][0] == 3
    engine.dispose()


def test_views(tmp_path, smf_file):
    Pipeline(make_config(tmp_path)).run()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'out' / 'smf.db'}")
    steps = pd.read_sql("select * from steps", engine)
    assert list(steps.columns) == [
        "system", "jobname", "stepname", "jobnumber", "stepnumber", "start_time", "end_time",
        "elapsed_sec", "cp_cpu_sec", "ziip_cpu_sec", "potential_cp_cpu_sec",
        "diskio_blk", "diskio_time", "tapeio_blk", "tapeio_time",
    ]
    job2 = steps[steps["jobname"] == "JOB2"].iloc[0]
    assert (job2["system"], job2["stepname"], job2["jobnumber"], job2["stepnumber"]) == ("SYSA", "STEP1", "JOB00042", 1)
    assert job2["elapsed_sec"] == pytest.approx(1.0)  # 10:00:00.00 initiator select -> 10:00:01.00 record
    assert job2["cp_cpu_sec"] == pytest.approx(1.55)
    assert job2["ziip_cpu_sec"] == pytest.approx(2.0)
    assert job2["potential_cp_cpu_sec"] == pytest.approx(1.55 + 2.0 * 512 / 256)
    assert len(pd.read_sql("select * from jobs", engine)) == 1
    io = steps.set_index("jobname")[["diskio_blk", "diskio_time", "tapeio_blk", "tapeio_time"]]
    assert list(io.loc["MYJOB"]) == pytest.approx([5, 10 * 128e-6, 0, 0])  # EXCP entries are DASD
    assert io.loc["BIGJOB", "diskio_blk"] == sum(range(50))
    assert list(io.loc["JOB2"]) == [0, 0, 0, 0]  # no EXCP section
    # A continuation record (EXCP overflow) is left out of the views, but its device I/O is added
    # to the step it continues (same identification fields).
    with engine.begin() as conn:
        conn.execute(sa.text(
            "insert into smf30_4 (smf_sid, smf30jbn, smf30jnm, smf30rst, smf30stn, smf30sit, smf_datetime,"
            " continuation, diskio_blk, diskio_time, tapeio_blk, tapeio_time)"
            " select smf_sid, smf30jbn, smf30jnm, smf30rst, smf30stn, smf30sit, smf_datetime, 1, 7, 0.25, 3, 0.5"
            " from smf30_4 where smf30jbn = 'JOB2'"))
    steps = pd.read_sql("select * from steps", engine)
    assert len(steps) == 3
    assert list(steps.set_index("jobname").loc["JOB2", ["diskio_blk", "diskio_time", "tapeio_blk", "tapeio_time"]]) \
        == [7, 0.25, 3, 0.5]
    # Subtypes 2/3 were filtered out: their tables are created empty so the view still works.
    intervals = pd.read_sql("select * from intervals", engine)
    assert intervals.empty and intervals.columns[1] == "subtype"
    engine.dispose()


def test_views_disabled(tmp_path, smf_file):
    target = {"type": "sqlite", "path": "out/smf.db", "views": False}
    Pipeline(make_config(tmp_path, output={"targets": [target]})).run()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'out' / 'smf.db'}")
    assert sa.inspect(engine).get_view_names() == []
    engine.dispose()


def test_json_array_mode(tmp_path, smf_file):
    cfg = make_config(tmp_path, output={"targets": [{"type": "json", "dir": "out", "lines": False}]})
    Pipeline(cfg).run()
    rows = json.loads((tmp_path / "out" / "smf30_5.json").read_text())
    assert len(rows) == 1 and rows[0]["smf30jbn"] == "MYJOB"


def test_bad_record_counted_not_fatal(tmp_path):
    path = tmp_path / "dump.smf"
    path.write_bytes(block(type30_record(subtype=9), type30_record(subtype=4)))
    cfg = make_config(tmp_path, filter={}, output={"targets": [{"type": "csv", "dir": "out"}]})
    stats = Pipeline(cfg).run()
    assert stats.failed == {(30, 9): 1} and stats.rows["smf30_4"] == 1


def test_cli_run_and_stats(tmp_path, smf_file, capsys):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("input:\n  files: [dump.smf]\noutput:\n  targets:\n    - {type: csv, dir: out}\n")
    assert main(["run", "-c", str(cfg)]) == 0
    assert "smf30_4" in capsys.readouterr().out
    assert main(["stats", str(smf_file)]) == 0
    out = capsys.readouterr().out
    assert "6 records in 7 segments" in out


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample SMF dump not available")
def test_sample_dump_counts(tmp_path):
    cfg = from_dict({"input": {"files": [str(SAMPLE)]}, "output": {"targets": [{"type": "csv", "dir": "out"}]}},
                    base_dir=tmp_path)
    stats = Pipeline(cfg).run()
    assert stats.reader.orphan_segments == 0 and not stats.failed
    assert {t: n for t, n in stats.rows.items()} == {
        "smf30_1": 110, "smf30_2": 164, "smf30_3": 470, "smf30_4": 471, "smf30_5": 101, "smf30_6": 14,
        "smf14": 1376, "smf15": 371,
    }
