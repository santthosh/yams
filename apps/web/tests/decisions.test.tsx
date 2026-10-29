import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DecisionEvidence } from "../src/components/decisions/DecisionEvidence";
import { PaperControls } from "../src/components/decisions/PaperControls";
import { RecommendationReview } from "../src/components/RecommendationReview";
import type { components } from "../src/api/generated/schema";
import fixture from "./decision-transport.json";
import portfolios from "./portfolio-transport.json";
type S = components["schemas"];
const decision = fixture.decision as unknown as S["RecommendationDetailV1"];
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});
it("renders an unavailable scenario as a reason, with no fabricated zero outcome", () => {
  const d = structuredClone(decision);
  d.forecast = {
    ...d.forecast!,
    status: "unavailable",
    unavailable_reason: "INSUFFICIENT_HISTORY",
    proposed: null,
    hold_unchanged: null,
    median_return_delta_fraction: null,
  };
  d.summary_action = "ALLOCATE_TO_CASH";
  d.actions = [];
  d.target_weights = [];
  d.cash_target_weight = "1";
  render(<DecisionEvidence decision={d} />);
  expect(
    screen.getByText(/Forecast unavailable: INSUFFICIENT HISTORY/),
  ).toBeTruthy();
  expect(
    screen.queryByRole("region", { name: "Scenario comparison" }),
  ).toBeNull();
  expect(screen.getByText(/No security actions/)).toBeTruthy();
  expect(screen.getByText(/ALLOCATE TO CASH/)).toBeTruthy();
});
it("retains exact server money and the original uint64 seed in canonical evidence", () => {
  const d = structuredClone(decision);
  d.estimated_total_trade_cost_usd = "9007199254740993.01";
  d.inputs_canonical_json = '{"seed":18446744073709551615}';
  render(<DecisionEvidence decision={d} />);
  expect(screen.getByText("$9,007,199,254,740,993.01")).toBeTruthy();
  expect(screen.getByText('{"seed":18446744073709551615}')).toBeTruthy();
  expect(
    screen.getByRole("region", { name: "Scenario comparison" }),
  ).toBeTruthy();
});
it("invalid saved approval prevents a replacement mutation", async () => {
  localStorage.setItem(
    `yams:approval:v1:${decision.id}`,
    '{"key":"invalid","expected_revision":1}',
  );
  const fetcher = vi.fn(async () => {
    throw new Error("No request should escape invalid storage");
  });
  vi.stubGlobal("fetch", fetcher);
  render(
    <PaperControls
      decision={decision}
      recommendationId={decision.id}
      refresh={() => {}}
      initialBatchId={null}
    />,
  );
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain(
      "saved request is unavailable",
    ),
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Review paper approval",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(fetcher).not.toHaveBeenCalled();
});
it("unreadable saved review cannot be overwritten by a new key", async () => {
  const account = { ...portfolios.cash, id: decision.portfolio_id };
  localStorage.setItem(`yams:review:v1:${account.id}`, "malformed");
  const posts: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.method === "POST") posts.push(request.url);
      if (request.url.includes("/decision-inputs"))
        return Response.json({
          snapshot_id: decision.snapshot_id,
          suggested_session: "2028-07-17",
          clock_at: decision.decision_cutoff_utc,
          unavailable_reason: null,
        });
      if (request.url.includes("/schedule"))
        return Response.json({}, { status: 503 });
      if (request.url.includes("/recommendations"))
        return Response.json({ items: [], next_cursor: null });
      return Response.json(account);
    }),
  );
  render(<RecommendationReview id={account.id} />);
  await waitFor(() =>
    expect(
      screen.getByText(/Saved review request cannot be read/),
    ).toBeTruthy(),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Generate paper review" }),
    ).toBeTruthy(),
  );
  const button = screen.getByRole("button", {
    name: "Generate paper review",
  }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.click(button);
  expect(posts).toEqual([]);
  expect(localStorage.getItem(`yams:review:v1:${account.id}`)).toBe(
    "malformed",
  );
});

it("stale immutable evidence remains visible while fresh approval is disabled", async () => {
  const d = {
    ...structuredClone(decision),
    is_current: false,
    stale_reasons: ["SNAPSHOT_SUPERSEDED"],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        recommendation_id: d.id,
        portfolio_id: d.portfolio_id,
        expected_revision: d.portfolio_revision,
        indicative_eligible_open_at: null,
        unavailable_reason: "SNAPSHOT_SUPERSEDED",
      }),
    ),
  );
  render(
    <PaperControls
      decision={d}
      recommendationId={d.id}
      refresh={() => {}}
      initialBatchId={null}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByText(/Approval unavailable: SNAPSHOT SUPERSEDED/),
    ).toBeTruthy(),
  );
  expect(screen.getByRole("status").textContent).toContain(
    "SNAPSHOT_SUPERSEDED",
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Review paper approval",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
});

