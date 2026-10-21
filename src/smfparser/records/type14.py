"""SMF types 14 and 15: non-VSAM data set activity.

Type 14 is written when a data set opened for INPUT or RDBACK is closed or reaches end of volume;
type 15 for OUTPUT, UPDAT, INOUT or OUTIN. Both have the same layout (IBM maps them with the one
IFGSMF14 macro), so both tables use the SMF14 field names. Layout per the z/OS 2.5 SMF manual,
checked against sample records. The records have no subtype.

A record is a fixed part (header, TIOT, JFCB, DCB/DEB) followed by SMF14NUC UCB sections (one
per volume), an optional Hiperbatch section and an optional extended information segment made
of self-describing sections (SMF14ESL length, SMF14STY type).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .. import decoders as d
from ..layout import Field as F
from ..layout import Section
from ..registry import ParseContext, RecordParser, register
from ..views import View
from .header import HEADER_SCHEMA, parse_header

# Offsets from the start of the record (RDW included).
DCB_DEB = 244  # start of the DCB/DEB section; UCB sections follow its SMF14SDC bytes

# SMF14RIN bits
RIN_DASD = 0x2000  # SMF14DAD
RIN_HIPERBATCH = 0x0008  # SMF14HBT
RIN_EXTENDED = 0x0004  # SMF14XSG

HIPERBATCH_LENGTH = 20

# Header, TIOT, JFCB and DCB/DEB sections, located from the start of the record.
FIXED = Section("fixed", (
    F("SMF14JBN", 18, 8, "char"),
    F("SMF14RSD", 30, 4, "date"),
    F("SMF14RST", 26, 4, "time", date="SMF14RSD"),
    F("SMF14UID", 34, 8, "char"),
    F("SMF14RIN", 42, 2),
    F("SMF14SDC", 44, 1),
    F("SMF14NUC", 45, 1),
    F("SMF14SUC", 46, 1),
    F("SMF14SET", 47, 1),
    F("SMF14OPD", 268, 4, "date"),
    F("SMF14OPE", 48, 4, "time", date="SMF14OPD"),
    # TIOT
    F("SMF14TIOE1", 52, 1),
    F("SMF14TIOE2", 53, 1),
    F("SMF14TIOE3", 54, 1),
    F("SMF14TIOE4", 55, 1),
    F("SMF14TIOE5", 56, 8, "char"),
    F("SMF14TIOE7", 67, 1),
    # JFCB (176 bytes from offset 68), JFCB field names
    F("JFCBDSNM", 68, 44, "char"),
    F("JFCBELNM", 112, 8, "char"),
    F("JFCBTSDM", 120, 1),
    F("JFCBLTYP", 134, 1),
    F("JFCBFLSQ", 136, 2),
    F("JFCBVLSQ", 138, 2),
    F("JFCBCRDT", 148, 3, "jfcbdate"),
    F("JFCBXPDT", 151, 3, "jfcbdate"),
    F("JFCBIND1", 154, 1),
    F("JFCBIND2", 155, 1),
    F("JFCBUFNO", 156, 1),
    F("JFCBUFL", 158, 2),
    F("JFCDSORG", 166, 2),
    F("JFCRECFM", 168, 1),
    F("JFCOPTCD", 169, 1),
    F("JFCBLKSI", 170, 2),
    F("JFCLRECL", 172, 2),
    F("JFCBNVOL", 185, 1),
    F("JFCBVOL1", 186, 6, "char"),
    F("JFCBVOL2", 192, 6, "char"),
    F("JFCBVOL3", 198, 6, "char"),
    F("JFCBVOL4", 204, 6, "char"),
    F("JFCBVOL5", 210, 6, "char"),
    F("JFCBPQTY", 220, 3),
    F("JFCBCTRI", 223, 1),
    F("JFCBSQTY", 224, 3),
    F("JFCBDQTY", 228, 3),
    F("JFCBVLCT", 242, 1),
    # DCB/DEB
    F("SMF14DCBOR", 244, 2),
    F("SMF14DCBRF", 246, 1),
    F("SMF14DCBMF", 247, 2),
    F("SMF14DCBFL", 249, 1),
    F("SMF14DCBOP", 250, 1),
    F("SMF14DEBFL", 252, 1),
    F("SMF14DEBOP", 253, 1),
    F("SMF14DEBVL", 254, 2),
))

# The 12 bytes after SMF14DEBVL differ for tape and DASD (SMF14RIN bit SMF14DAD).
DCB_TAPE = Section("dcb_tape", (
    F("SMF14DCBBL", 256, 4),
    F("SMF14DSSNO", 260, 6, "char"),
    F("SMF14TDA", 267, 1),
))

DCB_DASD = Section("dcb_dasd", (
    F("SMF14NTU", 256, 4),
    F("SMF14NTR", 260, 4),
    F("SMF14NER", 264, 1),
    F("SMF14EDI", 265, 1),
    F("SMF14FG1", 266, 1),
))

UCB = Section("ucb", (
    F("SMF14UCBDV", 0, 2),
    F("SMF14SRTEV", 2, 6, "char"),
    F("SMF14UCBTY", 8, 4),
    F("SMF14SRTES", 12, 1),
    F("SMF14NEX", 13, 1),
    F("SMF14EXCP", 16, 4),
    # tape extension
    F("SMF14SRTEF", 20, 2),
    F("SMF14SRTEQ", 22, 2),
    # DASD extension (overlays the tape one)
    F("SMF14NTA", 20, 4),
))
UCB_TAPE_ONLY = ("smf14srtef", "smf14srteq")
UCB_DASD_ONLY = ("smf14nta",)

HIPERBATCH = Section("hiperbatch", (
    F("SMF14IOREQ", 0, 4),
    F("SMF14CHITS", 4, 4),
    F("SMF14NMWTS", 8, 4),
    F("SMF14PHIOS", 12, 4),
    F("SMF14CIOS", 16, 4),
))

# Extended information sections. Offsets are from the start of the section, including its 4-byte
# descriptor (SMF14ESL, reserved byte, SMF14STY); the manual counts types 5, 6 and 7 from after it.
EXT_COMPRESSED = Section("compressed format data set (type 1)", (
    F("SMF14XF1", 4, 1),
    F("SMF14XF2", 5, 1),
    F("SMF14CDL", 6, 8),
    F("SMF14UDL", 14, 8),
    F("SMF14CDS", 22, 8),
    F("SMF14UDS", 30, 8),
    F("SMF14CIS", 38, 4),
    F("SMF14CMPTYPE", 80, 1),
))

EXT_SMS = Section("SMS class (type 2)", (
    F("SMF14MCN", 4, 8, "char"),
    F("SMF14DCN", 12, 8, "char"),
    F("SMF14SCN", 20, 8, "char"),
))

EXT_STEP = Section("step information (type 3)", (
    F("SMF14SPN", 4, 8, "char"),
    F("SMF14PGN", 12, 8, "char"),
    F("SMF14JOBID", 20, 8, "char"),
    F("SMF14PLXID", 28, 8, "char"),
))

EXT_CCSID = Section("ISO/ANSI V4 CCSID (type 4)", (
    F("SMF14CFG", 4, 1),
    F("SMF14USR", 5, 4),
    F("SMF14TPE", 9, 4),
    F("SMF14LBL", 13, 4),
))

EXT_ADDITIONAL = Section("additional data set characteristics (type 5)", (
    F("SMF14BFG", 4, 2),
    F("SMF14LBS", 6, 8),
    F("SMF14FLG1", 14, 1),
    F("SMF14FLG2", 15, 1),
    F("SMF14DSVER", 16, 1),
    F("SMF14ALI", 17, 44, "char"),
))

EXT_PDSE = Section("PDSE statistics (type 6)", (
    F("SMF14DRD", 4, 4),
    F("SMF14DRDH", 8, 4),
    F("SMF14MRD", 12, 4),
    F("SMF14MRDH", 16, 4),
    F("SMF14MCE", 20, 4),
    F("SMF14MST", 24, 4),
    F("SMF14MNC", 28, 4),
    F("SMF14MCF", 32, 4),
))

EXT_TAPE_ENCRYPTION = Section("tape encryption (type 7)", (
    F("SMF14KL1", 4, 64, "char"),
    F("SMF14CD1", 68, 1, "char"),
    F("SMF14KL2", 69, 64, "char"),
    F("SMF14CD2", 133, 1, "char"),
    F("SMF14KET", 134, 4, "sec100"),
))

EXT_RAS = Section("RAS (type 8)", (
    F("SMF14RFG0", 4, 1),
    F("SMF14RFG1", 5, 1),
    F("SMF14RASDATA0", 8, 1),
    F("SMF14RASDATA1", 9, 1),
))

EXT_DASD_ENCRYPTION = Section("DASD data set encryption (type 9)", (
    F("SMF14DEF", 4, 1),
    F("SMF14DET", 5, 2),
    F("SMF14DKL", 7, 64, "char"),
    F("SMF14FLGS", 71, 1),
))

# SMF14STY -> section, in column order.
EXTENDED: dict[int, Section] = {
    1: EXT_COMPRESSED,
    2: EXT_SMS,
    3: EXT_STEP,
    4: EXT_CCSID,
    5: EXT_ADDITIONAL,
    6: EXT_PDSE,
    7: EXT_TAPE_ENCRYPTION,
    8: EXT_RAS,
    9: EXT_DASD_ENCRYPTION,
}

# Columns derived from several fields.
DERIVED_SCHEMA = {
    "dsorg": "string",
    "recfm": "string",
    "disp": "string",
    "excp_total": "Int64",
    "nta_total": "Int64",
    "volsers": "string",
}

# Columns copied from the record into each UCB row.
UCB_KEY_COLUMNS = ("smf14jbn", "smf14tioe5", "jfcbdsnm", "smf14spn", "smf14jobid")


def dsorg(value: int | None) -> str | None:
    """DCBDSORG / JFCDSORG as in JCL: PS, PO, DA, IS, CX, AM (VSAM); U suffix if unmovable."""
    if not value:
        return None
    hi, lo = value >> 8, value & 0xFF
    for bit, name in ((0x80, "IS"), (0x40, "PS"), (0x20, "DA"), (0x10, "CX"), (0x02, "PO")):
        if hi & bit:
            return name + ("U" if hi & 0x01 else "")
    if lo & 0x08:
        return "AM"
    return None


def recfm(value: int | None) -> str | None:
    """DCBRECFM / JFCRECFM as in JCL, e.g. FB, VBS, FBA, U."""
    if not value:
        return None
    out = {0xC0: "U", 0x80: "F", 0x40: "V"}.get(value & 0xC0, "")
    if value & 0x10:
        out += "B"
    if value & 0x08:
        out += "S"
    if value & 0x04:
        out += "A"
    elif value & 0x02:
        out += "M"
    return out or None


def disp(ind2: int | None) -> str | None:
    """Status part of DISP= from JFCBIND2: NEW, MOD, OLD or SHR."""
    if ind2 is None:
        return None
    status = {0xC0: "NEW", 0x80: "MOD", 0x40: "OLD"}.get(ind2 & 0xC0)
    if status == "OLD" and ind2 & 0x08:
        return "SHR"
    return status


def extended_sections(rec: bytes, start: int) -> Iterator[tuple[int, int, int]]:
    """(SMF14STY, start, length) of each section in the extended information segment at `start`."""
    if start + 2 > len(rec):
        return
    end = min(start + d.uint(rec[start : start + 2]), len(rec))
    pos = start + 2
    while pos + 4 <= end:
        length = d.uint(rec[pos : pos + 2])
        if length < 4:
            return
        yield rec[pos + 3], pos, min(length, end - pos)
        pos += length


def _datasets_view(table_14: str, table_15: str) -> View:
    return View("datasets", (table_14, table_15), (
        ("system", "smf_sid"),
        ("smf_type", "smf_type"),
        ("jobname", "smf14jbn"),
        ("jobid", "smf14jobid"),
        ("stepname", "smf14spn"),
        ("program", "smf14pgn"),
        ("ddname", "smf14tioe5"),
        ("dsname", "jfcbdsnm"),
        ("member", "jfcbelnm"),
        ("open_time", "smf14ope"),
        ("close_time", "smf_datetime"),
        ("dsorg", "dsorg"),
        ("recfm", "recfm"),
        ("lrecl", "jfclrecl"),
        ("blksize", "jfcblksi"),
        ("disp", "disp"),
        ("volsers", "volsers"),
        ("excp", "excp_total"),
        ("tracks_allocated", "nta_total"),
        ("storclas", "smf14scn"),
        ("mgmtclas", "smf14mcn"),
        ("dataclas", "smf14dcn"),
    ))


class DatasetActivityParser(RecordParser):
    """Shared parser for types 14 and 15; subclasses set record_type."""

    @property
    def table(self) -> str:
        return f"smf{self.record_type}"

    @property
    def ucb_table(self) -> str:
        return f"smf{self.record_type}_ucb"

    def _row_schema(self) -> dict[str, str]:
        schema = dict(HEADER_SCHEMA)
        for section in (FIXED, DCB_TAPE, DCB_DASD, HIPERBATCH, *EXTENDED.values()):
            schema.update(section.schema())
        schema.update(DERIVED_SCHEMA)
        return schema

    def _ucb_schema(self) -> dict[str, str]:
        row = self._row_schema()
        schema = {c: row[c] for c in ("source_file", "record_offset", "smf_datetime", *UCB_KEY_COLUMNS)}
        schema["ucb_index"] = "Int64"
        schema.update(UCB.schema())
        return schema

    def schemas(self) -> dict[str, dict[str, str]]:
        tables = {self.table: self._row_schema()}
        if self.options.get("ucb", False):
            tables[self.ucb_table] = self._ucb_schema()
        return tables

    def parse(self, rec: bytes, ctx: ParseContext) -> Iterator[tuple[str, dict[str, Any]]]:
        if len(rec) < DCB_DEB:
            raise ValueError(f"record too short ({len(rec)} bytes)")
        row = parse_header(rec, ctx.codepage, ctx.source_file, ctx.offset)
        sdc, nuc, suc = rec[44], rec[45], rec[46]
        row.update(FIXED.decode(rec, 0, DCB_DEB + sdc, ctx.codepage))
        rin = row["smf14rin"]
        dasd = bool(rin & RIN_DASD)
        for section, applies in ((DCB_TAPE, not dasd), (DCB_DASD, dasd)):
            row.update(section.decode(rec, 0, DCB_DEB + sdc, ctx.codepage) if applies else section.empty())

        pos = DCB_DEB + sdc
        ucbs = []
        for _ in range(nuc):
            if suc == 0 or pos + suc > len(rec):
                break
            ucb = UCB.decode(rec, pos, suc, ctx.codepage)
            for c in UCB_TAPE_ONLY if dasd else UCB_DASD_ONLY:
                ucb[c] = None
            ucbs.append(ucb)
            pos += suc
        pos += rec[47]  # ISAM extension section (SMF14SET; always 0 on current releases)

        if rin & RIN_HIPERBATCH:
            row.update(HIPERBATCH.decode(rec, pos, HIPERBATCH_LENGTH, ctx.codepage))
            pos += HIPERBATCH_LENGTH
        else:
            row.update(HIPERBATCH.empty())

        found: dict[int, dict[str, Any]] = {}
        if rin & RIN_EXTENDED:
            for sty, start, length in extended_sections(rec, pos):
                if sty in EXTENDED and sty not in found:
                    found[sty] = EXTENDED[sty].decode(rec, start, length, ctx.codepage)
        for sty, section in EXTENDED.items():
            row.update(found.get(sty) or section.empty())

        row["dsorg"] = dsorg(row["smf14dcbor"]) or dsorg(row["jfcdsorg"])
        row["recfm"] = recfm(row["smf14dcbrf"]) or recfm(row["jfcrecfm"])
        row["disp"] = disp(row["jfcbind2"])
        row["excp_total"] = sum(u["smf14excp"] or 0 for u in ucbs) if ucbs else None
        row["nta_total"] = sum(u["smf14nta"] or 0 for u in ucbs) if dasd and ucbs else None
        row["volsers"] = ",".join(u["smf14srtev"] for u in ucbs if u["smf14srtev"]) or None
        yield self.table, row

        if self.options.get("ucb", False):
            for i, ucb in enumerate(ucbs):
                out = {c: row[c] for c in ("source_file", "record_offset", "smf_datetime", *UCB_KEY_COLUMNS)}
                out["ucb_index"] = i
                out.update(ucb)
                yield self.ucb_table, out


@register
class Type14Parser(DatasetActivityParser):
    record_type = 14

    def views(self) -> tuple[View, ...]:
        # The datasets view spans both types; type 14 owns it.
        return (_datasets_view("smf14", "smf15"),)


@register
class Type15Parser(DatasetActivityParser):
    record_type = 15
