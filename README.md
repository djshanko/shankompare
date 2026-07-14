# shankompare

A lightweight, cross-platform file and folder comparison tool for **Windows** and **Ubuntu**, focused on the workflow of comparing local folders against **SFTP servers**.

Built as a personal, trimmed-down alternative to Beyond Compare 5: instead of reimplementing every feature, shankompare concentrates on the comparison workflows actually used day to day, on top of an architecture that leaves room to grow.

## Features

### Version 1 (in development)

- **Folder compare** — side-by-side tree view of two folders (local ↔ local, local ↔ SFTP, SFTP ↔ SFTP) with color-highlighted differences
- **SFTP support** — named connection profiles, password and private-key authentication, credentials stored in the OS keyring
- **Flexible comparison criteria** — last modified time, size, or file content
- **Text compare** — side-by-side diff with within-line highlighting, jump to next/previous difference, show-only-differences filter

### Planned

Folder synchronization and file operations, saved sessions, dark mode, binary/hex compare, archive files as folders, FTP/FTPS, exclusion filters, and more — see [docs/ROADMAP.md](docs/ROADMAP.md).

## Requirements

- Python 3.12 or newer
- Windows 11 or Ubuntu 22.04+ (other Linux distributions likely work but are untested)

## Quick Start

> Not yet available — the project is in the documentation/design phase. Setup instructions will land with milestone M1. Developers: see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## License

TBD (MIT suggested).
