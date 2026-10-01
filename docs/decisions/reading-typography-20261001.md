# Reading typography: evidence, candidate portfolio, and default

Date: 2026-10-01  
Lane claim: `codex-reading-typography-20261001`  
Status: separate local typography candidate implemented and verified. Uncommitted branch `design/reading-typography-20261001`; see the implementation record below.

## Decision

Use Source Serif 4 as the initial body font for long-form reading, with Source Sans 3, Literata, Atkinson Hyperlegible Next, and Classic system serif as reader-selectable alternatives. Start at 20 CSS pixels, 1.65 line height, and a 66ch maximum reading width. These settings are a product design starting point, not an experimentally established optimum.

Source Serif 4 best fits this brief as a restrained, warm, professional book face. It also follows the existing [master product specification, §5.2](../master-product-spec.md#52-the-discipline-to-enforce), which specifies a serif reading body. That is an aesthetic and product-consistency judgment. Academic evidence does not establish Source Serif 4, or serif fonts generally, as a universal winner. Source Sans 3 is the strongest alternative when a reader wants the simplest contemporary presentation. The four bundled families have upstream SIL Open Font License 1.1 texts; Classic should use an installed system serif rather than redistribute a proprietary font.

Offer a small portfolio because individual preferences, apparent letter size, and visual needs differ. Preserve the reader's existing choice when defaults change. Do not call a choice "the scientifically best font," promise a percentage speed gain, label a font as a dyslexia treatment, or claim that this change has demonstrated reduced fatigue. The evidence supports testing those outcomes, not advertising them as achieved.

## Research method and confidence

This is a targeted evidence review, not a preregistered systematic review. Searches prioritized arXiv, then followed primary publications and citations into ACM TOCHI, CHI, DIS, TACCESS, vision science, ophthalmology, and dyslexia research. Search themes included font personalization, serif/sans comparisons, print size and x-height, spacing and line length, comprehension, comfort, visual fatigue, and dyslexia fonts. Font provenance was checked against publishers, designers, project repositories, and license texts. Retrieval was completed on 2026-10-01.

Methods and results were read in actual papers, including author-hosted ACM manuscripts, arXiv PDF/HTML, the original journal's PDF for the line-length experiment, and full-text PMC/Europe PMC articles. Author manuscript front pages sometimes retain submission-year placeholders; the publication identity is taken from the final DOI rather than a placeholder. The evidence below identifies whether a source is a peer-reviewed study, review, or preprint. Abstract-only findings and inaccessible presentation slides were not used to assign the default.

Relevant arXiv work includes AdaptiFont, THERIF, and SituFont. Much of the strongest controlled evidence on vision, size, and dyslexia is published outside arXiv. Availability on arXiv is an access route, not a quality ranking. THERIF's detailed source is an extended arXiv manuscript associated with CHI 2023 Late Breaking Work. SituFont's January 2026 arXiv revision reports conditional acceptance to CHI 2026; final publisher status was not independently confirmed. The review did not locate an independently verified, controlled long-reading trial directly comparing Source Serif 4, Source Sans 3, Literata, and Atkinson Hyperlegible Next. This is a search limitation, not proof that no such study exists.

The most secure conclusions are narrower than a font ranking: small text can limit fluent reading; equal point or pixel sizes do not equalize visible letters; typography effects can vary across readers; and speed, comprehension, subjective comfort, and fatigue are different outcomes. Confidence is lower in transferring brief, easy-text experiments to sustained reading of technical research on current devices.

## Primary evidence

### Individual differences and personalization

Wallace et al., 2022, ACM TOCHI: "Towards Individuated Reading Experiences." [Actual author manuscript](https://shaunwallace.org/files/Readability__TOCHI.pdf), [publication DOI](https://doi.org/10.1145/3502222).

The analyzed sample was 352 US online adults, ages 18–71, after 30% participant filtering. Each read five of 16 fonts, with two short passages per font and comprehension questions. Reading/learning disabilities were excluded; apparent font sizes were perceptually normalized. Mean observed individual fastest, slowest, and preferred-font speeds were 314, 232, and 275 WPM, respectively: the reported fastest/slowest difference is 35%, and fastest/preferred difference 14%. No font benefited everyone. Preferred fonts were the observed fastest for about 20% of participants.

Limits. five fonts per reader, sparse timing observations, easy passages, remote devices, and a largely young sample constrain transfer. Statistical caveat. choosing each person's maximum and minimum from the same noisy observations enlarges their separation. These extrema are not a fair held-out comparison against a default, and the 35% is not a validated expected gain for a new reader. The study did not test sustained fatigue or this candidate portfolio.

Cai et al., 2022, ACM DIS: "Personalized Font Recommendations." [Actual paper](https://jeffhuang.com/papers/PersonalizedFont_DIS22.pdf), [publication DOI](https://doi.org/10.1145/3532106.3533457).

Of 500 recruited adults, 252 remained after filtering. Each read eight fonts at 16px, not normalized for apparent size; eight eighth-grade passages were split into four 34–47-word screens each. Georgia was individually fastest for 46 people (18.3%), Arial for 45 (17.9%); neither was a majority winner. Only 76/252 preferred their observed fastest font. The population model found no significant font effect. The model's cross-validation results reported improvements of 25.6 WPM over preferred fonts, 14.8 over Arial, and 14.4 over Georgia.

Limits. 49.6% filtering, easy material, mostly younger adults, restricted devices, and correlated font attributes limit generalization and causal interpretation. The study tested Source Serif Pro, not Source Serif 4; a thin-stroke association at that size is not proof that Source Serif 4 will underperform. Comfort and sustained fatigue were not measured. Predictions require independent validation before becoming product claims.

Kadner, Keller, and Rothkopf, 2021, CHI/arXiv: "AdaptiFont." [Actual arXiv paper](https://arxiv.org/pdf/2104.10741), [publication DOI](https://doi.org/10.1145/3411764.3445140).

Eleven young German-speaking university participants, mean age 24, read approximately 95 short texts while a Bayesian procedure explored generated fonts. Texts were about 100 words; readers also detected target-category words and answered occasional comprehension questions. The procedure found different high-speed regions for different people, supporting the feasibility of individual font search.

Limits. a small, homogeneous sample, generated rather than production fonts, a dual task, and comparisons with a preliminary study constrain deployment claims. This is a personalization prototype, not proof of a named font's superiority or a sustained-comfort benefit.

Cai et al., 2023, CHI Late Breaking Work / extended arXiv manuscript: "THERIF." [Actual extended paper and appendices](https://arxiv.org/html/2303.04221), [version record](https://arxiv.org/abs/2303.04221), [first-party publication record](https://research.adobe.com/publication/therif-themes-for-readability-from-iterative-feedback/).

An iterative process involved 485 participants, after pilots involving 271. A separate performance evaluation retained 140 readers: 72 screened/self-reported as dyslexic and 68 without dyslexia. They read 150–250-word passages in three coordinated font-and-spacing themes and an Arial control. At least one theme was rated at least as comfortable as control by 91%; 61% rated one strictly more comfortable. There was no simple overall theme winner across speed, comprehension, and comfort. A later 25-person subset provided limited evidence of consistency on harder passages.

Limits. the approximately 30-minute session contained brief passages, rather than continuous long-form reading. Font, size, and spacing changed together, so no component's causal benefit is isolated. The study's weighted aggregate outcome is not a validated fatigue measure. Its unusually spacious themes, including a 4.5 line-height option, do not establish desirable defaults. This is useful evidence for offering options and measuring comfort separately.

Chen et al., 2024/2026, arXiv: "SituFont." [Actual January 2026 revision](https://arxiv.org/html/2410.09562v2), [version and acceptance-status record](https://arxiv.org/abs/2410.09562).

The project used 15 formative interviews, an 18-person exploratory study, and a 12-person evaluation of contextual font adjustment. The evaluation involved native Mandarin readers aged 18–34, a four-day adaptation period, and eight simulated combinations of lighting, movement, distraction, and fatigue. The revised methods specify two 50-character passages per condition, read-aloud goodput, and separate comprehension questions. Goodput improved in six of eight paired condition comparisons at the conventional unadjusted significance threshold; comprehension differences were not significant.

Limits. small samples, very short oral tasks, multiple comparisons, possible comprehension ceiling effects, one script, and artificial contexts prevent transfer to a Latin font ranking or a claim of reduced long-term fatigue. It suggests that reading circumstances can matter; it does not require automatic sensing or behavior collection in Antiek.

### Serif/sans distinctions and visual requirements

Arditi and Cho, 2005, Vision Research: "Serifs and font legibility." [Actual manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC4612630/), [publication DOI](https://doi.org/10.1016/j.visres.2005.06.013).

Custom fonts isolated serif size at 0%, 5%, and 10% of cap height, and varied spacing separately. Acuity tests used four normally sighted and two low-vision participants; RSVP and continuous-reading experiments each used four readers. Serifs did not significantly change reading speed. A tiny acuity benefit at intermediate serif size was plausibly attributable to the extra spacing needed for serifs.

Limits. one artificial font design and very small samples cannot establish universal equivalence, especially for low vision. Continuous reading used scrambled words on paper, while RSVP used brief sentences and an unusually high tolerated error rate. This is stronger evidence against a broad serif mechanism claim than against every possible difference between complete typefaces.

Mansfield, Legge, and Bane, 1996, IOVS: "Psychophysics of Reading XV." [Actual paper](https://legge.psych.umn.edu/sites/legge.psych.umn.edu/files/files/media/mansfield96_psychophysics_of_reading_xv-_font_effects_in_normal_and_low_vision.pdf), [PubMed record](https://pubmed.ncbi.nlm.nih.gov/8675391/).

MNREAD tests compared Times and Courier in 50 normally sighted and 42 low-vision readers. Maximum speed was approximately 5% higher with Times for normal vision, but approximately 10% higher with Courier for low vision. At sizes near critical print size, Times could be substantially slower; Courier supported smaller reading thresholds.

Limits. two fonts, printed oral-reading tests, older rendering, and different glyph dimensions prevent a general serif/sans or monospace recommendation. The relevant inference is that population and print size can change a font comparison's direction.

Xiong et al., 2018, IOVS: "Fonts Designed for Macular Degeneration." [Actual paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC6100668/), [publication DOI](https://doi.org/10.1167/iovs.18-24334).

Digital MNREAD tests involved 19 readers with macular degeneration, 14 age-matched controls, and 26 young controls. Five fonts included two designed for macular degeneration. Those designs helped some small-print acuity measures compared with Helvetica/Times, but did not outperform Courier on those measures. Although maximum-reading-speed font effects were significant overall in the macular-degeneration group, post-hoc pairwise comparisons were not significant.

Limits. brief oral reading and threshold measures differ from long-form comprehension and fatigue. Distinctive or specially designed letters should not be assumed to yield the fastest complete-text reading. This paper did not test either Atkinson family.

### Size, x-height, spacing, and line length

Legge and Bigelow, 2011, Journal of Vision: "Does print size matter for reading?" [Actual review](https://pmc.ncbi.nlm.nih.gov/articles/PMC3428264/), [publication DOI](https://doi.org/10.1167/11.5.8).

This review combines typography and vision experiments, rather than presenting one new trial. Normally sighted fluent reading often occupies a broad angular-x-height range of about 0.2°–2°. At 40cm, that corresponds to an x-height of roughly 1.4–14mm, not a body-size prescription. Below an individual's critical print size, speed can decline sharply; requirements increase with visual impairment.

Limits. a broad physiological speed plateau is not an aesthetic or comfort optimum. CSS pixels, viewing distance, device scaling, and each font's x-height prevent conversion to one universal interface size. X-height is useful to measure, but it does not describe all dimensions readers perceive.

Rello, Pielot, and Marcos, 2016, CHI: "Make It Big!" [Actual paper](https://www.pielot.org/pubs/Rello2016-Fontsize.pdf), [publication DOI](https://doi.org/10.1145/2858036.2858204).

The study involved 104 volunteers aged 14–54, mostly in higher education, reading short Spanish Wikipedia sections in Arial on a 17-inch 1024×768 monitor at 60cm. Six sizes ranged from 10 to 26 points. Larger sizes shortened fixation duration; comprehension favored some larger sizes, with no further objective improvement beyond 22pt. Reading speed was deliberately not measured. Very tight and very wide line-spacing conditions reduced comprehension.

Limit and unit correction: the recommended 18 was 18pt, not 18px. Its line-spacing multiplier of 1.0 meant the browser's 120% normal spacing; the tested multipliers therefore do not map directly to identically numbered CSS line heights. Short sections, fixed hardware, and eye-movement outcomes do not establish Antiek's 20px/1.65 optimum or a fatigue benefit.

Dyson and Kipping, 1998, Visible Language: "The Effects of Line Length and Method of Movement on Patterns of Reading from Screen." [Actual journal paper](https://journals.uc.edu/index.php/vl/article/download/5671/4535/7348), [journal record](https://journals.uc.edu/index.php/vl/article/view/5671).

The experiments compared 25, 55, and 100 characters per line, with scrolling and paging. Longer lines could be read faster without a comprehension difference, while 55-character lines were subjectively easiest and 100-character lines least liked. The second experiment used 24 participants; after separating scrolling time from reading time, its line-length speed effect was not significant.

Limits. older displays and navigation mechanics affect transfer. Speed and perceived ease disagreed, and navigation was part of the measured cost. The paper supports treating width as a tradeoff rather than declaring 66 characters universally optimal. Also, CSS `ch` is not a literal count of proportional-font characters.

### Dyslexia: font labels and spacing are separate questions

Rello and Baeza-Yates, 2016, ACM TACCESS: "The Effect of Font Type on Screen Readability by People with Dyslexia." [Actual paper](https://www.changedyslexia.org/publications/pdfs/2016-TACCESS-The%20E%EF%AC%80ect%20of%20Font%20Type.pdf?v1.5.15=), [publication DOI](https://doi.org/10.1145/2897736).

Ninety-seven Spanish readers, 48 with dyslexia and 49 controls, read twelve approximately 60-word texts in twelve fonts, at 18pt. Sans, monospaced, and roman styles produced shorter fixations for the dyslexic group, but the discussion reports no significant reading-time benefit for these style comparisons. OpenDyslexic was not a unique performance or preference winner; italics were less favorable.

Limits. fixation duration is not reading speed or sustained fatigue. Apparent sizes were not equalized, texts were brief, and language/population specificity matters. The related 2013 ASSETS paper is not counted here as an independent replication. This supports offering suitable conventional alternatives rather than assigning a special font to every dyslexic reader.

Kuster et al., 2018, Annals of Dyslexia: "Dyslexie font does not benefit reading in children with or without dyslexia." [Actual paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC5934461/), [publication DOI](https://doi.org/10.1007/s11881-017-0154-6).

Experiment 1 compared printed Arial and Dyslexie texts in 170 Dutch children diagnosed with dyslexia, ages 7–12, across sessions one to two weeks apart. Experiment 2 used 102 children with dyslexia and 45 controls, comparing word lists in Dyslexie, Arial, and Times New Roman. Dyslexie did not improve speed or accuracy. Preference was not a reliable performance guide.

Limits. oral reading in children and printed material differ from adult digital reading. The attempted size matching was imperfect, and horizontal spacing was not fully controlled. The result does not invalidate a person's preference or prove that every accessibility-oriented font is ineffective.

Zorzi et al., 2012, PNAS: "Extra-large letter spacing improves reading in dyslexia." [Actual paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC3396504/), [publication DOI](https://doi.org/10.1073/pnas.1205566109).

Seventy-four Italian and French dyslexic children, ages 8–14, read short printed sentences aloud. Adding 2.5pt inter-letter spacing to 14pt Times reduced errors and increased speed. A 20-person follow-up that controlled line spacing found 1.87 versus 1.64 syllables/second and approximately 6 versus 11.8 errors for spaced versus normal text.

Limits. this is evidence for a particular spacing intervention in children, not a named dyslexia font or a treatment claim. Short sentences, line layout, and differing spacing magnitudes matter; transfer to sustained adult screen reading needs testing.

Galliussi et al., 2020, Annals of Dyslexia: "Inter-letter spacing, inter-word spacing, and font with dyslexia-friendly features." [Actual paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC7188700/), [publication DOI](https://doi.org/10.1007/s11881-020-00194-x).

The study used 128 Italian children, 64 dyslexic and 64 controls, with a factorial manipulation of letterforms, letter spacing, and word spacing across eight equivalent texts. Dyslexia-oriented letterforms did not confer a reading benefit. Wider letter spacing did not provide a general speed advantage; increasing it without sufficient word separation could slightly impair speed.

Limits. children, oral reading, and the tested intervention range constrain generalization. Together with the positive spacing study, this favors optional, coordinated spacing adjustment and clear word boundaries. It does not justify widening every reader's letters or treating all spacing studies as contradictory replications of identical conditions.

### Fatigue, comprehension, and polarity

Benedetto et al., 2013, PLOS ONE: "E-Readers and Visual Fatigue." [Actual paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0083676).

Twelve readers completed repeated sessions on LCD, e-ink, and paper, averaging 73 minutes, with layout controlled and sessions separated by ten days. LCD produced greater subjective fatigue and some blink-related differences than the other media; reading-speed differences were not significant.

Limits. the sample was small and the 2013 device conditions, including brightness settings, constrain transfer to current screens. It compares media, not this font portfolio. Its useful lesson is methodological: unchanged speed does not imply unchanged fatigue, and a short font-speed task cannot substantiate a long-reading fatigue claim.

Palmén, Gilbert, and Crossland, 2023, CHI: "How bold can we be?" [Actual paper](https://thereadabilityconsortium.org/wp-content/uploads/2023/07/How-bold-can-we-be-The-impact-of-adjusting-font-grade-on-readability-in-light-and-dark-polarities-1.pdf), [publication DOI](https://doi.org/10.1145/3544548.3581552).

Separate glance and paragraph studies involved 126 and 333 participants, respectively. The phone paragraph task used Roboto Flex and approximately 100-word passages. Light polarity was faster for paragraph reading; varying font grade did not significantly improve paragraph speed. Polarity preferences were mixed.

Limits. glance effects do not transfer automatically to paragraphs; brief passages do not establish sustained comfort or nighttime fatigue. Offer polarity choice without describing dark mode or heavier type as a universal fatigue intervention.

Delgado et al., 2018, Educational Research Review: "Don't throw away your printed books." [Actual meta-analysis](https://doi.org/10.1016/j.edurev.2018.09.003).

This synthesis included 54 studies and 171,055 participants. It found a small paper advantage for comprehension, approximately Hedges' g = 0.21, especially for informational material and time-constrained tasks; the pattern differed for narrative-only material.

Limits. heterogeneous reading media and study conditions do not isolate font effects or evaluate Antiek. Typography can improve the reading experience, but this evidence does not show that typography alone closes a medium-related comprehension gap. Claims that the product makes screen reading cognitively equivalent to paper remain untested.

## What the evidence means for this candidate

The portfolio is justified by variability and user agency, not by an assumption that every reader needs a different font or that a preference preview discovers the fastest font. A speed-optimized recommendation would need repeated, held-out measurement. Preference is still a valid reason to choose a comfortable appearance even when it does not predict speed.

The serif/sans distinction is too coarse to decide performance: complete fonts also change proportions, stroke contrast, spacing, x-height, and familiarity. Source Serif 4's default position follows the product's reading identity. No empirical result above licenses transferring an Arial, Georgia, Times, Source Serif Pro, or custom-font ranking to it.

"Legibility" should mean distinguishing letters or reading at a threshold when that is what an experiment measured. "Readability" should identify its actual measure: WPM, accuracy, comprehension, comfort rating, or fatigue. Antiek should not substitute a fixation result, an OCR benchmark, or a designer's purpose statement for demonstrated human long-form benefits.

## Candidate comparison

| Candidate | Role and rationale | Evidence boundary |
| --- | --- | --- |
| Source Serif 4 | Default. Restrained book texture, warmth, and conventional italics fit sustained research prose and the existing serif convention. Optical-size designs give an appropriate text-oriented rendering path. | This is our design and engineering judgment. Adobe's [designer account](https://blog.adobe.com/en/publish/2021/03/04/source-serif-gets-optical-sizes) explains reworked proportions, spacing, kerning, and five optical-size designs. The changes are another reason not to transfer Source Serif Pro's results directly. No directly verified long-reading comparison establishes superiority. |
| Source Sans 3 | Alternative for the simplest contemporary reading appearance. Its relatively quiet forms also suit interface labels, making the reading/UI pairing coherent. | The [upstream project](https://github.com/adobe-fonts/source-sans/blob/release/README.md) identifies UI use as a design purpose. That is not a long-form performance trial. Its apparent size must be checked alongside the serif default. |
| Literata | A more expressive book-reading alternative with optical sizing; useful for readers who want a stronger editorial texture. | [TypeTogether's first-party account](https://www.typetogether.com/custom-fonts/literata-3-0) describes its Google Books commission and continuous digital-reading purpose. Those design goals do not quantify fatigue or prove a general advantage. Its distinctive texture makes it an alternative rather than the simplest default. |
| Atkinson Hyperlegible Next | A clear-form sans alternative for readers who value distinguishing similar characters. Evaluate actual paragraphs as well as samples such as `Il1`, `0O`, and numerals. | The [Braille Institute](https://www.brailleinstitute.org/freefont/) and [upstream project](https://github.com/googlefonts/atkinson-hyperlegible-next) explain character differentiation. A [CSUN 2024 exhibitor presentation](https://www.csun.edu/cod/conference/sessions/2024/index.php/public/presentations/view/3108.html) advertises a quantitative study of the original family, but its protocol/slides were not retrieved. It is not independent evidence for Next. Do not label Next a proven dyslexia font. |
| Classic, using installed Georgia or a system serif | Familiar book appearance and a useful local-font option. Georgia is a reasonable first choice where installed. | [Microsoft's account](https://learn.microsoft.com/en-us/typography/font-list/georgia) describes its screen-oriented design. Its favorable observations in Cai's experiment are limited to that experiment's fonts, sizes, and readers. A system stack can resolve differently across platforms; name the option Classic rather than promise identical Georgia rendering. |
| Charter | Credible warm, compact book face for a future comparison. | No controlled long-reading comparison was verified in this review. "Charter" can refer to different builds and licenses. The [original notice in the CTAN Type 1 distribution](https://mirrors.ibiblio.org/CTAN/fonts/charter/readme.charter) permits broad use with notice/trademark conditions; that does not license arbitrary Apple or modern commercial binaries. Pin and inspect a specific distribution before bundling. |
| Bookerly | A relevant reference for warm digital-book typography, not a bundled candidate. | Amazon's [2015 Kindle announcement](https://press.aboutamazon.com/2015/6/amazon-introduces-new-kindle-paperwhite-the-most-popular-kindle-now-even-better-still-only-119) makes reading and fatigue marketing claims without a disclosed controlled protocol. A downloadable file or font installed on a device is not evidence of general redistribution permission. No independently verified academic trial or suitable general-purpose embedding license was located. |

The portfolio labels should describe appearance or the family name. Avoid rankings such as fastest, healthiest, dyslexia-safe, and fatigue-free. Retain real upright and italic faces, appropriate weight selection, and text optical sizing where supported. These are typography-quality requirements, not promised cognitive effects.

## Practical layout settings

The initial 20px / 1.65 / 66ch combination aims for a readable, quiet page with enough leading for multi-paragraph research prose. The size is a modest nominal increase from the current main reader's 19px prose baseline, intended to avoid shrinking its reading experience. Actual apparent size remains font-dependent and must be inspected on desktop and phone viewports with the intended fonts loaded. A bounded width can shrink to the available viewport; it must not cause horizontal scrolling of prose. The 66ch cap is approximate: [`ch` measures the advance of the font's zero glyph](https://www.w3.org/TR/css-values-4/#font-relative-lengths), not 66 letters of arbitrary proportional text. Actual line lengths will change across families and content.

Equal CSS font sizes are a convenient product control, not a fair scientific normalization. Check actual x-height, cap height, line wrapping, and perceived size when switching fonts. Any per-family adjustment should be explicit, visually inspected, and recorded. Do not silently equate a nominal point size, CSS pixel size, x-height, or physical size. CSS fixes the ratio at [1pt = 4/3px](https://www.w3.org/TR/css-values-4/#absolute-lengths); the physical reading size still depends on scaling and viewing conditions.

Leave ordinary letter and word spacing as the initial setting. Offer a coordinated roomier option or controls if supported, with enough word separation and sensible wrapping. The mixed dyslexia-spacing results support choice rather than universal tracking. A person should be able to enlarge text without being forced into another font, and choose width/leading without losing claims, links, annotations, or controls.

[WCAG 2.2 text spacing](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html) requires that applicable content tolerate user overrides to line height 1.5, paragraph spacing 2em, letter spacing 0.12em, and word spacing 0.16em without loss of content or functionality. It does not require those values as the authored default, and it does not certify a font's reading performance. Check overrides together, alongside zoom, reflow, selection, and keyboard operation. Product typography changes must preserve semantic HTML and assistive-technology access.

Use low-friction font previews in real paragraphs, rather than presenting isolated lettering as proof. Keep a direct reset and preserve choices locally according to the product's existing preference conventions. A new default should apply to readers who have not selected a preference. UI controls and labels need their own compact sizing; body-reading settings should not expand every navigation element indiscriminately.

## Font provenance and full licenses

The notices below permit use, embedding, and redistribution under OFL 1.1 conditions. Bundled font software must retain the complete copyright notice and full license text; a link, abbreviated comment, or generic "open source" label is insufficient for the distribution record. Modified versions must respect any reserved font names. Notice differences matter: the Adobe release-branch notices inspected declare Source as a reserved font name. The adjacent Google Fonts Source Serif 4 OFL.txt names the Source Serif 4 Project Authors and declares no reserved font name. The actual bundled v4.004 binary embeds a 2014-2021 Adobe copyright and reserves Source. The Source Sans v3.052 binary embeds a 2023 Adobe copyright and reserves Source, while its adjacent OFL.txt has a 2010-2020 Adobe notice. Both complete external licenses and embedded binary notices are retained; the fonts are unmodified. Do not transfer a notice from one distribution to another based only on family name.

| Family | First-party repository | Inspected full notice for this candidate's Google Fonts distribution |
| --- | --- | --- |
| Source Serif 4 | [Adobe Source Serif](https://github.com/adobe-fonts/source-serif) | [Pinned OFL.txt, 2014 Project Authors notice, no declared reserved name](https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/sourceserif4/OFL.txt); compare the different [Adobe release notice](https://raw.githubusercontent.com/adobe-fonts/source-serif/release/LICENSE.md). |
| Source Sans 3 | [Adobe Source Sans](https://github.com/adobe-fonts/source-sans) | [Pinned OFL.txt, 2010–2020 Adobe notice, reserved name Source](https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/sourcesans3/OFL.txt) |
| Literata | [Literata project](https://github.com/googlefonts/literata) | [Pinned OFL.txt, 2017 Literata Project Authors notice](https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/literata/OFL.txt) |
| Atkinson Hyperlegible Next | [Atkinson Hyperlegible Next project](https://github.com/googlefonts/atkinson-hyperlegible-next) | [Pinned OFL.txt, 2020–2024 Atkinson Hyperlegible Next Project Authors notice](https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/atkinsonhyperlegiblenext/OFL.txt) |

Implementation provenance should record the exact source URL, release or commit, downloaded version/name metadata, file hashes, formats, subsets, covered scripts, weights, italic support, variable axes, and the path to each complete license. The pinned notice revision is not itself an immutable font-binary identifier; use the asset manifest for that evidence. Record conversion or subsetting if performed, and retain the notice applicable to the actual obtained distribution. Check loading failures and fallback rendering; keep the page usable while fonts load. A system serif option may use an installed font without adding its binary to the application.

The implementation record below links the actual asset manifest, full notices, loading measurements, and verification evidence.

## Feasible validation before making benefit claims

Run a small, consented crossover pilot with roughly 24–36 readers drawn from the intended research-reading audience. Include older readers and invite readers with dyslexia or low vision, while reporting those groups separately and avoiding underpowered subgroup promises. The sample is a feasibility target, not a power calculation or a population-representative study.

1. Primary comparison: Source Serif 4 versus Source Sans 3. Randomize order and counterbalance matched unfamiliar research reports across fonts, so a person does not reread the same material. Pilot report length to produce approximately 20–40 minutes of natural reading. Use separate sessions where possible, matching device, brightness, zoom, ambient conditions, and time of day. Record prior topic knowledge and any departures from these conditions.
2. Measure the intended outcome: collect baseline and post-reading visual discomfort/tiredness with the same prespecified symptom questions and response scale. Ask about ease and willingness to continue separately. Keep appearance preference separate from discomfort. Record duration; a shorter exposure can affect fatigue. Do not treat a new composite score as a validated clinical measure.
3. Protect comprehension: use substantive literal and inferential questions, prepared and scored without knowledge of font assignment. Match difficulty and report topic across conditions; avoid a few easy questions that all participants answer correctly. Record completion, attention interruptions, and reading speed as secondary outcomes. A faster condition with worse comprehension is not an uncomplicated improvement.
4. Analyze fairly: prespecify the primary paired comparison and report the paired effect with uncertainty, distributions, and individual variation. Account for report and order effects. Report exclusions and missing data rather than removing slow or low-comprehension readers to improve the result. Avoid dozens of subgroup tests. Set a meaningful comprehension tolerance with the research owner before examining results; estimate variance in this pilot before planning a confirmatory sample.
5. Validate personalization separately: if readers then try Literata, Atkinson, or Classic, treat that phase as exploration. Choose a promising option using one session and retest it on different material on another day. Compare against the default on held-out observations. Do not publish a maximum-minus-minimum result as a predicted personalization benefit.
6. Check real use: allow a subsequent voluntary week of long-form reading with the portfolio. Collect brief opt-in comfort and comprehension feedback without uploading reading content or inferring diagnoses. Record which font/settings were used and any switch back. Technical telemetry and a preference count alone cannot establish reduced fatigue.

Control both the practical product comparison and its interpretation. Keeping the shipped 20px setting in both fonts answers which shipped experience works better; normalizing apparent size in an additional comparison helps distinguish size from family. Neither design should be quietly substituted for the other. Results should identify the device, script, report difficulty, duration, and settings to which they apply.

Until this is done, a defensible claim is that Antiek offers a considered reading layout and font choices. "Reduces visual fatigue," "improves comprehension," "reads 35% faster," and "best font for dyslexia" are unsupported for this candidate.

## When to reconsider the default

Revisit Source Serif 4 if sustained, counterbalanced testing finds meaningfully better comfort with another candidate while maintaining comprehension; if repeated real-reader complaints reveal apparent-size, stroke, or rendering problems; or if the required language coverage, licensing, or loading costs are unsuitable. Inspect failures in the actual shipped assets before drawing conclusions about the family. A broader script portfolio needs its own typographic and reading assessment; evidence from Latin and Chinese studies is not interchangeable.

The default can also change if the product's intended reading identity changes. Record that as a product decision rather than inventing an empirical reason. Any replacement must preserve existing reader preferences and keep the original evidence boundaries visible.

## Implementation and verification record

The separate candidate is in `design/reading-typography-20261001`, based on product commit `b21200200fdace1ec3b7ed0e1a8bde683cd4d81e`. The candidate is published as PR #3603, with release checks recorded in the handoff. The palette/mascot candidate remains a separate lane, as requested. The full [handoff and gate record](../evidence/reading-typography-20261001/README.md) includes the environment, bounded scope, complete logs, visual evidence, review findings, and limitations.

### Reader behavior

The book reader and research manuscript share the same versioned, validated preference store. The Type button opens a labeled dialog for native reading text; Appearance settings expose the same controls. Source-link-only arXiv views omit the type trigger because Antiek does not control that external text. Font, size, line height, line width, and letter spacing apply immediately. Choices persist locally, synchronize between tabs, survive surface remounts, and reset to Source Serif 4 at 20 nominal CSS pixels, 1.65 leading, 66ch width, and natural tracking. Size uses rem units so a larger browser base size is respected. Corrupt or unsupported stored data falls back per field; blocked storage retains the live choice for the current tab.

The picker offers Source Serif 4, Source Sans 3, Literata, Atkinson Hyperlegible Next, and Classic system serif. Reading type applies to the prose; controls retain the existing interface typography. Research thesis, claims, rationale, and appendix inherit the selected body size and leading; compact citation/audit labels remain compact. Code remains monospaced. Existing sanitized HTML rendering, source gates, attribution markers, logical pages, and text-anchored highlights remain attached to the same material.

The book body's earlier max-w-3xl wrapper no longer caps the chosen prose width. Width choices use 52/66/78ch, bounded by the available pane. These are zero-glyph width units, not literal character counts. In the desktop Source Serif fixture at 20px the rendered widths were 520/660/780px. A phone cannot provide a wide desktop line, so the choices converge at the available width there. Controls stack when their own container is at most 16rem wide, rather than relying only on the outer viewport. Dialog controls and Close have a 44px minimum target at the tested base size.

Typography changes and completed font loads refresh passage/widget geometry even when the root rectangle does not resize. Book-island and manuscript regressions cover this case and event cleanup; a temporary-copy mutation that removed these refreshes made both new regressions fail.

### Exact font distribution

[Asset manifest](../../apps/reading/public/fonts/reading/manifest.json) records the original immutable asset URLs, SHA-256 hashes, unchanged Google-distributed Unicode subsets, weights, styles, variable axes, version/name metadata, and embedded copyrights. [Vendor script](../../apps/reading/scripts/vendor_reading_fonts.py) has an offline integrity check and a locked-download reproduction command; `--refresh` deliberately replaces the lock using current Google CSS and requires review. No font conversion, custom subsetting, renaming, or outline editing was performed. The application has no new package dependency. Install the separate vendor/check tooling from the frontend directory with `python3 -m pip install -r scripts/reading_fonts_requirements.txt`; fontTools and Brotli versions are pinned there.

| Family | Bundled version | Axes | Full adjacent license |
| --- | --- | --- | --- |
| Source Serif 4 | 4.004 | wght 200–900; opsz 8–60; separate italic | [OFL](../../apps/reading/public/fonts/reading/source-serif-OFL.txt) |
| Source Sans 3 | 3.052 | wght 200–900; separate italic | [OFL](../../apps/reading/public/fonts/reading/source-sans-OFL.txt) |
| Literata | 3.103 | wght 200–900; opsz 7–72; separate italic | [OFL](../../apps/reading/public/fonts/reading/literata-OFL.txt) |
| Atkinson Hyperlegible Next | 2.001 | wght 200–800; separate italic | [OFL](../../apps/reading/public/fonts/reading/atkinson-OFL.txt) |
| Classic system serif | Installed device font | Device dependent | No binary distributed |

The complete external notices come from Google Fonts commit `9710da1eacb3be272583c3224dcb70f9da6eadbb`. They do not replace embedded notices. Source Serif's actual binary reserves Source and embeds a 2014–2021 Adobe copyright despite the different adjacent Project Authors notice. Source Sans embeds a 2023 Adobe copyright and reserves Source, despite its adjacent 2010–2020 notice. Both are preserved and recorded in each binary's manifest metadata. The Google notice's lack of a Source Serif reservation is not evidence that the binary has no reserved name.

All 44 WOFF2 files total 2,065,532 bytes; the eight Latin faces total 604,720 bytes. Default Latin Source Serif regular and italic are 122,360 and 130,188 bytes respectively. The four custom families load from the application's own font path, with font-display swap, retained Unicode ranges, true italics/bold, and optical sizing for the serif families. The reader requests the selected face/subsets as needed; the visual portfolio deliberately renders every family. No cross-family claim about full script coverage follows from these sizes.

### Verification outcome

The final focused suite passed 355 tests across 33 files, including existing book-reader/attribution/anchor behavior, settings, the research manuscript, new preference boundaries, failed-load guidance, and geometry regressions. Type checking, production build, token lint, type-scale lint, offline asset checking, and fresh locked-download reproduction passed. The build retains a large-chunk warning; React Doctor's changed-scope scan reports the existing BookReader complexity warning. A source-context baseline comparison shows the same 84/100 score and existing full-file findings, with no new findings in this candidate. These are bounded diagnostics, not whole-product release approval.

Real Chrome inspection covered the same paragraph across all five families, genuine regular/italic/bold glyphs, a persisted choice after reload, desktop width differences, manuscript body inheritance, 320×568 and 390×844 controls, keyboard focus return/wrap, and dark settings with reduced-motion emulation. Blocking Literata's Latin requests on a fresh load left the passage readable in installed Georgia and exposed recovery guidance. [Portfolio](../evidence/reading-typography-20261001/portfolio.png), [mobile controls](../evidence/reading-typography-20261001/type-mobile.png), and [research note](../evidence/reading-typography-20261001/manuscript-desktop.png) are inspection artifacts, not reading-performance experiments.

Not proved: sustained fatigue reduction, better comprehension than print, a universally easiest font, or the proposed human study. Safari/Firefox rendering, full screen-reader behavior, every script subset, live backend/provider paths, and integration with the separate palette branch were not verified here.

### Release review corrections

The visible trigger is now Type, so a future composition with the separate palette control has distinct entry points. The font availability message probes regular Latin loading; italic and other script fallback remain readable but are not individually diagnosed. Integration with the palette branch must be verified on whichever candidate lands second. PR #3603 is currently a standalone typography change against main; no combined-palette verification is claimed.
