/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ANTIEK_UI?: string;
  readonly VITE_POSTHOG_PROJECT_TOKEN?: string;
  readonly VITE_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
