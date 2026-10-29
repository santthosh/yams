// Test-only SYNTHETIC_DATA_ONLY transport. Never imported by application code.
import http from "node:http";
import fs from "node:fs";
const fixtures = JSON.parse(
  fs.readFileSync(
    new URL("./transport-fixtures.json", import.meta.url),
    "utf8",
  ),
);
let mode = "ready";
let jobReads = 0;
const correlation = "33333333-3333-4333-8333-333333333333";
const server = http.createServer(async (request, response) => {
  const send = (body, status = 200) => {
    if (!response.destroyed) {
      response.writeHead(status, { "Content-Type": "application/json" });
      response.end(JSON.stringify(body));
    }
  };
  if (request.url === "/__control" && request.method === "POST") {
    let body = "";
    for await (const chunk of request) {
      body += chunk;
      if (body.length > 1024) {
        send({}, 413);
        return;
      }
    }
    const selected = JSON.parse(body).mode;
    if (!["ready", "not_ready", "timeout", "error"].includes(selected)) {
      send({}, 400);
      return;
    }
    mode = selected;
    jobReads = 0;
    send({ mode, label: fixtures.label });
    return;
  }
  if (request.url === "/__ready") {
    send({ label: fixtures.label });
    return;
  }
  if (mode === "timeout")
    await new Promise((resolve) => setTimeout(resolve, 4000));
  if (mode === "error") {
    send(
      {
        error: {
          message: "RAW_STACK_TRACE secret_database_password",
          correlation_id: correlation,
        },
      },
      500,
    );
    return;
  }
  if (request.url === "/api/v1/health") {
    send(
      mode === "not_ready"
        ? {
            ...fixtures.health,
            status: "not_ready",
            database: { status: "failed", reason: "DATABASE_UNAVAILABLE" },
            fixture_metadata: null,
            fixtures: { status: "failed", reason: "FIXTURES_UNAVAILABLE" },
          }
        : fixtures.health,
      mode === "not_ready" ? 503 : 200,
    );
    return;
  }
  if (request.url === "/api/v1/portfolios?limit=25") {
    send({ items: [], next_cursor: null });
    return;
  }
  if (request.url === "/api/v1/workspace") {
    send(
      mode === "not_ready"
        ? { error: { correlation_id: correlation } }
        : fixtures.workspace,
      mode === "not_ready" ? 503 : 200,
    );
    return;
  }
  if (request.url === `/api/v1/jobs/${fixtures.job.id}`) {
    jobReads += 1;
    const completed = jobReads >= 2;
    send({
      ...fixtures.job,
      attempts: 1,
      status: completed ? "completed" : "running",
      progress: completed ? 100 : 25,
      result: completed
        ? {
            kind: "diagnostic",
            resource_id: null,
            message: "Synthetic diagnostic completed.",
          }
        : null,
    });
    return;
  }
  send({ error: { correlation_id: correlation } }, 404);
});
server.listen(Number(process.env.YAMS_E2E_API_PORT || 3118), "127.0.0.1");
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(
    signal,
    () => server.closeAllConnections() || server.close(() => process.exit(0)),
  );
