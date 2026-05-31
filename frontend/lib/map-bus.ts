// A tiny typed pub/sub so components OUTSIDE the map subtree (e.g. the planner
// chat in app/page.tsx) can drive the map without prop-drilling across the
// next/dynamic boundary. The map subscribes; others emit.

import type { RewardWeights } from "@/lib/planner";
import type { OptStep } from "@/lib/optimizer";

/** Commands the map knows how to execute. */
export type MapCommand =
  | {
      type: "applyPlan";
      weights: RewardWeights;
      goal: string;
    }
  | {
      // The optimizer finished; replay these per-step states as the network
      // builds (stops land one-by-one, and migrate when weights change).
      type: "optimizerResult";
      steps: OptStep[];
    }
  | {
      // Fly the camera to a city event (e.g. clicking an alert card) and
      // highlight it. Carries the venue location + the event id.
      type: "focusEvent";
      eventId: string;
      lng: number;
      lat: number;
    };

type Handler = (cmd: MapCommand) => void;

const handlers = new Set<Handler>();

/** Broadcast a command to every current subscriber. */
export function emitMapCommand(cmd: MapCommand): void {
  for (const h of handlers) h(cmd);
}

/** Subscribe to commands; returns an unsubscribe function. */
export function subscribeMapCommand(handler: Handler): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}
