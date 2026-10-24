# Troubleshooting

Environment notes can help both routes. Rendering, font-fit, re-encoding and
export commands below belong to legacy v0.1. For v0.2 use
[research-video.md](research-video.md) and the remote voice recovery reference;
preserve silent clips, fixed font roles and frozen audio/frame timing.

## Installation and preflight

- Use Python 3.10 or newer in a local virtual environment.
- Prefer the official Python package index when a corporate or regional mirror lacks PEP 517 build dependencies such as `meson-python`, `pycairo`, or `srt`.
- Install FFmpeg and its `ffprobe` companion through the operating system package manager; a Python package is not a substitute.
- Install a TeX distribution only when the deck uses `MathTex`, `Tex`, or LaTeX source conversion.
- Run `scripts/preflight.py` from the same activated environment and `PATH` that will run the renderer.
- PDF extraction and verification use `pypdf`; do not add PyMuPDF as a fallback because
  its AGPL/commercial dual license changes the release obligations.

## Manim and manim-slides

- Use the versions constrained in `requirements.txt`. CLI flags have changed across Manim Slides releases.
- Run renders through `scripts/render_deck.py`; it sets the profile-specific slide manifest directory and deck-spec path.
- Do not add historical `--CE` or render-time `--folder` flags. Manim Slides 5.6 delegates rendering to Manim CE; `--folder` belongs to conversion.
- If `--skip-render` reports a missing manifest or media file, remove the flag and rebuild that scene.
- If a renamed scene leaves stale media, verify `scene_class` in `deck.yaml`, render without cache, and review `build/<profile>/slides` before deleting only the obsolete scene directory.

## Fonts and language

- Confirm target-language glyph coverage before the full render. Missing CJK glyphs often appear as boxes even when the Python source is valid.
- Choose and record an installed font in `src/theme.py`; do not assume a proprietary font is available on another machine.
- Shorten or wrap copy before shrinking below the readable minimum. Use the safe-width helper for titles and long labels.

## LaTeX and equations

- A missing `latex` executable blocks `MathTex` and `Tex` scenes but not plain `Text` scenes.
- Preserve the first LaTeX error from the render log; later FFmpeg or missing-file messages are often consequences, not the cause.
- Test one equation scene at draft quality before rendering the deck.

## HTML

- The HTML exporter is intentionally independent of RevealJS and CDNs. It embeds every video, so file size is roughly the sum of the videos plus base64 overhead.
- If the file is too large for email or a learning platform, reduce video bitrate or create a folder bundle only after confirming the delivery constraint.
- Browser autoplay may require the first user interaction. The deck remains navigable with arrow keys and the play button.

## PPTX and PDF

- PPTX slides contain videos and poster frames, not editable Manim shapes.
- The exporter replaces each converter-generated first-frame poster with the video's final stable frame and adds an image-only copy behind the video for media-unaware renderers. If thumbnails are black, re-run the PPTX export rather than accepting the default poster.
- Automatic video playback varies by presenter. Verify with the actual PowerPoint, Keynote, or LibreOffice version used at the venue when possible.
- If PowerPoint reports damaged media, confirm the embedded files with `scripts/verify_outputs.py`, then re-encode the source videos to H.264/AAC-compatible MP4.
- PDF pages are representative static frames. Use HTML or PPTX when intermediate animation states are essential.

## Visual QA

- The outer-margin detector is conservative and may flag deliberate edge-to-edge backgrounds or decorations. Record an explicit exception only after inspecting the full-resolution frame.
- A clean automated report never replaces manual inspection of the contact sheet, dense intermediate states, and final frames.
- When only one slide changes, re-render that slide, but run full-deck narrative and deliverable checks before release.
