# Antiek Mascot Profile — the Brain

**Status:** v4 — 32 shots across 4 rounds + 1 veo-3.1 idle video + transparent cutouts (2026-08-12)
**Replaces:** Werner (penguin) — `apps/reading/src/brand/werner/`
**Mission tie-in:** Antiek uses AI to *amplify* the human brain, never replace it. The mascot *is* the thesis: a warm, curious, capable brain doing the learning itself.

---

## 1. Concept

| | |
|---|---|
| **Subject** | A round, plump human brain — two hemispheres, visible cerebellum — brought to life as a character |
| **Face** | Kirby-like: two big glossy black oval eyes, tiny sweet smile, rosy round cheeks, no nose |
| **Body** | Thin black stick arms and stick legs with rounded tips (Gumball-style limbs) |
| **Aesthetic** | Studio Ghibli softness (painterly pastels, gentle light) × The Amazing World of Gumball hyper-realism (real 3D material, subsurface glow on the brain surface) |
| **Personality** | Curious, warm, delighted, wholesome. The joy of understanding. |
| **Name (proposed)** | **Cortex** — working title; alternates: **Noodle**, **Gyri**, **Spark**, **Crumbs**. Final name is the operator's call. |

**Why a brain:** every other AI product markets the *machine's* intelligence. Antiek's brand promise is the opposite — AI as a trainer/tutor/amplifier that makes *your* brain stronger. The mascot puts that promise on the face of the product: it's not a robot that thinks for you, it's a brain that thinks *with* you.

---

## 2. Design spec (canonical, for every future generation)

Verbatim character block — reuse in every prompt so generations stay consistent:

```
a cute cartoon mascot character: a round plump human brain with two smooth hemispheres,
soft stylized wrinkles, warm coral-pink color with cream highlights;
kirby-like face with two big glossy black oval eyes, a tiny sweet smiling mouth, and rosy pink round cheeks;
thin black stick arms and stick legs with rounded tips;
Studio Ghibli aesthetic: soft painterly pastel palette, gentle dreamy lighting, warm hand-painted feel;
rendered with hyper-realistic 3D texture like The Amazing World of Gumball,
subtle subsurface glow on the brain surface, crisp cinematic lighting
```

**Hard rules**
- Exactly **two** hemispheres + small cerebellum at the lower back. No brainstem noodle, no dripping, no exposed neurons.
- Face is **always** Kirby-simple: no nose, no eyebrows, no teeth. Cheeks are two round rosy blushes.
- Limbs are **always** thin black sticks with rounded tips. Never realistic hands/feet, never gloves.
- Palette is **warm coral-pink + cream + soft peach**. Never clinical pink-red, never gray matter.
- Texture: glossy-but-soft. Subsurface glow, gentle specular — *not* wet, *not* wrinkled like a real brain. "Gumball material," not "surgery textbook."

**Palette (measured from hero render; lock exact hexes during vectorization)**

| Role | Approx hex | Notes |
|---|---|---|
| Brain body | `#D9A090` | warm coral pink |
| Brain shadow | `#BF8578` | |
| Highlight | `#F0B8A8` | cream-pink sheen |
| Cheeks | `#F2A0A0` | rosy blush |
| Eyes/mouth/limbs | `#1A1A1A` | soft black |
| Cream bg | `#F0E4DA` | Ghibli paper cream |
| Dark surface | `#0B1020` | app `space-2` navy |
| Sun accent (existing brand) | `#FFD54A` | rail button, kept |

---

## 3. Shot gallery (round 1, 12 shots + assets)

All in `tools/brand/mascot-brain/`. Models: **GPT Image 2 (2K/4K), Krea 2 Large, Nano Banana Pro/2, Flux 1.1 Pro Ultra, Imagen 4 Ultra, Seedream 5 Pro, Z-Image + Veo 3.1 (video)**.

