import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import {
  CalibrationObservatoryFrame,
  type OutcomeRow,
} from "./index";

const OUTCOMES: OutcomeRow[] = [
  {
    outcome_id: "outcome-aurora-01",
    synthesis_id: "synthesis-market-signals",
    observer: "__operator__",
    observed_at: "2026-07-14 · 21:40",
  },
  {
    outcome_id: "outcome-prism-02",
    synthesis_id: "synthesis-model-routing",
    observer: "__researcher__",
    observed_at: "2026-07-13 · 08:15",
  },
  {
    outcome_id: "outcome-compass-03",
    synthesis_id: "synthesis-reading-cognition",
    observer: "__operator__",
    observed_at: "2026-07-11 · 18:44",
  },
];

interface FixtureProps {
  rows?: OutcomeRow[];
  loading?: boolean;
  error?: boolean;
  initialFilter?: string;
  productionArt?: boolean;
  shellHeight?: string;
}

function Fixture({
  rows = [],
  loading = false,
  error = false,
  initialFilter = "",
  productionArt = false,
  shellHeight = "100vh",
}: FixtureProps) {
  const [filter, setFilter] = useState(initialFilter);
  return (
    <div style={{ height: shellHeight }}>
      <CalibrationObservatoryFrame
        rows={rows}
        loading={loading}
        error={error}
        observerFilter={filter}
        onObserverFilterChange={setFilter}
        onRetry={() => undefined}
        onOpenSynthesis={() => undefined}
        fixture={!productionArt}
      />
    </div>
  );
}

const meta = {
  title: "Trust / Calibration Observatory",
  component: Fixture,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof Fixture>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Loading: Story = { args: { loading: true } };
export const Empty: Story = { args: {} };
export const Populated: Story = { args: { rows: OUTCOMES } };
export const Filtered: Story = {
  args: {
    rows: OUTCOMES.filter((row) => row.observer === "__operator__"),
    initialFilter: "__operator__",
  },
};
export const PrivateSafeFailure: Story = { args: { error: true } };
export const LongIdentifiers: Story = {
  args: {
    rows: [
      {
        outcome_id: "outcome-with-a-long-stable-identity-001",
        synthesis_id:
          "synthesis-a-deliberately-long-identifier-that-tests-table-containment",
        observer: "__operator_with_a_long_identifier__",
        observed_at: "2026-07-14T21:40:18.492Z",
      },
    ],
  },
};
export const ShellConstrainedLongRecord: Story = {
  args: {
    rows: Array.from({ length: 30 }, (_, index) => ({
      outcome_id: `outcome-${String(index).padStart(2, "0")}`,
      synthesis_id: `synthesis-${String(index).padStart(2, "0")}`,
      observer: "__operator__",
      observed_at: "2026-07-16 · 10:30",
    })),
    shellHeight: "320px",
  },
};
export const ProductionRaster: Story = {
  args: { rows: OUTCOMES, productionArt: true },
};
