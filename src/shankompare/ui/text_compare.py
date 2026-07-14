"""Side-by-side text comparison view (read-only in v1; editing lands in M3)."""

from PySide6.QtCore import Qt
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
    compute_rows,
    condense_rows,
    diff_run_starts,
)

_LINE_BG = {
    BlockKind.REPLACE: QColor("#fdecec"),
    BlockKind.DELETE: QColor("#e7f0fb"),  # left only — blue, matching the folder view
    BlockKind.INSERT: QColor("#e8f5e9"),  # right only — green
    BlockKind.SEPARATOR: QColor("#eeeeee"),
}
_INTRA_BG = QColor("#f5b5b5")
_PAD_BG = QColor("#f0f0f0")


class _Pane(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))


class TextCompareView(QWidget):
    def __init__(self, left_title: str, right_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._left_data: DecodedText | None = None
        self._right_data: DecodedText | None = None
        self._display_rows: list[Row] = []
        self._syncing = False

        self._left_info = QLabel(left_title)
        self._right_info = QLabel(right_title)
        self._status = QLabel("Loading…")

        self._ignore_ws = QCheckBox("Ignore whitespace")
        self._only_diff = QCheckBox("Only differences")
        self._context = QSpinBox()
        self._context.setRange(0, 100)
        self._context.setValue(3)
        self._context.setPrefix("context ")
        prev_btn = QPushButton("◀ Prev")
        next_btn = QPushButton("Next ▶")

        self._ignore_ws.toggled.connect(self._recompute)
        self._only_diff.toggled.connect(self._render)
        self._context.valueChanged.connect(self._render)
        prev_btn.clicked.connect(lambda: self._goto_diff(-1))
        next_btn.clicked.connect(lambda: self._goto_diff(+1))

        self._left_pane = _Pane()
        self._right_pane = _Pane()
        self._link_scrollbars()

        titles = QHBoxLayout()
        titles.addWidget(self._left_info, 1)
        titles.addWidget(self._right_info, 1)

        controls = QHBoxLayout()
        controls.addWidget(self._ignore_ws)
        controls.addWidget(self._only_diff)
        controls.addWidget(self._context)
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

    # --- data -----------------------------------------------------------------

    def set_data(self, left: DecodedText, right: DecodedText) -> None:
        self._left_data = left
        self._right_data = right
        self._left_info.setText(f"{self._left_info.text()}   [{left.encoding} · {left.eol}]")
        self._right_info.setText(f"{self._right_info.text()}   [{right.encoding} · {right.eol}]")
        self._recompute()

    def show_error(self, message: str) -> None:
        self._status.setText(message)

    def _recompute(self) -> None:
        if self._left_data is None or self._right_data is None:
            return
        options = TextDiffOptions(ignore_whitespace=self._ignore_ws.isChecked())
        self._rows = compute_rows(self._left_data.text, self._right_data.text, options)
        self._render()

    # --- rendering ---------------------------------------------------------------

    def _render(self) -> None:
        if self._left_data is None:
            return
        if self._only_diff.isChecked():
            rows = condense_rows(self._rows, self._context.value())
            if not rows:
                rows = []
        else:
            rows = self._rows
        self._display_rows = rows

        left_text = "\n".join(r.left_text if r.left_text is not None else "" for r in rows)
        right_text = "\n".join(r.right_text if r.right_text is not None else "" for r in rows)
        self._left_pane.setPlainText(left_text)
        self._right_pane.setPlainText(right_text)
        self._apply_highlights()

        diff_count = len(diff_run_starts(self._rows))
        if diff_count == 0:
            note = " (ignoring whitespace)" if self._ignore_ws.isChecked() else ""
            self._status.setText(f"Files are identical{note}")
        else:
            self._status.setText(f"{diff_count} difference section(s)")

    def _apply_highlights(self) -> None:
        left_selections: list[QTextEdit.ExtraSelection] = []
        right_selections: list[QTextEdit.ExtraSelection] = []
        for display_line, row in enumerate(self._display_rows):
            if row.kind is BlockKind.EQUAL:
                continue
            left_bg, right_bg = self._row_colors(row)
            if left_bg is not None:
                left_selections.append(self._line_selection(self._left_pane, display_line, left_bg))
            if right_bg is not None:
                right_selections.append(
                    self._line_selection(self._right_pane, display_line, right_bg)
                )
            for start, end in row.left_spans:
                left_selections.append(
                    self._span_selection(self._left_pane, display_line, start, end)
                )
            for start, end in row.right_spans:
                right_selections.append(
                    self._span_selection(self._right_pane, display_line, start, end)
                )
        self._left_pane.setExtraSelections(left_selections)
        self._right_pane.setExtraSelections(right_selections)

    @staticmethod
    def _row_colors(row: Row) -> tuple[QColor | None, QColor | None]:
        base = _LINE_BG.get(row.kind)
        left = base if row.left_text is not None else _PAD_BG
        right = base if row.right_text is not None else _PAD_BG
        return left, right

    @staticmethod
    def _line_selection(pane: QPlainTextEdit, line: int, color: QColor) -> QTextEdit.ExtraSelection:
        selection = QTextEdit.ExtraSelection()
        block = pane.document().findBlockByNumber(line)
        cursor = QTextCursor(block)
        selection.cursor = cursor
        selection.format.setBackground(color)
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        return selection

    @staticmethod
    def _span_selection(
        pane: QPlainTextEdit, line: int, start: int, end: int
    ) -> QTextEdit.ExtraSelection:
        selection = QTextEdit.ExtraSelection()
        block = pane.document().findBlockByNumber(line)
        length = len(block.text())
        start, end = min(start, length), min(end, length)
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + start)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        selection.cursor = cursor
        selection.format.setBackground(_INTRA_BG)
        return selection

    # --- navigation and scrolling ---------------------------------------------------

    def _goto_diff(self, step: int) -> None:
        starts = diff_run_starts(self._display_rows)
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
            block = pane.document().findBlockByNumber(target)
            cursor = QTextCursor(block)
            pane.setTextCursor(cursor)
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
