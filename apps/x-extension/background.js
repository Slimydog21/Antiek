// Background service worker — currently a no-op stub.
//
// Kept in the manifest as a placeholder so future async work (e.g. a
// "capture all replies in this thread" deep-traverse, or batching
// multiple captures) has a place to land without touching the
// manifest.

self.addEventListener("install", () => {
  // no-op
});
