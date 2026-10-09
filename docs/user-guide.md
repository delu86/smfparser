# User guide

## Installation

smfparser needs Python 3.11 or later. The repository pins 3.11 with [mise](https://mise.jdx.dev/).

```sh
mise install                                  # installs the pinned Python
mise exec -- python -m venv .venv
.venv/bin/pip install -e ".[dev]"             # drop [dev] if you don't need pytest
```

Installing creates the `smfparser` command in `.venv/bin/`. The MariaDB driver (`pymysql`) and the
Excel writer (`openpyxl`) are installed too. For another database, install its SQLAlchemy driver
(for example `psycopg` for PostgreSQL).

## Quick start

```sh
# What is in this dump?
.venv/bin/smfparser stats smf_files/MY.SMF.DUMP

# Parse it with the settings in a config file
cp config.example.yaml my-config.yaml          # then edit it
.venv/bin/smfparser run -c my-config.yaml
```

## Commands

### `smfparser stats FILE...`

Counts the records in each file by type and subtype, without decoding them. Use it to see what
a dump contains before you write a filter, or to check that a file reads cleanly:

```
smf_files/xcsmfp02.smfaltro.d261009.t103000: 71422 records in 75247 segments (orphan 0, truncated 0)
  type subtype    count
     2      -        1
    30      1      110
    30      4      471
   ...
```

*segments* can be higher than *records*, because long records are split into spanned segments.
*orphan* or *truncated* should be 0. If they aren't, the file is damaged or was transferred
incorrectly (see [SMF input format](smf-input-format.md)).

### `smfparser run -c CONFIG [FILE...] [--log-level LEVEL]`

Parses the input files and writes every output target in the config. Files given on the command
line replace `input.files`. At the end it prints a summary:

```
segments 187001  records 177333  orphan segments 0  truncated 0
records read 177333, parsed 4533, failed 0, no parser 0
rows written per table:
  smf30_4                  1843
  ...
```

- **failed**: records kept by the filter that could not be decoded. Each one is logged with its
  file offset and skipped; the run continues.
- **no parser**: records kept by the filter whose type has no decoder yet.

Exit codes: `0` success, `1` some records failed to parse, `2` configuration error.

## Configuration file

The config is a YAML file; `config.example.yaml` is a complete example. Relative paths are
resolved against **the config file's directory**, not the current directory. Any `${VAR}` in a
value is replaced with the environment variable `VAR`; use this for passwords.

```yaml
input:
  files: ["smf_files/*"]      # one or more glob patterns
  codepage: cp037             # EBCDIC code page for text fields

filter:
  include:                    # type -> subtypes; [] means all subtypes
    30: [4, 5]
  exclude: {}                 # same form; applied after include

records:
  30:
    excp: false               # true adds the smf30_excp table

output:
  chunk_rows: 50000
  targets:
    - {type: csv, dir: out/csv}

logging:
  level: INFO
```

### `input`

| Key | Default | Meaning |
|---|---|---|
| `files` | — | Glob patterns (a list, or one string). Each pattern must match at least one file. |
| `codepage` | `cp037` | Python codec name for EBCDIC text: `cp037` (US/Canada), `cp500` (international), `cp1140` (US with euro sign), `cp273` (Germany), `cp280` (Italy), and so on. |

### `filter`

Selects records before they are decoded, so filtering is cheap.

- `include`: a mapping of record type to a list of subtypes. An empty list keeps every subtype of
  that type. If `include` is left out, every record type that has a parser is kept. As a
  shorthand, a plain list of types keeps all their subtypes: `include: [30]`.
- `exclude`: same form. It is applied after `include`, so you can say "all of type 30 except
  subtype 6": `include: [30]` with `exclude: {30: [6]}`.

### `records`

Options for each record type, keyed by type number.

| Type | Key | Default | Meaning |
|---|---|---|---|
| 30 | `excp` | `false` | Also write `smf30_excp`, one row per DD from the EXCP section. This table can be very large: about 75 rows per type 30 record in typical batch workloads. |

### `output`

| Key | Default | Meaning |
|---|---|---|
| `chunk_rows` | `50000` | Rows kept in memory per table before they are passed to the writers. Lower it to use less memory. |
| `targets` | — | A list of output targets; every table is written to every target. |

Every target has a `type`. The other keys depend on the type:

**`csv`**: one `<table>.csv` per table.

| Key | Default | |
|---|---|---|
| `dir` | required | Output directory (created if missing). Existing files are overwritten. |
| `sep` | `,` | Field separator. |
| `encoding` | `utf-8` | File encoding. |

**`json`**: one file per table.

| Key | Default | |
|---|---|---|
| `dir` | required | Output directory. |
| `lines` | `true` | `true` writes [JSON Lines](https://jsonlines.org/) (`<table>.jsonl`, streamed). `false` writes one JSON array (`<table>.json`), built in memory at the end of the run. |
| `indent` | none | Indentation for array mode. |

Datetimes are written as ISO 8601 strings.

**`excel`**: one workbook, one sheet per table.

| Key | Default | |
|---|---|---|
| `path` | required | `.xlsx` file to create. |

Every row is held in memory until the end of the run. An Excel sheet holds at most 1,048,576
rows, so larger tables are cut off with a warning. Excel suits small extracts, such as one
subtype for a day. Use CSV or a database for bulk data.

**`sqlite`**, **`mariadb`**, **`sql`**: database tables, one per output table (`smf30_4`, …).

| Key | Applies to | Default | |
|---|---|---|---|
| `path` | sqlite | required | Database file. |
| `host`, `port` | mariadb | `localhost`, `3306` | Server address. |
| `database` | mariadb | required | Schema name; it must already exist. |
| `user`, `password` | mariadb | — | Credentials. Use `${ENV_VAR}` for the password. |
| `url` | sql | required | Any SQLAlchemy URL, e.g. `postgresql+psycopg://user:pw@host/db`. |
| `if_exists` | all | `append` | What to do when a table already exists at the start of the run: `append`, `replace` (drop and recreate) or `fail`. |
| `table_prefix` | all | `""` | Prefix added to every table name, e.g. `raw_`. |
| `batch_rows` | all | `1000` | Rows per INSERT statement. It is capped automatically to stay under the driver's bind-parameter limit. |

The parser creates tables from the DataFrame types:
- integers become `BIGINT`;
- seconds become `DOUBLE`/`REAL`;
- datetimes become `DATETIME(6)` on MariaDB, so hundredths of a second are kept;
- text becomes `TEXT`.

No indexes are created. Add your own, for example on `(smf30jbn, smf30jnm)` or `smf_datetime`.

> **Appending** the same dump twice duplicates its rows. Each row records `source_file` and
> `record_offset`, which you can use to deduplicate or to check whether a file was already loaded.

### `logging`

`level`: `DEBUG`, `INFO` (default), `WARNING` or `ERROR`. `--log-level` on the command line overrides it.

## Output tables

| Table | Contents |
|---|---|
| `smf30_1` … `smf30_6` | One row per type 30 record of that subtype. All six tables have the same columns. |
| `smf30_excp` | One row per DD (only with `records: {30: {excp: true}}`). |

Every row starts with the common columns `source_file`, `record_offset`, `smf_datetime`,
`smf_type`, `smf_subtype`, `smf_sid`, `smf_ssi` and `smf_flag`. The record's own fields follow.
They are listed with their meaning and units in the [SMF type 30 field reference](smf30-fields.md).

Value conventions:
- Text is decoded from EBCDIC, with trailing blanks removed.
- CPU times and I/O connect times are in seconds.
- A time of day and its date are combined into one datetime.
- Missing sections or fields are empty (NULL).

### Example queries

Top CPU consumers among steps (SQLite or MariaDB):

```sql
SELECT smf30jbn AS job, smf30jnm AS jobid, smf30stm AS step, smf30pgm AS program,
       smf30cpt + smf30cps AS cpu_seconds, smf30scn AS service_class
FROM smf30_4
ORDER BY cpu_seconds DESC
LIMIT 20;
```

Steps that ended with a nonzero completion code:

```sql
SELECT smf30jbn, smf30jnm, smf30stm, smf30scc, smf30arc, smf_datetime
FROM smf30_4
WHERE smf30scc <> 0;
```

`smf30scc` holds either a return code or an abend code; `smf30sti` holds the termination flags
that tell the two apart. The bit meanings are in the IBM manual; smfparser writes both fields as
plain integers.

Jobs by elapsed time (job end records), with pandas:

```python
import pandas as pd
jobs = pd.read_csv("out/csv/smf30_5.csv", parse_dates=["smf_datetime", "smf30sit"])
jobs["elapsed_s"] = (jobs["smf_datetime"] - jobs["smf30sit"]).dt.total_seconds()
print(jobs.nlargest(10, "elapsed_s")[["smf30jbn", "smf30jnm", "elapsed_s", "smf30cpt"]])
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `stats` shows a few records with odd types, many `truncated`, or a warning like `invalid RDW at offset 0` | The file was transferred in text/ASCII mode, or without RDWs. See [SMF input format](smf-input-format.md). |
| Text columns are garbled or contain `�` | Wrong `input.codepage`. |
| `error: no input files match …` | Globs are resolved relative to the config file's directory. |
| `environment variable X is not set` | The config contains `${X}`; export `X` before running. |
| MariaDB `Unknown database` | Create the schema first; smfparser creates tables, not databases. |
