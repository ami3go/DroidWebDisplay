[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$File,

  [string]$CertificateThumbprint = "",
  [string]$SignToolPath = "",
  [string]$TimestampUrl = "http://timestamp.digicert.com",
  [string]$ChecksumManifest = "",
  [switch]$VerifyOnly,
  [switch]$SkipTimestamp
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
  param([Parameter(Mandatory = $true)][string[]]$Arguments)

  & $script:ResolvedSignTool @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "signtool.exe failed with exit code $LASTEXITCODE: $($Arguments -join ' ')"
  }
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

$script:ResolvedSignTool = Resolve-SignTool

if (-not $VerifyOnly) {
  if ([string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    throw "-CertificateThumbprint is required when signing."
  }

  $thumbprint = $CertificateThumbprint -replace '\s', ''
  if ($thumbprint -notmatch '^[0-9A-Fa-f]{40}$') {
    throw "Certificate thumbprint must contain exactly 40 hexadecimal characters."
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
  Invoke-SignTool -Arguments $signArguments
}

Invoke-SignTool -Arguments @("verify", "/pa", "/all", "/v", $resolvedFile)

$signature = Get-AuthenticodeSignature -FilePath $resolvedFile
if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
  throw "Authenticode verification failed: $($signature.Status) - $($signature.StatusMessage)"
}

if ($ChecksumManifest) {
  Update-ChecksumManifest -SignedFile $resolvedFile -Manifest $ChecksumManifest
}

$subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { "unknown" }
Write-Host "Authenticode signature valid: $resolvedFile"
Write-Host "Signer: $subject"
