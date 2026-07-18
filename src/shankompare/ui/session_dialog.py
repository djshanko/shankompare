"""Save-session dialog: name field plus the list of sessions already saved."""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class SaveSessionDialog(QDialog):
    """Prompts for a session name, offering the saved ones for overwrite."""

    def __init__(self, existing_names: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Save session")
        self._existing_names = list(existing_names)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Session name")
        self._name_edit.textChanged.connect(self._update_ok)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Session name:"))
        layout.addWidget(self._name_edit)

        if self._existing_names:
            self._list = QListWidget()
            self._list.addItems(self._existing_names)
            self._list.currentTextChanged.connect(self._name_edit.setText)
            self._list.itemDoubleClicked.connect(self._on_accept)
            layout.addWidget(QLabel("Existing sessions (click one to overwrite it):"))
            layout.addWidget(self._list, 1)

        layout.addWidget(self._buttons)
        self._name_edit.setFocus()
        self._update_ok()

    def session_name(self) -> str:
        return self._name_edit.text().strip()

    def _ok_button(self):
        return self._buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _update_ok(self) -> None:
        name = self.session_name()
        button = self._ok_button()
        button.setEnabled(bool(name))
        button.setText("Overwrite" if name in self._existing_names else "Save")

    def _on_accept(self, _item: object = None) -> None:
        # _item soaks up the QListWidgetItem that itemDoubleClicked sends.
        name = self.session_name()
        if not name:
            return
        if name in self._existing_names:
            reply = QMessageBox.question(self, "Save session", f"Overwrite session '{name}'?")
            if reply != QMessageBox.StandardButton.Yes:
                return  # stay open so another name can be chosen
        self.accept()
