import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const files = [
  resolve(root, "tests/browser-support.test.mjs"),
  resolve(root, "tests/input.test.mjs"),
  resolve(root, "tests/api.test.mjs"),
  resolve(root, "tests/transfer.test.mjs"),
  resolve(root, "tests/display-config.test.mjs"),
  resolve(root, "tests/connection-profile.test.mjs"),
  resolve(root, "tests/layout.test.mjs"),
];
await new Promise((resolvePromise, reject) => {
  const child = spawn(process.execPath, ["--test", ...files], { stdio: "inherit" });
  child.on("exit", (code) => code === 0 ? resolvePromise() : reject(new Error(`tests exited ${code}`)));
});
