import type { Meta, StoryObj } from "@storybook/react";

import { EvidenceBriefing } from "./DerivedRevisionCompanion";

const passage = {
  citation_id: `dchunk_${"d".repeat(64)}`,
  chunk_ordinal: 0,
  member_index: 0,
  section_anchor: "bypass-ratio",
  section_path: "Propulsion / Turbofans",
  text: "A higher bypass ratio moves more air around the engine core, improving propulsive efficiency at subsonic cruise speeds.",
  text_sha256: "e".repeat(64),
};

const meta = {
  title: "Reading/Derived evidence briefing",
  component: EvidenceBriefing,
  decorators: [(Story) => <div className="min-h-screen w-80 bg-ice-1 p-4 dark:bg-charcoal-2"><Story /></div>],
  args: {
    briefing: {
      schema_version: "antiek.derived-evidence-briefing.v1",
      question: "Why did high-bypass turbofans replace turbojets on airliners?",
      question_sha256: "a".repeat(64),
      derived_asset_id: `ast_${"b".repeat(32)}`,
      revision_id: `rev_${"c".repeat(32)}`,
      content_sha256: "d".repeat(64),
      generation: 4,
      evidence_pack_sha256: "e".repeat(64),
      section_count: 2,
      passage_count: 2,
      sections: [
        { section_path: passage.section_path, passages: [passage] },
        { section_path: "Economics / Airline operations", passages: [{
          ...passage,
          citation_id: `dchunk_${"f".repeat(64)}`,
          chunk_ordinal: 1,
          section_anchor: "fuel-economics",
          section_path: "Economics / Airline operations",
          text: "Lower fuel burn and reduced community noise changed both route economics and airport operating constraints.",
        }] },
      ],
      briefing_json_sha256: "1".repeat(64),
      briefing_html: "",
      briefing_html_sha256: "2".repeat(64),
      artifact_sha256: "3".repeat(64),
    },
    showCitation: () => undefined,
    onFollowCitation: () => undefined,
  },
} satisfies Meta<typeof EvidenceBriefing>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Ready: Story = {};
