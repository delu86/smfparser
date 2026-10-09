"""Command line interface: `smfparser run` and `smfparser stats`."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .config import ConfigError, load
from .pipeline import Pipeline, RunStats
from .reader import ReaderStats, read_records
from .records.header import record_subtype, record_type


def _fmt_key(key: tuple[int, int | None]) -> str:
    rtype, subtype = key
    return f"{rtype:>4} {'-' if subtype is None else subtype:>6}"


def cmd_run(args: argparse.Namespace) -> int:
    try:
        config = load(args.config)
        paths = [Path(p) for p in args.files] if args.files else config.input_paths()
    except (ConfigError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    logging.getLogger().setLevel(args.log_level or config.log_level)
    if not config.targets:
        print("error: no output targets configured", file=sys.stderr)
        return 2
    stats = Pipeline(config).run(paths)
    _print_run_summary(stats)
    return 1 if stats.failed else 0


def _print_run_summary(stats: RunStats) -> None:
    r = stats.reader
    print(f"segments {r.segments}  records {r.records}  orphan segments {r.orphan_segments}  "
          f"truncated {r.truncated}")
    print(f"records read {sum(stats.read.values())}, parsed {sum(stats.kept.values())}, "
          f"failed {sum(stats.failed.values())}, no parser {sum(stats.unsupported.values())}")
    if stats.failed:
        print("failed (type subtype count):")
        for key, n in sorted(stats.failed.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
            print(f"  {_fmt_key(key)} {n:>8}")
    print("rows written per table:")
    for table, n in sorted(stats.rows.items()):
        print(f"  {table:<20} {n:>8}")


def cmd_stats(args: argparse.Namespace) -> int:
    for path in args.files:
        stats, counts = ReaderStats(), Counter()
        for rec, _ in read_records(path, stats):
            counts[(record_type(rec), record_subtype(rec))] += 1
        print(f"{path}: {stats.records} records in {stats.segments} segments "
              f"(orphan {stats.orphan_segments}, truncated {stats.truncated})")
        print("  type subtype    count")
        for key, n in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
            print(f"  {_fmt_key(key)} {n:>8}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smfparser", description="Parse IBM SMF binary dumps.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="parse files and write the configured outputs")
    p_run.add_argument("-c", "--config", required=True, help="YAML config file")
    p_run.add_argument("files", nargs="*", help="input files (override input.files)")
    p_run.add_argument("--log-level", help="override logging.level (DEBUG, INFO, WARNING, ...)")
    p_run.set_defaults(func=cmd_run)

    p_stats = sub.add_parser("stats", help="count records by type and subtype")
    p_stats.add_argument("files", nargs="+")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
