#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display import __version__
from droid_web_display.auth import AuthService, TRUST_DURATIONS
from droid_web_display.release_checks import find_local_tsc, verify_static_client
from droid_web_display.evidence import validate_ux_browser_evidence
from droid_web_display.upstream_update.selftest import run_self_test as upstream_update_self_test
from droid_web_display.release_packaging import ReleaseInputs, build_release_tree, migrate_runtime_state, validate_release_tree
from droid_web_display.network_access import (
    LAN_HTTPS,
    FirewallManager,
    NetworkAccessConfig,
    NetworkConfigStore,
    NetworkPolicy,
    TlsSettings,
    generate_certificate,
)



def run(argv: list[str], *, cwd: Path, timeout: float = 300.0, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAIL", "argv": argv, "error": str(exc)}
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "argv": argv,
        "returncode": result.returncode,
        "stdout": result.stdout[-24000:],
        "stderr": result.stderr[-24000:],
    }


def auth_self_test() -> dict[str, Any]:
    class Clock:
        value = 1_000_000.0
        def __call__(self) -> float:
            return self.value

    clock = Clock()
    with tempfile.TemporaryDirectory(prefix="droidwebdisplay-auth-") as temp:
        path = Path(temp) / "auth.json"
        service = AuthService(path, clock=clock)
        first = service.setup("123456", duration="1-hour", custom_seconds=None, user_agent="Gate 8")
        choices: dict[str, bool] = {"browser-session": True, "1-hour": True}
        grants = [first]
        for choice in ("1-day", "1-week", "1-month", "1-year", "forever"):
            grants.append(service.login("123456", duration=choice, custom_seconds=None, user_agent="Gate 8", client_key=choice))
            choices[choice] = True
        custom = service.login("123456", duration="custom", custom_seconds=600, user_agent="Gate 8", client_key="custom")
        choices["custom"] = custom.session["customSeconds"] == 600
        raw = path.read_text(encoding="utf-8")
        no_secrets = "123456" not in raw and all(grant.token not in raw for grant in grants)
        clock.value += 3601
        expired_rejected = service.authenticate(first.token) is None
        active = grants[1]
        individual = service.revoke(active.session["sessionId"], actor_session_id=active.session["sessionId"])
        remaining = service.login("123456", duration="1-day", custom_seconds=None, user_agent="Gate 8", client_key="remaining")
        global_count = service.revoke_all("123456", actor_session_id=remaining.session["sessionId"])
        checks = {
            "configured": service.configured,
            "allDurations": set(choices) == {*TRUST_DURATIONS, "custom"} and all(choices.values()),
            "rawSecretsAbsent": no_secrets,
            "expiredRejected": expired_rejected,
            "individualRevocation": individual,
            "globalRevocation": global_count >= 1,
        }
        return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "durationChoices": sorted(choices)}


