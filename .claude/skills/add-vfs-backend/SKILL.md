---
name: add-vfs-backend
description: Steps to add a new FileSystem backend (FTP, SMB, etc.) to shankompare's VFS layer, including the shared contract test suite. Use when adding or significantly changing a storage backend.
---

# Adding a VFS backend

Everything above the VFS layer (compare engine, sync, UI) sees only the abstract `FileSystem` interface — a correct new backend needs **zero changes** in upper layers except UI plumbing to open it.

## 1. Implement the interface

Create `src/shankompare/vfs/<name>.py` subclassing `FileSystem` from `vfs/base.py`. Abstract methods: `listdir`, `stat`, `open_read`, `open_write`, `mkdir`, `remove`, `rename`, `set_mtime`, `close`. Study `local.py` (simplest), `sftp.py` (remote + error translation), `archive.py` (read-only), `memory.py` (test fake).

Contract requirements (the tests in `tests/vfs_contract.py` enforce these):

- Paths are root-relative POSIX; normalize every incoming path with `base.normalize()` (rejects `..`, treats `.`/`""` as root). Never let a caller escape the root.
- `listdir` returns `EntryInfo` sorted by name.
- `EntryInfo.mtime` must be **timezone-aware UTC**. Backend-native stat goes in `raw`; portable code never reads `raw`.
- Raise only `VfsError` subtypes from `vfs/errors.py` (`VfsNotFound`, `VfsAuthError`, `VfsPermissionError`, `VfsConnectionError`). Translate every backend/library exception at the boundary — upper layers must never see paramiko/OS exceptions.
- `mkdir`: parent must exist, path must not. `remove`: files and *empty* dirs only. `open_write` truncates.
- Instances need not be thread-safe, but must be safe as "one instance per worker thread".
- Read-only backend? Raise `VfsError` from the mutating methods (see `archive.py`) — the contract suite has a read-only mode.
- Unicode-safe names and content throughout; never assume a filesystem encoding.

## 2. Export it

Add the class to `src/shankompare/vfs/__init__.py`.

## 3. Test it against the contract

Create `tests/test_<name>_fs.py`:

```python
from tests.vfs_contract import FileSystemContractTests

class TestMyFs(FileSystemContractTests):
    @pytest.fixture
    def fs(self):
        ...yield an empty, writable filesystem rooted somewhere disposable...
```

Add backend-specific tests (auth failures, connection drops) alongside. If the backend needs a live server, gate with env vars like `test_sftp_fs.py` does (`SHANKOMPARE_TEST_SFTP_*`) so `pytest` stays green offline.

## 4. Wire into the UI (separate concern)

To make it selectable: extend `SideSpec` handling in `ui/worker.py` (`open_side`), profile storage in `sessions/profiles.py` (credentials via `keyring` only — never in JSON/config), and the profile dialog. Follow the `qt-threading` skill: filesystems are created on worker threads only.

**Layering rule: nothing under `vfs/`, `compare/`, or `sessions/` may import Qt/PySide6.**
