@echo off
REM Build script for KMALL to SwathPKL Converter executable
REM EXE name/version, icon, and console behavior are controlled by KMALL_to_PKL_Converter.spec

set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH="
set "SPEC_FILE=KMALL_to_PKL_Converter.spec"
set "ICON_FILE=%SCRIPT_DIR%media\mac.ico"

REM Prefer currently activated virtual environment
if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_PATH=%VIRTUAL_ENV%\Scripts\python.exe"
)

REM Otherwise try project-local .venv
if "%PYTHON_PATH%"=="" set "PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe"

REM Fall back to active PATH python if project .venv is missing
if not exist "%PYTHON_PATH%" set "PYTHON_PATH=python"

if not exist "%SPEC_FILE%" (
    echo ERROR: Spec file not found: %SPEC_FILE%
    pause
    exit /b 1
)

if not exist "%ICON_FILE%" (
    echo WARNING: Icon file not found: %ICON_FILE%
    echo The spec will build without a custom icon.
)

REM Verify that Python is callable before continuing
"%PYTHON_PATH%" --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Could not run Python using "%PYTHON_PATH%"
    echo Make sure your virtual environment exists or Python is on PATH.
    pause
    exit /b 1
)

echo Installing PyInstaller if needed...
"%PYTHON_PATH%" -m pip install pyinstaller
if errorlevel 1 (
    echo ERROR: Failed to install PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building executable using %SPEC_FILE%...
"%PYTHON_PATH%" -m PyInstaller "%SPEC_FILE%" --clean
if errorlevel 1 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)

echo.
echo Build complete! The executable should be in the "dist" folder.
echo Output name format: KMALL_to_SwathPKL_Converter_v[version]
echo Version is read from "__version__" in kmall_to_pkl_converter.py.
pause
