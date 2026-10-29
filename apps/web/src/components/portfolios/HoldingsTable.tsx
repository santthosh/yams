import type { components } from "../../api/generated/schema";
import { EmptyState, Money, Quantity, ReturnPercent } from "../evidence";

type S = components["schemas"];
export function HoldingsTable({
  holdings,
}: {
  holdings: S["PaperPortfolioV1"]["holdings"];
}) {
  if (!holdings.length)
    return (
      <EmptyState title="No posted holdings">
        Your account holds cash until authorized synthetic fills post.
      </EmptyState>
    );
  return (
    <>
      <p className="portfolio-table-hint">
        Scroll the table for marks, values and weights.
      </p>
      <div
        className="table-scroll"
        role="region"
        aria-label="Posted holdings"
        tabIndex={0}
      >
        <table>
          <caption>
            Actual synthetic positions · values supplied by the backend
          </caption>
          <thead>
            <tr>
              <th scope="col">Asset / sector</th>
              <th scope="col">Shares</th>
              <th scope="col">Total basis</th>
              <th scope="col">Mark / session</th>
              <th scope="col">Value</th>
              <th scope="col">Weight</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((row) => (
              <tr key={row.asset_id}>
                <th scope="row">
                  <code>{row.asset_id}</code>
                  <p>{row.sector}</p>
                </th>
                <td>
                  <Quantity value={row.quantity} />
                </td>
                <td>
                  <Money value={row.total_basis_usd} />
                </td>
                <td>
                  <Money value={row.mark_price_usd} />
                  <p>{row.price_as_of_session ?? "No price session"}</p>
                  {row.reason && <p>{row.reason.replaceAll("_", " ")}</p>}
                </td>
                <td>
                  <Money value={row.market_value_usd} />
                </td>
                <td>
                  <ReturnPercent value={row.weight} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
