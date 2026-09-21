# Typography scale — audit, and why it is not being refactored

Measured 2026-09-21 against `origin/main`, as part of bringing the frontend to a
PostHog-grade standard. Recorded rather than actioned; the reasoning is below.

## The measurement

`design/tokens.css` defines colour, motion (`--motion-fast|base|slow`,
`--ease-standard|enter`) and radius (`--radius-sm|radius|radius-lg`) scales. It
defines **no type scale** — because this is a Tailwind project, where type and
spacing come from Tailwind's own scale.

So the typography analogue of a hardcoded hex is a **Tailwind arbitrary value**:
`text-[11px]` is off-scale by construction, exactly as `#0F1419` is.

**1,273 arbitrary-value utilities across 195 files; 1,197 are typographic.**

| value | count |
|---|---|
| `text-[11px]` | 408 |
| `text-[10px]` | 277 |
| `text-[12px]` | 221 |
| `text-[13px]` | 161 |
| `text-[14px]` | 34 |
| `text-[15px]` | 29 |
| `text-[9px]` | 15 |
| `text-[13.5px]` | **8** |
| `text-[12.5px]` | **8** |
| `text-[16px]` | 5 |

Densest files: `modes/Multimedia/index.tsx` (67), `modes/Library/index.tsx` (66),
`modes/Settings/index.tsx` (39).

## What this is, and is not

It is **not** sloppiness. The values cluster tightly at 9/10/11/12/13/14/15/16 px
— a deliberate, denser scale than Tailwind's default (`text-xs` 12, `text-sm` 14,
`text-base` 16). The product wants 10px and 11px, and Tailwind's default scale
has nothing there. Reaching for `text-[11px]` is the reasonable response to a
scale that does not contain the size you need.

It **is** a coherence gap in the "hard to vary" sense: the scale exists only as a
habit distributed over 195 files, not as a declaration anywhere. Nothing stops
the 1,198th value being 11.25px.

## Why it is not refactored here

Three reasons, in order of weight:

1. **It is a design decision, not a defect.** Defining the scale means choosing
   which sizes survive and which snap to a neighbour. That redefines the
   product's type rhythm and belongs to whoever owns the design language.
2. **Every instance is a visual change.** 1,197 edits would move a large
   fraction of the 747 lost-pixel shots, requiring a mass baseline re-mint. That
   is precisely the blanket re-mint this repo has just spent significant effort
   escaping — see `e88303b66`, which fixed a pixel gate that had never been
   capable of failing.
3. **The gain is real but not urgent.** Nothing renders wrongly today.

## The one actionable subset, if someone wants it

**16 half-pixel sizes** — `text-[13.5px]` (8) and `text-[12.5px]` (8) — sit off
*any* scale, including the informal one. No system has 12.5px beside 12px and
13px. They are the likeliest accidents in the set:

```
components/Lightbox.tsx           components/lemon/LemonToast.tsx
components/navigation/Topbar.tsx  components/windows/WorkspaceWindow.tsx
modes/Biography/index.tsx (x3)    modes/Home/Home.tsx (x2)
modes/Notebook/blocks/ImageBlock.tsx
shell/SceneChrome.tsx (x2)        shell/ThreadBreadcrumb.tsx (x2)
workspace/PanelHandle.tsx         workspace/WorkspaceDemo.stories.tsx
```

Snapping these to 13px and 12px is a bounded change (16 edits, a handful of
shots). It is still a visible change to body copy on Home and Biography, so it
wants a deliberate yes rather than a drive-by fix — which is why it is written
down here instead of committed.

## Recommended shape, if it is taken up

Declare the scale in `tailwind.config` as named steps (e.g. `text-2xs` 10px,
`text-xs` 11px) so the existing sizes become first-class, then migrate file by
file with the baseline re-minted per batch. That converts a distributed habit
into a declaration without a single mass re-mint.
