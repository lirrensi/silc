@echo off
setlocal enabledelayedexpansion

set "PROJECT_ROOT=%~dp0"
set "DIST_DIR=%PROJECT_ROOT%dist"
set "EXE_NAME=silc.exe"
set "INSTALL_DIR=%USERPROFILE%\silc"
set "EXE_PATH=%DIST_DIR%\%EXE_NAME%"
set "TARGET_PATH=%INSTALL_DIR%\%EXE_NAME%"

echo SILC Installer for Windows
echo ===========================

:: Check if executable exists
if not exist "%EXE_PATH%" (
    echo Executable not found in dist/, building first...
    python "%PROJECT_ROOT%build.py"
    if errorlevel 1 (
        echo Build failed!
        exit /b 1
    )
)

:: Create install directory
if not exist "%INSTALL_DIR%" (
    echo Creating install directory: %INSTALL_DIR%
    mkdir "%INSTALL_DIR%"
)

:: Copy executable
echo Copying executable to %INSTALL_DIR%
copy /Y "%EXE_PATH%" "%TARGET_PATH%"
if errorlevel 1 (
    echo Failed to copy executable!
    exit /b 1
)

:: Add to PATH
echo.
echo Adding %INSTALL_DIR% to PATH...

:: Check if already in PATH
echo %PATH% | find /i "%INSTALL_DIR%" >nul
if %errorlevel% == 0 (
    echo Already in PATH, skipping.
) else (
    :: Add to user PATH via registry
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CURRENT_PATH=%%B"
    set "NEW_PATH=%CURRENT_PATH%;%INSTALL_DIR%"
    reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "!NEW_PATH!" /f >nul 2>&1
    if %errorlevel% == 0 (
        echo Added to user PATH.
        echo.
        echo IMPORTANT: Please restart your terminal for PATH changes to take effect.
    ) else (
        echo Failed to add to PATH automatically.
        echo Please add %INSTALL_DIR% to your PATH manually.
    )
)

echo.
echo ==========================================
echo Installation complete!
echo ==========================================
echo Executable location: %TARGET_PATH%
echo Installation directory: %INSTALL_DIR%
echo.
echo Try running: %TARGET_PATH% --help
echo.
endlocal
