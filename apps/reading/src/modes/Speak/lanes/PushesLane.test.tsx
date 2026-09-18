import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { listPushesMock, repingInviteeMock, makeContributionInvitePathMock } = vi.hoisted(
  () => ({
    listPushesMock: vi.fn(),
    repingInviteeMock: vi.fn(),
    makeContributionInvitePathMock: vi.fn(),
  }),
);

vi.mock("../../../lib/speakApi", async (orig) => ({
  ...(await orig<typeof import("../../../lib/speakApi")>()),
  listPushes: listPushesMock,
  repingInvitee: repingInviteeMock,
  makeContributionInvitePath: makeContributionInvitePathMock,
}));

import PushesLane from "./PushesLane";
import { PUSHES_COPY } from "../../../lib/speakVocab";

beforeEach(() => {
  listPushesMock.mockReset().mockResolvedValue({
    honesty: {
      publicRanking: "fewest_voices_first_heuristic_not_ml_profile_matching",
      privateDelivery: "invite_path_only_no_email_send_in_mvp",
    },
    publicOpportunities: [
      {
        projectId: "p-pub",
        title: "Needs voices",
        subjectRef: "Uncle Theo",
        voiceCount: 0,
        rankReason: "fewest voices first — heuristic, not profile matching",
      },
    ],
    privateRepings: [
      {
        projectId: "p-priv",
        projectTitle: "Dad private",
        interviewId: "iv1",
        who: "aunt@x.com",
        status: "invited",
        token: "tok1",
        pendingQuestionCount: 2,
        invitePath: "/speak/invite/tok1",
      },
    ],
  });
  repingInviteeMock.mockReset().mockResolvedValue({
    interviewId: "iv1",
    token: "tok1",
    invitePath: "/speak/invite/tok1",
    followupsAdded: 1,
    pendingQuestionCount: 3,
    skippedReason: null,
  });
  makeContributionInvitePathMock.mockReset().mockResolvedValue("/speak/invite/tok-pub");
});
afterEach(cleanup);

function mount() {
  return render(
    <MemoryRouter>
      <PushesLane />
    </MemoryRouter>,
  );
}

describe("PushesLane — dual push dogfood surface", () => {
  it("shows honesty banner and both public + private panels", async () => {
    mount();
    expect(await screen.findByTestId("pushes-honesty-banner")).toBeTruthy();
    expect(screen.getByText(PUSHES_COPY.honestyBanner)).toBeTruthy();
    expect(screen.getByTestId("pushes-public-panel")).toBeTruthy();
    expect(screen.getByTestId("pushes-private-panel")).toBeTruthy();
    expect(screen.getByText(/uncle theo/i)).toBeTruthy();
    expect(screen.getByText(/aunt@x.com/i)).toBeTruthy();
  });

  it("re-ping calls API and does not invent ML claims", async () => {
    mount();
    await screen.findByTestId("reping-iv1");
    fireEvent.click(screen.getByTestId("reping-iv1"));
    await waitFor(() => expect(repingInviteeMock).toHaveBeenCalledWith("iv1"));
    // Honesty: banner still denies ML profile matching.
    expect(screen.getByText(/not ML profile matching/i)).toBeTruthy();
  });
});
