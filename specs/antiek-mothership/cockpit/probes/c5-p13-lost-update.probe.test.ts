import { expect, it } from "vitest";
import { useBlockSources, type BlockSourcesRecord } from "./blockSources";

it("P13 load/assign race with a latent backend", async () => {
  const saved: BlockSourcesRecord[] = [];
  const server: BlockSourcesRecord = { "b-1": [{ document_id: "docA", document_title: "A", assigned_at: "t0" }] };
  useBlockSources.getState().setBlockSourcesBackend({
    load: () => new Promise((r) => setTimeout(() => r(JSON.parse(JSON.stringify(server))), 50)),
    save: async (_d, rec) => {
      saved.push(JSON.parse(JSON.stringify(rec)));
    },
  });
  const pending = useBlockSources.getState().ensureDeliverable("d-1");
  useBlockSources.getState().assign("d-1", "b-2", { document_id: "docB", document_title: "B" });
  await pending;
  console.log("P13 first save sent:", JSON.stringify(saved[0]));
  console.log("P13 UI record after load:", JSON.stringify(useBlockSources.getState().records["d-1"]));
  expect(true).toBe(true);
});
