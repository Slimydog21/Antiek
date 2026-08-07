import { useEffect, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton, LemonInput, LemonSelect } from "../../components/lemon";
import {
  addUserModel,
  fetchUserModels,
  removeUserModel,
  type ProviderCatalogId,
  type ProviderKind,
  type UserModelRow,
} from "../../api/settingsModels";

/**
 * AddModelPanel — user-added model providers (BYOK).
 *
 * The API key is WRITE-ONLY: it lives in a password input, is cleared the
 * moment the form submits, and never comes back from the server (inventory
 * rows carry only a key_present flag). Stored encrypted at rest via the
 * house byok SecretBox mechanism (see settings_models_admin.py).
 */

type ProviderChoice = ProviderCatalogId | "openai" | "anthropic" | "custom";

interface ProviderOption {
  value: ProviderChoice;
  label: string;
  kind: ProviderKind;
  defaultBaseUrl?: string;
  variants?: ReadonlyArray<{ value: string; label: string }>;
}

/**
 * Mirrors the server-owned catalog in byot_provider_catalog.py. The server is
 * still authoritative: it rejects an unknown provider/model tuple and fills
 * the trusted endpoint. These rows only make those safe choices reachable.
 */
const PROVIDER_OPTIONS: ReadonlyArray<ProviderOption> = [
  {
    value: "deepseek",
    label: "DeepSeek",
    kind: "openai_compat",
    variants: [
      { value: "deepseek-reasoner", label: "DeepSeek V4 Pro" },
      { value: "deepseek-chat", label: "DeepSeek V4 Flash" },
    ],
  },
  {
    value: "kimi",
    label: "Moonshot / Kimi",
    kind: "openai_compat",
    variants: [{ value: "kimi-k2.5", label: "Kimi K2.5" }],
  },
  {
    value: "zhipu_glm",
    label: "Zhipu GLM",
    kind: "openai_compat",
    variants: [{ value: "glm-5.2", label: "GLM 5.2" }],
  },
  {
    value: "mimo",
    label: "Xiaomi MiMo",
    kind: "openai_compat",
    variants: [{ value: "mimo-v2.5-pro", label: "MiMo V2.5 Pro" }],
  },
  {
    value: "xai",
    label: "xAI",
    kind: "openai_compat",
    variants: [{ value: "grok-4.3", label: "Grok 4.3" }],
  },
  {
    value: "openai",
    label: "OpenAI",
    kind: "openai_compat",
    defaultBaseUrl: "https://api.openai.com/v1",
  },
  { value: "anthropic", label: "Anthropic", kind: "anthropic" },
  {
    value: "custom",
    label: "Custom OpenAI-compatible",
    kind: "openai_compat",
  },
];

const PROVIDER_SELECT_OPTIONS = PROVIDER_OPTIONS.map(({ value, label }) => ({
  value,
  label,
}));

export default function AddModelPanel() {
  const [models, setModels] = useState<UserModelRow[] | null>(null);
  const [staleRegistered, setStaleRegistered] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [providerChoice, setProviderChoice] =
    useState<ProviderChoice>("deepseek");
  const [displayName, setDisplayName] = useState("");
  const [modelId, setModelId] = useState("deepseek-reasoner");
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

  const provider = PROVIDER_OPTIONS.find(
    (option) => option.value === providerChoice,
  )!;
  const isPreset = provider.variants != null;
  const needsBaseUrl = providerChoice === "custom";
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
        provider_kind: provider.kind,
        ...(isPreset
          ? { provider_catalog_id: providerChoice as ProviderCatalogId }
          : {}),
        model_id: modelId,
        display_name: displayName.trim(),
        api_key: key,
        ...(needsBaseUrl && baseUrl
          ? { base_url: baseUrl }
          : provider.defaultBaseUrl
            ? { base_url: provider.defaultBaseUrl }
            : {}),
      });
      setDisplayName("");
      setModelId("");
      setBaseUrl("");
      setMessage(
        "Model added. Its key is stored encrypted and will not be shown again.",
      );
      await refresh();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
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
    try {
      await removeUserModel(row.id);
      setMessage("Model removed.");
      await refresh();
    } catch (e) {
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
          <p className="text-sm text-red-700 dark:text-red-300 font-mono">
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
                  <span
                    className={
                      m.hard_ceiling_eligible
                        ? "text-emerald-700 dark:text-emerald-300"
                        : "text-amber-700 dark:text-amber-300"
                    }
                    title={m.execution_status.replaceAll("_", " ")}
                  >
                    {m.hard_ceiling_eligible
                      ? "spend ceiling enforced"
                      : "execution blocked"}
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
              Provider
            </span>
            <LemonSelect<ProviderChoice>
              value={providerChoice}
              onChange={(nextProvider) => {
                const next = PROVIDER_OPTIONS.find(
                  (option) => option.value === nextProvider,
                )!;
                setProviderChoice(nextProvider);
                setModelId(next.variants?.[0]?.value ?? "");
                setDisplayName("");
                // A custom endpoint is credential-sensitive. Never carry it
                // across provider changes where it could receive another key.
                setBaseUrl("");
              }}
              options={PROVIDER_SELECT_OPTIONS}
              aria-label="Provider"
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
              placeholder={`My ${provider.label}`}
            />
          </label>
          {provider.variants ? (
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Model variant
              </span>
              <LemonSelect<string>
                value={modelId}
                onChange={setModelId}
                options={[...provider.variants]}
                aria-label="Model variant"
                fullWidth
              />
              <span className="text-[11px] text-ink-soft dark:text-starlight">
                Pricing is pinned by Antiek; execution stays blocked unless the
                server can enforce its spend ceiling.
              </span>
            </label>
          ) : (
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Model id
              </span>
              <LemonInput
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
                placeholder="model-id"
              />
            </label>
          )}
          {needsBaseUrl && (
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Base URL (full, including version prefix)
              </span>
              <LemonInput
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://provider.example/v1"
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
          <p
            className="text-xs text-ink-soft dark:text-starlight"
            role="status"
          >
            {message}
          </p>
        )}
      </div>
    </LemonCard>
  );
}
