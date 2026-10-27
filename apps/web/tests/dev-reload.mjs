import assert from "node:assert/strict";
import { mkdir, writeFile, unlink, rmdir } from "node:fs/promises";
import { chromium } from "@playwright/test";

const origin = process.argv[2];
assert(origin && new URL(origin).hostname === "127.0.0.1");
const directory = "src/app/dev-reload-verification";
// Refuse existing paths; cleanup owns only this newly created test route.
await mkdir(directory);
let browser;
try {
  const source = (text) =>
    `export default function Probe() { return <h1>${text}</h1>; }\n`;
  await writeFile(`${directory}/page.tsx`, source("Reload before"), {
    flag: "wx",
  });
  browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(`${origin}/dev-reload-verification`);
  await page
    .getByRole("heading", { name: "Reload before", exact: true })
    .waitFor();
  await writeFile(`${directory}/page.tsx`, source("Reload after"));
  // No page.reload(): the existing browser must receive the development update.
  await page
    .getByRole("heading", { name: "Reload after", exact: true })
    .waitFor();
  console.log("Native web hot reload passed without a browser reload");
} finally {
  await browser?.close();
  await unlink(`${directory}/page.tsx`).catch((error) => {
    if (error.code !== "ENOENT") throw error;
  });
  await rmdir(directory);
}
