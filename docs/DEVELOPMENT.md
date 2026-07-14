# shankompare — Development Guide

## Environment setup

Prerequisite: Python 3.12+ (`python --version` / `python3 --version`).

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

### Ubuntu (bash)

```bash
sudo apt install python3-venv libxcb-cursor0   # libxcb-cursor0 is required by Qt 6
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Dependencies

Runtime:

| Package | Purpose |
|---|---|
| PySide6 | Qt 6 GUI toolkit |
| paramiko | SSH/SFTP client |
| keyring | Store SFTP passwords in Windows Credential Manager / GNOME Keyring |
| platformdirs | Per-OS config directory resolution |

Development (`[dev]` extra): pytest, ruff.

## Day-to-day commands

```
python -m shankompare      # run the app
pytest                     # run all tests
pytest tests/test_vfs.py   # run one test file
ruff check .               # lint
ruff format .              # format
```

## Testing notes

- Core layers (`vfs`, `compare`, `sessions`) have no Qt dependency — test them headless.
- The VFS contract test suite runs against every `FileSystem` implementation; run it against `SftpFileSystem` manually with a real server (a Docker `atmoz/sftp` container works well) — it is skipped unless the `SHANKOMPARE_TEST_SFTP_*` environment variables are set, documented in `tests/test_sftp_fs.py`.
- Comparer tests use an in-memory fake `FileSystem`, so no fixtures on disk.

## Packaging (M3)

- Windows: PyInstaller one-folder build → zip or Inno Setup installer.
- Ubuntu: PyInstaller build, or AppImage if distribution beyond the dev machine is ever needed.
- Build on each target OS (PyInstaller does not cross-compile).

## Working on this repo with Claude Code

- `CLAUDE.md` at the repo root is loaded automatically every session — keep commands and conventions there up to date as they change.
- For a new milestone or any multi-file feature, start in **plan mode** (Shift+Tab or `--permission-mode plan`) so the approach is agreed before code is written.
- Commit early and often; Claude Code's review tooling (`/code-review`) and checkpoints work off git.
- After a feature lands, ask Claude to update the relevant docs (REQUIREMENTS tags, ROADMAP checkmarks) in the same session.
