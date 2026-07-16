# shankompare — User Manual

shankompare compares folders and files side by side — between local disks, SFTP servers, and archive files — and lets you copy, delete, edit, and synchronize the differences. This manual covers version 0.3.3.

## 1. Getting started

1. Pick the **left** and **right** sides at the top of the *Folders* tab. Each side is one of:
   - a **local folder** — type the path or click **…** to browse;
   - an **SFTP profile** — select it in the dropdown; the path field holds the remote folder (click **…** to browse the server);
   - an **archive file** — a path (local or remote) ending in `.zip`, `.tar`, `.tar.gz/.tgz`, `.tar.bz2` or `.tar.xz` opens read-only as if it were a folder. Tip: archive timestamps are often imprecise (zip stores no time zone), so when comparing an archive against a folder, disable *Modified time* or enable a *Content* check for accurate results.
   - the **…** browse button (local and remote) lets you pick either a folder or a supported archive file — no need to type the archive path by hand.
2. Choose comparison criteria (see §3) and click **Compare**.
3. Results stream into the tree as folders are scanned. Colors: **red** = different, **blue** = only on the left, **green** = only on the right, **orange** = not compared (see the tooltip for the reason).

## 2. SFTP profiles

**Profiles…** opens the profile manager. A profile stores host, port, username, authentication (password or private-key file), and an initial remote path. Passwords and key passphrases are kept in the operating system's credential store (Windows Credential Manager / GNOME Keyring) — never in files. If a stored password stops working, shankompare drops it and asks again.

## 3. Comparison criteria and filters

Two files with the same name count as *different* when any enabled criterion says so:

- **Size** — byte sizes differ.
- **Modified time** — mtimes differ by more than the tolerance (default 2 s; SFTP and FAT store whole seconds).
- **Adjust remote clock** (SFTP only, off by default) — when a remote file's modified time is stamped by the *server's own clock* and that clock is wrong or unsynced, every such file looks modified. Tick this to have shankompare measure the offset on connect (by timestamping a temporary probe file in the remote root) and subtract it from remote mtimes. Leave it **off** if your remote files already carry correct times (e.g. they were uploaded with timestamps preserved), otherwise the correction would shift good times and *create* differences. Needs a writable remote root; if the probe can't write, no adjustment is made. The measured offset is written to the log (see Troubleshooting).
- **Content** — CRC32 (the default) or byte-by-byte. When a content check is on the bytes are authoritative: a size mismatch is *different* without a read, but a differing modified time alone is **not** — the files are read and their contents decide, so an identical file that got a fresh timestamp (common after an SFTP copy) is reported the same. **Skip content if size+time match** (on by default) is a shortcut: a pair whose size *and* modified time already agree is taken as equal without reading it. Uncheck it to force a full read on every pair, catching same-size, same-time files whose bytes differ; pairs whose time differs are read either way.
- **Case sensitive** — controls whether `README.txt` and `readme.txt` are the same entry.

**Filters…** opens the exclusion filters: name patterns (`*.log __pycache__` — they match files *and* folders, case-insensitively), a file-size range, and a modified-date window. Excluded entries are invisible to the comparison and to sync. A ● on the button means filters are active. Filters are saved with sessions.

## 4. Working with results

- **Show** dropdown filters the tree (differences only, orphans, modified).
- **Refresh** re-scans the sides but only re-reads content for files whose size or modified time changed since the last comparison — much faster than a full **Compare** on large or remote trees. File operations (copy/delete/…) use this same fast refresh when the queue finishes, so only the files they touched are re-checked.
- **Expand all / Collapse all** open or close every folder in the tree.
- **Prev/Next diff** jump between differing files.
- **Double-click** a file pair to open it in a compare tab — text or hex is chosen automatically. Right-click → *Compare as text* / *Compare as hex* to force one.
- **Right-click** offers file operations: copy to the other side, delete, rename, copy timestamp. Multi-select works. Operations run in a background queue with progress in the status bar, and the comparison re-runs when the queue finishes. Deletes always ask first.
- Archive sides are **read-only**: operations that would modify one fail with a clear message.

## 5. Synchronization

After a comparison, the **Sync** button offers:

- **Mirror left → right** — the right side becomes an exact copy of the left (copies + deletes).
- **Mirror right → left** — the reverse.
- **Update both** — copies anything missing to the other side; when a file pair differs, the newer file wins. Pairs whose timestamps are too close to call are skipped and listed.

Every command shows its full plan — operation counts, the first items, and any warnings — before anything runs.

## 6. Text compare

Side-by-side view with changed lines shaded and the changed characters within them darker. A line-number gutter down each pane shows the real source line numbers (blank on padding rows where one side has no matching line). The bar shows each file's encoding and line-ending style.

