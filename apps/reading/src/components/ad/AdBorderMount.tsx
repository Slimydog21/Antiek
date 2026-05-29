// The single shell-level mount of the always-on ad border (SPR-07 M2).
//
// AppShell renders this ONCE. It derives the two inputs the border needs from
// the router — there is no per-lens fork, no per-route mount:
//
//   * lens — the active product workflow, from the pathname via the existing
//     workflowTaxonomy source of truth (workflowForPath). The `shared`
//     operator/governance bucket is not one of the four monetizable lenses, so
//     it maps to "research" (the default surface "/" already resolves to);
//     the border is still always on there, the telemetry is just stamped with
//     the default lens. The contract only admits the four VALID_LENSES.
//   * windowId — a stable id for the CURRENT lens session. It changes when the
//     lens changes, so each lens session is one WindowFrameBatch (second_index
//     restarts at 0 inside the new window). A fresh random suffix per lens
//     entry keeps two visits to the same lens from colliding in the trace.
//
// Splitting this off AppShell keeps AppShell's render free of ad-border state
// and lets the border be unit-tested without the whole shell (the shell test
// mocks this to null, exactly as it mocks the other heavy children).

import { useMemo, useRef } from "react";
import { useLocation } from "react-router-dom";

import { workflowForPath } from "../../shell/workflowTaxonomy";
import { AdBorder } from "./AdBorder";
import type { Lens } from "./frameContract";

/** Map a workflow to a telemetry lens. The four product workflows ARE the four
 *  lenses; the `shared` bucket (settings, operator, billing …) has no lens of
 *  its own and is stamped "research", the default surface. */
function lensForPath(pathname: string): Lens {
  const wf = workflowForPath(pathname);
  return wf === "shared" ? "research" : wf;
}

export function AdBorderMount() {
  const { pathname } = useLocation();
  const lens = lensForPath(pathname);

  // A new window each time the lens changes. The random suffix is allocated
  // once per lens value (useMemo keyed on lens) so re-renders within a lens
  // session keep the same window_id — the batch's trace anchor is stable for
  // the life of the session and only rolls over on a real lens switch.
  const sessionRef = useRef(Math.random().toString(36).slice(2, 10));
  const windowId = useMemo(
    () => `win:${lens}:${sessionRef.current}:${Math.random().toString(36).slice(2, 8)}`,
    [lens],
  );

  return <AdBorder lens={lens} windowId={windowId} />;
}

export default AdBorderMount;
