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
    ziip: int = 0,  # hundredths
    ziip_nf: int = 256,  # SMF30SNF
    accounting: list[str] | None = None,
    excp: list[tuple[str, int]] | None = None,  # (ddname, blocks)
    ident_length: int = 250,
    d: date = date(2026, 10, 9),
    continuation: bool = False,  # only subsystem, identification and EXCP sections, as in an overflow record
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
    processor[116:120] = u(ziip, 4)
    processor[40:44] = bytes.fromhex("0000000F")  # zero packed date (no interval start)
    processor[178:186] = e("IEFBR14", 8)
    processor = bytes(processor)
    performance = bytearray(211)
    performance[0:4] = u(48, 4)
    performance[36:44] = e("BATCH", 8)
    performance[44:52] = e("BTHIGH", 8)
    performance[136:138] = u(ziip_nf, 2)
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
        if continuation and data not in (subsystem, ident, excp_bytes):
            data, count = b"", 0
        sections.append((data, entry_len, count))
    triplets = b""
    payload = b""
    for data, entry_len, count in sections:
        triplets += u(pos if count else 0, 4) + u(entry_len, 2) + u(count, 2)
        payload += data
        pos += len(data)
    return with_rdw(hdr + triplets + payload)


def ext_section(sty: int, data: bytes) -> bytes:
    """An extended information section of a type 14/15 record: descriptor + data."""
    return u(len(data) + 4, 2) + b"\x00" + bytes([sty]) + data


def type14_record(
    rtype: int = 14,
    dasd: bool = True,
    ddname: str = "SYSUT1",
    dsname: str = "USER.TEST.DATA",
    volumes: list[tuple[str, int, int]] | None = None,  # (volser, excp, tracks or tape sequence)
    hiperbatch: bool = False,
    extended: list[bytes] | None = None,  # ext_section() entries; default SMS + step sections
    d: date = date(2026, 10, 9),
) -> bytes:
    """A type 14/15 record (with RDW): fixed part, UCB sections, optional Hiperbatch section and
    extended information segment."""
    volumes = volumes if volumes is not None else [("VOL001", 12, 150)]
    if extended is None:
        extended = [
            ext_section(2, e("MCSTD", 8) + e("DCSTD", 8) + e("SCSTD", 8)),
            ext_section(3, e("STEP1", 8) + e("IEBGENER", 8) + e("JOB00042", 8) + e("PLEX1", 8)),
        ]
    rin = (0x2000 if dasd else 0) | (0x0008 if hiperbatch else 0) | (0x0004 if extended else 0)

    fixed = bytearray(264)  # record offsets 4..268 (indexes are offset - 4)
    fixed[0:14] = header(rtype, None, 3_600_100, d)  # offsets 4..18
    fixed[14:22] = e("MYJOB", 8)  # SMF14JBN at 18
    fixed[22:26] = u(8_639_990, 4)  # SMF14RST: 23:59:59.90 the day before
    fixed[26:30] = smf_date_bytes(d - timedelta(days=1))
    fixed[38:40] = u(rin, 2)  # SMF14RIN at 42
    fixed[40:44] = bytes([28, len(volumes), 24, 0])  # SDC, NUC, SUC, SET
    fixed[44:48] = u(3_600_000, 4)  # SMF14OPE at 48: 10:00:00.00
    fixed[52:60] = e(ddname, 8)  # SMF14TIOE5 at 56
    fixed[64:108] = e(dsname, 44)  # JFCBDSNM at 68
    fixed[144:147] = bytes([126]) + u(282, 2)  # JFCBCRDT at 148: 2026.282
    fixed[151] = 0x48 if rtype == 14 else 0xC0  # JFCBIND2 at 155: SHR / NEW
    fixed[162:164] = u(0x4000, 2)  # JFCDSORG at 166: PS
    fixed[164] = 0x90  # JFCRECFM at 168: FB
    fixed[166:168] = u(27920, 2)  # JFCBLKSI at 170
    fixed[168:170] = u(80, 2)  # JFCLRECL at 172
    fixed[181] = len(volumes)  # JFCBNVOL at 185
    for i, (vol, _, _) in enumerate(volumes[:5]):
        fixed[182 + 6 * i : 188 + 6 * i] = e(vol, 6)
    fixed[240:242] = u(0x4000, 2)  # SMF14DCBOR at 244
    fixed[242] = 0x90  # SMF14DCBRF at 246
    if dasd:
        fixed[252:256] = u(0x00050100, 4)  # SMF14NTU at 256
        fixed[256:260] = u(3, 4)  # SMF14NTR at 260
    else:
        fixed[252:256] = u(777, 4)  # SMF14DCBBL at 256
        fixed[256:262] = e("VOL001", 6)  # SMF14DSSNO at 260
    body = bytes(fixed) + smf_date_bytes(d)  # SMF14OPD at 268

    for i, (vol, excp, extra) in enumerate(volumes):
        ucb = u(0x1234 + i, 2) + e(vol, 6) + u(0x3030200F if dasd else 0x78048081, 4) + bytes([0x10, 1]) + b"\0\0"
        ucb += u(excp, 4) + (u(extra, 4) if dasd else u(1, 2) + u(extra, 2))
        body += ucb
    if hiperbatch:
        body += u(10, 4) + u(7, 4) + u(1, 4) + u(3, 4) + u(2, 4)
    if extended:
        segment = b"".join(extended)
        body += u(len(segment) + 2, 2) + segment
    return with_rdw(body)


