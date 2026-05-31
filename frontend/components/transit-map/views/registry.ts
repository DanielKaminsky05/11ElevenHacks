// Central registry of all map views.
//
// Each view module lives in its own file and is listed here once. The shell
// (map-view.tsx) iterates this array to set up every view and to render the
// switcher. Adding a view = add a file + one import line here. Agents implement
// their own view file and DO NOT edit this registry (it is already wired).

import type { ViewModule } from "./types";
import { coverageView } from "./coverage";
import { equityGapView } from "./equity-gap";
import { demographicsView } from "./demographics";
import { occupationView } from "./occupation";
import { marginalizationView } from "./marginalization";

/** All overlay views, in switcher order. "Network" (routes/stops) is separate. */
export const VIEWS: ViewModule[] = [
  coverageView,
  equityGapView,
  demographicsView,
  occupationView,
  marginalizationView,
];

/** Look up a view by id. */
export function getView(id: string): ViewModule | undefined {
  return VIEWS.find((v) => v.id === id);
}
