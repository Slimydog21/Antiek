/// <reference types="vite/client" />

// pdf.js ships its worker as an ES module. Vite's ?url suffix returns
// the public URL the bundler emits for it. The default vite/client
// reference covers ?url for most asset types but not .mjs explicitly;
// declare so TS resolves it cleanly.
declare module "*.mjs?url" {
  const src: string;
  export default src;
}
