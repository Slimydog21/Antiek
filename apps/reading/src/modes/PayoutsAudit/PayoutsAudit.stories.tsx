import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "@storybook/test";

import { PayoutAuditView, type PayoutRow } from "./index";

const row = (status: string, amount: number, index: number, overrides: Partial<PayoutRow> = {}): PayoutRow => ({ transfer_attempt_id: `xfer-${index}`, decision_id: `decision-${index}`, stripe_transfer_id: status === "transferred" ? `tr_${index}` : null, recipient_account_id: status === "skipped_platform" ? null : `acct_${index}`, amount_usd_cents: amount, status, note: null, initiated_at: `2026-07-${String(10 + index).padStart(2, "0")}T09:30:00Z`, ...overrides });
const rows = [row("transferred", 12500, 1), row("skipped_escrow", 6400, 2), row("skipped_platform", 3100, 3), row("failed", 8700, 4), row("pending", 2200, 5)];
const callbacks = { onFilterChange: fn(), onRecipientChange: fn(), onApply: fn(), onClear: fn(), onRetry: fn() };
const meta = { title: "Trust / Payout Signal House", component: PayoutAuditView, parameters: { layout: "fullscreen" }, tags: ["autodocs", "a11y-audit"], args: { rows, filter: "all", recipientFilter: "", ...callbacks } } satisfies Meta<typeof PayoutAuditView>;
export default meta;
type Story = StoryObj<typeof meta>;

export const RecordedOutcomes: Story = {};
export const FilteredRecipient: Story = { args: { filter: "transferred", recipientFilter: "acct_1", applied: true, rows: [rows[0]] } };
export const EmptyAmbiguous: Story = { args: { rows: [] } };
export const Loading: Story = { args: { rows: [], state: "loading" } };
export const SafeFailure: Story = { args: { rows: [], state: "error" } };
export const UnknownStatus: Story = { args: { rows: [row("future_state", 4900, 7)] } };
export const InvalidTime: Story = { args: { rows: [row("transferred", 12500, 8, { initiated_at: "not-a-time" })] } };
export const LongIdentifiers: Story = { args: { rows: [row("transferred", 12500, 9, { recipient_account_id: "acct_" + "polar-research-collective-".repeat(8), decision_id: "decision-" + "x".repeat(150) })] } };
export const CapReached: Story = { args: { rows: Array.from({ length: 500 }, (_, index) => row(index % 2 ? "transferred" : "skipped_escrow", 100 + index, index)) } };
export const Narrow: Story = { parameters: { viewport: { defaultViewport: "mobile1" } } };
export const Night: Story = { parameters: { backgrounds: { default: "dark" } } };
