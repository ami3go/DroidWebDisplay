# Current release Security Review

## Result

Automated security gate: PASS.

## Controls reviewed

- Loopback-only bind enforced.
- PIN is never stored or logged in plaintext.
- Password hashing is deliberately slow and salted.
- Session tokens are generated with a CSPRNG and persisted only as hashes.
- Session identifiers contain no user or device data.
- Cookies are HttpOnly and SameSite=Strict.
- State-changing REST operations require a session-bound CSRF value.
- WebSockets require authentication and same-origin upgrade.
- Absolute expiration is checked on every authenticated request.
- Individual and global revocation invalidate server-side records.
- Authentication database corruption fails closed.
- Audit events exclude PIN and token fields.
- Static UI uses textContent for session labels and diagnostics.
- No Android helper or phone-side trust database was introduced.

## Accepted limitations

- Supported runtime is loopback HTTP, not HTTPS. Consequently the cookie does not use `Secure`; the service refuses non-loopback binds.
- The local operating-system account can read or delete project data and can reset authentication. Current release does not claim protection from a compromised OS account.
- Browser-session trust has a 24-hour server maximum even if the browser stays open longer.
- “Forever” means until revocation on the server; the browser cookie is capped at ten years.
- Authentication protects the bridge service, not direct ADB access by other local processes.

## Recovery

A user with filesystem access can intentionally remove `data/auth.json` through `tools/reset_auth.py --yes`. The reset is local and does not modify Android.
