"""Output writer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd


class Writer(ABC):
    """Receives DataFrame chunks per table; chunks of one table always share the same columns."""

    def __init__(self, options: dict[str, Any], resolve) -> None:
        self.options = options
        self._resolve = resolve  # maps a config-relative path to an absolute Path

    def path(self, key: str) -> Path:
        return self._resolve(str(self.options[key]))

    @abstractmethod
    def write(self, table: str, df: pd.DataFrame) -> None: ...

    def close(self) -> None:  # noqa: B027 - optional hook
        pass
