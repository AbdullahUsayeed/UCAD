@echo off
REM Build UCAD Assistant Installer
REM Requires: Inno Setup 6+ (install from https://jrsoftware.org/isdl.php)
REM
REM Usage:
REM   installer\build_installer.bat
REM
REM This builds:
REM   1. The launcher (via PyInstaller)
REM   2. The installer (via Inno Setup)

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set LAUNCHER_DIR=%PROJECT_DIR%\launcher
set DIST_DIR=%PROJECT_DIR%\dist

echo ========================================
echo  Building UCAD Assistant Installer
echo ========================================
echo.

REM Step 1: Build the launcher with PyInstaller
echo [1/3] Building launcher...
cd /d "%LAUNCHER_DIR%"
python build_launcher.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Launcher build failed!
    exit /b 1
)
echo Launcher built successfully.
echo.

REM Step 2: Copy launcher to installer staging
echo [2/3] Staging files for installer...
if not exist "%DIST_DIR%\UCAD Launcher" (
    echo ERROR: Launcher output not found at %DIST_DIR%\UCAD Launcher
    exit /b 1
)

REM Step 3: Build the Inno Setup installer
echo [3/3] Building installer...
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist %ISCC% (
    echo WARNING: Inno Setup compiler not found at %ISCC%
    echo Install from https://jrsoftware.org/isdl.php
    echo.
    echo Manual: Open installer\setup.iss in Inno Setup and compile.
    exit /b 1
)

%ISCC% "%SCRIPT_DIR%setup.iss"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Installer build failed!
    exit /b 1
)

echo.
echo ========================================
echo  UCAD Assistant installer built!
echo  Output: %DIST_DIR%
echo ========================================
