"""Saved comparison sessions: two sides plus compare options, as JSON."""

import dataclasses
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from platformdirs import user_config_dir

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
