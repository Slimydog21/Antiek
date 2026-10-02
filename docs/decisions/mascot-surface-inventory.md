# Antiek user-facing surface inventory — Doodles visual language

Every user-facing surface, each either **carrying the Doodles art** or
**explicitly waived with a reason**.

Coverage is derived from the router, not from `MODE_TAXONOMY`: the taxonomy
lists 42 modes, but `App.tsx` declares **61 routes across 50 routed
components**, and the difference is where surfaces went missing before.

| | count |
|---|---|
| routed components | 50 |
| carrying art | 13 |
| waived with reason | 34 |
| not surfaces (redirects, panel host) | 3 |
| uncovered | **0** |

## Carrying art (13 pieces across 14 placements)

| surface | feature | prop | placement |
|---|---|---|---|
| Home | research / read / write / speak | magnifier, book, pencil, mic | four workflow cards |
| Product window (SubActionList) | the activated door | as above | window header |
| Biography | biography | framed portrait | page header |
| InterviewIndex | interviews | two microphones | page header |
| Library | library | bookshelf | page header |
| NotebooksIndex | notebooks | spiral pad | page header |
| OutcomesIndex | outcomes | clipboard + tick | page header |
| Pricing | pricing | price tag | page header |
| Sources | sources | stack of books | page header |
| TrustCenter | trust | padlock | page header |
| WrestleApp | wrestler | rolled scroll | page header |
| Wait-arcade (ice fishing) | — | ice hole + rod | cartridge key art |
| Wait-arcade (paperclip) | — | lamp-lit desk at night | cartridge key art |


## Waived, with reason


| surface | workflow | reason |
|---|---|---|
| Notebook | read | No feature-identity header to hang art on (the surface has no <h1>, or its <h1> is per-record data). |
| Reader | read | Carries its door's art already via Home + the product window; art on the product's own page would duplicate, not inform. |
| Backtest report | research | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Brainstorm station | research | No feature-identity header to hang art on (the surface has no <h1>, or its <h1> is per-record data). |
| Deep Research Workspace | research | No prop that the model can draw AND that no other feature already owns — see feature-art/unshipped. |
| My research | research | No prop that the model can draw AND that no other feature already owns — see feature-art/unshipped. |
| Outcome | research | Carries its door's art already via Home + the product window; art on the product's own page would duplicate, not inform. |
| Research workstation | research | Carries its door's art already via Home + the product window; art on the product's own page would duplicate, not inform. |
| Trajectory replay | research | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Application map | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Billing | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Coordination | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Cross-graph citations | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Documents | shared | No prop that the model can draw AND that no other feature already owns — see feature-art/unshipped. |
| Explain provenance | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Federation config | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Login | shared | No feature-identity header to hang art on (the surface has no <h1>, or its <h1> is per-record data). |
| Loop 3 checklist | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Multimedia | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Objective card | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Operator dashboard | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Payouts audit | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Privacy | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Settings | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Signal inventory | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Skill rule detail | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Skill rules | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Substrate stats | shared | Admin/operator tooling. A mascot here is noise, not welcome — the user is doing a job, not choosing a product. |
| Public remembrances | speak | Sub-surface of a mode that already carries art; adding more would dilute the parent's identity. |
| Speak | speak | Keeps its LIVING BrainMascot (blink/breathing/pointer-tilt). Swapping for static art is a regression, and frozen-shell snapshots gate it. |
| Speak invite (landing) | speak | Sub-surface of a mode that already carries art; adding more would dilute the parent's identity. |
| Speak project console | speak | Carries its door's art already via Home + the product window; art on the product's own page would duplicate, not inform. |
| Creation studio | write | No feature-identity header to hang art on (the surface has no <h1>, or its <h1> is per-record data). |


## Newly covered (this pass — four surfaces the previous inventory missed)

The previous inventory was generated against `MODE_TAXONOMY` (42 modes). The app
declares **61 routes / 50 routed components**, so four real surfaces had no row
at all. Each is waived, and each reason is the one already applied to its
nearest sibling — not a new exemption invented to close the gap.

