# Current release Security Review

## Result

Automated security gate: PASS.

## Controls reviewed

- Local-only mode binds to loopback and does not expose the service to the LAN.
- LAN access is an explicit opt-in `lan-https` mode that requires TLS and applies configured private-network allowlisting.
- Host and Origin checks are enforced for browser/API access, including authenticated WebSocket upgrades.
- PIN is never stored or logged in plaintext.
- Password hashing is deliberately slow and salted.
- Session tokens are generated with a CSPRNG and persisted only as hashes.
- Session identifiers contain no user or device data.
- Authentication cookies are HttpOnly and SameSite=Strict.
- Authentication cookies use `Secure` when `lan-https` mode is active.
- State-changing REST operations require a session-bound CSRF value.
- WebSockets require authentication and an allowed origin.
- Absolute expiration is checked on every authenticated request.
- Individual and global revocation invalidate server-side records.
- Authentication database corruption fails closed.
- Audit events exclude PIN and token fields.
- Static UI uses textContent for session labels and diagnostics.
- Network configuration returned through the API does not expose TLS private-key material.
- No Android helper or phone-side trust database was introduced.

## Accepted limitations

- Local-only mode uses loopback HTTP by default. Its authentication cookie is therefore not marked `Secure`, but the service is restricted to loopback in that mode.
- LAN access is supported only through the explicit `lan-https` mode; LAN HTTP is not a supported exposure mode.
- Generated or privately issued TLS certificates may require explicit trust configuration in the client browser or operating system.
- The local operating-system account can read or delete project data and can reset authentication. The current release does not claim protection from a compromised OS account.
- Browser-session trust has a 24-hour server maximum even if the browser stays open longer.
- “Forever” means until revocation on the server; the browser cookie is capped at ten years.
- Authentication protects the bridge service, not direct ADB access by other local processes.

## Recovery

A user with filesystem access can intentionally remove `data/auth.json` through `tools/reset_auth.py --yes`. The reset is local and does not modify Android.

## Vulnerability reporting

See the repository-level `SECURITY.md` for supported-version policy and vulnerability-reporting guidance.
