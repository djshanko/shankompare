"""Folder comparison result view: filter toolbar + streaming tree."""

from PySide6.QtCore import QModelIndex, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from shankompare.compare import NodeResult, Status

from .folder_model import _ROOT_INDEX, FilterMode, FolderCompareModel, StatusFilterProxy


class FolderCompareView(QWidget):
    open_diff_requested = Signal(object, str)  # (NodeResult, rel_path)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = FolderCompareModel(self)
        self._proxy = StatusFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._filter_combo = QComboBox()
        for mode in FilterMode:
            self._filter_combo.addItem(mode.value, mode)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)

        prev_btn = QPushButton("◀ Prev diff")
        next_btn = QPushButton("Next diff ▶")
        prev_btn.clicked.connect(lambda: self._goto_diff(-1))
        next_btn.clicked.connect(lambda: self._goto_diff(+1))

        self._tree = QTreeView()
        self._tree.setModel(self._proxy)
        self._tree.setUniformRowHeights(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.setColumnWidth(0, 320)
        self._tree.setColumnWidth(2, 150)
        self._tree.setColumnWidth(4, 150)
        self._tree.doubleClicked.connect(self._on_activated)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Show:"))
        toolbar.addWidget(self._filter_combo)
        toolbar.addStretch(1)
        toolbar.addWidget(prev_btn)
        toolbar.addWidget(next_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self._tree, 1)

    # --- streaming slots (connected to CompareWorker signals) -----------------

    def compare_started(self) -> None:
        self._model.clear()

    def on_dir_scanned(self, node: NodeResult) -> None:
        self._model.on_dir_scanned(node)

    def on_content_checked(self, node: NodeResult) -> None:
        self._model.on_content_checked(node)

    def set_result(self, root: NodeResult) -> None:
        self._model.set_result(root)
        self.expand_differences()

    # --- interaction -----------------------------------------------------------

    def _on_filter_changed(self, _index: int) -> None:
        self._proxy.set_mode(self._filter_combo.currentData())
        self.expand_differences()

    def expand_differences(self, parent: QModelIndex = _ROOT_INDEX) -> None:
        for row in range(self._proxy.rowCount(parent)):
            index = self._proxy.index(row, 0, parent)
            item = self._proxy.data(index, FolderCompareModel.NodeRole)
            if item is not None and item.node.is_dir and item.node.status is not Status.SAME:
                self._tree.expand(index)
                self.expand_differences(index)

    def _on_activated(self, proxy_index: QModelIndex) -> None:
        item = self._proxy.data(proxy_index, FolderCompareModel.NodeRole)
        if item is None:
            return
        node = item.node
        if not node.is_dir and node.left is not None and node.right is not None:
            self.open_diff_requested.emit(node, str(item.rel_path))

    # --- next/previous difference ------------------------------------------------

    def _flat_visible(self, parent: QModelIndex, out: list[QModelIndex]) -> None:
        for row in range(self._proxy.rowCount(parent)):
            index = self._proxy.index(row, 0, parent)
            out.append(index)
            self._flat_visible(index, out)  # navigate into collapsed dirs too

    def _is_diff_row(self, index: QModelIndex) -> bool:
        item = self._proxy.data(index, FolderCompareModel.NodeRole)
        return item is not None and not item.node.is_dir and item.node.status is not Status.SAME

    def _goto_diff(self, step: int) -> None:
        rows: list[QModelIndex] = []
        self._flat_visible(QModelIndex(), rows)
        diff_positions = [i for i, index in enumerate(rows) if self._is_diff_row(index)]
        if not diff_positions:
            return
        current = self._tree.currentIndex().siblingAtColumn(0)
        position = rows.index(current) if current.isValid() and current in rows else -1
        if step > 0:
            candidates = [i for i in diff_positions if i > position]
            target = candidates[0] if candidates else diff_positions[0]
        else:
            candidates = [i for i in diff_positions if 0 <= i < position]
            target = candidates[-1] if candidates else diff_positions[-1]
        index = rows[target]
        self._tree.setCurrentIndex(index)
        self._tree.scrollTo(index, QTreeView.ScrollHint.PositionAtCenter)
