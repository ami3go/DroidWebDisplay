[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\Programs\DroidWebDisplay",
    [switch]$PurgeData
)
$ErrorActionPreference = "Stop"
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$candidates = @(
    (Join-Path $InstallRoot "runtime\python\python.exe"),
    (Join-Path $InstallRoot "runtime\python\Scripts\python.exe"),
    (Join-Path $InstallRoot ".venv\Scripts\python.exe")
)
$python = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$stopTool = Join-Path $InstallRoot "tools\stop_bridge_service.py"
if ($python -and (Test-Path $stopTool)) {
    & $python $stopTool --pid-file (Join-Path $InstallRoot "data\service.pid") 2>$null
}
$shortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\DroidWebDisplay.lnk"
Remove-Item -Force -ErrorAction SilentlyContinue $shortcut
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath("Desktop")) "DroidWebDisplay.lnk")
if ($PurgeData) {
    Remove-Item -Recurse -Force $InstallRoot
    Write-Host "DroidWebDisplay and runtime data removed."
    exit
}
$temp = Join-Path $env:TEMP ("DroidWebDisplay-preserve-" + [guid]::NewGuid())
New-Item -ItemType Directory -Force -Path $temp | Out-Null
foreach ($state in @("data", "downloads", "logs")) {
    $source = Join-Path $InstallRoot $state
    if (Test-Path $source) { Move-Item $source (Join-Path $temp $state) }
}
Remove-Item -Recurse -Force $InstallRoot
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
foreach ($state in @("data", "downloads", "logs")) {
    $source = Join-Path $temp $state
    if (Test-Path $source) { Move-Item $source (Join-Path $InstallRoot $state) }
}
Remove-Item -Recurse -Force $temp
Write-Host "Application removed. Runtime data was preserved in $InstallRoot. Use -PurgeData to delete it."
