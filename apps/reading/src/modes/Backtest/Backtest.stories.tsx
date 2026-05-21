import type { Meta, StoryObj } from "@storybook/react";

import Backtest from "./index";

/**
 * Backtest report page — surfaces middleware/backtest/analysis.py's
 * BacktestReport via GET /backtest/{synthesis_id} (master-spec §13.8).
 *
 * Storybook renders the page in its loading/error state (no
 * backend). The page chrome — synthesis header card, 6 metric
 * tiles, three detail-list sections, cross-link to /outcomes —
 * is documented in the unit tests at
 * test_api_backtest_endpoint.py.
 */
const meta = {
  title: "Trust / Backtest",
  component: Backtest,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Backtest>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
