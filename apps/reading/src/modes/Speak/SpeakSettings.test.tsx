import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import SpeakSettings from "./SpeakSettings";
import type { EconomicsView } from "../../lib/speakApi";
import { PAYOUT_COPY } from "../../lib/speakVocab";

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

// ── SPR-04 — the payout promise, legible & honest ──
describe("SpeakSettings — the payout promise is explained honestly (SPR-04)", () => {
  const renderPublic = (econ: EconomicsView = GATED) =>
    render(
      <SpeakSettings
        willBePublic
        subjectStatusWord={null}
        economics={econ}
        actionNote={null}
        onPublish={() => {}}
        onQuoteBook={() => {}}
        onReleasePayout={vi.fn()}
      />,
    );

  // ── M3 — the §9.3 Option-B basis, in human words (no formula, no per-second) ──
  it("explains the §9.3 Option-B basis: share weighted by corroboration + sourcing quality", () => {
    renderPublic();
    // Rendered (and single-sourced from PAYOUT_COPY, so it can't drift from the
    // public lane). The basis appears in both the split summary and the payout
    // section, so assert at least one.
    expect(screen.getAllByText((_t, el) => el?.textContent === PAYOUT_COPY.basis).length)
      .toBeGreaterThan(0);
    // Honest WORDS, not the formula and not a per-second/airtime model.
    expect(screen.queryByText(/per second|per-second|airtime|ad-duration|timecode|per minute|runtime/i))
      .toBeNull();
  });

  // ── M3 — slop earns $0 ──
  it("says a low-effort answer earns nothing (slop earns $0)", () => {
    renderPublic();
    expect(screen.getAllByText((_t, el) => el?.textContent?.includes(PAYOUT_COPY.slopEarnsZero) ?? false).length)
      .toBeGreaterThan(0);
  });

  // ── M3 — graded by a verifier, not the requester ──
  it("says the grade comes from the system's verifier, not the requester", () => {
    renderPublic();
    expect(screen.getAllByText((_t, el) => el?.textContent === PAYOUT_COPY.verifierNotRequester).length)
      .toBeGreaterThan(0);
  });

  // ── M2 — accrued-but-gated share, shown inline, branched on the LIVE gate ──
  it("shows the gated-disbursement inline state when disbursementAllowed is false", () => {
    renderPublic(GATED); // disbursementAllowed: false
    // The share FRACTION accrues now…
    expect(screen.getByText(/each voice's share accrues now/i)).toBeTruthy();
    // …the $ AMOUNT is honestly $0 (rendered, possibly in more than one place)…
    expect(screen.getAllByText(/\$0\.00/).length).toBeGreaterThan(0);
    // …and nothing is paid until the legal review (G2/G3).
    expect(screen.getByText(/nothing is paid out until the legal review \(g2\/g3\)/i)).toBeTruthy();
  });

  it("shows the open-disbursement inline copy when disbursementAllowed is true (hypothetical)", () => {
    renderPublic({ ...GATED, disbursementAllowed: true });
    expect(screen.getByText(/payouts are open — money routes to contributors/i)).toBeTruthy();
  });

  // ── M4 — escrow-only, honest $0, no withdraw affordance ──
  it("has no withdraw / cash-out / claim-earnings affordance, and $0 renders as $0", () => {
    renderPublic();
    expect(
      screen.queryByRole("button", {
        name: /withdraw|cash ?out|claim earnings|claim your|pay out|disburse|send money/i,
      }),
    ).toBeNull();
    expect(screen.getByText(/\$0\.00/)).toBeTruthy();
    // No projected/estimated $ figure that isn't $0.
    expect(screen.queryByText(/projected|estimated earnings|you will earn/i)).toBeNull();
  });
});
