from shankompare.sessions import (
    SIDE_LOCAL,
    SIDE_SFTP,
    AppSettings,
    Session,
    SessionSide,
    SessionStore,
    SettingsStore,
)


def test_session_roundtrip(tmp_path):
    store = SessionStore(tmp_path)
    sessions = [
        Session(
            name="deploy check",
            left=SessionSide(SIDE_LOCAL, "C:/projects/site"),
            right=SessionSide(SIDE_SFTP, "/var/www/site", profile="prod"),
            content="crc32",
            mtime_tolerance=5.0,
        ),
        Session(
            name="two locals",
            left=SessionSide(SIDE_LOCAL, "C:/a"),
            right=SessionSide(SIDE_LOCAL, "D:/b"),
            use_mtime=False,
        ),
    ]
    store.save(sessions)
    assert store.load() == sessions


def test_session_load_missing_returns_empty(tmp_path):
    assert SessionStore(tmp_path).load() == []


def test_session_unknown_keys_ignored(tmp_path):
    store = SessionStore(tmp_path)
    path = tmp_path / "sessions.json"
    path.write_text(
        '[{"name": "s", "left": {"kind": "local", "path": "x", "future_key": 1},'
        ' "right": {"kind": "local", "path": "y"}, "other_future": true}]',
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded == [
        Session(name="s", left=SessionSide("local", "x"), right=SessionSide("local", "y"))
    ]


def test_exclude_filters_roundtrip(tmp_path):
    from datetime import UTC, datetime

    from shankompare.compare import ExcludeFilters

    filters = ExcludeFilters(
        name_globs=("*.log", "__pycache__"),
        min_size=10,
        max_size=1024**2,
        modified_after=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session = Session(
        name="filtered",
        left=SessionSide(SIDE_LOCAL, "C:/a"),
        right=SessionSide(SIDE_LOCAL, "D:/b"),
    )
    session.set_exclude_filters(filters)
    store = SessionStore(tmp_path)
    store.save([session])
    loaded = store.load()[0]
    assert loaded.exclude_filters() == filters


def test_session_without_filter_fields_defaults_to_no_filters(tmp_path):
    store = SessionStore(tmp_path)
    (tmp_path / "sessions.json").write_text(
        '[{"name": "old", "left": {"kind": "local", "path": "x"},'
        ' "right": {"kind": "local", "path": "y"}}]',
        encoding="utf-8",
    )
    from shankompare.compare import ExcludeFilters

    assert store.load()[0].exclude_filters() == ExcludeFilters()


def test_settings_roundtrip(tmp_path):
    store = SettingsStore(tmp_path)
    assert store.load() == AppSettings()  # defaults when missing
    store.save(AppSettings(theme="dark"))
    assert store.load().theme == "dark"
