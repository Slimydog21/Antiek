import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { ThreadBreadcrumb } from "./ThreadBreadcrumb";
import { ThreadJump } from "./ThreadJump";
import {
  findForkedHop,
  threadFromWire,
  type Thread,
  type ThreadHop,
} from "./threadModel";

const { navigateMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => navigateMock };
});

afterEach(() => {
  cleanup();
  navigateMock.mockReset();
});

const CANONICAL = "insight-thread-1";

function hop(workflow: ThreadHop["workflow"], opts: Partial<ThreadHop> = {}): ThreadHop {
  return {
    workflow,
    entityId: CANONICAL,
    entityKind: "insight_node",
    seamEventId: null,
    seamActionType: null,
    provenanceRef: null,
    built: true,
    viaProvisionalSeam: false,
    ...opts,
  };
}

function thread(hops: ThreadHop[]): Thread {
  return {
    canonicalEntityId: CANONICAL,
    canonicalEntityKind: "insight_node",
    isDegenerate: hops.length <= 1,
    hops,
    stubs: [],
  };
}

describe("threadModel", () => {
  it("normalizes the FastAPI wire shape and detects forked hops", () => {
    const model = threadFromWire({
      canonical_entity_id: CANONICAL,
      canonical_entity_kind: "insight_node",
      is_degenerate: false,
      hops: [
        {
          workflow: "research",
          entity_id: CANONICAL,
          entity_kind: "insight_node",
          seam_event_id: null,
          seam_action_type: null,
          provenance_ref: null,
          built: true,
          via_provisional_seam: false,
        },
        {
          workflow: "read",
          entity_id: `${CANONICAL}-COPY`,
          entity_kind: "insight_node",
          seam_event_id: "evt-fork",
          seam_action_type: "seam.research_to_read",
          provenance_ref: "evt-origin",
          built: true,
          via_provisional_seam: false,
        },
      ],
      stubs: [],
    });

    expect(model.canonicalEntityId).toBe(CANONICAL);
    expect(model.hops[1].seamEventId).toBe("evt-fork");
    expect(findForkedHop(model)).toBe(`${CANONICAL}-COPY`);
  });
});

describe("ThreadBreadcrumb", () => {
  it("renders a full thread, suppresses the current hop, and jumps from built hops", () => {
    const onJump = vi.fn();
    render(
      <ThreadBreadcrumb
        thread={thread([
          hop("research"),
          hop("read", {
            seamEventId: "evt-r2read",
            seamActionType: "seam.research_to_read",
          }),
          hop("write", {
            seamEventId: "evt-read2write",
            seamActionType: "seam.read_to_write",
          }),
        ])}
        onJump={onJump}
      />,
    );

    expect(screen.getByTestId("thread-breadcrumb")).toBeTruthy();
    fireEvent.click(screen.getByTestId("thread-hop-read"));
    expect(onJump).toHaveBeenCalledWith(
      expect.objectContaining({ workflow: "read", entityId: CANONICAL }),
    );
    expect(screen.getByTestId("thread-hop-current-write")).toBeTruthy();
  });

  it("shows an honest non-clickable stub for an unbuilt hop", () => {
    const onJump = vi.fn();
    render(
      <ThreadBreadcrumb
        thread={thread([
          hop("speak"),
          hop("write", {
            seamEventId: "evt-speak2write",
            seamActionType: "seam.speak_to_write",
            built: false,
          }),
        ])}
        onJump={onJump}
      />,
    );

    expect(screen.getByTestId("thread-hop-stub-write")).toBeTruthy();
    expect(screen.queryByTestId("thread-hop-write")).toBeNull();
    expect(onJump).not.toHaveBeenCalled();
  });

  it("refuses to render continuity for a forked thread", () => {
    render(
      <ThreadBreadcrumb
        thread={thread([
          hop("research"),
          hop("read", { entityId: `${CANONICAL}-COPY`, seamEventId: "evt-fork" }),
        ])}
      />,
    );

    expect(screen.getByTestId("thread-breadcrumb-integrity-warning")).toBeTruthy();
    expect(screen.queryByTestId("thread-breadcrumb")).toBeNull();
  });

  it("labels provisional seam hops", () => {
    render(
      <ThreadBreadcrumb
        thread={thread([
          hop("write"),
          hop("speak", {
            seamEventId: "evt-write2speak",
            seamActionType: "seam.write_to_speak",
            viaProvisionalSeam: true,
          }),
        ])}
        activeEntityId="not-current"
      />,
    );

    expect(screen.getByText("(provisional)")).toBeTruthy();
  });
});

describe("ThreadJump", () => {
  it("uses SPR-04 workflow IA when jumping to another built workflow", () => {
    const onOpenPanel = vi.fn();
    render(
      <MemoryRouter>
        <ThreadJump
          thread={thread([
            hop("research"),
            hop("read", {
              seamEventId: "evt-r2read",
              seamActionType: "seam.research_to_read",
            }),
            hop("write", {
              seamEventId: "evt-read2write",
              seamActionType: "seam.read_to_write",
            }),
          ])}
          onOpenPanel={onOpenPanel}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("thread-hop-read"));

    expect(navigateMock).toHaveBeenCalledWith("/library");
    expect(onOpenPanel).toHaveBeenCalledWith(
      expect.objectContaining({ workflow: "read", entityId: CANONICAL }),
    );
  });
});
