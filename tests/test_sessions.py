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


def test_correct_clock_offset_roundtrips_and_defaults_false(tmp_path):
    store = SessionStore(tmp_path)
    session = Session(
        name="skewed",
        left=SessionSide(SIDE_LOCAL, "C:/a"),
        right=SessionSide(SIDE_SFTP, "/srv", profile="prod"),
        correct_clock_offset=True,
    )
    store.save([session])
    assert store.load()[0].correct_clock_offset is True
    # a session saved before this field existed loads as off
    (tmp_path / "sessions.json").write_text(
        '[{"name": "old", "left": {"kind": "local", "path": "x"},'
        ' "right": {"kind": "local", "path": "y"}}]',
        encoding="utf-8",
    )
    assert store.load()[0].correct_clock_offset is False


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


def test_compare_filters_roundtrip(tmp_path):
    from datetime import UTC, datetime

    from shankompare.compare import CompareFilters

    filters = CompareFilters(
        exclude_globs=("*.log", "__pycache__"),
        include_globs=("*.py", "weekly report*.xlsx"),
        min_size=10,
        max_size=1024**2,
        modified_after=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session = Session(
        name="filtered",
        left=SessionSide(SIDE_LOCAL, "C:/a"),
        right=SessionSide(SIDE_LOCAL, "D:/b"),
    )
    session.set_compare_filters(filters)
    store = SessionStore(tmp_path)
    store.save([session])
    loaded = store.load()[0]
    assert loaded.compare_filters() == filters


def test_session_without_filter_fields_defaults_to_no_filters(tmp_path):
    store = SessionStore(tmp_path)
    (tmp_path / "sessions.json").write_text(
        '[{"name": "old", "left": {"kind": "local", "path": "x"},'
        ' "right": {"kind": "local", "path": "y"}}]',
        encoding="utf-8",
    )
    from shankompare.compare import CompareFilters

    assert store.load()[0].compare_filters() == CompareFilters()


def test_session_predating_include_filters_still_loads(tmp_path):
    """Sessions written before include filters existed keep their exclusions."""
    store = SessionStore(tmp_path)
    (tmp_path / "sessions.json").write_text(
        '[{"name": "old", "left": {"kind": "local", "path": "x"},'
        ' "right": {"kind": "local", "path": "y"},'
        ' "exclude_globs": ["*.log"], "exclude_min_size": 10}]',
        encoding="utf-8",
    )
    from shankompare.compare import CompareFilters

    assert store.load()[0].compare_filters() == CompareFilters(
        exclude_globs=("*.log",), min_size=10
    )


def test_settings_roundtrip(tmp_path):
    store = SettingsStore(tmp_path)
    assert store.load() == AppSettings()  # defaults when missing
    store.save(AppSettings(theme="dark"))
    assert store.load().theme == "dark"
