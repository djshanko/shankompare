"""Clock-offset helpers for the SFTP backend (no server required).

These cover the pure translation between the server clock frame and the
local clock frame that ``SftpFileSystem`` applies to every mtime it reports.
"""

from datetime import UTC, datetime, timedelta

from shankompare.vfs.sftp import _apply_offset, _clock_offset, _remove_offset


def test_no_offset_is_identity():
    ts = datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC).timestamp()
    assert _apply_offset(ts, timedelta(0)) == datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)


def test_apply_offset_shifts_into_local_frame():
    # Server clock runs 1h ahead: a file the server stamped at 13:00 was really
    # written at 12:00 local, so it must read as 12:00 to match local files.
    server_stamp = datetime(2026, 7, 15, 13, 0, 0, tzinfo=UTC).timestamp()
    local = _apply_offset(server_stamp, timedelta(hours=1))
    assert local == datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)


def test_apply_offset_is_timezone_aware():
    assert _apply_offset(0, timedelta(seconds=30)).tzinfo is not None


def test_offset_round_trips_through_set_mtime():
    # A local-frame mtime written via set_mtime and read back via stat/listdir
    # is unchanged, whatever the skew — this is what keeps compare/sync stable.
    offset = timedelta(seconds=137)
    local_mtime = datetime(2026, 3, 1, 8, 30, 0, tzinfo=UTC)
    stored = _remove_offset(local_mtime, offset)  # what lands on the server
    assert _apply_offset(stored, offset) == local_mtime


def test_remove_offset_truncates_to_whole_seconds():
    mtime = datetime(2026, 3, 1, 8, 30, 0, 500_000, tzinfo=UTC)
    assert _remove_offset(mtime, timedelta(0)) == int(mtime.timestamp())


def test_clock_offset_uses_local_midpoint():
    # server_now sits at local 1005 while the local interval was [1000, 1002],
    # midpoint 1001 -> the server is ~4s ahead.
    assert _clock_offset(1005.0, 1000.0, 1002.0) == timedelta(seconds=4)


def test_clock_offset_detects_a_behind_server():
    assert _clock_offset(990.0, 1000.0, 1000.0) == timedelta(seconds=-10)
