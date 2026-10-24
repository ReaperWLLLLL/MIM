# Visual QA gates

Legacy v0.1 QA. New v0.2 videos require every-frame semantic/layout evidence
and decoded media verification described in [research-video.md](research-video.md).
The sampled-frame checks below do not replace that coverage or actual listening.

Visual QA has four layers. A deck passes only when all applicable layers pass or the final report records an explicit user-approved exception.

## Layer 1: specification QA

Run before generating code:

- valid `deck.yaml` and unique IDs;
- timing within 10% of the talk budget;
- every quantitative claim mapped to evidence;
- every animated slide has beats and a valid scene class;
- titles state takeaways rather than generic topics;
- no slide carries more than three independent claims.

## Layer 2: render integrity

Run after each draft render:

- every expected scene and slide segment exists;
- FFmpeg can decode every video;
- resolution and aspect ratio are consistent;
- duration is positive and plausible;
- poster frames and extracted review frames exist;
- no all-black, all-white, frozen, or single-frame segment unless intentionally declared;
- audio is absent unless explicitly requested for a source-media slide.

Treat missing scenes, undecodable files, wrong aspect ratio, and empty frames as blocking failures.

## Layer 3: composition and readability

Inspect the first, middle, and last frame of each segment, plus any frame containing the maximum number of objects.

Check:

- all important objects remain inside a 5% safe margin;
- body text is readable at normal presentation distance;
- no clipped equations, labels, captions, or citations;
- no collisions between text and moving objects;
- consistent title, body, equation, and citation hierarchy;
- adequate foreground/background contrast;
- color is not the only carrier of meaning;
- adjacent slides preserve object identity when a transformation implies continuity;
- visual density increases deliberately rather than accidentally;
- the final frame is stable long enough for the audience to absorb it.

Use image inspection for judgment. Automated bounding-box checks are evidence, not a substitute for reviewing rendered frames.
The bundled checker flags visible final-frame content entering the outer 2% margin as a major finding. Treat this as an early warning for the required 5% design-safe area; inspect deliberate full-bleed elements before accepting an exception.

## Layer 4: narrative and pacing

Review the complete draft as an audience member:

- the action titles alone tell a coherent story;
- animation reveals information in the order it is spoken;
- every motion explains a relationship or directs attention;
- no decorative animation delays the argument;
- equations are introduced before they transform;
- charts expose axes, units, legends, and the highlighted result;
- section transitions reset context;
- the conclusion restates contributions and limitations, not merely "Thank you";
- total runtime matches the requested talk length.

## Severity levels

| Severity | Meaning | Required action |
|---|---|---|
| `blocker` | Missing/invalid output or misleading scientific content. | Fix before any final export. |
| `major` | Readability, timing, evidence, or narrative defect. | Fix unless user explicitly accepts it. |
| `minor` | Local polish issue without comprehension risk. | Fix when inexpensive; otherwise record. |

## QA report format

Write `qa/report.md` with:

```markdown
## s07 — The scheduler shifts flexible jobs toward cleaner intervals

- Severity: major
- Evidence: `qa/draft/frames/s07-b2-middle.png`
- Finding: the SLA label overlaps the carbon-intensity curve at 1280x720.
- Repair: move the label above the plot and reserve the upper-right safe area.
- Status: fixed and re-rendered
```

End the report with an output-by-output verification table covering HTML, PPTX, PDF, speech, source, and rebuild commands.

Keep automated frames, contact sheets, and reports under `qa/draft/` or `qa/final/`. Final QA must not erase the draft evidence that explains what was repaired.
Keep `Final visual approval: pending` in `qa/report.md` until a human or vision-capable agent has inspected the final contact sheet, every full-resolution final frame, and dense intermediate states. Change it to `approved` only when all blocker and major findings are fixed or explicitly accepted; `verify_outputs.py` enforces this gate.
