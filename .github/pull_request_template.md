## Summary

<!-- What changes and why? -->

## Stability impact

<!-- Which existing user-visible behaviors could this affect? -->

Protected areas touched:

- [ ] Android <-> PC clipboard
- [ ] Keyboard / Ctrl+C / Ctrl+V
- [ ] Browser focus / clipboard permissions
- [ ] scrcpy control protocol / server arguments
- [ ] Physical display
- [ ] Virtual display
- [ ] Video startup / reconnect / rotation / resize
- [ ] File transfer / sync
- [ ] Windows background process handling
- [ ] Packaging / release runtime
- [ ] None of the above

## Compatibility contract

- [ ] I read `AGENTS.md` and `docs/STABILITY_CONTRACT.md`.
- [ ] I reviewed the relevant contract under `docs/contracts/`.
- [ ] Existing working behavior is preserved or intentionally improved.
- [ ] This change does not fix one path by disabling/degrading another.
- [ ] Architecture changes are documented with an ADR or equivalent rationale.

## Validation

- [ ] Relevant regression tests added/updated.
- [ ] Tests assert behavior rather than only source-text implementation details where practical.
- [ ] Web-client tests pass when browser/control behavior changed.
- [ ] Complete release gate passes before merge.
- [ ] Windows package smoke passes when relevant.
- [ ] Linux AppImage smoke passes when relevant.
- [ ] No known protected behavior is degraded.

## Regression notes

<!-- Explicitly list known risks, manual checks, or HIL checks. Do not leave a known regression implicit. -->
