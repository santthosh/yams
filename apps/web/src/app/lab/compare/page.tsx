import { ExperimentComparison } from "../../../components/ExperimentComparison";
export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ ids?: string | string[] }>;
}) {
  const query = await searchParams;
  const ids = typeof query.ids === "string" ? query.ids.split(",") : [];
  return <ExperimentComparison key={ids.join(",")} initialIds={ids} />;
}
