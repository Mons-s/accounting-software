@echo off
echo Building AccountingSoftware...
echo.

REM Clean previous build artefacts
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

REM Run PyInstaller with the spec file
pyinstaller AccountingSoftware.spec

echo.
if exist "dist\AccountingSoftware\AccountingSoftware.exe" (
    echo BUILD SUCCEEDED
    echo Output: dist\AccountingSoftware\
    echo.
    echo Give the client the entire "dist\AccountingSoftware" folder.
    echo The .exe is inside it.
) else (
    echo BUILD FAILED — check the output above for errors.
)
pause
