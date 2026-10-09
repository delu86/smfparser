# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python parser for IBM z/OS SMF binary dumps. Reads the raw dataset (RECFM=VBS, transferred in
binary with BDWs/RDWs kept), filters records by type/subtype per a YAML config, decodes them into
pandas DataFrames, and writes CSV, JSON, Excel, SQLite, MariaDB or any SQLAlchemy URL.
Currently supported: SMF type 30 (subtypes 1-6). Sample dumps live in `smf_files/` (git-ignored).
Documentation lives in `docs/` (user guide, input format, generated SMF30 field reference,
developer guide). After changing `records/type30.py`, regenerate the field reference with
`.venv/bin/python scripts/gen_smf30_fields_doc.py docs/smf30-fields.md`.

## Toolchain and commands

- Python 3.11, pinned via [mise](https://mise.jdx.dev/) in `mise.toml`. Project venv in `.venv`:
  - `mise exec -- python -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- Tests: `.venv/bin/pytest` (single test: `.venv/bin/pytest tests/test_type30.py::test_flat_row_for_subtype`).
  Tests build synthetic records (`tests/smfbuild.py`); `test_sample_dump_counts` runs only when the sample dump exists.
- Run: `.venv/bin/smfparser run -c config.example.yaml [files...]` (writes to `out/`, git-ignored).
- Inspect a dump: `.venv/bin/smfparser stats FILE...` (record counts by type/subtype, no decoding).

## Architecture (`src/smfparser/`)

- `reader.py` — detects blocked (BDW) vs RDW-only files, reassembles spanned segments, yields
  `(record, file_offset)` with a rebuilt RDW so offsets match IBM's documented offsets (which include the RDW).
- `decoders.py` — EBCDIC, big-endian ints, packed decimal, SMF `0cyydddF` dates, hundredths/128µs units, STCK TOD.
- `layout.py` — declarative `Field(name, offset, length, kind)` / `Section`; triplet (offset 4, length 2, count 2)
  helpers for self-defining sections. Field kinds map to a decoder and a pandas dtype. `kind="time"` fields are
  combined with a `date` field into a datetime (`not_before` handles midnight rollover).
- `registry.py` — `RecordParser` base class + `@register`; `supported_types()` imports `records/*` modules.
- `records/header.py` — standard SMF header columns shared by every table.
- `records/type30.py` — SMF30 section definitions (column names = IBM field names, lower case). One flat table per
  subtype (`smf30_1`..`smf30_6`); repeating EXCP section optionally goes to `smf30_excp` (`records: {30: {excp: true}}`).
- `pipeline.py` — read → filter → parse → per-table buffers → DataFrames with fixed schema/dtypes every
  `chunk_rows` → all writers. A record that fails to parse is counted and logged, not fatal.
- `writers/` — `files.py` (csv, json/jsonl, excel), `sql.py` (SQLAlchemy `to_sql`; batches capped by the
  driver's bind-parameter limit; DATETIME(6) on MySQL/MariaDB).
- `config.py` — YAML → dataclasses; relative paths resolve against the config file's directory; `${VAR}` env
  substitution for secrets.

## Adding a record type

Create `records/typeNN.py` with `Section` definitions and a `@register`ed `RecordParser` subclass
(`schemas()` must list every column of every table it can emit, in row order), and import the module in
`registry.supported_types()`.

## Layout caveats

SMF30 offsets follow the z/OS 2.x mapping and were checked against the sample data. The zAAP/zIIP time family
and `SMF30ICU/ISB_STEP_TERM/INIT` are stored as raw binary values: their units are not yet confirmed.