def cics_entry(owner: str, kind: str, ident: str, length: int, connector: int, offset: int, nickname: str) -> bytes:
    """A 26-byte CICS monitoring dictionary entry (offset X'FFFF' = excluded)."""
    return e(owner, 8) + e(kind, 1) + e(ident, 3) + u(length, 2) + u(connector, 2) + u(offset, 2) + e(nickname, 8)


def cics_record(
    cls: int,
    data: bytes,
    entry_length: int,
    count: int,
    connectors: list[int] | None = None,
    applid: str = "CICSA001",
    adjust_seconds: int = 3600,
    d: date = date(2026, 10, 26),
) -> bytes:
    """A type 110 subtype 1 record (with RDW): monitoring class `cls` with `count` entries of
    `entry_length` bytes (dictionary entries or performance records) after the connector list."""
    connectors = connectors or []
    hdr = header(110, 1, 4_020_000, d, ssi="CICS")  # 11:10:00
    ps_offset = 4 + len(hdr) + 4 + 16  # triplet count + 2 triplets
    product = bytearray(114)
    product[0:2] = u(0x0730, 2)
    product[2:10] = e(applid, 8)
    product[10:18] = e(applid, 8)
    product[22:24] = u(cls, 2)
    conn_offset = ps_offset + len(product)
    product[24:32] = u(conn_offset if connectors else 0, 4) + u(2 if connectors else 0, 2) + u(len(connectors), 2)
    rec_offset = conn_offset + 2 * len(connectors)
    product[32:40] = u(rec_offset, 4) + u(entry_length, 2) + u(count, 2)
    product[72:80] = u(adjust_seconds * 1_000_000 << 12, 8)
    product[82:90] = e("CICSJOB", 8)
    product[90:94] = smf_date_bytes(d)
    product[94:98] = u(360_000, 4)  # 01:00:00
    product[98:106] = e("CICSUSR", 8)
    product[106:114] = e("SP7.2.5", 8)
    data_len = len(data) + 2 * len(connectors)
    triplets = u(2, 2) + b"\0\0" + u(ps_offset, 4) + u(len(product), 2) + u(1, 2) + u(conn_offset, 4) + u(data_len, 2) + u(1, 2)
    conns = b"".join(u(c, 2) for c in connectors)
    return with_rdw(hdr + triplets + bytes(product) + conns + data)
