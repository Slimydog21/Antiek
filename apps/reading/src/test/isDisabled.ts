/**
 * isDisabled — is this control unusable right now?
 *
 * True for the native `disabled` attribute and for aria-disabled="true". A
 * LemonButton with a disabledReason uses the second, so it stays focusable
 * and its reason can be read; a test that asserted `button.disabled` would
 * now pass vacuously on `false`. Ask this instead.
 */
export function isDisabled(el: Element | null | undefined): boolean {
  if (!el) return false;
  if ((el as HTMLButtonElement).disabled === true) return true;
  return el.getAttribute("aria-disabled") === "true";
}
