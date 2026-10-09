# smfparser

[![tests](https://github.com/delu86/smfparser/actions/workflows/tests.yml/badge.svg)](https://github.com/delu86/smfparser/actions/workflows/tests.yml)

A Python parser for IBM z/OS **SMF** (System Management Facility) binary dumps. It reads the raw
records, keeps the record types and subtypes you choose, decodes them with pandas, and writes
**CSV, JSON, Excel, SQLite, MariaDB** or any database SQLAlchemy supports.

Supported record types: **30** (common address space work: job, step and interval accounting, subtypes 1–6).

## Features

- Reads blocked (BDW) and unblocked (RDW-only) binary dumps, and reassembles spanned records.
- Decodes EBCDIC, packed-decimal dates, TOD clocks and CPU-time units into proper text,
  datetimes and seconds.
- Writes one flat table per subtype, with IBM field names as columns, plus an optional per-DD
  EXCP table.
- Uses a YAML config for filters, code page, output targets and database credentials (taken from
  environment variables).
- Streams the input and writes in chunks, so large dumps don't need to fit in memory.

## Quick start

```sh
mise install                                  # Python 3.11 (see mise.toml)
mise exec -- python -m venv .venv
.venv/bin/pip install -e ".[dev]"

.venv/bin/smfparser stats path/to/SMF.DUMP     # what's in the dump?
cp config.example.yaml my-config.yaml          # choose inputs, filters, outputs
.venv/bin/smfparser run -c my-config.yaml
```

Minimal config:

```yaml
input:
  files: ["smf_files/*"]
filter:
  include: {30: [4, 5]}          # step end and job end only
output:
  targets:
    - {type: csv, dir: out/csv}
    - {type: sqlite, path: out/smf.db}
```

## Documentation

- [User guide](docs/user-guide.md): commands, every config option, output tables, example queries
- [SMF input format](docs/smf-input-format.md): getting SMF data off z/OS and how records are laid out
- [SMF type 30 field reference](docs/smf30-fields.md): every output column with offset, units and meaning
- [Developer guide](docs/developer-guide.md): architecture, adding record types or output formats, tests

## Development

```sh
.venv/bin/pytest
```

The tests use synthetic records, so they need no real SMF data. Real dumps go in `smf_files/`,
which is git-ignored.
