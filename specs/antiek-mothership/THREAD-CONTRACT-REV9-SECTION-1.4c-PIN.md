# THREAD-CONTRACT rev 9, §1.4c: the pinned section text for co-sign

**Status: final text for co-sign, 2026-09-27.** Lane A (Antiek Nudge v2) wrote it.
- **Agreed with:** Astra (the Codex backend Undertaker; semantics accepted in `specs/antiek-backend-forensic-20260927/INBOX.md`).
- **Paste target:** lane B (Antiek Sweep v2) pastes it verbatim into `THREAD-CONTRACT-REV9-PART1-DRAFT.md` as §1.4c.
- **Binding** only when rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT.
- **Fixture:** `apps/reading/src/lib/api/__fixtures__/html_text_projection_v1.json` on branch `contract/html-text-projection-fixture-20260927` @ `41e4825d3`.

---

### 1.4c HTML reader text projection, `html-text/v1` (rev 9)

**What it is for.** The one canonical text of an HTML body. Chunk offsets, anchor maps, pins, highlights and probes all count against it. Plain-text bodies keep `unicode-nfc-v1` (§1.4).

1. **Authority.** The projection is computed from the **served body**: the exact UTF-8 string that `/full-text` returns and the reader mounts.
   - **Legacy bodies** served by sanitizer v1.4.0 are projected exactly as served. Hidden intent they already lost is not reconstructed, no bytes are relabelled as another sanitizer version, and nothing stored is rewritten on read.
2. **Parse.** The HTML fragment parsing algorithm is used, with context element `div` (HTML namespace) and the scripting flag **enabled**.
   - **Browser:** the reader sets `div.innerHTML` to the served string.
   - **Python:** an HTML5-conformant fragment parser runs with the same context and flag, for example html5lib `parseFragment(served, container="div", scripting=True)`. It is never stdlib `HTMLParser`.
3. **Excluded subtrees.** `script`, `style`, `template` (whose content is not in the tree), `noscript` and `head`, and any element carrying the `hidden` attribute. No CSS is evaluated.
4. **Text.** Text-node data is taken in document order, with entities decoded by the parser.
   - **Outside `pre`:** each run of ASCII whitespace (U+0020, U+0009, U+000A, U+000D, U+000C) collapses to one U+0020, **across adjacent inline text nodes**.
   - **Inside `pre`:** source whitespace is kept.
   - **U+00A0** is kept.
5. **Block separators.** One generated `\n` separates the content of adjacent blocks.
   - **The block set:** `p h1 h2 h3 h4 h5 h6 li dt dd blockquote pre figcaption caption td th tr div section article header footer aside nav table ul ol dl figure hr br`.
   - **Placement:** a separator is pending until content follows. Two generated separators never touch, and there is none at the start or end. An empty block produces nothing, and a nested block produces one separator per boundary.
   - **Trimming:** only collapsible whitespace adjacent to a generated separator is trimmed. Newlines inside `pre` are content, not separators.
6. **Normalization.** NFC (`unicode-nfc-v1`) is applied **once, to the final assembled string**, never per node.
7. **Offsets.** Offsets are Unicode scalar values over the projection, half-open `[start, end)`.
8. **Digests are distinct concepts.**
   - `NodeTextAnchor.node_text_sha256` stays the sha256 of the **whole normalized chunk**.
   - `TextLocator.text_sha256 = sha256(utf8(projection[start:end]))` is the **selection** digest.
9. **Binding to bytes.**
   - **What anchors carry.** Every persisted anchor on an HTML body carries `text_projection: "html-text/v1"` **and** `served_body_sha256`, the sha256 of the exact served UTF-8 bytes. A sanitizer version alone does not bind bytes. `/full-text` and the anchor map return both values.
   - **On reopen.** An anchor whose `text_projection` or `served_body_sha256` differs from the document's current values re-resolves by quote and context, or reads `unresolved`. It never moves silently.
10. **Chunks (A03).** Each chunk's text is an exact substring of the projection of its document's served body. The anchor map uses that projection, never guarded `raw_text`.
11. **Endpoints (lane A).**
    - **Mapping.** A DOM endpoint (node, UTF-16 offset, in the `div`-context DOM) maps to a projection scalar. A backward user selection is first put in document order.
    - **Snapping.** A start inside dropped whitespace snaps forward past generated separators, and an end snaps backward.
    - **Refusals.** No anchor is written for:
      - an endpoint that splits a composed NFC group (`splits_normalization_group`);
      - an endpoint that splits a surrogate pair (`splits_surrogate_pair`);
      - a collapsed range (`empty_selection`);
      - a range that snapping reduces to empty or reverses (`empty_after_snap`).
    - **Painting.** A composed scalar maps back to every DOM range that produced it.
12. **Pagination.** Pages follow the mounted DOM's block boundaries. Offsets stay global to the document.
13. **Fixture.** `apps/reading/src/lib/api/__fixtures__/html_text_projection_v1.json`, imported byte-for-byte by both suites (pytest reads it by path).
    - **Astra authored,** independently of any projector: the projections, their hashes and the normalization rules.
    - **Lane A owns:** the DOM paths, selections, refusals and `fragment_parse`.
    - **Field meanings:** `html` is projector input. The sanitizer cases pin `raw_input`, `served_html_target` and `served_html_legacy_v1_4_0`. DOM paths address the served string in the pinned context.
14. **Owners.**
    - **Backend (Astra):** the projector, chunking, the anchor map, resolve, backfill, and `served_body_sha256` on `/full-text` and in anchors.
    - **Lane A:** DOM mapping, mark painting, pagination and the endpoint rules.
15. **Execution gates, not co-sign blockers.**
    - (a) A real Python/browser differential over the fixture, plus malformed-tree cases (foster parenting, misnested inline and block, implicit tbody), mounting-context cases, and a sample of served production strings.
    - (b) HTML5 canonicalization and hidden-subtree stripping in the sanitizer is a separate backend change. It needs its own version bump, preserved security allowlists, idempotency and the existing security regression suite. Its owner is unclaimed.
