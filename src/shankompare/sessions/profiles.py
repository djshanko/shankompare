"""SFTP connection profiles: JSON persistence plus keyring-backed secrets.

The JSON file never contains passwords or passphrases; those live in the
OS keyring under the ``shankompare`` service, keyed by profile name.
"""

import contextlib
import dataclasses
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import keyring
import keyring.errors
from platformdirs import user_config_dir

_SERVICE = "shankompare"

AUTH_PASSWORD = "password"
AUTH_KEY = "key"


@dataclass
class ConnectionProfile:
    name: str
    host: str
    port: int = 22
    username: str = ""
    auth_method: str = AUTH_PASSWORD
    key_file: str | None = None
    initial_path: str = "."

    def to_sftp_kwargs(self, secret: str | None) -> dict[str, Any]:
        """Keyword arguments for ``SftpFileSystem(profile.host, **kwargs)``.

        ``secret`` is the password for password auth, or the key passphrase
        for key auth.
        """
        kwargs: dict[str, Any] = {
            "port": self.port,
            "username": self.username or None,
            "root": self.initial_path or ".",
        }
        if self.auth_method == AUTH_KEY:
            kwargs["key_file"] = self.key_file
            kwargs["key_passphrase"] = secret
        else:
            kwargs["password"] = secret
        return kwargs


class ProfileStore:
    """Loads and saves profiles as JSON in the per-user config directory."""

    def __init__(self, config_dir: str | Path | None = None):
        base = Path(config_dir) if config_dir is not None else Path(user_config_dir(_SERVICE))
        self._path = base / "profiles.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[ConnectionProfile]:
        if not self._path.exists():
            return []
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        known = {f.name for f in dataclasses.fields(ConnectionProfile)}
        return [ConnectionProfile(**{k: v for k, v in item.items() if k in known}) for item in raw]

    def save(self, profiles: list[ConnectionProfile]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([asdict(p) for p in profiles], indent=2, ensure_ascii=False)
        self._path.write_text(payload, encoding="utf-8")

    @staticmethod
    def get_secret(profile_name: str) -> str | None:
        return keyring.get_password(_SERVICE, profile_name)

    @staticmethod
    def set_secret(profile_name: str, secret: str) -> None:
        keyring.set_password(_SERVICE, profile_name, secret)

    @staticmethod
    def delete_secret(profile_name: str) -> None:
        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(_SERVICE, profile_name)
