"""Regenerate docs/smf30-fields.md from the SMF30 section definitions.

Usage: .venv/bin/python scripts/gen_smf30_fields_doc.py docs/smf30-fields.md
Fails if a field in records/type30.py has no description in DESC.
"""

import sys
from smfparser.records import type30 as t
from smfparser.records.header import HEADER_SCHEMA

DESC = {
# header
"source_file": "Path of the dump file the record came from",
"record_offset": "Byte offset in the file of the record's first segment (with `source_file`, a unique row key)",
"smf_datetime": "Time and date the record was written (SMF30TME + SMF30DTE), local time",
"smf_type": "Record type (SMF30RTY), always 30",
"smf_subtype": "Record subtype (SMF30STP)",
"smf_sid": "System identifier (SMF30SID)",
"smf_ssi": "Subsystem identifier (SMF30WID), e.g. JES2, STC, TSO, OMVS",
"smf_flag": "Header flag byte (SMF30FLG)",
# subsystem
"SMF30TYP": "Subtype as recorded in the subsystem section",
"SMF30RVN": "Record version number",
"SMF30PNM": "Product name ('SMF')",
"SMF30OSL": "MVS product level, e.g. SP7.2.5",
"SMF30SYN": "System name (SYSNAME)",
"SMF30SYP": "Sysplex name",
# identification
"SMF30JBN": "Job or session name",
"SMF30PGM": "Program name (PGM= on the EXEC statement)",
"SMF30STM": "Step name",
"SMF30UIF": "User-defined identification (from the common exit parameter area)",
"SMF30JNM": "JES job identifier, e.g. JOB12345",
"SMF30STN": "Step number (first step = 1)",
"SMF30CLS": "Job class (1 character; blank for TSO sessions and started tasks)",
"SMF30JF1": "Job flags",
"SMF30PGN": "Performance group number (always zero since z/OS 1.3)",
"SMF30JPT": "JES input priority",
"SMF30STD": "Date the initiator selected the step or job",
"SMF30SIT": "Time the initiator selected the step or job",
"SMF30AST": "Device allocation start time",
"SMF30PPS": "Problem program start time",
"SMF30RSD": "Date the reader recognised the JOB card",
"SMF30RST": "Time the reader recognised the JOB card",
"SMF30RED": "Date the reader reached the end of the JCL",
"SMF30RET": "Time the reader reached the end of the JCL",
"SMF30USR": "Programmer name (from the JOB statement)",
"SMF30GRP": "RACF group ID",
"SMF30RUD": "RACF user ID",
"SMF30TID": "RACF terminal ID",
"SMF30TSN": "Terminal symbolic name",
"SMF30PSN": "Name of the step that invoked the procedure (blank if not in a procedure)",
"SMF30CL8": "Job class, 8 characters",
"SMF30ISS": "Interval start (subtypes 2, 3 and 6), from the TOD clock",
"SMF30IET": "Interval end (subtypes 2, 3 and 6), from the TOD clock",
"SMF30SSN": "Substep number (z/OS UNIX; zero otherwise)",
"SMF30EXN": "z/OS UNIX program name (first 16 bytes)",
"SMF30ASI": "Address space identifier (ASID)",
"SMF30COR": "JES job correlator",
# io
"SMF30INP": "Card-image records read from DD DATA / DD * datasets",
"SMF30TEP": "Total blocks transferred (sum of EXCP counts)",
"SMF30TPT": "TSO TPUTs issued",
"SMF30TGT": "TSO TGETs issued",
"SMF30RDR": "Reader device class",
"SMF30RDT": "Reader device type",
"SMF30TCN": "Total device connect time",
"SMF30DCF": "Device connect time flags",
"SMF30TRR": "DIV pages re-read",
"SMF30AIC": "DASD I/O connect time for the address space",
"SMF30AID": "DASD I/O disconnect time for the address space",
"SMF30AIW": "DASD I/O pending plus control-unit queue time for the address space",
"SMF30AIS": "DASD start subchannel (SSCH) count for the address space",
"SMF30EIC": "DASD I/O connect time for independent enclaves",
"SMF30EID": "DASD I/O disconnect time for independent enclaves",
"SMF30EIW": "DASD I/O pending time for independent enclaves",
"SMF30EIS": "DASD SSCH count for independent enclaves",
"SMF30TEX": "Total blocks transferred, 8-byte counter (does not wrap like SMF30TEP)",
# completion
"SMF30SCC": "Step completion code. Bit 0 set means user abend; otherwise a system abend code or return code",
"SMF30STI": "Step termination indicator flags (abend, cancelled by exit, flushed, …)",
"SMF30ARC": "Abend reason code",
# processor
"SMF30PTY": "Dispatching priority (reserved on recent releases)",
"SMF30TFL": "Timer flags: which CPU fields are valid",
"SMF30CPT": "Step CPU time under TCBs (standard CPs, including zIIP/zAAP-eligible work that ran on a CP)",
"SMF30CPS": "Step CPU time under SRBs",
"SMF30ICU": "Initiator CPU time under TCBs",
"SMF30ISB": "Initiator CPU time under SRBs",
"SMF30JVU": "Vector usage time, step (obsolete)",
"SMF30IVU": "Vector usage time, initiator (obsolete)",
"SMF30JVA": "Vector affinity time, step (obsolete)",
"SMF30IVA": "Vector affinity time, initiator (obsolete)",
"SMF30IDT": "Interval start date (subtypes 2 and 3)",
"SMF30IST": "Interval start time (subtypes 2 and 3)",
"SMF30IIP": "CPU time spent processing I/O interrupts",
"SMF30RCT": "Region control task CPU time",
"SMF30HPT": "CPU time for hiperspace processing",
"SMF30CSC": "ICSF crypto service count",
"SMF30DMI": "ADMF pages written",
"SMF30DMO": "ADMF pages read",
"SMF30ASR": "Additional SRB CPU time (preemptable and client SRBs)",
"SMF30ENC": "Independent enclave CPU time",
"SMF30DET": "Dependent enclave CPU time",
"SMF30CEP": "CPU time while enqueue-promoted",
"SMF30TF2": "Additional timer flags",
"SMF30T32": "Failure flags",
"SMF30T33": "Failure flags 2",
"SMF30_TIME_ON_IFA": "Time on zAAP",
"SMF30_ENCLAVE_TIME_ON_IFA": "Independent enclave time on zAAP",
"SMF30_DEP_ENCLAVE_TIME_ON_IFA": "Dependent enclave time on zAAP",
"SMF30_TIME_IFA_ON_CP": "zAAP-eligible time that ran on a standard CP",
"SMF30_ENCLAVE_TIME_IFA_ON_CP": "Independent enclave zAAP-eligible time on a CP",
"SMF30_DEP_ENCLAVE_TIME_IFA_ON_CP": "Dependent enclave zAAP-eligible time on a CP",
"SMF30CEPI": "Enqueue-promoted CPU time for the interval",
"SMF30_TIME_ON_ZIIP": "Time on zIIP",
"SMF30_ENCLAVE_TIME_ON_ZIIP": "Independent enclave time on zIIP",
"SMF30_DEPENC_TIME_ON_ZIIP": "Dependent enclave time on zIIP",
"SMF30_TIME_ZIIP_ON_CP": "zIIP-eligible time that ran on a standard CP",
"SMF30_ENCLAVE_TIME_ZIIP_ON_CP": "Independent enclave zIIP-eligible time on a CP",
"SMF30_DEPENC_TIME_ZIIP_ON_CP": "Dependent enclave zIIP-eligible time on a CP",
"SMF30_ENCLAVE_TIME_ZIIP_QUAL": "Independent enclave time qualified to run on a zIIP",
"SMF30_DEPENC_TIME_ZIIP_QUAL": "Dependent enclave time qualified to run on a zIIP",
"SMF30CRP": "CPU time while promoted for chronic resource contention",
"SMF30ICU_STEP_TERM": "Initiator TCB CPU time, step termination part",
"SMF30ICU_STEP_INIT": "Initiator TCB CPU time, step initialisation part",
"SMF30ISB_STEP_TERM": "Initiator SRB CPU time, step termination part",
"SMF30ISB_STEP_INIT": "Initiator SRB CPU time, step initialisation part",
"SMF30_MISSED_SMF30BLK": "EXCP block counts that could not be recorded",
"SMF30_MISSED_SMF30DCT": "Device connect time that could not be recorded",
"SMF30_HIGHEST_TASK_CPU_PERCENT": "Highest CPU percentage used by a single task",
"SMF30_HIGHEST_TASK_CPU_PROGRAM": "Program of the task with the highest CPU use",
# storage
"SMF30SFL": "Storage flags",
"SMF30SPK": "Storage protect key",
"SMF30PRV": "Largest private-area storage (below 16 MB) used, in KB",
"SMF30SYS": "Largest LSQA + SWA storage (below 16 MB) used, in KB",
"SMF30PGI": "Non-VIO page-ins",
"SMF30PGO": "Non-VIO page-outs",
"SMF30CPM": "Count of page reclaims",
"SMF30NSW": "Address space swap sequences",
"SMF30PSI": "Pages swapped in",
"SMF30PSO": "Pages swapped out",
"SMF30VPI": "VIO page-ins",
"SMF30VPO": "VIO page-outs",
"SMF30VPR": "VIO reclaims",
"SMF30CPI": "Common area page-ins",
"SMF30HPI": "Hiperspace page-ins",
"SMF30LPI": "LPA page-ins",
"SMF30HPO": "Hiperspace page-outs",
"SMF30PST": "Page seconds",
"SMF30PSC": "Page seconds, 8-byte counter",
"SMF30RGB": "Private area size below 16 MB, in bytes",
"SMF30ERG": "Private area size above 16 MB, in bytes",
"SMF30ARB": "Maximum storage allocated from the bottom of the private area below 16 MB, in bytes",
"SMF30EAR": "Maximum storage allocated from the bottom of the private area above 16 MB, in bytes",
"SMF30URB": "Maximum user-key storage allocated from the top of the private area below 16 MB, in bytes",
"SMF30EUR": "Maximum user-key storage allocated from the top of the private area above 16 MB, in bytes",
"SMF30RGN": "Region size requested (REGION=), in KB",
"SMF30DSV": "Data-in-virtual pages accessed",
"SMF30PIE": "Page-ins from auxiliary storage",
"SMF30POE": "Page-outs to auxiliary storage",
"SMF30BIA": "Blocks paged in from auxiliary storage",
"SMF30BOA": "Blocks paged out to auxiliary storage",
"SMF30KIA": "Pages in blocks paged in from auxiliary storage",
"SMF30KOA": "Pages in blocks paged out to auxiliary storage",
"SMF30KIE": "Pages in blocks paged in from expanded storage",
"SMF30KOE": "Pages in blocks paged out to expanded storage",
"SMF30PSF": "Page seconds for frames above 2 GB",
"SMF30PAI": "Shared page-ins from auxiliary storage",
"SMF30PEI": "Shared page-ins from expanded storage",
"SMF30ERS": "Real storage frames used for shared pages",
"SMF30MEM": "Memory limit (MEMLIMIT), in MB",
"SMF30MES": "Source of the MEMLIMIT value",
"SMF30HVR": "Maximum 64-bit private memory objects (high water mark)",
"SMF30HVA": "Number of 64-bit memory objects allocated",
"SMF30HVO": "High water mark of 64-bit private storage, in bytes",
"SMF30HVH": "High water mark of 64-bit private storage backed by real, in bytes",
"SMF30HSO": "High water mark of 64-bit shared storage, in bytes",
"SMF30HSH": "High water mark of 64-bit shared storage backed by real, in bytes",
# performance
"SMF30SRV": "Total service units",
"SMF30CSU": "CPU service units",
"SMF30SRB": "SRB service units",
"SMF30IO": "I/O service units",
"SMF30MSO": "Main storage occupancy service units",
"SMF30TAT": "Transaction active time (1.024 ms units)",
"SMF30SUS": "Service units consumed while the address space was swapped in",
"SMF30RES": "Transaction residency time (1.024 ms units)",
"SMF30TRS": "Number of transactions",
"SMF30WLM": "WLM workload name",
"SMF30SCN": "WLM service class name",
"SMF30GRN": "WLM resource group name",
"SMF30RCN": "WLM report class name",
"SMF30ETA": "Independent enclave transaction active time",
"SMF30ESU": "Independent enclave CPU service units",
"SMF30ETC": "Independent enclave transaction count",
"SMF30JQT": "Job queue time (1.024 ms units)",
"SMF30RQT": "Time the job waited ineligible because of a resource (1.024 ms units)",
"SMF30HQT": "Time the job was held (1.024 ms units)",
"SMF30SQT": "Time the job waited for an initiator after becoming eligible (1.024 ms units)",
"SMF30PF1": "Performance flags",
"SMF30PF2": "Performance flags 2",
"SMF30INV": "Invocation indicator",
"SMF30ZEP": "zIIP/zAAP eligibility flags",
"SMF30JPN": "JES2 job class or scheduling environment information",
"SMF30MSC": "Multisystem enclave service count",
"SMF30CPC": "CPU adjustment factor",
"SMF30LOC": "Normalisation factor for zAAP/zIIP time",
"SMF30SRC": "SRB adjustment factor",
"SMF30ZNF": "zAAP normalisation factor",
"SMF30SNF": "zIIP normalisation factor",
"SMF30SRV_L": "Total service units, 8-byte counter",
"SMF30CSU_L": "CPU service units, 8-byte counter",
"SMF30SRB_L": "SRB service units, 8-byte counter",
"SMF30IO_L": "I/O service units, 8-byte counter",
"SMF30MSO_L": "MSO service units, 8-byte counter",
"SMF30ESU_L": "Independent enclave service units, 8-byte counter",
"SMF30ACB": "Accounting flags",
"SMF30CR": "Capacity change flags",
"SMF30_CAPACITY_CHANGE_CNT": "Number of processor capacity changes during the interval",
"SMF30_RCTPCPUA_ACTUAL": "Actual CPU capability (RCTPCPUA)",
"SMF30_RCTPCPUA_NOMINAL": "Nominal CPU capability",
"SMF30_RCTPCPUA_SCALING_FACTOR": "Scaling factor for the CPU capability values",
"SMF30_CAPACITY_ADJUSTMENT_IND": "Capacity adjustment indicator (100 = no adjustment)",
"SMF30_CAPACITY_CHANGE_RSN": "Reason for the capacity change",
"SMF30_CAPACITY_FLAGS": "Capacity flags",
# operator
"SMF30PDM": "Non-specific tape volume mount requests",
"SMF30PRD": "Specific tape volume mount requests",
"SMF30PTM": "Non-specific DASD volume mount requests",
"SMF30TPR": "Specific DASD volume mount requests",
"SMF30MTM": "Mount requests for MSS virtual volumes",
"SMF30MSR": "Non-specific MSS virtual volume mount requests",
# excp
"SMF30DEV": "Device class",
"SMF30UTP": "Unit type",
"SMF30CUA": "Device number",
"SMF30DDN": "DD name",
"SMF30BLK": "Blocks transferred (EXCP count) for this DD",
"SMF30BSZ": "Largest block size",
"SMF30DCT": "Device connect time for this DD",
"SMF30XBS": "Blocks transferred, 8-byte counter",
}

