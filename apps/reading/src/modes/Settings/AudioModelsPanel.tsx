import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type FormEvent, type RefObject } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton, LemonInput } from "../../components/lemon";
import { awaitWorkspaceOwnerSession, isWorkspaceOwnerSession, subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { createAudioModel, deleteAudioModel, disableAudioModel, fetchAudioCatalog, fetchAudioModels, type AudioFailure, type AudioModelDescriptor, type AudioModelRecord, type WriteOnlyAudioCredential } from "../../api/settingsAudioModels";

function subscribe(listener: () => void): () => void { return subscribeWorkspaceOwnerAdmission(listener); }
function normal(owner: WorkspaceOwnerSession): boolean { return owner.subject !== null && /^acct_[a-f0-9]{32}$/.test(owner.subject); }
function failureCopy(result: AudioFailure): string {
  if (result.kind === "unknown") return "The change could not be confirmed. Refresh the saved list before making another change. Do not resubmit the key.";
  if (result.kind === "publication-unconfirmed") return result.credentialCleanupConfirmed
    ? "The model was not confirmed saved. Credential cleanup was confirmed. Refresh the saved list."
    : "The model was not confirmed saved. Credential cleanup is unconfirmed. Refresh the saved list.";
  switch (result.reason) {
    case "auth": return "Your session could not be verified. Sign in again before managing audio models.";
    case "missing": return "This audio model is unavailable. Refresh the saved list.";
    case "validation": return "Check the audio model choice, display name and key. The change was not confirmed.";
    case "protocol": return "The audio model response could not be verified. Refresh the saved list.";
    case "unavailable": return "Audio models are unavailable. Refresh the saved list when the service returns.";
  }
}
interface View {
  catalog: AudioModelDescriptor[] | null;
  models: AudioModelRecord[] | null;
  busy: boolean;
  message: string | null;
  error: boolean;
  uncertain: boolean;
}
interface Ticket {
  controller: AbortController;
  record: AudioModelRecord | null;
  credential: WriteOnlyAudioCredential | null;
}

export default function AudioModelsPanel() {
  const admission = useSyncExternalStore(subscribe, workspaceOwnerAdmission, workspaceOwnerAdmission);
  if (!normal(admission.session) || admission.state === "retiring" || admission.state === "failed") {
    return <LemonCard title="Audio models"><p>Sign in with a verified normal account to manage audio models.</p></LemonCard>;
  }
  return <AudioModelsSession key={admission.session.epoch} owner={admission.session} suspended={admission.state === "suspended"} />;
}
function AudioModelsSession({ owner, suspended }: { owner: WorkspaceOwnerSession; suspended: boolean }) {
  const [view, setView] = useState<View>({ catalog: null, models: null, busy: false, message: null, error: false, uncertain: false });
  const viewRef = useRef(view);
  const [choice, setChoice] = useState("");
  const [displayName, setDisplayName] = useState("");
  const keyRef = useRef<HTMLInputElement>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const alive = useRef(false);
  const pending = useRef<Ticket | null>(null);

  const clearSecret = useCallback(() => { if (keyRef.current) keyRef.current.value = ""; }, []);
  const sameLifetime = useCallback(() => {
    const admission = workspaceOwnerAdmission();
    return alive.current && normal(owner) && admission.session === owner && admission.state !== "retiring" && admission.state !== "failed";
  }, [owner]);
  const current = useCallback((ticket: Ticket) => {
    return sameLifetime() && pending.current === ticket && !ticket.controller.signal.aborted
      && (ticket.record === null || viewRef.current.models?.includes(ticket.record) === true);
  }, [sameLifetime]);
  const confirm = useCallback(async (ticket: Ticket) => {
    return await awaitWorkspaceOwnerSession(owner, ticket.controller.signal) && current(ticket) && isWorkspaceOwnerSession(owner);
  }, [current, owner]);
  const publish = useCallback((ticket: Ticket, next: View) => {
    if (!current(ticket) || !isWorkspaceOwnerSession(owner)) return;
    pending.current = null;
    viewRef.current = next;
    setView(next);
  }, [current, owner]);
  const begin = useCallback((record: AudioModelRecord | null = null): Ticket | null => {
    if (!sameLifetime() || !isWorkspaceOwnerSession(owner) || pending.current
      || (record !== null && !viewRef.current.models?.includes(record))) return null;
    const ticket: Ticket = { controller: new AbortController(), record, credential: null };
    pending.current = ticket;
    const next = { ...viewRef.current, busy: true, message: null };
    viewRef.current = next; setView(next);
    return ticket;
  }, [owner, sameLifetime]);
  const refresh = useCallback(async () => {
    const ticket = begin(); if (!ticket) return;
    if (!await confirm(ticket)) return;
    const catalog = await fetchAudioCatalog(ticket.controller.signal);
    if (!await confirm(ticket)) return;
    if (catalog.kind !== "success") {
      publish(ticket, { ...viewRef.current, busy: false, message: failureCopy(catalog), error: true }); return;
    }
    const models = await fetchAudioModels(ticket.controller.signal);
    if (!await confirm(ticket)) return;
    if (models.kind !== "success") {
      publish(ticket, { ...viewRef.current, catalog: catalog.value, busy: false, message: failureCopy(models), error: true }); return;
    }
    publish(ticket, { catalog: catalog.value, models: models.value, busy: false, message: null, error: false, uncertain: false });
  }, [begin, confirm, publish]);
  useEffect(() => {
    alive.current = true;
    const unsubscribe = subscribeWorkspaceOwnerAdmission((admission) => {
      clearSecret();
      if (admission.session !== owner || admission.state === "retiring" || admission.state === "failed") {
        alive.current = false;
        if (sectionRef.current) sectionRef.current.hidden = true;
        if (pending.current?.credential) pending.current.credential.value = "";
        pending.current?.controller.abort(); pending.current = null;
      }
    });
    return () => {
      alive.current = false; unsubscribe(); clearSecret();
      if (pending.current?.credential) pending.current.credential.value = "";
      pending.current?.controller.abort(); pending.current = null;
    };
  }, [owner, clearSecret]);
  useEffect(() => {
    if (!suspended && viewRef.current.models === null && !pending.current) void refresh();
    // The owner is immutable for this keyed mount; resume must not replace an in-flight ticket.
  }, [refresh, suspended]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const descriptor = viewRef.current.catalog?.find((item) => `${item.catalog_id}:${item.model_id}` === choice);
    if (!descriptor || viewRef.current.uncertain) { clearSecret(); return; }
    const ticket = begin(); if (!ticket) { clearSecret(); return; }
    const credential = { value: keyRef.current?.value ?? "" }; ticket.credential = credential;
    clearSecret();
    const name = displayName;
    if (!await confirm(ticket)) { credential.value = ""; return; }
    const result = await createAudioModel(descriptor, name, credential, ticket.controller.signal);
    credential.value = "";
    if (!await confirm(ticket)) return;
    if (result.kind !== "success") {
      publish(ticket, { ...viewRef.current, busy: false, error: true, message: failureCopy(result), uncertain: result.kind === "unknown" || result.kind === "publication-unconfirmed" }); return;
    }
    if (viewRef.current.models?.some((record) => record.id === result.value.id)) {
      publish(ticket, { ...viewRef.current, busy: false, error: true, uncertain: true, message: failureCopy({ kind: "unknown" }) }); return;
    }
    publish(ticket, { ...viewRef.current, models: [...(viewRef.current.models ?? []), result.value], busy: false, error: false, message: "Audio model saved. Transcription availability is not confirmed." });
  }
  async function mutate(record: AudioModelRecord, operation: "disable" | "delete") {
    if (viewRef.current.uncertain) return;
    const ticket = begin(record); if (!ticket) return;
    if (!await confirm(ticket)) return;
    const result = operation === "disable" ? await disableAudioModel(record.id, ticket.controller.signal) : await deleteAudioModel(record.id, ticket.controller.signal);
    if (!await confirm(ticket)) return;
    if (result.kind !== "success") {
      publish(ticket, { ...viewRef.current, busy: false, error: true, message: failureCopy(result), uncertain: result.kind === "unknown" || result.kind === "publication-unconfirmed" }); return;
    }
    const models = operation === "disable" ? (viewRef.current.models ?? []).map((item) => item === record ? { ...item, enabled: false, registered: false } : item)
      : (viewRef.current.models ?? []).filter((item) => item !== record);
    publish(ticket, { ...viewRef.current, models, busy: false, error: operation === "delete" && !result.value,
      uncertain: operation === "delete" && !result.value,
      message: operation === "disable" ? "Audio model disabled." : result.value ? "Audio model removed; credential removal confirmed." : "Audio model removed from the list. Credential cleanup is unconfirmed. Refresh before another change." });
  }
  return <AudioModelsView view={view} suspended={suspended} choice={choice} displayName={displayName} keyRef={keyRef} sectionRef={sectionRef}
    onChoice={(value) => { if (sameLifetime() && isWorkspaceOwnerSession(owner)) { clearSecret(); setChoice(value); } }}
    onName={(value) => { if (sameLifetime() && isWorkspaceOwnerSession(owner)) setDisplayName(value); }}
    onSubmit={submit} onMutate={mutate} onRefresh={refresh} />;
}
interface AudioModelsViewProps {
  view: View;
  suspended: boolean;
  choice: string;
  displayName: string;
  keyRef: RefObject<HTMLInputElement>;
  sectionRef: RefObject<HTMLDivElement>;
  onChoice: (value: string) => void;
  onName: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => Promise<void>;
  onMutate: (record: AudioModelRecord, operation: "disable" | "delete") => Promise<void>;
  onRefresh: () => Promise<void>;
}
function AudioModelsView({ view, suspended, choice, displayName, keyRef, sectionRef, onChoice, onName, onSubmit, onMutate, onRefresh }: AudioModelsViewProps) {
  const disabled = suspended || view.busy || view.uncertain;
  return <LemonCard title="Audio models">
    <div ref={sectionRef} className="space-y-4">
      <p className="text-sm text-ink-soft dark:text-moonlight">Save an audio-qualified key for transcription. Saving a model does not confirm transcription availability or authorize a paid request.</p>
      {suspended ? <p role="status">Verifying your session. Audio models and drafts are held.</p> : <>
        {view.message && <p role={view.error ? "alert" : "status"}>{view.message}</p>}
        <SavedAudioModels models={view.models} busy={view.busy} disabled={disabled} onMutate={onMutate} />
        <AudioModelForm catalog={view.catalog} loaded={view.models !== null} disabled={disabled} choice={choice} displayName={displayName}
          keyRef={keyRef} onChoice={onChoice} onName={onName} onSubmit={onSubmit} />
      </>}
      <LemonButton disabled={suspended || view.busy} onClick={() => void onRefresh()}>Refresh audio models</LemonButton>
    </div>
  </LemonCard>;
}

function SavedAudioModels({ models, busy, disabled, onMutate }: Pick<AudioModelsViewProps, "onMutate"> & { models: AudioModelRecord[] | null; busy: boolean; disabled: boolean }) {
  return <>        {models === null ? <p role="status">{busy ? "Loading audio models…" : "Saved audio models have not been loaded."}</p>
          : models.length === 0 ? <p>No saved audio models.</p> : <ul className="space-y-3" aria-label="Saved audio models">
            {models.map((record) => <li key={record.id} className="flex flex-wrap items-center gap-3 border-b border-rule pb-3">
              <div className="flex-1"><strong>{record.display_name}</strong><p className="text-sm">Whisper · {record.enabled ? "Saved" : "Disabled"} · {record.registered ? "Registration present" : "Registration unavailable"}</p></div>
              <LemonButton disabled={disabled || !record.enabled} onClick={() => void onMutate(record, "disable")} aria-label={`Disable ${record.display_name}`}>Disable</LemonButton>
              <LemonButton variant="danger" disabled={disabled} onClick={() => void onMutate(record, "delete")} aria-label={`Remove ${record.display_name}`}>Remove</LemonButton>
            </li>)}
          </ul>}
</>;
}
function AudioModelForm({ catalog, loaded, disabled, choice, displayName, keyRef, onChoice, onName, onSubmit }: Pick<AudioModelsViewProps, "choice" | "displayName" | "keyRef" | "onChoice" | "onName" | "onSubmit"> & { catalog: AudioModelDescriptor[] | null; loaded: boolean; disabled: boolean }) {
  return         <form onSubmit={(event) => void onSubmit(event)} aria-label="Add audio model">
          <fieldset disabled={disabled || !loaded || catalog === null} className="space-y-3">
            <div><label htmlFor="audio-model-choice">Audio model</label><select id="audio-model-choice" className="h-11 w-full px-3 border-edge border-sun rounded-hog bg-ice-0 dark:bg-charcoal-2" value={choice} onChange={(event) => onChoice(event.target.value)}>
              <option value="">Choose an audio model</option>{catalog?.map((model) => <option key={`${model.catalog_id}:${model.model_id}`} value={`${model.catalog_id}:${model.model_id}`}>OpenAI · Whisper transcription</option>)}
            </select></div>
            <div><label htmlFor="audio-model-name">Audio display name</label><LemonInput id="audio-model-name" value={displayName} maxLength={64} wrapperClassName="w-full" onChange={(event) => onName(event.target.value)} /></div>
            <div><label htmlFor="audio-model-key">Audio API key</label><LemonInput id="audio-model-key" ref={keyRef} type="password" autoComplete="off" maxLength={512} wrapperClassName="w-full" /><p className="text-xs">Write-only. Cleared when submitted or your session changes.</p></div>
            <LemonButton type="submit" variant="primary" disabled={!choice || displayName.length === 0}>Save audio model</LemonButton>
          </fieldset>
        </form>;
}
