# SMF input format

SMF writes binary, variable-length records. To parse them off the mainframe, the bytes must arrive
unchanged and the record boundaries must be kept. This page explains what smfparser expects and
how records are laid out.

## Getting the data off z/OS

1. **Dump the records to a sequential dataset.** Use `IFASMFDP` (SMF datasets) or `IFASMFDL`
   (log streams). The output has `RECFM=VBS`, usually with `LRECL=32760`.
2. **Transfer the dataset in binary mode, keeping the length prefixes.** Do not convert
   EBCDIC to ASCII; text is decoded by the parser.

smfparser reads both layouts a binary transfer can produce and **detects which one it has**:

| Layout | What the file contains | Typical way to produce it |
|---|---|---|
| Blocked | Every block starts with a 4-byte **BDW**, followed by RDW-prefixed segments | Transfer the dataset as undefined-format (RECFM=U) blocks, e.g. read it with a RECFM=U DCB override, or copy it to a RECFM=U dataset before transferring |
| Unblocked | RDW-prefixed segments back to back, with no BDWs | FTP in binary mode with `quote site rdw` (z/OS FTP server) |

A plain binary FTP *without* `site rdw` strips the length prefixes. Such a file cannot be parsed:
nothing marks where one record ends and the next begins. Run `smfparser stats` on a new file
first. A healthy file shows plausible record types and 0 orphan or truncated segments.

The sample dumps in `smf_files/` use the blocked layout.

## Physical structure

```
Blocked:   [BDW][RDW seg][RDW seg]…  [BDW][RDW seg]…
Unblocked: [RDW seg][RDW seg][RDW seg]…

BDW (4 bytes)  bytes 0-1  block length, including the BDW (big-endian)
               bytes 2-3  zero  (if bit 0 of byte 0 is set: extended BDW, 31-bit length in bytes 0-3)
RDW (4 bytes)  bytes 0-1  segment length, including the RDW
               byte  2    segment code: 0 complete, 1 first, 3 middle, 2 last
               byte  3    zero
```

**Spanned records.** A record longer than the space left in a block is split into segments: one
*first*, any number of *middle*, and one *last*. The reader joins them and gives the record a
fresh RDW. Offsets inside a record therefore always match IBM's documentation, which counts
the 4-byte RDW as offset 0. In the sample data about 5% of records are spanned, mostly large
type 30 interval records with many EXCP entries.

A segment out of sequence (a *middle* or *last* with no *first*, or a *first* that never
completes) is counted as an orphan and dropped. An invalid length ends the current block, or
the whole file in the unblocked layout, and is counted as truncated.

## Standard record header

Every SMF record starts with the same header. Offsets include the RDW:

| Offset | Len | Field | Format |
|---:|---:|---|---|
| 0 | 2 | Record length | binary |
| 2 | 2 | Segment descriptor | binary |
| 4 | 1 | Flag. Bit `x'40'`: the record has subtypes (extended header) | binary |
| 5 | 1 | Record type | binary |
| 6 | 4 | Time written, in hundredths of a second since midnight (local) | binary |
| 10 | 4 | Date written, `0cyydddF` | packed |
| 14 | 4 | System ID (SID) | EBCDIC |
| 18 | 4 | Subsystem ID, e.g. `JES2`, `STC` (extended header only) | EBCDIC |
| 22 | 2 | Subtype (extended header only) | binary |

Records without the `x'40'` flag, such as types 2 and 3, end their header at offset 18 and have
no subtype. `stats` shows their subtype as `-`.

## Self-defining sections

Most modern record types, including type 30, follow the header with **triplets**. Each triplet
describes one section:

```
offset (4 bytes)  from the start of the record, RDW included
length (2 bytes)  length of one occurrence
count  (2 bytes)  number of occurrences (0 = section absent)
```

Sections are located only through their triplets, never at fixed positions, so the record's
layout can change between z/OS releases without breaking parsers. A section can also be longer
than the fields smfparser knows about (newer release) or shorter (older release). Unknown trailing
bytes are ignored. Known fields that lie past the end of the section come out empty.

## Data formats

| Format | Encoding | How smfparser decodes it |
|---|---|---|
| Binary | Unsigned big-endian integer | `int` |
| EBCDIC | Text in an EBCDIC code page | `str` (code page from config; trailing blanks and `x'00'` removed) |
| Packed decimal | 2 digits per byte, sign in the last nibble (`C`/`F` +, `D`/`B` −) | `int` |
| SMF date | Packed `0cyydddF`: `c` century (0 = 19xx, 1 = 20xx), `yy` year, `ddd` day of the year | `date` (zero means none) |
| Time of day | Binary hundredths of a second since midnight | combined with its date into a `datetime` |
| TOD clock (STCK) | 64-bit; bit 51 = 1 microsecond; epoch 1900-01-01 | `datetime`. Usually UTC, unlike the header time, which is local |
| Durations | Binary in hundredths of a second, or 128 µs units | seconds (`float`) |
