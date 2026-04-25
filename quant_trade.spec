# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for quant_trade.

Build steps:
    1. maturin develop --release          # Compile quant_core.pyd first
    2. pyinstaller quant_trade.spec       # Bundle everything

Test on a CLEAN Windows machine (no Python/Rust installed) to verify
there are no missing DLL or import errors.

Windows MSVC runtime DLLs (vcruntime140.dll, msvcp140.dll) are located in:
    C:\\Windows\\System32\\   (if Visual C++ Redistributable is installed)
Update the paths below if your system has them elsewhere.
"""
import sys
import glob
from pathlib import Path

ROOT = Path(SPECPATH)

# ── quant_core extension (.pyd on Windows, .so on Linux/macOS) ───────────────
# Find the compiled extension in site-packages or the project root
def _find_quant_core():
    import importlib.util
    spec = importlib.util.find_spec("quant_core")
    if spec and spec.origin:
        return spec.origin
    # Fallback: search project root
    matches = list(ROOT.glob("quant_core*.pyd")) + list(ROOT.glob("quant_core*.so"))
    return str(matches[0]) if matches else None

quant_core_path = _find_quant_core()
binaries = []
if quant_core_path:
    binaries.append((quant_core_path, "."))

# ── MSVC runtime DLLs (Windows only) ─────────────────────────────────────────
if sys.platform == "win32":
    msvc_dlls = [
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    ]
    for dll in msvc_dlls:
        for search_dir in [r"C:\Windows\System32", r"C:\Windows\SysWOW64"]:
            candidate = Path(search_dir) / dll
            if candidate.exists():
                binaries.append((str(candidate), "."))
                break

# ── Data files ────────────────────────────────────────────────────────────────
datas = [
    (str(ROOT / "config"),                      "config"),
    (str(ROOT / "strategies"),                  "strategies"),
    (str(ROOT / "src" / "monitor" / "live_ui"), "src/monitor/live_ui"),
    (str(ROOT / "docs"),                        "docs"),
    (str(ROOT / "README.md"),                   "."),
]

# ── Hidden imports (dynamic imports that PyInstaller may miss) ────────────────
hiddenimports = [
    "quant_core",
    "streamlit",
    "streamlit.web.cli",
    "streamlit.runtime",
    "fastapi",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "akshare",
    "ccxt",
    "plotly",
    "pandas",
    "numpy",
    "pydantic",
    "pydantic_settings",
    "cryptography",
    "loguru",
    "apscheduler",
    "watchdog",
    "yaml",
    "sqlite3",
    "ta",
]

a = Analysis(
    ["launcher.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="quant_trade",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,      # keep console for log output
    icon=None,         # add a .ico file here if desired
    # Windows manifest: request admin rights if needed for service install
    # uac_admin=True,
)
