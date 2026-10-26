# PyInstaller build of the desktop application:  python -m PyInstaller --noconfirm --clean ifield.spec
# Output: dist\iFieldDataProcessing\iField Data Processing.exe (one folder, see build.ps1 for the zip/installer).
import os
import sys

sys.path.insert(0, os.getcwd())
import app.core  # noqa: E402,F401  (collections aliases needed to import savReaderWriter)
import savReaderWriter  # noqa: E402

from app import __version__  # noqa: E402

SAV_DIR = os.path.dirname(savReaderWriter.__file__)

datas = [
    ("app/gui/app.ico", "app/gui"),
    ("template/TemplateProject.mdd", "template"),
    ("dms/OutputDDFFile.dms", "dms"),
    ("projects/VNXXXXXXX_TEMPLATE", "projects/VNXXXXXXX_TEMPLATE"),
    # savReaderWriter loads its I/O DLLs from <exe folder>\savReaderWriter\spssio\win64 when frozen.
    (os.path.join(SAV_DIR, "spssio", "win64"), "savReaderWriter/spssio/win64"),
]

a = Analysis(
    ["ifield_app.py"],
    # savReaderWriter imports its own modules as top-level ones (`from savWriter import *`).
    pathex=[os.getcwd(), SAV_DIR],
    datas=datas,
    # win32timezone: imported by pywin32 at runtime when a COM value is a date.
    hiddenimports=["win32com.client", "pythoncom", "pywintypes", "win32timezone", "openpyxl", "xlsxwriter",
                   "py3k", "error", "generic", "header", "savReader", "savWriter", "savHeaderReader", "savReaderNp"],
    # Optional pandas/openpyxl dependencies that happen to be installed but are never used (~200 MB).
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "scipy", "numba", "llvmlite", "pyarrow", "PIL", "lxml",
              "sqlalchemy", "aiohttp", "greenlet", "zstandard", "fsspec", "jinja2",
              "PySide6.QtNetwork", "PySide6.QtWebEngineCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf"],
    noarchive=False,
)
# Software OpenGL fallback and Qt translations are not needed by this widgets-only UI.
a.binaries = [b for b in a.binaries if os.path.basename(b[0]).lower() != "opengl32sw.dll"]
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith("PySide6/translations")]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="iField Data Processing",
    icon="app/gui/app.ico",
    console=False,
    upx=False,
    contents_directory=".",
)

coll = COLLECT(exe, a.binaries, a.datas, name="iFieldDataProcessing", upx=False)
