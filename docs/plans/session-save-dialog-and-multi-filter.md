# Plan: Session-save dialog with overwrite list + multi-select "Show:" filter

> **Status: implemented in 0.3.4.** Kept as the design record; the shipped behavior is
> described in `docs/MANUAL.md` §4 and §8. One deviation from the plan below: the initial
> button text is set directly in `__init__` rather than by calling `_on_filter_changed()`,
> which would touch the tree widget before it is constructed.

Two independent UI features. No core (`vfs`/`compare`/`sessions`) changes are needed except
where noted; both are pure `ui/` work and must not break the headless smoke tests.

---

## Feature 1 — Save-session dialog listing existing sessions

### Current behavior

`MainWindow._save_session()` (`src/shankompare/ui/main_window.py:518`) uses
`QInputDialog.getText` for a bare name prompt. A name matching an existing session silently
replaces it (line 537: `[s for s in self._sessions if s.name != name] + [session]`).

### Target behavior

A small custom dialog that shows:

- A line edit for the session name (pre-filled with nothing, focused).
- A list of already-saved session names below it. Clicking (single-click) a list item copies
  that name into the line edit; double-clicking accepts the dialog with that name.
- The OK button is disabled while the trimmed name is empty.
- The OK button's text switches between **"Save"** and **"Overwrite"** live, depending on
  whether the trimmed name matches an existing session (case-sensitive, same rule as the
  replacement logic).
- Accepting the dialog with a name that matches an existing session pops a confirmation
  (`QMessageBox.question`): "Overwrite session '<name>'?" with Yes/No. **No** returns to the
  dialog (does not close it) so the user can pick another name; **Yes** accepts.

### Implementation steps

1. **New file `src/shankompare/ui/session_dialog.py`** with class `SaveSessionDialog(QDialog)`:
   - Constructor: `def __init__(self, existing_names: list[str], parent: QWidget | None = None)`.
   - Widgets: `QLineEdit` (`self._name_edit`), `QListWidget` populated with `existing_names`,
     `QDialogButtonBox(Ok | Cancel)`.
   - Wire `self._name_edit.textChanged` → private `_update_ok()` which:
     - disables the OK button when `self._name_edit.text().strip()` is empty;
     - sets its text to `"Overwrite"` if the stripped name is in `existing_names`, else `"Save"`.
     Call `_update_ok()` once at the end of `__init__` so the initial state is correct.
   - Wire `QListWidget.currentTextChanged` → set the line edit's text.
     Wire `QListWidget.itemDoubleClicked` → `self.accept`.
   - Public accessor: `def session_name(self) -> str: return self._name_edit.text().strip()`.
   - Connect the button box's `accepted` signal to a private `_on_accept()` (not directly to
     `self.accept`), and route `itemDoubleClicked` there too:

     ```python
     def _on_accept(self) -> None:
         name = self.session_name()
         if name in self._existing_names:
             reply = QMessageBox.question(
                 self, "Save session", f"Overwrite session '{name}'?"
             )
             if reply != QMessageBox.StandardButton.Yes:
                 return  # stay in the dialog so another name can be chosen
         self.accept()
     ```

     Store `existing_names` on the instance in `__init__` for this check.
   - All signal connections here are UI-thread widget signals, so lambdas are allowed
     (per CLAUDE.md, the lambda ban applies only to worker signals).
   - Window title: `"Save session"`. Add a short `QLabel` above the list, e.g.
     `"Existing sessions (click to overwrite):"`, only when `existing_names` is non-empty;
     with no saved sessions, show just the name field.

2. **Rewrite `MainWindow._save_session()`** to use it:

   ```python
   def _save_session(self) -> None:
       dialog = SaveSessionDialog([s.name for s in self._sessions], parent=self)
       if dialog.exec() != QDialog.DialogCode.Accepted:
           return
       name = dialog.session_name()
       if not name:
           return
       ...  # rest unchanged from current implementation
   ```

   Keep the existing replace-by-name logic, `_build_menus()` call, and status-bar message
   exactly as they are. Import `SaveSessionDialog` (and `QDialog` if not already imported)
   in `main_window.py`.

