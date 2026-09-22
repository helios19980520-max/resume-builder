# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the desktop build. Run from backend/:  pyinstaller resume_builder.spec
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
here = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(here, "static"), "static"),                          # built frontend (frontend/dist)
    (os.path.join(here, "app", "templates", "builtin"), os.path.join("app", "templates", "builtin")),
]
datas += collect_data_files("docx")          # python-docx default template + styles
datas += collect_data_files("certifi")
datas += collect_data_files("anthropic", include_py_files=False)

hiddenimports = (
    collect_submodules("uvicorn") + collect_submodules("anthropic") + collect_submodules("tavily")
    + collect_submodules("pydantic") + collect_submodules("docx") + ["pymupdf", "fitz", "multipart", "dotenv", "bs4", "httpx"]
)
if sys.platform.startswith("win"):
    hiddenimports += ["win32com", "win32com.client", "pythoncom", "pywintypes", "winreg"]

a = Analysis(
    ["desktop.py"],
    pathex=[here],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "pytest"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="ResumeBuilder",
    debug=False,
    strip=False,
    upx=False,
    console=True,          # keeps a small console window: closing it quits the app
    icon=None,
)
