import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import SpeakSettings from "./SpeakSettings";
import type { EconomicsView } from "../../lib/speakApi";

/**
 * SpeakSettings.test — split shown, not paid (Product Depth SPR-08 M4) +
 * SPR-10 M2 gate-status display + M3 AI-graded payout.
 *
 * Load-bearing claims:
 *  - for a public work the 70% contributor split is DISPLAYED as attribution,
 *    labelled not-yet-paid, with an honest $0 balance (no buyers/ad revenue);
 *  - there is NO disburse/pay control — the only money-adjacent button is the
 *    (gated) publish, which delegates to the host's gated handler;
 *  - a private work honestly shows no split;
 *  - the operator gates (G2/G3) are SHOWN as not-yet-activated, with NO
 *    affordance to close them (M2 — the hard boundary);
 *  - the AI-graded payout sets aside (escrow) what's owed, never disburses (M3).
 */
afterEach(cleanup);

const GATED: EconomicsView = {
  splitApplies: true,
  creatorCarriesCost: false,
  publicPublishingAllowed: false,
  publicPublishingReason: "gated on the legal gate (G2 lawyer review + G3 opt-in)",
  disbursementAllowed: false,
  disbursementReason: "disbursement is gated on G2/G3",
};

describe("SpeakSettings — the honest split", () => {
  it("shows the 70% split as attribution, labelled not paid, with a $0 balance", () => {
    render(
      <SpeakSettings
        willBePublic
        subjectStatusWord="deceased"
        economics={GATED}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
      />,
    );
    // 70% appears in both the split summary and the M2 matrix copy — assert
    // the load-bearing split-as-attribution sentence specifically.
    expect(screen.getByText(/70% of what it earns goes to the people/i)).toBeTruthy();
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
        economics={GATED}
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
        economics={{
          ...GATED,
          splitApplies: false,
          creatorCarriesCost: true,
        }}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
      />,
    );
    expect(screen.getByText(/there's no contributor split/i)).toBeTruthy();
    expect(screen.queryByText(/\$0\.00/)).toBeNull();
  });

  // ── M2 — the gates are SHOWN, never closable ──
  it("shows the operator gates as not-yet-activated, with no way to close them", () => {
    render(
      <SpeakSettings
        willBePublic
        subjectStatusWord={null}
        economics={GATED}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
      />,
    );
    expect(screen.getByText(/public publishing: not yet activated/i)).toBeTruthy();
    expect(screen.getByText(/payouts: not yet activated/i)).toBeTruthy();
    // The four-cell matrix is represented.
    expect(screen.getByText(/invite-only · kept private/i)).toBeTruthy();
    expect(screen.getByText(/invite-only · published/i)).toBeTruthy();
    // There is NO affordance to close/activate a gate.
    expect(
      screen.queryByRole("button", { name: /activate|close gate|enable publishing|unlock/i }),
    ).toBeNull();
  });

  // ── M3 — AI-graded payout sets aside (escrow), never disburses ──
  it("runs an AI-graded payout that sets aside what's owed (escrow), never pays out", async () => {
    const onReleasePayout = vi.fn().mockResolvedValue({
      spentUsd: "0", budgetUsd: "100", budgetExhausted: false, cappedCount: 0,
    });
    render(
      <SpeakSettings
        willBePublic
        subjectStatusWord={null}
        economics={GATED}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
        onReleasePayout={onReleasePayout}
      />,
    );
    fireEvent.change(screen.getByLabelText(/what you're hoping to learn/i), {
      target: { value: "his work and the war years" },
    });
    fireEvent.change(screen.getByLabelText(/total budget/i), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: /grade what's been shared/i }));
    await waitFor(() => expect(onReleasePayout).toHaveBeenCalledOnce());
    expect(onReleasePayout).toHaveBeenCalledWith({
      informationGoal: "his work and the war years",
      budgetUsd: "100",
      perInterviewCapUsd: "0",
    });
    // The result is framed as owed-not-paid (escrow).
    expect(await screen.findByText(/owed, not paid/i)).toBeTruthy();
  });
});
