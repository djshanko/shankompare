# shankompare

A lightweight, cross-platform file and folder comparison tool for **Windows** and **Ubuntu**, focused on the workflow of comparing local folders against **SFTP servers**.

Built as a personal, trimmed-down alternative to Beyond Compare 5: instead of reimplementing every feature, shankompare concentrates on the comparison workflows actually used day to day, on top of an architecture that leaves room to grow.

## Features

### Current (v1.x)

- **Folder compare** — live-streaming side-by-side tree of two folders (local ↔ local, local ↔ SFTP, SFTP ↔ SFTP) with color-highlighted differences, display filters, and next/previous-difference navigation
- **SFTP support** — named connection profiles, password and private-key authentication, credentials in the OS keyring, remote folder browser, automatic re-prompt on auth failure
- **Flexible comparison criteria** — last modified time (with tolerance), size, file content (CRC32 or byte-by-byte), filename case sensitivity
- **Text compare** — side-by-side diff with within-line highlighting, encoding/EOL detection, show-only-differences, inline editing with live recompare, copy sections between sides, save back preserving encoding
- **File operations** — copy, delete, rename, and timestamp sync straight from the folder tree, queued in the background with progress
- **Sessions & themes** — save/load comparisons as named sessions; light, dark, or follow-OS theme

### Planned

Dedicated sync commands, binary/hex compare, archive files as folders, FTP/FTPS, exclusion filters, and more — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Requirements

- Python 3.12 or newer
- Windows 11 or Ubuntu 22.04+ (other Linux distributions likely work but are untested)

## Quick Start

```
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows;  Ubuntu: source .venv/bin/activate
pip install -e .
python -m shankompare
```

Developers: see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## License

TBD (MIT suggested).
