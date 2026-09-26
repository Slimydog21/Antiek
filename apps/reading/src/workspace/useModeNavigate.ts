/**
 * useModeNavigate.ts — in-app navigation that keeps the operator's mode.
 *
 * A research spun from a reader lives at /inv/<id>?m=reading (its tab
 * stays in the reading tree). A surface inside it that opens another route
 * (a chased child, a new research, the notebook) must keep `?m`, or the
 * screen changes mode under the operator. These hooks route every such
 * navigation through the one helper, mothershipForPath.inMode.
 *
 *   useModeNavigate()  `navigate`, with the target kept in the current mode;
 *   useModePath()      the target for a <Link to> / <NavLink to>.
 */
import { useCallback } from "react";
import { useLocation, useNavigate, type NavigateOptions } from "react-router-dom";

import { inMode } from "./mothershipForPath";

export function useModePath(): (to: string) => string {
  const { pathname, search } = useLocation();
  return useCallback((to: string) => inMode(to, search, pathname), [pathname, search]);
}

export function useModeNavigate(): (to: string, options?: NavigateOptions) => void {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  return useCallback(
    (to: string, options?: NavigateOptions) => {
      const target = inMode(to, search, pathname);
      if (options) navigate(target, options);
      else navigate(target);
    },
    [navigate, pathname, search],
  );
}
