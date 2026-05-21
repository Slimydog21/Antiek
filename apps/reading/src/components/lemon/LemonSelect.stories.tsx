import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import LemonSelect from "./LemonSelect";

const meta = {
  title: "Lemon / Select",
  component: LemonSelect,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof LemonSelect>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ModelPicker: Story = {
  render: () => {
    const Inner = () => {
      const [v, setV] = useState<string | null>("flux-1-dev");
      return (
        <div className="p-6">
          <LemonSelect<string>
            value={v}
            onChange={setV}
            options={[
              { value: "flux-1-dev", label: "FLUX 1 dev" },
              { value: "imagen-4", label: "Imagen 4" },
              { value: "imagen-4-ultra", label: "Imagen 4 Ultra" },
              { value: "nano-banana", label: "Nano Banana (Gemini)" },
              { value: "ideogram-3", label: "Ideogram v3", disabled: true },
            ]}
          />
        </div>
      );
    };
    return <Inner />;
  },
};

export const FullWidth: Story = {
  render: () => {
    const Inner = () => {
      const [v, setV] = useState<number | null>(2);
      return (
        <div className="p-6 max-w-md">
          <LemonSelect<number>
            value={v}
            onChange={setV}
            fullWidth
            sizing="lg"
            options={[
              { value: 1, label: "Tier 1 — operator-facing" },
              { value: 2, label: "Tier 2 — workflow surfaces" },
              { value: 3, label: "Tier 3 — governance + meta" },
              { value: 4, label: "Tier 4 — experimental" },
            ]}
          />
        </div>
      );
    };
    return <Inner />;
  },
};

export const Placeholder: Story = {
  render: () => {
    const Inner = () => {
      const [v, setV] = useState<string | null>(null);
      return (
        <div className="p-6">
          <LemonSelect<string>
            value={v}
            onChange={setV}
            placeholder="Pick an investigation…"
            options={[
              { value: "nvda-q4", label: "NVDA Q4 risk model" },
              { value: "web-gaming-2026", label: "Web gaming 2026" },
              { value: "kalshi", label: "Kalshi liquidity gate" },
            ]}
          />
        </div>
      );
    };
    return <Inner />;
  },
};
