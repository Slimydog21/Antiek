import { Navigate, useLocation, useParams } from "react-router-dom";

const CANONICAL_ANCHOR = /^antiek-anchor-[0-9a-f]{64}$/;

export function canonicalAnchor(search: string): string | undefined {
  const anchor = new URLSearchParams(search).get("anchor");
  return anchor && CANONICAL_ANCHOR.test(anchor) ? anchor : undefined;
}

export function legacyWrestleRedirectTarget(
  documentId?: string,
  search = "",
): string {
  if (!documentId) return "/documents";
  const target = `/documents/${encodeURIComponent(documentId)}`;
  const anchor = canonicalAnchor(search);
  return anchor ? `${target}?anchor=${anchor}` : target;
}

export function LegacyWrestleRedirect() {
  const { documentId } = useParams<{ documentId: string }>();
  const { search } = useLocation();
  return <Navigate to={legacyWrestleRedirectTarget(documentId, search)} replace />;
}
