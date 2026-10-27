"use client";
import { useEffect, useState, type FormEvent } from "react";
import { createApiClient } from "../api/generated/client";
import { UUID_PATTERN } from "../lib/validation";
import { useWorkspace, correlationFrom } from "./workspace-provider";
import { JobProgress, ErrorState } from "./evidence";
import { Button } from "./ui/button";

export function JobInspector() {
  const { job, setJob } = useWorkspace();
  const [input, setInput] = useState(job?.id ?? "");
  const [request, setRequest] = useState({ id: job?.id ?? "", revision: 0 });
  const [phase, setPhase] = useState<
    "idle" | "loading" | "ready" | "error" | "missing"
  >(job ? "ready" : "idle");
  const [correlation, setCorrelation] = useState<string | undefined>();
  useEffect(() => {
    if (!request.id) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const client = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    async function poll() {
      try {
        const result = await client.GET("/api/v1/jobs/{job_id}", {
          params: { path: { job_id: request.id } },
        });
        if (controller.signal.aborted) return;
        if (!result.data) {
          setJob(null);
          setPhase(result.response.status === 404 ? "missing" : "error");
          setCorrelation(correlationFrom(result.error));
          return;
        }
        setJob(result.data);
        setPhase("ready");
        if (
          ["queued", "running", "cancel_requested"].includes(result.data.status)
        )
          timer = setTimeout(() => void poll(), 2000);
      } catch {
        if (!controller.signal.aborted) {
          setJob(null);
          setPhase("error");
        }
      }
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [request, setJob]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = input.trim();
    if (!UUID_PATTERN.test(id)) return;
    setJob(null);
    setCorrelation(undefined);
    setPhase("loading");
    setRequest((previous) => ({ id, revision: previous.revision + 1 }));
  }
  return (
    <section className="card" id="job-status">
      <h2>Inspect a job</h2>
      <p className="subtle">
        Look up a known job ID. This does not start, cancel or rerun work.
      </p>
      <form onSubmit={submit}>
        <label htmlFor="job-id">Job ID</label>
        <div className="lookup-row">
          <input
            id="job-id"
            name="job-id"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            required
            pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
            maxLength={36}
            placeholder="Paste a job UUID"
            autoComplete="off"
            aria-describedby="job-help"
          />
          <Button type="submit">Check status</Button>
        </div>
        <p id="job-help" className="subtle">
          Use the UUID returned when the job was created.
        </p>
      </form>
      {phase === "idle" && (
        <p>Enter a job ID to view its latest recorded status.</p>
      )}
      {phase === "loading" && <p role="status">Checking job status…</p>}
      {phase === "missing" && (
        <p role="status">
          No job found for this ID. Check the ID and try again.
        </p>
      )}
      {phase === "error" && <ErrorState correlationId={correlation} />}
      {phase === "ready" && job && <JobProgress job={job} />}
    </section>
  );
}