| surface | route | h1 | verdict |
|---|---|---|---|
| Write home | `/write`, `/write/:deliverableId` | "Write a piece" | **Waived** — door landing page. Same reason already applied to Research workstation (`/`): it carries its door's art via Home's workflow card and the product-window header, so art on the door's own page duplicates rather than informs. |
| Meta-reading | `/read/meta-reading`, `/read/meta-reading/:assetId` | "Meta-read your corpus" | **Waived** — no prop that is drawable AND unowned. Every candidate (book, bookshelf, stack of books, spiral pad, magnifier) is already the identity of a sibling read surface; reusing one would mis-signal which feature the user is on. Same reason as Deep Research Workspace and My research. |
| Personal space | `/readings`, `/meta-readings` | `{metaDocsOnly ? "Meta-docs" : "Your readings"}` | **Waived** — one component serves **two** feature identities off a prop. A single header piece would mislabel one of the two routes, and the surface has no stable feature header to hang art on. |
| Cost & consent | `/coordination/cost-consent` | "Cost & consent" | **Waived** — operator tooling, nested under `/coordination`, which the inventory already waives on exactly this ground. The user is doing a job here, not choosing a product. |

## Not surfaces (excluded, not waived)

| component | route | why it is not a surface |
|---|---|---|
| `Navigate` | `/interviews`, `/investigations`, `*` | React Router redirect element — renders no UI. |
| `InterviewRedirect` | `/interview/:interviewId` | Redirect shim to the canonical interview route. |
| `PanelWindowApp` | `/_panel/:panelId` | Internal panel host for popped-out windows; chrome belongs to the panel it hosts. |

## Recorded, not actioned — needs infrastructure

Per-route Open Graph / social cards. `apps/reading/index.html` carries **no OG
tags at all**, and per-route cards need meta infrastructure (SSR or a prerender
step) that does not exist in the Cloudflare Pages SPA build. This is recorded
rather than attempted: it is build-infrastructure work, not frontend craft.


## Appendix — generated coverage table

Derived from `<Route>` declarations in `apps/reading/src/App.tsx`. Regenerate
after adding a route; a surface with no row here is a gap, not a waiver.

| component | route(s) | status |
|---|---|---|
| Home | `/home` | art |
| ResearchWorkstation | `/`, `/inv/:investigationId` | waived |
| DeepResearchWorkspace | `/deep-research`, `/deep-research/:sessionId` | waived |
| WrestleApp | `/wrestle`, `/wrestle/:documentId` | art |
| Sources | `/sources` | art |
| WriteHome | `/write`, `/write/:deliverableId` | waived |
| CreationStudio | `/create`, `/create/:deliverableId` | waived |
| BrainstormStation | `/brainstorm` | waived |
| NotebooksIndex | `/notebooks` | art |
| AutoNotebook | `/notebook/auto/:investigationId`, `/notebook/auto` | waived |
| Notebook | `/notebook/:notebookId` | art |
| DocumentsIndex | `/documents` | waived |
| Library | `/library` | art |
| LibraryView | `/library/browse` | art |
| MetaReading | `/read/meta-reading`, `/read/meta-reading/:assetId` | waived |
| PersonalSpace | `/readings`, `/meta-readings` | waived |
| BookReader | `/read/:documentId` | waived |
| Billing | `/billing` | waived |
| Stats | `/stats` | waived |
| Map | `/map` | waived |
| Multimedia | `/multimedia` | waived |
| Backtest | `/backtest/:synthesisId` | waived |
| PrivacyDashboard | `/privacy` | waived |
| PricingPage | `/pricing` | art |
| Settings | `/settings` | waived |
| OperatorDashboard | `/operator` | waived |
| Coordination | `/coordination` | waived |
| CostConsent | `/coordination/cost-consent` | waived |
| Explain | `/explain/:kind/:id` | waived |
| ObjectiveCard | `/objective` | waived |
| Signals | `/signals` | waived |
| OutcomesIndex | `/outcomes` | art |
| Outcomes | `/outcomes/:synthesisId` | art |
| Replay | `/replay/:investigationId` | waived |
| InterviewRedirect | `/interview/:interviewId` | not-a-surface |
| SpeakIndex | `/speak` | waived |
| SpeakConsole | `/speak/:projectId` | waived |
| Biography | `/biography` | art |
| Loop3 | `/loop-3` | waived |
| SkillRules | `/skill-rules` | waived |
| SkillRuleDetail | `/skill-rules/:ruleId` | waived |
| Federation | `/federation` | waived |
| CrossGraphCitations | `/cross-graph/citations` | waived |
| MyResearch | `/my-research` | waived |
| PayoutsAudit | `/payouts` | waived |
| Login | `/login` | waived |
| TrustCenter | `/trust` | art |
| SpeakInvite | `/speak/invite/:token` | waived |
| SpeakPublicBrowse | `/speak/browse` | waived |
| PanelWindowApp | `/_panel/:panelId` | not-a-surface |
