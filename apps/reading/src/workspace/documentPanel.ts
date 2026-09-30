/**
 * The id of the route-content element the document tabs control. PanelLayout
 * (entry chunk) renders it; the lazy strip marks it role="tabpanel" and
 * labels it with the selected tab while the strip is mounted. Its own module
 * so the entry chunk takes one string, not the strip.
 */
export const DOCUMENT_PANEL_ID = "cockpit-document-panel";
