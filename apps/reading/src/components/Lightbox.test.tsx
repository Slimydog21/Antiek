import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import Lightbox from "./Lightbox";

afterEach(() => cleanup());

describe("Lightbox", () => {
  it("trims and renders safe image sources", () => {
    render(<Lightbox src=" https://img.example/notebook.png " alt="Notebook" />);

    const img = screen.getByRole("img", { name: "Notebook" });
    expect(img.getAttribute("src")).toBe("https://img.example/notebook.png");
  });

  it.each(["javascript:alert(1)", "data:text/html,owned", "/relative/image.png"])(
    "does not render unsafe image sources: %s",
    (src) => {
      render(<Lightbox src={src} alt="Unsafe" />);

      expect(screen.queryByRole("img")).toBeNull();
      expect(screen.getByText("Lightbox opened without a src.")).toBeTruthy();
    },
  );
});
