# DroidWebDisplay Desktop Host

DroidWebDisplay uses a small cross-platform desktop host around the existing browser service. The browser remains the primary Android-control UI; the desktop host owns the local server lifecycle.

## Default desktop behavior

Launching the packaged application on Windows or a graphical Linux session:

1. starts the embedded DroidWebDisplay server;
2. opens the browser unless disabled in settings or with `--no-browser`;
3. keeps a small server manager available;
4. shows a system-tray/status icon when the desktop provides a tray;
5. keeps the server running when the browser tab is closed;
6. stops the server cleanly when **Exit DroidWebDisplay** is selected.

The manager shows server state, URL, network mode, Android/ADB state, PID, uptime, and the last server error. It provides Start, Stop, Restart, Open Browser, Open Logs, autostart, and Exit controls.

## Windows

The PyInstaller executable is built as a windowed application, so normal launches do not create a console window. User autostart is stored under the current user's Windows `Run` registry key.

Persistent state and logs are kept below `%LOCALAPPDATA%\DroidWebDisplay`.

## Linux

On a graphical Linux session the same Qt desktop host is used. Qt uses the desktop's StatusNotifierItem/XEmbed tray support when available. If no tray is available, the server manager stays accessible as a normal minimized window and essential controls do not depend on the tray.

Desktop autostart is written to `~/.config/autostart/droidwebdisplay.desktop` (or `$XDG_CONFIG_HOME/autostart`).

Persistent state and logs are kept below `$XDG_STATE_HOME/droidwebdisplay` or `~/.local/state/droidwebdisplay`.

When neither `DISPLAY` nor `WAYLAND_DISPLAY` is available, DroidWebDisplay automatically falls back to headless server mode instead of trying to start Qt.

## Command line

```text
DroidWebDisplay                    # desktop host + server + browser
DroidWebDisplay --no-browser       # desktop host + server, no automatic browser
DroidWebDisplay --start-minimized  # desktop host starts minimized/to tray
DroidWebDisplay --headless         # server only; no desktop GUI and no automatic browser
DroidWebDisplay --headless --open-browser
```

Additional server arguments such as `--port 9000` are forwarded by the desktop host.

## Lifecycle and cleanup

The desktop host runs the existing Uvicorn service in a managed worker thread. Stop, Restart, Exit, SIGTERM, and SIGINT request `uvicorn.Server.should_exit` rather than killing the server directly. Normal FastAPI lifespan shutdown therefore closes the auto-download monitor, transfer manager, and scrcpy session manager before the host exits.

If graceful shutdown exceeds its timeout during application exit, the host terminates remaining child processes as a last-resort orphan-prevention measure.

## Single instance

Only one desktop host instance is allowed per user session. A second launch contacts the existing instance through a Qt local socket, raises the manager window, and opens DroidWebDisplay instead of starting a second server.

A separately started/headless DroidWebDisplay server is detected as an external instance. The desktop host can open it but will not stop or restart a server it does not own.

## Logs

Desktop/server output is written to `desktop-host.log` under the platform state log directory. The file rotates at approximately 2 MiB and keeps three older generations.
