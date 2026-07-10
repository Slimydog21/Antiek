import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { sendTwinsToWrite, type TwinNote } from "../../api/engagement";

export type SendTwinsToWriteProps = {
  assetId: string;
  sessionId: string;
  spawnId: string;
  investigationId: string;
  notes: TwinNote[];
};

export function SendTwinsToWrite(props: SendTwinsToWriteProps) {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const available = useMemo(() => new Set(props.notes.map((note) => note.note_id)), [props.notes]);
  const selectedNotes = selected.filter((id) => available.has(id));

  function toggle(noteId: string) {
    setSelected((current) => current.includes(noteId)
      ? current.filter((id) => id !== noteId)
      : [...current, noteId]);
  }

  async function send() {
    if (!title.trim() || selectedNotes.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await sendTwinsToWrite({
        asset_id: props.assetId,
        session_id: props.sessionId,
        spawn_id: props.spawnId,
        investigation_id: props.investigationId,
        title: title.trim(),
        note_ids: selectedNotes,
      });
      navigate(`/write/${encodeURIComponent(result.deliverable_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return <section aria-label="Send selected twin notes to Write" data-testid="send-twins-to-write">
    <h3>Send selected notes to Write</h3>
    <fieldset disabled={busy}>
      <legend>Select notes</legend>
      {props.notes.map((note) => <label key={note.note_id} className="block">
        <input type="checkbox" checked={selectedNotes.includes(note.note_id)}
          onChange={() => toggle(note.note_id)} />
        <span><strong>{note.kind === "insight" ? "Insight" : "Question"}:</strong> {note.text}</span>
      </label>)}
    </fieldset>
    <label className="block">
      Deliverable title
      <input data-testid="write-title" value={title} disabled={busy}
        onChange={(event) => setTitle(event.target.value)} />
    </label>
    <button type="button" data-testid="send-to-write" disabled={busy || !title.trim() || selectedNotes.length === 0}
      onClick={() => void send()}>
      {busy ? "Sending…" : "Send to Write"}
    </button>
    {error ? <p role="alert" className="error">{error}</p> : null}
  </section>;
}

export default SendTwinsToWrite;
