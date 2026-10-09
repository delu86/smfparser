"""Registry of record-type parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass
class ParseContext:
    source_file: str
    offset: int
    codepage: str = "cp037"


@dataclass
class ParserOptions:
    """Per-record-type options from the config (e.g. type30: {excp: true})."""

    values: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


class RecordParser(ABC):
    record_type: ClassVar[int]

    def __init__(self, options: ParserOptions | None = None) -> None:
        self.options = options or ParserOptions()

    @abstractmethod
    def schemas(self) -> dict[str, dict[str, str]]:
        """Every table this parser can emit: table name -> {column: pandas dtype}."""

    @abstractmethod
    def parse(self, rec: bytes, ctx: ParseContext) -> Iterator[tuple[str, dict[str, Any]]]:
        """Decode one record into (table name, row) pairs."""


_REGISTRY: dict[int, type[RecordParser]] = {}


def register(cls: type[RecordParser]) -> type[RecordParser]:
    _REGISTRY[cls.record_type] = cls
    return cls


def supported_types() -> dict[int, type[RecordParser]]:
    # Importing the record modules registers their parsers.
    from .records import type30  # noqa: F401

    return dict(_REGISTRY)
