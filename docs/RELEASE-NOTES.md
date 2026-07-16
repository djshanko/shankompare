# shankompare — Release Notes

## 0.3.3 — 2026-07-16

**New features**

- **Keyboard shortcuts across every view.** Refresh (F5), run/cancel comparison (F6/Esc), prev/next difference (F7/F8), copy to left/right (Alt+←/Alt+→), save the focused pane (Ctrl+S), close/switch tabs (Ctrl+W, Ctrl+Tab), and more — the full list is under **Help → Keyboard Shortcuts** and in the manual. View-specific keys act on whichever tab is in front.
- **Undo/redo in text compare.** Undo/Redo buttons and Ctrl+Z / Ctrl+Y act on the focused pane's edits in Edit mode.
- **Unsaved-edit protection in text compare.** A tab whose pane has unsaved edits shows a leading `*` in its title, and closing or refreshing that tab — or quitting the app — asks whether to save or discard, so edits can't be lost by accident.

**Changed**

- **Content check is now authoritative when it runs, and mtime differences no longer force a "different" verdict.** Previously an enabled content check still marked a pair *different* purely because their modified times differed. Now, with a content check on: a size mismatch is *different* without a read (different sizes prove different bytes), but a differing modified time triggers a read and the bytes decide — so an identical file that got a fresh timestamp on an SFTP copy is correctly reported the same.
- **New "Skip content if size+time match" option** (next to the content dropdown, on by default). When on, a pair whose size *and* modified time already agree is taken as equal without reading it — content is not re-run on files the folder tab already shows as matching. Uncheck it to force a full content read on every pair, catching same-size, same-time files whose bytes differ. Pairs whose time differs are read either way. Saved with sessions.
- **Content check now defaults to CRC32** (was "No content check"). New comparisons verify content by CRC32 out of the box; switch back to "No content check" or byte-by-byte in the dropdown as needed.

## 0.3.2 — 2026-07-16

**New features**

- **Remote clock-offset correction (opt-in)** — a new **Adjust remote clock** checkbox measures the SFTP server's clock on connect (by timestamping a temporary probe file) and corrects modified times by that offset. Enable it when your remote files are timestamped by the server's *own* clock and that clock is skewed; leave it off (the default) when remote files already carry correct times, so the offset isn't applied where it isn't wanted. The setting is saved with sessions.
- **Log file** — output now goes to a rotating `shankompare.log` (previously only the console, which a windowed build doesn't have). Open its folder from **Help → Open Log Folder**. The measured clock offset and any probe failure are recorded there.

## 0.3.1 — 2026-07-15

**New features**

- **Fast Refresh in the folder tab** — re-scans both sides but only re-reads content for files whose size or modified time changed since the last comparison, instead of re-hashing everything. Much quicker on large or SFTP trees.
- **Refresh after file operations** — copy/delete/rename now re-check only the files they touched (via the same fast refresh) rather than running a full re-compare.
- **Expand all / Collapse all** buttons in the folder tab.
- **Line numbers in text compare** — a gutter down each pane shows the real source line numbers, left blank on padding rows where one side has no matching line.

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
