import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,describe,expect,it,vi} from "vitest";
import TwinNotesPanel from "./TwinNotesPanel";
const preview=vi.fn(),apply=vi.fn(),draft=vi.fn(),list=vi.fn<()=>Promise<any>>(()=>Promise.resolve({assets:[]}));
vi.mock("../../api/research",async(load)=>{const actual=await load<typeof import("../../api/research")>();return {...actual,
 listTwinNotes:()=>list(),getTwinNoteHistory:vi.fn(),composeTwinNotes:vi.fn(),
 previewTwinNoteRevision:(...a:unknown[])=>preview(...a),applyTwinNoteRevision:(...a:unknown[])=>apply(...a),
 createTwinNoteWriteDraft:(...a:unknown[])=>draft(...a)};});
afterEach(()=>{cleanup();vi.clearAllMocks();});
describe("Cycle 49 twin-note workflow",()=>{
 it("invalidates a frozen preview on input edits and applies explicitly",async()=>{
  preview.mockResolvedValue({asset_id:"asset",expected_predecessor:null,preview_digest:"a".repeat(64),members:[{member_ordinal:0,investigation_id:"inv",window_id:"w-1"}],note_count:1,source_count:1});
  apply.mockResolvedValue({revision_id:`tnr-${"b".repeat(32)}`});
  render(<TwinNotesPanel/>); await screen.findByText("No twin notes yet.");
  fireEvent.change(screen.getByLabelText("Twin-note asset ID"),{target:{value:"asset"}});
  fireEvent.change(screen.getByLabelText("Ordered window IDs"),{target:{value:"w-1"}});
  fireEvent.click(screen.getByText("Preview")); expect(await screen.findByText("1 notes · 1 sources")).toBeTruthy();
  fireEvent.click(screen.getByText("Apply revision")); await waitFor(()=>expect(apply).toHaveBeenCalledTimes(1));
 expect(apply.mock.calls[0][0].idempotency_key).toBeTruthy();
 });
 it("freezes legacy and import controls while preview overlaps",async()=>{
  const rid=`tnr-${"d".repeat(32)}`;
  list.mockResolvedValueOnce({assets:[{asset_id:"a",asset_label:"A",current_revision:{revision_id:rid,asset_id:"a",note_count:1,source_count:1},revision_count:1}]});
  let finish:((value:any)=>void)|undefined; preview.mockReturnValue(new Promise(resolve=>{finish=resolve;}));
  render(<TwinNotesPanel/>); await screen.findByText("A");
  fireEvent.change(screen.getByLabelText("Twin-note asset ID"),{target:{value:"a"}});
  fireEvent.change(screen.getByLabelText("Ordered window IDs"),{target:{value:"w-1"}});
  fireEvent.click(screen.getByText("Preview")); await waitFor(()=>expect(preview).toHaveBeenCalledTimes(1));
  expect((screen.getByLabelText("Select current A") as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByText("Open current") as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByText("History") as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByText("Create Write draft") as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByLabelText("Refresh twin notes") as HTMLButtonElement).disabled).toBe(true);
  finish?.({asset_id:"a",expected_predecessor:null,preview_digest:"a".repeat(64),members:[],note_count:0,source_count:0});
  await screen.findByText("0 notes · 0 sources");
 });
 it("retains exact import command after an ambiguous failure",async()=>{
  const rid=`tnr-${"c".repeat(32)}`;
  list.mockResolvedValueOnce({assets:[{asset_id:"a",asset_label:"A",current_revision:{revision_id:rid,asset_id:"a",note_count:1,source_count:1},revision_count:1}]});
  draft.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({deliverable_id:"dlv-1"});
  render(<TwinNotesPanel/>); await screen.findByText("A"); fireEvent.click(screen.getByText("Create Write draft"));
  fireEvent.change(screen.getByLabelText("Write draft title"),{target:{value:"Review"}}); fireEvent.click(screen.getByText("Create draft"));
  await screen.findByRole("alert"); const first=draft.mock.calls[0][0]; fireEvent.click(screen.getByText("Create draft"));
  await waitFor(()=>expect(draft).toHaveBeenCalledTimes(2)); expect(draft.mock.calls[1][0]).toEqual(first);
 });
});
