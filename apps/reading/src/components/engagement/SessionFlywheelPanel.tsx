/**
 * SessionFlywheelPanel — complete floating deep-research session flywheel.
 *
 * Residual (cl): records output + optional twins/promote into research context
 * and feeds Antiek-bench usage events (server-side best-effort).
 * Residual (ee): onCompleted notifies parent so research context remounts
 * after twins/usage land.
 * Composes shipped completeSessionFlywheel. HTML-first context pack.
 */

import { useCallback, useState } from "react";
import {
  completeSessionFlywheel,
  type SessionFlywheelResponse,
} from "../../api/engagement";

export type SessionFlywheelPanelProps = {
  sessionId: string;
  /** Seed output from selection / goal when operator has not edited. */
  defaultOutputText?: string;
  /** Residual (ee): after successful flywheel complete. */
  onCompleted?: (result: SessionFlywheelResponse) => void;
};

export function SessionFlywheelPanel({
  sessionId,
  defaultOutputText = "",
  onCompleted,
}: SessionFlywheelPanelProps) {
  const [output, setOutput] = useState(defaultOutputText);
  const [recordTwins, setRecordTwins] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SessionFlywheelResponse | null>(null);

  const complete = useCallback(async () => {
    const sid = sessionId.trim();
    const text = output.trim();
    if (!sid) {
      setError("sessionId is required");
      return;
    }
    if (text.length < 3) {
      setError("Output text must be at least 3 characters");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await completeSessionFlywheel({
        session_id: sid,
        output_text: text,
        record_twins: recordTwins,
        include_twin_promote: recordTwins,
      });
      if (out.view_format !== "html") {
        throw new Error("flywheel view_format must be html");
      }
      setResult(out);
      onCompleted?.(out);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [sessionId, output, recordTwins, onCompleted]);

  return (
    <section
      className="space-y-2"
      data-testid="session-flywheel-panel"
      data-view-format="html"
      aria-label="Complete research flywheel"
    >
      <header>
        <h2 className="text-sm font-medium text-ink dark:text-parchment">
          Complete session flywheel
        </h2>
        <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
          Land output → twins/context pack → usage events for Antiek-bench
        </p>
      </header>
      <textarea
        data-testid="session-flywheel-output"
        value={output}
        onChange={(e) => setOutput(e.target.value)}
        disabled={busy}
        rows={3}
        placeholder="Synthesis / findings to record for this session…"
        className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[12px] font-mono dark:border-bright/20"
      />
      <label className="flex items-center gap-2 text-[11px] font-mono">
        <input
          type="checkbox"
          data-testid="session-flywheel-record-twins"
          checked={recordTwins}
          onChange={(e) => setRecordTwins(e.target.checked)}
          disabled={busy}
        />
        Record twin notes + promote to context
      </label>
      <button
        type="button"
        data-testid="session-flywheel-complete"
        disabled={busy || output.trim().length < 3}
        onClick={() => void complete()}
        className="rounded border border-ink/30 px-2 py-1 text-[12px] font-mono hover:bg-ink/5 disabled:opacity-50 dark:border-bright/30"
      >
        {busy ? "Completing…" : "Complete flywheel"}
      </button>
      {error ? (
        <p className="text-[11px] font-mono text-emperor" role="alert">
          {error}
        </p>
      ) : null}
      {result ? (
        <div
          className="space-y-1 rounded border border-ink/10 p-2 text-[11px] font-mono dark:border-bright/10"
          data-testid="session-flywheel-result"
          data-view-format="html"
        >
          <p>
            status=<code>{result.status}</code> · session=
            <code>{result.session_id}</code> · spawn=
            <code>{result.spawn_id}</code>
          </p>
          {result.prompt_block ? (
            <pre
              className="max-h-32 overflow-auto whitespace-pre-wrap"
              data-testid="session-flywheel-prompt-block"
            >
              {result.prompt_block}
            </pre>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default SessionFlywheelPanel;