it("a no-order server response is inspectable without an empty approval", async () => {
  const d = {
    ...structuredClone(decision),
    summary_action: "HOLD" as const,
    actions: [],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({
        recommendation_id: d.id,
        portfolio_id: d.portfolio_id,
        expected_revision: d.portfolio_revision,
        indicative_eligible_open_at: d.decision_cutoff_utc,
        unavailable_reason: "NO_EXECUTABLE_ORDERS",
      }),
    ),
  );
  render(
    <PaperControls
      decision={d}
      recommendationId={d.id}
      refresh={() => {}}
      initialBatchId={null}
    />,
  );
  await waitFor(() =>
    expect(
      screen.getByText(/Approval unavailable: NO EXECUTABLE ORDERS/),
    ).toBeTruthy(),
  );
  expect(
    (
      screen.getByRole("button", {
        name: "Review paper approval",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
  expect(
    (
      screen.getByRole("button", {
        name: "Dismiss decision",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(false);
});

it("announces a lost approval response inside the open confirmation dialog and retains its key", async () => {
  const requests: { key: string | null; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.url.endsWith("/approval-preview"))
        return Response.json({
          recommendation_id: decision.id,
          portfolio_id: decision.portfolio_id,
          expected_revision: decision.portfolio_revision,
          indicative_eligible_open_at: decision.decision_cutoff_utc,
          unavailable_reason: null,
        });
      if (request.url.endsWith("/apply-result"))
        return Response.json(
          { error: { code: "NOT_FOUND", message: "Unknown key" } },
          { status: 404 },
        );
      requests.push({
        key: request.headers.get("Idempotency-Key"),
        body: await request.json(),
      });
      throw new TypeError("Response lost after server acceptance");
    }),
  );
  render(
    <PaperControls
      decision={decision}
      recommendationId={decision.id}
      refresh={() => {}}
      initialBatchId={null}
    />,
  );
  const trigger = screen.getByRole("button", {
    name: "Review paper approval",
  }) as HTMLButtonElement;
  await waitFor(() => expect(trigger.disabled).toBe(false));
  fireEvent.click(trigger);
  fireEvent.click(
    screen.getByRole("button", { name: "Authorize paper orders" }),
  );
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toContain(
      "Approval outcome unconfirmed",
    ),
  );
  expect(screen.getByRole("dialog").contains(screen.getByRole("alert"))).toBe(
    true,
  );
  const saved = JSON.parse(
    localStorage.getItem(`yams:approval:v1:${decision.id}`)!,
  );
  expect(requests).toEqual([
    { key: saved.key, body: { expected_revision: saved.expected_revision } },
  ]);
  fireEvent.click(
    screen.getByRole("button", {
      name: "Recover or retry original authorization",
    }),
  );
  await waitFor(() => expect(requests.length).toBe(2));
  expect(requests[1]).toEqual(requests[0]);
});

it("refreshes a queued history row from its completed publication without submitting work", async () => {
  const d = structuredClone(decision);
  const account = { ...portfolios.cash, id: d.portfolio_id };
  const posts: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (request.method === "POST") posts.push(request.url);
      const url = new URL(request.url);
      if (url.pathname.endsWith("/decision-inputs"))
        return Response.json({
          snapshot_id: d.snapshot_id,
          suggested_session: d.as_of_session,
          clock_at: d.decision_cutoff_utc,
          unavailable_reason: null,
        });
      if (url.pathname.endsWith("/schedule"))
        return Response.json({}, { status: 503 });
      if (url.pathname.endsWith("/recommendations"))
        return Response.json({
          items: [
            {
              id: d.id,
              portfolio_id: d.portfolio_id,
              job_id: d.job_id,
              inputs: d.inputs,
              status: "queued",
              disposition: null,
              error: null,
            },
          ],
          next_cursor: null,
        });
      if (url.pathname.endsWith("/approval-preview"))
        return Response.json({ unavailable_reason: "NO_EXECUTABLE_ORDERS" });
      if (url.pathname.includes("/jobs/"))
        return Response.json({
          id: d.job_id,
          status: "completed",
          error: null,
        });
      if (url.pathname.endsWith(`/recommendations/${d.id}`))
        return Response.json(d);
      return Response.json(account);
    }),
  );
  render(<RecommendationReview id={account.id} />);
  await waitFor(() =>
    expect(
      screen.getByRole("option", { name: /completed · ready/ }),
    ).toBeTruthy(),
  );
  expect(
    screen.queryByRole("option", { name: /queued · unpublished/ }),
  ).toBeNull();
  expect(posts).toEqual([]);
});