- **Only differences** hides unchanged regions (adjustable context).
- **Ignore whitespace** ignores leading/trailing whitespace when matching lines.
- **Copy section ◀ / ▶** copies the difference under the cursor to the other side.
- **Edit** makes both panes editable; the comparison re-runs as you type. **Save left/right** writes back preserving the original encoding, BOM, and line endings. **Undo/Redo** (Ctrl+Z / Ctrl+Y) act on the focused pane.
- **Refresh** reloads both files. While a pane has unsaved edits, the tab title shows a leading `*`, and closing or refreshing the tab asks whether to save or discard.

Files up to 32 MiB are supported.

## 7. Hex compare

Binary files (detected by NUL bytes, or forced via right-click) open as a classic hex dump — offset, 16 bytes, ASCII — with differing bytes highlighted in both the hex and ASCII columns. If the files differ in length, the overhang counts as a difference. *Only differences* and *Prev/Next* work as in text compare. Hex view is read-only and limited to 2 MiB per file.

## 8. Sessions

The **Session** menu saves the current setup — both sides, all criteria, and exclusion filters — under a name, and loads it back with one click. Sessions live in `sessions.json` in the config folder (`%APPDATA%\shankompare` on Windows, `~/.config/shankompare` on Ubuntu); passwords stay in the keyring.

## 9. Themes

**View → Theme**: *System* follows the OS, *Light*/*Dark* force a look (using Qt's Fusion style so the choice works on every platform, including Windows 10). All difference colors adapt.

## 10. Keyboard shortcuts

Every shortcut is also listed under **Help → Keyboard Shortcuts**. View-specific keys act on whichever tab is in front, so the same key does the matching thing in each view (e.g. F7/F8 always step to the previous/next difference).

**Anywhere**

| Action | Shortcut |
| --- | --- |
| Refresh the active view | F5 |
| Close current tab | Ctrl+W |
| Next / Previous tab | Ctrl+Tab / Ctrl+Shift+Tab |
| Jump to the Folders tab | Ctrl+1 |

**Folders tab**

| Action | Shortcut |
| --- | --- |
| Run comparison | F6 |
| Cancel comparison | Esc |
| Previous / Next difference | F7 / F8 |
| Copy selection to left / right | Alt+← / Alt+→ |
| Delete selection on left / right | Ctrl+Del / Ctrl+Shift+Del |
| Open selected pair | Enter |
| Rename selected | F2 |
| Expand all / Collapse all | Ctrl+E / Ctrl+Shift+E |
| Edit filters | Ctrl+L |

**Text compare tab**

| Action | Shortcut |
| --- | --- |
| Previous / Next difference | F7 / F8 |
| Copy section to left / right | Alt+← / Alt+→ |
| Undo / Redo in the focused pane | Ctrl+Z / Ctrl+Y |
| Save the focused pane | Ctrl+S |
| Toggle Edit / Ignore whitespace / Only differences | Ctrl+E / Ctrl+I / Ctrl+D |
| Reload both files | F5 |

**Hex compare tab**

| Action | Shortcut |
| --- | --- |
| Previous / Next difference | F7 / F8 |
| Toggle Only differences | Ctrl+D |
| Reload both files | F5 |

Deletes always ask for confirmation first, and Save is enabled only when the focused pane has unsaved edits — so the destructive keys can't fire by accident.

## 11. Troubleshooting

- **Wrong password** — shankompare discards the stored secret and re-prompts, then retries automatically.
- **Connection lost** — you're offered a Retry.
- **A folder shows “Unknown ⚠”** — it couldn't be read (usually permissions); hover for the exact error. The rest of the comparison is unaffected.
- **File too large** — text compare stops at 32 MiB, hex at 2 MiB, archives at 256 MiB.
- **Everything looks stale** — file operations re-compare automatically, but external changes don't; click **Refresh** in the folder tab to re-check only what changed, **Compare** for a full re-scan, or **Refresh** inside a compare tab.
- **Every SFTP file shows as different (by modified time)** — the remote clock and your local clock disagree. If the remote files are timestamped by the server's own clock, tick **Adjust remote clock** (see §3) to correct it; it needs a **writable** remote root. Check **Help → Open Log Folder** → `shankompare.log`: a successful probe logs `SFTP clock offset measured: …`, a failed one logs a `clock-offset probe failed …` warning. If ticking it makes files show up as ~the offset *older* instead, your remote files already had correct times — untick it.
- **Seeing the logs** — **Help → Open Log Folder** opens `shankompare.log` (in `%LOCALAPPDATA%\shankompare\Logs` on Windows, `~/.local/state/shankompare/log` or `~/.cache/shankompare/log` on Ubuntu). It records connections, the measured clock offset, and errors — useful when the status bar message flashes by too quickly.
