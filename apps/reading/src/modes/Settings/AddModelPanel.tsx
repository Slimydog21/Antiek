import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton, LemonInput } from "../../components/lemon";
import {
  addUserModel,
  fetchSettingsModelCatalog,
  fetchUserModels,
  removeUserModel,
  type ProviderKind,
  type SettingsModelCatalogProvider,
  type UserModelRow,
} from "../../api/settingsModels";
import { fetchSettingsUsage, type SettingsUsageKeyEntry } from "../../api/settingsUsage";

/**
 * AddModelPanel — user-added model providers (BYOK).
 *
 * The API key is WRITE-ONLY: it lives in a password input, is cleared the
 * moment the form submits, and never comes back from the server (inventory
 * rows carry only a key_present flag). Stored encrypted at rest via the
 * house byok SecretBox mechanism (see settings_models_admin.py).
 */

const CUSTOM_PROVIDER = "custom";
type ProviderChoice = string | null;

const EXECUTION_LABELS: Record<UserModelRow["execution_status"], string> = {
  executable: "Executable",
  blocked_unknown_pricing: "Blocked: pricing unknown",
  blocked_idempotency_unproven: "Blocked: idempotency unproven",
  blocked_reconciliation_unproven: "Blocked: reconciliation unproven",
  blocked_hidden_retries: "Blocked: hidden retries",
  blocked_provider_qualification: "Blocked: provider qualification",
  blocked_selection_authority: "Blocked: selection authority",
  blocked_no_hard_ceiling_adapter: "Blocked: no hard-ceiling adapter",
  blocked_hard_ceiling_adapter_mismatch: "Blocked: adapter mismatch",
};

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function AddModelPanel() {
  const [models, setModels] = useState<UserModelRow[] | null>(null);
  const [usageByKey, setUsageByKey] = useState<Record<string, SettingsUsageKeyEntry>>({});
  const [staleRegistered, setStaleRegistered] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<SettingsModelCatalogProvider[] | null>(
    null,
  );
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [provider, setProvider] = useState<ProviderChoice>(null);
  const [kind, setKind] = useState<ProviderKind>("openai_compat");
  const [displayName, setDisplayName] = useState("");
  const [modelId, setModelId] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [messageKind, setMessageKind] = useState<"status" | "error">("status");
  const keyRef = useRef<HTMLInputElement>(null);
  const formHeadingRef = useRef<HTMLHeadingElement>(null);
  const removeButtonRefs = useRef(new Map<string, HTMLButtonElement>());
  const mountedRef = useRef(true);
  const providerChoiceTouchedRef = useRef(false);

  const preset = useMemo(
    () => catalog?.find((item) => item.catalog_id === provider),
    [catalog, provider],
  );

  function clearSecret() {
    setApiKey("");
    if (keyRef.current) keyRef.current.value = "";
  }

  function clearEditorTransientState() {
    clearSecret();
    setMessage(null);
  }

  async function refresh(): Promise<UserModelRow[] | null> {
    try {
      const [modelsResult, usageResult] = await Promise.allSettled([
        fetchUserModels(),
        fetchSettingsUsage(),
      ]);
      if (!mountedRef.current) return null;
      if (modelsResult.status === "rejected") {
        setLoadError("Can't load saved models. Try again.");
        return null;
      }
      const res = modelsResult.value;
      setModels(res.models);
      setStaleRegistered(res.stale_registered ?? []);
      setLoadError(null);
      if (usageResult.status === "fulfilled") {
        setUsageByKey(
          Object.fromEntries(
            usageResult.value.keys.map((key) => [key.api_key_id, key]),
          ),
        );
      } else {
        setUsageByKey({});
      }
      return res.models;
    } catch {
      if (!mountedRef.current) return null;
      setLoadError("Can't load saved models. Try again.");
      return null;
    }
  }

  async function loadCatalog() {
    setCatalogLoading(true);
    setCatalogError(null);
    try {
      const response = await fetchSettingsModelCatalog();
      if (!mountedRef.current) return;
      setCatalog(response.providers);
      if (!providerChoiceTouchedRef.current && response.providers.length > 0) {
        const first = response.providers[0];
        setKind(first.provider_kind);
        setModelId(first.models[0].id);
        setDisplayName(first.models[0].label);
        setProvider(first.catalog_id);
      }
    } catch {
      if (!mountedRef.current) return;
      setCatalogError("Can't load provider presets. Retry or use Advanced.");
    } finally {
      if (mountedRef.current) setCatalogLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    void loadCatalog();
    return () => {
      mountedRef.current = false;
      if (keyRef.current) keyRef.current.value = "";
    };
  }, []);

  const needsBaseUrl = provider === CUSTOM_PROVIDER && kind === "openai_compat";
  const canSubmit =
    !busy &&
    displayName.trim().length > 0 &&
    modelId.length > 0 &&
    apiKey.length > 0 &&
    (!needsBaseUrl || baseUrl.length > 0);

  function selectProvider(next: string) {
    providerChoiceTouchedRef.current = true;
    clearEditorTransientState();
    setProvider(next);
    const nextPreset = catalog?.find((item) => item.catalog_id === next);
    if (nextPreset) {
      setKind(nextPreset.provider_kind);
      setModelId(nextPreset.models[0].id);
      setDisplayName(nextPreset.models[0].label);
      setBaseUrl("");
    } else {
      setKind("openai_compat");
      setModelId("");
      setDisplayName("");
      setBaseUrl("");
    }
    queueMicrotask(() => keyRef.current?.focus());
  }

  function selectModel(nextModelId: string) {
    clearEditorTransientState();
    setModelId(nextModelId);
    const model = preset?.models.find((item) => item.id === nextModelId);
    if (model) setDisplayName(model.label);
    queueMicrotask(() => keyRef.current?.focus());
  }

  async function onAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setMessage(null);
    setMessageKind("status");
    // Write-only key: captured once, cleared from the field immediately —
    // whatever the server answers, the key never sits in the form again.
    const key = apiKey;
    clearSecret();
    try {
      await addUserModel({
        provider_kind: kind,
        ...(preset ? { provider_catalog_id: preset.catalog_id } : {}),
        model_id: modelId,
        display_name: displayName.trim(),
        api_key: key,
        ...(preset?.provider_kind === "openai_compat"
          ? { base_url: preset.default_base_url }
          : {}),
        ...(needsBaseUrl ? { base_url: baseUrl } : {}),
      });
      if (!mountedRef.current) return;
      setMessage(
        "Model added. Provider charges go to your provider account; Antiek reports metered usage separately.",
      );
      setMessageKind("status");
      await refresh();
    } catch {
      if (mountedRef.current) {
        setMessage(
          "Can't add this model. Check the non-secret fields and enter the API key again.",
        );
        setMessageKind("error");
      }
    } finally {
      if (mountedRef.current) {
        clearSecret();
        setBusy(false);
      }
    }
  }

  async function onRemove(row: UserModelRow) {
    if (
      !window.confirm(
        `Remove “${row.display_name}”? Its stored key becomes unusable.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setMessage(null);
    setMessageKind("status");
    const removedIndex =
      models?.findIndex((model) => model.id === row.id) ?? -1;
    try {
      await removeUserModel(row.id);
      if (!mountedRef.current) return;
      setMessage("Model removed.");
      const refreshedModels = await refresh();
      if (!mountedRef.current) return;
      const focusTarget =
        refreshedModels?.[removedIndex] ??
        (removedIndex > 0 ? refreshedModels?.[removedIndex - 1] : undefined);
      window.setTimeout(() => {
        if (focusTarget) removeButtonRefs.current.get(focusTarget.id)?.focus();
        else formHeadingRef.current?.focus();
      }, 0);
    } catch {
      if (!mountedRef.current) return;
      setMessage("Can't remove this model. Try again.");
      setMessageKind("error");
    } finally {
      if (mountedRef.current) setBusy(false);
    }
  }

  const submitDisabledReason = busy
    ? "Wait for the current model change to finish."
    : !displayName.trim() || !modelId || !apiKey || (needsBaseUrl && !baseUrl)
      ? "Complete the displayed fields and enter an API key."
      : null;

  return (
    <LemonCard title="Add model (BYOK)" elevation="z1">
      <div className="p-4 space-y-4" aria-busy={busy}>
        <p className="text-xs text-ink-soft dark:text-starlight">
          Bring your own provider key. It is encrypted at rest and never
          displayed again — the inventory only shows whether a key is stored.
        </p>

        {loadError && (
          <p
            className="text-sm text-red-700 dark:text-red-300 font-mono"
            role="alert"
          >
            {loadError}
          </p>
        )}
        {models === null && !loadError && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            Loading your models…
          </p>
        )}
        {models && models.length === 0 && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            No user-added models yet.
          </p>
        )}
        {staleRegistered.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300 font-mono">
            Stale registrations (registry record lost):{" "}
            {staleRegistered.join(", ")} — they cannot resolve keys and clear at
            the next restart.
          </p>
        )}
        {models && models.length > 0 && (
          <ul className="space-y-2" aria-label="Saved provider models">
            {models.map((m) => (
              <li
                key={m.id}
                className="flex min-w-0 flex-col gap-2 border-b border-ink/10 pb-2 font-mono text-[13px] dark:border-bright/10 min-[640px]:flex-row min-[640px]:items-start min-[640px]:justify-between"
              >
                <span className="min-w-0 break-words text-ink dark:text-bright font-semibold">
                  {m.display_name}
                  <span className="font-normal break-all text-ink-soft dark:text-starlight">
                    {" "}
                    · {m.provider_kind} · {m.model_id}
                  </span>
                </span>
                <span className="grid w-full min-w-0 grid-cols-2 items-center gap-2 min-[520px]:flex min-[520px]:flex-wrap min-[640px]:w-auto">
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
                  <span className="break-words">
                    {EXECUTION_LABELS[m.execution_status]}
                  </span>
                  {usageByKey[m.id]?.remaining_cents != null && (
                    <span className="text-[11px] text-emerald-700 dark:text-emerald-300">
                      remaining {formatCents(usageByKey[m.id].remaining_cents)}
                    </span>
                  )}
                  <button
                    ref={(element) => {
                      if (element) removeButtonRefs.current.set(m.id, element);
                      else removeButtonRefs.current.delete(m.id);
                    }}
                    type="button"
                    disabled={busy}
                    aria-describedby={
                      busy ? "model-mutation-disabled-reason" : undefined
                    }
                    onClick={() => void onRemove(m)}
                    className="min-h-11 justify-self-start text-xs font-semibold text-emperor underline underline-offset-4 disabled:opacity-50"
                  >
                    Remove
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <form
          className="space-y-4"
          onSubmit={onAdd}
          aria-busy={busy}
          aria-label="Add provider model"
        >
          <h3
            ref={formHeadingRef}
            tabIndex={-1}
            className="font-mono text-sm font-semibold text-ink outline-none focus-visible:ring-2 focus-visible:ring-sun dark:text-bright"
          >
            Add a provider model
          </h3>
          <fieldset className="space-y-2">
            <legend className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
              Provider
            </legend>
            {catalogLoading && (
              <p
                role="status"
                aria-live="polite"
                className="text-xs text-ink-soft dark:text-starlight"
              >
                Loading provider presets…
              </p>
            )}
            {catalogError && (
              <div
                role="alert"
                className="flex flex-wrap items-center gap-2 text-xs text-red-700 dark:text-red-300"
              >
                <span>{catalogError}</span>
                <LemonButton
                  type="button"
                  variant="tertiary"
                  size="sm"
                  onClick={() => void loadCatalog()}
                >
                  Retry presets
                </LemonButton>
              </div>
            )}
            <div className="grid grid-cols-1 min-[480px]:grid-cols-3 gap-2">
              {[
                ...(catalog ?? []).map((item) => ({
                  value: item.catalog_id,
                  label: item.display,
                })),
                { value: CUSTOM_PROVIDER, label: "Advanced" },
              ].map(({ value, label }) => (
                <label
                  key={value}
                  className="min-h-11 flex items-center gap-2 px-3 border-edge border-sun rounded-hog bg-ice-0 dark:bg-charcoal-2 font-mono text-[13px] cursor-pointer"
                >
                  <input
                    type="radio"
                    name="provider"
                    value={value}
                    checked={provider === value}
                    onChange={() => selectProvider(value)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <p className="text-xs text-ink-soft dark:text-starlight">
            Your provider bills API calls to your provider account. Antiek
            separately records metered usage and shows whether the selected
            route is actually executable.
          </p>

          {provider === CUSTOM_PROVIDER && (
            <label
              className="flex flex-col gap-1"
              htmlFor="custom-provider-kind"
            >
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Adapter
              </span>
              <select
                id="custom-provider-kind"
                value={kind}
                onChange={(event) => {
                  clearEditorTransientState();
                  setKind(event.target.value as ProviderKind);
                  setBaseUrl("");
                }}
                className="h-11 w-full px-3 border-edge border-sun rounded-hog bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright font-mono text-[13px]"
              >
                <option value="openai_compat">OpenAI-compatible</option>
                <option value="anthropic">Anthropic</option>
              </select>
            </label>
          )}

          {preset && (
            <label className="flex flex-col gap-1" htmlFor="preset-model">
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Model
              </span>
              <select
                id="preset-model"
                value={modelId}
                onChange={(event) => selectModel(event.target.value)}
                className="h-11 w-full px-3 border-edge border-sun rounded-hog bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright font-mono text-[13px]"
              >
                {preset.models.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="space-y-3">
            <div className="flex flex-col gap-1">
              <label
                htmlFor="model-display-name"
                className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight"
              >
                Display name
              </label>
              <LemonInput
                id="model-display-name"
                sizing="lg"
                wrapperClassName="w-full"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="My DeepSeek"
              />
            </div>
            {provider === CUSTOM_PROVIDER && (
              <div className="flex flex-col gap-1">
                <label
                  htmlFor="custom-model-id"
                  className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight"
                >
                  Model id
                </label>
                <LemonInput
                  id="custom-model-id"
                  sizing="lg"
                  wrapperClassName="w-full"
                  value={modelId}
                  onChange={(e) => setModelId(e.target.value)}
                  placeholder="deepseek-chat"
                />
              </div>
            )}
            {needsBaseUrl && (
              <div className="flex flex-col gap-1">
                <label
                  htmlFor="custom-base-url"
                  className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight"
                >
                  Base URL (full, including version prefix)
                </label>
                <LemonInput
                  id="custom-base-url"
                  sizing="lg"
                  wrapperClassName="w-full"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  placeholder="https://api.deepseek.com/v1"
                  inputMode="url"
                />
              </div>
            )}
            <div className="flex flex-col gap-1">
              <label
                htmlFor="provider-api-key"
                className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight"
              >
                API key (write-only)
              </label>
              <LemonInput
                id="provider-api-key"
                ref={keyRef}
                sizing="lg"
                wrapperClassName="w-full"
                type="password"
                autoComplete="new-password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-…"
              />
            </div>
            <div className="flex flex-col min-[480px]:flex-row gap-2">
              <LemonButton
                type="submit"
                variant="secondary"
                size="lg"
                disabled={!canSubmit}
                aria-describedby="add-model-disabled-reason"
                fullWidth
              >
                {busy ? "Adding…" : "Add model"}
              </LemonButton>
              <LemonButton
                type="button"
                variant="tertiary"
                size="lg"
                fullWidth
                onClick={() => {
                  clearEditorTransientState();
                  setDisplayName(preset?.models[0].label ?? "");
                  setModelId(preset?.models[0].id ?? "");
                  setBaseUrl("");
                  keyRef.current?.focus();
                }}
              >
                Cancel
              </LemonButton>
            </div>
          </div>
        </form>

        <p
          id="add-model-disabled-reason"
          className="text-xs text-ink-soft dark:text-starlight"
        >
          {submitDisabledReason ?? "Ready to add this model."}
        </p>
        <span id="model-mutation-disabled-reason" className="sr-only">
          Wait for the current model change to finish.
        </span>

        {message && (
          <p
            className={
              messageKind === "error"
                ? "text-xs text-red-700 dark:text-red-300"
                : "text-xs text-ink-soft dark:text-starlight"
            }
            role={messageKind === "error" ? "alert" : "status"}
            aria-live={messageKind === "error" ? "assertive" : "polite"}
          >
            {message}
          </p>
        )}
      </div>
    </LemonCard>
  );
}
