"""SQL views over the parsed tables, created by the database writers at the end of a run.

A view selects the same (alias, expression) columns from each of its source tables and joins them
with UNION ALL. Expressions are plain SQL, except `Elapsed`, which is rendered per dialect.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Elapsed:
    """Seconds between two datetime columns."""

    start: str
    end: str


Expr = str | Elapsed


@dataclass(frozen=True)
class View:
    name: str
    sources: tuple[str, ...]  # tables, combined with UNION ALL
    columns: tuple[tuple[str, Expr], ...]  # (alias, expression), in view column order
    where: str | None = None  # row filter applied to every source table


def elapsed_sql(dialect: str, start: str, end: str) -> str | None:
    """SQL for the seconds between two datetimes, or None if the dialect isn't supported."""
    if dialect == "mysql":
        return f"TIMESTAMPDIFF(MICROSECOND, {start}, {end}) / 1000000.0"
    if dialect == "sqlite":
        return f"ROUND((julianday({end}) - julianday({start})) * 86400.0, 3)"
    if dialect == "postgresql":
        return f"EXTRACT(EPOCH FROM ({end} - {start}))"
    return None


def supports(dialect: str) -> bool:
    return elapsed_sql(dialect, "a", "b") is not None


def render(view: View, dialect: str, prefix: str = "") -> str:
    """The SELECT statement behind a view (without CREATE VIEW)."""
    cols = []
    for alias, expr in view.columns:
        if isinstance(expr, Elapsed):
            sql = elapsed_sql(dialect, expr.start, expr.end)
            if sql is None:
                raise ValueError(f"views are not supported on {dialect}")
            expr = sql
        cols.append(f"{expr} AS {alias}")
    select = ",\n       ".join(cols)
    where = f"\nWHERE {view.where}" if view.where else ""
    return "\nUNION ALL\n".join(f"SELECT {select}\nFROM {prefix}{src}{where}" for src in view.sources)
