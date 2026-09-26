/**
 * useBranchTo.ts — `navigate` for a branch taken from the document on screen
 * (branchNavigation.ts says what a branch is and why).
 *
 * The reader is in the entry chunk, which has a hard gzip budget (npm run
 * build:check); this hook is the only part of the branch logic it carries.
 * branchNavigation itself loads on the first branch, which is always a
 * user's click on an async hand-off (a research spun, a link followed).
 */
import { useCallback } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useInWindow } from "../components/windows/windowHostContext";
import type { BranchSource } from "./branchNavigation";

/** A surface hosted in a window is not the tab on screen, so from there the
 *  navigation is a plain one. */
export function useBranchTo(): (to: string, origin: BranchSource) => void {
  const navigate = useNavigate();
  const location = useLocation();
  const inWindow = useInWindow();
  return useCallback(
    (to: string, origin: BranchSource) => {
      if (inWindow) {
        navigate(to);
        return;
      }
      void import("./branchNavigation").then(({ branchNavigation }) => {
        const go = branchNavigation(to, location, origin);
        if (go.options) navigate(go.to, go.options);
        else navigate(go.to);
      });
    },
    [navigate, location, inWindow],
  );
}
