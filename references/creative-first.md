# Creative-first Manim workflow

Use a visual explanation to resolve an audience question. Preserve the user's format, source, style and scope choices. A silent sample need not acquire narration, a new schema or a general rendering subsystem.

## Design the explanation

Read the relevant source and existing scenes first. For new material, a new chapter or a materially changed teaching scope, brainstorm the unresolved teaching choices with the user before selecting the example and authoring scenes. Use an installed brainstorming skill when available; the conversation below is sufficient when it is not.

Ask one consequential question at a time, using what the source and prior conversation already establish. Find out what the audience must be able to understand or do, and whether the example should be an introductory mechanism sketch, a source-sized worked example or a practical multi-part system. Discuss the features the example needs, not just a node count. Once grounded, propose concrete alternatives with their teaching tradeoffs and let the user choose.

Keep a short agreed brief, not a new schema:

- audience and intended depth;
- primary example's scale and structural features;
- simplifications, and what they preserve or remove;
- explanation tone, notation conventions and [visual style](visual-styles.md).

Identify which choices the user confirmed and which they explicitly delegated. An accepted palette, praise for an earlier animation, permission for full generation or relaxed QA does not answer an unresolved content-design question. If the user explicitly delegates example selection, state the proposed choice and reason in the brief, then proceed. For wording/layout edits within a confirmed brief, reuse it without another conversation.

For each scene, write a short note stating the audience's difficulty, the object followed, the operation and the resulting understanding. Minimal visual style controls emphasis and clutter, not problem complexity. Use focus, staged disclosure, selected matrix blocks or camera motion to make a suitably rich example readable. A small opening example may introduce an operation; return to the agreed main case for its application.

Choose the visual language for that operation. Vector addition can use moving arrows; a dependency can use a persistent connection; a formula can retain matching terms through a transform. Introduce meaning before measurements. Keep scientific assumptions accurate and introduce the working model once. Prepare screen copy using [copy-and-math.md](copy-and-math.md), keeping production/evidence commentary in notes.

## Make a representative sample

Build a short coherent scene that exercises the difficult explanation, using the established theme and semantic colors. A 20 to 30 second segment is often enough, but follow the content and the requested budget. Use native `Scene`, `MovingCameraScene` or `Slide` as appropriate. `Text`, `MathTex`, transforms, groups and camera motion are available without the registered-scene API.

Render into a new output directory at draft quality with the existing local environment. For example:

```bash
python -m manim -ql --disable_caching --media_dir build/sample-v01 src/sample.py ExplanatorySample
```

Use [native-manim.md](native-manim.md) for implementation; the legacy `DeckSlide` and strict `ResearchScene` APIs are not native-route prerequisites. For whole lectures and chapters, first map the substantive source coverage using [chapter-production.md](chapter-production.md).

Once the teaching brief is confirmed or its open choices explicitly delegated, apply the agreed execution mode. Let the user judge the animation when review is requested or the visual direction is unresolved. For already authorized full production, inspect the representative segment and continue within that brief. Do not stop at a sample and call a whole-chapter task complete. A successful render is not human approval.

## Review in proportion to the task

Compare the actual example with the agreed brief: does it retain the intended scale, interactions and difficulty? Check scientific meaning, direct explanatory text, typeset mathematics, continuity and useful pauses. Confirm decoding and inspect a few representative/crowded states. Deliberate superposition, vector assembly and glyph transformation are legitimate operations. Repair accidental occlusion or clipping.

State whether continuous playback was actually reviewed. Frame extraction and metadata do not prove pacing or teaching effectiveness. Human approval remains separate from tool success. Keep notes short; default previews do not require all-frame traces, approval hashes, counterfactual test suites or independent audit agents.

The strict `research-video.md` tools remain available for an existing v0.2 project or a requested synchronized/provenance workflow. Their invariants still apply when using those tools. Use a native creative route rather than falsifying or bypassing their records.

## Extend and deliver

After the visual language works, extend the scene structure in sections and revise affected sections in place. Add requested narration and export formats afterward using [post-production.md](post-production.md). Keep original source files, cite research claims, use locally licensed fonts and report remaining limitations. Do not publish, push or install models without authorization.
