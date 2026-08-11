# Two-way watched-folder transfer

The automatic transfer card can monitor one Android folder and one PC destination profile in both directions.

## Android to PC

- Uses structured ADB Sync LIST, STAT and RECV operations.
- Waits for stable size and modification time before queueing.
- Existing Android files are baselined by default.
- Optional verified source deletion remains available.

## PC to Android

- Watches the selected PC destination folder non-recursively.
- Copies a stable file into the managed upload spool; the original PC file is never passed to a worker that deletes spool files.
- Existing PC files are baselined by default.
- Duplicate handling can overwrite, rename safely, or fail.
- Upload completion is verified by Android file size.

## Loop prevention

Both local and Android fingerprints are persisted. A file produced by Android-to-PC download is marked before the PC scan, and a file produced by PC-to-Android upload is marked before the Android scan. This prevents immediate transfer loops between the two directions.

Partial and hidden files are ignored. Monitoring is disabled by default.
