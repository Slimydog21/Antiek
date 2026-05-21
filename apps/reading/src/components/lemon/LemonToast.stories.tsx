import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "./LemonButton";
import { LemonToastViewport, toast } from "./LemonToast";

const meta = {
  title: "Lemon / Toast",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {
  render: () => (
    <>
      <LemonToastViewport />
      <div className="p-12 flex flex-wrap gap-3">
        <LemonButton variant="primary" onClick={() => toast.ok("Investigation saved.")}>
          toast.ok
        </LemonButton>
        <LemonButton onClick={() => toast.warn("Popups blocked. Allow popups for this site.")}>
          toast.warn
        </LemonButton>
        <LemonButton variant="danger" onClick={() => toast.err("Network error: substrate unreachable.")}>
          toast.err
        </LemonButton>
        <LemonButton variant="tertiary" onClick={() => toast.info("Generating thumbnail…")}>
          toast.info
        </LemonButton>
        <LemonButton variant="tertiary" onClick={() => {
          toast.ok("First");
          toast.warn("Second");
          toast.err("Third");
          toast.info("Fourth");
        }}>
          Queue four at once
        </LemonButton>
      </div>
      <p className="px-12 text-sm text-shadow-1 dark:text-moonlight max-w-xl">
        Toasts stack top-right. Auto-dismiss after their ttl (ok: 4s, warn: 6s,
        err: 8s, info: 4s). Click ✕ to dismiss early.
      </p>
    </>
  ),
};