UNITS = {"sec100": "seconds (stored in hundredths)", "sec128us": "seconds (stored in 128 µs units)",
         "time": "datetime", "date": "date", "tod": "datetime (TOD clock, UTC)", "char": "text (EBCDIC)",
         "uint": "integer", "sint": "integer", "packed": "integer"}
RAW = {f.name for f in t.PROCESSOR.fields if f.name.startswith("SMF30_TIME") or "_TIME_" in f.name or f.name.endswith(("_STEP_TERM","_STEP_INIT")) or f.name in ("SMF30CEPI","SMF30CRP")}
TRIP = {t.TRIPLET_SUBSYSTEM:"SMF30SOF",t.TRIPLET_IDENT:"SMF30IOF",t.TRIPLET_IO:"SMF30UOF",t.TRIPLET_COMPLETION:"SMF30TOF",
        t.TRIPLET_PROCESSOR:"SMF30COF",t.TRIPLET_STORAGE:"SMF30ROF",t.TRIPLET_PERFORMANCE:"SMF30POF",t.TRIPLET_OPERATOR:"SMF30OOF",t.TRIPLET_EXCP:"SMF30EOF"}

missing=[]
def table(fields):
    out=["| Column | Offset | Len | Type | Description |","|---|---:|---:|---|---|"]
    for f in fields:
        desc=DESC.get(f.name) or missing.append(f.name) or ""
        kind=UNITS[f.kind]
        if f.name in RAW: kind="integer, raw (units not yet confirmed)"
        out.append(f"| `{f.column}` | {f.offset} | {f.length} | {kind} | {desc} |")
    return "\n".join(out)

