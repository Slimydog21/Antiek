import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "@storybook/test";

import { BillingView, type BillingSummary, type BillingViewProps } from "./index";

/**
 * Billing Usage Observatory — event-derived billable estimate view.
 *
 * NOT an invoice, charged amount, settled amount, API-key budget, or
 * full provider ledger. Pure BillingView stories for every observable
 * state: ready, empty, loading, failure, invalid input, malformed
 * payload, narrow, night, and long values.
 *
 * Every story carries the a11y-audit tag for automated accessibility
 * checks.
 */

const fullSummary: BillingSummary = {
  user_id: "__operator__",
  period: "2026-07",
  free_tokens_consumed: 0,
  free_tokens_remaining: 5_000_000,
  paid_public_token_cost_usd: "0.00",
  paid_public_margin_usd: "0.00",
  paid_private_token_cost_usd: "12.50",
  paid_private_margin_usd: "6.25",
  total_raw_usd: "12.50",
  total_margin_usd: "6.25",
  total_billable_usd: "18.75",
  record_count: 42,
};

const emptySummary: BillingSummary = {
  user_id: "__operator__",
  period: "2026-01",
  free_tokens_consumed: 0,
  free_tokens_remaining: 5_000_000,
  paid_public_token_cost_usd: "0.00",
  paid_public_margin_usd: "0.00",
  paid_private_token_cost_usd: "0.00",
  paid_private_margin_usd: "0.00",
  total_raw_usd: "0.00",
  total_margin_usd: "0.00",
  total_billable_usd: "0.00",
  record_count: 0,
};

const longValuesSummary: BillingSummary = {
  user_id: "__operator__",
  period: "2026-12",
  free_tokens_consumed: 0,
  free_tokens_remaining: 5_000_000,
  paid_public_token_cost_usd: "0.00",
  paid_public_margin_usd: "0.00",
  paid_private_token_cost_usd: "99999.99",
  paid_private_margin_usd: "49999.995",
  total_raw_usd: "99999.99",
  total_margin_usd: "49999.995",
  total_billable_usd: "149999.985",
  record_count: 999999,
};

const callbacks: Pick<
  BillingViewProps,
  "onUserIdChange" | "onPeriodChange" | "onApply" | "onRetry"
> = {
  onUserIdChange: fn(),
  onPeriodChange: fn(),
  onApply: fn(),
  onRetry: fn(),
};

const meta = {
  title: "Trust / Billing Usage Observatory",
  component: BillingView,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs", "a11y-audit"],
  args: {
    state: "ready",
    userId: "__operator__",
    period: "2026-07",
    data: fullSummary,
    userIdError: null,
    periodError: null,
    ...callbacks,
  },
} satisfies Meta<typeof BillingView>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default: operator view with 42 records. */
export const Ready: Story = {};

/** Empty: legitimate empty result (not an error). */
export const Empty: Story = {
  args: {
    state: "empty",
    data: emptySummary,
    period: "2026-01",
  },
};

/** Loading: aggregation in progress. */
export const Loading: Story = {
  args: {
    state: "loading",
    data: null,
  },
};

/** Failure: backend unavailable. Raw errors are never rendered. */
export const Failure: Story = {
  args: {
    state: "error",
    data: null,
  },
};

/** Idle: waiting for user to submit. */
export const Idle: Story = {
  args: {
    state: "idle",
    data: null,
  },
};

/** Invalid input: bad period format. */
export const InvalidPeriod: Story = {
  args: {
    state: "idle",
    period: "not-a-date",
    periodError: "Use YYYY-MM format (e.g. 2026-07)",
    data: null,
  },
};

/** Invalid input: empty user ID. */
export const InvalidUserId: Story = {
  args: {
    state: "idle",
    userId: "",
    userIdError: "User ID is required",
    data: null,
  },
};

/** Malformed payload: not rendered (error state shown instead). */
export const MalformedPayload: Story = {
  args: {
    state: "error",
    data: null,
  },
};

/** Narrow viewport: responsive layout. */
export const Narrow: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile1" },
  },
};

/** Night mode: dark theme. */
export const Night: Story = {
  args: {
    fixtureTheme: "dark",
  },
  parameters: {
    backgrounds: { default: "dark" },
  },
};

/** Long values: large amounts and long identifiers. */
export const LongValues: Story = {
  args: {
    data: longValuesSummary,
    userId: longValuesSummary.user_id,
    period: longValuesSummary.period,
  },
};
