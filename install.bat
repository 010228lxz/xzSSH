@echo off

:: xzSSH Installation Script for Windows
:: This script sets up a virtual environment, installs dependencies,
:: and makes the 'xzssh' command available.

setlocal

echo ------------------------------------------------
echo   Installing xzSSH...
echo ------------------------------------------------

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: python is not installed or not in PATH. Please install Python 3.9 or higher.
    exit /b 1
)

:: Create a virtual environment
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
) else (
    echo Virtual environment already exists.
)

:: Activate virtual environment and install
echo Installing dependencies and xzssh package...
call venv\Scripts\activate
pip install --upgrade pip
pip install -e .

echo ------------------------------------------------
echo   Installation Complete! ✔
echo ------------------------------------------------
echo.
echo To start using xzssh, activate the virtual environment:
echo   venv\Scripts\activate
echo.
echo Then you can run commands like:
echo   xzssh list
echo   xzssh --help
echo.
echo Alternatively, you can add an alias or update your PATH.
echo.

endlocal
