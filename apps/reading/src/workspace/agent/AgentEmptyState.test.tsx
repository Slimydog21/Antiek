/** AgentEmptyState.test.tsx — SPR-07 M7: three Antiek prompts, numbered 1/2/3. */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentEmptyState, CANNED_PROMPTS } from "./AgentEmptyState";

afterEach(cleanup);

describe("AgentEmptyState", () => {
  it("renders the three prompts in the Antiek wording and dispatches each with its number", () => {
    expect(CANNED_PROMPTS).toEqual([
      "What should I read next in this project?",
      "What is missing from this project's evidence?",
      "Where is this project's argument weakest?",
    ]);
    const onPrompt = vi.fn();
    const { getAllByRole } = render(<AgentEmptyState onPrompt={onPrompt} />);
    const buttons = getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(CANNED_PROMPTS.map((p, i) => `${i + 1}${p}`));
    fireEvent.click(buttons[1]);
    expect(onPrompt).toHaveBeenCalledWith(CANNED_PROMPTS[1], 2);
  });
});
