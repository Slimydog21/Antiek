import { useEffect, useRef, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton, LemonInput } from "../../components/lemon";
import {
  fetchToolConnections,
  removeToolConnection,
  saveToolConnection,
  type ToolConnection,
  type ToolVendor,
} from "../../api/toolConnections";

function statusLabel(row: ToolConnection): string {
  if (row.quota.kind === "youtube_units" && row.quota.hard_exhausted) {
    return "Quota exhausted";
  }
  if (row.status === "degraded") return "Needs attention";
  if (row.status === "configured_unverified") {
    return row.credential_kind === "contact"
      ? "Contact stored · not yet verified"
      : "Credential stored · not yet verified";
  }
  return "Not configured";
}

function quotaText(row: ToolConnection): string {
  const quota = row.quota;
  if (quota.kind === "youtube_units" && quota.hard_exhausted) {
    return quota.reset_at
      ? `Local quota exhausted · resets ${new Date(quota.reset_at).toLocaleString()}`
      : "Local quota exhausted";
  }
  if (quota.kind === "youtube_units" && quota.remaining != null && quota.limit != null) {
    const reset = quota.reset_at
      ? ` · resets ${new Date(quota.reset_at).toLocaleString()}`
      : "";
    return `${quota.remaining.toLocaleString()} of ${quota.limit.toLocaleString()} local units remain${reset}`;
  }
  return quota.note ?? "Quota unavailable";
}

