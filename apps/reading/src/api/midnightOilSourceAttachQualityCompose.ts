/**
 * Midnight Oil unattended + source attach quality pack (pure).
 *
 * Operator vision: set time + goals + price ceiling for unattended deep
 * research ("midnight oil"), while attaching knowledge-dense HTML sources
 * (arxiv/substack) under quality/budget honesty — highest-quality DR product
 * without needing the operator present in the workstation.
 *
 * live_execution_authorized always false.
 * remote_fetched always false.
 * pdf_view_authorized always false.
 * live_dispatched always false.
 * store_mutated always false.
 */

import {
  composeMidnightOilUnattendedPackage,
  type MidnightOilUnattendedPackageCompose,
  type MoGoalEntry,
} from "./midnightOilUnattendedPackageCompose";
import {
  composeSourcePublicationDrAttachQuality,
  type SourcePublicationDrAttachQualityCompose,
} from "./sourcePublicationDrAttachQualityCompose";
import type { HtmlNativeSourceRef } from "./htmlNativeSourceAttachCompose";
import type { CitationRecord } from "./deepResearchSourceCitationPack";
import type { PublicationFamily } from "./sourcePublicationRegistry";

export type { MoGoalEntry };

export interface MidnightOilSourceAttachQualityInput {
  operator_id: string;
  work_minutes: number;
  goals: MoGoalEntry[];
  usd_per_hour?: number | null;
  approved_ceiling_usd?: number | null;
  operator_ack: boolean;
  unattended_ack: boolean;
  spend_consent: boolean;
  brief_dispatch_ready?: boolean;
  /** Research session / parent for source attach. */
  session_id: string;
  parent_asset_id: string;
  requested_families: PublicationFamily[];
  sources: HtmlNativeSourceRef[];
  citations?: CitationRecord[] | null;
  derive_citations_from_sources?: boolean;
  quality_overall: number | null;
  quality_floor?: number;
  would_exceed: boolean | null;
  operator_override?: boolean;
  /**
   * When true (default), require MO unattended_package_ready AND source pack_ready.
   */
  require_both?: boolean;
}

export interface MidnightOilSourceAttachQualityCompose {
  operator_id: string;
  session_id: string;
  parent_asset_id: string;
  mo_unattended: MidnightOilUnattendedPackageCompose;
  source_quality: SourcePublicationDrAttachQualityCompose;
  /**
   * True when mo ready and source pack ready (or either if require_both=false)
   * and operator_ack + unattended_ack + spend_consent path still pure.
   */
  pack_ready: boolean;
  live_execution_authorized: false;
  remote_fetched: false;
  pdf_view_authorized: false;
  live_dispatched: false;
  store_mutated: false;
  notes: string[];
  authority: "midnight_oil_source_attach_quality_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose MO unattended package + arxiv/substack source quality attach.
 * Never launches workers; never scrapes; never charges.
 */
export function composeMidnightOilSourceAttachQuality(
  input: MidnightOilSourceAttachQualityInput,
): MidnightOilSourceAttachQualityCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (typeof input.unattended_ack !== "boolean") {
    throw new Error("unattended_ack must be an explicit boolean");
  }
  if (typeof input.spend_consent !== "boolean") {
    throw new Error("spend_consent must be an explicit boolean");
  }
  const operator_id = requireNonEmpty(input.operator_id, "operator_id");
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const notes: string[] = [
    "live_execution_authorized=false — midnight oil never launches workers",
    "remote_fetched=false — no live arxiv/substack scrape",
    "pdf_view_authorized=false — HTML-native sources only",
    "live_dispatched=false · store_mutated=false",
  ];

  const mo_unattended = composeMidnightOilUnattendedPackage({
    operator_id,
    work_minutes: input.work_minutes,
    goals: input.goals,
    usd_per_hour: input.usd_per_hour,
    approved_ceiling_usd: input.approved_ceiling_usd,
    operator_ack: input.operator_ack,
    unattended_ack: input.unattended_ack,
    spend_consent: input.spend_consent,
    brief_dispatch_ready: input.brief_dispatch_ready,
  });
  notes.push(...mo_unattended.notes.map((n) => `[mo] ${n}`));

  const source_quality = composeSourcePublicationDrAttachQuality({
    session_id,
    parent_asset_id,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    operator_ack: input.operator_ack,
  });
  notes.push(...source_quality.notes.map((n) => `[source_quality] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      mo_unattended.unattended_package_ready === true &&
      source_quality.pack_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (mo_unattended.unattended_package_ready === true ||
        source_quality.pack_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO unattended + source quality ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — MO package, source quality, or operator_ack gate open",
    );
  }

  if (
    mo_unattended.live_execution_authorized !== false ||
    source_quality.remote_fetched !== false ||
    source_quality.pdf_view_authorized !== false ||
    source_quality.live_dispatch_authorized !== false ||
    source_quality.store_mutated !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("live_execution_authorized=false");
  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("store_mutated=false");

  return {
    operator_id,
    session_id,
    parent_asset_id,
    mo_unattended,
    source_quality,
    pack_ready,
    live_execution_authorized: false,
    remote_fetched: false,
    pdf_view_authorized: false,
    live_dispatched: false,
    store_mutated: false,
    notes,
    authority: "midnight_oil_source_attach_quality_compose_advisory",
  };
}

export function formatMidnightOilSourceAttachQualitySummary(
  c: MidnightOilSourceAttachQualityCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_ready=${c.mo_unattended.unattended_package_ready} · ` +
    `source_ready=${c.source_quality.pack_ready} · ` +
    `sources=${c.source_quality.attach.source_count} · ` +
    `live_execution_authorized=false · remote_fetched=false · pdf_view_authorized=false`
  );
}
