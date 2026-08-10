"""Config files must never stop the app from starting, and never be half-written.

All three stores load during ``MainWindow.__init__``, so a raise here means no
window at all — and no UI to repair the file with.
"""

import contextlib
import json

from shankompare.sessions import (
    SIDE_LOCAL,
    AppSettings,
    ConnectionProfile,
    ProfileStore,
    Session,
    SessionSide,
    SessionStore,
    SettingsStore,
)

CORRUPT = [
    "",  # truncated to nothing
    "[{",  # crash mid-write
    "not json at all",
    '{"theme": "dark"}',  # right JSON, wrong shape for a list of records
]


def _session(name: str = "s") -> Session:
    return Session(
        name=name,
        left=SessionSide(SIDE_LOCAL, "C:/a"),
        right=SessionSide(SIDE_LOCAL, "D:/b"),
    )


def test_corrupt_sessions_file_loads_as_empty(tmp_path):
    store = SessionStore(tmp_path)
    for content in CORRUPT:
        (tmp_path / "sessions.json").write_text(content, encoding="utf-8")
        assert store.load() == []


def test_corrupt_profiles_file_loads_as_empty(tmp_path):
    store = ProfileStore(tmp_path)
    for content in CORRUPT:
        (tmp_path / "profiles.json").write_text(content, encoding="utf-8")
        assert store.load() == []


def test_corrupt_settings_file_loads_as_defaults(tmp_path):
    store = SettingsStore(tmp_path)
    for content in ["", "[{", "not json", "[1, 2, 3]", '{"theme": []}']:
        (tmp_path / "settings.json").write_text(content, encoding="utf-8")
        assert store.load() == AppSettings()


def test_corrupt_file_is_kept_as_bad_not_overwritten(tmp_path):
    """The unreadable content survives as <name>.bad for hand recovery."""
    path = tmp_path / "sessions.json"
    path.write_text("[{ half a session", encoding="utf-8")
    store = SessionStore(tmp_path)
    assert store.load() == []
    assert (tmp_path / "sessions.json.bad").read_text(encoding="utf-8") == "[{ half a session"
    assert not path.exists()

    store.save([_session()])  # the fresh file lands normally afterwards
    assert store.load() == [_session()]


def test_one_bad_record_does_not_lose_the_others(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "good",
                    "left": {"kind": "local", "path": "x"},
                    "right": {"kind": "local", "path": "y"},
                },
                "this is not a session",
                {"no_name_field": True},
                {
                    "name": "also good",
                    "left": {"kind": "local", "path": "p"},
                    "right": {"kind": "local", "path": "q"},
                },
            ]
        ),
        encoding="utf-8",
    )
    assert [s.name for s in SessionStore(tmp_path).load()] == ["good", "also good"]


def test_bad_profile_record_is_skipped(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(
        json.dumps([{"name": "prod", "host": "example.com"}, {"host": "no-name.example"}]),
        encoding="utf-8",
    )
    assert ProfileStore(tmp_path).load() == [ConnectionProfile(name="prod", host="example.com")]


def test_writes_leave_no_temp_file_behind(tmp_path):
    SessionStore(tmp_path).save([_session()])
    SettingsStore(tmp_path).save(AppSettings(theme="dark"))
    ProfileStore(tmp_path).save([ConnectionProfile(name="p", host="h")])
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "profiles.json",
        "sessions.json",
        "settings.json",
    ]


def test_failed_write_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    """An interrupted save must not truncate what was already saved."""
    store = SessionStore(tmp_path)
    store.save([_session("original")])

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("shankompare.sessions.storage.os.replace", boom)
    with contextlib.suppress(OSError):
        store.save([_session("replacement")])
    assert [s.name for s in store.load()] == ["original"]
