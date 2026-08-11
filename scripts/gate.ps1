param(
  [string]$BrowserEvidence = "",
  [switch]$RequireBrowserEvidence,
  [switch]$RequireWebClientBuild
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Args = @("$Root\tools\release_gate.py", "--output", "$Root\evidence\release\gate.json")
if ($RequireBrowserEvidence) { $Args += "--require-browser-evidence"; $Args += "--browser-evidence"; $Args += $BrowserEvidence }
if ($RequireWebClientBuild) { $Args += "--require-web-client-build" }
python @Args
