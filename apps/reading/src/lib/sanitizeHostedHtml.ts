const BLOCKED_ELEMENTS = new Set([
  "script", "iframe", "object", "embed", "form", "input", "button",
  "textarea", "select", "option", "svg", "math", "link", "meta", "base",
  "style", "template",
]);

const URL_ATTRIBUTES = new Set(["href", "src", "poster", "cite"]);

function isSafeUrl(value: string, attribute: string): boolean {
  const trimmed = value.trim();
  if (!trimmed || trimmed.startsWith("#") || trimmed.startsWith("/")) return true;
  if (attribute === "src" && /^data:image\/(?:png|gif|jpe?g|webp);base64,/i.test(trimmed)) {
    return true;
  }
  try {
    const url = new URL(trimmed, window.location.origin);
    return ["http:", "https:", "mailto:"].includes(url.protocol);
  } catch {
    return false;
  }
}

/** Sanitize API- and model-authored documents before mounting them in the app DOM. */
export function sanitizeHostedHtml(html: string): string {
  const document = new DOMParser().parseFromString(html, "text/html");
  for (const element of Array.from(document.body.querySelectorAll("*"))) {
    if (BLOCKED_ELEMENTS.has(element.localName)) {
      element.remove();
      continue;
    }
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      if (
        name.startsWith("on") ||
        name === "style" ||
        name === "srcdoc" ||
        (URL_ATTRIBUTES.has(name) && !isSafeUrl(attribute.value, name))
      ) {
        element.removeAttribute(attribute.name);
      }
    }
    if (element.localName === "a" && element.hasAttribute("href")) {
      element.setAttribute("rel", "noopener noreferrer");
    }
  }
  return document.body.innerHTML;
}
