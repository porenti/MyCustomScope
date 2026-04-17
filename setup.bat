@echo off
echo === Crosshair Overlay — Setup ===
echo.

where python >nul 2>&1 || (echo ERROR: Python not found in PATH & pause & exit /b 1)

echo [1/3] Creating virtual environment...
python -m venv venv

echo [2/3] Activating venv...
call venv\Scripts\activate.bat

echo [3/3] Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt

echo.
echo === Done! ===
echo Run the app:  python main.py
echo Build exe:    build.bat
echo.
pause
