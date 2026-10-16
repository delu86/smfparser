from smfparser.records.type30 import VIEWS
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
    assert sql.count("WHERE smf30cpt IS NOT NULL") == 2