| # | File | Angle / setting | Model | Intended use |
|---|---|---|---|---|
| 1 | `01_hero_front.png` | front portrait, chest-up | Krea 2 Large | **anchor** — avatar, hero, consistency reference |
| — | `01_hero_front_transparent.png` | hero, bg removed | rembg u2net | the canonical transparent pose |
| 2 | `02_fullbody_wave.png` | full body, ¾, waving | Krea 2 Large | onboarding, empty states |
| — | `02_fullbody_wave_transparent.png` | full body, bg removed | rembg u2net | compositable anywhere |
| 3 | `03_side_profile.png` | side profile | Krea 2 Large (i2i) | character sheet, logos |
| 4 | `04_back_view.png` | back ¾, cerebellum visible | Krea 2 Large (i2i) | animation turnaround |
| 5 | `05_reading_scene.png` | Ghibli library, reading | Krea 2 Large (i2i) | marketing, landing |
| 6 | `06_neural_setting.png` | neural-network night field | Krea 2 Large (i2i) | hero banner 16:9 |
| 7 | `07_desk_study.png` | wooden desk, notebook, tea | Krea 2 Large (i2i) | blog/OG imagery |
| 8 | `08_app_ui_dark_composite.png` | **idle pose, dark mode** | hero + `#0B1020` composite | rail mascot / dark UI |
| 9 | `09_logo_mark.png` | flat vector-style mark | Nano Banana Pro | logo mark (navy bg) |
| 10 | `10_action_leap.png` | mid-leap, joy | Flux 1.1 Pro Ultra | celebration, confetti |
| 11 | `11_character_sheet.png` | 2×2 expression sheet | Nano Banana Pro (i2i) | animation reference |
| 12 | `12_texture_closeup.png` | macro texture study | Imagen 4 Ultra | material bible |
| 13 | `13_insight_bulb.png` | thinking + lightbulb insight | Krea 2 Large (i2i) | 'aha' moments |
| 14 | `14_confetti_celebration.png` | jumping, confetti | Flux 1.1 Pro Ultra | celebrations |
| 16 | `16_hero_v2_2k.png` | **premium hero, 2K** | GPT Image 2 (i2i) | new anchor candidate |
| — | `16_hero_v2_2k_transparent.png` | 2K hero, bg removed | rembg u2net | canonical 2K pose |
| 17 | `17_social_card.png` | 16:9 banner, text space left | Krea 2 Large (i2i) | social/OG card |
| 18 | `18_dark_idle_v2.png` | **true dark idle, 2K** | GPT Image 2 (i2i) | rail mascot, dark UI |
| 19 | `19_graduation.png` | graduation cap, proud | Krea 2 Large (i2i) | learning milestones |
| 20 | `20_running_sparkle.png` | running, sparkle trail | Seedream 5 Pro (i2i) | motion, loading |
| 21 | `21_cinematic_poster.png` | golden-hour landscape poster | Z-Image (i2i) | landing hero |
| 22 | `22_peek_over_edge.png` | peeking over frame edge | Krea 2 Large (i2i) | playful moments |
| 23 | `23_shush_focus.png` | 'shh' focus mode, book | Krea 2 Large (i2i) | focus/distraction-free |
| 24 | `24_magnifier_research.png` | magnifying glass, 2K | GPT Image 2 (i2i) | research mode |
| 25 | `25_question_marks.png` | wonder + question marks | Nano Banana 2 (i2i) | curiosity states |
| 26 | `26_book_hug.png` | hugging a book, 2K | Nano Banana Pro (i2i) | love of reading |
| 27 | `27_loading_state.png` | waiting, loading dots, 2K | GPT Image 2 (i2i) | loading/empty states |
| 28 | `28_hero_v3_4k.png` | **definitive hero, 4K (2880²)** | GPT Image 2 (i2i) | THE anchor |
| — | `28_hero_v3_4k_transparent.png` | 4K hero, bg removed | rembg u2net | canonical 4K pose |
| 29 | `29_sleepy_night.png` | sleeping on a crescent moon | Imagen 4 Ultra | night mode, bedtime |
| 30 | `30_turnaround_sheet.png` | 4-view turnaround sheet, 2K | GPT Image 2 (i2i) | **animation bible** |
| 31 | `31_expression_lineup.png` | 6-expression lineup, 2K | Nano Banana 2 (i2i) | **animation moods** |
| 32 | `32_vertical_onboarding.png` | 9:16 mobile onboarding | Krea 2 Large (i2i) | mobile, text space below |
| 33 | `33_cinematic_wide.png` | 2.35:1 sunrise landscape | Krea 2 Large (i2i) | landing cinematic |
| 34 | `34_idle_video.mp4` | **8s idle animation (blink, breathe, wave)** | Veo 3.1 (image-to-video) | first animation proof |

| — | `mark-32/180/400.png` | resized transparent marks | local | favicon, avatar, rail |
| — | `CONTACT-SHEET.png` | all shots on one page | local | quick human review |

