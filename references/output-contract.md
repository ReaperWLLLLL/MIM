# Output and project contract

Legacy v0.1 outputs. For v0.2 narrated MP4, silent-video PPT and actual-timing
speech, use [research-video.md](research-video.md). These legacy HTML/PDF commands
do not provide the v0.2 publication or verification contract.

## Project layout

Create projects with this stable layout:

```text
project/
├── .private/               # ignored third-party originals and full-text extraction
├── source/                 # publishable user material or citation records; never overwrite
├── planning/
│   ├── design-brief.md
│   ├── evidence-map.md
│   ├── outline.md
│   └── deck.yaml
├── src/
│   ├── slides.py
│   ├── theme.py
│   ├── components/
│   └── scenes/
├── build/
│   ├── draft/             # draft media and manim-slides manifests
│   └── final/             # final media and manim-slides manifests
├── qa/
│   ├── text-review.md        # language audit and approval
│   ├── draft/
│   │   ├── frames/
│   │   ├── contact-sheet.png
│   │   └── automated-report.md
│   ├── final/
│   │   ├── frames/
│   │   ├── contact-sheet.png
│   │   └── automated-report.md
│   ├── deliverable-verification.md
│   └── report.md           # human review and repair ledger
└── deliverables/
    ├── presentation.html
    ├── presentation.pptx
    ├── presentation.pdf
    ├── speech.md
    └── rebuild.md
```

## HTML

- Export a dependency-free single-file player with every rendered video embedded as a data URI.
- Preserve speaker notes from `deck.yaml`, keyboard navigation, slide numbers, progress, play/pause, and fullscreen controls.
- Do not reference a CDN, remote font, script, stylesheet, or media asset.
- Warn when the single-file deck is too large for the intended delivery channel; offer a local folder bundle only with user approval.
- Verify the embedded media marker and absence of remote dependencies structurally. When browser automation is available, navigate every slide and check console errors.

## Video-based PPTX

- Use one Manim-rendered video or declared static image per PowerPoint slide.
- Include a unique, nonblank poster frame for every video. Use the final stable frame rather than the usually empty first animation frame.
- Place an image-only copy of that poster behind the video object. This gives LibreOffice and other media-unaware renderers a visible static fallback without changing PowerPoint playback.
- Enable automatic media playback where supported.
- Insert plain-text speaker notes derived from `deck.yaml`.
- Keep the slide size at 16:9 and match the rendered media resolution.
- Verify slide count, embedded media count, unique poster frames, static fallback order, automatic playback timing, exact notes, 16:9 page size, and archive integrity. If PowerPoint or LibreOffice is available, render every slide there and inspect the result.

The PPTX is intentionally media-based. Do not promise native editability of Manim objects.
Playback policy varies between PowerPoint, Keynote, LibreOffice, and browser viewers; test in the user's target presenter when available.

## PDF

- Export one representative static frame per logical slide.
- Prefer the final stable frame unless it hides an essential earlier state.
- Preserve titles, figure citations, and readable labels.
- Verify page count, page dimensions, embedded fonts when possible, and rendered-page previews.

## Speech manuscript

Create `speech.md` with one section per slide:

```markdown
## s07 | The scheduler shifts flexible jobs toward cleaner intervals

**Target time:** 75 seconds

Spoken manuscript...

**Advance cue:** After stating the SLA constraint.
**Evidence:** eq-03; fig-02
```

Match the requested language and speaking style. Keep the estimated total duration within 10% of the requested budget.

## Text review

Keep `qa/text-review.md` with the mechanical audit and manual acceptance record.
Final verification requires `Text review: approved`. Approval confirms that claims,
values, equations, citations, and terminology still match the evidence; notes sound
natural when read aloud; visible scene strings are synchronized; and affected
slides were re-rendered after wording changes.

## Rebuild instructions

Create `rebuild.md` containing exact commands for:

- environment preflight;
- validating `deck.yaml`;
- rendering one section at draft quality;
- rendering the full final deck;
- running QA;
- rebuilding each output independently.

Do not include machine-specific absolute paths in the delivered instructions.

## Publication boundary

- Keep unlicensed third-party originals, full-text extraction, and page renders under
  `.private/`; exclude that directory from version control and release archives.
- A public example may keep citations, official URLs, content hashes, locators,
  independently written summaries, and explanatory redraws with attribution.
- Do not bundle proprietary font files, FFmpeg binaries, or a Python environment as
  though they were covered by the project's license. Review those components separately.
- Preserve `LICENSE` and `THIRD_PARTY_NOTICES.md` in every source release.
