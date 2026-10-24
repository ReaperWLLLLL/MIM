# Native Manim authoring

Use native `Scene`, `MovingCameraScene` or `Slide` for creative visual work. This route does not require legacy `DeckSlide` or strict `ResearchScene` registration. Those retain their respective contracts.

## Small project, direct rendering

Keep source, a short explanation/coverage note and deliverables outside `SKILL_DIR`. Add shared helpers only when reused. The original runnable [branch-stamp example](../assets/native-example/branch_stamp.py) shows a branch becoming four signed matrix entries. It illustrates correspondence, not a universal layout.

```bash
python -m manim -ql --media_dir build/sample-v01 src/scenes.py Example
python -m manim -r 1280,720 --fps 30 --media_dir build/preview-v01 src/scenes.py Example
```

Run from the project root using installed versions. Verify the actual FFmpeg/FFprobe and TeX selected by PATH before reinstalling a broken global environment. Register a locally licensed user font in the process if discovery misses it; never distribute the font.

For an offline render, disable Manim's automatic update notification in the project's `manim.cfg` (`[CLI]` / `notify_outdated_version = False`); some installed releases otherwise contact PyPI after rendering. Rendering does not require a package upgrade.

## Geometry carries meaning

Use the agreed [visual style](visual-styles.md). The three runnable examples use
different composition and emphasis choices as well as colors. Reuse their values
without forcing the scene into the showcase layout.

Preserve semantic colors and object identity. Transfer or highlight matching parts of a physical diagram and formula explicitly. Derive data visuals from a checked model rather than unrelated hand-entered counters. Introduce the meaning of a quantity before its measurements.

Trackers and updaters expose continuous dependencies; remove them when no longer needed. Avoid simultaneous unrelated motion. Distinguish flow metaphors from literal time-domain physics. Use `MathTex`, define reference directions before using signs, and break equations into readable steps.

For mathematics embedded in prose, use [copy-and-math.md](copy-and-math.md) and the [mixed-caption example](../assets/native-example/mixed_math.py). A caption is not restricted to a plain string: combine `Text` and `MathTex` into a line/group and animate that group as needed. Preserve the distinction between a subscript, transpose and inverse; check the mixed line in the rendered frame.

## Readability and revision

Relative alignment and spacious explicit coordinates are both legitimate. Keep labels off important geometry. A box helps with a real container, not every sentence. Shorten copy or restructure before reducing text below readable size.

Inspect the most crowded state and a copy/transform transition. Re-render affected classes and rebuild the requested output. Preserve old deliverables until replacements are verified. Report sampled-frame inspection separately from continuous playback.
