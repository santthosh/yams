"use client";

import { useEffect, useRef, useState } from "react";
import type { Data, Layout } from "plotly.js";
import type { components } from "../../api/generated/schema";

type Point = components["schemas"]["ExperimentCurvePointV1"];
function Chart({
  points,
  kind,
}: {
  points: Point[];
  kind: "equity" | "drawdown" | "exposure";
}) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const title =
    kind === "equity"
      ? "Portfolio, SPY and cash (USD)"
      : kind === "drawdown"
        ? "Drawdown from the previous high"
        : "Cash and largest position exposure";
  useEffect(() => {
    const element = host.current;
    if (!element || !points.length) return;
    let disposed = false;
    let purge: (() => void) | undefined;
    void (async () => {
      try {
        const plotly = (await import("plotly.js-basic-dist-min")).default;
        if (disposed) return;
        const x = points.map((row) => row.session_date);
        const line = (
          name: string,
          y: (string | number | null)[],
          color: string,
          dash: "solid" | "dash" | "dot" = "solid",
        ): Data => ({
          x,
          y,
          name,
          type: "scatter",
          mode: "lines+markers",
          connectgaps: false,
          line: { color, dash },
          marker: { size: 4 },
        });
        const data: Data[] =
          kind === "equity"
            ? [
                line(
                  "Portfolio",
                  points.map((row) => row.portfolio_nav_usd),
                  "#1b6958",
                ),
                line(
                  "SPY proxy",
                  points.map((row) => row.benchmark_nav_usd),
                  "#705ba5",
                  "dash",
                ),
                line(
                  "Zero-yield cash",
                  points.map((row) => row.cash_baseline_nav_usd),
                  "#8a651f",
                  "dot",
                ),
              ]
            : kind === "drawdown"
              ? [
                  line(
                    "Drawdown",
                    points.map((row) => row.drawdown_fraction.value),
                    "#705ba5",
                  ),
                ]
              : [
                  line(
                    "Cash weight",
                    points.map((row) => row.cash_weight.value),
                    "#1b6958",
                  ),
                  line(
                    "Largest position",
                    points.map((row) => row.max_position_weight.value),
                    "#705ba5",
                    "dash",
                  ),
                ];
        const layout: Partial<Layout> = {
          autosize: true,
          height: 340,
          margin: { t: 20, r: 20, b: 85, l: 65 },
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { family: "Arial, sans-serif", color: "#33443d" },
          xaxis: {
            title: { text: "Pinned trading session" },
            type: "date",
            automargin: true,
          },
          yaxis: {
            type: "linear",
            title: { text: kind === "equity" ? "USD" : "Fraction" },
            tickformat: kind === "equity" ? ",.2f" : ".1%",
            automargin: true,
          },
          legend: { orientation: "h", y: -0.3 },
          hovermode: "x unified",
        };
        purge = () => plotly.purge(element);
        await plotly.react(element, data, layout, {
          responsive: true,
          displaylogo: false,
          displayModeBar: false,
          scrollZoom: false,
        });
      } catch {
        if (!disposed) setError(true);
      }
    })();
    return () => {
      disposed = true;
      purge?.();
    };
  }, [points, kind]);
  return (
    <figure className="experiment-figure">
      <figcaption>{title}</figcaption>
      {error ? (
        <p role="status">
          Chart unavailable. The exact series table remains available below.
        </p>
      ) : (
        <div ref={host} aria-hidden="true" className="experiment-chart" />
      )}
      <p className="muted">
        Exact values and unavailable reasons are in the series table. Charts
        show the loaded session window.
      </p>
    </figure>
  );
}
export default function ExperimentCharts({ points }: { points: Point[] }) {
  return (
    <div className="experiment-charts">
      <Chart points={points} kind="equity" />
      <Chart points={points} kind="drawdown" />
      <Chart points={points} kind="exposure" />
    </div>
  );
}
