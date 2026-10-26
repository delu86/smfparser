# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Python parser for IBM z/OS SMF binary dumps. Reads the raw dataset (RECFM=VBS, transferred in
binary with BDWs/RDWs kept), filters records by type/subtype per a YAML config, decodes them into
pandas DataFrames, and writes CSV, JSON, Excel, SQLite, MariaDB or any SQLAlchemy URL.
Currently supported: SMF types 14/15, 30 (subtypes 1-6) and 110 subtype 1 (CICS performance, class 3). Sample dumps live in `smf_files/` (git-ignored).
Documentation lives in `docs/` (user guide, input format, generated SMF30, SMF14/15 and SMF110 field references,
SMF30 views, developer guide). After changing `records/type30.py`, `records/type14.py` or `records/type110.py`,
regenerate the field reference with
`.venv/bin/python scripts/gen_smf30_fields_doc.py docs/smf30-fields.md` /
`.venv/bin/python scripts/gen_smf14_fields_doc.py docs/smf14-fields.md` /
`.venv/bin/python scripts/gen_smf110_fields_doc.py smf_files/dictionary.bin docs/smf110-fields.md` (built from the
CICS dictionary, not from code).

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
  subtype (`smf30_1`..`smf30_6`), plus a derived
  `continuation` flag (overflow records with no processor section; excluded from the views); repeating EXCP section optionally goes to `smf30_excp` (`records: {30: {excp: true}}`).
- `records/type14.py` — SMF14/15 (same layout, one `DatasetActivityParser` base, tables `smf14`/`smf15`). Fixed part
  at record offsets (tape vs DASD DCB extension chosen by `SMF14RIN`), then `SMF14NUC` UCB sections (optional
  `smf14_ucb`/`smf15_ucb`, `records: {14: {ucb: true}}`), Hiperbatch, and the extended segment whose typed sections
  (SMF14STY 1-9) are flattened into the row. Derived `dsorg`/`recfm`/`disp`/`excp_total`; view `datasets`.
- `records/type110.py` — SMF 110 subtype 1 CICS monitoring, performance class only: table `smf110_1`, one row per
  transaction. Layout comes from a dictionary (class 1) record loaded from `records: {110: {dictionary: path}}`
  (`ParserOptions.path` resolves it against the config dir); phase 1 applies one dictionary to every region and
  rejects records whose connector list differs. Columns `<nickname>_<id>` (e.g. `usrcput_008`); clocks give seconds
  plus `_count`; STCK times shifted to local with the product-section offset; one precompiled `struct` per transaction.
- `pipeline.py` — read → filter → parse → per-table buffers → DataFrames with fixed schema/dtypes every
  `chunk_rows` → all writers. A record that fails to parse is counted and logged, not fatal.
- `writers/` — `files.py` (csv, json/jsonl, excel), `sql.py` (SQLAlchemy `to_sql` with plain executemany;
  multi-row VALUES are too slow to build for wide tables; DATETIME(6) on MySQL/MariaDB).
- `views.py` — SQL views (`View`, per-dialect `Elapsed`); a parser lists its views in `views()` and `SqlWriter.finish`
  recreates them after each run (type 30: `steps`, `jobs`, `intervals`, defined in `records/type30.py`;
  types 14/15: `datasets`).
- `config.py` — YAML → dataclasses; relative paths resolve against the config file's directory; `${VAR}` env
  substitution for secrets.

## Adding a record type

Create `records/typeNN.py` with `Section` definitions and a `@register`ed `RecordParser` subclass
(`schemas()` must list every column of every table it can emit, in row order), and import the module in
`registry.supported_types()`.

## Layout caveats

SMF30 offsets follow the z/OS 2.x mapping and were checked against the sample data. All time fields are
converted to seconds. Most are in hundredths of a second. The promoted times (`SMF30CEP/CEPI/CRP`) and the
queue/residency times (`SMF30TAT/RES/ETA/JQT/RQT/HQT/SQT`) are in 1.024 ms units (`sec1024us`). Units come from
pacsys and the IBM SMF Explorer descriptions; the IBM SMF Explorer offsets are wrong, so don't use them.

SMF14/15 follow the z/OS 2.5 SMF manual (PDF `ieag200_v2r5.pdf`, which has every record layout). In the extended
sections the manual counts types 5, 6 and 7 from after the 4-byte descriptor and the others from its start;
`type14.py` counts every section from the start of its descriptor.

SMF 110 has no IBM SMF-manual layout (it is in the CICS TS monitoring docs, mapping DFHSMFDS/DFHMNPDA). Product
section offsets in `type110.py` were checked on the sample: class at +22, job name +82 (not +98, which is the region
user ID), local-time offset +72. `smf_files/dictionary.bin` comes from region CXS1WA01 but matches the connector list
of all 28 regions in the sample CICS dump. `test_sample_cics_dump` checks every transaction against EPV's export of the
same dump (`smf_files/epv_files/…`); all 95 EPV columns match, allowing for EPV quirks listed in the test.
