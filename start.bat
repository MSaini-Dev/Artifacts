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

set "PORT=8000"
set "MESH_PORT=8765"
set "MESH_AGENT_PORT=8000"
if not defined MESH_API_URL set "MESH_API_URL=http://127.0.0.1:8766"

if defined HOST (
    echo Brain API will bind to %HOST%:%PORT%.
) else (
    echo Brain API chooses its bind address from MESH_AGENT_TOKEN in the environment or root .env.
)

start "Mesh Node" /D "%CD%\mesh" cmd /k "%PYTHON% server.py --port %MESH_PORT%"
start "Brain API" cmd /k "%PYTHON% -m backend.run_server"
start "Brain UI" /D "%CD%\frontend" cmd /k npm run dev

echo.
echo Mesh UI:   http://127.0.0.1:%MESH_PORT%/
echo React UI:  http://127.0.0.1:5173/
echo Brain API: http://127.0.0.1:%PORT%/
echo.
echo If peers cannot call this agent, run allow_mesh_firewall.bat as Administrator
echo and make sure this Wi-Fi/Ethernet network is marked Private in Windows.
endlocal
