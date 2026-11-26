# 起新家：只用 pythonw + Hidden，不经过 cmd / run.bat，屏幕上不闪黑框。
# 用法：powershell -NoProfile -File .\start_hidden.ps1
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $py)) {
    $py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
}
Start-Process -FilePath $py -ArgumentList "`"$src\main.py`"" -WorkingDirectory $src -WindowStyle Hidden
