"""PyInstaller entry point (the frozen app can't use ``python -m``)."""

import sys

from shankompare.ui.app import run

if __name__ == "__main__":
    sys.exit(run())
