@echo off
setlocal

net session >nul 2>&1
if errorlevel 1 (
    echo This firewall setup needs Administrator permission.
    echo Right-click allow_mesh_firewall.bat and select "Run as administrator".
    exit /b 1
)

call :allow_tcp "Artifacts Mesh Agent API 8000" 8000
if errorlevel 1 goto :failed
call :allow_tcp "Artifacts Mesh WebSocket 8765" 8765
if errorlevel 1 goto :failed
call :allow_udp "Artifacts Mesh Discovery 3848" 3848
if errorlevel 1 goto :failed

echo.
echo Private-network firewall rules are installed for Mesh agent calls and discovery.
echo Ensure the active Windows network profile is Private.
exit /b 0

:allow_tcp
netsh advfirewall firewall delete rule name="%~1" >nul 2>&1
netsh advfirewall firewall add rule name="%~1" dir=in action=allow protocol=TCP localport=%~2 remoteip=localsubnet profile=private
exit /b %errorlevel%

:allow_udp
netsh advfirewall firewall delete rule name="%~1" >nul 2>&1
netsh advfirewall firewall add rule name="%~1" dir=in action=allow protocol=UDP localport=%~2 remoteip=localsubnet profile=private
exit /b %errorlevel%

:failed
echo Failed to install one or more firewall rules. Check the error above.
exit /b 1
