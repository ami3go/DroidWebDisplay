# DroidWebDisplay Stability Contract

## Purpose

DroidWebDisplay evolves incrementally. The current known-good behavior on `main` is the baseline until a change proves that a replacement is equal or better.

The goal is monotonic improvement: new work may extend, refactor, optimize, or replace existing architecture, but must not silently reduce already-working user-visible behavior.

## What counts as a regression

A regression is any change that causes previously supported behavior to stop working, become materially less reliable, require a new manual workaround, or interfere with another working subsystem.

Examples:

- fixing manual clipboard Copy by disabling automatic Android -> PC sync;
- improving virtual display behavior while changing the physical display unexpectedly;
- adding clipboard automation that blocks normal keyboard typing;
- changing session startup in a way that restores one bug but reintroduces black-screen startup;
- simplifying subprocess creation while bringing back visible Windows console flashes.

A regression remains a regression even if the new implementation is architecturally cleaner.

## Stability principle

Existing working user-visible behavior is a compatibility contract.

A replacement architecture is acceptable only when all affected contracts are preserved and the replacement is justified as equal-or-better in at least one meaningful dimension such as reliability, maintainability, performance, security, or supported capability.

## Protected behavior families

The following are especially sensitive because they cross component boundaries:

- Android <-> PC clipboard synchronization;
- keyboard input and shortcuts;
- browser focus and permission handling;
- scrcpy control protocol and server arguments;
- virtual-display lifecycle and physical-display isolation;
- video startup, reconnect, rotation, and resize;
- file transfer and folder synchronization;
- Windows hidden/background process behavior;
- packaged Windows and Linux runtime behavior.

Changes in one of these areas should be assumed capable of affecting related areas until tests demonstrate otherwise.

## Change policy

For a change that touches a protected behavior:

1. Identify the user-visible contract before editing code.
2. Preserve all existing directions/modes, not only the path being fixed.
3. Add or update behavioral regression coverage.
4. Prefer tests of public behavior or generated protocol/server arguments over source-text matching.
5. Run the complete release gate before merge.
6. Do not weaken tests to match a regression.
7. If architecture changes intentionally, update the relevant contract and ADR.

## Architecture replacement policy

Current architecture is not frozen forever. It may be replaced when the new design:

- preserves all documented compatibility contracts;
- does not create new user-visible regressions;
- has regression coverage for the affected behavior;
- explains why the replacement is better;
- updates architecture/ADR documentation before merge.

If those conditions are not met, retain the existing implementation and make the requested feature around it.

## Regression-test policy

Tests should encode behavior rather than incidental implementation whenever possible.

Bad protection:

```python
assert 'some_internal_flag=false' in source
```

Better protection:

```python
args = build_server_arguments(...)
assert 'some_internal_flag=false' not in args
```

Best protection, when practical, is an integration/HIL test that exercises the complete user path.

## Release policy

A release candidate is acceptable only when:

- the release gate passes;
- relevant regression tests pass;
- Windows package smoke tests pass;
- Linux AppImage smoke tests pass;
- no known protected behavior is degraded.

Known functional regressions must be fixed before release rather than documented as acceptable side effects unless the project explicitly decides to remove that feature.
