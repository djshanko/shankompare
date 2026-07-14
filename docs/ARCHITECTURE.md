# shankompare — Architecture

Four layers, with a strict rule: **Qt is only allowed in the UI layer.** Everything below it is plain Python, unit-testable headless. Dependencies point downward only.

```
┌─────────────────────────────────────────────┐
│ ui/        PySide6 — windows, views, workers │
├─────────────────────────────────────────────┤
│ sessions/  profiles, saved sessions, config  │
├─────────────────────────────────────────────┤
│ compare/   folder comparer, text differ      │
├─────────────────────────────────────────────┤
│ vfs/       FileSystem abstraction            │
└─────────────────────────────────────────────┘
```

Package layout: `src/shankompare/{vfs,compare,sessions,ui}/`.

## 1. VFS layer (`vfs/`)

The reason future backends (FTP, archives, SMB) slot in without rewrites: everything above this layer sees only the abstract interface, never paramiko or `os`.

```python
class FileSystem(ABC):
    def listdir(self, path: PurePosixPath) -> list[EntryInfo]: ...
    def stat(self, path: PurePosixPath) -> EntryInfo: ...
    def open_read(self, path: PurePosixPath) -> BinaryIO: ...
    def open_write(self, path: PurePosixPath) -> BinaryIO: ...
    def mkdir(self, path: PurePosixPath) -> None: ...
    def remove(self, path: PurePosixPath) -> None: ...
    def rename(self, src: PurePosixPath, dst: PurePosixPath) -> None: ...
    def close(self) -> None: ...
```

- `EntryInfo` is a frozen dataclass: `name`, `is_dir`, `size`, `mtime` (UTC), plus a free-form `raw` field for backend extras.
- Paths are POSIX-style within a filesystem; each `FileSystem` instance is rooted (a local base directory, or an SFTP profile + initial path). This makes local and remote code paths identical above the VFS.
- Backend errors are translated to a small exception hierarchy (`VfsError` → `VfsAuthError`, `VfsNotFound`, `VfsPermissionError`, `VfsConnectionError`) so upper layers never catch paramiko or OS exceptions.

**v1 implementations**

- `LocalFileSystem` — wraps `pathlib`/`os`; used for local drives and (on Windows) UNC/mapped network paths.
- `SftpFileSystem` — wraps one `paramiko.SFTPClient`. **Not thread-safe; one instance per worker thread.** Each compare side opens its own connection, which also gives SFTP ↔ SFTP for free.

**Future implementations (same interface, no upper-layer changes):** `FtpFileSystem`, `ArchiveFileSystem` (zip/tar as a read-only folder), `SmbFileSystem`.

## 2. Compare engine (`compare/`)

### Folder comparer

- Input: two `FileSystem` instances + `CompareOptions` (criteria: mtime with tolerance / size / content-CRC32 / content-bytes; case sensitivity).
- Walks both trees breadth-first in lockstep, aligning entries by name (case handling per options).
- Output: a tree of `NodeResult { name, status, left: EntryInfo|None, right: EntryInfo|None, children }` with status ∈ `LEFT_ONLY | RIGHT_ONLY | SAME | DIFFERENT | UNKNOWN`. A folder's status is derived from its children.
- Cheap criteria (name/size/mtime) run during the walk; content comparison is a second, lazier pass so the tree appears fast.
- Runs as a generator yielding progress events (`entered dir`, `compared N files`, partial results) — the caller (UI worker) decides how to consume; cancellation via a `threading.Event` checked between yields.

### Text differ

- v1: `difflib.SequenceMatcher` — line-level opcodes first, then a second character-level pass within each replaced line pair for intra-line highlighting.
- Output: a list of `DiffBlock { kind: equal|insert|delete|replace, left_range, right_range, intra_line_spans }` — pure data the UI renders; also directly usable by a future HTML export or patch viewer.
- Upgrade path: swap in a Myers/patience implementation behind the same output type if `difflib` quality/perf disappoints.
- Encoding detection (BOM sniff → UTF-8 strict → Latin-1 fallback) and EOL normalization live here, not in the UI.

## 3. Sessions & profiles (`sessions/`)

- `ConnectionProfile` — name, host, port, username, auth method, key file path, initial path. Serialized as JSON.
- Config location via `platformdirs`: `%APPDATA%\shankompare\` on Windows, `~/.config/shankompare/` on Ubuntu.
- Secrets (passwords, key passphrases) stored via `keyring` under service `shankompare`, keyed by profile name. The JSON never contains secrets.
- Future: `Session` (a pair of sides + compare options) serializes the same way.

## 4. UI layer (`ui/`)

- `MainWindow` — tabbed: folder-compare tabs and text-compare tabs.
- `FolderCompareView` — `QTreeView` over a custom `QAbstractItemModel` backed by the `NodeResult` tree; delegates paint status colors; toolbar holds filter toggles and next/prev difference.
- `TextCompareView` — two synchronized-scroll `QPlainTextEdit` panes; `DiffBlock` data drives `QSyntaxHighlighter`-style extra selections for line and intra-line coloring.
- `ProfileDialog` — manage SFTP profiles; a "Browse…" picker that works over any `FileSystem`.

### Threading model

- One `QThread` + worker object per running comparison. The worker owns its two `FileSystem` instances (created on the worker thread — required for paramiko).
- Worker consumes the comparer's progress generator and re-emits Qt signals (`progress`, `partial_result`, `finished`, `failed`); the model updates only on the UI thread.
- Cancellation: UI sets the `threading.Event`; worker winds down and closes its filesystems.

### Error handling

- `VfsError` subtypes map to user-facing dialogs/infobar messages (auth error → re-prompt credentials; connection error → offer retry).
- Unexpected exceptions in workers are caught at the worker boundary, logged (`logging` to console + rotating file in the config dir), and surfaced as a generic error with log pointer — the app must not die because one compare failed.

## 5. Walkthrough: local ↔ SFTP folder compare

1. User picks a local folder for the left side and an SFTP profile for the right, clicks Compare.
2. UI spawns a worker thread. Worker creates `LocalFileSystem(base)` and `SftpFileSystem(profile)` (password fetched from keyring; on `VfsAuthError` the UI re-prompts).
3. Worker runs the folder comparer generator; every yielded partial result is emitted as a signal; the tree model merges it in and the view updates live.
4. User double-clicks a `DIFFERENT` file pair → both files stream through `open_read()` into memory → text differ produces `DiffBlock`s → a new text-compare tab renders them.
5. User closes the tab or cancels; worker closes both filesystems and the thread exits.
