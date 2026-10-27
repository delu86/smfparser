from smfparser.records.type14 import Type14Parser, Type15Parser
from smfparser.records.type30 import VIEWS
from smfparser.records.type113 import Type113Parser
from smfparser.views import Elapsed, View, elapsed_sql, render, supports

VIEW = View("v", ("t1", "t2"), (("a", "col_a"), ("el", Elapsed("s", "e"))))


def test_render_union_and_prefix():
    sql = render(VIEW, "sqlite", "raw_")
    assert sql == (
        "SELECT col_a AS a,\n       ROUND((julianday(e) - julianday(s)) * 86400.0, 3) AS el\nFROM raw_t1"
        "\nUNION ALL\n"
        "SELECT col_a AS a,\n       ROUND((julianday(e) - julianday(s)) * 86400.0, 3) AS el\nFROM raw_t2"
    )


def test_elapsed_per_dialect():
    assert elapsed_sql("mysql", "s", "e") == "TIMESTAMPDIFF(MICROSECOND, s, e) / 1000000.0"
    assert "EPOCH" in elapsed_sql("postgresql", "s", "e")
    assert not supports("mssql")


def test_type30_views():
    names = {v.name: v.sources for v in VIEWS}
    assert names == {"steps": ("smf30_4",), "jobs": ("smf30_5",), "intervals": ("smf30_2", "smf30_3")}
    sql = render(VIEWS[2], "mysql")
    assert "TIMESTAMPDIFF(MICROSECOND, smf30ist, smf_datetime)" in sql
    # Continuation records (no processor section) are filtered out of both UNION branches.
    assert sql.count("WHERE NOT continuation") == 2


def test_datasets_view():
    [view] = Type14Parser().views()
    assert view.name == "datasets" and view.sources == ("smf14", "smf15")
    assert Type15Parser().views() == ()
    # Every column the view selects exists in both tables.
    columns = set(Type14Parser().schemas()["smf14"])
    assert {expr for _, expr in view.columns} <= columns


def test_type113_views():
    p = Type113Parser()
    assert [v.name for v in p.views()] == ["cpu_metrics", "cpu_type_metrics"]
    per_cpu, by_type = p.views()
    assert "GROUP BY" not in render(per_cpu, "mysql")
    assert render(by_type, "mysql").count("GROUP BY smf_sid, smf113intervalstart") == 1
    # Plain column expressions name columns of smf113_1.
    columns = set(p.schemas()["smf113_1"])
    plain = {expr for v in p.views() for _, expr in v.columns if expr.isidentifier()}
    assert plain <= columns
