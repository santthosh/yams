import Link from "next/link";
import { Button } from "../components/ui/button";
export default function NotFound() {
  return (
    <section className="not-found">
      <p className="eyebrow">404 · PAGE NOT FOUND</p>
      <h1>This path is still unexplored.</h1>
      <p>The page does not exist or is not available in this version.</p>
      <Button asChild>
        <Link href="/">Return to Dashboard</Link>
      </Button>
    </section>
  );
}
