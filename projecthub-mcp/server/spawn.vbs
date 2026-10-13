' Detach node from current process tree (survives SSH disconnect).
' Usage: wscript.exe spawn.vbs
Set oShell = CreateObject("WScript.Shell")
Set oFs = CreateObject("Scripting.FileSystemObject")
oShell.CurrentDirectory = oFs.GetParentFolderName(WScript.ScriptFullName)
' window style 0 (hidden), wait=False (fire-and-forget)
oShell.Run "cmd /c node index.mjs > mcp.log 2> mcp.err", 0, False
