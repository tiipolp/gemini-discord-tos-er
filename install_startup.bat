@echo off
set "SCRIPT_PATH=%~dp0main.py"
set "PYTHONW_PATH=pythonw.exe"
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\DiscordToSBot.lnk"
set "WORKING_DIR=%~dp0"

echo Creating startup shortcut...
echo Script Path: %SCRIPT_PATH%
echo Shortcut Path: %SHORTCUT_PATH%

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut($env:SHORTCUT_PATH); $Shortcut.TargetPath = $env:PYTHONW_PATH; $Shortcut.Arguments = '\"' + $env:SCRIPT_PATH + '\"'; $Shortcut.WorkingDirectory = $env:WORKING_DIR; $Shortcut.Save()"

echo Done
pause
