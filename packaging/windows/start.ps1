param([switch]$Console)
$ErrorActionPreference = "Stop"
$parent = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (Test-Path (Join-Path $parent "VERSION.json")) { $Root = $parent } else { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$candidates = @(
    (Join-Path $Root "runtime\python\python.exe"),
    (Join-Path $Root "runtime\python\Scripts\python.exe"),
    (Join-Path $Root ".venv\Scripts\python.exe")
)
$Python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) { throw "DroidWebDisplay Python runtime not found. Run install.ps1 first." }
$PythonW = $Python -replace 'python\.exe$', 'pythonw.exe'
if (-not (Test-Path $PythonW)) { $PythonW = $Python }
$PidFile = Join-Path $Root "data\service.pid"
if ($Console) {
    & $Python (Join-Path $Root "tools\run_bridge_service.py") --repo-root $Root --pid-file $PidFile --open-browser
} else {
    Start-Process -FilePath $PythonW -WorkingDirectory $Root -ArgumentList @((Join-Path $Root "tools\run_bridge_service.py"), "--repo-root", $Root, "--pid-file", $PidFile, "--open-browser") | Out-Null
}
