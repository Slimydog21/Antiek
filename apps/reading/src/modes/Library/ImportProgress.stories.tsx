// SPR-06 / M6 — Storybook: ImportProgress phases.
//
// One story per real backend phase. The grid orders them so a
// designer can scan the progression top-to-bottom. The "Failed"
// story exercises the humanizeError mapping.

import type { Meta, StoryObj } from "@storybook/react";

import { ImportProgress } from "./ImportProgress";
import type { IngestJob } from "../../../api/library/types";

const meta = {
  title: "Library / ImportProgress",
  component: ImportProgress,
  parameters: {
    layout: "centered",
  },
  decorators: [
    (Story) => (
      <div style={{ width: 480 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ImportProgress>;

export default meta;
type Story = StoryObj<typeof meta>;

function buildJob(overrides: Partial<IngestJob>): IngestJob {
  return {
    job_id: "job-fixture",
    url: "https://example.com",
    user_id: "__operator__",
    investigation_id: "__operator__",
    status: "pending",
    content_type: null,
    document_id: null,
    error: null,
    error_detail: null,
    attempts: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    metadata: {},
    ...overrides,
  };
}

export const Pending: Story = {
  args: { job: buildJob({ status: "pending" }) },
};

export const Fetching: Story = {
  args: { job: buildJob({ status: "running", content_type: null }) },
};

export const Extracting: Story = {
  args: {
    job: buildJob({ status: "running", content_type: "html_article" }),
  },
};

export const Ready: Story = {
  args: {
    job: buildJob({
      status: "succeeded",
      content_type: "html_article",
      document_id: "doc-url-abc123",
    }),
  },
};

export const FailedDomainBanned: Story = {
  args: {
    job: buildJob({
      status: "failed",
      content_type: null,
      error: "domain_banned",
      error_detail: "banned until 2026-05-22",
    }),
  },
};

export const FailedLowWordCount: Story = {
  args: {
    job: buildJob({
      status: "failed",
      content_type: "html_article",
      error: "low_word_count",
      error_detail: "Extracted 12 words",
    }),
  },
};
