"""Saved comparison sessions: two sides plus compare options, as JSON."""

import dataclasses
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from platformdirs import user_config_dir

from shankompare.compare import ExcludeFilters

SIDE_LOCAL = "local"
SIDE_SFTP = "sftp"


@dataclass
class SessionSide:
    kind: str  # SIDE_LOCAL or SIDE_SFTP
    path: str  # local folder path, or remote path
    profile: str | None = None  # profile name for SFTP sides


@dataclass
class Session:
    name: str
    left: SessionSide
    right: SessionSide
    use_size: bool = True
    use_mtime: bool = True
    mtime_tolerance: float = 2.0
    content: str = "none"  # ContentMode value
    case_sensitive: bool = True
    exclude_globs: list[str] = field(default_factory=list)
    exclude_min_size: int | None = None
    exclude_max_size: int | None = None
    exclude_modified_after: str | None = None  # ISO 8601
    exclude_modified_before: str | None = None

    def exclude_filters(self) -> ExcludeFilters:
        return ExcludeFilters(
            name_globs=tuple(self.exclude_globs),
            min_size=self.exclude_min_size,
            max_size=self.exclude_max_size,
            modified_after=_parse_iso(self.exclude_modified_after),
            modified_before=_parse_iso(self.exclude_modified_before),
        )

    def set_exclude_filters(self, filters: ExcludeFilters) -> None:
        self.exclude_globs = list(filters.name_globs)
        self.exclude_min_size = filters.min_size
        self.exclude_max_size = filters.max_size
        self.exclude_modified_after = _format_iso(filters.modified_after)
        self.exclude_modified_before = _format_iso(filters.modified_before)


def _parse_iso(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text) if text else None


def _format_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _filtered(cls, data: dict) -> dict:
    known = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in data.items() if k in known}


def _session_from_dict(data: dict) -> Session:
    kwargs = _filtered(Session, data)
    kwargs["left"] = SessionSide(**_filtered(SessionSide, data.get("left", {})))
    kwargs["right"] = SessionSide(**_filtered(SessionSide, data.get("right", {})))
    return Session(**kwargs)


class SessionStore:
    def __init__(self, config_dir: str | Path | None = None):
        base = Path(config_dir) if config_dir is not None else Path(user_config_dir("shankompare"))
        self._path = base / "sessions.json"

    def load(self) -> list[Session]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [_session_from_dict(item) for item in raw]

    def save(self, sessions: list[Session]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(s) for s in sessions], indent=2, ensure_ascii=False)
        self._path.write_text(payload, encoding="utf-8")


@dataclass
class AppSettings:
    theme: str = "system"  # "system" | "light" | "dark"
    extra: dict = field(default_factory=dict)  # forward-compatible scratch space


class SettingsStore:
    def __init__(self, config_dir: str | Path | None = None):
        base = Path(config_dir) if config_dir is not None else Path(user_config_dir("shankompare"))
        self._path = base / "settings.json"

    def load(self) -> AppSettings:
        if not self._path.exists():
            return AppSettings()
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return AppSettings(**_filtered(AppSettings, raw))

    def save(self, settings: AppSettings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8"
        )
