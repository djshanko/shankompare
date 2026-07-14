# shankompare — Release Notes

## 0.3.0 — 2026-07-14 (M4)

**New features**

- **Synchronization commands** — Sync ▾ Mirror left→right, Mirror right→left, and Update both (newer file wins). Every command shows its full plan for confirmation before running.
- **Exclusion filters** — Filters… excludes entries by name glob, file-size range, and modified-date window; saved and restored with sessions.
- **Binary/hex compare** — differing file pairs that look binary open as a side-by-side hex dump with per-byte highlighting, only-differences mode, and next/prev navigation. Right-click a pair to force *Compare as text* or *Compare as hex*.
- **Archives as folders** — a side pointing at a `.zip`, `.tar`, `.tar.gz/.tgz`, `.tar.bz2` or `.tar.xz` file (local or SFTP) is compared read-only as if it were a folder.
- **Help menu** — this user manual and these release notes, viewable inside the app.

## 0.2.x — 2026-07-14 (M3 + fixes)

- File operations from the folder tree (copy/delete/rename/copy-timestamp) on a background queue with automatic re-compare.
- Named sessions (sides + options) via the Session menu.
- Dark mode: system/light/dark with scheme-aware colors; later fixed to work on Windows 10 by switching to the Fusion style for explicit choices.
- Text compare editing: Edit mode with live re-compare, copy-section buttons, Save preserving encoding/EOL; current-line highlight and Refresh button added.
- Packaging: single-file PyInstaller executable with the application icon.
- Fixes: blank text-compare tabs (worker garbage-collected before running), intermittent crash opening diffs from local↔SFTP comparisons (worker signals delivered on the wrong thread).

## 0.1.0 — 2026-07-14 (M1–M2, first usable release)

- Side-by-side folder comparison: local ↔ local, local ↔ SFTP, SFTP ↔ SFTP, streaming results, display filters, next/prev difference.
- Comparison criteria: size, modified time with tolerance, content (CRC32 / byte-by-byte), filename case.
- SFTP profiles with password/private-key auth, credentials in the OS keyring, remote folder browser, re-prompt on auth failure, retry on connection loss.
- Text compare: intra-line highlighting, synchronized scrolling, only-differences with context, encoding (UTF-8/UTF-16/Latin-1 + BOM) and EOL detection, ignore-whitespace.
