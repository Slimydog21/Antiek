import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "@storybook/test";

import { FederationPolicyView, type FederationConfig } from "./index";

const strict: FederationConfig = { allowed_partner_substrates: [], require_opt_in_for_outbound_citations: true, require_attribution_for_outbound_citations: true };
const active: FederationConfig = { ...strict, allowed_partner_substrates: ["polar-archive", "research-coop"] };
const callbacks = { onDraftChange: fn(), onRequestSave: fn(), onConfirmSave: fn(), onCancelConfirm: fn(), onDiscard: fn(), onRetry: fn() };

const meta = { title: "Trust / Federation Airlock", component: FederationPolicyView, parameters: { layout: "fullscreen" }, tags: ["autodocs", "a11y-audit"], args: { ...callbacks, current: strict, draft: strict } } satisfies Meta<typeof FederationPolicyView>;
export default meta;
type Story = StoryObj<typeof meta>;

export const StrictDefault: Story = {};
export const ActivePassages: Story = { args: { current: active, draft: active } };
export const ExpandedRiskReview: Story = { args: { current: strict, draft: { ...strict, allowed_partner_substrates: ["research-coop"] }, confirmationOpen: true } };
export const RelaxedSafeguards: Story = { args: { current: strict, draft: { ...strict, require_opt_in_for_outbound_citations: false } } };
export const Loading: Story = { args: { current: null, draft: null, state: "loading" } };
export const SavePending: Story = { args: { current: strict, draft: active, state: "saving" } };
export const SaveFailureSafe: Story = { args: { current: strict, draft: active, state: "save-error" } };
export const MalformedResponse: Story = { args: { current: null, draft: null, state: "load-error" } };
export const LongPartnerList: Story = { args: { current: { ...strict, allowed_partner_substrates: Array.from({ length: 12 }, (_, index) => `research-partner-${index + 1}`) }, draft: { ...strict, allowed_partner_substrates: Array.from({ length: 12 }, (_, index) => `research-partner-${index + 1}`) } } };
export const Narrow: Story = { args: { current: active, draft: active }, parameters: { viewport: { defaultViewport: "mobile1" } } };
export const Night: Story = { args: { current: active, draft: active }, parameters: { backgrounds: { default: "dark" } } };
