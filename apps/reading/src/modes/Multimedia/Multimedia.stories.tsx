import type { Meta, StoryObj } from "@storybook/react";

import type { MultimediaAssetList } from "../../api/multimedia";
import Multimedia from "./index";

const emptyList: MultimediaAssetList = { assets: [], count: 0 };

const loadEmpty = async () => emptyList;
const loadForever = () => new Promise<MultimediaAssetList>(() => {});
const loadFailure = async (): Promise<MultimediaAssetList> => {
  throw new Error("fixture transport unavailable");
};

const meta = {
  title: "Multimedia / Production Bay",
  component: Multimedia,
  render: (args) => <Multimedia {...args} executionEnabled={false} />,
  argTypes: { executionEnabled: { control: false, table: { disable: true } } },
  parameters: { layout: "fullscreen" },
  tags: ["autodocs", "a11y-audit"],
} satisfies Meta<typeof Multimedia>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ReadyEmpty: Story = {
  args: { loadAssets: loadEmpty },
};

export const Loading: Story = {
  args: { loadAssets: loadForever },
};

export const SafeFailure: Story = {
  args: { loadAssets: loadFailure },
};

export const Night: Story = {
  args: { loadAssets: loadEmpty },
  parameters: { backgrounds: { default: "dark" } },
};

export const Narrow: Story = {
  args: { loadAssets: loadEmpty },
  parameters: { viewport: { defaultViewport: "mobile1" } },
};
