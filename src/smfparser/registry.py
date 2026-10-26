"""Registry of record-type parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from .views import View


@dataclass
class ParseContext:
    source_file: str
    offset: int
    codepage: str = "cp037"


@dataclass
class ParserOptions:
    """Per-record-type options from the config (e.g. type30: {excp: true})."""

    values: dict[str, Any] = field(default_factory=dict)
    base_dir: Path | None = None  # relative paths in the options resolve against it

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def path(self, key: str) -> Path | None:
        value = self.values.get(key)
        if not value:
            return None
        p = Path(value).expanduser()
        return p if p.is_absolute() or self.base_dir is None else self.base_dir / p


class RecordParser(ABC):
    record_type: ClassVar[int]

    def __init__(self, options: ParserOptions | None = None) -> None:
        self.options = options or ParserOptions()

    @abstractmethod
    def schemas(self) -> dict[str, dict[str, str]]:
        """Every table this parser can emit: table name -> {column: pandas dtype}."""

    def views(self) -> tuple[View, ...]:
        """SQL views over this parser's tables, created by the database writers."""
        return ()

    @abstractmethod
    def parse(self, rec: bytes, ctx: ParseContext) -> Iterator[tuple[str, dict[str, Any]]]:
        """Decode one record into (table name, row) pairs."""


_REGISTRY: dict[int, type[RecordParser]] = {}


def register(cls: type[RecordParser]) -> type[RecordParser]:
    _REGISTRY[cls.record_type] = cls
    return cls


def supported_types() -> dict[int, type[RecordParser]]:
    # Importing the record modules registers their parsers.
    from .records import type14, type30, type110  # noqa: F401

    return dict(_REGISTRY)
