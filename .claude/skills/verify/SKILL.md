---
name: verify
description: How to verify a shankompare change end-to-end — tests, lint, headless UI tests, and launching the GUI. Use before committing any code change.
---

# Verifying changes

Run with the project venv active (`.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on Ubuntu). If commands fail with import errors, the venv is not active or `pip install -e .[dev]` hasn't been run.

## Standard check sequence

```
ruff format .        # format first, so lint sees final code
ruff check .         # must be clean (line length 100, rules E,F,W,I,UP,B,SIM)
pytest               # full suite; fast, no network needed
```

All three must pass before committing. Run a single file with `pytest tests/test_folder_compare.py` while iterating.

## What the suite covers (and doesn't)

- Core layers (`vfs/`, `compare/`, `sessions/`) are headless — they must never import Qt. If a core test suddenly needs Qt, the change is layered wrong.
- Every `FileSystem` backend runs the shared contract suite in `tests/vfs_contract.py`. If you touched a backend, its `tests/test_*_fs.py` exercises the contract automatically.
- SFTP contract tests against a real server are skipped unless `SHANKOMPARE_TEST_SFTP_*` env vars are set (see `tests/test_sftp_fs.py`); don't try to make them run in CI-style checks.
- UI tests (`test_ui_smoke.py`, `test_ui_m4.py`) run Qt offscreen — they set `QT_QPA_PLATFORM=offscreen` before importing PySide6 (which is why `test_ui_smoke.py` has an E402 ignore). New UI tests must follow the same pattern.

## Verifying UI changes for real

Offscreen tests catch wiring errors, not visual/behavioral ones. For UI changes, also launch the app:

```
python -m shankompare
```

Exercise the changed flow manually (or describe to the user what to click). Threading bugs (wrong-thread widget access) are *intermittent* — a single successful run does not prove a signal/slot change safe; re-check the rules in the `qt-threading` skill instead.

## After a feature lands

Update docs in the same session: `docs/REQUIREMENTS.md` tags, `docs/ROADMAP.md` checkmarks, and `docs/MANUAL.md` / `docs/RELEASE-NOTES.md` if user-visible (these two are shown in-app via Help menu).
