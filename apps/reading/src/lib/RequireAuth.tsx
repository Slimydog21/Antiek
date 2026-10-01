import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth";

/** Auth gate. Children render only when authenticated; otherwise we
 * redirect to /login with the original path preserved in ?next= so the
 * post-callback redirect lands the user where they tried to go. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { state, protectedIdentity } = useAuth();
  const location = useLocation();
  if (state.status === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-ice-2 dark:bg-space-2 text-shadow-1 dark:text-moonlight text-xs tracking-[0.18em] uppercase font-sans">
        Loading…
      </div>
    );
  }
  if (state.status === "unauthenticated" && !(state.inferred && protectedIdentity)) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  if (state.status === "unavailable" && !protectedIdentity) return null;
  return <>{children}</>;
}
