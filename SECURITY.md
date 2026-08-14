# Security Policy

## Supported versions

DroidWebDisplay currently supports security fixes on the active release line represented by the latest published 0.11.x release and the current `main` branch.

Older release lines are not guaranteed to receive security updates. Users should reproduce a reported issue on the latest available release before filing it when practical.

## Reporting a vulnerability

Please do not publish exploit details, credentials, tokens, PINs, private keys, device identifiers, or other sensitive evidence in a public GitHub issue.

Use GitHub's private vulnerability reporting for this repository. Open the repository's **Security** area and choose **Report a vulnerability** to submit the report privately to the maintainer.

Include enough information to reproduce and assess the issue:

- affected DroidWebDisplay version or commit SHA;
- operating system and browser;
- Android device/version when relevant;
- whether the service was running in `local-only` or `lan-https` mode;
- concise reproduction steps;
- expected and observed behavior;
- impact and realistic attack prerequisites;
- relevant logs or screenshots with secrets and personal data redacted;
- whether the issue has been disclosed elsewhere.

Do not send live credentials, authentication cookies, PINs, TLS private keys, or other reusable secrets as test evidence.

## Disclosure and handling

Please allow the maintainer a reasonable opportunity to reproduce, assess, fix, and release a correction before public disclosure. Coordinated disclosure timing should be agreed through the private vulnerability report.

Security fixes may be released on the active release line and may require users to upgrade rather than backporting fixes to older releases.

## Security model

DroidWebDisplay is designed to run as a PC-local bridge by default. Local-only mode binds to loopback. Optional LAN access is explicit and uses HTTPS with network restrictions. Authentication protects access to the DroidWebDisplay bridge service; it does not protect direct ADB access available to other processes or users that already control the host operating system.

For the implementation-focused review of current controls and accepted limitations, see `docs/SECURITY_REVIEW.md`.
