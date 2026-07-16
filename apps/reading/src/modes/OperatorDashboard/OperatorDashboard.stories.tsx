import type { Meta, StoryObj } from "@storybook/react";
import OperatorDashboard from "./index";
import type { PublisherSummary } from "./index";

const publishers: PublisherSummary[] = [
  {
    ip_holder_id: "ip-mit",
    display_name: "MIT Press",
    legal_contact_email: "permissions@mit.edu",
    status: "pre_onboarded",
    escrow_balance_usd: "0.00",
    notification_sent_at: null,
    claimed_at: null,
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-penguin",
    display_name: "Penguin",
    legal_contact_email: null,
    status: "invited",
    escrow_balance_usd: "87.60",
    notification_sent_at: "2026-06-01",
    claimed_at: null,
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-princeton",
    display_name: "Princeton University Press",
    legal_contact_email: "rights@example.test",
    status: "pre_onboarded",
    escrow_balance_usd: "14.00",
    notification_sent_at: null,
    claimed_at: null,
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-cambridge",
    display_name: "Cambridge University Press",
    legal_contact_email: null,
    status: "claimed",
    escrow_balance_usd: "22.00",
    notification_sent_at: "2026-05-15",
    claimed_at: "2026-06-10",
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-oup",
    display_name: "Oxford University Press",
    legal_contact_email: null,
    status: "opted_out",
    escrow_balance_usd: "0.00",
    notification_sent_at: "2026-05-20",
    claimed_at: null,
    opted_out_at: "2026-07-01",
  },
];

const completeStats = {
  counts: {
    investigations: 100,
    notebooks: 10,
    outcomes: 5,
    skill_rules: 2,
    payout_transfers: 2,
    ip_holders: 2,
  },
  warnings: [],
};

const meta = {
  title: "Modes/Operator Watch Room",
  component: OperatorDashboard,
  parameters: { layout: "fullscreen" },
  args: {
    executionEnabled: false,
    initialPublishers: publishers,
    initialSnapshot: {
      stats: completeStats,
      pendingDeletions: 3,
      recentPayouts: [
        { status: "completed", amount_usd_cents: 1240, initiated_at: "2026-07-01" },
        { status: "pending", amount_usd_cents: 875, initiated_at: "2026-07-10" },
      ],
    },
    initialLoading: false,
    initialError: false,
    initialNotifyingId: null,
  },
} satisfies Meta<typeof OperatorDashboard>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Populated: Story = {};

export const Partial: Story = {
  args: {
    initialSnapshot: {
      stats: null,
      pendingDeletions: null,
      recentPayouts: null,
    },
  },
};

export const SafeFailure: Story = {
  args: {
    initialPublishers: [],
    initialSnapshot: {
      stats: null,
      pendingDeletions: null,
      recentPayouts: null,
    },
    initialError: true,
  },
};

export const Empty: Story = {
  args: {
    initialPublishers: [],
    initialSnapshot: {
      stats: { counts: {}, warnings: [] },
      pendingDeletions: 0,
      recentPayouts: [],
    },
  },
};

export const Notifying: Story = {
  args: {
    initialNotifyingId: "ip-mit",
  },
};

export const Loading: Story = {
  args: {
    initialPublishers: null,
    initialSnapshot: {
      stats: null,
      pendingDeletions: null,
      recentPayouts: null,
    },
    initialLoading: true,
  },
};

export const Night: Story = {
  render: (args) => <div className="dark"><OperatorDashboard {...args} /></div>,
  parameters: {
    backgrounds: { default: "dark" },
  },
};

export const Narrow: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile1" },
  },
};
