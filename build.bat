@echo off
echo === myCustomScope — Build EXE ===
echo.

call venv\Scripts\activate.bat || (echo ERROR: run setup.bat first & pause & exit /b 1)

echo [1/2] Cleaning previous build...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [2/2] Building...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "myCustomScope" ^
  --icon "icon.ico" ^
  --uac-admin ^
  --add-data "icon.ico;." ^
  --collect-all keyboard ^
  --hidden-import PyQt6.QtCore ^
  --hidden-import PyQt6.QtGui ^
  --hidden-import PyQt6.QtWidgets ^
  --hidden-import PyQt6.QtNetwork ^
  main.py

echo.
if exist dist\myCustomScope.exe (
    echo === Build successful! ===
    echo EXE: dist\myCustomScope.exe
) else (
    echo === Build FAILED — check output above ===
)
echo.
pause
