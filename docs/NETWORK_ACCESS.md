# Optional private-LAN access

DroidWebDisplay remains local-only by default and listens on `127.0.0.1:8765`.

The authenticated **Network access** card can enable access from approved devices on a private LAN. LAN mode requires:

- a specific active private IPv4 interface
- HTTPS
- PIN authentication
- a private IPv4 client allowlist
- Host and Origin validation
- Secure, HttpOnly, SameSite=Strict session cookies

The service never selects `0.0.0.0` automatically and the normal UI rejects public interfaces and allowlists broader than `/16`.

## Enabling LAN access

1. Open DroidWebDisplay locally and authenticate.
2. Open **Network access**.
3. Select **Private LAN with HTTPS**.
4. Select the active Ethernet or Wi-Fi interface.
5. Review the allowed subnet. Narrow it to `/32` entries when only specific clients should connect.
6. Generate an offline certificate or provide an existing PEM certificate and key that match the selected IP/hostname.
7. Optionally request a Windows Firewall rule scoped to the Private profile and configured allowlist.
8. Enter the current PIN and press **Validate**.
9. Press **Apply and restart**.

All trusted sessions are revoked when the network trust boundary changes. Sign in again at the displayed HTTPS URL.

A generated certificate is self-signed. The browser may show a warning until the downloaded public certificate is trusted on the client device. The private key is never downloadable through the API.

## Recovery

Stop the service and run:

```powershell
python tools\reset_network_access.py --local-only
```

This restores `127.0.0.1`, disables TLS, removes only the project-managed firewall rule when possible, and revokes LAN sessions without changing the PIN.

If the configured LAN listener or certificate fails during startup, the launcher automatically writes a local-only configuration and restarts on `127.0.0.1`.

## Security boundary

LAN mode is for trusted private networks only. It is not intended for Internet exposure, router port forwarding, public IP binding, wildcard CORS, or cloud relay use.
