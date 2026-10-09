"""Output writers, created from config targets."""

from __future__ import annotations

from ..config import Config, Target
from .base import Writer
from .files import CsvWriter, ExcelWriter, JsonWriter
from .sql import SqlWriter


def create_writer(target: Target, config: Config) -> Writer:
    if target.type == "csv":
        return CsvWriter(target.options, config.resolve)
    if target.type == "json":
        return JsonWriter(target.options, config.resolve)
    if target.type == "excel":
        return ExcelWriter(target.options, config.resolve)
    return SqlWriter(target.type, target.options, config.resolve)


__all__ = ["Writer", "create_writer"]
