/**
 * Link Monster — the furnace stage.
 *
 * One screen: the p5 furnace visualization (Weirdmageddon sky +
 * Cookie-Monster industrial incinerator + graph constellation) behind
 * a paste-bar that IS the monster's mouth, with the Monster Menu
 * (recent meals) on the right and honest leftover/error states.
 *
 * Route: /link-monster (registered in App.tsx).
 * API:   interfaces/research/api/link_monster_routes.py
 * Art:   docs/specs/link-monster-art-direction.md
 */

import { useCallback, useEffect, useRef, useState } from "react";
import p5 from "p5";

import {
  MonsterError,
  feedMonster,
  getMonsterStats,
  listMonsterFeed,
} from "../../api/linkMonster";
import type {
  LinkDigest,
  MonsterFeedItem,
  MonsterPlatform,
  MonsterStats,
} from "../../api/linkMonster";
import { usePrefersReducedMotion } from "../../workspace/usePrefersReducedMotion";
import { PLATFORM_META, createMonsterSketch } from "./monsterSketch";
import type { MonsterPhase } from "./monsterSketch";
import "./LinkMonster.css";

const URL_RE = /^https?:\/\/[^\s]+$/i;

function phaseLabel(phase: MonsterPhase): string {
  switch (phase) {
    case "feeding":
      return "THE MONSTER IS HUNGRY";
    case "chewing":
      return "IT IS CHEWING THE LINK…";
    case "digesting":
      return "DIGESTING INTO THE GRAPH…";
    case "absorbed":
      return "ABSORBED. THE GRAPH KNOWS.";
    case "leftover":
      return "THE MONSTER COULDN'T SWALLOW THAT ONE";
    default:
      return "FEED IT A LINK";
  }
}

function artifactBadges(d: LinkDigest): string[] {
  const b: string[] = [];
  if (d.artifacts.images > 0) b.push(`🖼 ${d.artifacts.images}`);
  if (d.artifacts.videos > 0) b.push("🎬");
  if (d.artifacts.transcript_chars > 0) b.push("🎙");
  if (d.artifacts.text_chars > 0) b.push(`📝 ${d.artifacts.text_chars}`);
  if (d.outcome === "snack") b.push("🥨 snack");
  return b;
}

