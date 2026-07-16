import { BrassBalanceCursor } from "../BrassBalanceCursor";
import { registerActivity } from "./registry";
import type { StationActivity } from "./types";

/** Cost-planning activity: the pointer becomes a brass weighing scale on the
 *  exact /pricing route. Werner remains at his station; no ambient class. */
export const brassBalanceActivity: StationActivity = {
  id: "brass-balance",
  label: "Brass balance",
  ambient: {
    activeClass: null,
    idleClass: null,
  },
  instrument: {
    render: BrassBalanceCursor,
    reads: ["live", "pointerIdle", "tabHidden"],
  },
  unlock: { kind: "route", policyId: "cost-planning" },
};

registerActivity(brassBalanceActivity);
