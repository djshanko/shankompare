"""Folder comparison result view: filter toolbar + streaming tree + file ops."""

from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from shankompare.compare import NodeResult, Status
from shankompare.vfs.ops import FileOp, OpKind

from .folder_model import _ROOT_INDEX, FilterMode, FolderCompareModel, StatusFilterProxy


class FolderCompareView(QWidget):
    open_diff_requested = Signal(object, str, str)  # (NodeResult, rel_path, mode)
    ops_requested = Signal(list)  # list[FileOp]
    refresh_requested = Signal()  # re-scan, re-checking content only for modified files

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._model = FolderCompareModel(self)
        self._proxy = StatusFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self._filter_combo = QComboBox()
        for mode in FilterMode:
            self._filter_combo.addItem(mode.value, mode)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setToolTip(
            "Re-scan, re-comparing content only for files modified since the last comparison"
        )
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.clicked.connect(self.refresh_requested)

        expand_btn = QPushButton("Expand all")
        collapse_btn = QPushButton("Collapse all")
        expand_btn.clicked.connect(self._tree_expand_all)
        collapse_btn.clicked.connect(self._tree_collapse_all)

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
        self._tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Show:"))
        toolbar.addWidget(self._filter_combo)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(expand_btn)
        toolbar.addWidget(collapse_btn)
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
        self._refresh_btn.setEnabled(True)

    # --- interaction -----------------------------------------------------------

    def _tree_expand_all(self) -> None:
        self._tree.expandAll()

    def _tree_collapse_all(self) -> None:
        self._tree.collapseAll()

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
            self.open_diff_requested.emit(node, str(item.rel_path), "auto")

    # --- file operations context menu ---------------------------------------------

    def _selected_items(self) -> list:
        items = []
        for index in self._tree.selectionModel().selectedRows(0):
            item = self._proxy.data(index, FolderCompareModel.NodeRole)
            if item is not None:
                items.append(item)
        return items

    def _show_context_menu(self, pos: QPoint) -> None:
        items = self._selected_items()
        if not items:
            return
        with_left = [i for i in items if i.node.left is not None]
        with_right = [i for i in items if i.node.right is not None]
        file_pairs = [
            i
            for i in items
            if not i.node.is_dir and i.node.left is not None and i.node.right is not None
        ]

        menu = QMenu(self)

        if len(items) == 1 and file_pairs:
            pair = file_pairs[0]
            for label, mode in (("Compare as text", "text"), ("Compare as hex", "hex")):
                action = menu.addAction(label)
                action.triggered.connect(
                    lambda _=False, i=pair, m=mode: self.open_diff_requested.emit(
                        i.node, str(i.rel_path), m
                    )
                )
            menu.addSeparator()

        def add(label: str, eligible: list, builder) -> None:
            action = menu.addAction(label)
            if eligible:
                ops = [builder(item) for item in eligible]
                action.triggered.connect(lambda _=False, o=ops: self.ops_requested.emit(o))
            else:
                action.setEnabled(False)

        add("Copy to right", with_left, lambda i: FileOp(OpKind.COPY_LTR, str(i.rel_path)))
        add("Copy to left", with_right, lambda i: FileOp(OpKind.COPY_RTL, str(i.rel_path)))
        menu.addSeparator()
        add("Delete on left", with_left, lambda i: FileOp(OpKind.DELETE_LEFT, str(i.rel_path)))
        add("Delete on right", with_right, lambda i: FileOp(OpKind.DELETE_RIGHT, str(i.rel_path)))
        menu.addSeparator()
        add(
            "Copy timestamp to right",
            file_pairs,
            lambda i: FileOp(OpKind.MTIME_LTR, str(i.rel_path)),
        )
        add(
            "Copy timestamp to left",
            file_pairs,
            lambda i: FileOp(OpKind.MTIME_RTL, str(i.rel_path)),
        )
        menu.addSeparator()
        rename_action = menu.addAction("Rename…")
        rename_action.setEnabled(len(items) == 1)
        if len(items) == 1:
            rename_action.triggered.connect(lambda _=False, i=items[0]: self._rename(i))

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _rename(self, item) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename", f"New name for {item.node.name}:", text=item.node.name
        )
        new_name = new_name.strip()
        if ok and new_name and new_name != item.node.name:
            self.ops_requested.emit([FileOp(OpKind.RENAME, str(item.rel_path), new_name=new_name)])

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
