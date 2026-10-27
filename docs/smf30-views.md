# SMF type 30 views

The raw tables (`smf30_1` … `smf30_6`) have hundreds of columns named after IBM fields. The views
put the most useful facts about each step, job and interval under readable names, with elapsed
time and CPU totals already worked out. Use them to debug, to explore the data, and as a source for
charts and dashboards.

| View | Source | One row per |
|---|---|---|
| `steps` | `smf30_4` | step that ended |
| `jobs` | `smf30_5` | job that ended (totals for the whole job) |
| `intervals` | `smf30_2` UNION ALL `smf30_3` | interval of long-running work (started tasks, TSO users, long jobs) |

Continuation records are left out of all three views (see [Caveats](#caveats)), so each row is one
step, job or interval. Their device I/O is added to the row they continue.

## How the views are created

The views are created by the database outputs (`sqlite`, `mariadb`, `sql`) at the end of every
successful `smfparser run`:

- Each view is dropped and created again on every run, so the definition always matches the
  smfparser version you run.
- A view needs all of its source tables. If a run doesn't produce one of them (for example, a dump
  with no subtype 3), smfparser creates that table empty, so the view still works.
- `table_prefix` applies to views too: with `table_prefix: raw_` they are called `raw_steps`,
  `raw_jobs` and `raw_intervals`, and they read the `raw_smf30_*` tables.
- To turn the views off, add `views: false` to the target.
- The views use dialect-specific SQL to compute elapsed time. SQLite, MariaDB/MySQL and PostgreSQL
  are supported. On any other database the views are skipped with a warning.

## Columns

All three views have the same columns. `intervals` has one extra column, `subtype`.

| Column | Type | Definition |
|---|---|---|
| `system` | text | `smf_sid`: the SMF system ID of the system that wrote the record |
| `subtype` | integer | *intervals only*. `smf_subtype`: 2 = interval, 3 = last interval before the step ended |
| `jobname` | text | `smf30jbn`: job name (or started task or TSO user ID) |
| `stepname` | text | `smf30stm`: step name. **Empty in `jobs`**, because job end records don't carry a step name. |
| `jobnumber` | text | `smf30jnm`: JES job ID, e.g. `JOB12345`, `STC06141` |
| `stepnumber` | integer | `smf30stn`: step number. In `jobs`, the number of the last step. |
| `start_time` | datetime | See [Start and end times](#start-and-end-times). |
| `end_time` | datetime | `smf_datetime`: when the record was written |
| `elapsed_sec` | number | `end_time − start_time`, in seconds |
| `cp_cpu_sec` | number | CPU seconds on standard processors (CPs) |
| `ziip_cpu_sec` | number | CPU seconds on zIIPs |
| `potential_cp_cpu_sec` | number | CPU seconds this work would have used if it had all run on CPs |
| `diskio_blk` | integer | Blocks transferred to and from DASD (EXCP entries with device class `X'20'`) |
| `diskio_time` | number | DASD connect seconds of those entries |
| `tapeio_blk` | integer | Blocks transferred to and from tape (device class `X'80'`) |
| `tapeio_time` | number | Tape connect seconds of those entries |

### Start and end times

| View | `start_time` | `end_time` |
|---|---|---|
| `steps` | `smf30sit`: step initiation | `smf_datetime`: the record is written when the step ends |
| `jobs` | `smf30sit`: when the initiator selected the job | `smf_datetime`: the record is written when the job ends |
| `intervals` | `smf30ist`: interval start | `smf_datetime`: the record is written when the interval ends |

How `elapsed_sec` is computed depends on the database:

| Database | Expression |
|---|---|
| MariaDB / MySQL | `TIMESTAMPDIFF(MICROSECOND, start, end) / 1000000.0` |
| SQLite | `ROUND((julianday(end) - julianday(start)) * 86400.0, 3)` |
| PostgreSQL | `EXTRACT(EPOCH FROM (end - start))` |

SMF times have a resolution of 1/100 s, so every elapsed time is a multiple of 0.01 s.

### CPU time formulas

The formulas come from Cheryl Watson's *The Many CPU Fields Of SMF* (SHARE, 2013). Which fields
already contain which comes from the SMF30 layout of Pacific Systems Group. Every source field is
in seconds, and a NULL counts as 0.

**`cp_cpu_sec`**: total work that ran on standard CPs

```
smf30cpt + smf30cps + smf30icu + smf30isb + smf30iip + smf30rct + smf30hpt
```

| Field | What it measures |
|---|---|
| `smf30cpt` | Work running under TCBs (task control blocks). Also includes enclave time, preemptable and client SRB time, and zIIP/zAAP-eligible work that ran on a CP. |
| `smf30cps` | Work running under SRBs (service request blocks) |
| `smf30icu`, `smf30isb` | Initiator TCB/SRB time (step setup and cleanup) |
| `smf30iip` | Handling I/O interrupts |
| `smf30rct` | Region control task (address space startup and swapping) |
| `smf30hpt` | Moving data between a hiperspace and the address space |

**`ziip_cpu_sec`**: work that ran on a zIIP

```
smf30_time_on_ziip
```

**`potential_cp_cpu_sec`**: what the work would have cost if it had all run on CPs

```
cp_cpu_sec
  + smf30_time_on_ifa  * smf30znf / 256
  + smf30_time_on_ziip * smf30snf / 256
```

`smf30znf` and `smf30snf` are the normalisation factors for zAAPs and zIIPs. They are 256 when the
specialty engines run at the same speed as the CPs. On a sub-capacity machine they are larger,
because the specialty engine is faster than a CP. Use this column to estimate CP cost without
specialty engines, or to compare work across machines.

> **Don't add these fields to the totals.** `smf30asr`, `smf30enc`, `smf30det`,
> `smf30_time_ziip_on_cp` and `smf30_time_ifa_on_cp` are already included in `smf30cpt`.
> Adding them counts the same CPU time twice.

The source fields are kept as doubles, so a sum can show floating-point noise, such as
`0.21000000000000002`. Round in your query or chart if you need to.

## Example queries

Top 20 steps by CP time:

```sql
SELECT jobname, jobnumber, stepnumber, stepname, cp_cpu_sec, ziip_cpu_sec, elapsed_sec
FROM steps
ORDER BY cp_cpu_sec DESC
LIMIT 20;
```

Share of each job's CPU that ran on zIIP:

```sql
SELECT jobname, jobnumber, cp_cpu_sec, ziip_cpu_sec,
       ROUND(100.0 * ziip_cpu_sec / NULLIF(cp_cpu_sec + ziip_cpu_sec, 0), 1) AS ziip_pct
FROM jobs
ORDER BY ziip_cpu_sec DESC;
```

Timeline of one started task, interval by interval:

```sql
SELECT start_time, end_time, subtype, cp_cpu_sec, ziip_cpu_sec,
       cp_cpu_sec / NULLIF(elapsed_sec, 0) AS cps_busy
FROM intervals
WHERE jobname = 'CQMDBSTR'
ORDER BY end_time;
```

`cps_busy` is the average number of CPs the task kept busy during the interval. 0.5 means half a
CP.

The steps of one job, in order:

```sql
SELECT stepnumber, stepname, start_time, end_time, elapsed_sec, cp_cpu_sec
FROM steps
WHERE jobnumber = 'JOB56950'
ORDER BY stepnumber;
```

### Device I/O

`diskio_blk`, `diskio_time`, `tapeio_blk` and `tapeio_time` add up the EXCP section, one entry per
DD (`smf30blk` blocks, `smf30dct` connect time), split by device class `smf30dev`. They match EPV's
`DISKIO`, `DISKIOTM`, `TAPEIO` and `TAPEIOTM`. The parser computes them for every record, so they are
also columns of the `smf30_*` tables, and they don't need `excp: true`.

A view row also includes the device I/O of its continuation records. A continuation is matched to its
record on `system`, `jobnumber`, reader start (`smf30rst`), `stepnumber` and `start_time`
(`smf30sit`), plus the interval end (`smf30iet`) in `intervals`.

Entries for other device classes (e.g. `X'00'` for DDs with no device, such as spool or DUMMY) are not
counted. Their sum is not `smf30tep`, which also counts I/O not attributed to any DD.

## Caveats

- **Continuation records are filtered out:** an SMF record holds at most about 32 KB. When a step
  has more DDs than fit in one record (about 1,000), z/OS writes the rest in continuation records.
  These carry only the subsystem, identification and EXCP sections: no CPU, no interval start,
  no service data. The parser marks them with `continuation = true` in every output (see the
  [field reference](smf30-fields.md#common-header-columns)). The tables keep them (with
  `excp: true` they hold the remaining DDs), but every view adds `WHERE NOT continuation` so each
  step, job or interval appears once. Their device I/O is added to the row they continue
  (see [Device I/O](#device-io)); every other column comes from the first record only. In the sample dump, this removes 14 step, 47 job and
  17 interval rows. To look at them, query the tables, e.g.
  `SELECT * FROM smf30_4 WHERE continuation`.
- **Duplicates:** if you load the same dump twice with `if_exists: append`, its rows appear twice in
  the views too. Use `if_exists: replace`, or deduplicate on `source_file` and `record_offset` in
  the source tables.
- **Job numbers are reused:** JES reuses job numbers. To identify one job execution, combine
  `system`, `jobnumber` and `start_time`.
- **A step can appear in both views:** a long-running step writes interval records (in
  `intervals`) and then a step end record (in `steps`). Its CPU time is in both views, so never
  add the two together.
- **Subtype 6 isn't included:** intervals of system address spaces (`smf30_6`) are not in
  `intervals`.

## Adding a column

The views are defined in one place, `src/smfparser/records/type30.py`:

- `_view_columns()` lists the columns shared by all three views;
- `VIEWS` lists the views and their source tables.

1. Add an `(alias, SQL expression)` pair to `_view_columns()`. You can use any column of the
   `smf30_*` tables (see the [field reference](smf30-fields.md)).
2. Write expressions that work on every database you use: plain column names, arithmetic and
   `COALESCE` are portable.
3. Run `smfparser run` again. The views are recreated automatically.

For example, to add the program name and the WLM service class:

```python
("program", "smf30pgm"),
("service_class", "smf30scn"),
```

The [developer guide](developer-guide.md#adding-a-view-or-view-column) explains how views work in
the code.
