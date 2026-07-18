import { useEffect, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton, LemonInput, LemonSelect } from "../../components/lemon";
import {
  addUserModel,
  fetchUserModels,
  removeUserModel,
  type ProviderKind,
  type UserModelRow,
} from "../../api/settingsModels";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * AddModelPanel — user-added model providers (BYOK).
 *
 * The API key is WRITE-ONLY: it lives in a password input, is cleared the
 * moment the form submits, and never comes back from the server (inventory
 * rows carry only a key_present flag). Stored encrypted at rest via the
 * house byok SecretBox mechanism (see settings_models_admin.py).
 */

const KIND_OPTIONS = [
  { value: "openai_compat" as ProviderKind, label: "OpenAI-compatible" },
  { value: "anthropic" as ProviderKind, label: "Anthropic" },
];

export default function AddModelPanel() {
  const [models, setModels] = useState<UserModelRow[] | null>(null);
  const [staleRegistered, setStaleRegistered] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [kind, setKind] = useState<ProviderKind>("openai_compat");
  const [displayName, setDisplayName] = useState("");
  const [modelId, setModelId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    try {
      const res = await fetchUserModels();
      setModels(res.models);
      setStaleRegistered(res.stale_registered ?? []);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  const needsBaseUrl = kind === "openai_compat";
  const canSubmit =
    !busy &&
    displayName.trim().length > 0 &&
    modelId.length > 0 &&
    apiKey.length > 0 &&
    (!needsBaseUrl || baseUrl.length > 0);

  async function onAdd() {
    setBusy(true);
    setMessage(null);
    // Write-only key: captured once, cleared from the field immediately —
    // whatever the server answers, the key never sits in the form again.
    const key = apiKey;
    setApiKey("");
    try {
      await addUserModel({
        provider_kind: kind,
        model_id: modelId,
        display_name: displayName.trim(),
        api_key: key,
        ...(needsBaseUrl && baseUrl ? { base_url: baseUrl } : {}),
      });
      setDisplayName("");
      setModelId("");
      setBaseUrl("");
      setMessage("Model added. Its key is stored encrypted and will not be shown again.");
      // Living-TV: BYOK model add is a noted bookkeeping beat.
      emitWernerExperience("note_saved");
      await refresh();
    } catch (e) {
      emitWernerExperience("fail");
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(row: UserModelRow) {
    if (!window.confirm(`Remove “${row.display_name}”? Its stored key becomes unusable.`)) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await removeUserModel(row.id);
      setMessage("Model removed.");
      emitWernerExperience("note_saved");
      await refresh();
    } catch (e) {
      emitWernerExperience("fail");
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <LemonCard title="Add model (BYOK)" elevation="z1">
      <div className="p-4 space-y-4">
        <p className="text-xs text-ink-soft dark:text-starlight">
          Bring your own provider key. It is encrypted at rest and never
          displayed again — the inventory only shows whether a key is stored.
        </p>

        {loadError && (
          <p className="text-sm text-red-700 dark:text-red-300 font-mono">{loadError}</p>
        )}
        {models === null && !loadError && (
          <p className="text-sm text-ink-soft dark:text-starlight">Loading your models…</p>
        )}
        {models && models.length === 0 && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            No user-added models yet.
          </p>
        )}
        {staleRegistered.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300 font-mono">
            Stale registrations (registry record lost):{" "}
            {staleRegistered.join(", ")} — they cannot resolve keys and clear
            at the next restart.
          </p>
        )}
        {models && models.length > 0 && (
          <ul className="space-y-2">
            {models.map((m) => (
              <li
                key={m.id}
                className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/10 dark:border-bright/10 pb-2 font-mono text-[13px]"
              >
                <span className="text-ink dark:text-bright font-semibold">
                  {m.display_name}
                  <span className="font-normal text-ink-soft dark:text-starlight">
                    {" "}
                    · {m.provider_kind} · {m.model_id}
                  </span>
                </span>
                <span className="flex items-center gap-3">
                  <span
                    className={
                      m.key_present
                        ? "text-emerald-700 dark:text-emerald-300"
                        : "text-amber-700 dark:text-amber-300"
                    }
                  >
                    {m.key_present ? "key stored" : "no key"}
                  </span>
                  <span
                    className={
                      m.registered
                        ? "text-emerald-700 dark:text-emerald-300"
                        : "text-amber-700 dark:text-amber-300"
                    }
                  >
                    {m.registered ? "registered" : "not registered"}
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void onRemove(m)}
                    className="text-xs font-semibold text-emperor underline underline-offset-4 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="space-y-3">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
              Provider kind
            </span>
            <LemonSelect<ProviderKind>
              value={kind}
              onChange={(nextKind) => {
                setKind(nextKind);
                // Anthropic uses its trusted default endpoint in this UI.
                // Clear the now-hidden custom endpoint so a stale OpenAI URL
                // can never receive the newly entered Anthropic credential.
                if (nextKind === "anthropic") setBaseUrl("");
              }}
              options={KIND_OPTIONS}
              aria-label="Provider kind"
              fullWidth
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
              Display name
            </span>
            <LemonInput
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="My DeepSeek"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
              Model id
            </span>
            <LemonInput
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="deepseek-chat"
            />
          </label>
          {needsBaseUrl && (
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Base URL (full, including version prefix)
              </span>
              <LemonInput
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.deepseek.com/v1"
                inputMode="url"
              />
            </label>
          )}
          <label className="flex flex-col gap-1">
            <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
              API key (write-only)
            </span>
            <LemonInput
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-…"
            />
          </label>
          <LemonButton
            type="button"
            variant="secondary"
            size="md"
            disabled={!canSubmit}
            onClick={() => void onAdd()}
          >
            {busy ? "Adding…" : "Add model"}
          </LemonButton>
        </div>

        {message && (
          <p className="text-xs text-ink-soft dark:text-starlight" role="status">
            {message}
          </p>
        )}
      </div>
    </LemonCard>
  );
}
