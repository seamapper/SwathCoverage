@echo off
REM Build script for KMALL to Swath PKL Converter
REM This will create a single-file executable with no console window

set PYTHON_PATH=C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe
set PIP_PATH=C:\Users\pjohnson\PycharmProjects\.venv\Scripts\pip.exe
set PYINSTALLER_PATH=C:\Users\pjohnson\PycharmProjects\.venv\Scripts\pyinstaller.exe

echo Installing PyInstaller if needed...
"%PIP_PATH%" install pyinstaller

echo.
echo Building executable...
"%PYINSTALLER_PATH%" KMALL_to_PKL_Converter.spec --clean

echo.
echo Build complete! The executable should be in the 'dist' folder.
pause

