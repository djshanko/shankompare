"""Qt item model over the comparison result tree, with status filtering.

The model keeps a mirror tree of lightweight ``_Item`` wrappers so that
Qt's row bookkeeping stays consistent while the engine streams results in
from the worker thread (the engine mutates ``NodeResult.children`` before
the queued signal arrives; the mirror is only extended inside
begin/endInsertRows).
"""

from enum import Enum
from pathlib import PurePosixPath

from PySide6.QtCore import QAbstractItemModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor

from shankompare.compare import NodeResult, Status
from shankompare.vfs import EntryInfo

# shared default for Qt model-method signatures (B008: no call in defaults)
_ROOT_INDEX = QModelIndex()

STATUS_LABEL = {
    Status.SAME: "Same",
    Status.DIFFERENT: "Different",
    Status.LEFT_ONLY: "Left only",
    Status.RIGHT_ONLY: "Right only",
    Status.UNKNOWN: "Unknown",
}

_STATUS_COLOR_LIGHT = {
    Status.DIFFERENT: QColor("#c62828"),
    Status.LEFT_ONLY: QColor("#1565c0"),
    Status.RIGHT_ONLY: QColor("#2e7d32"),
    Status.UNKNOWN: QColor("#9e6a03"),
}

_STATUS_COLOR_DARK = {
    Status.DIFFERENT: QColor("#ef9a9a"),
    Status.LEFT_ONLY: QColor("#90caf9"),
    Status.RIGHT_ONLY: QColor("#a5d6a7"),
    Status.UNKNOWN: QColor("#ffcc80"),
}


def status_color(status: Status) -> QColor | None:
    from .theme import is_dark

    palette = _STATUS_COLOR_DARK if is_dark() else _STATUS_COLOR_LIGHT
    return palette.get(status)


def _fmt_size(entry: EntryInfo | None) -> str:
    if entry is None or entry.is_dir:
        return ""
    return f"{entry.size:,}"


def _fmt_mtime(entry: EntryInfo | None) -> str:
    if entry is None:
        return ""
    return entry.mtime.astimezone().strftime("%Y-%m-%d %H:%M:%S")


class _Item:
    __slots__ = ("node", "parent", "children", "row", "rel_path")

    def __init__(self, node: NodeResult, parent: "_Item | None", row: int, rel_path: PurePosixPath):
        self.node = node
        self.parent = parent
        self.children: list[_Item] = []
        self.row = row
        self.rel_path = rel_path


