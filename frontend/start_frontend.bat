@echo off
cd /d "C:\Users\USER\Desktop\Forex Trading Bot\frontend"
start /B /MIN "" "C:\Program Files\nodejs\node.exe" "node_modules\next\dist\bin\next" dev -p 3001 > frontend.log 2>&1
echo Frontend starting...
