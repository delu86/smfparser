# smfparser documentation

smfparser reads binary SMF (System Management Facility) dumps from IBM z/OS. You choose which record
types and subtypes to keep in a YAML config file. The parser decodes them with pandas and writes
the result as CSV, JSON, Excel, SQLite, MariaDB or any database SQLAlchemy supports.

| Document | Read it to… |
|---|---|
| [User guide](user-guide.md) | install, run the CLI, write a config file, understand the outputs |
| [SMF input format](smf-input-format.md) | get SMF data off the mainframe in a form the parser reads; learn how records are laid out |
| [SMF type 30 field reference](smf30-fields.md) | look up every output column: source offset, type, units, meaning |
| [SMF type 30 views](smf30-views.md) | use the `steps`, `jobs` and `intervals` views: elapsed time and CPU totals per step, job and interval |
| [SMF type 110 field reference](smf110-fields.md) | look up the CICS transaction columns: dictionary fields, types, how each is decoded |
| [SMF type 113 field reference](smf113-fields.md) | look up the hardware counter columns (CPU-measurement facility, per CPU and interval) |
| [Developer guide](developer-guide.md) | understand the code structure, add a record type or output format, run the tests |

Supported record types: **14/15** (non-VSAM data set activity), **30** (common address space work,
subtypes 1–6), **110** subtype 1 (CICS monitoring, performance class: one row per transaction) and
**113** subtypes 1 and 2 (hardware counters: one row per CPU per interval).
