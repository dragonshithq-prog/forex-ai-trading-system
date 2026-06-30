@echo off
cd /d "%~dp0intelligence"
echo ============================================
echo  GitHub Intelligence Report Server
echo ============================================
echo.
echo  Starting server on http://localhost:8080
echo.
start "" http://localhost:8080
wscript "%~dp0start_server.vbs"
echo.
echo  Server is running in the background.
echo  Open http://localhost:8080 in your browser.
echo  To stop: taskkill /f /im node.exe
echo.
pause
