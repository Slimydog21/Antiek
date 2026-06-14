import type { Meta, StoryObj } from "@storybook/react";
import type { ReactNode } from "react";

import { SceneStatusBadge } from "./SceneStatusBadge";
import { AuthCtx, type AuthContextValue, type AuthState } from "../lib/auth";

/**
 * SceneStatusBadge.stories — the OPERATOR-ONLY fallback badge, co-located +
 * state-driven (ALC SPR-09, product-character capstone polish — the last
 * un-storied STATEFUL scene component, paired with KreaArtLayer).
 *
 * The badge is the one scene chip with a documented 3-STATE MATRIX driven by
 * AUTH × fallback (SceneStatusBadge.tsx:17-23):
 *   operator + fallback     ⇒ render the badge with the reason text
 *   operator + live         ⇒ render NOTHING (null — no badge when art is live)
 *   NON-operator + fallback ⇒ render NOTHING — ABSENT FROM THE DOM (a logged-out
 *                             reader must never see internal degradation reasons)
 *
 * It reads auth via the OPTIONAL `useContext(AuthCtx)` (the AuthCtx export added
 * in SPR-04, src/lib/auth.tsx) — never the throwing `useAuth` — so it renders
 * safely with or without a provider. These stories drive each matrix cell through
 * the REAL `AuthCtx.Provider` at a real `AuthState` (the same lever the badge's
 * own test uses, SceneStatusBadge.test.tsx:31-40) plus the component's real
 * props. No markup is faked: each state on screen is the state the component's
 * real auth × fallback branch actually reaches.
 *
 * NO NETWORK. The badge consumes only props (isFallback + reason); these stories
 * add no fetch — pure context + props, deterministic, static (the badge has no
 * animation). storyFetch is intentionally NOT used (no fetch is needed).
 *
 * RENDER SHAPE: BLOCK-bodied render arrows only (the SPR-08 build-storybook
 * csf-indexer escape lesson). A relative wrapper anchors the `position:absolute`
 * bottom-left chip so it is visible in the canvas.
 */

// The two auth states the matrix turns on (mirrors the badge's own test).
const OPERATOR: AuthState = {
  status: "authenticated",
  identity: { user_id: "op-1", email: "op@antiek.ai", auth_method: "bearer_token" },
};
const READER_LOGGED_OUT: AuthState = { status: "unauthenticated" };

/** Wrap children in a real AuthCtx provider at a given auth state. */
function withAuth(state: AuthState, children: ReactNode): ReactNode {
  const value: AuthContextValue = {
    state,
    refresh: async () => {},
    signOut: async () => {},
  };
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

const meta = {
  title: "Scene / SceneStatusBadge",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** A dark stage that anchors the absolute bottom-left chip; the caption names the
 *  matrix cell and what should be visible. The badge self-gates from inside. */
const BadgeStage = ({
  label,
  auth,
  isFallback,
  reason,
}: {
  label: string;
  auth: AuthState;
  isFallback: boolean;
  reason: string | null;
}) => {
  return (
    <div className="bg-ink p-6">
      <div className="mb-2 font-mono text-xs uppercase tracking-wider text-starlight">
        SceneStatusBadge · {label}
      </div>
      {/* A relative box so the badge's `position:absolute; left/bottom:12px`
          anchors here; mimics the scene edge the badge actually sits over. */}
      <div className="relative aspect-video w-full overflow-hidden rounded-hog bg-shadow-1 dark:bg-space-2">
        {withAuth(auth, <SceneStatusBadge isFallback={isFallback} reason={reason} />)}
      </div>
    </div>
  );
};

/** operator + fallback ⇒ the badge is PRESENT, naming the reason. The operator's
 *  quiet "the live art is off" glance (e.g. "scene: procedural · no_api_balance"). */
export const OperatorFallbackWithReason: Story = {
  render: () => {
    return (
      <BadgeStage
        label="operator + fallback ⇒ badge with reason"
        auth={OPERATOR}
        isFallback
        reason="no_api_balance"
      />
    );
  },
};

/** operator + live ⇒ the badge renders NULL (no badge when art is live). The
 *  stage is intentionally empty — that absence IS the documented state. */
export const OperatorLiveNull: Story = {
  render: () => {
    return (
      <BadgeStage
        label="operator + live ⇒ no badge (renders null)"
        auth={OPERATOR}
        isFallback={false}
        reason={null}
      />
    );
  },
};

/** NON-operator (logged out) + fallback ⇒ the badge is ABSENT FROM THE DOM (not
 *  CSS-hidden). The reason string never reaches a logged-out reader — the whole
 *  privacy contract. The stage is empty by design. */
export const NonOperatorAbsent: Story = {
  render: () => {
    return (
      <BadgeStage
        label="non-operator + fallback ⇒ absent from the DOM"
        auth={READER_LOGGED_OUT}
        isFallback
        reason="no_api_balance"
      />
    );
  },
};
