/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ANTIEK_UI?: string;
  readonly VITE_POSTHOG_PROJECT_TOKEN?: string;
  readonly VITE_POSTHOG_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// pdf.js ships its worker as an ES module. Vite's ?url suffix returns
// the public URL the bundler emits for it. The default vite/client
// reference covers ?url for most asset types but not .mjs explicitly;
// declare so TS resolves it cleanly.
declare module "*.mjs?url" {
  const src: string;
  export default src;
}
