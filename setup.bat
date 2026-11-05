@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3 was not found. Install Python 3 and add it to PATH.
        exit /b 1
    )
    set "PYTHON=python"
)

%PYTHON% -m pip install --upgrade pip
if errorlevel 1 goto :failed

%PYTHON% -m pip install -r backend\requirements.txt
if errorlevel 1 goto :failed

where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js and npm were not found. Install the current Node.js LTS release and rerun setup.bat.
    exit /b 1
)

pushd frontend
call npm ci
if errorlevel 1 (
    popd
    goto :failed
)
popd

echo.
echo Setup completed using the installed Python environment. Run start.bat to start Mesh, the Brain API, and the React UI.
exit /b 0

:failed
echo.
echo Setup failed. Review the error above, resolve it, and rerun setup.bat.
exit /b 1
