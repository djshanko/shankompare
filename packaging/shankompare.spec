# PyInstaller spec: single-file windowed build for Windows and Ubuntu.
# One self-contained executable — nothing else to copy alongside it.
# (First launch is a little slower: the bundle unpacks itself to a temp dir.)
#
# Build from the repo root with the venv active:
#   pyinstaller packaging/shankompare.spec --noconfirm

a = Analysis(
    ["launcher.py"],
    pathex=["../src"],
    binaries=[],
    datas=[
        ("../assets/icons", "assets/icons"),
        ("../docs/MANUAL.md", "docs"),
        ("../docs/RELEASE-NOTES.md", "docs"),
    ],
    hiddenimports=["keyring.backends.Windows", "keyring.backends.SecretService"],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="shankompare",
    console=False,
    upx=False,
    icon="../assets/icons/shankompare.ico",
)
