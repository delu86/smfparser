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
  14:
    ucb: false                # true adds the smf14_ucb table (one row per volume)

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
| 110 | `dictionary` | none | Path (relative to the config file) of an SMF file holding the CICS monitoring dictionary record (subtype 1, class 1). Required for type 110: without it the records are skipped with a warning. See [CICS dictionary](#cics-dictionary-type-110) below. |
| 110 | `local_time` | `true` | Convert CICS timestamps (`start_005`, `stop_006`, …), which are UTC, to the local time recorded with each record, so they line up with `smf_datetime`. |
| 110 | `hex` | `[]` | Informal names of extra character fields to write as hex instead of text, e.g. `[RRMSURID]`. |
| 113 | `counters` | `false` | Also write `smf113_1_counters` / `smf113_2_counters`, one row per hardware counter. They hold every counter, including those without a column in `smf113_1`/`smf113_2` (the z/OS counter set, and extended counters past number 287). |
| 14, 15 | `ucb` | `false` | Also write `smf14_ucb` / `smf15_ucb`, one row per volume (device number, volser, EXCP count, tracks allocated). Most data sets use one volume; `smf14`/`smf15` already carry the totals and the volser list. |

#### CICS dictionary (type 110)

CICS performance records carry no field names, only a list of field connectors. Their layout is
described by a separate *dictionary* record that CICS writes when monitoring starts, and the MCT can
exclude fields, so the layout can vary between regions. smfparser reads one dictionary from the file
given in `records: {110: {dictionary: …}}` and applies it to every region. The file can be an SMF dump that
contains the dictionary record, or a dataset holding just that record. Like other SMF input, it must be
transferred in binary with the RDWs kept.

Each performance record's connector list is compared with the dictionary. A record from a region
whose MCT records a different set of fields is not parsed: it is counted under `failed` and logged as
`field connectors differ from the dictionary`. The `smf110_1` columns are listed in the
[SMF type 110 field reference](smf110-fields.md), which you can regenerate for your own dictionary.

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
| `batch_rows` | all | `1000` | Rows passed to the driver per `executemany` call. |
| `views` | all | `true` | Create the views at the end of the run: [`steps`, `jobs` and `intervals`](smf30-views.md) (type 30) and [`datasets`](smf14-fields.md#the-datasets-view) (types 14/15). |

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
| `steps`, `jobs`, `intervals` | Views (database outputs only) with readable names, elapsed time and CPU totals. See [SMF type 30 views](smf30-views.md). |
| `smf14`, `smf15` | One row per non-VSAM data set close or end of volume: type 14 for input, type 15 for output. Both tables have the same columns. |
| `smf14_ucb`, `smf15_ucb` | One row per volume (only with `records: {14: {ucb: true}}` / `{15: …}`). |
| `datasets` | View over `smf14` and `smf15` (database outputs only). See [SMF types 14/15](smf14-fields.md#the-datasets-view). |
| `smf110_1` | One row per CICS transaction, from type 110 subtype 1 performance (class 3) records. Columns depend on the CICS dictionary. See the [SMF type 110 field reference](smf110-fields.md). |
| `smf113_1`, `smf113_2` | One row per CPU per HIS interval: hardware counter deltas (subtype 1) or absolute values (subtype 2). See the [SMF type 113 field reference](smf113-fields.md). |
| `smf113_1_counters`, `smf113_2_counters` | One row per counter (only with `records: {113: {counters: true}}`). |

Every row starts with the common columns `source_file`, `record_offset`, `smf_datetime`,
`smf_type`, `smf_subtype`, `smf_sid`, `smf_ssi` and `smf_flag`. The record's own fields follow. Type 30
tables end with `continuation`, which is true for the overflow records z/OS writes when a step has
too many DDs for one record.
They are listed with their meaning and units in the [SMF type 30 field reference](smf30-fields.md)
the [SMF types 14/15 field reference](smf14-fields.md), the [SMF type 110 field reference](smf110-fields.md)
and the [SMF type 113 field reference](smf113-fields.md).

Value conventions:
- Text is decoded from EBCDIC, with trailing blanks removed.
- CPU, I/O connect, queue and residency times are in seconds. So are CICS clocks, whose start count is in a separate `_count` column.
- A time of day and its date are combined into one datetime.
- Missing sections or fields are empty (NULL).

### Example queries

Top CPU consumers among steps (SQLite or MariaDB). The [`steps` view](smf30-views.md) has a fuller CPU total:

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

Data sets a job read and wrote, from the [`datasets` view](smf14-fields.md#the-datasets-view)
(types 14 and 15). Counts are cumulative within a step, so take the last close per DD:

```sql
SELECT stepname, ddname, dsname,
       CASE smf_type WHEN 14 THEN 'input' ELSE 'output' END AS direction,
       dsorg, recfm, disp, MAX(excp) AS excp, MAX(close_time) AS closed
FROM datasets
WHERE jobname = 'MYJOB'
GROUP BY stepname, ddname, dsname, smf_type, dsorg, recfm, disp
ORDER BY closed;
```

Busiest CICS transactions, with average response time and CPU per transaction (`smf110_1`):

```sql
SELECT smfmnspn AS region, tran_001 AS tran, COUNT(*) AS n,
       AVG(elapsed) AS avg_response_s, AVG(internal_response) AS avg_internal_s, AVG(usrcput_008) AS avg_cpu_s,
       SUM(usrcput_008) AS total_cpu_s, SUM(db2reqct_180) AS db2_requests
FROM smf110_1
GROUP BY smfmnspn, tran_001
ORDER BY total_cpu_s DESC
LIMIT 20;
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `stats` shows a few records with odd types, many `truncated`, or a warning like `invalid RDW at offset 0` | The file was transferred in text/ASCII mode, or without RDWs. See [SMF input format](smf-input-format.md). |
| Text columns are garbled or contain `�` | Wrong `input.codepage`. |
| `error: no input files match …` | Globs are resolved relative to the config file's directory. |
| `environment variable X is not set` | The config contains `${X}`; export `X` before running. |
| MariaDB `Unknown database` | Create the schema first; smfparser creates tables, not databases. |
| Warning `views are not supported on …` | The database is not SQLite, MariaDB/MySQL or PostgreSQL. The tables are written, but the views are skipped. |
