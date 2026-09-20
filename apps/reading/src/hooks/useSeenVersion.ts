import { useEffect, useState } from "react";

import { getSeenVersion, subscribeSeen } from "../workspace/seen";

/**
 * useSeenVersion — re-render when any investigation's seen-state changes
 * (herdr transfer P0-3). Surfaces that display unread state call this and
 * re-read lastSeenAt() in render; markSeen in ANY surface (or tab) then
 * updates them all. Returns the current version number (unused value —
 * the re-render is the point).
 */
export function useSeenVersion(): number {
  const [version, setVersion] = useState(getSeenVersion);
  useEffect(() => subscribeSeen(() => setVersion(getSeenVersion())), []);
  return version;
}
