[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:LOCALAPPDATA\Programs\GptBridgeScrcpy",
    [switch]$DesktopShortcut,
    [switch]$NoShortcut,
    [switch]$AllowOnlineDependencies
)
$ErrorActionPreference = "Stop"
$parent = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (Test-Path (Join-Path $parent "VERSION.json")) { $Source = $parent }
else { $Source = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
if ($Source -eq $InstallRoot) { throw "InstallRoot must be different from the release source folder." }

Write-Host "Installing Gpt-Bridge to $InstallRoot"
# Stop an existing installed service before replacing application files.
$oldCandidates = @(
    (Join-Path $InstallRoot "runtime\python\python.exe"),
    (Join-Path $InstallRoot "runtime\python\Scripts\python.exe"),
    (Join-Path $InstallRoot ".venv\Scripts\python.exe")
)
$oldPython = $oldCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$oldStop = Join-Path $InstallRoot "tools\stop_bridge_service.py"
if ($oldPython -and (Test-Path $oldStop)) {
    & $oldPython $oldStop --pid-file (Join-Path $InstallRoot "data\service.pid") 2>$null
}
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
foreach ($state in @("data", "downloads", "logs")) { New-Item -ItemType Directory -Force -Path (Join-Path $InstallRoot $state) | Out-Null }

# Copy application files while preserving runtime state and the existing virtual environment.
$excludeDirs = @("data", "downloads", "logs", ".venv", "evidence", ".pytest_cache", "node_modules", ".git")
$xd = ($excludeDirs | ForEach-Object { '"' + $_ + '"' }) -join ' '
$cmd = "robocopy `"$Source`" `"$InstallRoot`" /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD $xd"
cmd.exe /d /s /c $cmd | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

$runtimeCandidates = @(
    (Join-Path $InstallRoot "runtime\python\python.exe"),
    (Join-Path $InstallRoot "runtime\python\Scripts\python.exe")
)
$runtimePython = $runtimeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $runtimePython) {
    $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) { $python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source }
    if (-not $python) { throw "Python 3.11 or newer is required unless a bundled runtime is included." }
    $venvPython = Join-Path $InstallRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        if ([IO.Path]::GetFileName($python) -ieq "py.exe") { & $python -3.11 -m venv (Join-Path $InstallRoot ".venv") }
        else { & $python -m venv (Join-Path $InstallRoot ".venv") }
        if ($LASTEXITCODE) { throw "Failed to create Python virtual environment" }
    }
    $wheelhouse = Join-Path $InstallRoot "wheelhouse"
    if (Test-Path $wheelhouse) {
        & $venvPython -m pip install --disable-pip-version-check --no-index --find-links $wheelhouse -e $InstallRoot
    } elseif ($AllowOnlineDependencies) {
        & $venvPython -m pip install --disable-pip-version-check -e $InstallRoot
    } else {
        throw "Offline wheelhouse is not present. Supply a complete offline release or rerun with -AllowOnlineDependencies on an Internet-connected PC."
    }
    if ($LASTEXITCODE) { throw "Python dependency installation failed" }
}

# Compile a tiny launcher using the .NET compiler available through Windows PowerShell.
$launcher = Join-Path $InstallRoot "GptBridge.exe"
$launcherSource = Join-Path $InstallRoot "installer\GptBridgeLauncher.cs"
if (-not (Test-Path $launcherSource)) { $launcherSource = Join-Path $InstallRoot "packaging\windows\GptBridgeLauncher.cs" }
$sourceCode = Get-Content -Raw $launcherSource
if (Test-Path $launcher) { Remove-Item -Force $launcher }
Add-Type -TypeDefinition $sourceCode -Language CSharp -OutputAssembly $launcher -OutputType ConsoleApplication

if (-not $NoShortcut) {
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $startMenu "Gpt-Bridge.lnk"))
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $InstallRoot
    $shortcut.Save()
    if ($DesktopShortcut) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $shortcut = $shell.CreateShortcut((Join-Path $desktop "Gpt-Bridge.lnk"))
        $shortcut.TargetPath = $launcher
        $shortcut.WorkingDirectory = $InstallRoot
        $shortcut.Save()
    }
}
Write-Host "Installation complete. Runtime state under data/, downloads/, and logs/ is preserved during upgrades."
