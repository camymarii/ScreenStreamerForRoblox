@echo off
echo ==========================================
echo   Screen Share App - Dependency Installer
echo ==========================================
echo.

:: Upgrade pip first
echo Upgrading pip...
python -m pip install --upgrade pip

echo.
echo Installing dependencies one by one...
echo.

:: Install numpy first (older version for compatibility)
echo [1/5] Installing NumPy 1.26.4...
python -m pip install numpy==1.26.4

:: Install other dependencies
echo [2/5] Installing Pillow...
python -m pip install pillow

echo [3/5] Installing Flask...
python -m pip install flask

echo [4/5] Installing Werkzeug...
python -m pip install werkzeug

echo [5/5] Installing OpenCV...
python -m pip install opencv-python

echo.
echo ==========================================
echo   Installation Complete!
echo ==========================================
echo.
echo To run the app, type: python main.py
echo.
pause
