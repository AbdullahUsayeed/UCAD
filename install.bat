@echo off
:: install.bat — double-click to install UCAD Assistant into FreeCAD
set "MOD_DIR=%APPDATA%\FreeCAD\v1-1\Mod\AICompanion"
if exist "%MOD_DIR%" (
    echo Updating existing installation...
    rmdir /s /q "%MOD_DIR%"
)
xcopy /E /I /Y "%~dp0AICompanion" "%MOD_DIR%\"
echo UCAD installed! Restart FreeCAD and activate UCAD Assistant workbench.
pause
