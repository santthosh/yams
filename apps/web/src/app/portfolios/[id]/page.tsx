import { PortfolioDetail } from "../../../components/portfolios/PortfolioDetail";
export default async function PortfolioPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <PortfolioDetail key={id} id={id} />;
}
