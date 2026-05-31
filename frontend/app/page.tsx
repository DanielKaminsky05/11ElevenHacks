import { TransitMap } from "@/components/transit-map/transit-map";
import { PlannerChat } from "@/components/planner-chat/planner-chat";
import { OptimizerPanel } from "@/components/optimizer-panel/optimizer-panel";
import { NewsFeed } from "@/components/news-feed/news-feed";

export default function Home() {
  return (
    <main className="relative w-full overflow-hidden" style={{ height: "100dvh" }}>
      <TransitMap />
      <NewsFeed />
      <OptimizerPanel />
      <PlannerChat />
    </main>
  );
}
