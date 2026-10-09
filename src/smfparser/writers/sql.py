"""Database writer (SQLAlchemy): SQLite, MariaDB, or any SQLAlchemy URL."""

from __future__ import annotations

from typing import Any

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from .base import Writer

IF_EXISTS = ("append", "replace", "fail")

# Bind-parameter limits per statement (SQLite >= 3.32: 32766; MySQL/MariaDB: 65535).
MAX_PARAMS = {"sqlite": 32_766, "mysql": 65_535}
DEFAULT_MAX_PARAMS = 30_000


def database_url(ttype: str, options: dict[str, Any], resolve) -> sa.URL | str:
    if ttype == "sqlite":
        return f"sqlite:///{resolve(str(options['path']))}"
    if ttype == "mariadb":
        return sa.URL.create(
            "mysql+pymysql",
            username=options.get("user"),
            password=options.get("password"),
            host=options.get("host", "localhost"),
            port=int(options.get("port", 3306)),
            database=options["database"],
            query={"charset": "utf8mb4"},
        )
    return str(options["url"])


class SqlWriter(Writer):
    """Writes each table with DataFrame.to_sql.

    `if_exists` (append|replace|fail) applies to the first chunk of each table in a run;
    later chunks always append.
    """

    def __init__(self, ttype: str, options, resolve) -> None:
        super().__init__(options, resolve)
        if ttype == "sqlite":
            self.path("path").parent.mkdir(parents=True, exist_ok=True)
        self.if_exists = options.get("if_exists", "append")
        if self.if_exists not in IF_EXISTS:
            raise ValueError(f"if_exists must be one of {IF_EXISTS}")
        self.prefix = options.get("table_prefix", "")
        self.engine = sa.create_engine(database_url(ttype, options, resolve))
        self._started: set[str] = set()

    def write(self, table: str, df: pd.DataFrame) -> None:
        first = table not in self._started
        self._started.add(table)
        # Multi-row INSERTs bind rows x columns parameters; stay under the driver limit.
        max_params = MAX_PARAMS.get(self.engine.dialect.name, DEFAULT_MAX_PARAMS)
        batch = max(1, min(int(self.options.get("batch_rows", 1000)), max_params // max(1, len(df.columns))))
        df.to_sql(
            self.prefix + table,
            self.engine,
            if_exists=self.if_exists if first else "append",
            index=False,
            chunksize=batch,
            method="multi",
            dtype=self._column_types(df),
        )

    def _column_types(self, df: pd.DataFrame) -> dict[str, Any] | None:
        # MySQL/MariaDB DATETIME defaults to whole seconds; SMF times carry hundredths.
        if self.engine.dialect.name != "mysql":
            return None
        return {c: mysql.DATETIME(fsp=6) for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])}

    def close(self) -> None:
        self.engine.dispose()
