@echo off
rem =========================================================================
rem  setup_firewall.bat  --  run ONCE ON THE TEACHER PC, as Administrator.
rem  Allows incoming viewing traffic (TCP 8765) and LAN discovery (UDP 5007).
rem  Without this the viewers simply never connect: Windows blocks the port.
rem  Pass your own ports if you changed them:
rem      setup_firewall.bat 9000 9001
rem =========================================================================
net session >nul 2>nul
if errorlevel 1 (
  echo Run this file as Administrator:  right click, "Run as administrator".
  pause
  exit /b 1
)

set "TCPPORT=%~1"
set "UDPPORT=%~2"
if "%TCPPORT%"=="" set "TCPPORT=8765"
if "%UDPPORT%"=="" set "UDPPORT=5007"

netsh advfirewall firewall add rule name="mydesk stream TCP" dir=in action=allow protocol=TCP localport=%TCPPORT%
netsh advfirewall firewall add rule name="mydesk discover UDP" dir=in action=allow protocol=UDP localport=%UDPPORT%

echo.
echo [firewall] TCP %TCPPORT% and UDP %UDPPORT% opened for this LAN.
echo [firewall] remove later with:
echo   netsh advfirewall firewall delete rule name="mydesk stream TCP"
echo   netsh advfirewall firewall delete rule name="mydesk discover UDP"
echo.
echo If a viewer still cannot connect, the port may be blocked by another rule:
echo   test from a viewer PC:   curl http://TEACHER-IP:8765/view
pause
