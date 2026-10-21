"""Regenerate docs/smf14-fields.md from the SMF14/15 section definitions.

Usage: .venv/bin/python scripts/gen_smf14_fields_doc.py docs/smf14-fields.md
Fails if a field in records/type14.py has no description in DESC.
"""

import sys
from smfparser.records import type14 as t
from smfparser.records.header import HEADER_SCHEMA

DESC = {
# header
"source_file": "Path of the dump file the record came from",
"record_offset": "Byte offset in the file of the record's first segment (with `source_file`, a unique row key)",
"smf_datetime": "Time and date the record was written (SMF14TME + SMF14DTE), local time: when the data set was closed or reached end of volume",
"smf_type": "Record type (SMF14RTY): 14 or 15",
"smf_subtype": "Always empty: types 14 and 15 have no subtypes",
"smf_sid": "System identifier (SMF14SID)",
"smf_ssi": "Always empty: types 14 and 15 have no subsystem identifier",
"smf_flag": "Header flag byte (SMF14FLG)",
# fixed part
"SMF14JBN": "Job name",
"SMF14RSD": "Date the reader recognised the JOB card",
"SMF14RST": "Time the reader recognised the JOB card",
"SMF14UID": "User-defined identification (from the common exit parameter area)",
"SMF14RIN": "Record and data set indicators. Bits (value): EOV 0x4000, DASD 0x2000, temporary data set 0x1000, BDAM 0x0800, ISAM 0x0400/0x0200, VIO 0x0100, PDSE 0x0080, QSAM TRUNC on PDSE 0x0040, null PDSE segment 0x0020, extended format 0x0010, Hiperbatch section 0x0008, extended information segment 0x0004, closed by task termination 0x0002, task abending 0x0001",
"SMF14SDC": "Length of the DCB/DEB section (28)",
"SMF14NUC": "Number of UCB sections (one per volume processed)",
"SMF14SUC": "Length of each UCB section",
"SMF14SET": "Length of the ISAM extension section (always 0 on current releases)",
"SMF14OPD": "Date the data set was opened",
"SMF14OPE": "Time the data set was opened",
"SMF14TIOE1": "Length of the TIOT DD entry (TIOELNGH)",
"SMF14TIOE2": "TIOT status byte (TIOESTTA): tape label processing, unallocation, rewind/unload",
"SMF14TIOE3": "Number of devices requested at allocation (TIOEWTCT)",
"SMF14TIOE4": "Data set and device indicator (TIOELINK)",
"SMF14TIOE5": "DD name (TIOEDDNM)",
"SMF14TIOE7": "TIOESTTC byte",
"JFCBDSNM": "Data set name (DSNAME=)",
"JFCBELNM": "Member name or relative generation number, e.g. `+1`",
"JFCBTSDM": "Job/data management flags: 0x80 cataloged, 0x20 subsystem data set, …",
"JFCBLTYP": "Label type (LABEL=): 0x02 SL, 0x01 NL, 0x04 NSL, 0x10 BLP, 0x40 AL, …",
"JFCBFLSQ": "Tape file sequence number (LABEL=(n,…))",
"JFCBVLSQ": "Volume sequence number (VOL=(,,n))",
"JFCBCRDT": "Data set creation date",
"JFCBXPDT": "Data set expiration date (LABEL=EXPDT= or RETPD=); empty if none. 1999-12-31 (99365) means never expires",
"JFCBIND1": "Indicator byte 1: 0xC0 RLSE, 0x02 GDG generation, 0x01 PDS member",
"JFCBIND2": "Indicator byte 2: DISP status (0xC0 NEW, 0x80 MOD, 0x40 OLD; 0x08 shared), 0x01 temporary",
"JFCBUFNO": "Number of buffers (BUFNO=)",
"JFCBUFL": "Buffer length (BUFL=)",
"JFCDSORG": "Data set organisation from the JFCB (DSORG=), 2 bytes",
"JFCRECFM": "Record format from the JFCB (RECFM=)",
"JFCOPTCD": "Option codes (OPTCD=)",
"JFCBLKSI": "Block size (BLKSIZE=)",
"JFCLRECL": "Logical record length (LRECL=)",
"JFCBNVOL": "Number of volume serials for the data set",
"JFCBVOL1": "Volume serial 1",
"JFCBVOL2": "Volume serial 2",
"JFCBVOL3": "Volume serial 3",
"JFCBVOL4": "Volume serial 4",
"JFCBVOL5": "Volume serial 5 (later volumes are in JFCB extensions, not recorded)",
"JFCBPQTY": "Primary space quantity (SPACE=)",
"JFCBCTRI": "Space request type: 0xC0 CYL, 0x80 TRK, 0x40 average block length; 0x08 CONTIG, 0x01 ROUND, …",
"JFCBSQTY": "Secondary space quantity",
"JFCBDQTY": "Directory blocks quantity",
"JFCBVLCT": "Volume count (VOL=(,,,n))",
"SMF14DCBOR": "Data set organisation in use (DCBDSORG)",
"SMF14DCBRF": "Record format in use (DCBRECFM)",
"SMF14DCBMF": "I/O macro and options (DCBMACRF)",
"SMF14DCBFL": "OPEN/CLOSE/EOV flags, e.g. type of last I/O (DCBOFLGS)",
"SMF14DCBOP": "Option codes (DCBOPTCD)",
"SMF14DEBFL": "Data set and device status (DEBOFLGS)",
"SMF14DEBOP": "I/O method and EOV disposition (DEBOPATB)",
"SMF14DEBVL": "Volume sequence number (DEBVOLSQ)",
# tape / DASD extensions
"SMF14DCBBL": "Block count for the volume (DCBBLKCT)",
"SMF14DSSNO": "Data set serial number (UCBFSER)",
"SMF14TDA": "Tape data set authorisation flags",
"SMF14NTU": "Relative track and record of the last user block: TTR0 (basic format), TTTR (large format, SMF14FG1 bit 0), or tracks used on all volumes (extended format)",
"SMF14NTR": "Tracks released by DADSM (partial release)",
"SMF14NER": "Extents released by DADSM",
"SMF14EDI": "Enhanced Data Integrity flags",
"SMF14FG1": "Flags: 0x80 large format data set, 0x40 EXCP/XDAP issued on an EAV",
# UCB
"SMF14UCBDV": "Device number (X'7FFF' for VIO)",
"SMF14SRTEV": "Volume serial",
"SMF14UCBTY": "Unit type (UCBTYP); the third byte is the device class (0x20 DASD, 0x80 tape)",
"SMF14SRTES": "DASD volume status (UCBSTAB): private, public, storage",
"SMF14NEX": "Number of extents on the volume",
"SMF14EXCP": "EXCP count (blocks transferred) on the volume, cumulative for the step. For PDSEs, pages read or written; for compressed data sets, physical blocks",
"SMF14SRTEF": "Data set sequence count",
"SMF14SRTEQ": "Data set sequence number",
"SMF14NTA": "Tracks allocated on the volume",
# Hiperbatch
"SMF14IOREQ": "I/O requests for which Hiperbatch looked in its buffers",
"SMF14CHITS": "I/O requests satisfied from Hiperbatch buffers",
"SMF14NMWTS": "Times Hiperbatch suspended the requester because another user was reading the data",
"SMF14PHIOS": "I/O requests satisfied by DASD I/O",
"SMF14CIOS": "DASD I/Os whose data Hiperbatch copied into its buffers",
# type 1
"SMF14XF1": "Indicators: 0x80 SMF14CDS/SMF14UDS are invalid",
"SMF14XF2": "Indicators (reserved)",
"SMF14CDL": "Bytes of compressed data read or written since open",
"SMF14UDL": "Bytes of data read or written since open, before compression",
"SMF14CDS": "Size of the compressed format data set, compressed bytes",
"SMF14UDS": "Size of the compressed format data set, uncompressed bytes",
"SMF14CIS": "Physical block size of the extended format data set",
"SMF14CMPTYPE": "Compression type: 0 none/unknown, 1 generic, 2 tailored, 3 zEDC",
# type 2
"SMF14MCN": "SMS management class",
"SMF14DCN": "SMS data class",
"SMF14SCN": "SMS storage class",
# type 3
"SMF14SPN": "Step name",
"SMF14PGN": "Program name of the step",
"SMF14JOBID": "JES job ID, e.g. JOB12345 (DASD only)",
"SMF14PLXID": "Sysplex name (DASD only)",
# type 4
"SMF14CFG": "CCSID indicators",
"SMF14USR": "CCSID the application expects",
"SMF14TPE": "CCSID of the data on tape",
"SMF14LBL": "CCSID in the tape label of an existing tape opened for input",
# type 5
"SMF14BFG": "Indicators: 0x8000 block size present, 0x4000 flags present, 0x2000 data set version present, 0x1000 alias present",
"SMF14LBS": "Block size (8-byte value; covers large block interface sizes)",
"SMF14FLG1": "Flags: 0x80 BSAM user PGFIX, 0x40/0x20 DCBE EADSCB=OK, 0x10 DD has an XTIOT entry",
"SMF14FLG2": "Flags (byte 2)",
"SMF14DSVER": "Data set version: 0 neither PDSE nor extended format, 1 PDSE V1 or extended format V1, 2 V2",
"SMF14ALI": "Alias data set name",
# type 6
"SMF14DRD": "PDSE directory read requests",
"SMF14DRDH": "PDSE directory read cache hits",
"SMF14MRD": "PDSE member read requests",
"SMF14MRDH": "PDSE member read cache hits",
"SMF14MCE": "Members eligible for caching",
"SMF14MST": "Member cache pages stolen",
"SMF14MNC": "Members eligible for caching but not cached",
"SMF14MCF": "Members eligible for caching but the cache was full",
# type 7
"SMF14KL1": "Tape encryption key label 1",
"SMF14CD1": "Encoding of key label 1: L label, H hash",
"SMF14KL2": "Tape encryption key label 2",
"SMF14CD2": "Encoding of key label 2: L label, H hash",
"SMF14KET": "Key exchange (encryption overhead) time; type 15 only, file sequence 1 from load point",
# type 8
"SMF14RFG0": "RAS flags present: 0x80 DCBE reject flags, 0x40 partial release flags",
"SMF14RFG1": "Authorisation: 0x80 DCBE BYPASS_AUTH=YES, 0x40 JSCBPASS, 0x20 caller authorised, 0x10 SAF check bypassed",
"SMF14RASDATA0": "Why the DCBE was invalidated (0x80 EXCP without foundation extension, 0x40 DSORG, 0x20 not addressable, …)",
"SMF14RASDATA1": "Why CLOSE did not do partial release (0x80 VIO, 0x40 abending, 0x20 not opened for output, …, 0x04 I/O error)",
# type 9
"SMF14DEF": "DASD encryption flags: 0x80 data set encrypted, 0x40 decryption bypassed, 0x20 blocks without prefix, 0x10 archived key",
"SMF14DET": "Encryption type: X'0100' = AES-256",
"SMF14DKL": "Data set encryption key label",
"SMF14FLGS": "Flags: 0x80 BSAM user PGFIX, 0x10 XTIOT, 0x08 DSENCRYPT=OK (EXCP)",
}

