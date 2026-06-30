Dim shell
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "node server.js", 0, False
shell.Run "cmd /c start http://localhost:8080", 1, False
