import path from "node:path";
import { fileURLToPath } from "node:url";

const config = {
  agentRules: false,
  output: process.env.YAMS_STANDALONE === "1" ? "standalone" : undefined,
  outputFileTracingRoot: path.resolve(
    path.dirname(fileURLToPath(import.meta.url)),
    "../..",
  ),
};
export default config;
