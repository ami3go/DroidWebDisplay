import assert from "node:assert/strict";
import test from "node:test";
import { androidBreadcrumbs, DeletedAndroidPathTracker, formatBytes, parentAndroidPath, sortStorageEntries, UploadExplorerRefreshTracker } from "../dist/assets/transfer-controller.js";

test("formats transfer sizes deterministically", () => {
  assert.equal(formatBytes(0), "0 B");
  assert.equal(formatBytes(1024), "1.00 KiB");
  assert.equal(formatBytes(10 * 1024 * 1024), "10.0 MiB");
});

test("Android storage parent navigation stays inside the active shared root", () => {
  assert.equal(parentAndroidPath("/sdcard/Download/folder/file"), "/sdcard/Download/folder");
  assert.equal(parentAndroidPath("/sdcard/Download"), "/sdcard/Download");
  assert.equal(parentAndroidPath("/sdcard/Documents/project"), "/sdcard/Documents");
  assert.equal(parentAndroidPath("/sdcard/Pictures"), "/sdcard/Pictures");
});

test("Explorer breadcrumbs preserve the selected Android shared root", () => {
  assert.deepEqual(androidBreadcrumbs("/sdcard/Download/reports/2026"), [
    { label: "Download", path: "/sdcard/Download" },
    { label: "reports", path: "/sdcard/Download/reports" },
    { label: "2026", path: "/sdcard/Download/reports/2026" },
  ]);
  assert.deepEqual(androidBreadcrumbs("/sdcard/Documents"), [
    { label: "Documents", path: "/sdcard/Documents" },
  ]);
});

test("Explorer sorting keeps folders first and supports details columns", () => {
  const entries = [
    { name: "z.txt", path: "/sdcard/Download/z.txt", mode: 0, size: 5, modifiedAt: 10, isDirectory: false },
    { name: "Folder 2", path: "/sdcard/Download/Folder 2", mode: 0, size: 0, modifiedAt: 5, isDirectory: true },
    { name: "a.txt", path: "/sdcard/Download/a.txt", mode: 0, size: 20, modifiedAt: 20, isDirectory: false },
  ];
  assert.deepEqual(sortStorageEntries(entries, "name", "ascending").map((item) => item.name), ["Folder 2", "a.txt", "z.txt"]);
  assert.deepEqual(sortStorageEntries(entries, "size", "descending").map((item) => item.name), ["Folder 2", "a.txt", "z.txt"]);
  assert.deepEqual(sortStorageEntries(entries, "modified", "ascending").map((item) => item.name), ["Folder 2", "z.txt", "a.txt"]);
});

test("Explorer refresh waits for a verified drop upload and only refreshes an affected path", () => {
  const transfer = (transferId, state, destinationPath = "/sdcard/Download/DroidWebDisplayInbox/report.txt") => ({
    transferId,
    direction: "upload",
    serial: "PHONE",
    destinationPath,
    state,
  });
  const tracker = new UploadExplorerRefreshTracker();
  tracker.track(transfer("T1", "queued"));
  assert.equal(tracker.consumeCompleted([transfer("T1", "transferring")], "PHONE", "/sdcard/Download"), false);
  assert.equal(tracker.consumeCompleted([transfer("T1", "completed")], "PHONE", "/sdcard/Download"), true);
  assert.equal(tracker.consumeCompleted([transfer("T1", "completed")], "PHONE", "/sdcard/Download"), false);

  tracker.track(transfer("T2", "queued"));
  assert.equal(tracker.consumeCompleted([transfer("T2", "failed")], "PHONE", "/sdcard/Download"), false);

  tracker.track(transfer("T3", "queued", "/sdcard/Pictures/image.png"));
  assert.equal(tracker.consumeCompleted([transfer("T3", "completed", "/sdcard/Pictures/image.png")], "PHONE", "/sdcard/Download"), false);
});

test("Recent pictures hide deleted MediaStore rows until Android drops the stale index entry", () => {
  const entry = (path) => ({
    name: path.split("/").at(-1),
    path,
    mode: 0,
    size: 1,
    modifiedAt: 1,
    isDirectory: false,
  });
  const deletedFile = entry("/sdcard/DCIM/deleted photo.jpg");
  const deletedChild = entry("/sdcard/Pictures/old album/child.jpg");
  const kept = entry("/sdcard/DCIM/kept.jpg");
  const tracker = new DeletedAndroidPathTracker();

  tracker.track(deletedFile.path, false);
  tracker.track("/sdcard/Pictures/old album", true);
  assert.deepEqual(tracker.filter([deletedFile, deletedChild, kept]), [kept]);
  assert.deepEqual(tracker.filter([kept]), [kept]);
  // Once MediaStore has omitted the tombstones, a genuinely recreated path is
  // visible again instead of being hidden for the rest of the browser session.
  assert.deepEqual(tracker.filter([deletedFile, kept]), [deletedFile, kept]);
});
