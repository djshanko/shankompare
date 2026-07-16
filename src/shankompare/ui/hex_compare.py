"""Side-by-side hex comparison view (read-only)."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from shankompare.compare import BlockKind, count_differing_bytes, format_hex_line, hex_rows
from shankompare.compare.hex import HexRow, ascii_char_span, hex_char_span

from .panes import (
    DiffPane,
    current_line_selection,
    diff_colors,
    line_selection,
    link_scrollbars,
    span_selection,
)

_MAX_SPAN_ROWS = 1500  # beyond this, per-byte highlighting is skipped (line bg only)


class HexCompareView(QWidget):
    refresh_requested = Signal()

    def __init__(self, left_title: str, right_title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[HexRow] = []
        self._display: list[HexRow | None] = []  # None = "⋯" separator line
        self._diff_selections: dict = {}

        self._left_info = QLabel(left_title)
        self._right_info = QLabel(right_title)
        self._status = QLabel("Loading…")

        self._only_diff = QCheckBox("Only differences")
        self._only_diff.setShortcut("Ctrl+D")
        self._only_diff.setToolTip("Hide unchanged rows (Ctrl+D)")
        self._context = QSpinBox()
        self._context.setRange(0, 100)
        self._context.setValue(2)
        self._context.setPrefix("context ")
        self._context.setToolTip(
            "Unchanged rows to keep around each difference (only differences mode)"
        )
        self._context.setEnabled(False)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setShortcut("F5")
        refresh_btn.setToolTip("Reload both files from disk / server (F5)")
        prev_btn = QPushButton("◀ Prev")
        next_btn = QPushButton("Next ▶")
        prev_btn.setShortcut("F7")
        next_btn.setShortcut("F8")
        prev_btn.setToolTip("Jump to the previous difference (F7)")
        next_btn.setToolTip("Jump to the next difference (F8)")

        self._only_diff.toggled.connect(self._on_only_diff_toggled)
        self._context.valueChanged.connect(self._render)
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        prev_btn.clicked.connect(lambda: self._goto_diff(-1))
        next_btn.clicked.connect(lambda: self._goto_diff(+1))

        self._left_pane = DiffPane()
        self._right_pane = DiffPane()
        link_scrollbars(self._left_pane, self._right_pane)
        self._left_pane.cursorPositionChanged.connect(self._push_selections)
        self._right_pane.cursorPositionChanged.connect(self._push_selections)

        titles = QHBoxLayout()
        titles.addWidget(self._left_info, 1)
        titles.addWidget(self._right_info, 1)

        controls = QHBoxLayout()
        controls.addWidget(self._only_diff)
        controls.addWidget(self._context)
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

    # --- data -------------------------------------------------------------------

    def on_hex_loaded(self, data) -> None:
        """Slot for DiffLoadWorker.hex_ready (bound method: queued to UI thread)."""
        self._left_size = len(data.left)
        self._right_size = len(data.right)
        self._rows = hex_rows(data.left, data.right)
        self._render()

    def show_error(self, message: str) -> None:
        self._status.setText(message)

    def refresh_theme(self) -> None:
        if self._rows:
            self._render()

    def _on_refresh_clicked(self) -> None:
        self._status.setText("Reloading…")
        self.refresh_requested.emit()

    def _on_only_diff_toggled(self, only_diff: bool) -> None:
        self._context.setEnabled(only_diff)
        self._render()

    # --- rendering -----------------------------------------------------------------

    def _visible_rows(self) -> list[HexRow | None]:
        if not self._only_diff.isChecked():
            return list(self._rows)
        context = self._context.value()
        keep = [False] * len(self._rows)
        for index, row in enumerate(self._rows):
            if row.is_diff:
                for k in range(max(0, index - context), min(len(self._rows), index + context + 1)):
                    keep[k] = True
        out: list[HexRow | None] = []
        pending_gap = False
        for index, row in enumerate(self._rows):
            if keep[index]:
                if pending_gap or (not out and index > 0):
                    out.append(None)
                pending_gap = False
                out.append(row)
            elif out:
                pending_gap = True
        if pending_gap:
            out.append(None)
        return out

    def _render(self) -> None:
        self._display = self._visible_rows()
        left_lines = []
        right_lines = []
        for row in self._display:
            if row is None:
                left_lines.append("⋯")
                right_lines.append("⋯")
            else:
                left_lines.append(format_hex_line(row.offset, row.left))
                right_lines.append(format_hex_line(row.offset, row.right))
        self._left_pane.setPlainText("\n".join(left_lines))
        self._right_pane.setPlainText("\n".join(right_lines))
        self._apply_highlights()
        self._update_status()

    def _apply_highlights(self) -> None:
        colors = diff_colors()
        left_selections: list[QTextEdit.ExtraSelection] = []
        right_selections: list[QTextEdit.ExtraSelection] = []
        diff_row_count = sum(1 for row in self._display if row is not None and row.is_diff)
        with_spans = diff_row_count <= _MAX_SPAN_ROWS
        for line, row in enumerate(self._display):
            if row is None:
                sep = colors[BlockKind.SEPARATOR]
                left_selections.append(line_selection(self._left_pane, line, sep))
                right_selections.append(line_selection(self._right_pane, line, sep))
                continue
            if not row.is_diff:
                continue
            bg = colors[BlockKind.REPLACE]
            left_selections.append(line_selection(self._left_pane, line, bg))
            right_selections.append(line_selection(self._right_pane, line, bg))
            if not with_spans:
                continue
            intra = colors["intra"]
            for byte_index in row.diff_bytes:
                for start, end in (hex_char_span(byte_index), ascii_char_span(byte_index)):
                    left_selections.append(span_selection(self._left_pane, line, start, end, intra))
                    right_selections.append(
                        span_selection(self._right_pane, line, start, end, intra)
                    )
        self._diff_selections = {
            self._left_pane: left_selections,
            self._right_pane: right_selections,
        }
        self._push_selections()

    def _push_selections(self) -> None:
        highlight = self.palette().highlight().color()
        highlight.setAlpha(55)
        for pane, diff_selections in self._diff_selections.items():
            marker = current_line_selection(pane, highlight)
            pane.setExtraSelections([*diff_selections, marker])

    def _update_status(self) -> None:
        differing = count_differing_bytes(self._rows)
        if differing == 0:
            self._status.setText(f"Files are identical ({self._left_size:,} bytes)")
        else:
            diff_rows = sum(1 for row in self._rows if row.is_diff)
            sizes = f"left {self._left_size:,} B · right {self._right_size:,} B"
            self._status.setText(f"{differing:,} differing byte(s) in {diff_rows} row(s) — {sizes}")

    # --- navigation --------------------------------------------------------------------

    def _diff_starts(self) -> list[int]:
        starts = []
        in_run = False
        for line, row in enumerate(self._display):
            is_diff = row is not None and row.is_diff
            if is_diff and not in_run:
                starts.append(line)
            in_run = is_diff
        return starts

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
