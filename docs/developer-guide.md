# Developer guide

## Code map

```
src/smfparser/
  cli.py              argparse front end: `run`, `stats`
  config.py           YAML -> Config dataclasses; filters; ${ENV} substitution; path resolution
  reader.py           BDW/RDW detection, segment walking, spanned-record reassembly
  decoders.py         primitive formats: EBCDIC, binary, packed, SMF date/time, STCK
  layout.py           Field / Section / triplet: declarative section decoding
  registry.py         RecordParser base class, @register, supported_types()
  records/
    header.py         common header columns (HEADER_SCHEMA, parse_header)
    type30.py         SMF type 30 sections and Type30Parser
  pipeline.py         read -> filter -> parse -> buffer -> DataFrame -> writers
  writers/
    base.py           Writer interface
    files.py          CsvWriter, JsonWriter, ExcelWriter
    sql.py            SqlWriter (SQLite, MariaDB, any SQLAlchemy URL)
scripts/
  gen_smf30_fields_doc.py   regenerates docs/smf30-fields.md
tests/
  smfbuild.py         builders for synthetic records, blocks and dumps
  test_*.py
```

## Data flow

```
file ─► reader.read_records ─► (record bytes, offset)
          │  detect blocked/unblocked, join spanned segments, rebuild RDW
          ▼
pipeline: header.record_type / record_subtype ─► config.filter.keep? ──no──► counted, dropped
          │ yes
          ▼
registry parser.parse(record, ctx) ─► (table, row dict) …
          │  a parse error is logged and counted; the run continues
          ▼
per-table buffer ─(chunk_rows)─► to_frame(rows, schema) ─► every Writer.write(table, df)
                                     fixed columns + dtypes
```

Key design points:

- **Fixed schemas.** Every parser declares all columns and pandas dtypes of every table it can emit
  (`schemas()`). `pipeline.to_frame` builds every chunk with exactly those columns and types. So
  the CSV header, the SQL table definition and the Excel sheet don't change from one chunk to the
  next, even when a chunk has no value at all for some column.
- **Streaming.** The file is memory-mapped and records are yielded one at a time. Only the
  per-table buffers (at most `chunk_rows` rows each) are held in memory. The exceptions are the
  Excel writer and the JSON array mode, which keep everything until `close()`.
- **Filtering before decoding.** Type and subtype are read straight from the header bytes, so
  record types you don't want cost almost nothing.
- **IBM offsets.** Records keep their RDW, so offsets in `type30.py` can be copied straight from IBM's
  tables. Triplet offsets count the RDW too.

## Field kinds

`layout.KINDS` maps a kind to a decoder and a pandas dtype:

| Kind | Decodes | pandas dtype |
|---|---|---|
| `char` | EBCDIC text | `string` |
| `uint`, `sint` | big-endian integer | `Int64` |
| `packed` | packed decimal | `Int64` |
| `date` | `0cyydddF` → `date` | `datetime64[us]` |
| `time` | hundredths since midnight + `date=` field → `datetime` (optional `not_before=` for midnight rollover) | `datetime64[us]` |
| `tod` | STCK → `datetime` | `datetime64[us]` |
| `sec100` | hundredths → seconds | `Float64` |
| `sec128us` | 128 µs units → seconds | `Float64` |

Times are combined with their dates after all of a section's fields are decoded, so the `date`
field can sit anywhere in the section. A `not_before` reference to another `time` field only
works if that field comes **earlier** in the `Section`, because it must already be a datetime.
`smf30sit` comes before `smf30ast` and `smf30pps` for this reason.

## Adding a record type

1. Create `src/smfparser/records/typeNN.py`:

   ```python
   from ..layout import Field as F, Section, occurrences, triplet
   from ..registry import ParseContext, RecordParser, register
   from .header import HEADER_SCHEMA, parse_header

   # Illustrative names and offsets: take the real ones from the IBM record layout.
   TRIPLET_PRODUCT = 24                         # header offset of the product section's triplet

   PRODUCT = Section("product", (
       F("SMFNNVER", 0, 2),
       F("SMFNNPRD", 2, 8, "char"),
   ))

   @register
   class TypeNNParser(RecordParser):
       record_type = NN

       def schemas(self):
           return {"smfNN": {**HEADER_SCHEMA, **PRODUCT.schema()}}

       def parse(self, rec, ctx: ParseContext):
           row = parse_header(rec, ctx.codepage, ctx.source_file, ctx.offset)
           t = triplet(rec, TRIPLET_PRODUCT)
           start = next(occurrences(rec, t), None)
           row.update(PRODUCT.empty() if start is None else PRODUCT.decode(rec, start, t.length, ctx.codepage))
           yield "smfNN", row
   ```

2. Import the module in `registry.supported_types()` so it registers itself.
3. Add tests with synthetic records (see `tests/smfbuild.py`). If you have a sample dump, check
   the decoded values against it.
4. Document the tables, as for type 30 (`scripts/` + `docs/`).

Rules for `parse()`:
- Yield rows whose keys match `schemas()[table]` exactly, in the same order.
- Raise on records you can't handle. The pipeline counts and logs the error and moves on.
- Repeating sections either go to a child table that carries the parent's `source_file` and
  `record_offset`, or get folded into one column (as type 30 does with accounting).
- Options from `records: {NN: {...}}` arrive as `self.options.get(key, default)`.

## Adding an output format

Subclass `writers.base.Writer`. `write(table, df)` is called once per chunk; chunks of one table
always have identical columns. `close()` is called once, even after an error. Then register the
target type in `config.TARGET_TYPES` (with its required key) and in `writers.create_writer`.

## Tests

```sh
.venv/bin/pytest                         # all tests
.venv/bin/pytest tests/test_type30.py    # one module
```

- `tests/smfbuild.py` builds headers, type 30 records, RDW segments and BDW blocks, so tests don't
  depend on real data.
- `test_sample_dump_counts` runs against `smf_files/` when it exists (the directory is git-ignored)
  and checks the row count of each subtype.
- MariaDB isn't tested automatically. To test it by hand, start a throwaway server:
  `docker run --rm -d -p 127.0.0.1:33306:3306 -e MARIADB_ROOT_PASSWORD=x -e MARIADB_DATABASE=smf mariadb:11`.
  Then run with a `mariadb` target on port 33306.

## Regenerating the type 30 field reference

`docs/smf30-fields.md` is generated from the `Section` definitions in `records/type30.py`, plus
the descriptions in `scripts/gen_smf30_fields_doc.py`:

```sh
.venv/bin/python scripts/gen_smf30_fields_doc.py docs/smf30-fields.md
```

The script fails if a field has no description, so a new field can't be left undocumented.

## Known gaps

- zAAP/zIIP time fields, `SMF30CEPI`, `SMF30CRP` and the `SMF30ICU/ISB_STEP_TERM/INIT` fields are
  written as raw integers until their units are confirmed against the IBM documentation. Performance
  queue and residency times (`SMF30TAT`, `SMF30RES`, `SMF30JQT`, …) are also raw (1.024 ms units).
- Type 30 sections not decoded yet: APPC/MVS resource, z/OS UNIX (OpenMVS) process, usage data
  (product/IFAUSAGE), counter data, zEDC and crypto sections.
- Flag fields (`SMF30STI`, `SMF30TFL`, …) are written as integers, not broken into bits.
