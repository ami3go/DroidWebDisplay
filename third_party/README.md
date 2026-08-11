# Third-party source checkouts

`third_party/scrcpy` is the clean upstream scrcpy submodule in a Git checkout. Release ZIP files do not embed the complete upstream repository. Initialize it with:

```bash
git submodule update --init --recursive third_party/scrcpy
```

For a release ZIP or a workspace without Git submodule metadata, `tools/update_scrcpy.py --clone-if-missing` can create the clean checkout from the official repository URL.

Do not place Gpt-Bridge changes inside the upstream checkout. Patch files belong in `patches/scrcpy/` and are applied only to temporary build workspaces.
