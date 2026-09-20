/** Login destinations must be root-relative paths, not browser URL syntax. */
export function safeNext(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return "/";
  for (const char of value) {
    const code = char.charCodeAt(0);
    if (char === "\\" || code < 32 || code === 127) return "/";
  }
  return value;
}
