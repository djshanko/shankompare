# shankompare — Roadmap

Milestones build on each other; each ends in something runnable. Tags here match docs/REQUIREMENTS.md ([v1] = M1–M2, [v1.x] = M3, [future] = M4+).

## M1 — Skeleton and core engine ✅ (done 2026-07-14)

Goal: a comparison works end to end, even if the UI is bare.

- Project skeleton: `pyproject.toml`, `src/shankompare/` package layout, pytest + ruff configured, CI-less but `pytest` green.
- `vfs/`: `FileSystem` interface, `EntryInfo`, exception hierarchy, `LocalFileSystem`, `SftpFileSystem`.
- `sessions/`: `ConnectionProfile` JSON persistence + keyring integration.
- `compare/`: folder comparer with mtime/size/content criteria, progress generator, cancellation.
- Minimal UI: main window, pick two sides (local path or SFTP profile), run compare on a worker thread, show results in a basic colored tree.
- Tests: VFS contract test suite run against `LocalFileSystem` (and against a fake in-memory FS used by comparer tests); comparer unit tests for every status and criteria combination.

## M2 — Full v1 UI ✅ (done 2026-07-14)

Goal: daily-drivable for the primary use case.

- Folder compare view: display filters (only differences / added / modified), auto-expanded subfolders, next/prev difference navigation, re-compare.
- Profile manager dialog with remote folder browser.
- Text compare view: side-by-side with intra-line highlighting, synchronized scrolling, next/prev difference, show-only-differences with context, encoding + EOL handling, ignore-whitespace option.
- Robust SFTP error handling (re-prompt on auth failure, retry on connection loss).
- **This is the v1 release.**

## M3 — Quality of life (v1.x)

- File operations from the folder view: copy and delete across sides, then move/rename/set-mtime — with background progress and multiple queued operations.
- Sessions: save/load a comparison (sides + options) as a named session.
- Dark mode (Qt palette based, follow-OS by default with manual override).
- Inline editing in text compare with dynamic recomparison; gutter buttons to copy sections between sides.
- Packaging: PyInstaller builds for Windows and Ubuntu.

## M4+ — Backlog (future)

Ordered by expected value, not committed:

- Synchronization commands (mirror left→right, update both)
- Exclusion filters (name globs, size, mtime)
- Binary/hex compare view
- Archive files as folders (`ArchiveFileSystem`)
- FTP / FTPS backends; SSH agent + keyboard-interactive auth; resumable transfers
- Unix patch file viewer
- Syntax highlighting and find & replace in text compare
- SMB backend, MBCS encodings, pausable operations
