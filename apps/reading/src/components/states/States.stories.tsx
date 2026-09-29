import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "../lemon/LemonButton";
import { EmptyState, ErrorState, LoadingState } from "./index";

/**
 * The shared loading / empty / error states. Each story sits on a page-sized
 * surface in the page token so the day and night grounds read as they do in
 * the app.
 */
const meta = {
  title: "States / States",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function Surface({ children }: { children: React.ReactNode }) {
  return <div className="h-screen w-full bg-page text-1">{children}</div>;
}

export const LoadingList: Story = {
  render: () => (
    <Surface>
      <LoadingState label="Opening your research" />
    </Surface>
  ),
};

export const LoadingPage: Story = {
  render: () => (
    <Surface>
      <LoadingState label="Opening the book" shape="page" />
    </Surface>
  ),
};

export const Empty: Story = {
  render: () => (
    <Surface>
      <EmptyState
        title="No research yet"
        body="Ask a question and the research you start shows up here, running or finished."
        action={
          <LemonButton variant="primary" size="sm">
            Start a research
          </LemonButton>
        }
      />
    </Surface>
  ),
};

export const ErrorPage: Story = {
  render: () => (
    <Surface>
      <ErrorState
        title="Couldn't open this book"
        body="Your library and notes are unchanged. Check your connection, then try again."
        detail="Failed to fetch"
        onRetry={() => {}}
      />
    </Surface>
  ),
};

export const ErrorInline: Story = {
  render: () => (
    <Surface>
      <div className="mx-auto max-w-xl p-6">
        <ErrorState
          variant="inline"
          title="Couldn't start the research"
          body="Your question is still here, so you can send it again."
          detail="Submit failed: POST /investigations failed: HTTP 500"
          onRetry={() => {}}
        />
      </div>
    </Surface>
  ),
};
