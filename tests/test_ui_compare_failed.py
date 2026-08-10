"""Headless tests for how a failed comparison is reported to the user.

Each failure kind gets exactly one dialog: an auth failure is reported by the
retry path, a connection failure offers a retry, anything else is fatal.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from shankompare.sessions import ConnectionProfile
from shankompare.ui import main_window as mw
from shankompare.ui.main_window import MainWindow
from shankompare.ui.worker import LocalSide, SftpSide


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(monkeypatch):
    """Record every message box the window raises, answering each one."""
    seen: list[tuple[str, str]] = []

    def record(kind, answer=None):
        def show(_parent, title, text, *args, **kwargs):
            seen.append((kind, title))
            return answer

        return show

    monkeypatch.setattr(mw.QMessageBox, "critical", record("critical"))
    monkeypatch.setattr(mw.QMessageBox, "warning", record("warning"))
    monkeypatch.setattr(
        mw.QMessageBox, "question", record("question", QMessageBox.StandardButton.Cancel)
    )
    return seen


def _sftp_side() -> SftpSide:
    return SftpSide(ConnectionProfile(name="prod", host="example.com"), secret="stale")


def test_cancelled_auth_retry_shows_one_dialog(app, dialogs, monkeypatch):
    """The bug: declining the password prompt also raised a second, fatal dialog."""
    window = MainWindow()
    window._sides = (_sftp_side(), LocalSide("C:/tmp"))
    monkeypatch.setattr(mw, "prompt_secret", lambda *a: (None, False))  # user cancels
    monkeypatch.setattr(mw.ProfileStore, "delete_secret", lambda name: None)

    window._on_compare_failed("auth", "left", "authentication failed")

    assert dialogs == [("warning", "Authentication failed")]


def test_auth_failure_on_a_local_side_is_reported_once(app, dialogs):
    """No side to re-prompt for — still exactly one dialog."""
    window = MainWindow()
    window._sides = (LocalSide("C:/a"), LocalSide("C:/b"))

    window._on_compare_failed("auth", "left", "authentication failed")

    assert dialogs == [("critical", "Authentication failed")]


def test_connection_failure_offers_retry_only(app, dialogs):
    window = MainWindow()
    window._sides = (_sftp_side(), LocalSide("C:/tmp"))

    window._on_compare_failed("connection", "left", "connection refused")

    assert dialogs == [("question", "Connection failed")]


def test_other_failures_are_fatal(app, dialogs):
    window = MainWindow()
    window._sides = (LocalSide("C:/a"), LocalSide("C:/b"))

    window._on_compare_failed("vfs", "", "root directory does not exist")

    assert dialogs == [("critical", "Comparison failed")]
