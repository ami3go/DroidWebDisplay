import { access, cp, mkdir, readdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { constants } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, relative, resolve } from "node:path";
import { spawn } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(root, "../..");
const protocolRoot = resolve(repo, "packages/scrcpy-protocol");
const dist = resolve(root, "dist");
const manifestPath = resolve(root, "dist-manifest.json");
const stage = resolve(root, `.dist-stage-${process.pid}`);
const backup = resolve(root, `.dist-backup-${process.pid}`);

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function resolveCompiler() {
  const candidates = [
    process.env.GPT_BRIDGE_TSC,
    resolve(root, "node_modules/typescript/bin/tsc"),
    resolve(protocolRoot, "node_modules/typescript/bin/tsc"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      await access(candidate, constants.R_OK);
      return candidate;
    } catch {
      // Continue to the next pinned package-local candidate.
    }
  }
  throw new Error(
    "TypeScript compiler is not installed. The bundled dist remains unchanged. " +
    "Run `npm.cmd ci` in apps\\web-client (Windows) or `npm ci` there, then retry."
  );
}

async function runCompiler(compiler) {
  const args = [compiler, "-p", resolve(root, "tsconfig.json"), "--outDir", resolve(stage, "assets")];
  await new Promise((resolvePromise, reject) => {
    const child = spawn(process.execPath, args, { stdio: "inherit", shell: false });
    child.on("error", reject);
    child.on("exit", (code) => code === 0 ? resolvePromise() : reject(new Error(`tsc exited ${code}`)));
  });
}

async function listFiles(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) result.push(...await listFiles(path));
    else if (entry.isFile()) result.push(path);
  }
  return result.sort();
}

async function createManifest(directory) {
  const files = [];
  for (const path of await listFiles(directory)) {
    const data = await readFile(path);
    files.push({
      path: relative(directory, path).replaceAll("\\\\", "/"),
      bytes: data.byteLength,
      sha256: createHash("sha256").update(data).digest("hex"),
    });
  }
  return {
    schemaVersion: 1,
    packageVersion: "0.11.2",
    generatedBy: "apps/web-client/tools/build.mjs",
    files,
  };
}

async function installStage() {
  await rm(backup, { recursive: true, force: true });
  const hadDist = await exists(dist);
  if (hadDist) await rename(dist, backup);
  try {
    await rename(stage, dist);
    await rm(backup, { recursive: true, force: true });
  } catch (error) {
    await rm(dist, { recursive: true, force: true });
    if (hadDist && await exists(backup)) await rename(backup, dist);
    throw error;
  }
}

const compiler = await resolveCompiler(); // Resolve before touching the bundled dist.
if (!await exists(resolve(protocolRoot, "dist/src/index.js"))) {
  throw new Error("Compiled scrcpy protocol adapter is missing: packages/scrcpy-protocol/dist/src/index.js");
}

await rm(stage, { recursive: true, force: true });
await mkdir(stage, { recursive: true });
try {
  await runCompiler(compiler);
  await cp(resolve(root, "static"), stage, { recursive: true });
  await mkdir(resolve(stage, "vendor/scrcpy-protocol"), { recursive: true });
  await cp(resolve(protocolRoot, "dist"), resolve(stage, "vendor/scrcpy-protocol"), { recursive: true });
  const manifest = await createManifest(stage);
  await installStage();
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
  console.log(`Built web client with ${manifest.files.length} files using ${compiler}`);
} catch (error) {
  await rm(stage, { recursive: true, force: true });
  throw error;
}
