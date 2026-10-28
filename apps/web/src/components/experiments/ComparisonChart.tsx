"use client";
import { useEffect, useRef, useState } from "react";
import type { Data } from "plotly.js";
import type { Point, Run } from "./comparison";
export default function ComparisonChart({
  runs,
  points,
}: {
  runs: Run[];
  points: Record<string, Point[]>;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    void (async () => {
      try {
        const plotly = (await import("plotly.js-basic-dist-min")).default;
        if (disposed) return;
        const line = (
          name: string,
          rows: Point[],
          values: (string | null)[],
          dash: "solid" | "dash" | "dot" = "solid",
        ): Data => ({
          name,
          x: rows.map((row) => row.session_date),
          y: values,
          type: "scatter",
          mode: "lines+markers",
          connectgaps: false,
          line: { dash },
        });
        const baseline = points[runs[0].id] ?? [];
        const data = runs.map((run) => {
          const rows = points[run.id] ?? [];
          return line(
            `${run.strategy_config.display_name} · ${run.id.slice(0, 8)}`,
            rows,
            rows.map((row) => row.portfolio_nav_usd),
          );
        });
        data.push(
          line(
            "SPY proxy",
            baseline,
            baseline.map((row) => row.benchmark_nav_usd),
            "dash",
          ),
        );
        data.push(
          line(
            "Zero-yield cash",
            baseline,
            baseline.map((row) => row.cash_baseline_nav_usd),
            "dot",
          ),
        );
        cleanup = () => plotly.purge(element);
        await plotly.react(
          element,
          data,
          {
            autosize: true,
            height: 400,
            margin: { t: 20, r: 20, l: 65, b: 105 },
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#33443d", family: "Arial, sans-serif" },
            xaxis: {
              type: "date",
              title: { text: "Pinned trading session" },
              automargin: true,
            },
            yaxis: {
              type: "linear",
              title: { text: "USD" },
              tickformat: ",.2f",
              automargin: true,
            },
            legend: { orientation: "h", y: -0.3 },
            hovermode: "x unified",
          },
          {
            responsive: true,
            displaylogo: false,
            displayModeBar: false,
            scrollZoom: false,
          },
        );
      } catch {
        if (!disposed) setError(true);
      }
    })();
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [runs, points]);
  return (
    <figure className="experiment-figure">
      <figcaption>
        Comparable portfolio NAV, SPY proxy and zero-yield cash (USD)
      </figcaption>
      {error ? (
        <p role="status">
          Chart unavailable. Exact session tables remain below.
        </p>
      ) : (
        <div className="comparison-chart" ref={host} aria-hidden="true" />
      )}
    </figure>
  );
}
