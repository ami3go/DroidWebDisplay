$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location "$Root\packages\scrcpy-protocol"
try { npm.cmd ci --ignore-scripts } finally { Pop-Location }
Push-Location "$Root\apps\web-client"
try { npm.cmd ci --ignore-scripts } finally { Pop-Location }
Write-Host "Package-local Node.js dependencies installed."
