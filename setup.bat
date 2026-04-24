@echo off
setlocal enabledelayedexpansion

echo === quant_trade setup ===

REM 1. Check Python >= 3.11
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo Python %PY_VER% found
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    if %%a LSS 3 ( echo ERROR: Python 3.11+ required & exit /b 1 )
    if %%a EQU 3 if %%b LSS 11 ( echo ERROR: Python 3.11+ required & exit /b 1 )
)
echo Python %PY_VER% OK

REM 2. Check / install Rust
rustup --version >nul 2>&1
if errorlevel 1 (
    echo Rust not found. Checking for admin rights to install...
    net session >nul 2>&1
    if errorlevel 1 (
        echo WARNING: Admin rights required for rustup silent install.
        echo Please run this script as Administrator, OR install Rust manually:
        echo   https://rustup.rs
        pause
        exit /b 1
    )
    echo Downloading rustup-init.exe...
    powershell -Command "Invoke-WebRequest -Uri 'https://win.rustup.rs/x86_64' -OutFile rustup-init.exe"
    if errorlevel 1 (
        echo ERROR: Download failed. Install manually from https://rustup.rs
        pause
        exit /b 1
    )
    rustup-init.exe -y --default-toolchain stable-x86_64-pc-windows-msvc
    del rustup-init.exe
    set PATH=%USERPROFILE%\.cargo\bin;%PATH%
)
echo Rust OK

REM 3. Create virtualenv
if not exist ".venv\" (
    python -m venv .venv
    echo Created .venv
)
call .venv\Scripts\activate.bat

REM 4. Install Python dependencies
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo Python dependencies installed

REM 5. Compile Rust extension
maturin develop --release
echo Rust extension compiled

REM 6. Copy .env template if missing
if not exist "config\.env" (
    copy config\.env.example config\.env
    echo Created config\.env from template — update KEYSTORE_SALT before use
)

echo.
echo === Setup complete! ===
echo Activate venv: .venv\Scripts\activate
echo Start GUI:     python launcher.py
pause