class FolderCompareModel(QAbstractItemModel):
    NodeRole = Qt.ItemDataRole.UserRole

    COLUMNS = ("Name", "Size (L)", "Modified (L)", "Size (R)", "Modified (R)", "Status")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: _Item | None = None
        self._by_node: dict[int, _Item] = {}

    # --- streaming updates (queued from the worker thread) --------------------

    def clear(self) -> None:
        self.beginResetModel()
        self._root = None
        self._by_node = {}
        self.endResetModel()

    def on_dir_scanned(self, node: NodeResult) -> None:
        if self._root is None:
            # first event is always the comparison root
            self._root = _Item(node, None, 0, PurePosixPath("."))
            self._by_node[id(node)] = self._root
        item = self._by_node.get(id(node))
        if item is None or item.children:
            return
        children = list(node.children)  # snapshot; the engine won't extend it further
        if not children:
            return
        self.beginInsertRows(self._index_for(item), 0, len(children) - 1)
        self._attach_children(item, children)
        self.endInsertRows()

    def on_content_checked(self, node: NodeResult) -> None:
        item = self._by_node.get(id(node))
        if item is not None:
            index = self._index_for(item)
            if index.isValid():
                last = index.siblingAtColumn(self.columnCount() - 1)
                self.dataChanged.emit(index, last)

    def set_result(self, root: NodeResult) -> None:
        """Full rebuild from the final tree once the comparison completes."""
        self.beginResetModel()
        self._by_node = {}
        self._root = _Item(root, None, 0, PurePosixPath("."))
        self._by_node[id(root)] = self._root
        stack = [self._root]
        while stack:
            item = stack.pop()
            self._attach_children(item, item.node.children)
            stack.extend(item.children)
        self.endResetModel()

    def _attach_children(self, item: _Item, children: list[NodeResult]) -> None:
        for row, child in enumerate(children):
            child_item = _Item(child, item, row, item.rel_path / child.name)
            item.children.append(child_item)
            self._by_node[id(child)] = child_item

    def _index_for(self, item: _Item) -> QModelIndex:
        if item.parent is None:
            return QModelIndex()
        return self.createIndex(item.row, 0, item)

    def item_at(self, index: QModelIndex) -> "_Item | None":
        if not index.isValid():
            return None
        return index.internalPointer()

    # --- QAbstractItemModel plumbing ------------------------------------------

    def index(self, row: int, column: int, parent: QModelIndex = _ROOT_INDEX) -> QModelIndex:
        parent_item = self._root if not parent.isValid() else parent.internalPointer()
        if parent_item is None or row >= len(parent_item.children):
            return QModelIndex()
        return self.createIndex(row, column, parent_item.children[row])

    def parent(self, index: QModelIndex = _ROOT_INDEX) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()
        item: _Item = index.internalPointer()
        if item.parent is None or item.parent.parent is None:
            return QModelIndex()
        return self.createIndex(item.parent.row, 0, item.parent)

    def rowCount(self, parent: QModelIndex = _ROOT_INDEX) -> int:
        if not parent.isValid():
            return len(self._root.children) if self._root is not None else 0
        if parent.column() != 0:
            return 0
        return len(parent.internalPointer().children)

    def columnCount(self, parent: QModelIndex = _ROOT_INDEX) -> int:
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item: _Item = index.internalPointer()
        node = item.node
        if role == Qt.ItemDataRole.DisplayRole:
            column = index.column()
            if column == 0:
                return node.name
            if column == 1:
                return _fmt_size(node.left)
            if column == 2:
                return _fmt_mtime(node.left)
            if column == 3:
                return _fmt_size(node.right)
            if column == 4:
                return _fmt_mtime(node.right)
            label = STATUS_LABEL[node.status]
            return f"{label} ⚠" if node.error else label
        if role == Qt.ItemDataRole.ForegroundRole:
            color = status_color(node.status)
            return QBrush(color) if color is not None else None
        if role == Qt.ItemDataRole.ToolTipRole:
            return node.error
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() in (1, 3):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == self.NodeRole:
            return item
        return None


class FilterMode(Enum):
    ALL = "All items"
    DIFFERENCES = "Differences only"
    MODIFIED = "Modified only"
    LEFT_ONLY = "Left orphans"
    RIGHT_ONLY = "Right orphans"


class StatusFilterProxy(QSortFilterProxyModel):
    """Shows a row if its status matches the mode, or any descendant's does."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = FilterMode.ALL

    def set_mode(self, mode: FilterMode) -> None:
        self.beginFilterChange()
        self._mode = mode
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if self._mode is FilterMode.ALL:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        item = model.data(index, FolderCompareModel.NodeRole)
        return item is not None and self._accepts(item.node)

    def _accepts(self, node: NodeResult) -> bool:
        if self._matches(node.status):
            return True
        return any(self._accepts(child) for child in node.children)

    def _matches(self, status: Status) -> bool:
        if self._mode is FilterMode.DIFFERENCES:
            return status is not Status.SAME
        if self._mode is FilterMode.MODIFIED:
            return status is Status.DIFFERENT
        if self._mode is FilterMode.LEFT_ONLY:
            return status is Status.LEFT_ONLY
        if self._mode is FilterMode.RIGHT_ONLY:
            return status is Status.RIGHT_ONLY
        return True
