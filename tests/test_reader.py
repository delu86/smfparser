from datetime import date

from smfbuild import block, header, with_rdw

from smfparser.reader import ReaderStats, detect_blocked, iter_records

D = date(2026, 10, 9)
REC_A = header(2, None, 100, D)
REC_B = header(30, 4, 200, D) + bytes(range(256)) * 3


def test_blocked_with_spanned_record():
    b = REC_B
    data = block(with_rdw(REC_A), with_rdw(b[:100], seg=1)) + block(with_rdw(b[100:400], seg=3)) + block(
        with_rdw(b[400:], seg=2), with_rdw(REC_A)
    )
    assert detect_blocked(data)
    stats = ReaderStats()
    out = list(iter_records(data, stats))
    assert [r for r, _ in out] == [with_rdw(REC_A), with_rdw(REC_B), with_rdw(REC_A)]
    # offsets point at the first segment of each record
    assert out[0][1] == 4
    assert out[1][1] == 4 + len(with_rdw(REC_A))
    assert stats.records == 3 and stats.segments == 5 and stats.orphan_segments == 0


def test_unblocked_rdw_only():
    data = with_rdw(REC_A) + with_rdw(REC_B[:50], seg=1) + with_rdw(REC_B[50:], seg=2)
    assert not detect_blocked(data)
    assert [r for r, _ in iter_records(data)] == [with_rdw(REC_A), with_rdw(REC_B)]


def test_orphan_segments_are_skipped():
    data = block(with_rdw(REC_B[50:], seg=2), with_rdw(REC_A), with_rdw(REC_B[:50], seg=1), with_rdw(REC_A))
    stats = ReaderStats()
    assert [r for r, _ in iter_records(data, stats)] == [with_rdw(REC_A), with_rdw(REC_A)]
    assert stats.orphan_segments == 2


def test_truncated_block_stops_cleanly():
    data = block(with_rdw(REC_A), with_rdw(REC_A))
    data = data + data[:-5]  # second block cut short
    stats = ReaderStats()
    records = list(iter_records(data, stats))
    assert len(records) >= 2
    assert stats.truncated == 1


def test_empty_input():
    assert list(iter_records(b"")) == []
