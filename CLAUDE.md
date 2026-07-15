# shankompare

Cross-platform (Windows + Ubuntu) file/folder comparison tool, built as a lighter-weight personal replacement for Beyond Compare 5. Primary use case: side-by-side comparison between local folders and SFTP servers, plus text file diff.

**Current status:** v0.3.2 — M4 (sync commands, exclusion filters (session-persisted), binary/hex compare, archives as folders, in-app manual + release notes) plus folder-tab fast Refresh (modified-only re-check, also used after file ops), expand/collapse all, line numbers in text compare, and SFTP remote clock-offset correction. Next: M5+ backlog (see docs/ROADMAP.md).

## Tech Stack

- Python 3.12+
- PySide6 (Qt 6) — GUI
- paramiko — SFTP
- keyring — credential storage
- pytest — tests
- ruff — lint + format

## Commands

Create environment and install (first time):

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

```bash
# Ubuntu (bash)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Day-to-day (with the venv active):

```
python -m shankompare      # run the app
pytest                     # run tests
ruff check .               # lint
ruff format .              # format
```

## Code Conventions

- Package layout: `src/shankompare/` with subpackages `vfs/`, `compare/`, `sessions/`, `ui/`.
- Type hints on all public functions and methods.
- **Core logic (`vfs`, `compare`, `sessions`) must not import Qt.** Only `ui/` may depend on PySide6. Core must be unit-testable headless.
- Long-running work (folder scans, SFTP transfers, diffs of large files) runs on worker threads; UI updates only via Qt signals.
- **Worker signals must connect to bound methods of QObjects, never lambdas/partials.** A lambda has no receiver, so Qt runs it on the emitting worker thread — touching widgets there crashes intermittently. Lambdas are fine only for UI-thread signals (button clicks).
- Credentials go through `keyring`, never in config files or code.
- Paths and file content are Unicode-safe end to end; never assume a filesystem encoding.

## Project Skills

Task-specific guides in `.claude/skills/` — invoke the matching skill before starting these tasks:

- `qt-threading` — any background/long-running work triggered from the UI (worker pattern, signal rules)
- `add-vfs-backend` — adding or changing a `FileSystem` backend (contract requirements, test suite)
- `verify` — checks to run before committing (format, lint, tests, headless UI tests)
- `release` — version bump checklist (version locations, in-app docs, packaging)

## Documentation

- docs/REQUIREMENTS.md — full feature spec, tagged [v1] / [future]
- docs/ARCHITECTURE.md — layer design (VFS, compare engine, sessions, UI)
- docs/ROADMAP.md — milestones M1–M4+
- docs/DEVELOPMENT.md — environment setup, packaging, workflow
- General Features.md — original feature list this project was scoped from