**Dark-mode note:** Krea 2 Large would NOT hold a flat `#0B1020` background (two re-rolls came back cream) — but **GPT Image 2 delivered it** (`18_dark_idle_v2.png`, 71% navy, verified). The deterministic composite (`08_app_ui_dark_composite.png`) remains as the pixel-perfect fallback for UI placement.

---

## 4. Consistency protocol (how to keep the same brain)

1. **Anchor lock:** `28_hero_v3_4k.png` is the new canonical identity (4K, GPT Image 2, i2i from the v1 anchor); `01_hero_front.png` remains the legacy v1 anchor and the source for all i2i references.
2. **i2i recipe (verified):** compress anchor to ≤768px JPEG (quality ~78), base64 data-URI, send as `image_url` with `strength 0.5–0.6` for scenes, `0.6–0.7` for poses, to `krea/krea-2/large` (payload requires `resolution: "1K"`; `negative_prompt` is NOT accepted on that endpoint — drop it or use `creativity`).
3. **Prompt block:** always paste the verbatim character block above + ", same character as the reference image, consistent face, colors and proportions".
4. **Post-pass:** if a shot drifts, re-roll with the same recipe rather than hand-fixing.
5. **Transparent pass:** rembg u2net (installed in kernel venv) on the anchor pose; deterministic composite onto any UI background.

---

## 5. App asset pipeline (mirrors Werner)

Replace `apps/reading/src/brand/werner/` with `apps/reading/src/brand/cortex/` (or chosen name):

```
src/brand/cortex/
  poses/anchor/cortex_default_v1.png      <- 01_hero_front_transparent.png
  poses/anchor/cortex_hero_v1.png         <- 01_hero_front.png (hero crop)
  poses/cortex_thinking_v1.png            <- 11_character_sheet (thinking cell)
  poses/cortex_sleeping_v1.png            <- 11_character_sheet (sleepy cell)
  poses/cortex_happy_v1.png               <- 11_character_sheet (excited cell)
  marks/mark-32.png  mark-180.png  avatar-400.png  social-card-1200.png  stack-lockup.svg
```

Required next asset pass (not done yet):
- **Vector logo mark** — hand-trace `09_logo_mark.png` to SVG for `stack-lockup.svg`/`favicon.svg` (brain silhouette + two dot eyes + smile is a tractable 3-path SVG).
- **Dark-surface check** — verify transparent pose composites on `space-2` (`#0B1020`) like Werner's M4 criterion (composite already produced; check at 64px rail size for belly-fringe).
- **Social card 1200×630** — crop/place hero or reading scene.

---

## 6. Next steps (animation & interaction — round 2, not started)

- **Idle animation:** blink (2-frame), breathing bounce, occasional cheek-shine shift — from `11_character_sheet`.
- **Cursor interaction:** eyes track cursor (Kirby-style pupils), wave on hover, happy squish on click — per the operator's brief.
- **Background presence:** low-opacity floating brain in empty states / loading screens, Ghibli sparkle trail.
- **Mood system:** map app states (reading, thinking, lost, celebrating) to the sheet's four moods, extended to 6–8.
- Where: the reading app's existing Werner animation component (`brand-werner-animations` surface) gets renamed/re-skinned to the brain.

---

## 7. QA status (honest)

- **Programmatic QA: passed.** All shots carry the coral-pink brain (13–34% coverage), logo mark is 78% navy + cream mark, transparent mattes are clean (corners 0.0 alpha, center 1.0, <2% ramp), marks generated.
- **Vision-model review: STILL NOT completed.** Every vision-capable candidate failed: kimi-sub/k3 = billing-cycle quota exhausted (403); grok-sub/grok-4.5 and openai-codex = auth preflight failed; xiaomi mimo-v2.5-pro, zai/glm-5.2, deepseek-v4 = text-only. **The operator should eyeball `CONTACT-SHEET.png`** before round 2.
- Cross-shot consistency is *good but not pixel-perfect*; the i2i shots share the anchor's face by construction. Prompt-only shots (logo mark, action leap, texture closeup) may drift slightly.
- Exact palette hexes are approximate until vectorization. Name is unconfirmed (Cortex is a proposal).

*Generated with Krea API (krea-2/large, nano-banana-pro, flux-1.1-pro-ultra, imagen-4-ultra) + rembg u2net cutouts. Reroll recipe documented in §4.*
