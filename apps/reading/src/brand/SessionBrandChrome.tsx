/**
 * SessionBrandChrome — shared living-TV product-door densify pattern.
 *
 * Every operator/product door should consume session Imagine assets
 * (thinking mark + living-TV invent strip), not leave invent inventory-only.
 * One component keeps layout, testids, and asset paths hard to vary.
 */

import type { ReactNode } from "react";

import thinkingArt from "./werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "./werner/poses/session/werner_living_tv_session_v1.webp";

export interface SessionBrandChromeProps {
  /** Human title shown next to the thinking mark. */
  title: string;
  /**
   * Prefix for data-testid attributes:
   *   `${testIdPrefix}-werner-brand`
   *   `${testIdPrefix}-living-tv-art`
   */
  testIdPrefix: string;
  /** Optional description / meta under the invent strip. */
  children?: ReactNode;
  /** Title heading level — index doors use h1; nested panels may use h2. */
  as?: "h1" | "h2";
  titleClassName?: string;
  /** Override invent strip (e.g. midnight-oil specific webp). */
  inventSrc?: string;
  inventMatchHint?: string;
  /** Size of the thinking mark in pixels. */
  markSize?: number;
  inventHeightClass?: string;
}

export default function SessionBrandChrome({
  title,
  testIdPrefix,
  children,
  as = "h1",
  titleClassName = "text-2xl font-serif text-ink dark:text-bright",
  inventSrc = livingTvArt,
  markSize = 48,
  inventHeightClass = "h-16",
}: SessionBrandChromeProps) {
  const TitleTag = as;
  return (
    <header className="space-y-2">
      <div className="flex items-center gap-3">
        <img
          src={thinkingArt}
          alt=""
          aria-hidden="true"
          data-testid={`${testIdPrefix}-werner-brand`}
          className="shrink-0 object-contain"
          style={{ width: markSize, height: markSize }}
        />
        <TitleTag className={titleClassName}>{title}</TitleTag>
      </div>
      <img
        src={inventSrc}
        alt=""
        aria-hidden="true"
        data-testid={`${testIdPrefix}-living-tv-art`}
        className={`${inventHeightClass} w-full max-w-md rounded-md object-cover object-center`}
        loading="lazy"
        decoding="async"
      />
      {children}
    </header>
  );
}

/** Re-export default invent path for tests that assert asset identity. */
export const SESSION_LIVING_TV_ASSET_HINT = /werner_living_tv_session_v1/;
