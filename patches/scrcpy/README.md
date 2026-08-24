# DroidWebDisplay scrcpy patch series

Place numbered `*.patch` files here, for example:

```text
001-first-change.patch
002-follow-up.patch
```

The update tools apply patches in lexical order to a temporary clean clone. A failed check or application aborts the series and resets the temporary workspace. Patches are never applied directly to `third_party/scrcpy`.

The stable v4.1 server applies `001-deterministic-manual-clipboard.patch` so
manual Copy/Ctrl+C always receives a clipboard response even when the copied
Android text is unchanged. Native clipboard autosync remains enabled for
normal Android -> PC change notifications.
