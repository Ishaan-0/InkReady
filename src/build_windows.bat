@echo off
REM Build InkReady.exe for Windows
REM Run this from the src\ directory: build_windows.bat
REM
REM Produces: ..\build\windows\InkReady.exe
REM Requires: pip install -r requirements.txt

pyinstaller ^
  --name InkReady ^
  --windowed ^
  --onefile ^
  --clean ^
  app.py

if not exist "..\build\windows" mkdir "..\build\windows"
if exist "..\build\windows\InkReady.exe" del "..\build\windows\InkReady.exe"
move dist\InkReady.exe ..\build\windows\InkReady.exe

REM Clean up PyInstaller artifacts
rmdir /s /q build
rmdir /s /q dist
del InkReady.spec

echo Done ^> ..\build\windows\InkReady.exe
