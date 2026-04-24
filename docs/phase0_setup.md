# Phase 0: Development Environment Setup

## Requirements

| Component | Version | Notes |
|---|---|---|
| Python | 3.11+ | [python.org](https://www.python.org) |
| Rust / Cargo | stable | via rustup |
| MSVC Build Tools | 2019+ | **Windows only** — required for Rust `x86_64-pc-windows-msvc` toolchain |
| Admin rights | — | **Windows only** — needed for silent rustup installation |

> **Windows admin note**: `setup.bat` detects whether it has admin rights before attempting to download `rustup-init.exe`. If the check fails, it prints the manual install URL and exits cleanly.

## Quick Start

### Linux / macOS
```bash
git clone https://github.com/buggg-hfc/quant_trade.git
cd quant_trade
chmod +x setup.sh
./setup.sh
source .venv/bin/activate
python launcher.py
```

### Windows (run as Administrator)
```
git clone https://github.com/buggg-hfc/quant_trade.git
cd quant_trade
setup.bat
.venv\Scripts\activate
python launcher.py
```

## What `setup.sh` / `setup.bat` Does

1. Checks Python ≥ 3.11
2. Detects `rustup`; if missing, downloads and installs it silently (needs admin on Windows)
3. Creates a `.venv` virtual environment
4. Runs `pip install -r requirements.txt`
5. Runs `maturin develop --release` to compile the Rust extension
6. Copies `config/.env.example` → `config/.env` if not yet present

## pyproject.toml Fields Explained

```toml
[build-system]
requires = ["maturin>=1.4,<2.0"]
build-backend = "maturin"

[project]
name = "quant-trade"
requires-python = ">=3.11"

[tool.maturin]
module-name = "quant_core"        # Must match the #[pymodule] fn name in lib.rs
manifest-path = "core_engine/Cargo.toml"   # Cargo.toml location (not project root)
python-source = "src"             # Python package root
features = ["pyo3/extension-module"]
```

Key pitfall: `module-name` **must exactly match** the function name annotated with `#[pymodule]` in `core_engine/src/lib.rs`. Mismatch causes `ImportError` at runtime.

## Verify the Build

```bash
# Rust unit tests
cd core_engine && cargo test && cd ..

# Python smoke test
python -c "from quant_core import EventEngine, Bar, BacktestRunner; print('quant_core OK')"
```

## Common Errors

| Error | Cause | Fix |
|---|---|---|
| `linker 'link.exe' not found` | MSVC tools missing (Windows) | Install "Build Tools for Visual Studio" |
| `maturin: command not found` | venv not active or maturin not installed | `source .venv/bin/activate && pip install maturin` |
| `ImportError: DLL load failed` | MSVC runtime DLLs missing | Install "Visual C++ Redistributable" |
| `error: package 'quant-trade' ... no lib target` | Wrong Cargo.toml path in pyproject.toml | Check `manifest-path` field |
| `ModuleNotFoundError: quant_core` | Extension not compiled or wrong Python env | Run `maturin develop --release` in active venv |

## Directory Structure After Setup

```
quant_trade/
├── core_engine/       # Rust source
├── src/               # Python packages
├── strategies/        # User strategy files (hot-reloaded)
├── config/
│   ├── settings.yaml  # Main config
│   └── .env           # Created from .env.example — update KEYSTORE_SALT
├── data_cache/        # SQLite cache (gitignored)
├── logs/              # Log files (gitignored)
└── reports/           # Backtest HTML reports (gitignored)
```
