# Repository Cleanup Report

Version 0.8.3 converts the accumulated phase-by-phase development package into a current-state repository.

Removed:

- Phase 1–7 CI workflows and launch scripts.
- Phase 1–7 gate tools and historical gate evidence.
- Phase 1–7 architecture, run, and gate-review documents.
- The obsolete server build/submodule framework and generated Python caches.
- Duplicate historical roadmap copies and package self-test files.

Preserved:

- All current runtime features.
- The pinned scrcpy v4.1 protocol adapter and fixtures.
- Relevant regression coverage, reorganized by feature instead of phase number.
- Current authentication, virtual-display, transfer, monitor, and UI documentation.
- The current release gate and browser evidence validation.
