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

## M3 — Quality of life (v1.x) ✅ (done 2026-07-14)

- File operations from the folder view: copy and delete across sides, plus rename and set-mtime — background queue with progress, auto re-compare when the queue drains.
- Sessions: save/load a comparison (sides + options) as a named session (Session menu).
- Dark mode: follows the OS by default with manual override (View → Theme); all diff/status colors are scheme-aware.
- Inline editing in text compare (Edit mode) with debounced dynamic recomparison; copy-section buttons move the current difference between sides; Save writes back preserving encoding and EOL style.
- Packaging: PyInstaller one-folder builds (`packaging/shankompare.spec`).

## M4 — Feature updates ✅ (done 2026-07-14, v0.3.0)

- Synchronization commands (mirror left→right, mirror right→left, update both) with a confirmation plan
- Exclusion filters (name globs, size, mtime) which are also stored in session configuration
- Binary/hex compare view with automatic binary detection and per-byte highlighting
- Archive files as folders (`ArchiveFileSystem`, zip/tar, read-only, local or SFTP)
- In-app user manual and release notes (Help menu)

## 0.3.1 — QoL patch ✅ (done 2026-07-15)

Small enhancements on top of M4 (not a milestone):

- Folder-tab fast **Refresh**: re-scan re-checking content only for files modified since the last compare; also used automatically after file operations.
- Expand all / Collapse all in the folder tree.
- Line numbers in the text compare view.

## 0.3.2 — QoL patch ✅ (done 2026-07-16)

Small enhancement on top of M4 (not a milestone):

- SFTP **remote clock-offset correction** (opt-in *Adjust remote clock*): the server clock is measured on connect and its skew subtracted from remote modified times, for servers that stamp files with their own (skewed) clock.
- **Log file** (`shankompare.log`, rotating) with an Open Log Folder entry in the Help menu.

## 0.3.3 — QoL patch ✅ (done 2026-07-16)

Small enhancement on top of M4 (not a milestone):

- **Content-check gating rework**: content is authoritative when on — a size mismatch is *different* without a read, but a differing modified time triggers a read instead of a false *different* (fixes identical SFTP files that got a fresh timestamp reporting different).
- New **Skip content if size+time match** option (on by default; saved with sessions) to trust matching metadata, or force a full read on every pair.
- Content check now **defaults to CRC32** (was off).
- **Keyboard shortcuts** across all views (folder, text, hex) plus global tab management, listed under Help → Keyboard Shortcuts and in the manual.
- **Text-compare undo/redo** (buttons + Ctrl+Z / Ctrl+Y on the focused pane) and **unsaved-edit protection**: a `*` in the tab title while edits are pending, with a save/discard prompt when closing or refreshing the tab or quitting the app.

## 0.3.4 — QoL patch ✅ (done 2026-07-18)

Small enhancements on top of M4 (not a milestone):

- **Include filters** alongside the existing exclusions (empty = include everything; exclusions take priority; folders always pass so subtrees are still walked). Saved with sessions.
- Filter patterns may contain **whitespace** when double-quoted (`"My Documents"`); both filter fields show an example.
- Folder tab right-click → **Copy left path / Copy right path** (multi-select, one path per line).
- **Files present on only one side now open** in a text/hex tab, with the missing side shown as an empty `(missing)` pane.
- **Save session lists the existing sessions** for overwrite (with a confirmation), instead of silently replacing a name collision.
- **Show filter accepts multiple categories** (checkable menu over the four statuses, with All / Differences-only presets); not-yet-compared rows always stay visible.

## 0.3.5 — QoL patch ✅ (done 2026-08-07)

Small enhancements on top of M4 (not a milestone):

- Folder tab **Select** button, next to Show and carrying the same status options (Unchanged / Modified / Left orphans / Right orphans / All / Differences only); each choice selects the matching files for a batch copy/delete/timestamp operation. Folders are skipped so operations apply to individual files predictably.
- **Word wrap** in text compare (**Wrap** checkbox, Ctrl+Shift+W); off by default since wrapping can nudge the two panes out of vertical alignment.

## 0.3.6 — Correctness patch ✅ (done 2026-08-10)

No new features; the outcome of a full code and repository review:

- Refresh no longer reuses a previous verdict when the user has asked for content to be read on every pair — a copy that fixed a content-only difference could otherwise stay marked *different* indefinitely.
- SFTP errors *during* a transfer are translated like errors when opening a file, so one dropped connection costs one file instead of the whole comparison or operation batch.
- A remote or archive entry whose name carries Windows path syntax can no longer be written outside the destination root.
- Config files survive corruption and interrupted saves (set aside as `.bad`, defaults loaded, atomic writes) rather than blocking startup.
- One dialog per failed comparison; hex compare enforces its size limit before transferring; a zeroed zip timestamp no longer fails the archive.
- Icons and the in-app manual/release notes ship inside the package, so an ordinary `pip install` finds them.
- CI runs format, lint and the test suite on Windows *and* Ubuntu on every push.

## M5+ — Backlog (future)

Ordered by expected value, not committed:

- FTP / FTPS backends; SSH agent + keyboard-interactive auth; resumable transfers
- Unix patch file viewer
- Syntax highlighting and find & replace in text compare
- SMB backend, MBCS encodings, pausable operations
