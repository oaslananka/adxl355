import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const [reportPath = ".npm-install-pack.json"] = process.argv.slice(2);
const [metadata] = JSON.parse(readFileSync(resolve(reportPath), "utf8"));
if (!metadata?.filename) throw new Error("npm pack report did not contain a filename");
const npmCli = process.env.npm_execpath;
if (!npmCli) throw new Error("npm_execpath is required");

const archivePath = resolve(metadata.filename);
const root = mkdtempSync(join(tmpdir(), "adxl355-node-core-only-"));
try {
  writeFileSync(join(root, "package.json"), '{"private":true,"type":"module"}\n');
  const install = spawnSync(
    process.execPath,
    [
      npmCli,
      "install",
      "--ignore-scripts",
      "--omit=optional",
      "--no-audit",
      "--no-fund",
      archivePath,
    ],
    { cwd: root, encoding: "utf8" },
  );
  if (install.status !== 0) {
    throw new Error(`core-only install failed: ${install.stderr || install.stdout}`);
  }

  const smokePath = join(root, "smoke.mjs");
  writeFileSync(
    smokePath,
    `
      import { ADXL355, BusError } from "@oaslananka/adxl355";
      import { LinuxSpiTransport } from "@oaslananka/adxl355/linux/spi";
      import { LinuxI2cTransport } from "@oaslananka/adxl355/linux/i2c";
      if (typeof ADXL355 !== "function") throw new Error("core import failed");
      for (const open of [LinuxSpiTransport.open, LinuxI2cTransport.open]) {
        try {
          await open.call(null);
          throw new Error("optional backend unexpectedly opened");
        } catch (error) {
          if (!(error instanceof BusError)) throw error;
        }
      }
      console.log("core-only optional dependency smoke passed");
    `,
  );
  const smoke = spawnSync(process.execPath, [smokePath], {
    cwd: root,
    encoding: "utf8",
  });
  if (smoke.status !== 0) {
    throw new Error(`core-only smoke failed: ${smoke.stderr || smoke.stdout}`);
  }
  process.stdout.write(smoke.stdout);
} finally {
  rmSync(root, { recursive: true, force: true });
  rmSync(resolve(reportPath), { force: true });
  rmSync(archivePath, { force: true });
}
