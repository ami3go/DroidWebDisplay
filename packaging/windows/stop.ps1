$ErrorActionPreference = "Stop"
$parent = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (Test-Path (Join-Path $parent "VERSION.json")) { $Root = $parent } else { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$candidates = @((Join-Path $Root "runtime\python\python.exe"), (Join-Path $Root "runtime\python\Scripts\python.exe"), (Join-Path $Root ".venv\Scripts\python.exe"))
$Python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) { throw "Installed Python runtime not found." }
& $Python (Join-Path $Root "tools\stop_bridge_service.py") --pid-file (Join-Path $Root "data\service.pid")
