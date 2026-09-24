import type { Meta, StoryObj } from "@storybook/react";

import LemonButton from "./LemonButton";
import { LemonDropdown, LemonMenuItem } from "./LemonDropdown";

const meta = {
  title: "Lemon / Dropdown",
  component: LemonDropdown,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonDropdown>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PanelActions: Story = {
  render: () => (
    <div className="p-6">
      <LemonDropdown trigger={<LemonButton variant="tertiary">⋯</LemonButton>}>
        {({ close }) => (
          <>
            <LemonMenuItem icon="◧" onClick={() => { alert("dock left"); close(); }}>
              Dock left
            </LemonMenuItem>
            <LemonMenuItem icon="◨" onClick={() => { alert("dock right"); close(); }}>
              Dock right
            </LemonMenuItem>
            <LemonMenuItem icon="▢" onClick={() => { alert("float"); close(); }}>
              Float
            </LemonMenuItem>
            <LemonMenuItem icon="↗" onClick={() => { alert("popout"); close(); }}>
              Pop out
            </LemonMenuItem>
            <div className="my-1 border-t border-rule dark:border-charcoal-1" />
            <LemonMenuItem icon="✕" onClick={() => { alert("close"); close(); }}>
              Close panel
            </LemonMenuItem>
          </>
        )}
      </LemonDropdown>
    </div>
  ),
};

export const AlignRight: Story = {
  render: () => (
    <div className="p-6 flex justify-end">
      <LemonDropdown trigger={<LemonButton>Open right-aligned</LemonButton>} align="below-right">
        {({ close }) => (
          <>
            <LemonMenuItem onClick={() => close()}>Profile</LemonMenuItem>
            <LemonMenuItem onClick={() => close()}>Settings</LemonMenuItem>
            <div className="my-1 border-t border-rule dark:border-charcoal-1" />
            <LemonMenuItem onClick={() => close()}>Sign out</LemonMenuItem>
          </>
        )}
      </LemonDropdown>
    </div>
  ),
};

// A model picker's shape: one item cannot be used yet and says why. It stays
// reachable with the arrow keys (Enter on the trigger, then ArrowDown).
export const WithDisabledItem: Story = {
  render: () => (
    <div className="p-6 pb-48">
      <LemonDropdown trigger={<LemonButton>Model</LemonButton>}>
        {({ close }) => (
          <>
            <LemonMenuItem onClick={() => close()}>House route</LemonMenuItem>
            <LemonMenuItem onClick={() => close()} disabledReason="No key for this provider yet">
              Claude via your key
            </LemonMenuItem>
            <LemonMenuItem onClick={() => close()}>DeepSeek via your key</LemonMenuItem>
          </>
        )}
      </LemonDropdown>
    </div>
  ),
};
