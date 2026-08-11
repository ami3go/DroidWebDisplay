# Current release Architecture — Authentication and PC-Local Trusted Sessions

## Trust boundary

The authority is the Python bridge process and its local authentication database. The Android device is not involved in PIN verification, session issuance, browser recognition or revocation.

The supported network boundary is loopback only:

```text
127.0.0.1
localhost
::1
```

`BridgeConfig.validate()` rejects other bind hosts.

## Authentication storage

`data/auth.json` stores:

- A versioned PIN hash record.
- Trusted-session metadata.
- SHA-256 digests of session tokens.
- Per-session CSRF values.
- Bounded audit events.

It does not store:

- The PIN.
- Raw session tokens.
- Clipboard contents.
- Transferred file contents.

Writes use a temporary file and atomic replacement. File permissions are restricted where the platform supports POSIX permissions. Existing but malformed authentication storage causes startup failure rather than resetting security.

## PIN verification

PINs contain 4–12 digits. They are hashed with:

```text
PBKDF2-HMAC-SHA256
600,000 iterations
16-byte random salt
32-byte derived value
```

Verification uses constant-time comparison.

## Session model

A session contains:

- Public session ID.
- Random 256-bit bearer token, held only by the browser cookie.
- SHA-256 bearer-token digest in the database.
- Session-specific CSRF token.
- Creation, last-seen and optional absolute-expiration timestamps.
- Browser label and bounded User-Agent diagnostic.
- Revocation timestamp and reason.

The cookie is HttpOnly, SameSite=Strict and scoped to `/`. `Secure` is intentionally false because the supported runtime is loopback HTTP. Non-loopback HTTP is rejected rather than treated as supported deployment.

## REST protection

Public endpoints:

```text
GET  /api/v1/auth/status
POST /api/v1/auth/setup
POST /api/v1/auth/login
```

All other `/api/v1/*` endpoints require a valid trusted-session cookie. State-changing requests also require the session-specific `X-DroidWebDisplay-CSRF` header. Browser Origin is checked when supplied.

## WebSocket protection

Both session channels and the event stream validate:

1. Same-origin WebSocket upgrade.
2. Trusted-session cookie.
3. Session expiration and revocation.

Rejected upgrades close with:

```text
4401 authentication required
4403 origin rejected
```

## Expiration choices

```text
browser-session: session cookie, server maximum 24 hours
1-hour
1-day
1-week
1-month: 30 days
1-year: 365 days
forever: server-side until revoked; persistent cookie capped at 10 years
custom: 5 minutes to 10 years
```

## Revocation

- Logout revokes only the current session.
- Individual revoke targets one session ID.
- Global revoke requires the current PIN and revokes all sessions.
- PIN change requires the current PIN and revokes all sessions.

## Audit

Audit records include event type, timestamp, public session ID and non-sensitive result metadata. The audit writer removes keys containing `pin` or `token` before persistence.
