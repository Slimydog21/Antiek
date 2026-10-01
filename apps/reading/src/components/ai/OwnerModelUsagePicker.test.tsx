import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("../../lib/posthogClient", () => ({
  posthogEnabled: false,
  posthog: { identify: vi.fn(), reset: vi.fn() },
}));
vi.mock("../../hooks/useReadingState", () => ({
  setReadingStateOwner: vi.fn(),
}));
vi.mock("../../modes/Write/sectionProseOwner", () => ({
  setSectionProseOwner: vi.fn(),
  suspendSectionProseDispatch: vi.fn(),
}));
import { AuthProvider, useAuth, type AuthContextValue } from "../../lib/auth";
import {
  useOwnerModelController,
  type OwnerModelController,
} from "../../hooks/useOwnerModelController";
import type { UserModelRow } from "../../api/settingsModels";
import type { SettingsUsageKeyEntry } from "../../api/settingsUsage";
import Picker from "./OwnerModelUsagePicker";
import type ModelUsagePickerView from "./ModelUsagePickerView";
const capturedView = vi.hoisted<{
  props: Parameters<typeof ModelUsagePickerView>[0] | null;
}>(() => ({ props: null }));
vi.mock("./ModelUsagePickerView", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./ModelUsagePickerView")>();
  const { createElement } = await import("react");
  return {
    ...actual,
    default: (props: Parameters<typeof ModelUsagePickerView>[0]) => {
      capturedView.props = props;
      return createElement(actual.default, props);
    },
  };
});
let resourceCurrent: (() => boolean) | undefined;
let auth: AuthContextValue;
let controller: OwnerModelController;
let owner: string;
let rows: UserModelRow[];
let usage: SettingsUsageKeyEntry[];
let paths: string[];
let modelsRead: (() => Promise<Response>) | null = null;
let balanceBody: (id: string) => unknown;
let balanceRead: ((id: string) => Promise<Response>) | null;
const base: UserModelRow = {
  id: "key-0",
  provider_kind: "openai_compat",
  provider_catalog_id: "deepseek",
  model_id: "primary",
  model_ids: ["primary", "secondary", "secondary"],
  display_name: "Fixture key",
  base_url: null,
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
  pricing_status: "known",
  hard_ceiling_eligible: true,
  execution_status: "executable",
  rate_snapshot: null,
};
const json = (value: unknown) => new Response(JSON.stringify(value));
function body(id: string) {
  return {
    api_key_id: id,
    catalog_id: "deepseek",
    kind: "balance_native",
    balance_usd: 0.0031,
    granted_usd: null,
    spend_usd: null,
    budget_usd: null,
    utilization: null,
    window_label: null,
    resets_at: null,
    note: null,
    held_cents: 0,
    available_cents: null,
  };
}
function Probe() {
  auth = useAuth();
  controller = useOwnerModelController({
    operationPrefix: "fixture",
    policy: "strict-owner",
    allowHouse: true,
  });
  return (
    <Picker
      controller={controller}
      {...{ isResourceCurrent: resourceCurrent }}
      allowHouse
      triggerAriaLabel="Choose fixture model"
    />
  );
}
beforeEach(() => {
  modelsRead = null;
  resourceCurrent = undefined;
  capturedView.props = null;
  owner = "a";
  rows = [{ ...base }];
  usage = [
    {
      api_key_id: "key-0",
      used_cents: 1,
      limit_cents: 0,
      remaining_cents: -1,
      held_cents: 2,
      available_cents: -3,
    },
  ];
  paths = [];
  balanceBody = body;
  balanceRead = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(String(input), "http://fixture").pathname;
      paths.push(path);
      if (path === "/auth/me")
        return json({
          user_id: owner,
          email: null,
          auth_method: "antiek_session_cookie",
        });
      if (path === "/settings/models/user")
        return modelsRead
          ? modelsRead()
          : json({
              models: rows,
              count: rows.length,
              stale_registered: [],
              source: "fixture",
            });
      if (path === "/settings/usage")
        return json({ keys: usage, count: usage.length });
      if (path.startsWith("/settings/balance/")) {
        const id = decodeURIComponent(path.slice("/settings/balance/".length));
        return balanceRead ? balanceRead(id) : json(balanceBody(id));
      }
      throw new Error("fixture route denied");
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function mount() {
  const view = render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
  return view;
}
async function open() {
  const button = await screen.findByRole("button", { name: "Choose fixture model" });
  await waitFor(() => expect(button.hasAttribute("disabled")).toBe(false));
  fireEvent.click(button);
}
describe("mandatory scoped model usage picker", () => {
  it("has one inventory authority, exact variant selection and honest zero/held/precision labels", async () => {
    await mount();
    await open();
    await screen.findByText(/cap \$0.00/);
    expect(document.body.textContent).toContain("held $0.02");
    expect(document.body.textContent).toContain("available $-0.03");
    await screen.findByText("Provider-reported credit $0.0031");
    expect(screen.getByText("Default (house route)").className).not.toContain(
      "font-semibold",
    );
    fireEvent.click(screen.getByText("secondary"));
    expect(controller.selection).toEqual({
      kind: "saved",
      recordId: "key-0",
      modelId: "secondary",
    });
    expect(
      screen.getByRole("button", { name: "Choose fixture model" }).textContent,
    ).toContain("secondary");
    await open();
    expect(screen.getByText("secondary").className).toContain("font-semibold");
    expect(
      paths.filter((path) => path === "/settings/models/user"),
    ).toHaveLength(1);
    expect(
      paths.filter((path) => path.startsWith("/settings/balance/")),
    ).toHaveLength(1);
  });
  it.each(["duplicate", "foreign", "absent"])(
    "does not turn %s usage into uncapped",
    async (kind) => {
      usage =
        kind === "duplicate"
          ? [usage[0], usage[0]]
          : kind === "foreign"
            ? [{ ...usage[0], api_key_id: "foreign" }]
            : [];
      await mount();
      await open();
      await screen.findByText(
        kind === "absent"
          ? "Usage unavailable (no entry)"
          : "Usage unavailable",
      );
      expect(document.body.textContent).not.toContain("uncapped");
    },
  );
  it.each(["record", "catalog"])(
    "refuses mismatched balance %s without removing model choice",
    async (kind) => {
      balanceBody = (id) => ({
        ...body(id),
        ...(kind === "record"
          ? { api_key_id: "foreign" }
          : { catalog_id: "other" }),
      });
      await mount();
      await open();
      await screen.findByText("Provider balance unavailable");
      fireEvent.click(screen.getByText("secondary"));
      expect(controller.selection.kind).toBe("saved");
    },
  );
  it("fetches six unique keys eagerly, remaining only on actual menu mount, and all on refresh", async () => {
    rows = Array.from({ length: 8 }, (_, i) => ({
      ...base,
      id: `key-${i}`,
      display_name: `Fixture ${i}`,
    }));
    usage = [];
    await mount();
    await waitFor(() =>
      expect(
        paths.filter((path) => path.startsWith("/settings/balance/")),
      ).toHaveLength(6),
    );
    await open();
    await waitFor(() =>
      expect(
        paths.filter((path) => path.startsWith("/settings/balance/")),
      ).toHaveLength(8),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh model usage" }),
    );
    await waitFor(() =>
      expect(
        paths.filter((path) => path.startsWith("/settings/balance/")),
      ).toHaveLength(16),
    );
    expect(
      paths.filter((path) => path === "/settings/models/user"),
    ).toHaveLength(2);
  });
  it("preserves physical slots across owner retirement and picker unmount/remount", async () => {
    rows = Array.from({ length: 3 }, (_, i) => ({ ...base, id: `key-${i}` }));
    usage = [];
    const pending: { id: string; resolve: (value: Response) => void }[] = [];
    let live = 0;
    let peak = 0;
    balanceRead = (id) => {
      live++;
      peak = Math.max(peak, live);
      return new Promise<Response>((resolve) =>
        pending.push({
          id,
          resolve: (value) => {
            live--;
            resolve(value);
          },
        }),
      );
    };
    const first = await mount();
    await waitFor(() => expect(pending).toHaveLength(2));
    first.unmount();
    owner = "b";
    await mount();
    expect(pending).toHaveLength(2);
    await act(async () => {
      pending[0].resolve(json({ ...body(pending[0].id), balance_usd: 999 }));
    });
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(peak).toBe(2);
    await act(async () => {
      pending[1].resolve(json(body(pending[1].id)));
    });
    await waitFor(() => expect(pending).toHaveLength(4));
    await act(async () => {
      pending[2].resolve(json(body(pending[2].id)));
      pending[3].resolve(json(body(pending[3].id)));
    });
    await waitFor(() => expect(pending).toHaveLength(5));
    await act(async () => pending[4].resolve(json(body(pending[4].id))));
    await open();
    expect(document.body.textContent).not.toContain("$999.00");
    expect(peak).toBe(2);
  });
  it("retains unavailable secondary intent without displaying/highlighting primary after refresh", async () => {
    await mount();
    await open();
    fireEvent.click(screen.getByText("secondary"));
    rows = [{ ...base, model_ids: ["primary"] }];
    await act(async () => controller.refresh());
    await waitFor(() => expect(controller.selection.kind).toBe("unavailable"));
    expect(
      screen.getByRole("button", { name: "Choose fixture model" }).textContent,
    ).toContain("Selected model unavailable · secondary");
    await open();
    expect(screen.getByText("Fixture key").className).not.toContain(
      "font-semibold",
    );
  });
  it("retires selection and observations across A to B to A without adopting prior authority", async () => {
    await mount();
    await open();
    fireEvent.click(screen.getByText("secondary"));
    owner = "b";
    await act(async () => auth.refresh());
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    expect(controller.selection.kind).toBe("unselected");
    owner = "a";
    await act(async () => auth.refresh());
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    expect(controller.selection.kind).toBe("unselected");
    expect(
      paths.filter((path) => path === "/settings/models/user"),
    ).toHaveLength(3);
  });
  it.each([
    [0, "$0.00"],
    [42, "$42.00"],
    [42.5, "$42.50"],
    [0.0031, "$0.0031"],
    [-0.0001, "$-0.0001"],
    [42.50001, "$42.50001"],
    [1.037e-9, "$1.037e-9"],
  ])("preserves numeric provider credit %s", async (value, label) => {
    balanceBody = (id) => ({ ...body(id), balance_usd: value });
    await mount();
    await open();
    await screen.findByText(`Provider-reported credit ${label}`);
  });
  it("reads remaining rows again when an already open menu receives a new inventory epoch", async () => {
    rows = Array.from({ length: 8 }, (_, i) => ({
      ...base,
      id: `key-${i}`,
      display_name: `Fixture ${i}`,
    }));
    usage = [];
    await mount();
    await open();
    await waitFor(() =>
      expect(
        paths.filter((path) => path.startsWith("/settings/balance/")),
      ).toHaveLength(8),
    );
    await act(async () => controller.refresh());
    await waitFor(() =>
      expect(
        paths.filter((path) => path.startsWith("/settings/balance/")),
      ).toHaveLength(16),
    );
    expect(screen.getByText("Fixture 7")).toBeDefined();
    await act(async () => auth.refresh());
    await waitFor(() =>
      expect(
        paths.filter((path) => path.startsWith("/settings/balance/")),
      ).toHaveLength(24),
    );
    expect(screen.getByText("Fixture 7")).toBeDefined();
  });

  it("recovers failed inventory through explicit refresh without selecting a fallback", async () => {
    modelsRead = async () => new Response(null, { status: 503 });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(controller.inventory.kind).toBe("failed"));
    expect(controller.selection.kind).toBe("unselected");
    modelsRead = null;
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh model usage" }),
    );
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    await open();
    await screen.findByText("secondary");
    expect(controller.selection.kind).toBe("unselected");
    expect(
      paths.filter((path) => path === "/settings/models/user"),
    ).toHaveLength(2);
  });
  it("denies retained picker commands immediately when host admission retires", async () => {
    let admitted = true;
    resourceCurrent = () => admitted;
    await mount();
    await open();
    await screen.findByText("Provider-reported credit $0.0031");
    const retained = capturedView.props;
    expect(retained).not.toBeNull();
    const before = paths.length;
    admitted = false;
    await act(async () => {
      retained?.onChange("key-0", "secondary");
      retained?.onMenuMount?.();
      await retained?.onRefresh();
    });
    expect(controller.selection.kind).toBe("unselected");
    expect(paths).toHaveLength(before);
  });

  it("hides retired selection and late metrics, then starts a fresh same-account resource cycle", async () => {
    const oldAdmission = { current: true };
    resourceCurrent = () => oldAdmission.current;
    let release: (response: Response) => void = () => {
      throw new Error("fixture response not captured");
    };
    balanceRead = () =>
      new Promise<Response>((resolve) => {
        release = resolve;
      });
    const view = await mount();
    await open();
    fireEvent.click(screen.getByText("secondary"));
    await open();
    const retained = capturedView.props;
    oldAdmission.current = false;
    view.rerender(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await act(async () => release(json({ ...body("key-0"), balance_usd: 999 })));
    expect(document.body.textContent).not.toContain("Fixture key");
    expect(document.body.textContent).not.toContain("secondary");
    expect(document.body.textContent).not.toContain("$999.00");
    expect(document.body.textContent).not.toContain("No API keys yet");
    expect(document.body.textContent).toMatch(/resource.*unavailable|unavailable.*resource/i);
    const usageBefore = paths.filter(
      (path) => path === "/settings/usage",
    ).length;
    resourceCurrent = () => true;
    balanceRead = null;
    view.rerender(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() =>
      expect(paths.filter((path) => path === "/settings/usage")).toHaveLength(
        usageBefore + 1,
      ),
    );
    const before = paths.length;
    await act(async () => {
      retained?.onChange("", undefined);
      await retained?.onRefresh();
    });
    expect(controller.selection).toEqual({
      kind: "saved",
      recordId: "key-0",
      modelId: "secondary",
    });
    expect(paths).toHaveLength(before);
    await screen.findByText("Provider-reported credit $0.0031");
  });

  it("keeps retired physical balance reads in the two-slot cap across fresh resource admission", async () => {
    rows = Array.from({ length: 3 }, (_, i) => ({ ...base, id: `key-${i}` }));
    usage = [];
    const oldAdmission = { current: true };
    resourceCurrent = () => oldAdmission.current;
    const pending: { id: string; resolve: (value: Response) => void }[] = [];
    let live = 0;
    let peak = 0;
    balanceRead = (id) => {
      live++;
      peak = Math.max(peak, live);
      return new Promise<Response>((resolve) =>
        pending.push({
          id,
          resolve: (value) => {
            live--;
            resolve(value);
          },
        }),
      );
    };
    const view = await mount();
    await waitFor(() => expect(pending).toHaveLength(2));
    oldAdmission.current = false;
    resourceCurrent = () => true;
    view.rerender(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(pending).toHaveLength(2);
    await act(async () => pending[0].resolve(json({ ...body(pending[0].id), balance_usd: 999 })));
    await waitFor(() => expect(pending).toHaveLength(3));
    expect(peak).toBe(2);
    await act(async () => pending[1].resolve(json(body(pending[1].id))));
    await waitFor(() => expect(pending).toHaveLength(4));
    await act(async () => {
      pending[2].resolve(json(body(pending[2].id)));
      pending[3].resolve(json(body(pending[3].id)));
    });
    await waitFor(() => expect(pending).toHaveLength(5));
    await act(async () => pending[4].resolve(json(body(pending[4].id))));
    await open();
    expect(document.body.textContent).not.toContain("$999.00");
    expect(peak).toBe(2);
    expect(paths.filter((path) => path === "/settings/models/user")).toHaveLength(1);
    expect(paths.filter((path) => path === "/settings/usage")).toHaveLength(2);
  });

  it("does not dispatch queued balance work when admission retires before a physical slot settles", async () => {
    rows = Array.from({ length: 8 }, (_, i) => ({ ...base, id: `key-${i}` }));
    usage = [];
    let admitted = true;
    resourceCurrent = () => admitted;
    const pending: { id: string; resolve: (value: Response) => void }[] = [];
    balanceRead = (id) =>
      new Promise<Response>((resolve) => pending.push({ id, resolve }));
    await mount();
    await waitFor(() => expect(pending).toHaveLength(2));
    const retained = capturedView.props;
    admitted = false;
    await act(async () => {
      retained?.onMenuMount?.();
      pending[0].resolve(json(body(pending[0].id)));
      pending[1].resolve(json(body(pending[1].id)));
    });
    expect(pending).toHaveLength(2);
    expect(paths.filter((path) => path.startsWith("/settings/balance/"))).toHaveLength(2);
  });

  it("does not transfer an old resource's held refresh-all marker to a new same-account resource", async () => {
    rows = Array.from({ length: 8 }, (_, i) => ({
      ...base,
      id: `key-${i}`,
      display_name: `Fixture ${i}`,
    }));
    usage = [];
    const oldAdmission = { current: true };
    resourceCurrent = () => oldAdmission.current;
    const view = await mount();
    await waitFor(() =>
      expect(paths.filter((path) => path.startsWith("/settings/balance/"))).toHaveLength(6),
    );
    let release: (response: Response) => void = () => {
      throw new Error("held inventory fixture not captured");
    };
    modelsRead = () =>
      new Promise<Response>((resolve) => {
        release = resolve;
      });
    const retained = capturedView.props;
    let refresh: void | Promise<void>;
    act(() => {
      refresh = retained?.onRefresh();
    });
    await waitFor(() => expect(controller.inventory.kind).toBe("loading"));
    oldAdmission.current = false;
    resourceCurrent = () => true;
    view.rerender(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await act(async () => {
      release(json({
        models: rows,
        count: rows.length,
        stale_registered: [],
        source: "fixture",
      }));
      await refresh;
    });
    await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
    await waitFor(() =>
      expect(paths.filter((path) => path.startsWith("/settings/balance/"))).toHaveLength(12),
    );
    await open();
    await waitFor(() =>
      expect(paths.filter((path) => path.startsWith("/settings/balance/"))).toHaveLength(14),
    );
  });

});
