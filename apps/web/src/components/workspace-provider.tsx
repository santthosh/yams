"use client";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { createApiClient } from "../api/generated/client";
import type { components } from "../api/generated/schema";
import { UUID_PATTERN } from "../lib/validation";

type Schema = components["schemas"];
type State = {
  phase: "loading" | "ready" | "error";
  health: Schema["HealthV1"] | null;
  workspace: Schema["WorkspaceV1"] | null;
  correlationId?: string;
};
const initial: State = { phase: "loading", health: null, workspace: null };
const Context = createContext<
  | (State & {
      refresh: () => void;
      job: Schema["JobV1"] | null;
      setJob: (job: Schema["JobV1"] | null) => void;
    })
  | null
>(null);
export function correlationFrom(value: unknown): string | undefined {
  if (typeof value !== "object" || value === null || !("error" in value))
    return undefined;
  const error = value.error;
  if (
    typeof error !== "object" ||
    error === null ||
    !("correlation_id" in error) ||
    typeof error.correlation_id !== "string"
  )
    return undefined;
  return UUID_PATTERN.test(error.correlation_id)
    ? error.correlation_id
    : undefined;
}
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>(initial);
  const [epoch, setEpoch] = useState(0);
  const [job, setJob] = useState<Schema["JobV1"] | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const client = createApiClient(window.location.origin, (input, init) =>
      fetch(input, { ...init, signal: controller.signal }),
    );
    async function load() {
      try {
        const [healthResult, workspaceResult] = await Promise.all([
          client.GET("/api/v1/health"),
          client.GET("/api/v1/workspace"),
        ]);
        if (controller.signal.aborted) return;
        const candidate = healthResult.data ?? healthResult.error;
        const health =
          candidate &&
          "status" in candidate &&
          ["ready", "not_ready"].includes(candidate.status) &&
          candidate.database &&
          candidate.fixtures &&
          candidate.migration &&
          candidate.workspace
            ? candidate
            : null;
        setState({
          phase:
            health && (health.status === "not_ready" || workspaceResult.data)
              ? "ready"
              : "error",
          health,
          workspace: workspaceResult.data ?? null,
          correlationId:
            correlationFrom(healthResult.error) ??
            correlationFrom(workspaceResult.error),
        });
      } catch {
        if (!controller.signal.aborted)
          setState({ ...initial, phase: "error" });
      }
    }
    void load();
    return () => controller.abort();
  }, [epoch]);
  return (
    <Context.Provider
      value={{
        ...state,
        job,
        setJob,
        refresh: () => {
          setState(initial);
          setEpoch((value) => value + 1);
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useWorkspace() {
  const context = useContext(Context);
  if (!context) throw new Error("Workspace context unavailable");
  return context;
}
