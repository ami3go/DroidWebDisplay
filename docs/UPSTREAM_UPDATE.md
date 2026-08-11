# Controlled scrcpy upstream update workflow

Phase 10 keeps the currently approved scrcpy adapter and server available while a newer upstream revision is investigated in isolation.

## Invariants

- `compatibility/scrcpy-versions.json` keeps `scrcpy-4.1` as the default until another adapter reaches `stable`.
- Every target version receives a separate immutable directory under `packages/scrcpy-protocol/src/versions/`.
- The clean upstream checkout must have no tracked or untracked changes before and after the workflow.
- Optional DroidWebDisplay patches are stored outside the upstream checkout and applied only to temporary clones.
- A failed patch aborts the operation and resets the temporary clone.
- `experimental` is the only status assigned during registration.
- `candidate` requires automated evidence.
- `stable` requires automated, browser, and Android hardware evidence plus a verified matching server SHA-256.
- Only a stable adapter may become `defaultAdapter`.

## Initialize the upstream source

In a Git checkout:

```bash
git submodule update --init --recursive third_party/scrcpy
```

From a release ZIP:

```bash
python tools/update_scrcpy.py --target v4.2 --clone-if-missing --fetch
```

The target shown above is an example. Use the actual tag or full commit selected for review.

## Inspect only

```bash
python tools/inspect_scrcpy_protocol.py \
  --source-dir third_party/scrcpy \
  --base 2926c06c5dc3064ae6d8db706f1a98a37cfcf3f0 \
  --target <tag-or-commit> \
  --output-dir evidence/upstream/<version>
```

The JSON and Markdown reports classify changes affecting:

- server command-line options;
- socket connection order;
- handshake and device metadata;
- video and audio packet formats;
- control messages and clipboard behavior;
- shutdown and cleanup;
- Android API and build requirements.

The classification is a review aid, not automatic proof of compatibility.

## Full preparation workflow

```bash
python tools/update_scrcpy.py \
  --target <tag-or-commit> \
  --version <version> \
  --source-dir third_party/scrcpy \
  --fetch \
  --scaffold-adapter \
  --register \
  --report-dir evidence/upstream/<version>
```

This command:

1. verifies the upstream checkout is clean;
2. fetches tags when requested;
3. resolves the target to a full commit;
4. compares it with the current stable upstream commit;
5. writes protocol inspection reports;
6. creates a separate experimental adapter scaffold;
7. registers the adapter as experimental without changing the stable default;
8. writes a compatibility matrix and update summary.

Use `--select-source` only when the actual submodule checkout should move to the target commit. The operation refuses a dirty checkout and verifies that the resulting checkout remains clean.

## Build the matching server

The official upstream build uses its Gradle wrapper for the Android server. The tool builds in a temporary clone and copies only the resulting artifact and manifest into the DroidWebDisplay tree.

```bash
python tools/build_scrcpy_server.py \
  --source-dir third_party/scrcpy \
  --revision <tag-or-commit> \
  --patch-dir patches/scrcpy \
  --output server/scrcpy-server-v<version>.experimental
```

Use `--dry-run` to validate inputs without starting Gradle. Build prerequisites remain the JDK and Android SDK required by the selected upstream revision.

## Apply patches separately

```bash
python tools/apply_scrcpy_patches.py \
  --workspace <temporary-clean-scrcpy-clone> \
  --patch-dir patches/scrcpy
```

This command is intentionally restricted to a Git workspace. It should not be pointed at the permanent submodule.

## Promotion

Promote to candidate after automated protocol and compatibility tests:

```bash
python tools/promote_scrcpy_adapter.py \
  --adapter scrcpy-<version> \
  --status candidate \
  --automated-evidence evidence/upstream/<version>/gate-automated.json
```

Promote to stable only after all required evidence and a verified server build are recorded:

```bash
python tools/promote_scrcpy_adapter.py \
  --adapter scrcpy-<version> \
  --status stable \
  --automated-evidence <automated-report> \
  --browser-evidence <browser-report> \
  --hardware-evidence <hardware-report>
```

Add `--make-default` only to the stable promotion after release approval.

## Gate 10

```bash
python tools/release_gate.py --output evidence/release/gate10.json
```

The gate runs a local temporary-Git self-test. It verifies relevant-area detection, isolated adapter creation, stable-default preservation, fatal patch failure, clean upstream state, and evidence-gated promotion without requiring network access.
