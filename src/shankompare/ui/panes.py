"""Shared building blocks for side-by-side compare views (text and hex)."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPalette, QTextCursor, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from shankompare.compare import BlockKind

from .theme import is_dark

_LIGHT = {
    BlockKind.REPLACE: QColor("#fdecec"),
    BlockKind.DELETE: QColor("#e7f0fb"),  # left only — blue, matching the folder view
    BlockKind.INSERT: QColor("#e8f5e9"),  # right only — green
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


def diff_colors() -> dict:
    return _DARK if is_dark() else _LIGHT


class _LineNumberArea(QWidget):
    """Gutter widget painted by its owning ``DiffPane``."""

    def __init__(self, pane: "DiffPane") -> None:
        super().__init__(pane)
        self._pane = pane

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        return QSize(self._pane.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._pane.paint_line_numbers(event)


class DiffPane(QPlainTextEdit):
    """Monospace pane that keeps a visible, keyboard-movable cursor while read-only.

    Optionally shows a line-number gutter: call ``set_line_numbers`` to display
    a fixed number per display row (aligned view, where rows may be padding),
    or ``set_sequential_numbering`` for plain 1..N (raw/edit view). With neither
    the gutter has zero width and is invisible (e.g. the hex view).
    """

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self._apply_interaction_flags()

        self._numbers: list[int | None] = []
        self._sequential = False
        self._gutter = _LineNumberArea(self)
        self.blockCountChanged.connect(self._refresh_gutter_width)
        self.updateRequest.connect(self._on_update_request)
        self._refresh_gutter_width()

    def setReadOnly(self, read_only: bool) -> None:  # noqa: N802 (Qt override)
        super().setReadOnly(read_only)
        self._apply_interaction_flags()

    def _apply_interaction_flags(self) -> None:
        if self.isReadOnly():
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )

    # --- line-number gutter ----------------------------------------------------

    def set_line_numbers(self, numbers: list[int | None]) -> None:
        """Show ``numbers[i]`` beside display row i; ``None`` leaves a blank."""
        self._sequential = False
        self._numbers = numbers
        self._refresh_gutter_width()
        self._gutter.update()

    def set_sequential_numbering(self, enabled: bool) -> None:
        """Number rows 1..N by document position (used for raw/editable text)."""
        self._sequential = enabled
        self._numbers = []
        self._refresh_gutter_width()
        self._gutter.update()

    def _max_number(self) -> int:
        if self._sequential:
            return self.blockCount()
        return max((n for n in self._numbers if n is not None), default=0)

    def line_number_area_width(self) -> int:
        top = self._max_number()
        if top <= 0:
            return 0
        digits = len(str(top))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _refresh_gutter_width(self, _count: int = 0) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._refresh_gutter_width()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def _number_for_block(self, block_number: int) -> int | None:
        if self._sequential:
            return block_number + 1
        if 0 <= block_number < len(self._numbers):
            return self._numbers[block_number]
        return None

    def paint_line_numbers(self, event) -> None:
        width = self.line_number_area_width()
        if width == 0:
            return
        palette = self.palette()
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), palette.color(QPalette.ColorRole.Window))
        painter.setPen(palette.color(QPalette.ColorRole.PlaceholderText))
        block = self.firstVisibleBlock()
        offset = self.contentOffset()
        top = self.blockBoundingGeometry(block).translated(offset).top()
        line_height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + self.blockBoundingRect(block).height()
            if block.isVisible() and bottom >= event.rect().top():
                number = self._number_for_block(block.blockNumber())
                if number is not None:
                    painter.drawText(
                        0,
                        int(top),
                        width - 5,
                        line_height,
                        int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                        str(number),
                    )
            block = block.next()
            top = bottom


def link_scrollbars(left: QPlainTextEdit, right: QPlainTextEdit) -> None:
    """Keep two panes' scrollbars in lockstep (UI-thread signals only)."""
    syncing = [False]

    def follower(target):
        def sync(value: int) -> None:
            if syncing[0]:
                return
            syncing[0] = True
            try:
                target.setValue(value)
            finally:
                syncing[0] = False

        return sync

    pairs = [
        (left.verticalScrollBar(), right.verticalScrollBar()),
        (left.horizontalScrollBar(), right.horizontalScrollBar()),
    ]
    for a, b in pairs:
        a.valueChanged.connect(follower(b))
        b.valueChanged.connect(follower(a))


def line_selection(pane: QPlainTextEdit, line: int, color: QColor) -> QTextEdit.ExtraSelection:
    selection = QTextEdit.ExtraSelection()
    block = pane.document().findBlockByNumber(line)
    selection.cursor = QTextCursor(block)
    selection.format.setBackground(color)
    selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
    return selection


def span_selection(
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


def current_line_selection(pane: QPlainTextEdit, color: QColor) -> QTextEdit.ExtraSelection:
    selection = QTextEdit.ExtraSelection()
    cursor = pane.textCursor()
    cursor.clearSelection()
    selection.cursor = cursor
    selection.format.setBackground(color)
    selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
    return selection
