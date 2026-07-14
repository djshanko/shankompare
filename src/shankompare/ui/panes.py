"""Shared building blocks for side-by-side compare views (text and hex)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QTextCursor, QTextFormat
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit

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


class DiffPane(QPlainTextEdit):
    """Monospace pane that keeps a visible, keyboard-movable cursor while read-only."""

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
        if self.isReadOnly():
            self.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )


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
