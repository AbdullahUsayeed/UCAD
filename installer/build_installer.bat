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
set MOD_STAGE=%PROJECT_DIR%\build\mod_stage

echo ========================================
echo  Building UCAD Assistant Installer
echo ========================================
echo.

REM Step 1: Build the launcher with PyInstaller
echo [1/4] Building launcher...
cd /d "%LAUNCHER_DIR%"
python build_launcher.py
if %ERRORLEVEL% neq 0 (
    echo ERROR: Launcher build failed!
    exit /b 1
)
echo Launcher built successfully.
echo.

REM Step 2: Stage the Mod source for the installer
echo [2/4] Staging Mod source...
cd /d "%PROJECT_DIR%"
python -c "import tools.stage_mod" 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Mod staging failed. Is tools/stage_mod.py present?
    exit /b 1
)
if not exist "%MOD_STAGE%\InitGui.py" (
    echo ERROR: Staged mod not found at %MOD_STAGE%
    exit /b 1
)
echo Mod staged at %MOD_STAGE%.
echo.

REM Step 3: Verify launcher output
echo [3/4] Verifying launcher output...
if not exist "%DIST_DIR%\UCAD Launcher" (
    echo ERROR: Launcher output not found at %DIST_DIR%\UCAD Launcher
    exit /b 1
)
echo Launcher output verified.
echo.

REM Step 4: Build the Inno Setup installer
echo [4/4] Building installer...
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
