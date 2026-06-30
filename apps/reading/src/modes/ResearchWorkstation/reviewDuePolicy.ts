import { useCallback, useState } from "react";

const REVIEW_DUE_POLICY_KEY = "antiek.research.review_due_policy";
const DISABLED_VALUE = "off";

export function readReviewDuePolicy(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(REVIEW_DUE_POLICY_KEY) !== DISABLED_VALUE;
  } catch {
    return true;
  }
}

export function writeReviewDuePolicy(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (enabled) {
      window.localStorage.removeItem(REVIEW_DUE_POLICY_KEY);
    } else {
      window.localStorage.setItem(REVIEW_DUE_POLICY_KEY, DISABLED_VALUE);
    }
  } catch {
    /* localStorage unavailable — the in-memory hook state still applies */
  }
}

export function useReviewDuePolicy(): [boolean, (enabled: boolean) => void] {
  const [enabled, setEnabledState] = useState(() => readReviewDuePolicy());
  const setEnabled = useCallback((next: boolean) => {
    setEnabledState(next);
    writeReviewDuePolicy(next);
  }, []);
  return [enabled, setEnabled];
}
