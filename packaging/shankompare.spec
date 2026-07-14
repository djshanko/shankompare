# PyInstaller spec: one-folder windowed build for Windows and Ubuntu.
# Build from the repo root with the venv active:
#   pyinstaller packaging/shankompare.spec --noconfirm

a = Analysis(
    ["launcher.py"],
    pathex=["../src"],
    binaries=[],
    datas=[],
    hiddenimports=["keyring.backends.Windows", "keyring.backends.SecretService"],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="shankompare",
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="shankompare",
)
