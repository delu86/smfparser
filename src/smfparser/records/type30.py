"""SMF type 30: common address space work (job/step accounting).

Layout per the z/OS SMF30 record mapping (IFASMFR3). Column names are the IBM field names in
lower case so they can be cross-referenced with the manual. Offsets were checked against
sample records (record version '05', z/OS 2.5).

Subtypes: 1 job start, 2 interval, 3 last interval, 4 step end, 5 job end,
6 system address space interval.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .. import decoders as d
from ..layout import Field as F
from ..layout import Section, occurrences, triplet
from ..registry import ParseContext, RecordParser, register
from .header import HEADER_SCHEMA, parse_header

SUBTYPES = (1, 2, 3, 4, 5, 6)

# Triplet locations in the header/self-defining section.
TRIPLET_SUBSYSTEM = 24  # SMF30SOF
TRIPLET_IDENT = 32  # SMF30IOF
TRIPLET_IO = 40  # SMF30UOF
TRIPLET_COMPLETION = 48  # SMF30TOF
TRIPLET_PROCESSOR = 56  # SMF30COF
TRIPLET_ACCOUNTING = 64  # SMF30AOF
TRIPLET_STORAGE = 72  # SMF30ROF
TRIPLET_PERFORMANCE = 80  # SMF30POF
TRIPLET_OPERATOR = 88  # SMF30OOF
TRIPLET_EXCP = 96  # SMF30EOF

SUBSYSTEM = Section("subsystem", (
    F("SMF30TYP", 0, 2),
    F("SMF30RVN", 4, 2, "char"),
    F("SMF30PNM", 6, 8, "char"),
    F("SMF30OSL", 14, 8, "char"),
    F("SMF30SYN", 22, 8, "char"),
    F("SMF30SYP", 30, 8, "char"),
))

IDENT = Section("identification", (
    F("SMF30JBN", 0, 8, "char"),
    F("SMF30PGM", 8, 8, "char"),
    F("SMF30STM", 16, 8, "char"),
    F("SMF30UIF", 24, 8, "char"),
    F("SMF30JNM", 32, 8, "char"),
    F("SMF30STN", 40, 2),
    F("SMF30CLS", 42, 1, "char"),
    F("SMF30JF1", 43, 1),
    F("SMF30PGN", 44, 2),
    F("SMF30JPT", 46, 2),
    F("SMF30STD", 60, 4, "date"),
    F("SMF30SIT", 56, 4, "time", date="SMF30STD"),
    F("SMF30AST", 48, 4, "time", date="SMF30STD", not_before="SMF30SIT"),
    F("SMF30PPS", 52, 4, "time", date="SMF30STD", not_before="SMF30SIT"),
    F("SMF30RSD", 68, 4, "date"),
    F("SMF30RST", 64, 4, "time", date="SMF30RSD"),
    F("SMF30RED", 76, 4, "date"),
    F("SMF30RET", 72, 4, "time", date="SMF30RED"),
    F("SMF30USR", 80, 20, "char"),
    F("SMF30GRP", 100, 8, "char"),
    F("SMF30RUD", 108, 8, "char"),
    F("SMF30TID", 116, 8, "char"),
    F("SMF30TSN", 124, 8, "char"),
    F("SMF30PSN", 132, 8, "char"),
    F("SMF30CL8", 140, 8, "char"),
    F("SMF30ISS", 148, 8, "tod"),
    F("SMF30IET", 156, 8, "tod"),
    F("SMF30SSN", 164, 4),
    F("SMF30EXN", 168, 16, "char"),
    F("SMF30ASI", 184, 2),
    F("SMF30COR", 186, 64, "char"),
))

IO = Section("io", (
    F("SMF30INP", 0, 4),
    F("SMF30TEP", 4, 4),
    F("SMF30TPT", 8, 4),
    F("SMF30TGT", 12, 4),
    F("SMF30RDR", 16, 1),
    F("SMF30RDT", 17, 1),
    F("SMF30TCN", 18, 4, "sec128us"),
    F("SMF30DCF", 22, 4),
    F("SMF30TRR", 28, 4),
    F("SMF30AIC", 32, 4, "sec128us"),
    F("SMF30AID", 36, 4, "sec128us"),
    F("SMF30AIW", 40, 4, "sec128us"),
    F("SMF30AIS", 44, 4),
    F("SMF30EIC", 48, 4, "sec128us"),
    F("SMF30EID", 52, 4, "sec128us"),
    F("SMF30EIW", 56, 4, "sec128us"),
    F("SMF30EIS", 60, 4),
    F("SMF30TEX", 64, 8),
))

COMPLETION = Section("completion", (
    F("SMF30SCC", 0, 2),
    F("SMF30STI", 2, 2),
    F("SMF30ARC", 4, 4),
))

# CPU times are in hundredths of a second, converted to seconds. The zAAP/zIIP family and the
# initiator step-term/init fields are kept as raw binary values until their units are confirmed.
PROCESSOR = Section("processor", (
    F("SMF30PTY", 0, 2),
    F("SMF30TFL", 2, 2),
    F("SMF30CPT", 4, 4, "sec100"),
    F("SMF30CPS", 8, 4, "sec100"),
    F("SMF30ICU", 12, 4, "sec100"),
    F("SMF30ISB", 16, 4, "sec100"),
    F("SMF30JVU", 20, 4, "sec100"),
    F("SMF30IVU", 24, 4, "sec100"),
    F("SMF30JVA", 28, 4, "sec100"),
    F("SMF30IVA", 32, 4, "sec100"),
    F("SMF30IDT", 40, 4, "date"),
    F("SMF30IST", 36, 4, "time", date="SMF30IDT"),
    F("SMF30IIP", 44, 4, "sec100"),
    F("SMF30RCT", 48, 4, "sec100"),
    F("SMF30HPT", 52, 4, "sec100"),
    F("SMF30CSC", 56, 4),
    F("SMF30DMI", 60, 4),
    F("SMF30DMO", 64, 4),
    F("SMF30ASR", 68, 4, "sec100"),
    F("SMF30ENC", 72, 4, "sec100"),
    F("SMF30DET", 76, 4, "sec100"),
    F("SMF30CEP", 80, 4, "sec100"),
    F("SMF30TF2", 84, 1),
    F("SMF30T32", 85, 1),
    F("SMF30T33", 86, 1),
    F("SMF30_TIME_ON_IFA", 88, 4),
    F("SMF30_ENCLAVE_TIME_ON_IFA", 92, 4),
    F("SMF30_DEP_ENCLAVE_TIME_ON_IFA", 96, 4),
    F("SMF30_TIME_IFA_ON_CP", 100, 4),
    F("SMF30_ENCLAVE_TIME_IFA_ON_CP", 104, 4),
    F("SMF30_DEP_ENCLAVE_TIME_IFA_ON_CP", 108, 4),
    F("SMF30CEPI", 112, 4),
    F("SMF30_TIME_ON_ZIIP", 116, 4),
    F("SMF30_ENCLAVE_TIME_ON_ZIIP", 120, 4),
    F("SMF30_DEPENC_TIME_ON_ZIIP", 124, 4),
    F("SMF30_TIME_ZIIP_ON_CP", 128, 4),
    F("SMF30_ENCLAVE_TIME_ZIIP_ON_CP", 132, 4),
    F("SMF30_DEPENC_TIME_ZIIP_ON_CP", 136, 4),
    F("SMF30_ENCLAVE_TIME_ZIIP_QUAL", 140, 4),
    F("SMF30_DEPENC_TIME_ZIIP_QUAL", 144, 4),
    F("SMF30CRP", 148, 4),
    F("SMF30ICU_STEP_TERM", 152, 4),
    F("SMF30ICU_STEP_INIT", 156, 4),
    F("SMF30ISB_STEP_TERM", 160, 4),
    F("SMF30ISB_STEP_INIT", 164, 4),
    F("SMF30_MISSED_SMF30BLK", 168, 4),
    F("SMF30_MISSED_SMF30DCT", 172, 4),
    F("SMF30_HIGHEST_TASK_CPU_PERCENT", 176, 2),
    F("SMF30_HIGHEST_TASK_CPU_PROGRAM", 178, 8, "char"),
))

STORAGE = Section("storage", (
    F("SMF30SFL", 2, 1),
    F("SMF30SPK", 3, 1),
    F("SMF30PRV", 4, 2),
    F("SMF30SYS", 6, 2),
    F("SMF30PGI", 8, 4),
    F("SMF30PGO", 12, 4),
    F("SMF30CPM", 16, 4),
    F("SMF30NSW", 20, 4),
    F("SMF30PSI", 24, 4),
    F("SMF30PSO", 28, 4),
    F("SMF30VPI", 32, 4),
    F("SMF30VPO", 36, 4),
    F("SMF30VPR", 40, 4),
    F("SMF30CPI", 44, 4),
    F("SMF30HPI", 48, 4),
    F("SMF30LPI", 52, 4),
    F("SMF30HPO", 56, 4),
    F("SMF30PST", 60, 4),
    F("SMF30PSC", 64, 8),
    F("SMF30RGB", 72, 4),
    F("SMF30ERG", 76, 4),
    F("SMF30ARB", 80, 4),
    F("SMF30EAR", 84, 4),
    F("SMF30URB", 88, 4),
    F("SMF30EUR", 92, 4),
    F("SMF30RGN", 96, 4),
    F("SMF30DSV", 100, 4),
    F("SMF30PIE", 104, 4),
    F("SMF30POE", 108, 4),
    F("SMF30BIA", 112, 4),
    F("SMF30BOA", 116, 4),
    F("SMF30KIA", 128, 4),
    F("SMF30KOA", 132, 4),
    F("SMF30KIE", 136, 4),
    F("SMF30KOE", 140, 4),
    F("SMF30PSF", 144, 8),
    F("SMF30PAI", 152, 4),
    F("SMF30PEI", 156, 4),
    F("SMF30ERS", 160, 8),
    F("SMF30MEM", 168, 8),
    F("SMF30MES", 176, 1),
    F("SMF30HVR", 184, 8),
    F("SMF30HVA", 192, 8),
    F("SMF30HVO", 200, 8),
    F("SMF30HVH", 208, 8),
    F("SMF30HSO", 216, 8),
    F("SMF30HSH", 224, 8),
))

PERFORMANCE = Section("performance", (
    F("SMF30SRV", 0, 4),
    F("SMF30CSU", 4, 4),
    F("SMF30SRB", 8, 4),
    F("SMF30IO", 12, 4),
    F("SMF30MSO", 16, 4),
    F("SMF30TAT", 20, 4),
    F("SMF30SUS", 24, 4),
    F("SMF30RES", 28, 4),
    F("SMF30TRS", 32, 4),
    F("SMF30WLM", 36, 8, "char"),
    F("SMF30SCN", 44, 8, "char"),
    F("SMF30GRN", 52, 8, "char"),
    F("SMF30RCN", 60, 8, "char"),
    F("SMF30ETA", 68, 4),
    F("SMF30ESU", 72, 4),
    F("SMF30ETC", 76, 4),
    F("SMF30JQT", 96, 4),
    F("SMF30RQT", 100, 4),
    F("SMF30HQT", 104, 4),
    F("SMF30SQT", 108, 4),
    F("SMF30PF1", 112, 1),
    F("SMF30PF2", 113, 1),
    F("SMF30INV", 114, 1),
    F("SMF30ZEP", 115, 1),
    F("SMF30JPN", 116, 8, "char"),
    F("SMF30MSC", 124, 4),
    F("SMF30CPC", 128, 2),
    F("SMF30LOC", 130, 2),
    F("SMF30SRC", 132, 2),
    F("SMF30ZNF", 134, 2),
    F("SMF30SNF", 136, 2),
    F("SMF30SRV_L", 144, 8),
    F("SMF30CSU_L", 152, 8),
    F("SMF30SRB_L", 160, 8),
    F("SMF30IO_L", 168, 8),
    F("SMF30MSO_L", 176, 8),
    F("SMF30ESU_L", 184, 8),
    F("SMF30ACB", 192, 1),
    F("SMF30CR", 193, 1),
    F("SMF30_CAPACITY_CHANGE_CNT", 194, 2),
    F("SMF30_RCTPCPUA_ACTUAL", 196, 4),
    F("SMF30_RCTPCPUA_NOMINAL", 200, 4),
    F("SMF30_RCTPCPUA_SCALING_FACTOR", 204, 4),
    F("SMF30_CAPACITY_ADJUSTMENT_IND", 208, 1),
    F("SMF30_CAPACITY_CHANGE_RSN", 209, 1),
    F("SMF30_CAPACITY_FLAGS", 210, 1),
))

OPERATOR = Section("operator", (
    F("SMF30PDM", 0, 4),
    F("SMF30PRD", 4, 4),
    F("SMF30PTM", 8, 4),
    F("SMF30TPR", 12, 4),
    F("SMF30MTM", 16, 4),
    F("SMF30MSR", 20, 4),
))

EXCP = Section("excp", (
    F("SMF30DEV", 0, 1),
    F("SMF30UTP", 1, 1),
    F("SMF30CUA", 2, 2),
    F("SMF30DDN", 4, 8, "char"),
    F("SMF30BLK", 12, 4),
    F("SMF30BSZ", 16, 2),
    F("SMF30DCT", 18, 4, "sec128us"),
    F("SMF30XBS", 22, 8),
))

# Single-occurrence sections flattened into the per-subtype row, in column order.
FLAT_SECTIONS: tuple[tuple[int, Section], ...] = (
    (TRIPLET_SUBSYSTEM, SUBSYSTEM),
    (TRIPLET_IDENT, IDENT),
    (TRIPLET_IO, IO),
    (TRIPLET_COMPLETION, COMPLETION),
    (TRIPLET_PROCESSOR, PROCESSOR),
    (TRIPLET_STORAGE, STORAGE),
    (TRIPLET_PERFORMANCE, PERFORMANCE),
    (TRIPLET_OPERATOR, OPERATOR),
)

ACCOUNTING_SCHEMA = {"smf30act": "string"}

# Identification columns copied into each EXCP row to make it usable on its own.
EXCP_KEY_COLUMNS = ("smf30jbn", "smf30jnm", "smf30stm", "smf30stn", "smf30pgm")


def decode_accounting(rec: bytes, codepage: str) -> str | None:
    """Accounting fields (SMF30ACL length byte + SMF30ACT text), comma-joined as in JCL."""
    t = triplet(rec, TRIPLET_ACCOUNTING)
    if t.count == 0:
        return None
    pos, end = t.offset, min(t.offset + t.length, len(rec))
    values = []
    for _ in range(t.count):
        if pos >= end:
            break
        n = rec[pos]
        values.append(d.ebcdic(rec[pos + 1 : pos + 1 + n], codepage))
        pos += 1 + n
    return ",".join(values)


@register
class Type30Parser(RecordParser):
    record_type = 30

    def table_name(self, subtype: int) -> str:
        return f"smf30_{subtype}"

    def _row_schema(self) -> dict[str, str]:
        schema = dict(HEADER_SCHEMA)
        for _, section in FLAT_SECTIONS:
            schema.update(section.schema())
        schema.update(ACCOUNTING_SCHEMA)
        return schema

    def schemas(self) -> dict[str, dict[str, str]]:
        row = self._row_schema()
        tables = {self.table_name(st): row for st in SUBTYPES}
        if self.options.get("excp", False):
            excp = {c: row[c] for c in ("source_file", "record_offset", "smf_datetime", "smf_subtype")}
            excp.update({c: row[c] for c in EXCP_KEY_COLUMNS})
            excp["excp_index"] = "Int64"
            excp.update(EXCP.schema())
            tables["smf30_excp"] = excp
        return tables

    def parse(self, rec: bytes, ctx: ParseContext) -> Iterator[tuple[str, dict[str, Any]]]:
        row = parse_header(rec, ctx.codepage, ctx.source_file, ctx.offset)
        subtype = row["smf_subtype"]
        if subtype not in SUBTYPES:
            raise ValueError(f"unsupported SMF 30 subtype {subtype}")
        for at, section in FLAT_SECTIONS:
            t = triplet(rec, at)
            start = next(occurrences(rec, t), None)
            row.update(section.empty() if start is None else section.decode(rec, start, t.length, ctx.codepage))
        row["smf30act"] = decode_accounting(rec, ctx.codepage)
        yield self.table_name(subtype), row

        if self.options.get("excp", False):
            t = triplet(rec, TRIPLET_EXCP)
            for i, start in enumerate(occurrences(rec, t)):
                excp = {c: row[c] for c in ("source_file", "record_offset", "smf_datetime", "smf_subtype")}
                excp.update({c: row[c] for c in EXCP_KEY_COLUMNS})
                excp["excp_index"] = i
                excp.update(EXCP.decode(rec, start, t.length, ctx.codepage))
                yield "smf30_excp", excp
