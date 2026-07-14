"""Side-by-side text comparison view.

Two modes:
- **Aligned** (default, read-only): padded rows keep both panes lined up;
  supports show-only-differences with context.
- **Edit**: each pane shows its raw file and is editable; the diff re-runs
  ~400 ms after typing stops. Copy-section buttons and Save work in both.
"""

from dataclasses import replace

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFontDatabase, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from shankompare.compare import (
    BlockKind,
    DecodedText,
    Row,
    TextDiffOptions,
    align_rows,
    apply_copy_section,
    block_index_for_left_line,
    condense_rows,
    diff_lines,
    diff_run_starts,
    encode_text,
)
from shankompare.compare.text import intraline_spans, split_lines

from .theme import is_dark

_LIGHT = {
    BlockKind.REPLACE: QColor("#fdecec"),
    BlockKind.DELETE: QColor("#e7f0fb"),
    BlockKind.INSERT: QColor("#e8f5e9"),
    BlockKind.SEPARATOR: QColor("#eeeeee"),
    "intra": QColor("#f5b5b5"),
    "pad": QColor("#f0f0f0"),
}
_DARK = {
    BlockKind.REPLACE: QColor("#4a2a2a"),
    BlockKind.DELETE: QColor("#26384f"),
    BlockKind.INSERT: QColor("#28402b"),
    BlockKind.SEPARATOR: QColor("#3a3a3a"),
    "intra": QColor("#7e3d3d"),
    "pad": QColor("#333333"),
}


def _colors() -> dict:
    return _DARK if is_dark() else _LIGHT


class _Pane(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._apply_interaction_flags()

    def setReadOnly(self, read_only: bool) -> None:  # noqa: N802 (Qt override)
        super().setReadOnly(read_only)
        self._apply_interaction_flags()

    def _apply_interaction_flags(self) -> None:
        # keep a visible, keyboard-movable cursor even while read-only
        if self.isReadOnly():
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )


