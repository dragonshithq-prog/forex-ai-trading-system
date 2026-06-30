@echo off
cd /d "%~dp0"
echo ============================================
echo  GitHub Intelligence Report Server
echo ============================================
echo.
echo  Starting server on http://localhost:8080
echo  Opening browser...
echo.
start "" http://localhost:8080
wscript "%~dp0start_server.vbs"
echo  Server is running in the background.
echo  Close this window to stop the server.
echo.
tasklist /fi "pid eq %ERRORLEVEL%" 2>nul | find "node.exe" >nul && (
  echo  To stop: run taskkill /f /im node.exe
)
echo.
pause
