import { useCallback, useEffect, useRef, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import {
  createEvidenceManifest,
  getEvidenceManifest,
  listEvidenceManifests,
  launchEvidenceManifest,
} from "../../api/research";
import type {
  DerivedEvidenceCollectionSummary,
  EvidenceManifestDetail,
  EvidenceManifestSummary,
} from "../../api/research";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import AIActionFailure from "../../shared/AIActionFailure";
import { useInvestigation } from "../../hooks/useInvestigation";
import ThinkingStream from "./ThinkingStream";
import { useNavigate } from "react-router-dom";
import { CelebrateBurst, useCelebrate } from "../../shared/delight";

// ── Types ────────────────────────────────────────────────────────────

interface Props {
  /** All owner collection summaries to select from. No excerpts. */
  collections: DerivedEvidenceCollectionSummary[];
  /** Disable controls while parent is busy. */
  disabled: boolean;
  /** Notify parent of pending state. */
  onPendingChange: (pending: boolean) => void;
}

type ManifestView =
  | { kind: "composer" }
  | { kind: "inspecting"; manifest: EvidenceManifestDetail }
  | { kind: "launching"; manifest: EvidenceManifestDetail; question: string };

// ── Helpers ──────────────────────────────────────────────────────────

function collectionIdentity(c: DerivedEvidenceCollectionSummary): string {
  return `${c.label} · ${c.derived_asset_id.slice(0, 8)}… · ${c.member_count} passages`;
}

// ── Component ────────────────────────────────────────────────────────

export default function EvidenceManifestComposer({
  collections,
  disabled,
  onPendingChange,
}: Props) {
  const [view, setView] = useState<ManifestView>({ kind: "composer" });
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [label, setLabel] = useState("");
  const [savedManifests, setSavedManifests] = useState<EvidenceManifestSummary[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  const setBusy = useCallback(
    (value: boolean) => { setPending(value); onPendingChange(value); },
    [onPendingChange],
  );

  // ── Collection selection ─────────────────────────────────────────

  const toggleCollection = useCallback((collectionId: string) => {
    setSelectedIds((prev) =>
      prev.includes(collectionId) ? prev.filter((id) => id !== collectionId) : [...prev, collectionId],
    );
  }, []);

  // ── Save manifest ────────────────────────────────────────────────

  const saveManifest = useCallback(async () => {
    const trimmed = label.trim();
    if (trimmed.length < 1) { setError("Give this manifest a label."); return; }
    if (selectedIds.length < 2 || selectedIds.length > 8) {
      setError("Select 2–8 collections.");
      return;
    }
    const exactGen = ++generation.current;
    setBusy(true); setError(null);
    try {
      const manifest = await createEvidenceManifest({
        label: trimmed,
        collection_ids: selectedIds,
        idempotency_key: `manifest-create-${crypto.randomUUID()}`,
      });
      if (exactGen !== generation.current) return;
      setView({ kind: "inspecting", manifest });
      setSelectedIds([]);
      setLabel("");
    } catch {
      if (exactGen === generation.current) setError("Could not save manifest. Try again.");
    } finally {
      if (exactGen === generation.current) setBusy(false);
    }
  }, [label, selectedIds, setBusy]);

  // ── Load saved manifests ─────────────────────────────────────────

  const loadSaved = useCallback(async () => {
    const exactGen = ++generation.current;
    setBusy(true); setError(null);
    try {
      const list = await listEvidenceManifests();
      if (exactGen !== generation.current) return;
      setSavedManifests(list.manifests);
    } catch {
      if (exactGen === generation.current) setError("Could not load saved manifests.");
    } finally {
      if (exactGen === generation.current) setBusy(false);
    }
  }, [setBusy]);

  // ── Inspect a saved manifest ─────────────────────────────────────

  const inspectManifest = useCallback(async (manifestId: string) => {
    const exactGen = ++generation.current;
    setBusy(true); setError(null);
    try {
      const detail = await getEvidenceManifest(manifestId);
      if (exactGen !== generation.current) return;
      setView({ kind: "inspecting", manifest: detail });
    } catch {
      if (exactGen === generation.current) setError("Could not load manifest detail.");
    } finally {
      if (exactGen === generation.current) setBusy(false);
    }
  }, [setBusy]);

  const frozen = disabled || pending;

  // ── Render: inspecting ───────────────────────────────────────────

  if (view.kind === "inspecting") {
    return (
      <EvidenceManifestInspectView
        manifest={view.manifest}
        frozen={frozen}
        onBack={() => setView({ kind: "composer" })}
        onLaunch={(question) => setView({
          kind: "launching",
          manifest: view.manifest,
          question,
        })}
      />
    );
  }

  // ── Render: launching ────────────────────────────────────────────

  if (view.kind === "launching") {
    return (
      <ManifestLaunchView
        manifest={view.manifest}
        initialQuestion={view.question}
        onBack={() => setView({ kind: "inspecting", manifest: view.manifest })}
      />
    );
  }

  // ── Render: composer ─────────────────────────────────────────────

  return (
    <section
      className="mt-4 border-t border-ink-mute/30 pt-3"
      aria-labelledby="manifest-composer-heading"
    >
      <div className="flex items-center justify-between">
        <h3 id="manifest-composer-heading" className="font-mono text-[11px] font-semibold uppercase">
          Evidence manifests
        </h3>
        <LemonButton
          disabled={frozen}
          onClick={() => void loadSaved()}
        >
          Load saved
        </LemonButton>
      </div>

      {/* Collection checklist */}
      <fieldset disabled={frozen} className="mt-2 space-y-1">
        <legend className="font-mono text-[10px] uppercase mb-1">
          Select 2–8 collections
        </legend>
        {collections.length === 0 ? (
          <p className="text-xs text-ink-soft">No evidence collections saved yet.</p>
        ) : (
          collections.map((c) => (
            <label
              key={c.collection_id}
              className="flex items-start gap-2 text-xs cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(c.collection_id)}
                onChange={() => toggleCollection(c.collection_id)}
                className="mt-0.5"
              />
              <span>{collectionIdentity(c)}</span>
              {selectedIds.includes(c.collection_id) && (
                <span className="font-mono text-[10px] text-ink-soft ml-auto">
                  #{selectedIds.indexOf(c.collection_id) + 1}
                </span>
              )}
            </label>
          ))
        )}
      </fieldset>

      {/* Label + save */}
      {selectedIds.length >= 2 && (
        <div className="mt-3 space-y-2">
          <label className="block font-mono text-[10px]">
            Label
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Cross-asset evidence manifest"
              className="block w-full mt-1 border px-2 py-1 text-sm"
              maxLength={200}
            />
          </label>
          <LemonButton
            variant="primary"
            disabled={frozen || label.trim().length < 1}
            onClick={() => void saveManifest()}
          >
            {pending ? "Saving…" : "Save manifest"}
          </LemonButton>
        </div>
      )}

      {/* Saved manifests list */}
      {savedManifests.length > 0 && (
        <div className="mt-3">
          <h4 className="font-mono text-[10px] uppercase mb-1">Saved manifests</h4>
          <ul className="space-y-1">
            {savedManifests.map((m) => (
              <li key={m.manifest_id} className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  className="underline text-blue"
                  onClick={() => void inspectManifest(m.manifest_id)}
                >
                  {m.label}
                </button>
                <span className="text-ink-soft font-mono text-[10px]">
                  {m.collection_count} collections · {m.total_passage_count} passages
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {pending && <div role="status" className="font-mono text-[10px] mt-2">Working…</div>}
      {error && <div role="alert" className="font-mono text-[10px] text-emperor mt-2">{error}</div>}
    </section>
  );
}

// ── Manifest inspect view ────────────────────────────────────────────

function EvidenceManifestInspectView({
  manifest,
  frozen,
  onBack,
  onLaunch,
}: {
  manifest: EvidenceManifestDetail;
  frozen: boolean;
  onBack: () => void;
  onLaunch: (question: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [showLaunchForm, setShowLaunchForm] = useState(false);

  return (
    <section
      className="mt-4 border-t border-ink-mute/30 pt-3"
      aria-labelledby="manifest-inspect-heading"
    >
      <div className="flex items-center justify-between mb-2">
        <h3 id="manifest-inspect-heading" className="font-mono text-[11px] font-semibold uppercase">
          Manifest: {manifest.label}
        </h3>
        <button type="button" className="text-xs underline" onClick={onBack}>
          ← Back
        </button>
      </div>

      {/* Manifest summary */}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mb-3">
        <dt className="font-mono text-[10px] text-ink-soft">Collections</dt>
        <dd>{manifest.collection_count}</dd>
        <dt className="font-mono text-[10px] text-ink-soft">Total passages</dt>
        <dd>{manifest.total_passage_count}</dd>
        <dt className="font-mono text-[10px] text-ink-soft">Digest</dt>
        <dd className="font-mono text-[10px] truncate" title={manifest.manifest_sha256}>
          {manifest.manifest_sha256.slice(0, 16)}…
        </dd>
        <dt className="font-mono text-[10px] text-ink-soft">Version</dt>
        <dd>{manifest.version}</dd>
      </dl>

      {/* Ordered collection summaries */}
      <h4 className="font-mono text-[10px] uppercase mb-1">Ordered collections</h4>
      <ol className="space-y-2 mb-3">
        {manifest.collections.map((collection, idx) => (
          <li
            key={collection.collection_id}
            className="border border-ink-mute/20 p-2 text-xs"
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px]">{idx + 1}.</span>
              <span className="font-semibold">{collection.label}</span>
            </div>
            <dl className="grid grid-cols-2 gap-x-2 gap-y-0.5 mt-1 text-[10px] text-ink-soft">
              <dt>Asset</dt>
              <dd className="font-mono truncate">{collection.derived_asset_id.slice(0, 12)}…</dd>
              <dt>Passages</dt>
              <dd>{collection.member_count}</dd>
              <dt>Version</dt>
              <dd>{manifest.collection_refs[idx]?.version}</dd>
            </dl>
          </li>
        ))}
      </ol>

      {/* Launch form — second gesture */}
      {!showLaunchForm ? (
        <LemonButton
          variant="primary"
          disabled={frozen}
          onClick={() => setShowLaunchForm(true)}
        >
          Research manifest
        </LemonButton>
      ) : (
        <div className="space-y-2">
          <label className="block font-mono text-[10px]">
            Research question
            <LemonTextarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What do you want to find out?"
              minRows={3}
              maxRows={8}
              disabled={frozen}
              autoFocus
            />
          </label>
          <div className="flex items-center gap-2">
            <LemonButton
              variant="primary"
              disabled={frozen || question.trim().length < 3}
              onClick={() => onLaunch(question)}
            >
              Confirm launch
            </LemonButton>
            <button
              type="button"
              className="text-xs underline"
              onClick={() => setShowLaunchForm(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

// ── Manifest launch view ─────────────────────────────────────────────

function ManifestLaunchView({
  manifest,
  initialQuestion,
  onBack,
}: {
  manifest: EvidenceManifestDetail;
  initialQuestion: string;
  onBack: () => void;
}) {
  const [question] = useState(initialQuestion);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [launchedId, setLaunchedId] = useState<string | null>(null);
  const launchKey = useRef<string | null>(null);
  const launching = useRef(false);
  const launchGen = useRef(0);
  const autoStarted = useRef(false);
  const navigate = useNavigate();
  const { celebrating, celebrate } = useCelebrate();

  const launch = useCallback(async () => {
    if (launching.current) return;
    launching.current = true;
    const gen = ++launchGen.current;
    setBusy(true); setError(null);
    try {
      launchKey.current ??= `manifest-launch-${crypto.randomUUID()}`;
      const resp = await launchEvidenceManifest(
        manifest.manifest_id,
        manifest.etag,
        launchKey.current,
        { question },
      );
      if (gen !== launchGen.current) return;
      setLaunchedId(resp.investigation_id);
      celebrate();
    } catch (e) {
      if (gen === launchGen.current) {
        setError(e instanceof Error ? e.message : "Launch failed. Try again.");
      }
    } finally {
      if (gen === launchGen.current) { launching.current = false; setBusy(false); }
    }
  }, [manifest, question, celebrate]);

  useEffect(() => {
    if (autoStarted.current) return;
    autoStarted.current = true;
    void launch();
  }, [launch]);

  if (launchedId) {
    return (
      <LaunchedManifestThread
        childId={launchedId}
        onOpenInMain={() => navigate(`/inv/${launchedId}`)}
      />
    );
  }

  return (
    <section
      className="mt-4 border-t border-ink-mute/30 pt-3"
      aria-labelledby="manifest-launch-heading"
    >
      <div className="flex items-center justify-between mb-2">
        <h3 id="manifest-launch-heading" className="font-mono text-[11px] font-semibold uppercase">
          Launching manifest: {manifest.label}
        </h3>
        <button type="button" className="text-xs underline" onClick={onBack} disabled={busy}>
          ← Back
        </button>
      </div>

      <blockquote className="text-sm font-serif text-ink-soft italic border-l-edge border-sun pl-3 py-1 mb-3">
        "{question}"
      </blockquote>

      <p className="text-xs text-ink-soft mb-3">
        This will launch a research trajectory built from {manifest.collection_count} verified collections
        ({manifest.total_passage_count} passages). Context is built server-side from verified storage.
      </p>

      {error && (
        <AIActionFailure
          title="Couldn't launch manifest research"
          reason={error}
          onRetry={() => void launch()}
          retryLabel="Try again"
        />
      )}

      <div className="flex items-center justify-end gap-2">
        <CelebrateBurst active={celebrating} size={40} />
        {busy && <span role="status" className="font-mono text-[10px]">Launching…</span>}
      </div>
    </section>
  );
}

/** The launched manifest research's live thinking stream. Reuses the
 *  same ThinkingStream component as ChaseThread — the child IS a
 *  running research. */
function LaunchedManifestThread({
  childId,
  onOpenInMain,
}: {
  childId: string;
  onOpenInMain: () => void;
}) {
  const inv = useInvestigation(childId);
  const getState = useWorkspace.getState;
  return (
    <div className="flex flex-col h-full text-ink dark:text-bright">
      <div className="px-3 py-2 border-b border-rule dark:border-charcoal-1 flex items-center justify-between text-xs font-mono">
        <span className="text-shadow-1 dark:text-moonlight">manifest research running…</span>
        <button
          type="button"
          onClick={() => {
            onOpenInMain();
            const ws = getState();
            const me = Object.values(ws.panels).find(
              (p) => p.kind === "ChaseThread",
            );
            if (me) getState().close(me.id);
          }}
          className="text-ink dark:text-bright hover:underline shrink-0 ml-2"
        >
          open in main view →
        </button>
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">
        <ThinkingStream investigation={inv} />
      </div>
    </div>
  );
}