DERIVED = {
"dsorg": "Data set organisation as in JCL (PS, PO, DA, IS, CX, AM for VSAM; U suffix when unmovable), from SMF14DCBOR, else JFCDSORG",
"recfm": "Record format as in JCL (F, FB, V, VB, VBS, U, plus A or M for control characters), from SMF14DCBRF, else JFCRECFM",
"disp": "DISP status from JFCBIND2: NEW, MOD, OLD or SHR",
"excp_total": "Sum of SMF14EXCP over all UCB sections: blocks transferred, cumulative for the step",
"nta_total": "Sum of SMF14NTA over all UCB sections: tracks allocated (DASD only)",
"volsers": "Volume serials of the UCB sections (the volumes processed), comma-separated",
}

UNITS = {"sec100": "seconds (stored in hundredths)", "time": "datetime", "date": "date",
         "jfcbdate": "date", "char": "text (EBCDIC)", "uint": "integer"}

missing = []


def table(fields, relative=True):
    head = "Offset" if relative else "Record offset"
    out = [f"| Column | {head} | Len | Type | Description |", "|---|---:|---:|---|---|"]
    for f in fields:
        desc = DESC.get(f.name) or missing.append(f.name) or ""
        out.append(f"| `{f.column}` | {f.offset} | {f.length} | {UNITS[f.kind]} | {desc} |")
    return "\n".join(out)


