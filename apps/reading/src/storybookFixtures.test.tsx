import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { composeStory } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import * as claimStories from "./components/ClaimCard.stories";
import * as roadmapStories from "./modes/Coordination/Coordination.stories";
import * as costStories from "./modes/Coordination/CostConsent.stories";
import * as synthesisStories from "./modes/ResearchWorkstation/MasterMdViewer.stories";

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => vi.stubGlobal("ResizeObserver", NoopResizeObserver));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const WithPassedGrounding = composeStory(
  claimStories.WithPassedGrounding,
  claimStories.default,
);
const WithFailedGrounding = composeStory(
  claimStories.WithFailedGrounding,
  claimStories.default,
);
const PendingGrounding = composeStory(
  claimStories.PendingGrounding,
  claimStories.default,
);
const SampleSynthesis = composeStory(
  synthesisStories.SampleSynthesis,
  synthesisStories.default,
);
const EmptySynthesis = composeStory(
  synthesisStories.Empty,
  synthesisStories.default,
);
const CanonicalRoadmap = composeStory(
  roadmapStories.CanonicalRoadmap,
  roadmapStories.default,
);
const CostFixture = composeStory(costStories.CostFixture, costStories.default);

it("renders the three grounding states from their Storybook fixtures", () => {
  const passed = render(<WithPassedGrounding />);
  expect(screen.getByText("✓ grounded")).toBeTruthy();
  passed.unmount();

  const failed = render(<WithFailedGrounding />);
  expect(screen.getByText("⚠ not located")).toBeTruthy();
  failed.unmount();

  render(<PendingGrounding />);
  expect(screen.getByText(/grounding check in flight/)).toBeTruthy();
});

it("renders both synthesis stories with the current parsed-synthesis contract", () => {
  const sample = render(
    <MemoryRouter>
      <SampleSynthesis />
    </MemoryRouter>,
  );
  expect(
    screen.getByText(
      "How do neutral-atom gate error rates compare at the 100-qubit scale?",
    ),
  ).toBeTruthy();
  sample.unmount();

  render(
    <MemoryRouter>
      <EmptySynthesis />
    </MemoryRouter>,
  );
  expect(screen.getByText("undetermined")).toBeTruthy();
});

it("renders the roadmap fixture as a roadmap story", () => {
  render(<CanonicalRoadmap />);
  expect(screen.getByRole("heading", { name: "Roadmap" })).toBeTruthy();
});

it("renders the cost fixture as an inference-cost story", () => {
  render(<CostFixture />);
  expect(screen.getByRole("heading", { name: "Inference cost" })).toBeTruthy();
});
