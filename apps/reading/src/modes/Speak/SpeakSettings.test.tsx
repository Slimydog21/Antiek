import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import SpeakSettings from "./SpeakSettings";

/**
 * SpeakSettings.test — split shown, not paid (Product Depth SPR-08 M4).
 *
 * Load-bearing claims:
 *  - for a public work the 70% contributor split is DISPLAYED as attribution,
 *    labelled not-yet-paid, with an honest $0 balance (no buyers/ad revenue);
 *  - there is NO disburse/pay control — the only money-adjacent button is the
 *    (gated) publish, which delegates to the host's gated handler;
 *  - a private work honestly shows no split.
 */
afterEach(cleanup);

describe("SpeakSettings — the honest split", () => {
  it("shows the 70% split as attribution, labelled not paid, with a $0 balance", () => {
    render(
      <SpeakSettings
        willBePublic
        subjectStatusWord="deceased"
        economics={{ splitApplies: true, creatorCarriesCost: false }}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
      />,
    );
    expect(screen.getByText(/70%/)).toBeTruthy();
    expect(screen.getByText(/\$0\.00/)).toBeTruthy();
    expect(screen.getByText(/no buyers or ad revenue yet/i)).toBeTruthy();
    expect(screen.getByText(/this is what each voice is owed, not a payment/i)).toBeTruthy();
    // No disburse / pay-out control exists on this surface.
    expect(screen.queryByRole("button", { name: /pay|disburse|send money|payout/i })).toBeNull();
  });

  it("the only money-adjacent control is the gated publish, which calls the host handler", () => {
    const onPublish = vi.fn();
    render(
      <SpeakSettings
        willBePublic
        subjectStatusWord={null}
        economics={{ splitApplies: true, creatorCarriesCost: false }}
        actionNote={null}
        onPublish={onPublish}
        onQuoteBook={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /try to publish/i }));
    expect(onPublish).toHaveBeenCalledOnce();
  });

  it("a private work honestly shows no split", () => {
    render(
      <SpeakSettings
        willBePublic={false}
        subjectStatusWord={null}
        economics={{ splitApplies: false, creatorCarriesCost: true }}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
      />,
    );
    expect(screen.getByText(/there's no contributor split/i)).toBeTruthy();
    expect(screen.queryByText(/\$0\.00/)).toBeNull();
  });
});