export default function LinkMonster() {
  const canvasRef = useRef<HTMLDivElement>(null);
  const p5Ref = useRef<p5 | null>(null);
  const handleRef = useRef<ReturnType<typeof createMonsterSketch>["handle"] | null>(null);

  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<MonsterPhase>("idle");
  const [feed, setFeed] = useState<MonsterFeedItem[]>([]);
  const [stats, setStats] = useState<MonsterStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MonsterFeedItem | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);

  const reducedMotion = usePrefersReducedMotion();

  const refreshFeed = useCallback(async () => {
    try {
      const [items, s] = await Promise.all([listMonsterFeed(20), getMonsterStats()]);
      setFeed(items);
      setStats(s);
    } catch {
      // Feed failing is not fatal to the stage; keep prior state.
    }
  }, []);

  useEffect(() => {
    refreshFeed().then(() => setLoadedOnce(true));
  }, [refreshFeed]);

  useEffect(() => {
    if (!canvasRef.current) return;
    const { sketch, handle } = createMonsterSketch({
      reducedMotion,
      onPhaseChange: setPhase,
    });
    handleRef.current = handle;
    const inst = new p5(sketch, canvasRef.current);
    p5Ref.current = inst;
    return () => {
      inst.remove();
      p5Ref.current = null;
      handleRef.current = null;
    };
  }, [reducedMotion]);

  const submit = useCallback(async () => {
    const trimmed = url.trim();
    if (!URL_RE.test(trimmed)) {
      setError("That is not a link the Monster can eat. Try https://…");
      handleRef.current?.leftover("invalid_url");
      return;
    }
    setBusy(true);
    setError(null);
    handleRef.current?.feed(trimmed);
    try {
      const res = await feedMonster(trimmed);
      handleRef.current?.absorb(res.digest);
      setUrl("");
      await refreshFeed();
    } catch (err) {
      const kind = err instanceof MonsterError ? err.kind : "http";
      const msg = err instanceof MonsterError ? err.message : "the Monster choked";
      setError(msg);
      handleRef.current?.leftover(kind);
    } finally {
      setBusy(false);
    }
  }, [url, refreshFeed]);

  const feedPlatform = (item: MonsterFeedItem): MonsterPlatform => item.digest.platform;

  return (
    <div className="lm-root">
      <div className="lm-stage" ref={canvasRef} aria-hidden="true" />

      <header className="lm-header">
        <h1 className="lm-title">LINK MONSTER</h1>
        <p className="lm-tagline">the front door of the graph · feed it anything</p>
      </header>

      <section className="lm-paste" aria-label="Feed a link to the Monster">
        <label className="lm-paste-label" htmlFor="lm-url">
          {phaseLabel(phase)}
        </label>
        <div className="lm-paste-row">
          <input
            id="lm-url"
            className="lm-input"
            type="url"
            placeholder="https://…"
            value={url}
            disabled={busy}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submit();
            }}
            aria-label="Link to feed"
          />
          <button
            className="lm-feed"
            type="button"
            disabled={busy || !url.trim()}
            onClick={() => void submit()}
          >
            {busy ? "CHEWING…" : "FEED IT"}
          </button>
        </div>
        {error ? (
          <p className="lm-leftover" role="alert">
            ⚠ {error}
          </p>
        ) : (
          <p className="lm-hint">X · YouTube · Instagram · TikTok · Substack · anything</p>
        )}
      </section>

      <aside className="lm-menu" aria-label="Monster menu — recent meals">
        <h2 className="lm-menu-title">
          THE MENU <span className="lm-menu-count">{feed.length}</span>
        </h2>
        <div className="lm-menu-list">
          {!loadedOnce && <p className="lm-empty">summoning the Monster…</p>}
          {loadedOnce && feed.length === 0 && (
            <p className="lm-empty">nothing eaten yet. feed it a link.</p>
          )}
          {feed.map((item) => (
            <button
              key={item.document_id}
              type="button"
              className="lm-card"
              onClick={() => setSelected(item)}
            >
              <span className={`lm-chip lm-chip-${feedPlatform(item)}`}>
                {PLATFORM_META[feedPlatform(item)].glyph} {PLATFORM_META[feedPlatform(item)].label}
              </span>
              <span className="lm-card-title">{item.digest.title ?? item.source_uri}</span>
              {item.digest.author && <span className="lm-card-author">{item.digest.author}</span>}
              <span className="lm-card-badges">{artifactBadges(item.digest).join(" ")}</span>
            </button>
          ))}
        </div>
        {stats && (
          <footer className="lm-stats">
            <span title="meals">{stats.meals} meals</span>
            <span title="snacks">{stats.snacks} snacks</span>
            <span title="chunks stewed">{stats.chunks} chunks</span>
            <span title="graph nodes">{stats.nodes} nodes</span>
            <span title="graph edges">{stats.edges} edges</span>
          </footer>
        )}
      </aside>

      {selected && (
        <div
          className="lm-modal-backdrop"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setSelected(null);
          }}
        >
          <article className="lm-modal" role="dialog" aria-modal="true">
            <header className="lm-modal-head">
              <h2>{selected.digest.title ?? selected.source_uri}</h2>
              <button type="button" className="lm-modal-close" onClick={() => setSelected(null)}>
                ✕
              </button>
            </header>
            <dl className="lm-modal-facts">
              <div>
                <dt>platform</dt>
                <dd>{selected.digest.platform_label}</dd>
              </div>
              {selected.digest.author && (
                <div>
                  <dt>author</dt>
                  <dd>{selected.digest.author}</dd>
                </div>
              )}
              {selected.digest.site_name && (
                <div>
                  <dt>site</dt>
                  <dd>{selected.digest.site_name}</dd>
                </div>
              )}
              {selected.digest.published_at && (
                <div>
                  <dt>published</dt>
                  <dd>{selected.digest.published_at.slice(0, 10)}</dd>
                </div>
              )}
              <div>
                <dt>url</dt>
                <dd className="lm-modal-url">{selected.source_uri}</dd>
              </div>
            </dl>
            {selected.digest.thumbnail_url && (
              <img
                className="lm-modal-thumb"
                src={selected.digest.thumbnail_url}
                alt=""
                referrerPolicy="no-referrer"
              />
            )}
            {selected.digest.description && (
              <p className="lm-modal-desc">{selected.digest.description}</p>
            )}
            <section className="lm-modal-artifacts">
              <h3>what the Monster got out of it</h3>
              <ul>
                {selected.digest.video && (
                  <li>
                    🎬 {selected.digest.video.channel ?? "video"} ·{" "}
                    {selected.digest.video.duration_seconds
                      ? `${Math.round(selected.digest.video.duration_seconds / 60)}m`
                      : "duration unknown"}
                  </li>
                )}
                {selected.digest.transcript && selected.digest.transcript.chars > 0 && (
                  <li>
                    🎙 transcript · {selected.digest.transcript.chars} chars ·{" "}
                    {selected.digest.transcript.caption_kind ?? "unknown"} captions
                  </li>
                )}
                {selected.digest.text && selected.digest.text.word_count > 0 && (
                  <li>
                    📝 {selected.digest.text.word_count} words · source:{" "}
                    {selected.digest.text.source}
                  </li>
                )}
                {selected.digest.image_urls.map((img) => (
                  <li key={img}>🖼 {img}</li>
                ))}
                {artifactBadges(selected.digest).length === 0 && <li>nothing but metadata</li>}
              </ul>
              <h3>provenance</h3>
              <ul className="lm-modal-prov">
                {Object.entries(selected.digest.provenance).map(([k, v]) => (
                  <li key={k}>
                    <code>{k}</code> → {v}
                  </li>
                ))}
              </ul>
            </section>
          </article>
        </div>
      )}
    </div>
  );
}
