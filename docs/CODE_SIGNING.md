# Windows Code Signing

DroidWebDisplay Windows release executables should be Authenticode-signed before a final public release. Signing is deliberately separated from normal CI packaging so pull requests and routine branch builds do not consume production signatures or gain access to signing credentials.

## Release signing policy

For a final Windows release:

1. Build and smoke-test the Windows executable from the exact release commit using the normal Release Gate.
2. Copy the validated executable to the controlled signing host or signing service.
3. Sign the executable with a publicly trusted code-signing identity using SHA-256.
4. Apply an RFC 3161 timestamp using SHA-256. Timestamping is required for production so the Authenticode signature can remain valid after the short-lived signing certificate or certificate validity period ends.
5. Verify the resulting Authenticode signature with the Windows Authenticode policy.
6. Regenerate `SHA256SUMS.txt` after signing. Authenticode changes the executable bytes, so any checksum produced before signing is obsolete.
7. Publish only the signed executable, the post-signing checksum manifest, and release notes that state the exact source commit and signing status.

Do not sign an artifact whose source commit, Release Gate result, or provenance is uncertain.

## Private-key handling

Production private keys must not be committed to the repository or stored as a PFX/P12 blob in GitHub Actions secrets. Current publicly trusted OV code-signing certificates are expected to use protected hardware or cloud key storage. Use a hardware token, HSM-backed cloud signing service, or another provider mechanism that exposes the certificate to Windows without exporting the private key.

The repository helper signs by certificate thumbprint from the Windows certificate store. This is compatible with many hardware-token and cloud-HSM providers after their CSP/KSP or signing client is installed on the controlled Windows signing host.

## Provider assessment — 2026-08-14

### Azure Artifact Signing

Microsoft currently recommends Azure Artifact Signing for non-Store Windows distribution. The Basic tier is approximately USD 9.99 per account per month and includes 5,000 signatures per month. Public Trust is available to organizations in the European Union, but individual developer eligibility is currently limited to the United States and Canada.

DroidWebDisplay is currently published from a personal GitHub account, so this repository does not assume that an eligible EU organization identity exists. If the project is later published through a qualifying legal organization, Azure Artifact Signing is the preferred hosted signing backend because it supports GitHub Actions and OIDC without an exportable private key.

Microsoft documentation:

- https://learn.microsoft.com/azure/artifact-signing/
- https://learn.microsoft.com/windows/apps/package-and-deploy/code-signing-options

### Traditional OV certificate with protected key storage

A publicly trusted OV certificate remains the general-purpose option when Azure Artifact Signing eligibility is unavailable. Microsoft currently describes typical OV pricing in the approximate USD 150–300/year range, depending on the CA and service. New certificates use protected hardware or cloud key storage rather than an ordinary exportable software key.

For DroidWebDisplay, use a provider whose token/cloud client exposes the code-signing certificate to the Windows certificate store, then use `tools/sign_windows_release.ps1` on a controlled Windows signing host.

### SignPath Foundation

SignPath Foundation offers free signing to qualifying open-source projects, but its free OSS conditions prohibit proprietary components except for limited exceptions. The current DroidWebDisplay Windows package includes Android SDK Platform-Tools (`adb`), distributed under the Android Software Development Kit License Agreement rather than an OSI open-source license.

Because of that packaging dependency, SignPath Foundation is not the default DroidWebDisplay signing plan unless SignPath explicitly approves this artifact composition or the Windows package is changed so it satisfies the Foundation conditions.

## Signing a release executable

Prerequisites on the signing host:

- Windows 10/11 or Windows Server with the Windows SDK `signtool.exe` installed.
- A publicly trusted code-signing certificate available through the Windows certificate store.
- Access to the certificate private key through its hardware token, HSM, or provider signing client.
- The validated release executable and `SHA256SUMS.txt` from the release staging area.

List code-signing certificates and copy the intended thumbprint:

```powershell
Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
  Select-Object Subject, Thumbprint, NotAfter
```

Sign and update the checksum manifest:

```powershell
.\tools\sign_windows_release.ps1 `
  -File .\release\DroidWebDisplay-0.11.2-windows-x86_64.exe `
  -CertificateThumbprint '<CERTIFICATE-THUMBPRINT>' `
  -TimestampUrl 'http://timestamp.digicert.com' `
  -ChecksumManifest .\release\SHA256SUMS.txt
```

The helper performs all of the following:

- signs only an `.exe` artifact;
- uses SHA-256 for the Authenticode file digest;
- uses RFC 3161 timestamping with SHA-256 for production signing;
- runs `signtool verify /pa /all /v` after signing;
- checks `Get-AuthenticodeSignature` returns `Valid`;
- rewrites the checksum entry for the executable after signing.

Verify an already signed executable without changing it:

```powershell
.\tools\sign_windows_release.ps1 `
  -File .\release\DroidWebDisplay-0.11.2-windows-x86_64.exe `
  -VerifyOnly
```

## CI signing smoke

The Windows Release Gate creates a disposable copy of the CI executable, creates a temporary self-signed code-signing certificate, trusts it only inside the ephemeral runner, signs and verifies the copy, validates checksum rewriting, then deletes the copy and test certificate.

The uploaded `windows-package-smoke` artifact remains the original unsigned CI executable. The temporary CI certificate must never be used for a public release.

`-SkipTimestamp` exists only for this isolated CI smoke. Production release signing must use an RFC 3161 timestamp.

## Release checklist

Before publishing a signed Windows release, confirm all of these are true:

- Release Gate passed on the exact source SHA.
- The signing certificate identifies the intended publisher and is not expired/revoked.
- The signing operation used SHA-256 and an RFC 3161 SHA-256 timestamp.
- `signtool verify /pa /all /v` passes.
- `Get-AuthenticodeSignature` reports `Valid`.
- `SHA256SUMS.txt` was generated or updated after signing.
- The released EXE hash matches the post-signing manifest.
- Release notes identify whether the Windows executable is signed and identify the exact source commit.
