"""SMF type 113: hardware capacity, reporting and statistics (CPU-measurement facility counters).

Written by HIS (hardware instrumentation services) once per CPU each collection interval.
Subtype 1 holds counter deltas since the previous record (the IBM-recommended subtype); subtype 2
holds the counters' absolute values and only the basic, problem-state, crypto and extended sets.
Layout per the z/OS 2.5 SMF manual, checked against sample records.

A record is the standard header, a self-defining section with triplets for the subsystem,
identification and data sections, then the data section: a subtype header, counter set
descriptors located by a triplet in that header, and the counters themselves. Counter slot n of a
set is counter number base + n of the CPU-measurement facility (basic 0, problem-state 32, crypto
64, extended 128, MT-diagnostic 448). Extended counters are machine-model dependent; IBM documents
them per model in SA23-2261.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from .. import decoders as d
from ..decoders import QUARTER_HOUR, whole_quarters
from ..layout import Field as F
from ..layout import Section, occurrences, triplet
from ..registry import ParseContext, RecordParser, register
from ..views import View
from .header import HEADER_SCHEMA, parse_header

log = logging.getLogger(__name__)

SUBTYPES = (1, 2)

# Triplets in the self-defining section, offsets from the start of the record (RDW included).
TRIPLET_SUBSYSTEM = 28
TRIPLET_IDENTIFICATION = 36
TRIPLET_DATA = 44

SUBSYSTEM = Section("subsystem", (
    F("SMF113RVN", 2, 2, "char"),
    F("SMF113PNM", 4, 8, "char"),
    F("SMF113OSL", 12, 8, "char"),
))

IDENTIFICATION = Section("identification", (
    F("SMF113JBN", 0, 8, "char"),
    F("SMF113RSD", 12, 4, "date"),
    F("SMF113RST", 8, 4, "time", date="SMF113RSD"),
    F("SMF113STP", 16, 8, "char"),
    F("SMF113IntervalStart", 24, 8, "tod"),
    F("SMF113IntervalEnd", 32, 8, "tod"),
))

# Subtype headers, offsets from the start of the data section (SMF113DOF). The counter set
# triplet (SMF113_1_CSOF / SMF113_2_CSOF) is read separately.
DATA_1 = Section("subtype 1 data", (
    F("SMF113_1_CTS", 0, 8, "tod"),
    F("SMF113_1_CTM", 8, 8, "tod"),
    F("SMF113_1_CpuId", 16, 2),
    F("SMF113_1_CpuProcClass", 18, 1),
    F("SMF113_1_CpuSpeed", 20, 4),
    F("SMF113_1_MachType", 24, 4, "char"),
    F("SMF113_1_MachModel", 28, 16, "char"),
    F("SMF113_1_CtrVersion0", 44, 2),
    F("SMF113_1_CtrVersion1", 46, 2),
    F("SMF113_1_CtrVersion2", 48, 2),
    F("SMF113_1_Flags", 50, 2),
    F("SMF113_1_MachSeqCode", 60, 16, "char"),
    F("SMF113_1_CoreId", 76, 2),
))
CS_TRIPLET_1 = 52

DATA_2 = Section("subtype 2 data", (
    F("SMF113_2_CTS", 0, 8, "tod"),
    F("SMF113_2_CTM", 8, 8, "tod"),
    F("SMF113_2_CpuProcClass", 17, 1),
    F("SMF113_2_CF", 18, 2),
    F("SMF113_2_CTRVN1", 20, 2),
    F("SMF113_2_CTRVN2", 22, 2),
    F("SMF113_2_CPSP", 40, 4),
    F("SMF113_2_MachType", 44, 4, "char"),
    F("SMF113_2_MachModel", 48, 16, "char"),
    F("SMF113_2_CpuId", 64, 2),
    F("SMF113_2_MachSeqCode", 68, 16, "char"),
))
CS_TRIPLET_2 = 24
COUNTERS_TRIPLET_2 = 32  # SMF113_2_CDOF: the counters of every set, contiguous in set order

DATA = {1: DATA_1, 2: DATA_2}

# Counter set type (SMF113_1_CSType / SMF113_2_CST) -> (column prefix, first counter number,
# counter columns). The columns cover what a z15 records (MT-diagnostic: 9, with room to spare);
# extra counters are only in the counters table. The z/OS counter set (5) has no counter numbers.
COUNTER_SETS: dict[int, tuple[str, int | None, int]] = {
    1: ("basic", 0, 6),
    2: ("problem", 32, 6),
    3: ("crypto", 64, 20),
    4: ("extended", 128, 160),
    5: ("zos", None, 0),
    6: ("mtdiag", 448, 16),
}

PROC_CLASSES = {0: "CP", 2: "zAAP", 4: "zIIP"}

COUNTER_SCHEMA = {
    f"{prefix}_{base + i}": "Int64" for prefix, base, n in COUNTER_SETS.values() if base is not None for i in range(n)
}
DERIVED_SCHEMA = {"cpu_type": "string", "duration_sec": "Float64"}

# Columns copied from the record into each counters-table row, after the CPU ID (cpu_id).
COUNTER_KEY_COLUMNS = ("source_file", "record_offset", "smf_datetime", "smf_sid", "cpu_type",
                       "smf113intervalstart", "smf113intervalend")
COUNTER_ROW_SCHEMA = {
    "cpu_id": "Int64", "counter_set": "string", "counter_index": "Int64", "counter_number": "Int64",
    "counter_value": "Int64",
}

# CPU MF metrics, from IBM's "CPU MF Formulas" (WSC, April 2025). The L1 miss sourcing counters
# and the RNI weights depend on the machine generation, given by SMF113_1_CtrVersion2.
# Generation -> (machine, extended counters for L2P, L3P, L4LP, L4RP, MEMP,
# RNI = k * (a*L3P + b*L4LP + c*L4RP + d*MEMP) / 100 as (k, a, b, c, d)).
Counters = tuple[int, ...]
GENERATIONS: dict[int, tuple[str, Counters, Counters, Counters, Counters, Counters, tuple[float, ...]]] = {
    4: ("z13", (133, 136), (144, 145, 162, 163), (146, 147, 148, 164, 165, 166),
        (*range(149, 158), *range(167, 176)), (158, 159, 160, 161, 176, 177, 178, 179), (2.3, 0.4, 1.6, 3.5, 7.5)),
    5: ("z14", (133, 136), (144, 146, 162, 164), (147, 149, 156, 165, 167, 174, 150, 152, 158, 168, 170),
        (153, 155, 157, 171, 173, 175), (145, 148, 151, 154, 163, 166, 169, 172), (2.4, 0.4, 1.5, 3.2, 7.0)),
    6: ("z15", (133, 136), (144, 146, 162, 164), (147, 149, 156, 165, 167, 174, 150, 152, 158, 168, 170),
        (153, 155, 157, 171, 173, 175), (145, 148, 151, 154, 163, 166, 169, 172), (2.9, 0.45, 1.5, 3.2, 6.5)),
    7: ("z16", (145, 146, 169, 170), (147, 149, 150, 151, 171, 173, 174, 175),
        (148, 152, 153, 154, *range(160, 166), 172, 176, 177, 178), (155, 166, 167, 168, 179),
        (156, 157, 158, 159, 180, 181, 182, 183), (4.1, 0.45, 1.3, 5.0, 6.1)),
    8: ("z17", (145, 146, 169, 170), (147, 149, 150, 151, 171, 173, 174, 175),
        (148, 152, 153, 154, *range(160, 166), 172, 176, 177, 178), (155, 166, 167, 168, 179),
        (156, 157, 158, 159), (4.7, 0.45, 1.2, 4.5, 6.0)),
}
SOURCING = ("l2p", "l3p", "l4lp", "l4rp", "memp")


def _metrics(agg: bool) -> tuple[tuple[str, str], ...]:
    """(alias, SQL) of the CPU MF metrics, per row or (agg) over a group of rows."""
    def c(col: str) -> str:
        return f"SUM({col})" if agg else col

    def per_100(num: str, den: str) -> str:
        return f"100.0 * {num} / NULLIF({den}, 0)"

    def by_generation(sql: dict[int, str]) -> str:
        whens = " ".join(f"WHEN {g} THEN {e}" for g, e in sql.items())
        return f"CASE smf113_1_ctrversion2 {whens} END"

    l1_misses = f"{c('basic_2')} + {c('basic_4')}"
    sourcing = {g: {name: per_100("(" + " + ".join(c(f"extended_{n}") for n in counters) + ")", l1_misses)
                    for name, counters in zip(SOURCING, gen[1:6])} for g, gen in GENERATIONS.items()}
    rni = {}
    for g, gen in GENERATIONS.items():
        k, *weights = gen[6]
        terms = " + ".join(f"{w} * {sourcing[g][name]}" for w, name in zip(weights, SOURCING[1:]))
        rni[g] = f"{k} * ({terms}) / 100"
    busy = "1.0 * basic_0 / (smf113_1_cpuspeed * 1000000.0)"  # seconds the CPU was dispatched
    return (
        ("cpi", f"1.0 * {c('basic_0')} / NULLIF({c('basic_1')}, 0)"),
        ("prbstate", per_100(c("problem_33"), c("basic_1"))),
        ("l1mp", per_100(f"({l1_misses})", c("basic_1"))),
        *((name, by_generation({g: s[name] for g, s in sourcing.items()})) for name in SOURCING),
        ("rni", by_generation(rni)),
        ("lparcpu", f"100.0 * {c(busy)} / NULLIF(duration_sec, 0)"),
    )


CPU_KEYS = (
    ("system", "smf_sid"),
    ("interval_start", "smf113intervalstart"),
    ("interval_end", "smf113intervalend"),
    ("duration_sec", "duration_sec"),
)
MACHINE = (
    ("cpu_type", "cpu_type"),
    ("machine_type", "smf113_1_machtype"),
    ("machine_model", "smf113_1_machmodel"),
    ("counter_version", "smf113_1_ctrversion2"),
)
VIEWS = (
    View("cpu_metrics", ("smf113_1",), (
        *CPU_KEYS,
        ("cpu_id", "smf113_1_cpuid"),
        ("core_id", "smf113_1_coreid"),
        *MACHINE,
        ("cpu_speed", "smf113_1_cpuspeed"),
        ("cycles", "basic_0"),
        ("instructions", "basic_1"),
        *_metrics(agg=False),
    )),
    View("cpu_type_metrics", ("smf113_1",), (
        *CPU_KEYS,
        *MACHINE,
        ("cpus", "COUNT(*)"),
        ("cycles", "SUM(basic_0)"),
        ("instructions", "SUM(basic_1)"),
        *_metrics(agg=True),
    ), group_by=", ".join(expr for _, expr in (*CPU_KEYS, *MACHINE))),
)


def counter_sets(rec: bytes, data: int, subtype: int) -> Iterator[tuple[int, list[int]]]:
    """(counter set type, counter values in slot order) for each counter set of the record."""
    if subtype == 1:
        for start in occurrences(rec, triplet(rec, data + CS_TRIPLET_1)):
            # SMF113_1_CDLN is the width of one counter: 8 (SMF113_1_LCR) or 4 (SMF113_1_SCR).
            values = triplet(rec, start + 4)
            yield d.uint(rec[start : start + 2]), [
                d.uint(rec[at : at + values.length]) for at in occurrences(rec, values)]
        return
    counters = triplet(rec, data + COUNTERS_TRIPLET_2)
    pos = counters.offset
    for start in occurrences(rec, triplet(rec, data + CS_TRIPLET_2)):
        n = d.uint(rec[start + 2 : start + 4])  # SMF113_2_CSN
        end = min(pos + n * counters.length, len(rec))
        yield rec[start], [d.uint(rec[at : at + counters.length]) for at in range(pos, end, counters.length)]
        pos += n * counters.length


@register
class Type113Parser(RecordParser):
    record_type = 113

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._utc_offsets: dict[str, timedelta] = {}  # system -> local time minus UTC, last seen
        self._warned_unmapped: set[tuple[int, int]] = set()

    def views(self) -> tuple[View, ...]:
        return VIEWS

    def _row_schema(self, subtype: int) -> dict[str, str]:
        schema = dict(HEADER_SCHEMA)
        for section in (SUBSYSTEM, IDENTIFICATION, DATA[subtype]):
            schema.update(section.schema())
        schema.update(COUNTER_SCHEMA)
        schema.update(DERIVED_SCHEMA)
        return schema

    def _counter_schema(self, subtype: int) -> dict[str, str]:
        row = self._row_schema(subtype)
        return {c: row[c] for c in COUNTER_KEY_COLUMNS} | COUNTER_ROW_SCHEMA

    def schemas(self) -> dict[str, dict[str, str]]:
        tables = {f"smf113_{s}": self._row_schema(s) for s in SUBTYPES}
        if self.options.get("counters", False):
            tables.update({f"smf113_{s}_counters": self._counter_schema(s) for s in SUBTYPES})
        return tables

    def parse(self, rec: bytes, ctx: ParseContext) -> Iterator[tuple[str, dict[str, Any]]]:
        row = parse_header(rec, ctx.codepage, ctx.source_file, ctx.offset)
        subtype = row["smf_subtype"]
        if subtype not in SUBTYPES:
            raise ValueError(f"unsupported SMF 113 subtype {subtype}")
        for at, section in ((TRIPLET_SUBSYSTEM, SUBSYSTEM), (TRIPLET_IDENTIFICATION, IDENTIFICATION)):
            t = triplet(rec, at)
            start = next(occurrences(rec, t), None)
            row.update(section.empty() if start is None else section.decode(rec, start, t.length, ctx.codepage))
        data = triplet(rec, TRIPLET_DATA)
        if data.count == 0 or data.offset >= len(rec):
            raise ValueError("no data section")
        # The subtype header ends where the counter set descriptors begin.
        cs_offset = triplet(rec, data.offset + (CS_TRIPLET_1 if subtype == 1 else CS_TRIPLET_2)).offset
        header_length = cs_offset - data.offset if cs_offset > data.offset else data.length
        row.update(DATA[subtype].decode(rec, data.offset, header_length, ctx.codepage))

        prefix = f"smf113_{subtype}_"
        times = [c for c in ("smf113intervalstart", "smf113intervalend", prefix + "cts", prefix + "ctm") if row[c]]
        if times:
            shift = self._utc_offset(row, row[prefix + "ctm"] or row[times[-1]])
            for c in times:
                row[c] += shift

        row.update(dict.fromkeys(COUNTER_SCHEMA))
        counters = []
        for cs_type, values in counter_sets(rec, data.offset, subtype):
            name, base, columns = COUNTER_SETS.get(cs_type, (f"set{cs_type}", None, 0))
            for i, value in enumerate(values):
                counters.append((name, i, None if base is None else base + i, value))
                if i < columns:
                    row[f"{name}_{base + i}"] = value
            if len(values) > columns and base is not None and (subtype, cs_type) not in self._warned_unmapped:
                self._warned_unmapped.add((subtype, cs_type))
                log.warning("SMF 113 subtype %d: %d %s counters, only the first %d have columns "
                            "(all are in smf113_%d_counters with records: {113: {counters: true}})",
                            subtype, len(values), name, columns, subtype)

        proc_class = row[prefix + "cpuprocclass"]
        row["cpu_type"] = PROC_CLASSES.get(proc_class, None if proc_class is None else str(proc_class))
        start, end = row["smf113intervalstart"], row["smf113intervalend"]
        row["duration_sec"] = (end - start).total_seconds() if start and end else None
        yield f"smf113_{subtype}", row

        if self.options.get("counters", False):
            keys = {c: row[c] for c in COUNTER_KEY_COLUMNS}
            for name, index, number, value in counters:
                yield f"smf113_{subtype}_counters", keys | {
                    "cpu_id": row[prefix + "cpuid"], "counter_set": name, "counter_index": index,
                    "counter_number": number, "counter_value": value}

    def _utc_offset(self, row: dict[str, Any], tod: Any) -> timedelta:
        """Local time minus UTC, to shift the TOD-clock times to local time.

        HIS writes the record as soon as it reads the counters (SMF113_x_CTM), so the record time
        (local) minus CTM is the offset to within a second. Failing that, reuse the system's last
        offset, else floor the gap to quarter hours."""
        written = row["smf_datetime"]
        offset = whole_quarters(written - tod) if written is not None else None
        if offset is not None:
            self._utc_offsets[row["smf_sid"]] = offset
            return offset
        known = self._utc_offsets.get(row["smf_sid"])
        if known is not None or written is None:
            return known or timedelta(0)
        return (written - tod + timedelta(seconds=1)) // QUARTER_HOUR * QUARTER_HOUR
