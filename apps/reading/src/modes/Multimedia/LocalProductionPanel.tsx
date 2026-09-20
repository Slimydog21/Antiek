import { useEffect, useRef, useState } from "react";

import {
  attestMultimediaLocalCard,
  getMultimediaLocalCapability,
  inspectMultimediaLocal,
  multimediaLocalCardPreviewUrl,
  prepareMultimediaLocal,
  produceMultimediaLocal,
  recoverMultimediaLocal,
} from "../../api/multimedia";
import type {
  MultimediaAssetRecord,
  MultimediaLocalCapability,
  MultimediaLocalPreparedSet,
} from "../../api/multimedia";
import { LemonButton } from "../../components/lemon";

type Pending = "capability" | "prepare" | "attest" | "produce" | "recover" | null;

export function LocalProductionPanel({
  record,
  onRegistered,
}: {
  record: MultimediaAssetRecord;
  onRegistered: () => void | Promise<void>;
}) {
  const requestVersion = useRef(0);
  const [capability, setCapability] = useState<MultimediaLocalCapability | null>(null);
  const [prepared, setPrepared] = useState<MultimediaLocalPreparedSet | null>(null);
  const [pending, setPending] = useState<Pending>("capability");
  const [error, setError] = useState<string | null>(null);
  const assetId = record.asset.asset_id;
  const revisionId = record.asset.revision_id;

  useEffect(() => {
    const version = ++requestVersion.current;
    setCapability(null);
    setPrepared(null);
    setPending("capability");
    setError(null);
    getMultimediaLocalCapability()
      .then((value) => {
        if (version === requestVersion.current) setCapability(value);
      })
      .catch(() => {
        if (version === requestVersion.current) setError("Local production status is unavailable.");
      })
      .finally(() => {
        if (version === requestVersion.current) setPending(null);
      });
    return () => {
      requestVersion.current += 1;
    };
  }, [assetId, revisionId]);

  async function command(
    kind: Exclude<Pending, "capability" | null>,
    operation: () => Promise<MultimediaLocalPreparedSet>,
  ) {
    if (pending) return;
    const version = requestVersion.current;
    setPending(kind);
    setError(null);
    try {
      const result = await operation();
      if (version !== requestVersion.current) return;
      setPrepared(result);
      if (result.status === "registered") await onRegistered();
    } catch {
      if (version === requestVersion.current) {
        setError("Local production authority changed. Refresh the current revision.");
      }
    } finally {
      if (version === requestVersion.current) setPending(null);
    }
  }

  async function refresh() {
    if (!prepared || pending) return;
    await command("prepare", () => inspectMultimediaLocal(assetId, revisionId, prepared.set_id));
  }

  const unavailable = capability?.available === false;
  const recoverable = prepared?.recoverable === true;
  const ready = prepared?.status === "ready_to_produce";

  return (
    <section className="border-t border-rule pt-4 dark:border-charcoal-1" aria-label="Local production">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-mono text-[13px] font-semibold text-ink dark:text-bright">
            Local documentary
          </h3>
          <p className="mt-1 text-[12px] text-shadow-1 dark:text-moonlight">
            Fully local narration and source cards. No Krea or paid-provider fallback.
          </p>
        </div>
        <span className="font-mono text-[12px] font-semibold text-ink dark:text-bright">
          $0.00 · Local
        </span>
      </div>

      {pending === "capability" && (
        <p className="mt-3 font-mono text-[11px] text-shadow-2 dark:text-moonlight">Checking local capability...</p>
      )}
      {unavailable && (
        <p className="mt-3 text-[12px] text-emperor">Local production is not configured on this server.</p>
      )}
      {error && <p className="mt-3 text-[12px] text-emperor">{error}</p>}

      {capability?.available && !prepared && (
        <LemonButton
          className="mt-3"
          variant="secondary"
          onClick={() => command("prepare", () => prepareMultimediaLocal(assetId, revisionId))}
          disabled={pending !== null}
        >
          {pending === "prepare" ? "Preparing locally..." : "Prepare local chapters"}
        </LemonButton>
      )}

      {prepared && (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {prepared.chapters.map((chapter) => (
              <article key={chapter.chapter_id} className="border border-rule p-3 dark:border-charcoal-1">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h4 className="truncate text-[13px] font-semibold text-ink dark:text-bright">
                      {chapter.title}
                    </h4>
                    <p className="mt-1 font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                      {chapter.source_count} {chapter.source_count === 1 ? "source" : "sources"}
                    </p>
                  </div>
                  <span className="shrink-0 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
                    {chapter.attested ? "Reviewed" : chapter.card_ready ? "Review required" : "Preparing"}
                  </span>
                </div>
                {chapter.card_id && chapter.card_ready && (
                  <img
                    className="mt-3 aspect-video w-full border border-rule object-cover dark:border-charcoal-1"
                    src={multimediaLocalCardPreviewUrl(assetId, revisionId, prepared.set_id, chapter.card_id)}
                    alt={`Source card for ${chapter.title}`}
                  />
                )}
                <div className="mt-3 flex items-center justify-between gap-3">
                  <span className="font-mono text-[11px] text-shadow-2 dark:text-moonlight">
                    Narration {chapter.narration_ready ? "ready" : "pending"}
                  </span>
                  {chapter.card_id && chapter.card_ready && !chapter.attested && (
                    <LemonButton
                      size="sm"
                      variant="secondary"
                      disabled={pending !== null}
                      onClick={() => command(
                        "attest",
                        () => attestMultimediaLocalCard(
                          assetId, revisionId, prepared.set_id, chapter.card_id!,
                        ),
                      )}
                    >
                      {pending === "attest" ? "Reviewing..." : "Attest source card"}
                    </LemonButton>
                  )}
                </div>
              </article>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {recoverable ? (
              <LemonButton
                variant="primary"
                disabled={pending !== null}
                onClick={() => command(
                  "recover",
                  () => recoverMultimediaLocal(assetId, revisionId, prepared.set_id),
                )}
              >
                {pending === "recover" ? "Recovering..." : "Recover local production"}
              </LemonButton>
            ) : prepared.status === "registered" ? (
              <span className="font-mono text-[12px] font-semibold text-ink dark:text-bright">
                Verified playback ready
              </span>
            ) : (
              <LemonButton
                variant="primary"
                disabled={!ready || pending !== null}
                onClick={() => command(
                  "produce",
                  () => produceMultimediaLocal(assetId, revisionId, prepared.set_id),
                )}
              >
                {pending === "produce" ? "Producing locally..." : "Produce locally · $0"}
              </LemonButton>
            )}
            <LemonButton size="sm" variant="tertiary" disabled={pending !== null} onClick={refresh}>
              Refresh status
            </LemonButton>
          </div>
        </>
      )}
    </section>
  );
}

export default LocalProductionPanel;