o = []
o.append("""# SMF types 14 and 15 field reference

<!-- Generated by scripts/gen_smf14_fields_doc.py from src/smfparser/records/type14.py. Do not edit by hand. -->

SMF type 14 is written when a non-VSAM data set (DASD, tape or VIO) opened for INPUT or RDBACK is
closed or reaches end of volume. Type 15 is the same for OUTPUT, UPDAT, INOUT and OUTIN. VSAM
data sets are recorded by type 64 instead, and DD * / SYSOUT data sets are not recorded.

| Type | Table | Contents |
|---:|---|---|
| 14 | `smf14` | One row per input close / EOV |
| 15 | `smf15` | One row per output close / EOV |
| 14 | `smf14_ucb` | One row per volume (UCB section); only with `records: {14: {ucb: true}}` |
| 15 | `smf15_ucb` | One row per volume; only with `records: {15: {ucb: true}}` |
| both | `datasets` | View over `smf14` and `smf15` (database outputs only), see the end of this page |

The two record types have the same layout (IBM maps both with the IFGSMF14 macro), so `smf14` and
`smf15` have the same columns, named after the SMF14 fields. Column names are the IBM field names in
lower case; JFCB fields keep their JFCB names (`jfcbdsnm`, …). The layout follows the z/OS 2.5 SMF
manual and was checked against z/OS 2.5 records. Sections 4, 7 and 9 did not occur in the sample
data and are unverified.

**Things to know**
- If a data set is closed several times in one step, each close writes a record, and the counts
  (EXCP, block count) are **cumulative**. Take the last record per step and DD to avoid
  double counting. The PDSE statistics (type 6 section) are the exception: they are written only
  at close and are not cumulative.
- An end-of-volume record (`smf14rin` bit 0x4000) is written each time a multi-volume data set
  moves to the next volume.
- Text is decoded from EBCDIC with trailing blanks and binary zeros removed. Flag bytes are
  written as integers; their bits are listed in the descriptions.
- Fields that don't apply to a record are empty (NULL): tape fields on DASD records and the
  reverse, and every field of a section the record doesn't contain.

## Common header columns
""")
o.append("| Column | Type | Description |\n|---|---|---|")
for c, dt in HEADER_SCHEMA.items():
    o.append(f"| `{c}` | {dt} | {DESC[c]} |")
