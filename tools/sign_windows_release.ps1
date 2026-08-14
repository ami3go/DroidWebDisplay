[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$File,

  [string]$CertificateThumbprint = "",
  [string]$SignToolPath = "",
  [string]$TimestampUrl = "http://timestamp.digicert.com",
  [string]$ChecksumManifest = "",
  [switch]$VerifyOnly,
  [switch]$SkipTimestamp,
  [switch]$CiSelfSignedSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-SignTool {
  if ($SignToolPath) {
    if (-not (Test-Path -LiteralPath $SignToolPath -PathType Leaf)) {
      throw "SignTool was not found at: $SignToolPath"
    }
    return (Resolve-Path -LiteralPath $SignToolPath).Path
  }

  $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $programFilesX86 = ${env:ProgramFiles(x86)}
  if ($programFilesX86) {
    $glob = Join-Path $programFilesX86 "Windows Kits\10\bin\*\x64\signtool.exe"
    $candidate = Get-ChildItem -Path $glob -File -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($candidate) {
      return $candidate.FullName
    }
  }

  throw "signtool.exe was not found. Install the Windows SDK or pass -SignToolPath."
}

function Invoke-SignTool {
  param(
    [Parameter(Mandatory = $true)][string]$Operation,
    [Parameter(Mandatory = $true)][string[]]$Arguments
  )

  Write-Host "SignTool $Operation starting."
  & $script:ResolvedSignTool @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "signtool.exe $Operation failed with exit code $LASTEXITCODE: $($Arguments -join ' ')"
  }
  Write-Host "SignTool $Operation completed."
}

function Update-ChecksumManifest {
  param(
    [Parameter(Mandatory = $true)][string]$SignedFile,
    [Parameter(Mandatory = $true)][string]$Manifest
  )

  if ([IO.Path]::IsPathRooted($Manifest)) {
    $manifestPath = [IO.Path]::GetFullPath($Manifest)
  } else {
    $manifestPath = [IO.Path]::GetFullPath((Join-Path (Get-Location) $Manifest))
  }

  $manifestDirectory = Split-Path -Parent $manifestPath
  if ($manifestDirectory) {
    New-Item -ItemType Directory -Path $manifestDirectory -Force | Out-Null
  }

  $fileName = [IO.Path]::GetFileName($SignedFile)
  $hash = (Get-FileHash -LiteralPath $SignedFile -Algorithm SHA256).Hash.ToLowerInvariant()
  $pattern = '^[0-9A-Fa-f]{64}\s+\*?' + [regex]::Escape($fileName) + '$'

  $lines = @()
  if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    $lines = @(Get-Content -LiteralPath $manifestPath | Where-Object { $_ -notmatch $pattern })
  }
  $lines += "$hash  $fileName"

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllLines($manifestPath, $lines, $utf8NoBom)
  Write-Host "Updated SHA-256 manifest: $manifestPath"
}

$resolvedFile = (Resolve-Path -LiteralPath $File).Path
if ([IO.Path]::GetExtension($resolvedFile) -ne ".exe") {
  throw "Only Windows .exe release artifacts are accepted: $resolvedFile"
}

$thumbprint = $CertificateThumbprint -replace '\s', ''
if ($thumbprint -and $thumbprint -notmatch '^[0-9A-Fa-f]{40}$') {
  throw "Certificate thumbprint must contain exactly 40 hexadecimal characters."
}

if ($CiSelfSignedSmoke) {
  if (-not $SkipTimestamp) {
    throw "-CiSelfSignedSmoke is test-only and requires -SkipTimestamp. Production signing must be timestamped."
  }
  if ([string]::IsNullOrWhiteSpace($thumbprint)) {
    throw "-CiSelfSignedSmoke requires -CertificateThumbprint so the embedded signer identity can be verified."
  }
}

Write-Host "Resolving signtool.exe."
$script:ResolvedSignTool = Resolve-SignTool
Write-Host "Using SignTool: $script:ResolvedSignTool"

if (-not $VerifyOnly) {
  if ([string]::IsNullOrWhiteSpace($thumbprint)) {
    throw "-CertificateThumbprint is required when signing."
  }

  $signArguments = @(
    "sign",
    "/sha1", $thumbprint,
    "/fd", "SHA256",
    "/d", "DroidWebDisplay",
    "/du", "https://github.com/ami3go/DroidWebDisplay"
  )

  if (-not $SkipTimestamp) {
    if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
      throw "-TimestampUrl cannot be empty unless -SkipTimestamp is used for a non-release test."
    }
    $signArguments += @("/tr", $TimestampUrl, "/td", "SHA256")
  }

  $signArguments += $resolvedFile
  Invoke-SignTool -Operation "sign" -Arguments $signArguments
}

if (-not $CiSelfSignedSmoke) {
  Invoke-SignTool -Operation "verify" -Arguments @("verify", "/pa", "/all", "/v", $resolvedFile)
}

Write-Host "PowerShell Authenticode inspection starting."
$signature = Get-AuthenticodeSignature -FilePath $resolvedFile
if (-not $signature.SignerCertificate) {
  throw "Authenticode inspection found no embedded signer certificate."
}

$actualThumbprint = ($signature.SignerCertificate.Thumbprint -replace '\s', '').ToUpperInvariant()
if ($CiSelfSignedSmoke) {
  if ($actualThumbprint -ne $thumbprint.ToUpperInvariant()) {
    throw "CI self-signed smoke signer mismatch: expected $thumbprint, got $actualThumbprint"
  }
  Write-Host "CI self-signed Authenticode signer matched expected thumbprint."
} elseif ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
  throw "Authenticode verification failed: $($signature.Status) - $($signature.StatusMessage)"
}
Write-Host "PowerShell Authenticode inspection completed."

if ($ChecksumManifest) {
  Update-ChecksumManifest -SignedFile $resolvedFile -Manifest $ChecksumManifest
}

$subject = $signature.SignerCertificate.Subject
if ($CiSelfSignedSmoke) {
  Write-Host "Authenticode CI smoke signature present: $resolvedFile"
} else {
  Write-Host "Authenticode signature valid: $resolvedFile"
}
Write-Host "Signer: $subject"