3. **Tests** (`tests/test_ui_smoke.py` style — offscreen Qt, see existing tests for the
   pattern and the `qapp`/offscreen fixture used there):
   - Constructing `SaveSessionDialog(["a", "b"])` lists both names and OK starts disabled.
   - Typing `"a"` (via `dialog._name_edit.setText("a")`) enables OK with text `"Overwrite"`;
     typing `"c"` shows `"Save"`; whitespace-only (`"  "`) disables OK.
   - Selecting a list item fills the line edit.
   - Overwrite confirmation: monkeypatch `QMessageBox.question` (patch it on the
     `session_dialog` module's import) to return `No` and check `_on_accept()` leaves the
     dialog open (`dialog.result()` unchanged); patch it to return `Yes` and check the
     dialog is accepted. With a non-existing name, `_on_accept()` must accept without
     calling `question` at all (patch with a stub that fails the test if invoked).
   - Do **not** call `exec()` in tests (it blocks); drive the widgets directly.

---

## Feature 2 — Multi-select "Show:" filter

### Current behavior

`FolderCompareView` (`src/shankompare/ui/folder_view.py:35`) has a plain `QComboBox` filled
from `FilterMode` (`src/shankompare/ui/folder_model.py:207` — ALL, DIFFERENCES, MODIFIED,
LEFT_ONLY, RIGHT_ONLY). `StatusFilterProxy.set_mode(FilterMode)` maps the single mode to
status checks in `_matches()` (`folder_model.py:240`).

### Target behavior

The user can select any combination of status categories. Categories map 1:1 onto
`Status` values (`src/shankompare/compare/folder.py:108`):

| Checkbox label  | Status              |
|-----------------|---------------------|
| Unchanged       | `Status.SAME`       |
| Modified        | `Status.DIFFERENT`  |
| Left orphans    | `Status.LEFT_ONLY`  |
| Right orphans   | `Status.RIGHT_ONLY` |

`Status.UNKNOWN` (still being scanned/checked) is **always shown** regardless of selection —
otherwise rows would vanish mid-scan. (The old DIFFERENCES/MODIFIED modes hid UNKNOWN;
always-show is the deliberate new behavior so streaming results stay visible.)

The old presets are expressible as combinations: "All" = all four checked,
"Differences only" = all but Unchanged.

UI: replace the `QComboBox` with a **`QToolButton` with a popup `QMenu` of checkable
actions** (`QToolButton.InstantPopup`). This is simpler and more robust than a
checkable-item combo box (no view/model event hacks to keep the popup open). The button
text summarizes the selection.

### Implementation steps

1. **`src/shankompare/ui/folder_model.py` — replace mode with a status set:**
   - Delete the `FilterMode` enum.
   - In `StatusFilterProxy`: replace `self._mode` with
     `self._statuses: frozenset[Status]` defaulting to
     `frozenset({Status.SAME, Status.DIFFERENT, Status.LEFT_ONLY, Status.RIGHT_ONLY})`.
   - Replace `set_mode` with:

     ```python
     def set_statuses(self, statuses: frozenset[Status]) -> None:
         self.beginFilterChange()
         self._statuses = statuses
         self.endFilterChange()
     ```

   - `filterAcceptsRow`: short-circuit `return True` when all four statuses are selected
     (equivalent of the old ALL fast path).
   - `_matches(status)` becomes:
     `return status is Status.UNKNOWN or status in self._statuses`.
   - `_accepts` (descendant recursion) is unchanged.

2. **`src/shankompare/ui/folder_view.py` — the filter button:**
   - Remove `self._filter_combo`; add:

     ```python
     _FILTER_CHOICES: list[tuple[str, Status]] = [
         ("Unchanged", Status.SAME),
         ("Modified", Status.DIFFERENT),
         ("Left orphans", Status.LEFT_ONLY),
         ("Right orphans", Status.RIGHT_ONLY),
     ]
     ```

     (module-level constant), then in `__init__`:

     ```python
     self._filter_btn = QToolButton()
     self._filter_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
     menu = QMenu(self._filter_btn)
     self._filter_actions: dict[Status, QAction] = {}
     for label, status in _FILTER_CHOICES:
         action = menu.addAction(label)
         action.setCheckable(True)
         action.setChecked(True)
         action.toggled.connect(self._on_filter_changed)
         self._filter_actions[status] = action
     menu.addSeparator()
     menu.addAction("All", self._filter_select_all)
     menu.addAction("Differences only", self._filter_select_differences)
     self._filter_btn.setMenu(menu)
     ```

     The two preset actions are plain (non-checkable) shortcuts that set the four
     checkboxes accordingly (Differences only = everything except Unchanged).
   - In the toolbar layout (line ~94) put `self._filter_btn` where `_filter_combo` was.
   - Replace `_on_filter_changed`:

     ```python
     def _on_filter_changed(self, _checked: bool = False) -> None:
         selected = frozenset(
             status for status, action in self._filter_actions.items() if action.isChecked()
         )
         self._proxy.set_statuses(selected)
         self._filter_btn.setText(self._filter_summary(selected))
         self.expand_differences()
     ```

     `_filter_summary` returns `"Show: All"` when all four are checked,
     `"Show: Differences"` when exactly Unchanged is unchecked, `"Show: None"` for empty,
     otherwise a `+`-joined list of the checked labels (e.g. `"Show: Modified + Left orphans"`).
   - The preset slots (`_filter_select_all`, `_filter_select_differences`) set the four
     actions' checked states with `blockSignals` around the loop, then call
     `_on_filter_changed()` once, to avoid four proxy re-filters per preset click.
   - Since the button text now carries the "Show:" prefix, drop the separate
     `QLabel("Show:")` from the toolbar (and the now-unused `QLabel`/`QComboBox` imports
     if nothing else uses them). Import `QToolButton` and `QAction`
     (`PySide6.QtGui.QAction`).
   - Empty selection is allowed and simply shows only UNKNOWN rows (i.e. nothing after a
     finished scan); no special-casing needed.

3. **Fix the existing test** `tests/test_ui_smoke.py:73-83`: it imports `FilterMode` and
   calls `view._proxy.set_mode(FilterMode.DIFFERENCES)`. Change to:

   ```python
   from shankompare.compare import Status
   view._proxy.set_statuses(frozenset({Status.DIFFERENT, Status.LEFT_ONLY, Status.RIGHT_ONLY}))
   ```

4. **New tests** (same file/style):
   - Proxy: with a small result tree, `set_statuses({Status.LEFT_ONLY})` shows left-only
     rows (and their ancestor dirs via `_accepts` recursion) and hides SAME/DIFFERENT rows;
     all-four-selected shows everything; empty set hides everything except UNKNOWN.
   - View: toggling `view._filter_actions[Status.SAME]` off updates the proxy and the
     button text; the "Differences only" preset unchecks exactly Unchanged.

5. **Docs**: `_show_shortcuts` / `SHORTCUTS_MARKDOWN` and the in-app manual
   (`MANUAL.md` — see `doc_path` usage in `main_window.py`) mention the Show filter if they
   describe the old dropdown; grep for "Show" / "Differences only" in `src/shankompare/ui/`
   docs assets and update wording to describe the checkable menu.

---

## Verification (both features)

Run the `verify` project skill before committing: `ruff format .`, `ruff check .`,
`pytest` (UI tests run offscreen). Then launch `python -m shankompare` and manually check:

1. Session → Save current… shows the list; picking an existing name shows "Overwrite",
   asks for confirmation (No returns to the dialog, Yes replaces without duplicating);
   a new name appends; menu rebuilds with the new entry.
2. Folder compare: filter button defaults to "Show: All"; toggling categories live-filters
   the tree; presets work; filtering during an in-progress scan keeps UNKNOWN rows visible.

Do not bump the version; this is feature work for the next release (the `release` skill
handles version/docs when cutting it).
