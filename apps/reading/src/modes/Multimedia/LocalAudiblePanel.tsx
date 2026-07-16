import { useEffect, useRef, useState } from "react";

import {
  getMultimediaLocalAudibleCapability,
  getMultimediaLocalAudiblePlayback,
  inspectMultimediaLocalAudible,
  prepareMultimediaLocalAudible,
  produceMultimediaLocalAudible,
  recoverMultimediaLocalAudible,
} from "../../api/multimedia";
import type {
  MultimediaAssetRecord,
  MultimediaLocalAudiblePlayback,
  MultimediaLocalAudiblePreparedSet,
  MultimediaLocalCapability,
} from "../../api/multimedia";
import { LemonButton } from "../../components/lemon";
import { emitWernerExperience } from "../../werner/reactionBus";
import { ActiveListeningPlayer } from "./ActiveListeningPlayer";

type Pending = "capability" | "prepare" | "produce" | "recover" | "playback" | null;

export function LocalAudiblePanel({
  record,
  onRegistered,
}: {
  record: MultimediaAssetRecord;
  onRegistered: () => void | Promise<void>;
}) {
  const requestVersion = useRef(0);
  const [capability, setCapability] = useState<MultimediaLocalCapability | null>(null);
  const [prepared, setPrepared] = useState<MultimediaLocalAudiblePreparedSet | null>(null);
  const [playback, setPlayback] = useState<MultimediaLocalAudiblePlayback | null>(null);
  const [pending, setPending] = useState<Pending>("capability");
  const [error, setError] = useState<string | null>(null);
  const assetId = record.asset.asset_id;
  const revisionId = record.asset.revision_id;

  useEffect(() => {
    const version = ++requestVersion.current;
    setCapability(null);
    setPrepared(null);
    setPlayback(null);
    setPending("capability");
    setError(null);
    getMultimediaLocalAudibleCapability()
      .then((value) => {
        if (version === requestVersion.current) setCapability(value);
      })
      .catch(() => {
        if (version === requestVersion.current) setError("Local audible status is unavailable.");
      })
      .finally(() => {
        if (version === requestVersion.current) setPending(null);
      });
    return () => {
      requestVersion.current += 1;
    };
  }, [assetId, revisionId]);

  async function command(
    kind: Exclude<Pending, "capability" | "playback" | null>,
    operation: () => Promise<MultimediaLocalAudiblePreparedSet>,
  ) {
    if (pending) return;
    const version = requestVersion.current;
    setPending(kind);
    setError(null);
    try {
      const result = await operation();
      if (version !== requestVersion.current) return;
      setPrepared(result);
      if (result.status === "registered") {
        await onRegistered();
        if (version !== requestVersion.current) return;
        setPending("playback");
        const media = await getMultimediaLocalAudiblePlayback(assetId, revisionId);
        if (version === requestVersion.current) {
          setPlayback(media);
          // Living-TV: local audible ready — happy craft beat.
          emitWernerExperience("piece_started");
        }
      } else if (kind === "prepare") {
        emitWernerExperience("highlight");
      } else if (kind === "recover") {
        emitWernerExperience("note_saved");
      }
    } catch {
      if (version === requestVersion.current) {
        setError("Local audible authority changed. Refresh the current revision.");
        emitWernerExperience("fail");
      }
    } finally {
      if (version === requestVersion.current) setPending(null);
    }
  }

  const recoverable = prepared?.recoverable === true;
  const ready = prepared?.status === "ready_to_produce";

  return (
    <section className="border-t border-rule pt-4 dark:border-charcoal-1" aria-label="Local audible experience">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-mono text-[13px] font-semibold text-ink dark:text-bright">
            Local audible experience
          </h3>
          <p className="mt-1 text-[12px] text-shadow-1 dark:text-moonlight">
            Movement-ready narration with source-linked remember beats and recaps. No paid TTS fallback.
          </p>
        </div>
        <span className="font-mono text-[12px] font-semibold text-ink dark:text-bright">
          $0.00 · Local
        </span>
      </div>

      {pending === "capability" && (
        <p className="mt-3 font-mono text-[11px] text-shadow-2 dark:text-moonlight">Checking local audio...</p>
      )}
      {capability?.available === false && (
        <p className="mt-3 text-[12px] text-emperor">Local audible production is not configured on this server.</p>
      )}
      {error && <p className="mt-3 text-[12px] text-emperor">{error}</p>}

      {capability?.available && !prepared && (
        <LemonButton
          className="mt-3"
          variant="secondary"
          onClick={() => command("prepare", () => prepareMultimediaLocalAudible(assetId, revisionId))}
          disabled={pending !== null}
        >
          {pending === "prepare" ? "Preparing local audio..." : "Prepare audible experience"}
        </LemonButton>
      )}

      {prepared && (
        <>
          <div className="mt-4 border-y border-rule dark:border-charcoal-1">
            {prepared.chapters.map((chapter) => (
              <div
                key={chapter.chapter_id}
                className="grid gap-2 border-b border-rule py-3 last:border-b-0 dark:border-charcoal-1 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center"
              >
                <div className="min-w-0">
                  <h4 className="truncate text-[13px] font-semibold text-ink dark:text-bright">{chapter.title}</h4>
                  <p className="mt-1 font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                    {chapter.ready_span_count}/{chapter.span_count} spans · {formatDuration(chapter.duration_seconds)} · {chapter.source_count} {chapter.source_count === 1 ? "source" : "sources"}
                  </p>
                </div>
                <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                  {chapter.remember_ready && chapter.recap_ready ? "Remember + recap ready" : "Retention pending"}
                </span>
                <span className="font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                  {chapter.learned_claim_count} {chapter.learned_claim_count === 1 ? "learned claim" : "learned claims"}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {recoverable ? (
              <LemonButton
                variant="primary"
                disabled={pending !== null}
                onClick={() => command("recover", () => recoverMultimediaLocalAudible(assetId, revisionId, prepared.set_id))}
              >
                {pending === "recover" ? "Recovering audio..." : "Recover audible experience"}
              </LemonButton>
            ) : prepared.status === "registered" ? (
              <span className="font-mono text-[12px] font-semibold text-ink dark:text-bright">Verified audio ready</span>
            ) : (
              <LemonButton
                variant="primary"
                disabled={!ready || pending !== null}
                onClick={() => command("produce", () => produceMultimediaLocalAudible(assetId, revisionId, prepared.set_id))}
              >
                {pending === "produce" ? "Producing audio..." : "Produce audible experience · $0"}
              </LemonButton>
            )}
            <LemonButton
              size="sm"
              variant="tertiary"
              disabled={pending !== null}
              onClick={() => command("prepare", () => inspectMultimediaLocalAudible(assetId, revisionId, prepared.set_id))}
            >
              Refresh status
            </LemonButton>
            <span className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">
              {formatDuration(prepared.total_duration_seconds)} prepared
            </span>
          </div>

          {pending === "playback" && <p className="mt-3 font-mono text-[11px] text-shadow-2">Verifying audio...</p>}
          {playback && (
            <div className="mt-4 border-t border-rule pt-4 dark:border-charcoal-1">
              <ActiveListeningPlayer playback={playback} title={record.asset.title} />
              <p className="mt-2 font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                {playback.chapter_ids.length} chapters · {playback.retention_marker_count} retention beats · {playback.learned_claim_count} learned claims
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function formatDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  return `${minutes}:${String(rounded % 60).padStart(2, "0")}`;
}

export default LocalAudiblePanel;
