import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdCreative } from "./AdCreative";

describe("AdCreative", () => {
  it("encodes house-promo document ids before linking to the Reader", () => {
    render(
      <AdCreative
        orientation="horizontal"
        fill={{
          position: "top",
          kind: "house",
          house: {
            promoted_document_id: "doc with/slash",
            title: "Promoted source",
            author: "A",
          },
          revenue_usd_cents: 0,
        }}
      />,
    );

    expect(screen.getByRole("link", { name: /Promoted source/ }).getAttribute("href")).toBe(
      "/read/doc%20with%2Fslash",
    );
  });
});
