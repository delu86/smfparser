import pytest

from smfparser.config import ConfigError, RecordFilter, from_dict, load


def test_filter_include_and_exclude():
    f = RecordFilter(include={30: [4, 5], 70: []}, exclude={70: [2]})
    assert f.keep(30, 4) and not f.keep(30, 1)
    assert f.keep(70, 1) and not f.keep(70, 2)
    assert not f.keep(14, None)


def test_filter_default_keeps_everything_not_excluded():
    f = RecordFilter(exclude={14: []})
    assert f.keep(30, 1) and not f.keep(14, None)


def test_from_dict_parses_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("SMF_PW", "secret")
    cfg = from_dict(
        {
            "input": {"files": "*.smf", "codepage": "cp500"},
            "filter": {"include": [30], "exclude": {30: [6]}},
            "records": {30: {"excp": True}},
            "output": {
                "chunk_rows": 10,
                "targets": [{"type": "mariadb", "database": "smf", "password": "${SMF_PW}"}],
            },
        },
        base_dir=tmp_path,
    )
    assert cfg.files == ["*.smf"] and cfg.codepage == "cp500"
    assert cfg.filter.include == {30: []} and cfg.filter.exclude == {30: [6]}
    assert cfg.record_options == {30: {"excp": True}}
    assert cfg.targets[0].options["password"] == "secret"
    assert cfg.resolve("out/x.csv") == tmp_path / "out/x.csv"


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"output": {"targets": [{"type": "parquet"}]}}, "unknown output type"),
        ({"output": {"targets": [{"type": "csv"}]}}, "needs 'dir'"),
        ({"input": {"codepage": "nope"}}, "unknown codepage"),
        ({"output": {"targets": [{"type": "sql", "url": "${UNSET_VAR_XYZ}"}]}}, "UNSET_VAR_XYZ"),
    ],
)
def test_invalid_config(raw, message):
    with pytest.raises(ConfigError, match=message):
        from_dict(raw)


def test_load_resolves_inputs_relative_to_config(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.smf").write_bytes(b"")
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text("input:\n  files: ['data/*.smf']\n")
    assert load(cfg_file).input_paths() == [tmp_path / "data" / "a.smf"]


def test_missing_inputs_error(tmp_path):
    with pytest.raises(ConfigError, match="no input files"):
        from_dict({"input": {"files": ["missing/*"]}}, base_dir=tmp_path).input_paths()
