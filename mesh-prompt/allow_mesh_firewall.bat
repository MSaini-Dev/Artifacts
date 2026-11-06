@echo off
:: ============================================================================
:: allow_mesh_firewall.bat
:: Configures Windows Defender Firewall inbound rules for Mesh & Brain Studio.
:: Restricts rules strictly to the Private profile (local trusted LAN / Wi-Fi).
:: NEVER open these ports on Public network profiles.
::
:: Ports opened on Private profile:
::   TCP 8000  - Brain Studio Web UI / Backend
::   TCP 8765  - Mesh WebSocket peer-to-peer communication
::   TCP 8766  - Mesh REST API (REQUIRED for Android Remote Prompt & Status)
::   UDP 3848  - Mesh Auto-discovery beacons
:: ============================================================================

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Administrator privileges required.
    echo Please right-click this script and select 'Run as administrator'.
    pause
    exit /b 1
)

echo Configuring Windows Firewall inbound rules for Private LAN...

call :allow_tcp "Brain Studio Web UI 8000" 8000
call :allow_tcp "Mesh Node WebSocket 8765" 8765
call :allow_tcp "Mesh REST API 8766" 8766
call :allow_udp "Mesh Node Discovery 3848" 3848

echo.
echo ============================================================================
echo [SUCCESS] Windows Defender Firewall rules created successfully!
echo Ports allowed on Private LAN:
echo   - TCP 8000 (Brain Studio UI)
echo   - TCP 8765 (Mesh WebSocket)
echo   - TCP 8766 (Mesh REST API - Android Remote Prompt Box)
echo   - UDP 3848 (Mesh Node Discovery)
echo.
echo NOTE: Ensure your Wi-Fi or Ethernet connection in Windows is set to
echo 'Private network' (Settings ^> Network ^& internet ^> Wi-Fi ^> Network profile: Private).
echo ============================================================================
goto :eof

:allow_tcp
netsh advfirewall firewall delete rule name=%1 >nul 2>&1
netsh advfirewall firewall add rule name=%1 dir=in action=allow protocol=TCP localport=%2 profile=private
if %errorLevel% equ 0 (
    echo  [OK] Inbound TCP %2 (%1)
) else (
    echo  [FAIL] Could not add rule for TCP %2
)
goto :eof

:allow_udp
netsh advfirewall firewall delete rule name=%1 >nul 2>&1
netsh advfirewall firewall add rule name=%1 dir=in action=allow protocol=UDP localport=%2 profile=private
if %errorLevel% equ 0 (
    echo  [OK] Inbound UDP %2 (%1)
) else (
    echo  [FAIL] Could not add rule for UDP %2
)
goto :eof
