import { StrictMode, useLayoutEffect, useMemo, useSyncExternalStore } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { unstable_HistoryRouter as HistoryRouter, useLocation } from "react-router-dom";
import {
  initializeNavigationHistory, readNavigationEpoch, subscribeNavigationLifetime,
  replaceNavigationStateWithoutPublication, type NavigationHistory,
} from "./navigationLifetime";
import { clearWsFromUrl } from "./persistence";

const stops: Array<() => void> = [];
afterEach(() => {
  cleanup();
  for (const stop of stops.splice(0)) stop();
  vi.restoreAllMocks();
});
function observe(stop: () => void): void { stops.push(stop); }
function bootstrap(): NavigationHistory {
  const history = initializeNavigationHistory(window);
  history.replace("/");
  return history;
}
type Capture = {
  path: string;
  key: string;
  epoch: number | null;
  submit: () => boolean;
  timer: () => boolean;
};
function Probe({ report }: { report: (value: Capture) => void }) {
  const location = useLocation();
  const epoch = useSyncExternalStore(subscribeNavigationLifetime, readNavigationEpoch, () => null);
  const value = useMemo(() => ({
    path: location.pathname + location.search,
    key: location.key,
    epoch,
    submit: () => epoch !== null && readNavigationEpoch() === epoch,
    timer: () => epoch !== null && readNavigationEpoch() === epoch,
  }), [location.pathname, location.search, location.key, epoch]);
  useLayoutEffect(() => { report(value); }, [report, value]);
  return <output data-testid="location">{value.path}</output>;
}