o=[]
o.append("""# SMF type 30 field reference

<!-- Generated by scripts/gen_smf30_fields_doc.py from src/smfparser/records/type30.py. Do not edit by hand. -->

SMF type 30 ("common address space work") is written for jobs, steps, started tasks and TSO
sessions. smfparser writes one table per subtype. Every table has the same columns, listed below:
the common header columns first, then the sections in the order shown here.

| Subtype | Table | Written when |
|---:|---|---|
| 1 | `smf30_1` | Job or session starts |
| 2 | `smf30_2` | Interval (for long-running work) |
| 3 | `smf30_3` | Last interval, at step end |
| 4 | `smf30_4` | Step ends |
| 5 | `smf30_5` | Job ends (totals for the job) |
| 6 | `smf30_6` | System address space interval |
| any | `smf30_excp` | One row per DD from the EXCP section (only with `records: {30: {excp: true}}`) |

A section can be missing from a record; for example, subtype 1 has no processor accounting
section. Its columns are then empty (NULL). A field that lies past the end of a shorter, older
section is also empty.

Column names are the IBM field names in lower case. *Offset* is relative to the start of the
section, which the header triplet in brackets points to. Offsets were checked against
z/OS 2.5 records (record version `05`).

**Conventions**
- Text is decoded from EBCDIC (code page `input.codepage`, default `cp037`), with trailing blanks and binary zeros removed.
- CPU times and connect times are converted to **seconds**.
- A time of day is combined with its date into a single datetime. `smf30ast` and `smf30pps` have no date of their
  own and use `smf30std`; if the result is earlier than `smf30sit`, it is moved to the next day (midnight rollover).
- Fields marked *raw* are written as unconverted binary integers until their units are checked
  against the IBM documentation. The same applies to queue and residency times documented in 1.024 ms units.

## Common header columns
""")
o.append("| Column | Type | Description |\n|---|---|---|")
for c,dt in HEADER_SCHEMA.items():
    o.append(f"| `{c}` | {dt} | {DESC[c]} |")
o.append("\nThe accounting section, which is variable length, becomes one column, `smf30act`: the JOB/EXEC accounting fields joined with commas, as in JCL.\n")
for at,s in t.FLAT_SECTIONS:
    o.append(f"## {s.name.capitalize()} section ({TRIP[at]})\n")
    o.append(table(s.fields)+"\n")
o.append(f"""## EXCP section ({TRIP[t.TRIPLET_EXCP]}): table `smf30_excp`

One row per DD entry. Each row also carries `source_file`, `record_offset`, `smf_datetime`, `smf_subtype`,
{", ".join(f"`{c}`" for c in t.EXCP_KEY_COLUMNS)} from the parent record, and `excp_index`
(the entry's position within the record). `source_file` + `record_offset` join back to the subtype table.
""")
o.append(table(t.EXCP.fields)+"\n")
if missing: sys.exit(f"missing descriptions: {missing}")
open(sys.argv[1],"w").write("\n".join(o))
