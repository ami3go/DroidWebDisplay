import { readdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const names = (await readdir(join(root, "tests")))
  .filter((name) => name.endsWith(".test.mjs"))
  .sort()
  .map((name) => join(root, "tests", name));
if (!names.length) throw new Error("No JavaScript tests found");
const result = spawnSync(process.execPath, ["--test", ...names], { stdio: "inherit" });
process.exit(result.status ?? 1);
