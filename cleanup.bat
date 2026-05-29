@echo off
title Cleanup Build Files

echo ================================================================
echo Cleanup Build Files
echo ================================================================
echo.

echo This will remove temporary build files and keep only:
echo - Core source files (main.py, etc.)
echo - Generated EXE file (dist folder)
echo.

set /p confirm="Continue cleanup? (y/n): "
if /i not "%confirm%"=="y" (
    echo Cleanup cancelled
    pause
    exit /b 0
)

echo.
echo Starting cleanup...
echo.

REM Remove build directories
if exist "build" (
    echo Removing build directory...
    rmdir /s /q "build"
    echo Build directory removed
)

if exist "__pycache__" (
    echo Removing __pycache__ directory...
    rmdir /s /q "__pycache__"
    echo __pycache__ directory removed
)

REM Remove spec files
echo Removing spec files...
del /q *.spec 2>nul

REM Remove temporary files
echo Removing temporary files...
del /q *.pyc 2>nul
del /q *.pyo 2>nul
del /q *.tmp 2>nul
del /q version_info.txt 2>nul

echo.
echo ================================================================
echo Cleanup completed!
echo ================================================================
echo.

echo Remaining important files:
echo - Source code files (*.py)
echo - EXE file in dist folder
echo - Documentation files
echo.

echo Your project directory is now clean!
echo.

pause
