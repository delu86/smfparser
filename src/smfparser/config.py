"""YAML configuration loading and validation.

Relative paths in the config are resolved against the config file's directory.
``${VAR}`` in any string value is replaced with the environment variable VAR.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .decoders import DEFAULT_CODEPAGE

TARGET_TYPES = ("csv", "json", "excel", "sqlite", "mariadb", "sql")
_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ConfigError(ValueError):
    pass


@dataclass
class RecordFilter:
    """Type -> subtypes to keep/drop. An empty subtype list means every subtype."""

    include: dict[int, list[int]] | None = None
    exclude: dict[int, list[int]] = field(default_factory=dict)

    def keep(self, rtype: int, subtype: int | None) -> bool:
        if self.include is not None:
            subs = self.include.get(rtype)
            if subs is None or (subs and subtype not in subs):
                return False
        subs = self.exclude.get(rtype)
        if subs is not None and (not subs or subtype in subs):
            return False
        return True


@dataclass
class Target:
    type: str
    options: dict[str, Any]


@dataclass
class Config:
    files: list[str]
    codepage: str = DEFAULT_CODEPAGE
    filter: RecordFilter = field(default_factory=RecordFilter)
    chunk_rows: int = 50_000
    targets: list[Target] = field(default_factory=list)
    record_options: dict[int, dict[str, Any]] = field(default_factory=dict)
    log_level: str = "INFO"
    base_dir: Path = field(default_factory=Path.cwd)

    def resolve(self, path: str) -> Path:
        p = Path(path).expanduser()
        return p if p.is_absolute() else self.base_dir / p

    def input_paths(self) -> list[Path]:
        paths: list[Path] = []
        for pattern in self.files:
            resolved = self.resolve(pattern)
            matches = sorted(p for p in resolved.parent.glob(resolved.name) if p.is_file())
            if not matches:
                raise ConfigError(f"no input files match {pattern!r}")
            paths.extend(matches)
        return paths


def _substitute_env(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in os.environ:
                raise ConfigError(f"environment variable {name} is not set")
            return os.environ[name]
        return _ENV.sub(repl, value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def _type_map(raw: Any, where: str) -> dict[int, list[int]]:
    if raw is None:
        return {}
    if isinstance(raw, list):  # shorthand: [30, 70] keeps every subtype
        raw = {t: [] for t in raw}
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a mapping of type -> [subtypes]")
    out: dict[int, list[int]] = {}
    for rtype, subs in raw.items():
        try:
            out[int(rtype)] = [int(s) for s in (subs or [])]
        except (TypeError, ValueError) as e:
            raise ConfigError(f"{where}: invalid entry {rtype!r}: {subs!r}") from e
    return out


def _target(raw: Any) -> Target:
    if not isinstance(raw, dict) or "type" not in raw:
        raise ConfigError(f"output target needs a 'type': {raw!r}")
    ttype = str(raw["type"]).lower()
    if ttype not in TARGET_TYPES:
        raise ConfigError(f"unknown output type {ttype!r}; expected one of {', '.join(TARGET_TYPES)}")
    options = {k: v for k, v in raw.items() if k != "type"}
    required = {"csv": "dir", "json": "dir", "excel": "path", "sqlite": "path", "mariadb": "database", "sql": "url"}
    if required[ttype] not in options:
        raise ConfigError(f"{ttype} output needs '{required[ttype]}'")
    return Target(ttype, options)


def from_dict(raw: dict[str, Any], base_dir: Path | None = None) -> Config:
    raw = _substitute_env(raw or {})
    inp = raw.get("input") or {}
    files = inp.get("files") or []
    if isinstance(files, str):
        files = [files]
    flt = raw.get("filter") or {}
    out = raw.get("output") or {}
    records = raw.get("records") or {}
    cfg = Config(
        files=list(files),
        codepage=inp.get("codepage", DEFAULT_CODEPAGE),
        filter=RecordFilter(
            include=_type_map(flt["include"], "filter.include") if flt.get("include") else None,
            exclude=_type_map(flt.get("exclude"), "filter.exclude"),
        ),
        chunk_rows=int(out.get("chunk_rows", 50_000)),
        targets=[_target(t) for t in out.get("targets") or []],
        record_options={int(str(k).removeprefix("type")): v or {} for k, v in records.items()},
        log_level=str((raw.get("logging") or {}).get("level", "INFO")).upper(),
        base_dir=base_dir or Path.cwd(),
    )
    try:
        "".encode(cfg.codepage)
    except LookupError as e:
        raise ConfigError(f"unknown codepage {cfg.codepage!r}") from e
    if cfg.chunk_rows <= 0:
        raise ConfigError("output.chunk_rows must be positive")
    return cfg


def load(path: str | Path) -> Config:
    path = Path(path)
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is not None and not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return from_dict(raw or {}, base_dir=path.resolve().parent)
