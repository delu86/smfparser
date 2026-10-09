# smfparser documentation

smfparser reads binary SMF (System Management Facility) dumps from IBM z/OS. You choose which record
types and subtypes to keep in a YAML config file. The parser decodes them with pandas and writes
the result as CSV, JSON, Excel, SQLite, MariaDB or any database SQLAlchemy supports.

| Document | Read it to… |
|---|---|
| [User guide](user-guide.md) | install, run the CLI, write a config file, understand the outputs |
| [SMF input format](smf-input-format.md) | get SMF data off the mainframe in a form the parser reads; learn how records are laid out |
| [SMF type 30 field reference](smf30-fields.md) | look up every output column: source offset, type, units, meaning |
| [Developer guide](developer-guide.md) | understand the code structure, add a record type or output format, run the tests |

Supported record types: **30** (common address space work, subtypes 1–6).
