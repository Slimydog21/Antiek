import { useState } from "react";

import {
  inviteStatusLabel,
  type InviteStatus,
} from "../../lib/speakVocab";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Speak SPR-03 M2 — the invitation surface.
 *
 * The operator creates a project and invites a subject's friends and
 * family by link. This panel lists each invitee's lifecycle status,
 * exposes the copyable invite link, and offers an invite form.
 *
 * Presentational by design: invitees are SOURCES, not accounts (the
 * line that keeps v1 inside the single-operator constraint; the public
 * open-contribution ecosystem is gated on G7). The component is driven
 * by props so it renders in Storybook without a backend; the host wires
 * `onInvite` to `substrate.speak.invitations.invite_stakeholder`.
 */
export type { InviteStatus };

export type InviteRow = {
  interviewId: string;
  email: string | null;
  handle: string | null;
  status: InviteStatus;
  link: string;
  requiredScopes: ("record" | "attribute" | "publish")[];
};

type Props = {
  projectTitle: string;
  publishIntent: "private_never_published" | "will_be_public";
  invites: InviteRow[];
  onInvite?: (email: string) => void | Promise<void>;
};

/** Plain words for the consent scopes a friend is asked for. `record` is what
 *  taking part requires; `attribute`/`publish` are optional choices the friend
 *  makes — so the operator reads "Sharing a memory" + which optionals are asked
 *  for, not raw scope tokens. */
const SCOPE_LABELS: Record<InviteRow["requiredScopes"][number], string> = {
  record: "Sharing a memory",
  attribute: "their name shown",
  publish: "public sharing",
};

function describeScopes(scopes: InviteRow["requiredScopes"]): string {
  const required = scopes.includes("record") ? SCOPE_LABELS.record : null;
  const optional = scopes
    .filter((s) => s !== "record")
    .map((s) => SCOPE_LABELS[s]);
  const parts: string[] = [];
  if (required) parts.push(required);
  if (optional.length > 0) parts.push(`optional: ${optional.join(", ")}`);
  // Always show the required floor even if scopes somehow arrived empty.
  return parts.length > 0 ? parts.join(" · ") : SCOPE_LABELS.record;
}

const STATUS_STYLE: Record<InviteStatus, string> = {
  invited: "text-ink-mute dark:text-moonlight",
  in_progress: "text-sun-deep dark:text-sun",
  completed: "text-aurora",
  declined: "text-emperor",
  incomplete: "text-ink-mute dark:text-moonlight italic",
};

export default function Invites({
  projectTitle,
  publishIntent,
  invites,
  onInvite,
}: Props) {
  const [email, setEmail] = useState("");

  const submit = async () => {
    const trimmed = email.trim();
    if (!trimmed || !onInvite) return;
    try {
      await onInvite(trimmed);
      setEmail("");
      // Living-TV: stakeholder invite sent — noted beat.
      emitWernerExperience("note_saved");
    } catch {
      emitWernerExperience("fail");
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 bg-ice-0 dark:bg-charcoal-2">
      <header className="mb-3">
        <h2 className="text-sm font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          {projectTitle} · invitations
        </h2>
        <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight mt-1">
          {publishIntent === "will_be_public"
            ? "will-be-public — invites capture publish-scope consent"
            : "private — invites capture record consent"}
          {" · "}
          {invites.length} invitee{invites.length === 1 ? "" : "s"}
        </p>
      </header>

      <div className="flex gap-2 mb-4">
        <input
          type="email"
          value={email}
          placeholder="friend@example.com"
          onChange={(e) => setEmail(e.target.value)}
          className="flex-1 font-mono text-[12px] px-2 py-1 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!onInvite}
          className="font-mono text-[11px] px-3 py-1 border border-ink rounded text-sun-deep dark:text-sun hover:underline disabled:opacity-40"
        >
          send invite
        </button>
      </div>

      {invites.length === 0 ? (
        <p className="text-[12px] italic text-ink-mute dark:text-moonlight font-serif">
          No invitees yet — send the first link above.
        </p>
      ) : (
        <ul className="space-y-2">
          {invites.map((iv) => (
            <li
              key={iv.interviewId}
              className="border border-ink-mute/40 rounded p-2 flex flex-col gap-1"
            >
              <div className="flex items-center justify-between">
                <span className="font-serif text-[14px] text-ink dark:text-bright">
                  {iv.email ?? iv.handle ?? iv.interviewId}
                </span>
                <span
                  className={
                    "font-mono text-[10px] uppercase tracking-wider " +
                    STATUS_STYLE[iv.status]
                  }
                >
                  {inviteStatusLabel(iv.status)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <code className="text-[10px] text-ink-mute dark:text-moonlight truncate">
                  {iv.link}
                </code>
                <button
                  type="button"
                  onClick={() => void navigator.clipboard?.writeText(iv.link)}
                  className="font-mono text-[10px] text-sun-deep dark:text-sun hover:underline shrink-0"
                >
                  copy
                </button>
              </div>
              <span className="font-mono text-[9px] text-ink-mute dark:text-moonlight">
                consent: {describeScopes(iv.requiredScopes)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