describe("actual root navigation lifetime", () => {
  it("is not ready before bootstrap, then installs exactly one observer before any root subscriber", () => {
    expect(readNavigationEpoch()).toBeNull();
    const ready = vi.fn();
    observe(subscribeNavigationLifetime(ready));
    const add = vi.spyOn(window, "addEventListener");
    const history = initializeNavigationHistory(window);
    expect(readNavigationEpoch()).toBe(0);
    expect(ready).toHaveBeenCalledTimes(1);
    expect(add.mock.calls.filter(([name]) => name === "popstate")).toHaveLength(1);
    expect(initializeNavigationHistory(window)).toBe(history);
    expect(add.mock.calls.filter(([name]) => name === "popstate")).toHaveLength(1);
    const before = readNavigationEpoch()!;
    history.push("/before-react");
    expect(readNavigationEpoch()).toBe(before + 1);
    expect(history.location.pathname).toBe("/before-react");
  });

  it("advances PUSH and identical REPLACE before lifetime/router subscribers and preserves live delegation", () => {
    const history = bootstrap();
    const before = readNavigationEpoch()!;
    const order: Array<[string, number | null, string]> = [];
    observe(subscribeNavigationLifetime(() => order.push(["lifetime", readNavigationEpoch(), history.location.pathname])));
    observe(history.listen((update) => order.push([update.action, readNavigationEpoch(), update.location.pathname])));
    history.push("/next?q=1", { draft: "retained" });
    const key = history.location.key;
    expect(history.action).toBe("PUSH");
    expect(history.location.state).toEqual({ draft: "retained" });
    history.replace(history.location);
    expect(history.action).toBe("REPLACE");
    expect(history.location.key).toBe(key);
    expect(order).toEqual([
      ["lifetime", before + 1, "/next"], ["PUSH", before + 1, "/next"],
      ["lifetime", before + 2, "/next"], ["REPLACE", before + 2, "/next"],
    ]);
    expect(history.createHref("/x?q=1")).toBe("/x?q=1");
    expect(history.createURL("/x?q=1").pathname).toBe("/x");
    expect(history.encodeLocation("/x?q=1")).toEqual({ pathname: "/x", search: "?q=1", hash: "" });
  });

  it("observes real browser-history POP before a facade subscriber", async () => {
    const history = bootstrap();
    history.push("/pop-target");
    const before = readNavigationEpoch()!;
    let epochAtPop: number | null = null;
    await act(async () => {
      await new Promise<void>((resolve) => {
        const stop = history.listen((update) => {
          if (update.action !== "POP") return;
          epochAtPop = readNavigationEpoch();
          stop();
          resolve();
        });
        observe(stop);
        history.go(-1);
      });
    });
    expect(history.location.pathname).toBe("/");
    expect(epochAtPop).toBe(before + 1);
  });

  it("retires retained callbacks on original-entry ABA before consumer commit", () => {
    const history = bootstrap();
    let current: Capture | null = null;
    const report = (value: Capture) => { current = value; };
    render(<HistoryRouter history={history}><Probe report={report} /></HistoryRouter>);
    const original = current!;
    const originalState: unknown = window.history.state;
    const originalUrl = window.location.href;
    act(() => {
      history.push("/temporary");
      // Controlled browser event delivery restores the exact historical state
      // and URL, then enters the real package POP listener; no fake epoch.
      // The separate test above uses asynchronous native history.go(-1).
      window.history.replaceState(originalState, "", originalUrl);
      window.dispatchEvent(new PopStateEvent("popstate", { state: originalState }));
      expect(window.location.pathname).toBe("/");
      expect(history.location.key).toBe(original.key);
      expect(current).toBe(original);
      expect(original.submit()).toBe(false);
      expect(original.timer()).toBe(false);
    });
    expect(current!.path).toBe("/");
    expect(current!.epoch).not.toBe(original.epoch);
  });

  it("keeps ordinary same-home renders current and StrictMode cleanup does not detach the observer", () => {
    const history = bootstrap();
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    let current: Capture | null = null;
    const report = (value: Capture) => { current = value; };
    const host = <StrictMode><HistoryRouter history={history}><Probe report={report} /></HistoryRouter></StrictMode>;
    const view = render(host);
    const original = current!;
    view.rerender(<StrictMode><HistoryRouter history={history}><Probe report={(value) => report(value)} /></HistoryRouter></StrictMode>);
    expect(readNavigationEpoch()).toBe(original.epoch);
    expect(original.submit()).toBe(true);
    expect(original.timer()).toBe(true);
    act(() => { history.push("/strict"); });
    expect(screen.getByTestId("location").textContent).toBe("/strict");
    view.unmount();
    expect(add.mock.calls.filter(([name]) => name === "popstate")).toHaveLength(0);
    expect(remove.mock.calls.filter(([name]) => name === "popstate")).toHaveLength(0);
    const before = readNavigationEpoch()!;
    history.push("/after-cleanup");
    expect(readNavigationEpoch()).toBe(before + 1);
  });

  it("isolates callback faults and cleans independent duplicate subscriptions without disposing observation", () => {
    const history = bootstrap();
    const notice = vi.fn();
    const first = subscribeNavigationLifetime(notice);
    const second = subscribeNavigationLifetime(notice);
    observe(first); observe(second);
    observe(subscribeNavigationLifetime(() => { throw new Error("observer fault"); }));
    observe(history.listen(() => { throw new Error("subscriber fault"); }));
    const routing = vi.fn();
    observe(history.listen(routing));
    history.push("/one");
    expect(notice).toHaveBeenCalledTimes(2);
    expect(routing).toHaveBeenCalledTimes(1);
    first(); first();
    history.replace("/two");
    expect(notice).toHaveBeenCalledTimes(3);
    expect(routing).toHaveBeenCalledTimes(2);
    second();
    const before = readNavigationEpoch()!;
    history.push("/three");
    expect(notice).toHaveBeenCalledTimes(3);
    expect(readNavigationEpoch()).toBe(before + 1);
  });

  it("rejects rebinding to a conflicting actual Window", () => {
    const history = bootstrap();
    const frame = document.createElement("iframe");
    document.body.append(frame);
    try {
      const otherWindow = frame.contentWindow;
      expect(otherWindow).not.toBeNull();
      expect(() => initializeNavigationHistory(otherWindow!)).toThrow("another Window");
      expect(initializeNavigationHistory(window)).toBe(history);
    } finally { frame.remove(); }
  });

  it("preserves the actual observer, subscribers and counter through module handover", async () => {
    const history = bootstrap();
    const oldEpoch = readNavigationEpoch()!;
    const oldCallback = () => readNavigationEpoch() === oldEpoch;
    const notice = vi.fn();
    observe(subscribeNavigationLifetime(notice));
    const add = vi.spyOn(window, "addEventListener");
    vi.resetModules();
    const handedOver = await import("./navigationLifetime");
    expect(handedOver.initializeNavigationHistory(window)).toBe(history);
    expect(handedOver.readNavigationEpoch()).toBe(oldEpoch);
    history.push("/handover");
    expect(handedOver.readNavigationEpoch()).toBe(oldEpoch + 1);
    expect(readNavigationEpoch()).toBe(oldEpoch + 1);
    expect(oldCallback()).toBe(false);
    expect(notice).toHaveBeenCalledTimes(1);
    expect(add.mock.calls.filter(([name]) => name === "popstate")).toHaveLength(0);
  });

  it("removes ws through exactly the original native replacement without router publication", () => {
    const history = bootstrap();
    history.replace("/?keep=1&ws=fixture#anchor");
    const routing = vi.fn();
    observe(history.listen(routing));
    const notice = vi.fn();
    observe(subscribeNavigationLifetime(notice));
    const before = readNavigationEpoch()!;
    const replace = vi.spyOn(window.history, "replaceState");
    clearWsFromUrl();
    expect(replace).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith({}, "", "/?keep=1#anchor");
    expect(window.history.state).toEqual({});
    expect(window.location.search).toBe("?keep=1");
    expect(window.location.hash).toBe("#anchor");
    expect(readNavigationEpoch()).toBe(before + 1);
    expect(notice).toHaveBeenCalledTimes(1);
    expect(routing).not.toHaveBeenCalled();
    clearWsFromUrl();
    expect(readNavigationEpoch()).toBe(before + 1);
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it("keeps direct throws and absent-ws no-ops from advancing or publishing", () => {
    const history = bootstrap();
    const before = readNavigationEpoch();
    clearWsFromUrl();
    expect(readNavigationEpoch()).toBe(before);
    history.replace("/?ws=fixture");
    const beforeThrow = readNavigationEpoch();
    const routing = vi.fn();
    observe(history.listen(routing));
    vi.spyOn(window.history, "replaceState").mockImplementation(() => { throw new Error("replacement denied"); });
    expect(() => clearWsFromUrl()).toThrow("replacement denied");
    expect(readNavigationEpoch()).toBe(beforeThrow);
    expect(routing).not.toHaveBeenCalled();
  });

  it("preserves removal of a present empty ws and the standalone native helper contract", () => {
    const history = bootstrap();
    history.replace("/?ws=&keep=1");
    const before = readNavigationEpoch()!;
    clearWsFromUrl();
    expect(window.location.search).toBe("?keep=1");
    expect(readNavigationEpoch()).toBe(before + 1);
    replaceNavigationStateWithoutPublication({ retained: true }, "/?keep=2");
    expect(window.history.state).toEqual({ retained: true });
    expect(readNavigationEpoch()).toBe(before + 2);
  });

  it("permanently refuses exhausted admission while actual routing and subscribers still work", () => {
    const history = bootstrap();
    // Deliberate private counter fault injection; the getter is real and the
    // transition below still uses the actual router. No production test API.
    const registry: unknown = Reflect.get(globalThis, Symbol.for("antiek.navigationLifetime.v1"));
    if (typeof registry !== "object" || registry === null || !("lifetime" in registry) ||
        typeof registry.lifetime !== "object" || registry.lifetime === null) throw new Error("No observed lifetime");
    Reflect.set(registry.lifetime, "epoch", Number.MAX_SAFE_INTEGER);
    const admittedAtLimit = readNavigationEpoch();
    let current: Capture | null = null;
    render(<HistoryRouter history={history}><Probe report={(value) => { current = value; }} /></HistoryRouter>);
    const retained = current!;
    const routing = vi.fn();
    observe(history.listen(routing));
    act(() => { history.replace("/still-routes"); });
    expect(admittedAtLimit).toBe(Number.MAX_SAFE_INTEGER);
    expect(readNavigationEpoch()).toBeNull();
    expect(history.location.pathname).toBe("/still-routes");
    expect(screen.getByTestId("location").textContent).toBe("/still-routes");
    expect(retained.submit()).toBe(false);
    expect(retained.timer()).toBe(false);
    expect(routing).toHaveBeenCalledTimes(1);
    expect(initializeNavigationHistory(window)).toBe(history);
    expect(readNavigationEpoch()).toBeNull();
  });
});
