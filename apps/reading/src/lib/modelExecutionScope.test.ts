import { describe, expect, it } from "vitest";
import {
  createModelExecutionScope,
  parseModelIdentity,
} from "./modelExecutionScope";
const identity = {
  user_id: "owner-a",
  email: null,
  auth_method: "antiek_session_cookie",
};
describe("model execution identity", () => {
  it("copies and freezes the validated projection without freezing its input", () => {
    const input = { ...identity };
    const parsed = parseModelIdentity(input);
    expect(parsed).toEqual(identity);
    expect(Object.isFrozen(parsed)).toBe(true);
    input.user_id = "owner-b";
    expect(parsed?.user_id).toBe("owner-a");
    expect(Object.isFrozen(input)).toBe(false);
  });
  it.each([
    null,
    {},
    { ...identity, email: undefined },
    { ...identity, user_id: " ".repeat(2) },
    { ...identity, user_id: "x".repeat(257) },
    { ...identity, auth_method: "unauthenticated_local" },
    { ...identity, user_id: "service" },
    { ...identity, user_id: "shared" },
    { ...identity, user_id: "local" },
    { ...identity, user_id: "__operator__" },
    { ...identity, user_id: "__operator__", email: "a@@b" },
    { ...identity, user_id: "__operator__", email: "a@" },
  ])("refuses an invalid projection %#", (value) =>
    expect(parseModelIdentity(value)).toBeNull(),
  );
  it("admits a verified sentinel without deriving an owner", () =>
    expect(
      parseModelIdentity({
        ...identity,
        user_id: "__operator__",
        email: " Person@Example.org ",
      })?.email,
    ).toBe(" Person@Example.org "));
  it("retires exact tokens through A to B to A", () => {
    const store = createModelExecutionScope();
    const a = store.verify(identity);
    expect(a.kind).toBe("ready");
    if (a.kind !== "ready") return;
    expect(store.isCurrent(a)).toBe(true);
    store.suspend("checking_identity");
    expect(store.isCurrent(a)).toBe(false);
    store.verify({ ...identity, user_id: "owner-b" });
    store.verify(identity);
    expect(store.isCurrent(a)).toBe(false);
    expect(Object.isFrozen(a.identity)).toBe(true);
  });
});
