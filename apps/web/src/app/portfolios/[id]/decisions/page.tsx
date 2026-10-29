import { RecommendationReview } from "../../../../components/RecommendationReview";
export default async function DecisionsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <RecommendationReview key={id} id={id} />;
}