export default function ToolConnectionsPanel() {
  const [rows, setRows] = useState<ToolConnection[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [action, setAction] = useState<
    { kind: "edit" | "disconnect"; vendor: ToolVendor } | null
  >(null);
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState<ToolVendor | null>(null);
  const [message, setMessage] = useState<{
    vendor: ToolVendor;
    kind: "success" | "error";
    text: string;
  } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const triggerRefs = useRef<Partial<Record<ToolVendor, HTMLButtonElement | null>>>({});
  const disconnectRefs = useRef<Partial<Record<ToolVendor, HTMLButtonElement | null>>>({});
  const cancelDisconnectRef = useRef<HTMLButtonElement>(null);
  const confirmDisconnectRef = useRef<HTMLButtonElement>(null);

  async function refresh() {
    try {
      setRows(await fetchToolConnections());
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Tool connections are unavailable");
      throw error;
    }
  }

  useEffect(() => {
    void refresh().catch(() => undefined);
    return () => setCredential("");
  }, []);

  useEffect(() => {
    if (action?.kind === "edit") inputRef.current?.focus();
    if (action?.kind === "disconnect") cancelDisconnectRef.current?.focus();
  }, [action]);

  function openEditor(vendor: ToolVendor) {
    setCredential("");
    setMessage(null);
    setAction({ kind: "edit", vendor });
  }

  function closeEditor(vendor: ToolVendor, returnFocus = true) {
    setCredential("");
    setAction((current) =>
      current?.kind === "edit" && current.vendor === vendor ? null : current,
    );
    if (returnFocus) queueMicrotask(() => triggerRefs.current[vendor]?.focus());
  }

  function openDisconnect(vendor: ToolVendor) {
    setCredential("");
    setMessage(null);
    setAction({ kind: "disconnect", vendor });
  }

  function closeDisconnect(vendor: ToolVendor) {
    setAction((current) =>
      current?.kind === "disconnect" && current.vendor === vendor ? null : current,
    );
    queueMicrotask(() => disconnectRefs.current[vendor]?.focus());
  }

  async function save(row: ToolConnection) {
    const writeOnlyValue = credential;
    setCredential("");
    setBusy(row.vendor);
    setMessage(null);
    try {
      const updated = await saveToolConnection(row.vendor, writeOnlyValue);
      setRows((current) => current?.map((item) => item.vendor === row.vendor ? updated : item) ?? null);
      setMessage({ vendor: row.vendor, kind: "success", text: `${row.display_name} settings saved. The value will not be shown again.` });
      closeEditor(row.vendor);
    } catch (error) {
      setMessage({ vendor: row.vendor, kind: "error", text: error instanceof Error ? error.message : "Connection could not be saved" });
    } finally {
      setBusy(null);
    }
  }

  async function disconnect(row: ToolConnection) {
    setBusy(row.vendor);
    setMessage(null);
    try {
      await removeToolConnection(row.vendor);
      setRows((current) => current?.map((item) => item.vendor === row.vendor ? {
        ...item,
        credential_present: false,
        status: "unconfigured",
        status_note: null,
        quota: item.quota.kind === "youtube_units" ? {
          ...item.quota,
          remaining: null,
          limit: null,
          reset_at: null,
          hard_exhausted: null,
          note: "Connect a credential to start local quota tracking",
        } : item.quota,
      } : item) ?? null);
      setAction(null);
      queueMicrotask(() => triggerRefs.current[row.vendor]?.focus());
      try {
        await refresh();
        setMessage({ vendor: row.vendor, kind: "success", text: `${row.display_name} disconnected.` });
      } catch {
        setMessage({ vendor: row.vendor, kind: "error", text: `${row.display_name} disconnected, but current tool status could not be refreshed.` });
      }
    } catch (error) {
      setMessage({ vendor: row.vendor, kind: "error", text: error instanceof Error ? error.message : "Connection could not be removed" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <LemonCard title="Tools & data" elevation="z1">
      <div className="p-4 space-y-4">
        <p className="max-w-2xl text-sm font-serif text-ink-soft dark:text-starlight">
          Connect accounts Antiek may use for research. Credentials and SEC contact details are
          encrypted, scoped to your account, and never displayed after saving. Stored does not
          mean the provider has been reached yet.
        </p>

        {loadError && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{loadError}</p>}
        {rows === null && !loadError && <p role="status" className="text-sm text-ink-soft dark:text-starlight">Loading tool connections…</p>}

        {rows && (
          <ul className="ml-2 border-l-2 border-ink/15 pl-5 dark:border-bright/15" aria-label="Tool connections">
            {rows.map((row) => {
              const isEditing = action?.kind === "edit" && action.vendor === row.vendor;
              const isConfirming = action?.kind === "disconnect" && action.vendor === row.vendor;
              const isBusy = busy === row.vendor;
              const actionsLocked = busy !== null;
              const inputId = `tool-credential-${row.vendor}`;
              return (
                <li key={row.vendor} className="relative border-b border-ink/10 py-5 last:border-b-0 dark:border-bright/10">
                  <span
                    aria-hidden="true"
                    className={`absolute -left-[1.72rem] top-7 h-3 w-3 rounded-full border-2 ${row.credential_present ? "border-emerald-700 bg-ice-2 dark:border-emerald-300 dark:bg-space-2" : row.status === "degraded" ? "border-red-700 bg-red-100 dark:border-red-300 dark:bg-red-950" : "border-ink/30 bg-ice-2 dark:border-bright/30 dark:bg-space-2"}`}
                  />
                  <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
                    <div className="min-w-0">
                      <h3 className="font-semibold text-ink dark:text-bright">{row.display_name}</h3>
                      <p className="mt-1 text-sm text-ink-soft dark:text-starlight">
                        <span className="font-medium text-ink dark:text-bright">{statusLabel(row)}</span>
                        <span aria-hidden="true"> · </span>
                        <span className="font-mono text-xs">{row.credential_kind === "contact" ? "SEC contact" : "API key"}</span>
                      </p>
                      <p className="mt-1 text-xs text-ink-soft dark:text-starlight">{quotaText(row)}</p>
                      {row.quota.kind === "youtube_units" && row.quota.remaining != null && row.quota.limit != null && (
                        <meter
                          className="mt-2 h-2 w-full max-w-xs"
                          min={0}
                          max={row.quota.limit}
                          value={row.quota.remaining}
                          aria-label="YouTube local quota remaining"
                        />
                      )}
                      {row.status_note && <p className="mt-1 text-xs text-red-700 dark:text-red-300">{row.status_note}</p>}
                      <a className="mt-2 block w-fit text-xs font-semibold underline underline-offset-4" href={row.docs_url} target="_blank" rel="noreferrer">Provider setup guide</a>
                    </div>
                    <div className="flex flex-wrap gap-2 sm:justify-end">
                      <LemonButton
                        ref={(node) => { triggerRefs.current[row.vendor] = node; }}
                        type="button"
                        variant={row.credential_present ? "secondary" : "primary"}
                        size="lg"
                        disabled={actionsLocked}
                        aria-expanded={isEditing}
                        aria-controls={`${inputId}-form`}
                        onClick={() => isEditing ? closeEditor(row.vendor) : openEditor(row.vendor)}
                        className="w-full sm:h-9 sm:w-auto"
                      >
                        {isEditing ? "Cancel" : row.credential_present ? "Replace" : "Connect"}
                      </LemonButton>
                      {row.credential_present && !isEditing && (
                        <LemonButton
                          ref={(node) => { disconnectRefs.current[row.vendor] = node; }}
                          type="button"
                          variant="tertiary"
                          size="lg"
                          className="w-full sm:h-9 sm:w-auto"
                          disabled={actionsLocked}
                          onClick={() => openDisconnect(row.vendor)}
                        >
                          Disconnect
                        </LemonButton>
                      )}
                    </div>
                  </div>

                  {isEditing && (
                    <form
                      id={`${inputId}-form`}
                      className="mt-4 max-w-xl border-l-2 border-sun pl-4"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void save(row);
                      }}
                    >
                      <label htmlFor={inputId} className="block text-xs font-semibold uppercase tracking-wider text-ink-soft dark:text-starlight">
                        {row.credential_kind === "contact" ? "SEC contact email (write-only)" : "API key (write-only)"}
                      </label>
                      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                        <LemonInput
                          ref={inputRef}
                          id={inputId}
                          type={row.credential_kind === "contact" ? "email" : "password"}
                          autoComplete="new-password"
                          required
                          minLength={row.credential_kind === "contact" ? undefined : 8}
                          maxLength={512}
                          value={credential}
                          onChange={(event) => setCredential(event.target.value)}
                          placeholder={row.credential_kind === "contact" ? "name@example.com" : "Paste key"}
                          wrapperClassName="flex-1"
                        />
                        <LemonButton type="submit" variant="primary" size="lg" className="w-full sm:h-9 sm:w-auto" disabled={isBusy || credential.trim().length === 0}>
                          {isBusy ? "Saving…" : "Save connection"}
                        </LemonButton>
                      </div>
                    </form>
                  )}

                  {isConfirming && (
                    <div
                      role="alertdialog"
                      aria-labelledby={`disconnect-${row.vendor}-title`}
                      aria-describedby={`disconnect-${row.vendor}-description`}
                      onKeyDown={(event) => {
                        if (event.key === "Escape" && !isBusy) closeDisconnect(row.vendor);
                        if (event.key === "Tab") {
                          const first = cancelDisconnectRef.current;
                          const last = confirmDisconnectRef.current;
                          if (event.shiftKey && document.activeElement === first) {
                            event.preventDefault();
                            last?.focus();
                          } else if (!event.shiftKey && document.activeElement === last) {
                            event.preventDefault();
                            first?.focus();
                          }
                        }
                      }}
                      className="mt-4 border border-red-700/40 p-3 dark:border-red-300/40"
                    >
                      <p id={`disconnect-${row.vendor}-title`} className="font-semibold">Disconnect {row.display_name}?</p>
                      <p id={`disconnect-${row.vendor}-description`} className="mt-1 text-sm">Antiek will delete the stored value and stop resolving this tool.</p>
                      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                        <LemonButton ref={cancelDisconnectRef} type="button" variant="tertiary" size="lg" className="w-full sm:h-9 sm:w-auto" disabled={isBusy} onClick={() => closeDisconnect(row.vendor)}>Cancel</LemonButton>
                        <LemonButton ref={confirmDisconnectRef} type="button" variant="danger" size="lg" className="w-full sm:h-9 sm:w-auto" disabled={isBusy} onClick={() => void disconnect(row)}>{isBusy ? "Disconnecting…" : "Disconnect"}</LemonButton>
                      </div>
                    </div>
                  )}
                  {message?.vendor === row.vendor && (
                    <p
                      role={message.kind === "error" ? "alert" : "status"}
                      aria-live={message.kind === "error" ? "assertive" : "polite"}
                      className={`mt-3 ${message.kind === "error" ? "text-sm text-red-700 dark:text-red-300" : "text-sm text-ink-soft dark:text-starlight"}`}
                    >
                      {message.text}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}

      </div>
    </LemonCard>
  );
}
