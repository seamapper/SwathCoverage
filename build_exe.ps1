# Build script for KMALL to Swath PKL Converter
# This will create a single-file executable with no console window

$pythonPath = "C:\Users\pjohnson\PycharmProjects\.venv\Scripts\python.exe"
$pipPath = "C:\Users\pjohnson\PycharmProjects\.venv\Scripts\pip.exe"
$pyinstallerPath = "C:\Users\pjohnson\PycharmProjects\.venv\Scripts\pyinstaller.exe"

Write-Host "Installing PyInstaller if needed..." -ForegroundColor Cyan
& $pipPath install pyinstaller

Write-Host "`nBuilding executable..." -ForegroundColor Cyan
& $pyinstallerPath KMALL_to_PKL_Converter.spec --clean

Write-Host "`nBuild complete! The executable should be in the 'dist' folder." -ForegroundColor Green
Read-Host "Press Enter to exit"

