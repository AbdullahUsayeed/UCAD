@echo off
:: install.bat — double-click to install UCAD Assistant into FreeCAD
set "MOD_DIR=%APPDATA%\FreeCAD\v1-1\Mod\AICompanion"
if not exist "%APPDATA%\FreeCAD\v1-1\Mod\" (
    echo FreeCAD not found. Install FreeCAD first.
    pause & exit /b 1
)
if exist "%MOD_DIR%" (
    echo Updating existing installation...
    rmdir /s /q "%MOD_DIR%"
)
xcopy /E /I /Y "%~dp0AICompanion" "%MOD_DIR%\"
echo UCAD installed! Restart FreeCAD and activate UCAD Assistant workbench.
pause