o.append("""
## Header, TIOT, JFCB and DCB/DEB sections

Offsets are from the start of the record, RDW included.
""")
o.append(table(t.FIXED.fields, relative=False) + "\n")
o.append("## DCB/DEB tape extension\n\nFilled for tape records (`smf14rin` without the DASD bit 0x2000).\n")
o.append(table(t.DCB_TAPE.fields, relative=False) + "\n")
o.append("## DCB/DEB DASD extension\n\nFilled for DASD records (`smf14rin` bit 0x2000).\n")
o.append(table(t.DCB_DASD.fields, relative=False) + "\n")
o.append("""## Hiperbatch section

Present when `smf14rin` bit 0x0008 is set. Offsets are from the start of the section.
""")
o.append(table(t.HIPERBATCH.fields) + "\n")
o.append("""## Extended information sections

Present when `smf14rin` bit 0x0004 is set (almost every record on current releases). Each section
starts with a 4-byte descriptor holding its length and type (`SMF14STY`). Offsets are from the
start of the section, **including** the descriptor. The IBM manual counts the type 5, 6 and 7
sections from after the descriptor, so their offsets here are 4 higher than in the manual.
""")
for sty, section in t.EXTENDED.items():
    o.append(f"### {section.name[0].upper()}{section.name[1:]}\n")
    o.append(table(section.fields) + "\n")
o.append("## Derived columns\n\nComputed by smfparser from several fields; last in every row.\n")
o.append("| Column | Type | Description |\n|---|---|---|")
for c, dt in t.DERIVED_SCHEMA.items():
    o.append(f"| `{c}` | {dt} | {DERIVED[c]} |")
o.append(f"""
## UCB section: tables `smf14_ucb`, `smf15_ucb`

One row per volume, written only with the `ucb` option. Each row also carries `source_file`,
`record_offset`, `smf_datetime`, {", ".join(f"`{c}`" for c in t.UCB_KEY_COLUMNS)} from the parent
record, and `ucb_index` (the volume's position in the record). `source_file` + `record_offset` join
back to `smf14`/`smf15`. `smf14srtef`/`smf14srteq` apply to tape and `smf14nta` to DASD.
""")
o.append(table(t.UCB.fields) + "\n")
[view] = t.Type14Parser().views()
o.append("""## The `datasets` view

Database outputs get a `datasets` view: `smf14` and `smf15` combined with `UNION ALL`, with readable
column names. `smf_type` tells input (14) from output (15).

| View column | Source column |
|---|---|""")
for alias, expr in view.columns:
    o.append(f"| `{alias}` | `{expr}` |")
o.append("""
Example: the data sets a job wrote, with the last close per DD:

```sql
SELECT stepname, ddname, dsname, MAX(close_time) AS closed, MAX(excp) AS excp
FROM datasets
WHERE jobname = 'MYJOB' AND smf_type = 15
GROUP BY stepname, ddname, dsname;
```
""")
if missing:
    sys.exit(f"missing descriptions: {missing}")
open(sys.argv[1], "w").write("\n".join(o))
