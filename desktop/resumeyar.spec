# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

SRC = Path(SPECPATH).parent.parent
ASSETS = Path(SPECPATH) / "assets"

datas = [
    (str(SRC / "templates"), "templates"),
    (str(SRC / "static"), "static"),
    (str(ASSETS / "resumeyar.ico"), "assets"),
]
datas += collect_data_files("reportlab")
datas += collect_data_files("docx")
datas += collect_data_files("certifi")
datas += collect_data_files("webview")

hiddenimports = [
    "services",
    "services.ai",
    "services.cv_parse",
    "services.emailer",
    "services.jobsource",
    "services.pdfgen",
    "services.tailoring",
    "jinja2.ext",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr",
]

excludes = [
    "openai",
    "pydantic",
    "pydantic_core",
    "numpy",
    "onnxruntime",
    "pymupdf",
    "pymupdf4llm",
    "pypdfium2",
    "matplotlib",
    "pandas",
    "scipy",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "IPython",
    "pytest",
    "tkinter.test",
    "unittest",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Resumeyar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "resumeyar.ico"),
    version=str(Path(SPECPATH) / "version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Resumeyar",
)
