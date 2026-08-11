# Third-Party Notices

## scrcpy

- Project: scrcpy
- Copyright: Genymobile and scrcpy contributors
- Repository: `https://github.com/Genymobile/scrcpy`
- Pinned release: `v4.1`
- Pinned commit: `2926c06c5dc3064ae6d8db706f1a98a37cfcf3f0`
- License: Apache License 2.0

The scrcpy source is referenced as a Git submodule and the scrcpy server may be built or downloaded using the included Phase 1 tooling. The scrcpy license must accompany any distributed scrcpy binary.

## FastAPI

- Project: FastAPI
- License: MIT

## Uvicorn

- Project: Uvicorn
- License: BSD-3-Clause

## Pydantic

- Project: Pydantic
- License: MIT

## websockets

- Project: websockets
- Copyright: Aymeric Augustin and contributors
- License: BSD-3-Clause

Dependency versions are constrained in `pyproject.toml`. Release packaging should generate a resolved dependency inventory for the actual shipped environment.

## TypeScript

- Project: TypeScript
- Version: 5.8.3
- Publisher: Microsoft Corporation
- License: Apache License 2.0

TypeScript is a development-time compiler. The compiler itself is not bundled in the release ZIP; the generated JavaScript and declarations under `packages/scrcpy-protocol/dist/` are bundled so Gate 3 protocol tests can run with Node.js alone.

## python-multipart

FastAPI multipart form parsing for browser uploads. Licensed under Apache-2.0.

## Android SDK Platform-Tools (optional release component)

- Provider: Google LLC
- Component used by Gpt-Bridge: `adb`
- Distribution: Android SDK Platform-Tools
- License: Android Software Development Kit License Agreement

Platform-Tools are not silently downloaded or redistributed by the source package. A release builder may provide an accepted Platform-Tools directory to `tools/build_release.py`; the exact bundled revision is then recorded in `VERSION.json` when `source.properties` is present.
