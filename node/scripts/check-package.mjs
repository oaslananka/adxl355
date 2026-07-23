import { spawnSync } from "node:child_process";

const result = spawnSync("npm", ["pack", "--dry-run", "--json"], {
  cwd: new URL("..", import.meta.url),
  encoding: "utf8",
  shell: process.platform === "win32",
});

if (result.status !== 0) {
  process.stderr.write(result.stderr || result.stdout);
  process.exit(result.status ?? 1);
}

const [metadata] = JSON.parse(result.stdout);
const files = metadata.files.map((entry) => entry.path).sort();
const required = [
  "LICENSE",
  "README.md",
  "dist/index.d.ts",
  "dist/index.js",
  "package.json",
];
const forbiddenPrefixes = ["src/", "test/", "scripts/"];
const forbiddenFiles = new Set(["tsconfig.json", "vitest.config.ts"]);

for (const path of required) {
  if (!files.includes(path)) {
    throw new Error(`package is missing required file: ${path}`);
  }
}

for (const path of files) {
  if (forbiddenPrefixes.some((prefix) => path.startsWith(prefix)) || forbiddenFiles.has(path)) {
    throw new Error(`package contains development-only file: ${path}`);
  }
  if (
    !path.startsWith("dist/") &&
    !["LICENSE", "README.md", "package.json"].includes(path)
  ) {
    throw new Error(`package contains unexpected file: ${path}`);
  }
}

console.log(`validated npm package contents (${files.length} files)`);
