"""Helpers that build synthetic SMF records and dump files for tests."""

from __future__ import annotations

from datetime import date, timedelta

CP = "cp037"


def e(text: str, length: int) -> bytes:
    return text.ljust(length).encode(CP)[:length]


def u(value: int, length: int) -> bytes:
    return value.to_bytes(length, "big")


def smf_date_bytes(d: date) -> bytes:
    """0cyydddF packed date."""
    century = 1 if d.year >= 2000 else 0
    digits = f"{century}{d.year % 100:02d}{d.timetuple().tm_yday:03d}"
    return bytes.fromhex(f"0{digits}F")


def header(rtype: int, subtype: int | None, hundredths: int, d: date, sid: str = "SYSA", ssi: str = "JES2") -> bytes:
    """Standard header without the RDW (flag .. subtype)."""
    flag = 0x5E if subtype is not None else 0x1E
    out = bytes([flag, rtype]) + u(hundredths, 4) + smf_date_bytes(d) + e(sid, 4)
    if subtype is not None:
        out += e(ssi, 4) + u(subtype, 2)
    return out


def with_rdw(body: bytes, seg: int = 0) -> bytes:
    return u(len(body) + 4, 2) + bytes([seg, 0]) + body


def block(*segments: bytes) -> bytes:
    data = b"".join(segments)
    return u(len(data) + 4, 2) + b"\x00\x00" + data


def record_body(rec: bytes) -> bytes:
    """Strip the RDW from a full record."""
    return rec[4:]


def type30_record(
    subtype: int = 4,
    jobname: str = "MYJOB",
    program: str = "IEFBR14",
    stepname: str = "STEP1",
    cpu_tcb: int = 151,  # hundredths
    cpu_srb: int = 4,
    accounting: list[str] | None = None,
    excp: list[tuple[str, int]] | None = None,  # (ddname, blocks)
    ident_length: int = 250,
    d: date = date(2026, 10, 9),
) -> bytes:
    """A type 30 record (with RDW) holding subsystem, identification, completion, processor,
    performance, accounting and EXCP sections."""
    accounting = accounting or []
    excp = excp or []

    subsystem = u(subtype, 2) + b"\x00\x00" + e("05", 2) + e("SMF", 8) + e("SP7.2.5", 8) + e("SY1", 8) + e("PLEX1", 8)
    ident = bytearray(256)
    ident[0:8] = e(jobname, 8)
    ident[8:16] = e(program, 8)
    ident[16:24] = e(stepname, 8)
    ident[32:40] = e("JOB00042", 8)
    ident[40:42] = u(1, 2)
    ident[42:43] = e("A", 1)
    ident[48:52] = u(3_600_050, 4)  # 10:00:00.50 allocation start
    ident[52:56] = u(3_600_060, 4)
    ident[56:60] = u(3_600_000, 4)  # 10:00:00.00 initiator select
    ident[60:64] = smf_date_bytes(d)
    ident[64:68] = u(8_639_990, 4)  # reader start 23:59:59.90 the day before
    ident[68:72] = smf_date_bytes(d - timedelta(days=1))
    ident[72:76] = u(10, 4)
    ident[76:80] = smf_date_bytes(d)
    ident[80:100] = e("PROGRAMMER", 20)
    ident[140:148] = e("A", 8)
    ident[186:250] = e("CORRELATOR", 64)
    ident = bytes(ident[:ident_length])
    completion = u(0, 2) + u(0, 2) + u(0, 4)
    processor = bytearray(186)
    processor[2:4] = u(0x8000, 2)
    processor[4:8] = u(cpu_tcb, 4)
    processor[8:12] = u(cpu_srb, 4)
    processor[40:44] = bytes.fromhex("0000000F")  # zero packed date (no interval start)
    processor[178:186] = e("IEFBR14", 8)
    processor = bytes(processor)
    performance = bytearray(211)
    performance[0:4] = u(48, 4)
    performance[36:44] = e("BATCH", 8)
    performance[44:52] = e("BTHIGH", 8)
    performance = bytes(performance)
    acct = b"".join(bytes([len(a)]) + e(a, len(a)) for a in accounting)
    excp_bytes = b"".join(u(0x20, 1) + u(0x0F, 1) + u(0x1234, 2) + e(dd, 8) + u(blk, 4) + u(27998, 2)
                          + u(10, 4) + u(blk, 8) for dd, blk in excp)

    hdr = header(30, subtype, 3_600_100, d)
    triplet_area = 8 * 10
    pos = 4 + len(hdr) + triplet_area
    sections: list[tuple[bytes, int, int]] = []  # (data, entry length, count) in triplet order
    for data, entry_len, count in (
        (subsystem, len(subsystem), 1),
        (ident, len(ident), 1),
        (b"", 0, 0),  # I/O
        (completion, len(completion), 1),
        (processor, len(processor), 1),
        (acct, len(acct), len(accounting)),
        (b"", 0, 0),  # storage
        (performance, len(performance), 1),
        (b"", 0, 0),  # operator
        (excp_bytes, 30, len(excp)),
    ):
        sections.append((data, entry_len, count))
    triplets = b""
    payload = b""
    for data, entry_len, count in sections:
        triplets += u(pos if count else 0, 4) + u(entry_len, 2) + u(count, 2)
        payload += data
        pos += len(data)
    return with_rdw(hdr + triplets + payload)
