# End-to-end workflow

Legacy v0.1 only. For new narrated research videos or `schema_version: "0.2"`,
read [research-video.md](research-video.md) instead. Its audio-derived timing,
60fps default and full-frame audit supersede this route's estimates and samples.
Preserve this workflow for revisions of existing v0.1 projects; migration is not automatic.

## 1. Establish the brief

Read the source material before proposing visuals. Create `planning/design-brief.md` with:

- audience and assumed prior knowledge;
- talk type and exact time budget;
- one-sentence thesis;
- three to five audience takeaways;
- evidence that must appear;
- content that may be omitted;
- language, notation, citation, and accessibility constraints;
- requested deliverables.

Ask the user to approve the brief unless they explicitly request an autonomous run.

## 2. Build the evidence map

Create `planning/evidence-map.md`. Give every reusable source item a stable ID such as `src-paper-p4`, `fig-02`, or `eq-03`. Record the original file and page, section, figure, table, or equation location. Never invent a citation or experimental value.

## 3. Plan the narrative

Create `planning/outline.md` before writing Manim code. Use action titles: each slide title should state the point the audience should understand, not merely name a topic. Budget time by slide and reserve time for the opening, transitions, conclusion, and questions.

Recommended arcs:

- Research talk: problem -> gap -> insight -> method -> evidence -> implications.
- Thesis defense: motivation -> research questions -> contributions -> methods -> results -> limitations -> conclusion.
- Technical lesson: prerequisite -> intuition -> construction -> worked example -> failure mode -> exercise or recap.

Ask the user to approve the outline unless autonomous mode was requested.

## 4. Write `deck.yaml`

Convert the approved outline into the schema in `deck-spec.md`. Run:

```bash
python scripts/validate_deck.py path/to/deck.yaml
```

Do not generate scenes from an invalid specification.

## 5. Humanize the audience-facing copy

Read `text-humanization.md`. Apply the general humanizer pass and then the
language-specific pass. For Chinese decks, use `humanizer` followed by
`humanizer-zh` when available. Keep claims, numbers, equations, citations, and
technical terms unchanged.

Run `scripts/audit_text.py`, review `qa/text-review.md`, and synchronize approved
wording across `deck.yaml`, speaker notes, and visible scene strings. Text changes
invalidate prior visual approval and require a new render of every affected slide.

## 6. Implement one representative sample

Use [legacy Manim authoring](manim-authoring.md) for this v0.1 route. For environment or exporter failures consult [troubleshooting](troubleshooting.md).

Implement a title/transition slide and one technically difficult explanatory slide. Render at draft quality. This sample must establish typography, palette, notation, animation pacing, and visual density.

Ask the user to approve the sample unless autonomous mode was requested.

## 7. Implement in sections

Prefer one Manim `Slide` subclass per logical slide so HTML, PPTX, PDF, notes, and QA evidence stay aligned. Use a tightly coupled multi-slide class only when object continuity cannot be preserved otherwise. Keep reusable visual primitives in `src/components/` and theme constants in `src/theme.py`. Use stable scene names from `deck.yaml` so individual slides or sections can be rebuilt independently.

## 8. Render a draft

Render at 854x480 or 1280x720 and reduced frame rate. Export poster frames and a contact sheet. Do not spend time on 1080p or 4K until the structure and timing pass QA.

## 9. Run visual QA

Apply all automated and human-review gates in `visual-qa.md`. Write findings to `qa/report.md`, including slide ID, severity, evidence, and proposed repair. Re-render only affected sections.

## 10. Build final deliverables

After the draft passes QA, render the final resolution and package outputs according to `output-contract.md`. Run final-profile visual QA, inspect its full-resolution evidence, record human or vision-agent approval in `qa/report.md`, and only then verify every deliverable. File existence alone is insufficient.

## 11. Handoff

Provide:

- final deliverables;
- source project and `deck.yaml`;
- the QA report;
- unresolved limitations;
- exact commands for rebuilding and revising one section.
