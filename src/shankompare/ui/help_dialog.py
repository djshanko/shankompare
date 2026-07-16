"""Simple markdown viewer used for the user manual and release notes."""

from pathlib import Path

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout


class HelpDialog(QDialog):
    def __init__(
        self,
        title: str,
        markdown_path: Path | None = None,
        parent=None,
        *,
        markdown_text: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 640)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        if markdown_text is not None:
            browser.document().setMarkdown(markdown_text)
        elif markdown_path is not None:
            try:
                browser.document().setMarkdown(markdown_path.read_text(encoding="utf-8"))
            except OSError as exc:
                browser.setPlainText(f"Could not load {markdown_path.name}: {exc}")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(browser, 1)
        layout.addWidget(buttons)
