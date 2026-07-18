"""Dialog for editing comparison filters (name globs, size range, mtime window)."""

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from shankompare.compare import CompareFilters, format_globs, parse_globs, parse_size


def _format_size(value: int | None) -> str:
    if value is None:
        return ""
    for suffix, factor in (("G", 1024**3), ("M", 1024**2), ("k", 1024)):
        if value % factor == 0 and value >= factor:
            return f"{value // factor}{suffix}"
    return str(value)


class FiltersDialog(QDialog):
    def __init__(self, filters: CompareFilters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filters")
        self._result: CompareFilters | None = None

        self._include_globs = QLineEdit(format_globs(filters.include_globs))
        self._include_globs.setPlaceholderText('e.g. *.py *.txt "weekly report*.xlsx"')
        self._globs = QLineEdit(format_globs(filters.exclude_globs))
        self._globs.setPlaceholderText('e.g. *.log __pycache__ "My Documents"')
        self._min_size = QLineEdit(_format_size(filters.min_size))
        self._min_size.setPlaceholderText("e.g. 1k — empty = no limit")
        self._max_size = QLineEdit(_format_size(filters.max_size))
        self._max_size.setPlaceholderText("e.g. 100M — empty = no limit")

        self._after_check = QCheckBox("Only files modified after:")
        self._after_edit = QDateTimeEdit()
        self._after_edit.setCalendarPopup(True)
        self._after_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        self._before_check = QCheckBox("Only files modified before:")
        self._before_edit = QDateTimeEdit()
        self._before_edit.setCalendarPopup(True)
        self._before_edit.setDisplayFormat("yyyy-MM-dd HH:mm")

        now = QDateTime.currentDateTime()
        for check, edit, value in (
            (self._after_check, self._after_edit, filters.modified_after),
            (self._before_check, self._before_edit, filters.modified_before),
        ):
            if value is not None:
                check.setChecked(True)
                edit.setDateTime(QDateTime(value.astimezone()))
            else:
                edit.setDateTime(now)
            edit.setEnabled(check.isChecked())
            check.toggled.connect(edit.setEnabled)

        form = QFormLayout()
        form.addRow("Include names:", self._include_globs)
        form.addRow("Exclude names:", self._globs)
        form.addRow("Min file size:", self._min_size)
        form.addRow("Max file size:", self._max_size)
        after_row = QHBoxLayout()
        after_row.addWidget(self._after_check)
        after_row.addWidget(self._after_edit, 1)
        form.addRow(after_row)
        before_row = QHBoxLayout()
        before_row.addWidget(self._before_check)
        before_row.addWidget(self._before_edit, 1)
        form.addRow(before_row)

        hint = QLabel(
            "Include patterns limit which files are compared; leave empty to include "
            "everything. Exclude patterns remove files and folders, and win over "
            "include patterns. Matching is case-insensitive. "
            "Include, size and date limits apply to files only, so folders are always "
            "walked."
        )
        hint.setWordWrap(True)

        clear_btn = QPushButton("Clear all")
        clear_btn.clicked.connect(self._clear)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.addButton(clear_btn, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)

    def _clear(self) -> None:
        self._include_globs.clear()
        self._globs.clear()
        self._min_size.clear()
        self._max_size.clear()
        self._after_check.setChecked(False)
        self._before_check.setChecked(False)

    def _on_accept(self) -> None:
        try:
            min_size = parse_size(self._min_size.text())
            max_size = parse_size(self._max_size.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Filters", str(exc))
            return
        modified_after = None
        if self._after_check.isChecked():
            modified_after = self._after_edit.dateTime().toPython().astimezone()
        modified_before = None
        if self._before_check.isChecked():
            modified_before = self._before_edit.dateTime().toPython().astimezone()
        self._result = CompareFilters(
            exclude_globs=parse_globs(self._globs.text()),
            include_globs=parse_globs(self._include_globs.text()),
            min_size=min_size,
            max_size=max_size,
            modified_after=modified_after,
            modified_before=modified_before,
        )
        self.accept()

    def filters(self) -> CompareFilters:
        assert self._result is not None  # only valid after accept
        return self._result
