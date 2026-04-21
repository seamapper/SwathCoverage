@echo off
REM Build script for Swath Coverage Plotter executable
REM Version number in exe name is read dynamically by SwathCoveragePlotter.spec

set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH="

REM Prefer currently activated virtual environment
if defined VIRTUAL_ENV (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" set "PYTHON_PATH=%VIRTUAL_ENV%\Scripts\python.exe"
)

REM Otherwise try project-local .venv
if "%PYTHON_PATH%"=="" set "PYTHON_PATH=%SCRIPT_DIR%.venv\Scripts\python.exe"

REM Fall back to active PATH python if project .venv is missing
if not exist "%PYTHON_PATH%" set "PYTHON_PATH=python"

REM Build only the Swath Coverage Plotter spec
set "SPEC_FILE=SwathCoveragePlotter.spec"

if not exist "%SPEC_FILE%" (
    echo ERROR: Spec file not found: %SPEC_FILE%
    echo Expected spec: SwathCoveragePlotter.spec
    pause
    exit /b 1
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

echo.
echo Building executable using %SPEC_FILE%...
"%PYTHON_PATH%" -m PyInstaller "%SPEC_FILE%" --clean

echo.
echo Build complete! The executable should be in the 'dist' folder.
echo Note: executable name/version is controlled by SwathCoveragePlotter.spec.
pause

