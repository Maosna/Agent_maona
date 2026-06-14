Set ws = CreateObject("Wscript.Shell")
ws.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ws.Run "cmd /c npm start", 0, False
