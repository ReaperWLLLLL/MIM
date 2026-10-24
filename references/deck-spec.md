# `deck.yaml` specification

Legacy v0.1 schema. New v0.2 research-video projects use
[research-video.md](research-video.md) and `assets/research-template/`; do not copy
this schema's theme, output or estimated-timing defaults into that route.

`deck.yaml` is the source of truth for narrative structure, timing, evidence, scenes, notes, and exports. Keep content decisions here and implementation details in Python.

## Required top-level structure

```yaml
schema_version: "0.1"
project:
  title: "Why compute should follow renewable energy"
  kind: "research-talk"
  language: "zh-CN"
  audience: "Energy systems researchers"
  duration_minutes: 20
  aspect_ratio: "16:9"
  theme: "scientific-dark"
  source_files:
    - ".private/sources/paper.pdf"
narrative:
  thesis: "Carbon-aware scheduling makes computing a flexible grid load."
  takeaways:
    - "Spatial and temporal flexibility can reduce marginal emissions."
    - "The scheduler must preserve service-level constraints."
slides: []
outputs:
  html: "deliverables/presentation.html"
  pptx: "deliverables/presentation.pptx"
  pdf: "deliverables/presentation.pdf"
  speech: "deliverables/speech.md"
```

## Project fields

| Field | Requirement |
|---|---|
| `title` | Non-empty string. |
| `kind` | `research-talk`, `thesis-defense`, or `technical-lesson`. |
| `language` | BCP-47-like tag such as `en`, `zh-CN`, or `fr`. |
| `audience` | Concrete description of expected viewers. |
| `duration_minutes` | Positive number. |
| `aspect_ratio` | `16:9` for v0.1. |
| `theme` | Theme identifier implemented by the project. |
| `source_files` | Non-empty list of project-relative source paths. Put unlicensed third-party originals under ignored `.private/sources/`; use a tracked citation record for public examples. |

## Slide fields

Each item in `slides` must contain:

```yaml
- id: "s07"
  section: "method"
  title: "The scheduler shifts flexible jobs toward cleaner intervals"
  purpose: "explain"
  claim: "Carbon intensity becomes a scheduling signal subject to SLA constraints."
  duration_seconds: 75
  source_refs: ["eq-03", "fig-02"]
  scene_class: "SchedulingMechanism"
  visual_mode: "manim"
  notes: |
    First establish the conventional queue, then reveal carbon intensity.
    Emphasize that the SLA boundary never moves.
  beats:
    - id: "b1"
      narration: "Jobs initially enter a conventional queue."
      action: "Create the queue, workers, and arriving jobs."
    - id: "b2"
      narration: "Carbon intensity changes across time and regions."
      action: "Reveal the carbon signal and map it onto available slots."
  qa:
    must_show: ["queue", "carbon signal", "SLA boundary"]
    avoid: ["more than two simultaneous equations"]
```

Rules:

- `id` must match `sNN` or `sNNN` and be unique.
- `section`, `title`, `claim`, `scene_class`, and `notes` must be non-empty.
- `purpose` must be one of `open`, `motivate`, `explain`, `derive`, `compare`, `evidence`, `transition`, `recap`, or `close`.
- `duration_seconds` must be positive.
- `visual_mode` must be `manim`, `static`, `media`, or `hybrid`.
- `source_refs` may be empty only for framing, transition, and closing slides.
- `beats` must contain at least one item for `manim` and `hybrid` slides.
- Beat IDs must be unique within the slide.
- Use valid Python class identifiers for `scene_class`.

## Timing rules

- The sum of `duration_seconds` should be within 10% of `project.duration_minutes * 60`.
- Reserve explicit time for opening and closing slides.
- Use 30-90 seconds for most research slides.
- Split any slide requiring more than three independent claims.

## Audience-facing language rules

- Run the humanization workflow in `text-humanization.md` after the specification
  validates and before implementing the representative sample.
- Keep action titles concrete. Avoid promotional claims, slogan-like oppositions,
  generic signposting, and vague authority.
- Preserve formulas, values, citations, proper names, and standard technical terms.
- Read speaker notes aloud in the requested language and keep the estimated total
  duration within 10% of the requested budget.
- Synchronize every wording change with visible scene strings, then re-render and
  repeat visual QA.

## Evidence rules

- Every quantitative claim must have at least one `source_ref`.
- Every `source_ref` must match an ID declared in the first column of `planning/evidence-map.md`; the validator rejects unknown or duplicate IDs.
- Reused paper figures must retain source and page/figure identifiers.
- Do not publish third-party source documents, extracted full text, or page images
  unless their license or explicit permission allows redistribution.
- Distinguish reported evidence from proposed interpretation in the notes.
- Never create a plausible-looking but unsupported experimental result.

## Scene naming

Use stable semantic names such as `ProblemScale`, `MethodOverview`, or `AblationResults`; do not use `Scene1`. Once published, avoid renaming scene classes because section-level caches and revision commands depend on them.
