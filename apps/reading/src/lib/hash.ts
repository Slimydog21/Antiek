// Browser-native SHA-256 of an ArrayBuffer / Uint8Array.
//
// Produces the same hex format as Python's hashlib so document_id /
// content_hash values are comparable across the polyglot seam.

export async function sha256Hex(data: ArrayBuffer | Uint8Array): Promise<string> {
  // crypto.subtle.digest requires an ArrayBuffer (not SharedArrayBuffer).
  // Copy if the source might be backed by a SharedArrayBuffer or if it's
  // a Uint8Array view onto a larger buffer.
  let buf: ArrayBuffer;
  if (data instanceof Uint8Array) {
    const copy = new Uint8Array(data.byteLength);
    copy.set(data);
    buf = copy.buffer;
  } else {
    buf = data;
  }
  const digest = await crypto.subtle.digest("SHA-256", buf);
  const bytes = new Uint8Array(digest);
  let out = "";
  for (let i = 0; i < bytes.length; i++) {
    out += bytes[i].toString(16).padStart(2, "0");
  }
  return out;
}

// Convenience: render the prefixed form used in payload fields
// (mirrors the Python ``sha256:<12 hex>`` pattern in dispatch).
export async function sha256Prefix(
  data: ArrayBuffer | Uint8Array,
  n = 12,
): Promise<string> {
  return "sha256:" + (await sha256Hex(data)).slice(0, n);
}
