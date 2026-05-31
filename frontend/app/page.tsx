import { TransitMap } from "@/components/transit-map/transit-map";
import { PlannerChat } from "@/components/planner-chat/planner-chat";

export default function Home() {
  return (
    <main className="relative w-full overflow-hidden" style={{ height: "100dvh" }}>
      <TransitMap />
      <PlannerChat />
    </main>
  );
}
