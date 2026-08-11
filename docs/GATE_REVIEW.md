# Current release Gate Review

## Automated acceptance

- Untrusted REST access rejected.
- Untrusted WebSocket access rejected.
- First PIN setup works.
- Login works.
- All required trust-duration choices work.
- Invalid custom duration rejected.
- Expired session rejected.
- Individual revocation works.
- Global revocation works.
- PIN change invalidates existing sessions.
- Raw PIN and session tokens absent from persistent storage and audit.
- OpenAPI declares cookie authentication.
- Loopback-only default retained.
- UI states PC-local trust and does not claim phone-authoritative memory.
- No Android helper application introduced.

## Regression layers

Gate 8 retains:

- Python suite.
- Browser-client suite.
- scrcpy v4.1 protocol suite.
- OpenAPI determinism.
- Hash-verified static browser bundle.
- Optional strict TypeScript build.
