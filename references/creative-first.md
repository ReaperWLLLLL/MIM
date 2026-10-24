# Creative-first Manim workflow

Use a visual explanation to resolve an audience question. Preserve the user's format, source, style and scope choices. A silent sample need not acquire narration, a new schema or a general rendering subsystem.

## Design the explanation

Read the relevant source and existing scenes first. For new material, a new section or a materially changed explanation scope, brainstorm the unresolved communication choices with the user before selecting the example and authoring scenes. Use an installed brainstorming skill when available; the conversation below is sufficient when it is not.

Ask one consequential question at a time, using what the source and prior conversation already establish. Find out what the speaker wants the audience to understand: a contribution, mechanism, result, comparison or practical process. For a research presentation, identify the main claim, the audience's background and the evidence supporting the claim. Choose the central object accordingly: the actual method, a result comparison, a real system or a worked example. When an example is useful, discuss its scale and features. Propose alternatives with their explanatory tradeoffs and let the user choose.

Keep a short agreed brief, not a new schema:

- audience, main message and intended depth;
- central objects, evidence or examples, including relevant scale and structural features;
- simplifications, and what they preserve or remove;
- explanation tone, notation conventions and [visual style](visual-styles.md).

Identify which choices the user confirmed and which they explicitly delegated. An accepted palette, praise for an earlier animation, permission for full generation or relaxed QA does not answer an unresolved content-design question. If the user explicitly delegates content selection, state the proposed choice and reason in the brief, then proceed. For wording/layout edits within a confirmed brief, reuse it without another conversation.

For each scene, write a short note stating the audience's difficulty, the object followed, the operation and the resulting understanding. Minimal visual style controls emphasis and clutter, not problem complexity. Use focus, staged disclosure, selected matrix blocks or camera motion to make a suitably rich example readable. A small opening example may introduce an operation; return to the actual method or system when that is the subject. A research-results talk can instead follow the experiment and the comparison it supports.

Choose the visual language for that operation. Vector addition can use moving arrows; a dependency can use a persistent connection; a formula can retain matching terms through a transform. Choose an order that serves the argument: a mechanism may need its quantities introduced first, while a results talk may open with an observed finding and then explain it. Keep illustrative data distinct from the speaker's measured results. Keep scientific assumptions accurate and introduce the working model once. Prepare screen copy using [copy-and-math.md](copy-and-math.md), keeping production/evidence commentary in notes.

## Make a representative sample

Build a short coherent scene that exercises the difficult explanation, using the established theme and semantic colors. A 20 to 30 second segment is often enough, but follow the content and the requested budget. Use native `Scene`, `MovingCameraScene` or `Slide` as appropriate. `Text`, `MathTex`, transforms, groups and camera motion are available without the registered-scene API.

Render into a new output directory at draft quality with the existing local environment. For example:

```bash
python -m manim -ql --disable_caching --media_dir build/sample-v01 src/sample.py ExplanatorySample
```

Use [native-manim.md](native-manim.md) for implementation; the legacy `DeckSlide` and strict `ResearchScene` APIs are not native-route prerequisites. For complete talks and long-form explanations, first map the substantive source coverage using [chapter-production.md](chapter-production.md).

Once the communication brief is confirmed or its open choices explicitly delegated, apply the agreed execution mode. Let the user judge the animation when review is requested or the visual direction is unresolved. For already authorized full production, inspect the representative segment and continue within that brief. Do not stop at a sample and call a full-talk task complete. A successful render is not human approval.

## Review in proportion to the task

Compare the actual scene content with the agreed brief: does it communicate the intended claim, preserve the evidence and retain the necessary scale and interactions? Check scientific meaning, direct explanatory text, typeset mathematics, continuity and useful pauses. Confirm decoding and inspect a few representative/crowded states. Deliberate superposition, vector assembly and glyph transformation are legitimate operations. Repair accidental occlusion or clipping.

State whether continuous playback was actually reviewed. Frame extraction and metadata do not prove pacing or explanatory clarity. Human approval remains separate from tool success. Keep notes short; default previews do not require all-frame traces, approval hashes, counterfactual test suites or independent audit agents.

The strict `research-video.md` tools remain available for an existing v0.2 project or a requested synchronized/provenance workflow. Their invariants still apply when using those tools. Use a native creative route rather than falsifying or bypassing their records.

## Extend and deliver

After the visual language works, extend the scene structure in sections and revise affected sections in place. Add requested narration and export formats afterward using [post-production.md](post-production.md). Keep original source files, cite research claims, use locally licensed fonts and report remaining limitations. Do not publish, push or install models without authorization.
