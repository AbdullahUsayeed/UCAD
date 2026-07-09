@echo off
REM UCAD Assistant — Complete Build Pipeline
REM 
REM Usage:
REM   scripts\build_all.bat         Full build
REM   scripts\build_all.bat test    Test then build
REM
REM Requires:
REM   - Python 3.10+
REM   - PyInstaller (pip install pyinstaller)
REM   - Inno Setup 6+ (https://jrsoftware.org/isdl.php)

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set DIST_DIR=%PROJECT_DIR%\dist

echo ========================================
echo  UCAD Assistant Build Pipeline
echo ========================================
echo.

REM Step 0: Run tests (optional)
if /I "%~1"=="test" (
    echo [0/4] Running test suite...
    cd /d "%PROJECT_DIR%"
    python -m pytest tests/ -v
    if !ERRORLEVEL! neq 0 (
        echo ERROR: Tests failed!
        exit /b 1
    )
    echo Tests passed.
    echo.
)

REM Step 1: Verify version
echo [1/4] Checking version...
cd /d "%PROJECT_DIR%"
for /f "tokens=2 delims=><" %%a in ('findstr "<version>" package.xml') do set VERSION=%%a
echo Version: %VERSION%
echo.

REM Step 2: Build launcher
echo [2/4] Building launcher (PyInstaller)...
cd /d "%PROJECT_DIR%\launcher"
python build_launcher.py
if !ERRORLEVEL! neq 0 (
    echo ERROR: Launcher build failed!
    exit /b 1
)
echo.

REM Step 3: Verify launcher executable
echo [3/4] Verifying launcher...
if not exist "%DIST_DIR%\UCAD Launcher\UCAD Launcher.exe" (
    echo ERROR: Launcher executable not found!
    exit /b 1
)
echo Launcher executable: %DIST_DIR%\UCAD Launcher\UCAD Launcher.exe
echo.

REM Step 4: Build installer
echo [4/4] Building installer (Inno Setup)...

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist %ISCC% (
    echo WARNING: Inno Setup not found. Skipping installer build.
    echo Installer source: installer\setup.iss
    echo.
    goto :done
)

%ISCC% "%PROJECT_DIR%\installer\setup.iss"
if !ERRORLEVEL! neq 0 (
    echo ERROR: Installer build failed!
    exit /b 1
)

:done
echo.
echo ========================================
echo  Build complete!
echo  Launcher: %DIST_DIR%\UCAD Launcher\
echo  Installer: %DIST_DIR%\UCAD_Assistant_%VERSION%_Setup.exe
echo ========================================
