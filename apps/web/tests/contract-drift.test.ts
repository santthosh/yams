// @vitest-environment node
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, it } from "vitest";

it("changes generated TS when the schema changes and fails drift until regenerated", async () => {
  const directory = await mkdtemp(path.join(tmpdir(), "yams-contract-drift-"));
  try {
    const schema = JSON.parse(
      await readFile(
        new URL("../../../contracts/openapi.json", import.meta.url),
        "utf8",
      ),
    );
    const schemaPath = path.join(directory, "openapi.json");
    const script = fileURLToPath(
      new URL("../scripts/contracts.mjs", import.meta.url),
    );
    const args = [
      script,
      `--schema=${schemaPath}`,
      `--output-dir=${directory}`,
    ];
    await writeFile(schemaPath, JSON.stringify(schema));
    execFileSync(process.execPath, args);
    const before = await readFile(path.join(directory, "schema.ts"), "utf8");
    schema.components.schemas.Liveness.properties.drift_probe = {
      type: "string",
    };
    await writeFile(schemaPath, JSON.stringify(schema));
    expect(() =>
      execFileSync(process.execPath, [...args, "--check"], { stdio: "pipe" }),
    ).toThrow();
    execFileSync(process.execPath, args);
    const after = await readFile(path.join(directory, "schema.ts"), "utf8");
    expect(after).not.toBe(before);
    expect(after).toContain("drift_probe");
    execFileSync(process.execPath, [...args, "--check"]);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 15000);
