import { BookOpenText, LoaderCircle, Search, Telescope } from "lucide-react";
import { FormEvent, RefObject, useEffect, useRef, useState } from "react";

import {
  getDerivedCompanionConversation,
  prepareDerivedCompanionEvidence,
  type DerivedAssetReadingResponse,
  type DerivedCompanionCitation,
  type DerivedCompanionAnswer,
  type DerivedCompanionEvidenceResponse,
  type DerivedCompanionExecutionProjection,
  type DerivedEvidenceBriefing,
} from "../../api/research";
import { LemonButton, LemonTag } from "../../components/lemon";

interface Props {
  model: DerivedAssetReadingResponse;
  articleRef: RefObject<HTMLElement>;
  onFollowCitation: (citation: DerivedCompanionCitation) => void;
}

type PersistedTurn = Awaited<ReturnType<typeof getDerivedCompanionConversation>>["turns"][number];

function GroundedAnswer({
  answer, citations, showCitation, onFollowCitation,
}: {
  answer: DerivedCompanionAnswer;
  citations: DerivedCompanionCitation[];
  showCitation: (anchor: string) => void;
  onFollowCitation: (citation: DerivedCompanionCitation) => void;
}) {
  const byId = new Map(citations.map((citation) => [citation.citation_id, citation]));
  return <section className="mb-4 border-b border-rule pb-3 dark:border-charcoal-1" aria-label="Grounded companion answer">
    <div className="mb-2 flex items-center justify-between gap-2">
      <p className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">{answer.provider} · {answer.model}</p>
      {answer.unsupported_claim_count > 0 ? <LemonTag colour="sun">{answer.unsupported_claim_count} unsupported</LemonTag> : <LemonTag colour="aurora">Grounded</LemonTag>}
    </div>
    <ol className="space-y-2">{answer.claims.map((claim) => <li key={claim.claim_id}>
      <p className="font-serif text-sm leading-relaxed text-ink dark:text-bright">{claim.text}</p>
      {claim.supported ? <div className="mt-1 flex flex-wrap gap-2">{claim.citation_ids.map((citationId, index) => {
        const citation = byId.get(citationId);
        return citation ? <span key={citationId} className="inline-flex items-center gap-2">
          <button type="button" onClick={() => showCitation(citation.section_anchor)} className="font-mono text-[10px] text-link underline">[{index + 1}] {citation.section_path || "Cited section"}</button>
          <button type="button" aria-label={`Follow citation ${index + 1}`} onClick={() => onFollowCitation(citation)} className="text-link"><Telescope size={12} /></button>
        </span> : null;
      })}</div> : <p className="mt-1 font-mono text-[10px] text-warning">Unsupported by this evidence pack</p>}
    </li>)}</ol>
  </section>;
}

export function EvidenceBriefing({
  briefing, showCitation, onFollowCitation,
}: {
  briefing: DerivedEvidenceBriefing;
  showCitation: (anchor: string) => void;
  onFollowCitation: (citation: DerivedCompanionCitation) => void;
}) {
  return <section aria-label="Evidence briefing">
    <div className="mb-3 flex items-baseline justify-between gap-2 border-b border-rule pb-2 dark:border-charcoal-1">
      <h3 className="font-serif text-sm font-semibold text-ink dark:text-bright">Evidence briefing</h3>
      <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">{briefing.section_count} sections · {briefing.passage_count} passages</span>
    </div>
    <div className="space-y-4">{briefing.sections.map((section, sectionIndex) => <section key={`${section.section_path}:${sectionIndex}`}>
      <h4 className="mb-2 font-mono text-[10px] font-semibold uppercase text-shadow-1 dark:text-moonlight">{section.section_path || "Untitled section"}</h4>
      <ol className="space-y-3">{section.passages.map((citation) => <li key={citation.citation_id} className="border-b border-rule pb-3 dark:border-charcoal-1">
        <blockquote className="font-serif text-sm leading-relaxed text-ink dark:text-bright">{citation.text}</blockquote>
        <div className="mt-1 flex items-center justify-between gap-2">
          <button type="button" onClick={() => showCitation(citation.section_anchor)} className="text-left font-mono text-[10px] text-link underline">Open section</button>
          <button type="button" onClick={() => onFollowCitation(citation)} className="inline-flex shrink-0 items-center gap-1 font-mono text-[10px] text-link underline"><Telescope size={12} /> Follow this</button>
        </div>
      </li>)}</ol>
    </section>)}</div>
  </section>;
}

function executionLabel(execution: DerivedCompanionExecutionProjection | null): string {
  if (!execution) return "Checking route evidence";
  if (execution.reason === "qualification_registry_invalid") return "Route evidence unavailable";
  if (execution.reason === "executable_route_not_registered") {
    return `${execution.routes.length} routes checked · execution not registered`;
  }
  return `${execution.routes.length} routes checked · none qualified`;
}

function clientTurnId(): string {
  return `reader-${crypto.randomUUID()}`;
}

