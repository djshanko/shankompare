# shankompare — Release Notes

## 0.3.6 — 2026-08-10

A correctness and robustness release from a full code review: no new features, but several ways the app could mislead you, lose work, or refuse to start are gone.

**Fixed**

- **A file fixed by a copy could stay marked *different* forever.** With **Skip content if size+time match** unchecked, the automatic refresh after a file operation trusted size and modified time to decide what had changed — but copying preserves the source timestamp, so a pair that differed *only* in content looked untouched afterwards and kept its old verdict. That refresh now re-reads the content, which is what unchecking the option asks for in the first place. See the note in §4 of the manual: in that mode Refresh is a full re-read, and slower on large or remote trees.
- **A dropped SFTP connection no longer sinks a whole comparison or operation batch.** Errors during a transfer (as opposed to when opening the file) escaped as an unexpected internal error, abandoning everything queued behind them. They are now reported per file: the comparison marks that row and carries on, and a copy batch records the failure and continues with the rest.
- **Files from a remote server or archive can no longer be written outside the compared folder.** An entry whose *name* contained Windows path syntax — backslashes, or a drive letter — could escape the destination root when copied to a local side. Such a name is now refused.
- **A damaged settings or sessions file no longer stops the app from starting.** A config file truncated by a crash (or hand-edited into invalid JSON) raised before the main window existed, leaving no way in. Unreadable files are now set aside as `<name>.bad` and the app starts with defaults; a single malformed session or profile is skipped without costing the others. Saves are also written atomically, so an interrupted one leaves the previous version intact instead of a half-written file.
- **A failed login reported itself twice.** Cancelling the password re-prompt after an authentication failure raised a second dialog repeating the same message.
- **Hex compare rejects an oversized file before transferring it**, instead of downloading up to the (much larger) text limit first and refusing afterwards; the message now names the limit that actually applied.
- **A zip entry with a zeroed timestamp no longer fails the whole archive** — such entries show as dated at the epoch.

**Note:** if you run shankompare from a normal `pip install` rather than a source checkout or the packaged executable, **Help → User Manual** and the window icon now work; they were missing from the installed package.

## 0.3.5 — 2026-08-07

**New features**

- **Select files by status in the folder tab.** A new **Select** button sits next to **Show**, with the same status options — **Unchanged**, **Modified**, **Left orphans**, **Right orphans**, plus **All** and **Differences only**. Choosing one selects every visible file matching that status, ready for a batch copy, delete, or timestamp operation. Where **Show** decides what the tree displays, **Select** decides what is highlighted; folders are skipped so a chosen operation applies to individual files predictably.
- **Word wrap in text compare.** A new **Wrap** checkbox (Ctrl+Shift+W) wraps long lines to the pane width so you can read them without scrolling sideways. It is off by default, because wrapping a line onto extra rows can push its neighbour out of vertical alignment with the other pane.

## 0.3.4 — 2026-07-18

**New features**

- **Include filters.** The filters dialog now has an **Include names** field alongside the existing exclusions: when it is set, only files whose name matches one of the patterns are compared; leave it empty to include everything (the previous behaviour). Folders are never filtered out by include patterns, so subfolders are still walked and their matching files found. **Exclusions take priority** — a name matching both an include and an exclude pattern is excluded. Include patterns are saved with sessions.
- **Patterns can contain spaces.** Wrap a pattern in double quotes when the name has whitespace in it — `*.log "My Documents" "weekly report*.xlsx"`. Both filter fields show an example of this, and quoted patterns survive being saved and reopened.
- **Copy left/right path.** Right-click in the folder tab → **Copy left path** / **Copy right path** puts the selected entries' full paths on the clipboard, one per line. Local paths use the platform's native form; SFTP paths stay plain remote paths, ready to paste back into a path box.
- **Open a file that exists on only one side.** Orphan files now open in a compare tab (double-click, Enter, or right-click → *Open as text* / *Open as hex*) instead of doing nothing. The missing side shows as an empty pane labelled *(missing)*, so the content is readable — and saving that pane in Edit mode creates the file on that side.
- **Save session shows the sessions you already have.** **Session → Save current…** now lists the saved session names next to the name field. Click one to overwrite it — the button changes to **Overwrite** and asks for confirmation first — or type a new name to add one. Previously a name that happened to match an existing session replaced it silently.
- **The Show filter takes several categories at once.** The single-choice dropdown in the folder tab became a checkable menu: tick any combination of **Unchanged**, **Modified**, **Left orphans** and **Right orphans** (for example modified files *and* left orphans, which the old list couldn't express). The button text summarizes the selection, and **All** / **Differences only** presets are at the bottom of the menu.

**Changed**

- **Files still being compared now stay visible under every Show filter.** Previously a filter such as *Differences only* hid not-yet-checked rows, so results appeared to flicker in and out while a large or remote scan streamed in. They now always show, in orange, until their status is known.

**Note for existing sessions:** saved sessions load unchanged; they simply start with no include patterns.

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
