import { useLocation } from "react-router-dom";

import { getActivityForPathname } from "./activities";

/** Route-derived station activity. Both mascot ambient and cursor shell call
 * this hook, so one deterministic pathname policy drives both surfaces. */
export function useStationActivity() {
  const { pathname } = useLocation();
  return getActivityForPathname(pathname);
}
