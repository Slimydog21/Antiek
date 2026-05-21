# Sprint 17 — Lemon UI Evaluation Spike (PostHog Wedge 1b)

**Status**: spike scaffold ready 2026-05-19. Operator visual eye test
is the load-bearing decision gate; this document captures the spike
procedure + decision criteria so the spike runs on a clean branch.

**Scope**: half-day on a side branch. NOT merged to main regardless of
outcome — the spike is a decision-making exercise, not a build.

**Reference**: master-spec §5.5 + §5.6 (PostHog design philosophy is
Antiek's design philosophy; the evaluation gate is whether Lemon UI
preserves the researcher's-notebook aesthetic). `integration_posthog.md`
§5.1b for the four hard decision criteria.

---

## Procedure

### 1. Branch + install

```bash
cd ~/Desktop/Antiek/apps/reading
git checkout -b sprint17-lemon-ui-spike
npm install --save-dev @posthog/lemon-ui
```

### 2. Migrate the lowest-risk component

`ChatInput` is the right spike target — minimal surface (textarea + button +
region chip), no state-machine complexity, no third-party deps already on
it. Replace the bespoke Tailwind component with Lemon UI's
`LemonTextArea` + `LemonButton`.

The fixture story at `apps/reading/src/components/ChatInput.stories.tsx`
is the visual reference. The migrated component should render
identically in the same Storybook story slots.

### 3. Capture measurements

**Bundle-size delta** (the deterministic gate):

```bash
npm run build
ls -l dist/assets/index-*.js  # capture pre-migration KB
# (migrate ChatInput)
npm run build
ls -l dist/assets/index-*.js  # capture post-migration KB
```

Decision threshold: **delta < 80 KB gzipped**. If above, reject.

**TypeScript strict** (deterministic):

```bash
npm run typecheck
```

Decision threshold: **zero errors**. If any, reject.

**Tailwind interop** (deterministic):

```bash
npm run storybook
# Open ChatInput stories; verify Tailwind classes still apply
# alongside Lemon UI's own styling layer
```

Decision threshold: **no visible style collision**. If Lemon UI's
styles override Tailwind in unexpected ways, reject.

### 4. Operator visual-fit eye test (the load-bearing gate)

Open the migrated `ChatInput` story in Storybook AND the original
custom `ChatInput` story side-by-side. The operator judges whether
the Lemon UI version preserves:

- Serif body font where prose-adjacent
- No forced bullets in chat-feed adjacent surfaces
- Researcher's-notebook color palette (stone-50 background, stone-900
  text, no SaaS-dashboard primary blues)
- Visual weight matching the rest of `apps/reading/`

**This is the gate that defaults to NO.** Lemon UI is built for
PostHog's SaaS-dashboard aesthetic. The default assumption is that it
will NOT pass the eye test. The spike's job is to verify that
assumption empirically rather than assert it.

### 5. Migration-coverage projection

If steps 1-4 pass, project: of the 9 existing components (ClaimCard,
NotesPanel, ChatInput, NotesFeed, CrossDocSidebar, PdfViewer,
MasterMdViewer, ParkedQuestion, WatchForLaterFolder), how many would
plausibly migrate to Lemon UI components?

Decision threshold: **≥60% projected migration coverage**. If less,
the maintenance overhead of mixing Lemon UI + custom components
exceeds the value of adopting Lemon UI partially.

---

## Verdict structure

When the spike completes, the verdict is one of:

- **ADOPT**: all four gates passed. Merge the migration to main; plan
  Sprint 18 work for the remaining components.
- **KEEP CUSTOM**: any gate failed. Document the failing gate(s);
  spike branch is deleted; Storybook stays as the design-system source
  of truth without Lemon UI underneath.

**Either verdict is defensible.** The evaluation IS the deliverable.

---

## Sprint placement

Spike runs in Sprint 17 (half-day). Verdict captured here at the
end. Operator-required visual eye test is the only piece that cannot
be automated.

If ADOPT: the migration to remaining components is a Sprint 18-19
side-track, NOT blocking the notebook surface (Wedge 2) which is the
linchpin.

If KEEP CUSTOM: the spike branch is deleted. Storybook design-system
work continues without Lemon UI dependency.

---

## Result section (filled in at verdict landing)

- [ ] Branch created
- [ ] `@posthog/lemon-ui` installed
- [ ] `ChatInput` migrated
- [ ] Bundle-size delta measured: _____ KB gzipped
- [ ] TypeScript strict result: pass / fail
- [ ] Tailwind interop result: pass / fail
- [ ] Operator visual-fit eye test result: pass / fail
- [ ] Migration-coverage projection: ___ / 9 components

**Verdict**: ADOPT | KEEP CUSTOM

**Reasoning** (one paragraph):
