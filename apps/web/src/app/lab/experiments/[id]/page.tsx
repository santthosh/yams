import { ExperimentReport } from "../../../../components/experiments/ExperimentReport";
export default async function ExperimentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ExperimentReport key={id} id={id} />;
}
