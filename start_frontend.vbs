Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\USER\Desktop\Forex Trading Bot\frontend"
WshShell.Run "cmd /c start ""ForexFrontend"" /B cmd /c ""..\.venv312\Scripts\node.exe node_modules\.bin\next.cmd dev -p 3001 > ..\frontend.log 2>&1""", 0, False