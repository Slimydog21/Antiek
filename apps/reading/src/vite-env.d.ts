/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ANTIEK_UI?: string;
  readonly VITE_POSTHOG_PROJECT_TOKEN?: string;
  readonly VITE_POSTHOG_HOST?: string;
  /** Opt-in MASTER.md manual sponsor footer (website ads MVP). Set to "1". */
  readonly VITE_MANUAL_SPONSOR_FOOTER?: string;
  /** Optional operator-sold sponsor display name (with landing URL → ad fill). */
  readonly VITE_MANUAL_SPONSOR_NAME?: string;
  readonly VITE_MANUAL_SPONSOR_LANDING_URL?: string;
  /** Optional creative image URL; defaults to /mark-32.png when name+landing set. */
  readonly VITE_MANUAL_SPONSOR_CREATIVE_URL?: string;
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
