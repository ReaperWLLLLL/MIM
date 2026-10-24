# Manim authoring rules

Legacy v0.1 authoring. For v0.2 use the `ResearchScene` API in
[research-video.md](research-video.md): registered text/objects, fixed role sizes
and every-emitted-frame audits. The legacy fit/shrink and template helpers below
are not the research-video production contract.

## Scene mapping

For v0.1, prefer one `Slide` subclass per logical slide and keep the class name identical to `scene_class` in `deck.yaml`. Do not call `next_slide()` inside that class unless the specification intentionally maps each resulting segment as a separate deliverable slide.

Set `skip_reversing = True` for HTML, PPTX, and PDF workflows. Keep scene names stable so one slide can be re-rendered without invalidating the whole deck.

Keep every scene derived from the template `DeckSlide`. Its setup reads the matching `notes` from `deck.yaml`, writes them into the Manim Slides manifest, and isolates manifests by build profile. If replacing the base class, preserve this behavior or speaker notes will disappear from HTML and PPTX.

## Composition

- Use a 16:9 frame and reserve a 5% safe margin.
- Define typography, colors, stroke widths, and spacing in `src/theme.py`.
- Keep titles in a consistent region; allow deliberate full-frame exceptions.
- Prefer groups, alignment, and relative positioning over unexplained numeric coordinates.
- Shorten copy before shrinking it below the readable minimum.
- Keep citations and captions inside the safe area.
- Pass titles and long labels through a safe-width helper, then confirm the rendered final frame; source-code coordinates alone cannot prove that text is unclipped.

## Object identity

Reuse the same mobject when the audience should perceive continuity. Prefer `Transform`, `TransformMatchingTex`, or explicit state transitions over destroying one object and recreating an unrelated replacement.

Use consistent colors for stable concepts. Do not reuse the same accent color for different semantic roles within a sequence.

## Animation pacing

- Reveal objects in narration order.
- Use shorter motion for local attention shifts and longer motion for conceptual transformations.
- Avoid simultaneous unrelated motion.
- Add a stable pause after dense transformations and before the scene ends.
- At draft time, optimize clarity rather than cinematic smoothness.
- Use low-quality section renders for iteration and high quality only after approval.

## Text and formulas

- Use `Text` for prose and `MathTex` for mathematical notation.
- Choose fonts with glyph coverage for the target language before full rendering.
- Test Chinese, Greek, subscript, and symbol coverage when applicable.
- Break long equations by semantic groups, not arbitrary visual width.
- Render equations once and transform matching parts where possible.

## Reusable components

Place recurring elements in `src/components/`: action titles, citation labels, equation-definition cards, annotated axes, result callouts, process nodes, chapter indicators, and debug overlays. Do not make components so rigid that every scientific concept is forced into the same diagram.

## Draft debugging

Render one scene at low quality. Inspect first, middle, maximum-density, and final frames. Enable safe-area or bounding-box overlays when placement is uncertain, disable them before final render, preserve logs, and re-render only the affected scene.
