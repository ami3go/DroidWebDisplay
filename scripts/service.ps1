param(
  [string]$DownloadDirectory = "",
  [int]$TransferConcurrency = 1,
  [switch]$NoBrowser
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Args = @("$Root\tools\run_bridge_service.py", "--repo-root", $Root, "--transfer-concurrency", "$TransferConcurrency")
if ($DownloadDirectory) { $Args += "--download-directory"; $Args += $DownloadDirectory }
if (-not $NoBrowser) { $Args += "--open-browser" }
python @Args
