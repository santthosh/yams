import type { components } from "../../api/generated/schema";
import { Quantity } from "../evidence";

type Batch = components["schemas"]["PaperOrderBatchV1"];
/** Server quantities and states; authorization is never presented as a fill. */
export function OrderBatchState({ batch }: { batch: Batch | null }) {
  if (!batch)
    return (
      <div className="notice" role="note">
        <strong>No batch selected</strong>
        <p>
          Inspect an existing approval or explicitly authorize a current
          decision. An approval event alone is not a fill.
        </p>
      </div>
    );
  return (
    <section aria-label="Paper order batch" className="portfolio-batch">
      <h3>
        {batch.terminal ? "Closed paper batch" : "Approved · execution pending"}
      </h3>
      <p>
        {batch.status.replaceAll("_", " ")} ·{" "}
        {batch.terminal ? "No remaining intent" : "Not all orders have posted"}
      </p>
      <p>
        Original approval: {batch.approved_at} · Eligible opening:{" "}
        {batch.eligible_open_at}
      </p>
      {batch.reason && <p>{batch.reason.replaceAll("_", " ")}</p>}
      <p className="portfolio-table-hint">
        Scroll the table to inspect all order quantities.
      </p>
      <div
        className="table-scroll"
        role="region"
        aria-label="Approved order quantities"
        tabIndex={0}
      >
        <table>
          <caption>Requested, posted and remaining synthetic shares</caption>
          <thead>
            <tr>
              <th scope="col">Asset</th>
              <th scope="col">Side</th>
              <th scope="col">Requested</th>
              <th scope="col">Filled</th>
              <th scope="col">Pending</th>
              <th scope="col">Closed shortfall</th>
              <th scope="col">State</th>
            </tr>
          </thead>
          <tbody>
            {batch.orders.map((row) => (
              <tr key={row.id}>
                <th scope="row">{row.asset_id}</th>
                <td>{row.side}</td>
                <td>
                  <Quantity value={row.requested_quantity} />
                </td>
                <td>
                  <Quantity value={row.filled_quantity} />
                </td>
                <td>
                  <Quantity value={row.pending_quantity} />
                </td>
                <td>
                  <Quantity value={row.cancelled_or_skipped_quantity} />
                </td>
                <td>
                  {row.status.replaceAll("_", " ")} ·{" "}
                  {row.terminal ? "closed" : "waiting"}
                  {row.reason && <p>{row.reason.replaceAll("_", " ")}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