class TextCompareView(QWidget):
    save_requested = Signal(str, bytes)  # side ("left"/"right"), encoded content
    refresh_requested = Signal()

    def __init__(self, left_title: str, right_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._left_title = left_title
        self._right_title = right_title
        self._left_data: DecodedText | None = None
        self._right_data: DecodedText | None = None
        self._blocks: list = []
        self._rows: list[Row] = []
        self._display_rows: list[Row] = []
        self._syncing = False
        self._updating = False
        self._dirty = {"left": False, "right": False}
        self._diff_selections: dict = {}

        self._left_info = QLabel(left_title)
        self._right_info = QLabel(right_title)
        self._status = QLabel("Loading…")

        self._edit_check = QCheckBox("Edit")
        self._ignore_ws = QCheckBox("Ignore whitespace")
        self._only_diff = QCheckBox("Only differences")
        self._context = QSpinBox()
        self._context.setRange(0, 100)
        self._context.setValue(3)
        self._context.setPrefix("context ")
        copy_rtl_btn = QPushButton("◀ Copy section")
        copy_ltr_btn = QPushButton("Copy section ▶")
        self._save_left = QPushButton("Save left")
        self._save_right = QPushButton("Save right")
        self._save_left.setEnabled(False)
        self._save_right.setEnabled(False)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Reload both files from disk / server")
        prev_btn = QPushButton("◀ Prev")
        next_btn = QPushButton("Next ▶")

        self._edit_check.toggled.connect(self._on_edit_toggled)
        self._ignore_ws.toggled.connect(self._recompute)
        self._only_diff.toggled.connect(self._render)
        self._context.valueChanged.connect(self._render)
        copy_ltr_btn.clicked.connect(lambda: self._copy_section("ltr"))
        copy_rtl_btn.clicked.connect(lambda: self._copy_section("rtl"))
        self._save_left.clicked.connect(lambda: self._save("left"))
        self._save_right.clicked.connect(lambda: self._save("right"))
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        prev_btn.clicked.connect(lambda: self._goto_diff(-1))
        next_btn.clicked.connect(lambda: self._goto_diff(+1))

        self._left_pane = _Pane()
        self._right_pane = _Pane()
        self._link_scrollbars()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(400)
        self._debounce.timeout.connect(self._on_edited)
        self._left_pane.textChanged.connect(lambda: self._on_text_changed("left"))
        self._right_pane.textChanged.connect(lambda: self._on_text_changed("right"))
        self._left_pane.cursorPositionChanged.connect(self._push_selections)
        self._right_pane.cursorPositionChanged.connect(self._push_selections)

        titles = QHBoxLayout()
        titles.addWidget(self._left_info, 1)
        titles.addWidget(self._right_info, 1)

        controls = QHBoxLayout()
        for widget in (self._edit_check, self._ignore_ws, self._only_diff, self._context):
            controls.addWidget(widget)
        controls.addWidget(copy_rtl_btn)
        controls.addWidget(copy_ltr_btn)
        controls.addWidget(self._save_left)
        controls.addWidget(self._save_right)
        controls.addWidget(refresh_btn)
        controls.addStretch(1)
        controls.addWidget(self._status)
        controls.addStretch(1)
        controls.addWidget(prev_btn)
        controls.addWidget(next_btn)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._left_pane)
        splitter.addWidget(self._right_pane)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.addLayout(titles)
        layout.addLayout(controls)
        layout.addWidget(splitter, 1)

    # --- data ------------------------------------------------------------------

    def set_data(self, left: DecodedText, right: DecodedText) -> None:
        self._left_data = left
        self._right_data = right
        self._left_info.setText(f"{self._left_title}   [{left.encoding} · {left.eol}]")
        self._right_info.setText(f"{self._right_title}   [{right.encoding} · {right.eol}]")
        self._set_dirty("left", False)
        self._set_dirty("right", False)
        self._recompute()

    def on_diff_loaded(self, data) -> None:
        """Slot for TextDiffWorker.finished — a bound method of this QObject,
        so Qt queues the call onto the UI thread (a lambda would run on the
        worker thread and crash inside Qt's painting/text machinery)."""
        self.set_data(data.left, data.right)

    def show_error(self, message: str) -> None:
        self._status.setText(message)

    def on_save_failed(self, message: str) -> None:
        self._status.setText(f"Save failed: {message}")

    def _on_refresh_clicked(self) -> None:
        if self._dirty["left"] or self._dirty["right"]:
            self._status.setText("Unsaved changes — save or discard them, then refresh.")
            return
        self._status.setText("Reloading…")
        self.refresh_requested.emit()

    def refresh_theme(self) -> None:
        if self._left_data is not None:
            self._render()

    @property
    def edit_mode(self) -> bool:
        return self._edit_check.isChecked()

    def _options(self) -> TextDiffOptions:
        return TextDiffOptions(ignore_whitespace=self._ignore_ws.isChecked())

    def _recompute(self) -> None:
        if self._left_data is None or self._right_data is None:
            return
        self._blocks = diff_lines(self._left_data.text, self._right_data.text, self._options())
        self._rows = align_rows(self._left_data.text, self._right_data.text, self._blocks)
        self._render()

    # --- editing ---------------------------------------------------------------

    def _on_edit_toggled(self, editing: bool) -> None:
        if self._left_data is None:
            return
        self._only_diff.setEnabled(not editing)
        self._context.setEnabled(not editing)
        if editing:
            self._only_diff.setChecked(False)
        self._left_pane.setReadOnly(not editing)
        self._right_pane.setReadOnly(not editing)
        self._render()

    def _on_text_changed(self, side: str) -> None:
        if self._updating or not self.edit_mode:
            return
        self._set_dirty(side)
        self._debounce.start()

    def _on_edited(self) -> None:
        if self._left_data is None or self._right_data is None or not self.edit_mode:
            return
        self._left_data = replace(self._left_data, text=self._left_pane.toPlainText())
        self._right_data = replace(self._right_data, text=self._right_pane.toPlainText())
        self._blocks = diff_lines(self._left_data.text, self._right_data.text, self._options())
        self._rows = align_rows(self._left_data.text, self._right_data.text, self._blocks)
        self._apply_highlights_raw()
        self._update_status()

    def _set_dirty(self, side: str, dirty: bool = True) -> None:
        self._dirty[side] = dirty
        self._save_left.setEnabled(self._dirty["left"])
        self._save_right.setEnabled(self._dirty["right"])

    def _save(self, side: str) -> None:
        data = self._left_data if side == "left" else self._right_data
        if data is None:
            return
        if self.edit_mode:  # flush any pending edits first
            self._on_edited()
            data = self._left_data if side == "left" else self._right_data
        self.save_requested.emit(side, encode_text(data.text, data.encoding, data.eol))

    def mark_saved(self, side: str) -> None:
        self._set_dirty(side, False)
        self._status.setText(f"Saved {side} side.")

    # --- copy sections -----------------------------------------------------------

    def _current_block_index(self) -> int | None:
        line = self._left_pane.textCursor().blockNumber()
        if self.edit_mode:
            return block_index_for_left_line(self._blocks, line)
        if 0 <= line < len(self._display_rows):
            index = self._display_rows[line].block_index
            if index is not None and self._blocks[index].kind is not BlockKind.EQUAL:
                return index
            return block_index_for_left_line(self._blocks, self._display_rows[line].left_no or 0)
        return block_index_for_left_line(self._blocks, 0)

    def _copy_section(self, direction: str) -> None:
        if self._left_data is None or self._right_data is None:
            return
        index = self._current_block_index()
        if index is None:
            return
        new_left, new_right = apply_copy_section(
            self._left_data.text, self._right_data.text, self._blocks[index], direction
        )
        self._left_data = replace(self._left_data, text=new_left)
        self._right_data = replace(self._right_data, text=new_right)
        self._set_dirty("right" if direction == "ltr" else "left")
        self._recompute()

    # --- rendering ---------------------------------------------------------------

    def _render(self) -> None:
        if self._left_data is None or self._right_data is None:
            return
        scroll = self._left_pane.verticalScrollBar().value()
        self._updating = True
        try:
            if self.edit_mode:
                self._left_pane.setPlainText(self._left_data.text)
                self._right_pane.setPlainText(self._right_data.text)
                self._apply_highlights_raw()
            else:
                rows = self._rows
                if self._only_diff.isChecked():
                    rows = condense_rows(self._rows, self._context.value())
                self._display_rows = rows
                left_text = "\n".join(r.left_text if r.left_text is not None else "" for r in rows)
                right_text = "\n".join(
                    r.right_text if r.right_text is not None else "" for r in rows
                )
                self._left_pane.setPlainText(left_text)
                self._right_pane.setPlainText(right_text)
                self._apply_highlights_aligned()
        finally:
            self._updating = False
        self._left_pane.verticalScrollBar().setValue(scroll)
        self._update_status()

    def _update_status(self) -> None:
        diff_count = len(diff_run_starts(self._rows))
        if diff_count == 0:
            note = " (ignoring whitespace)" if self._ignore_ws.isChecked() else ""
            self._status.setText(f"Files are identical{note}")
        else:
            self._status.setText(f"{diff_count} difference section(s)")

    def _apply_highlights_aligned(self) -> None:
        colors = _colors()
        left_selections: list[QTextEdit.ExtraSelection] = []
        right_selections: list[QTextEdit.ExtraSelection] = []
        for display_line, row in enumerate(self._display_rows):
            if row.kind is BlockKind.EQUAL:
                continue
            base = colors.get(row.kind)
            left_bg = base if row.left_text is not None else colors["pad"]
            right_bg = base if row.right_text is not None else colors["pad"]
            if left_bg is not None:
                left_selections.append(self._line_selection(self._left_pane, display_line, left_bg))
            if right_bg is not None:
                right_selections.append(
                    self._line_selection(self._right_pane, display_line, right_bg)
                )
            for start, end in row.left_spans:
                left_selections.append(
                    self._span_selection(self._left_pane, display_line, start, end, colors["intra"])
                )
            for start, end in row.right_spans:
                right_selections.append(
                    self._span_selection(
                        self._right_pane, display_line, start, end, colors["intra"]
                    )
                )
        self._set_diff_selections(left_selections, right_selections)

    def _apply_highlights_raw(self) -> None:
        colors = _colors()
        left_lines = split_lines(self._left_data.text)
        right_lines = split_lines(self._right_data.text)
        left_selections: list[QTextEdit.ExtraSelection] = []
        right_selections: list[QTextEdit.ExtraSelection] = []
        for block in self._blocks:
            if block.kind is BlockKind.EQUAL:
                continue
            left_bg = colors[BlockKind.REPLACE if block.kind is BlockKind.REPLACE else block.kind]
            for line in range(block.left_start, block.left_end):
                left_selections.append(self._line_selection(self._left_pane, line, left_bg))
            for line in range(block.right_start, block.right_end):
                right_selections.append(self._line_selection(self._right_pane, line, left_bg))
            if block.kind is BlockKind.REPLACE:
                pairs = min(block.left_end - block.left_start, block.right_end - block.right_start)
                for k in range(pairs):
                    i, j = block.left_start + k, block.right_start + k
                    left_spans, right_spans = intraline_spans(left_lines[i], right_lines[j])
                    for start, end in left_spans:
                        left_selections.append(
                            self._span_selection(self._left_pane, i, start, end, colors["intra"])
                        )
                    for start, end in right_spans:
                        right_selections.append(
                            self._span_selection(self._right_pane, j, start, end, colors["intra"])
                        )
        self._set_diff_selections(left_selections, right_selections)

    def _set_diff_selections(self, left: list, right: list) -> None:
        self._diff_selections = {self._left_pane: left, self._right_pane: right}
        self._push_selections()

    def _push_selections(self) -> None:
        """Diff highlights plus a semi-transparent current-line marker."""
        highlight = self.palette().highlight().color()
        highlight.setAlpha(55)
        for pane, diff_selections in self._diff_selections.items():
            current = QTextEdit.ExtraSelection()
            cursor = pane.textCursor()
            cursor.clearSelection()
            current.cursor = cursor
            current.format.setBackground(highlight)
            current.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            pane.setExtraSelections([*diff_selections, current])

    @staticmethod
    def _line_selection(pane: QPlainTextEdit, line: int, color: QColor) -> QTextEdit.ExtraSelection:
        selection = QTextEdit.ExtraSelection()
        block = pane.document().findBlockByNumber(line)
        selection.cursor = QTextCursor(block)
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        return selection

    @staticmethod
    def _span_selection(
        pane: QPlainTextEdit, line: int, start: int, end: int, color: QColor
    ) -> QTextEdit.ExtraSelection:
        selection = QTextEdit.ExtraSelection()
        block = pane.document().findBlockByNumber(line)
        length = len(block.text())
        start, end = min(start, length), min(end, length)
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        selection.cursor = cursor
        selection.format.setBackground(color)
        return selection

    # --- navigation and scrolling ---------------------------------------------------

    def _diff_starts(self) -> list[int]:
        if not self.edit_mode:
            return diff_run_starts(self._display_rows)
        return [max(b.left_start, 0) for b in self._blocks if b.kind is not BlockKind.EQUAL]

    def _goto_diff(self, step: int) -> None:
        starts = self._diff_starts()
        if not starts:
            return
        current = self._left_pane.textCursor().blockNumber()
        if step > 0:
            candidates = [i for i in starts if i > current]
            target = candidates[0] if candidates else starts[0]
        else:
            candidates = [i for i in starts if i < current]
            target = candidates[-1] if candidates else starts[-1]
        for pane in (self._left_pane, self._right_pane):
            block = pane.document().findBlockByNumber(min(target, pane.blockCount() - 1))
            pane.setTextCursor(QTextCursor(block))
            pane.centerCursor()

    def _link_scrollbars(self) -> None:
        pairs = [
            (self._left_pane.verticalScrollBar(), self._right_pane.verticalScrollBar()),
            (self._left_pane.horizontalScrollBar(), self._right_pane.horizontalScrollBar()),
        ]
        for a, b in pairs:
            a.valueChanged.connect(lambda value, other=b: self._sync_scroll(other, value))
            b.valueChanged.connect(lambda value, other=a: self._sync_scroll(other, value))

    def _sync_scroll(self, target, value: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            target.setValue(value)
        finally:
            self._syncing = False
