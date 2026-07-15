---
name: release
description: Checklist for cutting a new shankompare version — version bump locations, release notes, manual, packaging. Use when bumping the version or preparing a release/milestone completion.
---

# Cutting a release

## Version bump (two places, keep in sync)

1. `pyproject.toml` → `[project] version`
2. `src/shankompare/__init__.py` → `__version__`

Semver-ish: milestones bump the minor version (M4 → 0.3.0).

## User-facing docs (shown inside the app)

The Help menu renders these files directly (`main_window.py` → `_show_doc`):

- `docs/RELEASE-NOTES.md` — add a section for the new version at the top, matching the existing format. Every user-visible change goes here.
- `docs/MANUAL.md` — update for any new/changed feature or behavior.

## Project docs

- `docs/ROADMAP.md` — check off completed milestone items.
- `docs/REQUIREMENTS.md` — retag delivered items from [future] to [v1] where applicable.
- `CLAUDE.md` — update the "Current status" line.

## Verify, then package

Run the full check sequence from the `verify` skill (format, lint, pytest, launch the app once).

PyInstaller build (must run on each target OS — no cross-compiling):

```
pip install -e .[dev,package]
pyinstaller packaging/shankompare.spec --noconfirm
```

Output is a single self-contained executable: `dist/shankompare.exe` (Windows) / `dist/shankompare` (Ubuntu). First launch is slow (self-extracts) — that's normal.

## Commit

One commit for the release, message style matches history, e.g. `M4 complete (v0.3.0): sync, filters, hex compare, archives, manual`. Commit only when the user asks.
