# shankompare — Requirements

Feature specification derived from the original Beyond Compare 5 feature list (`General Features.md`), scoped for a personal tool whose primary use case is **local ↔ SFTP folder comparison**.

Tags:

- **[v1]** — required for the first usable release (milestones M1–M2)
- **[v1.x]** — planned shortly after v1 (milestone M3)
- **[future]** — backlog; the architecture must accommodate it, but no implementation is scheduled
- **[out of scope]** — deliberately not planned

## 1. General

| Requirement | Tag |
|---|---|
| Responsive, multithreaded interface — no comparison or transfer ever blocks the UI thread | [v1] |
| Runs on Windows 11 and Ubuntu 22.04+ from one codebase | [v1] |
| Unicode support for file paths and file content | [v1] |
| Save comparisons as sessions to load later | [v1.x] |
| Dark mode | [v1.x] |
| View Unix patch files as side-by-side comparison | [future] |
| Standalone text editor | [out of scope] |
| MBCS (non-Unicode legacy encodings) support | [future] |

### v1 detail — responsiveness

- Folder scans, content comparisons, and SFTP operations run on worker threads.
- The UI shows progress for scans longer than ~0.5 s and results stream in as subfolders complete.
- A running comparison can be cancelled.

## 2. Folder Compare

| Requirement | Tag |
|---|---|
| Compare two folders side by side in a tree view | [v1] |
| Any combination of sides: local ↔ local, local ↔ SFTP, SFTP ↔ SFTP | [v1] |
| Color highlighting: added (only on one side), modified, matching | [v1] |
| Automatically compare subfolders and expand them in place | [v1] |
| Display filters: show only differences / only added / only modified / all | [v1] |
| Comparison criteria: last modified time (with configurable tolerance, ≥2 s for FAT/SFTP granularity) | [v1] |
| Correct a skewed SFTP server clock when comparing modified times (opt-in, measured per connection) | [v1.x] |
| Comparison criteria: size | [v1] |
| Comparison criteria: file content (CRC32 or byte-by-byte) | [v1] |
| Comparison criteria: filename case sensitivity toggle | [v1] |
| Open a selected file pair in the text compare view | [v1] |
| File operations: copy, delete between sides, with background progress | [v1.x] |
| File operations: move, rename, set last modified time | [v1.x] |
| Dedicated synchronization commands (mirror, update) | [future] |
| Exclusion filters (name patterns, size, mtime) | [future] |
| Comparison criteria: DOS attributes, exe/dll versions, format-specific content | [out of scope] |
| Pause running operations | [future] |

## 3. Text Compare

| Requirement | Tag |
|---|---|
| Side-by-side display of two text files | [v1] |
| Color highlighting of differences within lines (intra-line diff) | [v1] |
| Jump to next/previous difference | [v1] |
| Display filter: show only differences (with context lines) | [v1] |
| Detect and handle encodings: UTF-8 (± BOM), UTF-16, Latin-1 fallback | [v1] |
| Handle mixed line endings (LF/CRLF) with an option to ignore EOL differences | [v1] |
| Option: ignore leading/trailing whitespace | [v1] |
| Inline editing with dynamic recomparison | [v1.x] |
| Adaptive gutter buttons for copying sections between sides | [v1.x] |
| Syntax highlighting | [future] |
| Find & replace | [future] |
| Formatted HTML view; line details as text/hex/character alignment | [out of scope] |

## 4. Virtual File System

| Requirement | Tag |
|---|---|
| Local drives (including network-mapped drives) | [v1] |
| SFTP (SSH) servers | [v1] |
| SFTP: named connection profiles (host, port, user, auth method, initial path) | [v1] |
| SFTP auth: password and private key file (with passphrase) | [v1] |
| SFTP: passwords/passphrases stored in the OS keyring, never in config files | [v1] |
| SFTP: multiple simultaneous connections (each compare side owns its connection) | [v1] |
| SFTP auth: SSH agent, keyboard-interactive | [future] |
| SFTP: resume interrupted transfers | [future] |
| FTP and FTP over SSL | [future] |
| Remote SMB servers via dedicated client (UNC paths already work as local paths on Windows) | [future] |
| Archive files: compare/expand as folders without extracting | [future] |

## 5. Binary Compare

Entire section **[future]**: hex display, inline editing, limit display to differences, wrap lines, find & replace.

## 6. Non-Functional

- **[v1]** Folder compare of trees with ~10,000 files completes without UI freezes; memory stays proportional to tree size, not file contents.
- **[v1]** SFTP errors (auth failure, dropped connection, permission denied) surface as clear messages, never tracebacks or hangs.
- **[v1]** Core logic (VFS, compare engine) importable and testable without Qt or a display.
- **[v1.x]** Distributable as a standalone executable per platform (PyInstaller).
