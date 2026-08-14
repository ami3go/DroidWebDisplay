from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIGNING_SCRIPT = ROOT / "tools" / "sign_windows_release.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
README = ROOT / "README.md"
POLICY = ROOT / "docs" / "CODE_SIGNING.md"
PACKAGING = ROOT / "packaging" / "README.md"


def test_signing_helper_is_sha256_timestamped_and_fail_closed() -> None:
    script = SIGNING_SCRIPT.read_text(encoding="utf-8")

    assert '"sign"' in script
    assert '"/fd", "SHA256"' in script
    assert '"/tr", $TimestampUrl, "/td", "SHA256"' in script
    assert '"verify", "/pa", "/all", "/v"' in script
    assert "Get-AuthenticodeSignature" in script
    assert "SignatureStatus]::Valid" in script
    assert "CertificateThumbprint" in script
    assert "ChecksumManifest" in script
    assert "Get-FileHash" in script
    assert "Only Windows .exe release artifacts are accepted" in script
    assert ".pfx" not in script.lower()
    assert ".p12" not in script.lower()


def test_windows_ci_smokes_signing_on_disposable_copy_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Smoke-test Windows Authenticode signing helper" in workflow
    assert "timeout-minutes: 2" in workflow
    assert "DroidWebDisplay-signing-smoke.exe" in workflow
    assert "New-SelfSignedCertificate" in workflow
    assert "-Type CodeSigningCert" in workflow
    assert "System.Security.Cryptography.X509Certificates.X509Store" in workflow
    assert 'Add-CurrentUserCertificate -StoreName "Root"' in workflow
    assert 'Add-CurrentUserCertificate -StoreName "TrustedPublisher"' in workflow
    assert 'Remove-CurrentUserCertificate -StoreName "Root"' in workflow
    assert 'Remove-CurrentUserCertificate -StoreName "TrustedPublisher"' in workflow
    assert "-SkipTimestamp" in workflow
    assert "-VerifyOnly" in workflow
    assert "Remove-Item $signedCopy" in workflow
    assert "path: dist/DroidWebDisplay.exe" in workflow
    assert "path: $signedCopy" not in workflow


def test_code_signing_policy_protects_private_keys_and_post_signing_checksums() -> None:
    policy = POLICY.read_text(encoding="utf-8")
    packaging = PACKAGING.read_text(encoding="utf-8")

    assert "must not be committed to the repository" in policy
    assert "must not be committed to the repository or stored as a PFX/P12 blob" in policy
    assert "Regenerate `SHA256SUMS.txt` after signing" in policy
    assert "RFC 3161" in policy
    assert "Azure Artifact Signing" in policy
    assert "SignPath Foundation" in policy
    assert "Android SDK Platform-Tools" in policy
    assert "The normal package build and CI smoke remain unsigned" in packaging
    assert "PFX/P12 files in GitHub Actions secrets" in packaging


def test_readme_documents_windows_signature_verification() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "Get-AuthenticodeSignature" in readme
    assert "DroidWebDisplay Authenticode signature is not valid" in readme
    assert "docs/CODE_SIGNING.md" in readme
    assert "unsigned pre-release" in readme