export default function DerivedRevisionCompanion({
  model, articleRef, onFollowCitation,
}: Props) {
  const activeClientId = useRef<string | null>(null);
  const requestGeneration = useRef(0);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<DerivedCompanionEvidenceResponse | null>(null);
  const [turns, setTurns] = useState<PersistedTurn[]>([]);
  const [execution, setExecution] = useState<DerivedCompanionExecutionProjection | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const generation = ++requestGeneration.current;
    activeClientId.current = null;
    setWorking(false);
    setResult(null);
    setError(null);
    setTurns([]);
    setExecution(null);
    void getDerivedCompanionConversation(model).then((conversation) => {
      if (generation !== requestGeneration.current) return;
      if (conversation.scope.revision_id !== model.revision_id
          || conversation.scope.content_sha256 !== model.content_sha256) return;
      setTurns(conversation.turns);
      setExecution(conversation.execution);
    }).catch(() => {
      if (generation === requestGeneration.current) {
        setError("Saved companion evidence could not be loaded.");
      }
    });
    return () => { requestGeneration.current += 1; };
  }, [model]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = question.trim();
    if (!normalized || working) return;
    const generation = ++requestGeneration.current;
    activeClientId.current ??= clientTurnId();
    setWorking(true);
    setError(null);
    try {
      const next = await prepareDerivedCompanionEvidence(
        model, activeClientId.current, normalized,
      );
      if (generation !== requestGeneration.current) return;
      if (next.scope.derived_asset_id !== model.derived_asset_id
          || next.scope.revision_id !== model.revision_id
          || next.scope.content_sha256 !== model.content_sha256) {
        throw new Error("companion identity conflict");
      }
      setResult(next);
      setExecution(next.execution);
      setTurns((current) => [...current.filter(
        (turn) => turn.client_turn_id !== next.client_turn_id,
      ), {
        client_turn_id: next.client_turn_id,
        question: normalized,
        state: next.state,
        failure_code: next.failure_code,
        evidence_pack: next.evidence_pack,
        briefing: next.briefing,
        answer: next.answer,
      }]);
      activeClientId.current = null;
    } catch {
      if (generation === requestGeneration.current) {
        setError("The evidence request could not be verified. Retry keeps the same request identity.");
      }
    } finally {
      if (generation === requestGeneration.current) setWorking(false);
    }
  }

  function showCitation(anchor: string) {
    const escaped = CSS.escape(anchor);
    const target = articleRef.current?.querySelector<HTMLElement>(`#${escaped}`);
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.animate(
      [{ outline: "3px solid #f9bd2b" }, { outline: "3px solid transparent" }],
      { duration: 1800, easing: "ease-out" },
    );
  }

  return <aside className="hidden w-80 flex-shrink-0 overflow-y-auto border-l border-rule bg-ice-1 dark:border-charcoal-1 dark:bg-charcoal-2 lg:flex lg:flex-col" aria-label="Derived revision companion">
    <header className="border-b border-rule px-4 pb-3 pt-4 dark:border-charcoal-1">
      <div className="flex items-center justify-between gap-2">
        <p className="font-serif text-sm text-ink dark:text-bright">Question this revision</p>
        <LemonTag colour={model.is_current ? "aurora" : "sun"}>{model.is_current ? "Current" : "Historical"}</LemonTag>
      </div>
      <p className="mt-1 font-mono text-[10px] text-shadow-1 dark:text-moonlight">Generation {model.generation} · exact citations</p>
    </header>
    <form className="border-b border-rule p-4 dark:border-charcoal-1" onSubmit={submit}>
      <label htmlFor="derived-companion-question" className="sr-only">Question about this revision</label>
      <textarea id="derived-companion-question" value={question} disabled={working} onChange={(event) => {
        setQuestion(event.target.value);
        activeClientId.current = null;
        setResult(null);
      }} rows={4} maxLength={8000} placeholder="What does this revision say about..." className="w-full resize-y border border-rule bg-white p-2 font-serif text-sm text-ink outline-none focus:border-ink dark:border-charcoal-1 dark:bg-charcoal-3 dark:text-bright" />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="font-mono text-[10px] text-shadow-1 dark:text-moonlight">
          {executionLabel(execution)}
        </span>
        <LemonButton type="submit" size="sm" disabled={working || question.trim().length === 0}>
          {working ? <LoaderCircle className="animate-spin" size={14} /> : <Search size={14} />} Find evidence
        </LemonButton>
      </div>
    </form>
    {error ? <p role="alert" className="border-b border-rule px-4 py-3 text-xs text-danger dark:border-charcoal-1">{error}</p> : null}
    <div className="min-h-0 flex-1 p-4">
      {!result && turns.length === 0 ? <div className="flex gap-2 text-sm text-ink-mute dark:text-moonlight"><BookOpenText className="mt-0.5 shrink-0" size={16} /><p className="font-serif leading-relaxed">Antiek will retrieve passages from the exact revision on screen. Model execution remains unavailable until a route has verified idempotency, pricing, and spend recovery.</p></div> : null}
      {result?.state === "insufficient_evidence" ? <p className="font-serif text-sm leading-relaxed text-ink-mute dark:text-moonlight">No matching evidence was found in this revision. No model was called.</p> : null}
      {result?.answer ? <GroundedAnswer answer={result.answer} citations={result.evidence_pack.citations} showCitation={showCitation} onFollowCitation={onFollowCitation} /> : null}
      {result?.briefing ? <EvidenceBriefing briefing={result.briefing} showCitation={showCitation} onFollowCitation={onFollowCitation} /> : null}
      {!result && turns.length > 0 ? <ol className="space-y-4" aria-label="Saved revision evidence">{turns.map((turn) => <li key={turn.client_turn_id}>
        <p className="mb-2 font-serif text-sm font-semibold text-ink dark:text-bright">{turn.question}</p>
        {turn.answer ? <GroundedAnswer answer={turn.answer} citations={turn.evidence_pack.citations} showCitation={showCitation} onFollowCitation={onFollowCitation} /> : null}
        {turn.state === "insufficient_evidence" ? <p className="font-serif text-sm text-ink-mute dark:text-moonlight">No matching evidence was found. No model was called.</p> : turn.briefing ? <EvidenceBriefing briefing={turn.briefing} showCitation={showCitation} onFollowCitation={onFollowCitation} /> : null}
      </li>)}</ol> : null}
    </div>
  </aside>;
}
