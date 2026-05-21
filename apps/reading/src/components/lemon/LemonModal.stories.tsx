import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import LemonButton from "./LemonButton";
import LemonInput from "./LemonInput";
import LemonModal from "./LemonModal";

const meta = {
  title: "Lemon / Modal",
  component: LemonModal,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => {
    const Inner = () => {
      const [open, setOpen] = useState(false);
      return (
        <div className="p-12">
          <LemonButton variant="primary" onClick={() => setOpen(true)}>
            Open modal
          </LemonButton>
          <LemonModal
            open={open}
            onClose={() => setOpen(false)}
            title="Confirm shutdown"
            footer={
              <div className="flex justify-end gap-2">
                <LemonButton variant="tertiary" onClick={() => setOpen(false)}>
                  Cancel
                </LemonButton>
                <LemonButton variant="danger" onClick={() => setOpen(false)}>
                  Shut down
                </LemonButton>
              </div>
            }
          >
            <p className="text-sm text-shadow-1 dark:text-starlight">
              The investigation is still streaming events. Shutting down now
              will cancel the in-flight chain. ESC, click-outside, or Cancel
              to dismiss.
            </p>
          </LemonModal>
        </div>
      );
    };
    return <Inner />;
  },
};

export const Sizes: Story = {
  render: () => {
    const Inner = () => {
      const [size, setSize] = useState<"sm" | "md" | "lg" | "full" | null>(null);
      return (
        <div className="p-12 flex gap-3">
          {(["sm", "md", "lg", "full"] as const).map((s) => (
            <LemonButton key={s} onClick={() => setSize(s)}>
              {s}
            </LemonButton>
          ))}
          {size && (
            <LemonModal
              open
              onClose={() => setSize(null)}
              title={`Size: ${size}`}
              size={size}
            >
              <p>Modal at size {size}.</p>
            </LemonModal>
          )}
        </div>
      );
    };
    return <Inner />;
  },
};

export const WithForm: Story = {
  render: () => {
    const Inner = () => {
      const [open, setOpen] = useState(true);
      return (
        <div className="p-12">
          <LemonModal
            open={open}
            onClose={() => setOpen(false)}
            title="New investigation"
            footer={
              <div className="flex justify-end gap-2">
                <LemonButton variant="tertiary" onClick={() => setOpen(false)}>
                  Cancel
                </LemonButton>
                <LemonButton variant="primary" onClick={() => setOpen(false)}>
                  Start
                </LemonButton>
              </div>
            }
          >
            <div className="space-y-3">
              <label className="block text-xs font-mono uppercase tracking-wider">
                Question
              </label>
              <LemonInput placeholder="What do you want to research?" />
            </div>
          </LemonModal>
        </div>
      );
    };
    return <Inner />;
  },
};
