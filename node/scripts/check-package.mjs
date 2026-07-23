import { readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const reportPath = resolve(".npm-pack.json");
let metadata;
try {
  [metadata] = JSON.parse(readFileSync(reportPath, "utf8"));
} finally {
  rmSync(reportPath, { force: true });
}

if (!metadata || !Array.isArray(metadata.files)) {
  throw new Error("npm pack report did not contain a package file list");
}

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
