import { useCallback, useEffect, useState } from "react";

import {
  fetchCertifiedProviderCredentials,
  putCertifiedProviderCredential,
  type CertifiedProviderCredentialInventory,
  type CertifiedProviderHandle,
} from "../../api/settingsModels";
import { LemonButton } from "../../components/lemon";
import LemonCard from "../../components/lemon/LemonCard";

const PROVIDER_LABELS: Record<CertifiedProviderHandle, string> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  hermes: "Hermes gateway",
  openrouter: "OpenRouter",
  xiaomi: "Xiaomi MiMo",
  zai: "Z.ai GLM",
};

export default function CertifiedProviderKeysPanel() {
  const [inventory, setInventory] =
    useState<CertifiedProviderCredentialInventory | null>();
  const [active, setActive] = useState<CertifiedProviderHandle | null>(null);
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setInventory(await fetchCertifiedProviderCredentials());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setInventory(undefined);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (inventory === null) return null;

  async function save(handle: CertifiedProviderHandle) {
    setSaving(true);
    setError(null);
    try {
      await putCertifiedProviderCredential(handle, key);
      setKey("");
      setActive(null);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSaving(false);
    }
  }

  return (
    <LemonCard title="Certified dispatch keys" elevation="z1">
      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="max-w-xl text-sm text-ink dark:text-bright">
            These keys drive process-wide certified routes. Personal model keys
            stay in the separate model inventory below.
          </p>
          {inventory && (
            <span className="font-mono text-[11px] text-ink-soft dark:text-starlight">
              env fallback: {inventory.byot_only ? "off" : "on"}
            </span>
          )}
        </div>

        {error && (
          <p role="alert" className="font-mono text-xs text-red-700 dark:text-red-300">
            Key update unavailable. {error}
          </p>
        )}
        {inventory === undefined && !error && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            Checking operator key access…
          </p>
        )}

        {inventory && (
          <ul className="divide-y divide-ink/10 dark:divide-bright/10">
            {inventory.providers.map((provider) => {
              const editing = active === provider.provider_handle;
              return (
                <li key={provider.provider_handle} className="py-3 first:pt-1">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-mono text-[13px] font-semibold text-ink dark:text-bright">
                        {PROVIDER_LABELS[provider.provider_handle]}
                      </p>
                      <p className="font-mono text-[11px] text-ink-soft dark:text-starlight">
                        {provider.provider_handle} · {provider.key_present ? "encrypted key stored" : "no certified key"}
                      </p>
                    </div>
                    <LemonButton
                      size="sm"
                      variant="tertiary"
                      aria-expanded={editing}
                      aria-label={`${
                        editing
                          ? "Cancel key update"
                          : provider.key_present
                            ? "Replace key"
                            : "Add key"
                      } for ${PROVIDER_LABELS[provider.provider_handle]}`}
                      onClick={() => {
                        setActive(editing ? null : provider.provider_handle);
                        setKey("");
                        setError(null);
                      }}
                    >
                      {editing ? "Cancel" : provider.key_present ? "Replace key" : "Add key"}
                    </LemonButton>
                  </div>
                  {editing && (
                    <form
                      className="mt-3 flex flex-col gap-2 sm:flex-row"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void save(provider.provider_handle);
                      }}
                    >
                      <label className="min-w-0 flex-1">
                        <span className="sr-only">{PROVIDER_LABELS[provider.provider_handle]} API key</span>
                        <input
                          autoComplete="off"
                          type="password"
                          value={key}
                          minLength={8}
                          maxLength={512}
                          required
                          autoFocus
                          onChange={(event) => setKey(event.target.value)}
                          placeholder="Paste API key"
                          className="h-9 w-full rounded-hog border border-ink/20 bg-transparent px-3 font-mono text-[13px] text-ink outline-none focus:border-sun dark:border-bright/20 dark:text-bright"
                        />
                      </label>
                      <LemonButton type="submit" size="sm" variant="primary" disabled={saving || key.length < 8}>
                        {saving ? "Saving…" : "Save and activate"}
                      </LemonButton>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-[11px] text-ink-soft dark:text-starlight">
          Turn off environment fallback only after every required route shows an encrypted key.
        </p>
      </div>
    </LemonCard>
  );
}
