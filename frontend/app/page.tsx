import { TransitMap } from "@/components/transit-map/transit-map";

export default function Home() {
  return (
    <main className="w-full overflow-hidden" style={{ height: "100dvh" }}>
      <TransitMap />
    </main>
  );
}
