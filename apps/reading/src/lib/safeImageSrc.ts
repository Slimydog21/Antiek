export function safeImageSrc(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const src = value.trim();
  if (!src) return null;
  if (/^data:image\/[a-z0-9.+-]+;base64,/i.test(src)) return src;
  try {
    const parsed = new URL(src);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? src : null;
  } catch {
    return null;
  }
}