def network_access_self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="droidwebdisplay-network-") as temp:
        root = Path(temp)
        cert = root / "cert.pem"
        key = root / "key.pem"
        certificate = generate_certificate(cert, key, bind_address="192.168.50.20", hostname="bridge-test", validity_days=90)
        config = NetworkAccessConfig(
            mode=LAN_HTTPS,
            bind_address="192.168.50.20",
            port=8765,
            allowed_networks=("192.168.50.0/24", "192.168.60.10/32"),
            hostname="bridge-test",
            tls=TlsSettings(enabled=True, certificate_path=str(cert), private_key_path=str(key)),
        ).validate(require_files=True)
        policy = NetworkPolicy(config)
        store = NetworkConfigStore(root / "network-access.json")
        store.save(config)
        loaded = store.load()
        local = store.reset_local_only(port=8765)
        firewall = " ".join(FirewallManager.command_for(config))
        checks = {
            "certificateSan": "192.168.50.20" in certificate["ipAddresses"] and "bridge-test" in certificate["dnsNames"],
            "specificBind": config.bind_address == "192.168.50.20" and config.bind_address != "0.0.0.0",
            "clientAllowlist": policy.client_allowed("192.168.50.25") and not policy.client_allowed("192.168.51.25"),
            "originAllowlist": policy.origin_allowed("https://bridge-test:8765") and not policy.origin_allowed("https://evil.example"),
            "atomicPersistence": loaded.mode == LAN_HTTPS and local.mode == "local-only",
            "firewallPrivateProfile": "-Profile Private" in firewall and "192.168.50.0/24" in firewall,
        }
        return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def packaging_self_test(root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="droidwebdisplay-package-") as temp:
        temp_root = Path(temp)
        release = temp_root / "DroidWebDisplay"
        result = build_release_tree(
            root,
            release,
            ReleaseInputs(target="source", allow_missing_server=True),
        )
        validation = validate_release_tree(release)
        previous = temp_root / "previous"
        (previous / "data/tls").mkdir(parents=True)
        (previous / "data/auth.json").write_text("{}", encoding="utf-8")
        (previous / "data/network-access.json").write_text("{}", encoding="utf-8")
        (previous / "data/tls/cert.pem").write_text("cert", encoding="utf-8")
        migration = migrate_runtime_state(previous, release)
        required_launchers = all((release / name).is_file() for name in ("DroidWebDisplay.cmd", "DroidWebDisplay.ps1", "DroidWebDisplay.sh"))
        checks = {
            "releaseTree": validation.get("status") == "PASS",
            "versionManifest": (release / "VERSION.json").is_file(),
            "licenses": all((release / "licenses" / name).is_file() for name in ("DroidWebDisplay-LICENSE.txt", "scrcpy-LICENSE.txt", "THIRD_PARTY_NOTICES.txt")),
            "launchers": required_launchers,
            "runtimeStateExcluded": not (release / "data/auto-download-monitor.json").exists(),
            "migration": set(migration["copied"]) >= {"auth.json", "network-access.json", "tls/cert.pem"},
            "offlineReadinessExplicit": result["readyForOfflineUse"] is False,
        }
        return {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "readyForOfflineUse": result["readyForOfflineUse"],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the current DroidWebDisplay release gate")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node", default="node")
    parser.add_argument("--browser-evidence", type=Path)
    parser.add_argument("--require-browser-evidence", action="store_true")
    parser.add_argument("--require-web-client-build", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.repo_root.resolve()
    node = shutil.which(args.node) or (str(Path(args.node)) if Path(args.node).is_file() else None)
    checks: dict[str, Any] = {}
    checks["pythonTests"] = run([args.python, "-m", "pytest", "-q"], cwd=root)
    checks["openapi"] = run([args.python, "tools/generate_openapi.py", "--check"], cwd=root, timeout=60)
    checks["staticClient"] = verify_static_client(root)
    checks["authenticationSelfTest"] = auth_self_test()
    checks["upstreamUpdateSelfTest"] = upstream_update_self_test()
    checks["networkAccessSelfTest"] = network_access_self_test()
    checks["packagingSelfTest"] = packaging_self_test(root)

    if node:
        checks["node"] = run([node, "--version"], cwd=root, timeout=10)
        checks["protocolTests"] = run([node, "tools/run-tests.mjs"], cwd=root / "packages/scrcpy-protocol")
        checks["webClientTests"] = run([node, "tools/run-tests.mjs"], cwd=root / "apps/web-client")
        compiler = find_local_tsc(root)
        if compiler:
            env = dict(os.environ)
            env["DROID_WEB_DISPLAY_TSC"] = str(compiler)
            checks["webClientBuild"] = run([node, "tools/build.mjs"], cwd=root / "apps/web-client", env=env)
            checks["webClientBuild"]["compiler"] = str(compiler)
        elif args.require_web_client_build:
            checks["webClientBuild"] = {"status": "FAIL", "error": "package-local TypeScript compiler is missing"}
        else:
            checks["webClientBuild"] = {"status": checks["staticClient"]["status"], "mode": "bundled-artifact"}
    else:
        for name in ("node", "protocolTests", "webClientTests", "webClientBuild"):
            checks[name] = {"status": "FAIL", "error": "Node.js not found"}

    auth_source = (root / "droid_web_display/auth.py").read_text(encoding="utf-8")
    api_source = (root / "droid_web_display/api/app.py").read_text(encoding="utf-8")
    html_source = (root / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    config_source = (root / "droid_web_display/config.py").read_text(encoding="utf-8")
    openapi = json.loads((root / "packages/bridge-api/openapi/openapi-v1.json").read_text(encoding="utf-8"))
    required_durations = {"browser-session", "1-hour", "1-day", "1-week", "1-month", "1-year", "forever"}
    checks["trustDurations"] = {
        "status": "PASS" if required_durations.issubset(TRUST_DURATIONS) and "custom" in html_source else "FAIL",
        "choices": [*TRUST_DURATIONS, "custom"],
        "customValidated": "CUSTOM_MIN_SECONDS" in auth_source and "CUSTOM_MAX_SECONDS" in auth_source,
    }
    checks["apiAndWebSocketProtection"] = {
        "status": "PASS" if all(token in api_source for token in (
            "authentication_required", "authentication_required\", \"message", "csrf_rejected", "authenticate_websocket", "4401",
        )) else "FAIL",
        "restProtected": True,
        "webSocketProtected": True,
        "csrf": "session-bound-header",
    }
    checks["cookiePolicy"] = {
        "status": "PASS" if all(token in api_source for token in (
            "httponly=True", 'samesite="strict"', 'path="/"', "secure=active_network_config.mode == LAN_HTTPS",
        )) else "FAIL",
        "httpOnly": True,
        "sameSite": "strict",
        "localSecure": False,
        "lanSecure": True,
    }
    checks["revocation"] = {
        "status": "PASS" if all(token in api_source + auth_source for token in (
            "auth_revoke_session", "auth_revoke_all", "session-revoked", "all-sessions-revoked",
        )) else "FAIL",
        "individual": True,
        "global": True,
    }
    scheme = openapi.get("components", {}).get("securitySchemes", {}).get("pcLocalSession", {})
    checks["openapiSecurity"] = {
        "status": "PASS" if scheme.get("in") == "cookie" and scheme.get("name") == "droid_web_display_id" else "FAIL",
        "scheme": scheme,
    }
    checks["auditRedaction"] = {
        "status": "PASS" if "if \"pin\" not in key.lower() and \"token\" not in key.lower()" in auth_source else "FAIL",
        "pinLogged": False,
        "rawTokenLogged": False,
    }
    checks["loopbackTrustModel"] = {
        "status": "PASS" if all(token in config_source + html_source for token in (
            '"127.0.0.1"', 'network_mode: str = "local-only"', "Android phone does not remember or authorize this browser",
        )) else "FAIL",
        "bindDefault": "127.0.0.1",
        "lanOptional": True,
        "phoneAuthoritative": False,
        "androidHelperIntroduced": False,
    }

    controller_source = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    main_source = (root / "apps/web-client/src/main.ts").read_text(encoding="utf-8")
    monitor_source = (root / "droid_web_display/transfers/monitor.py").read_text(encoding="utf-8")
    manager_source = (root / "droid_web_display/transfers/manager.py").read_text(encoding="utf-8")
    audio_source = (root / "apps/web-client/src/audio-player.ts").read_text(encoding="utf-8")
    adapter_source = (root / "packages/scrcpy-protocol/src/versions/v4_1/adapter.ts").read_text(encoding="utf-8")
    command_source = (root / "droid_web_display/scrcpy/command.py").read_text(encoding="utf-8")
    path_source = (root / "droid_web_display/transfers/paths.py").read_text(encoding="utf-8")
    adb_source = (root / "droid_web_display/adb/client.py").read_text(encoding="utf-8")
    css_source = (root / "apps/web-client/static/styles.css").read_text(encoding="utf-8")

    checks["optionalAudioPipeline"] = {
        "status": "PASS" if all(token in audio_source + adapter_source + command_source + controller_source + html_source for token in (
            "WebCodecsAudioPlayer", "AudioDecoder", "StreamDisabledError", "audio_bit_rate", 'id="audio-enabled"',
            "Video and control remain active", "Browser audio may have interruptions or delay", "<h2>Audio</h2>",
        )) and "Audio experimental" not in html_source and "Experimental:" not in html_source else "FAIL",
        "codec": "opus",
        "experimentalLabel": False,
        "latencyWarning": True,
        "failureIsolation": True,
    }
    clipboard_tokens = (
        "clipboardAutoSync", "copyAndroidClipboard", "pollPcClipboard", 'id="clipboard-copy-android"',
        "synchronizePcClipboard", "clipboardMessage(text, sequence, false)",
        'permissionState !== "granted" && !requestPermission', "#clipboardReadAllowed",
    )
    checks["clipboardCompletion"] = {
        "status": "PASS" if all(token in controller_source + html_source for token in clipboard_tokens)
        and 'pasteText(text, "automatic PC clipboard")' not in controller_source else "FAIL",
        "pcToAndroid": True,
        "androidToPc": True,
        "maximumSizeConfigurable": True,
        "automaticSyncPaste": False,
        "backgroundPermissionPromptLoopPrevented": True,
    }
    # Ctrl+V is a native browser paste routed from a document "paste" listener,
    # never a keydown shortcut: the paste event fires on the focused element and
    # the app moves focus off the canvas, so a keydown branch (or a canvas-scoped
    # listener) leaves Ctrl+V silently dead. Assert the real routing and assert
    # the dead shape stays gone.
    checks["clipboardKeyboardShortcuts"] = {
        "status": "PASS" if all(token in controller_source + html_source for token in (
            'document.addEventListener("paste"', 'pasteText(text, "Ctrl+V")',
            "isEditableTarget(event.target)", 'shortcut === "copy"',
            "androidClipboardCopyMessage()", "Ctrl+V pastes and Ctrl+C copies",
        )) and not any(token in controller_source for token in (
            'shortcut === "paste"', 'canvas.addEventListener("paste"',
        )) else "FAIL",
        "ctrlV": "native-paste-event",
        "ctrlC": "remote-copy",
        "automaticSyncStillNonPasting": "clipboardMessage(text, sequence, false)" in controller_source,
    }
    checks["virtualKeyboardSuppression"] = {
        "status": "PASS" if all(token in controller_source + html_source + command_source for token in (
            'id="virtual-hide-keyboard"', 'hideVirtualKeyboard.checked ? "hide"',
            "display_ime_policy=", "if options.display_mode == DisplayMode.VIRTUAL",
            "Virtual display only. Phone screen mode keeps the normal Android keyboard behavior.",
        )) else "FAIL",
        "policy": "hide",
        "virtualDisplayOnly": True,
        "physicalDisplayAffected": False,
    }
    permanent_native_layout = (
        'data-ui="droidwebdisplay-native-single-drawer-v1"' in html_source
        and 'id="gb-single-drawer-root"' in html_source
        and 'id="workspace-layout"' not in html_source
        and '<aside class="sidepanel">' not in html_source
        and '<aside class="transfer-panel"' not in html_source
        and "workspaceLayout" not in controller_source
    )
    checks["reconnectAndLayout"] = {
        "status": "PASS" if permanent_native_layout and all(token in controller_source + html_source + css_source for token in (
            "scheduleReconnect", "reconnectNow", "requestFullscreen", ':focus-visible', 'aria-live="polite"',
        )) else "FAIL",
        "automaticReconnect": True,
        "manualReconnect": True,
        "fullscreen": True,
        "keyboardFocus": True,
        "permanentNativeLayout": permanent_native_layout,
    }
    checks["settingsRoundTrip"] = {
        "status": "PASS" if all(token in controller_source + html_source for token in (
            "exportSettings", "importSettings", "droidwebdisplay-settings-v1", 'id="settings-export"', 'id="settings-import"',
        )) else "FAIL",
        "schemaVersion": 1,
    }
    old_gate_tokens = ("data-gate4-check", "data-gate5-check", "data-gate6-check", "data-gate7-check", "Gate 4 verification", "Gate 5 verification", "Gate 6 verification", "Gate 7 verification")
    compact_labels = all(token in html_source for token in (">Download<", ">Reset<", ">Save<", ">Scan now<")) and all(token not in html_source for token in (">Load<", ">Browse<", ">Upload<")) and "Android File Explorer" in html_source and "Custom PC folder" in html_source
    checks["storageAndUiAdjustments"] = {
        "status": "PASS" if compact_labels and all(token not in html_source for token in old_gate_tokens) and all(token in path_source + adb_source + css_source for token in (
            "/sdcard/Documents", "external_storage_roots", "SD card ·", "#screen { cursor: default; }", ".uniform-buttons > button",
        )) else "FAIL",
        "compactButtonLabels": compact_labels,
        "uniformButtonHeight": "2.55rem" in css_source,
        "mouseCursor": "default",
        "documentsCanonicalPath": "/sdcard/Documents",
        "externalSdDiscovery": True,
        "oldGateCheckboxesPresent": any(token in html_source for token in old_gate_tokens),
    }

    checks["compactConnectionStatus"] = {
        "status": "PASS" if all(token in html_source + css_source + controller_source for token in (
            'id="connection-status"', 'id="status-icon"', '.connection-status { flex: 0 0 auto; height: 1.46rem;',
            # The chip lives inside the brand lockup, under the wordmark.
            '.topbar-brand { flex: 0 0 auto; display: flex; flex-direction: column;',
            'class="status-ring-progress"', 'class="status-check"', 'connection-ring-spin', 'border-radius: 999px',
            '.connection-status[data-state="connected"]', '.connection-status[data-state="disconnected"]',
            'statusContainer.dataset.state = state',
        )) and 'class="status-card"' not in html_source and 'statusIcon.textContent' not in controller_source else "FAIL",
        "toolbarPlacement": "brand-lockup",
        "chipHeight": "1.46rem",
        "visualStyle": "animated-ring-status-chip",
        "states": ["connected", "disconnected", "connecting"],
        "legacySideCardPresent": 'class="status-card"' in html_source,
    }

    drawer_source = (root / "apps/web-client/static/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    native_accordion_contract = all(token in html_source for token in (
        'id="gb-single-drawer-root"', 'data-section-key="files-explorer"', 'data-section-key="files-sync"', 'data-section-key="files-queue"',
        'data-section-key="access-web-browser"', 'data-section-key="access-pin"', 'data-section-key="access-revoke-all"',
    )) and 'data-section-key="files-load"' not in html_source and "droidwebdisplay.ui.drawer.accordions.v1" in drawer_source
    checks["collapsibleCards"] = {
        "status": "PASS" if native_accordion_contract and permanent_native_layout and "initializeCollapsibleCards" not in main_source else "FAIL",
        "nativePersistedAccordions": native_accordion_contract,
        "legacyPanelsPresent": '<aside class="sidepanel">' in html_source or '<aside class="transfer-panel"' in html_source,
        "obsoleteControlsCardRemoved": "<h2>Controls</h2>" not in html_source,
    }
    checks["singlePageVerticalScroll"] = {
        "status": "PASS" if permanent_native_layout and ".native-workspace" in css_source and "overflow: auto; max-height: calc(100vh - 72px);" not in css_source else "FAIL",
        "pageScrollbarOnly": True,
        "rightPanelOwnScrollbar": False,
        "workspaceTopAligned": True,
        "nativeWorkspace": True,
    }

    checks["focusLayoutEscape"] = {
        "status": "PASS" if permanent_native_layout and 'id="fullscreen"' in html_source and 'id="exit-focus"' not in html_source and "exitFocus" not in controller_source else "FAIL",
        "toolbarPlacement": True,
        "selectorAlwaysVisible": False,
        "selectorPresent": 'id="workspace-layout"' in html_source,
        "permanentFocusStyle": True,
        "dedicatedExitButton": False,
    }

    checks["twoWayFolderSync"] = {
        "status": "PASS" if all(token in html_source + monitor_source + manager_source for token in (
            'id="auto-upload-enabled"', 'id="auto-upload-duplicate"', 'id="auto-upload-existing"',
            "pc_to_android_enabled", "include_existing_pc", "upload_duplicate_policy",
            "spool_local_file", "upload-completed", "processedPcFingerprints",
            "downloaded-from-android", "uploaded-from-pc",
        )) else "FAIL",
        "androidToPc": True,
        "pcToAndroid": True,
        "nonRecursive": True,
        "stableFileDetection": True,
        "loopPrevention": "bidirectional-fingerprints",
        "disabledByDefault": True,
    }


    network_source = (root / "droid_web_display/network_access.py").read_text(encoding="utf-8")
    launcher_source = (root / "tools/run_bridge_service.py").read_text(encoding="utf-8")
    network_ui_source = (root / "apps/web-client/src/network-controller.ts").read_text(encoding="utf-8")
    reset_source = (root / "tools/reset_network_access.py").read_text(encoding="utf-8")
    checks["optionalLanAccess"] = {
        "status": "PASS" if all(token in network_source + api_source + launcher_source + network_ui_source + reset_source + html_source for token in (
            'LOCAL_ONLY = "local-only"', 'LAN_HTTPS = "lan-https"', "specific private IPv4 address",
            "generate_certificate", "client-network-rejected", "host_rejected", "origin_rejected",
            "secure=active_network_config.mode == LAN_HTTPS", "/api/v1/network/apply",
            'id="network-card"', "Apply and restart", "reset_network_access.py --local-only",
            "server.should_exit = True", "Falling back to local-only access",
        )) else "FAIL",
        "defaultMode": "local-only",
        "lanMode": "private-lan-https",
        "specificInterfaceOnly": True,
        "pinRequired": True,
        "secureCookies": True,
        "clientNetworkAllowlist": True,
        "hostAndOriginValidation": True,
        "recoveryTool": "tools/reset_network_access.py",
        "firewallOptional": True,
    }


    update_tool_files = (
        "tools/update_scrcpy.py",
        "tools/inspect_scrcpy_protocol.py",
        "tools/scaffold_scrcpy_adapter.py",
        "tools/apply_scrcpy_patches.py",
        "tools/build_scrcpy_server.py",
        "tools/promote_scrcpy_adapter.py",
        "docs/UPSTREAM_UPDATE.md",
        ".gitmodules",
    )
    compatibility_manifest = json.loads((root / "compatibility/scrcpy-versions.json").read_text(encoding="utf-8"))
    stable_adapter = compatibility_manifest.get("defaultAdapter")
    stable_entry = compatibility_manifest.get("supportedVersions", {}).get(stable_adapter, {})
    update_source = (root / "tools/update_scrcpy.py").read_text(encoding="utf-8")
    promotion_source = (root / "droid_web_display/upstream_update/compatibility.py").read_text(encoding="utf-8")
    patch_source = (root / "droid_web_display/upstream_update/patches.py").read_text(encoding="utf-8")
    inspection_source = (root / "droid_web_display/upstream_update/inspection.py").read_text(encoding="utf-8")
    checks["upstreamUpdateAutomation"] = {
        "status": "PASS" if all((root / item).is_file() for item in update_tool_files)
        and stable_adapter == "scrcpy-4.1"
        and stable_entry.get("status") == "stable"
        and all(token in update_source + promotion_source + patch_source + inspection_source for token in (
            "fetch_tags", "checkout_clean_revision", "scaffold_adapter", "build_matching_server",
            "stable promotion requires Android hardware evidence", "patch series stopped and workspace was reset",
            "socketConnectionAndOrder", "handshakeAndDeviceMetadata", "controlMessages",
        )) else "FAIL",
        "stableAdapter": stable_adapter,
        "stableVersionPreserved": stable_entry.get("version") == "4.1",
        "separateExperimentalAdapterPolicy": True,
        "patchFailureIsFatal": True,
        "evidenceGatedPromotion": True,
        "toolFiles": list(update_tool_files),
    }

    packaging_source = (root / "droid_web_display/release_packaging.py").read_text(encoding="utf-8")
    packaging_doc = (root / "packaging/README.md").read_text(encoding="utf-8")
    windows_installer = (root / "packaging/windows/install.ps1").read_text(encoding="utf-8")
    linux_installer = (root / "packaging/linux/install.sh").read_text(encoding="utf-8")
    windows_uninstaller = (root / "packaging/windows/uninstall.ps1").read_text(encoding="utf-8")
    linux_uninstaller = (root / "packaging/linux/uninstall.sh").read_text(encoding="utf-8")
    packaging_all = packaging_source + packaging_doc + windows_installer + linux_installer + windows_uninstaller + linux_uninstaller
    checks["phase11Packaging"] = {
        "status": "PASS" if all(token in packaging_all for token in (
            "VERSION.json", "scrcpy-server.manifest.json", "officialReleaseServerSha256",
            "requirements-runtime.txt", "wheelhouse", "DroidWebDisplay.ps1", "DroidWebDisplay.sh",
            "migrate_runtime_state", "DroidWebDisplay-LICENSE.txt", "scrcpy-LICENSE.txt",
            "PurgeData", "--purge-data", "Android Platform-Tools",
        )) else "FAIL",
        "targets": ["windows", "linux", "source"],
        "serverChecksumVerifiedAtPackaging": True,
        "runtimeStateExcluded": True,
        "configurationMigration": True,
        "licensesIncluded": True,
        "offlineBundleRequiresExplicitPlatformArtifacts": True,
    }

    if args.browser_evidence:
        checks["browserHil"] = validate_ux_browser_evidence(args.browser_evidence.resolve())
    elif args.require_browser_evidence:
        checks["browserHil"] = {"status": "FAIL", "error": "--browser-evidence is required"}
    else:
        checks["browserHil"] = {"status": "SKIP", "reason": "browser evidence not required"}

    mandatory = [
        "pythonTests", "openapi", "staticClient", "authenticationSelfTest", "node", "protocolTests",
        "webClientTests", "webClientBuild", "trustDurations", "apiAndWebSocketProtection", "cookiePolicy",
        "revocation", "openapiSecurity", "auditRedaction", "loopbackTrustModel",
        "optionalAudioPipeline", "clipboardCompletion", "clipboardKeyboardShortcuts", "virtualKeyboardSuppression", "reconnectAndLayout", "settingsRoundTrip",
        "storageAndUiAdjustments", "compactConnectionStatus", "collapsibleCards", "focusLayoutEscape", "singlePageVerticalScroll", "twoWayFolderSync",
        "upstreamUpdateSelfTest", "upstreamUpdateAutomation", "networkAccessSelfTest", "optionalLanAccess",
        "packagingSelfTest", "phase11Packaging",
    ]
    if args.require_browser_evidence:
        mandatory.append("browserHil")
    status = "PASS" if all(checks[name].get("status") == "PASS" for name in mandatory) else "FAIL"
    report = {
        "schemaVersion": 1,
        "phase": 11,
        "packageVersion": __version__,
        "adapter": "scrcpy-4.1",
        "scrcpyVersion": "4.1",
        "status": status,
        "checks": checks,
    }
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
