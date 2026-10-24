# Research-video workflow (v0.2)

This is the strict synchronized-production route for existing v0.2 projects or explicitly requested audio/frame/provenance guarantees. For new creative samples and ordinary human-reviewed animations, start with [creative-first](creative-first.md). The commands below retain their validation contracts; they are not mandatory prerequisites for a native Manim preview.

Find commands under Setup, Verified audio, Scene authoring and Export. Local revision covers reuse; Reproducible handoff lists the records to retain.

This route produces a complete narrated MP4, a PPTX with chapter-matched silent video and a real-timing manuscript. The generic [research template](../assets/research-template/planning/deck.yaml) demonstrates the API in twelve planned seconds; it is not a paper explanation or a finished production. Existing v0.1 projects use [the legacy workflow](workflow.md).

## Brief and evidence

Confirm the input version/path, audience, target duration, language, target PPT application and desired approval gates. Ask whether the user wants video plus silent-video PPT when "presentation" is ambiguous. Offer three minimal themes: `midnight` (dark blue), `paper` (warm light), `slate` (neutral dark). For a missing theme preference, state the `midnight` default. Confirm a custom palette before rendering it.

Write `planning/design-brief.md`, `planning/outline.md` and `planning/evidence-map.md`. Explain the research question and the mechanism needed to understand the answer. Select results that support that explanation, and cite exact source locators for claims, values, equations and explanatory redraws. Put a calculation's scope beside that calculation. Keep production directions in beat `action`, not narration or captions.

Obtain brief/outline and representative-sample approval unless autonomous production was explicitly requested. Preserve those artifacts either way. Read [source ingestion](source-ingestion.md), [scientific storytelling](scientific-storytelling.md) and [licensing](licensing-and-publication.md) as needed. Read sources privately; public `source_files` may point to a bibliographic record with original evidence summaries. It must actually exist at build time. Rendering from that record does not independently verify the paper's evidence. If the required build input remains private, document its lawful local placement before validation.

## Setup and project

Use the local rendering environment from `requirements.txt`: Manim CE, Manim Slides, FFmpeg/FFprobe, Pango/Cairo and a locally licensed Microsoft YaHei installation. Add LaTeX only for scenes using TeX. Do not copy fonts, environments or external binaries into the project.

Run `python "$SKILL_DIR/scripts/preflight.py" --need-pptx` (add `--need-pdf-input` or `--need-latex` when needed). This is the renderer preflight, not a remote voice readiness check. Confirm `ssh tts-host` and its prepared worker/model manifest separately using [remote voice documentation](remote-voice.md). Installation/download are explicit preparation, not automatic synthesis recovery; do not run them without authorization. `requirements-tts.txt` belongs only on tts-host. The client needs no TTS packages or weights.

Copy the research template into a **new, absent** project directory; `scaffold_project.py` still creates v0.1 projects:

```bash
test ! -e ./my-research-video && cp -R "$SKILL_DIR/assets/research-template" ./my-research-video
cd ./my-research-video
python "$SKILL_DIR/scripts/build_research.py" validate --spec planning/deck.yaml
```

Replace the template's content and planned budget for the real task. Keep `schema_version: "0.2"`. Default final `render` is `{width: 1920, height: 1080, fps: 60}`; draft is 960×540 at 15fps. A draft timeline cannot be used for a final render. Template `voice` is SSH `tts-host`, root `/srv/manim-tts`, model `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`, speaker `Uncle_Fu`; use calm, moderate-speed Mandarin narration. Voice configuration supports `instruct` and literal ordered `pronunciation` replacements. Review actual readings; the voice name alone does not prove the result is suitable.

Set `project.theme` to a preset or `custom`; for custom set `project.theme_custom: planning/custom-theme.yaml`. [The custom example](../assets/research-template/planning/custom-theme.yaml) changes colors. Theme data validates colors, font family/roles, line width and spacing. Default roles are fixed 48/30/20, with no per-label shrinking. A custom theme can replace the complete `title`/`body`/`caption` group. Sizes must be at least 36/24/18, with title > body > caption. The scene creates and audits text at those configured sizes; scaling text or its parent still fails. Review each composition with its chosen role group.

## Final copy before audio

Read [text humanization](text-humanization.md). Store all visible labels, formula display strings, captions and subtitles in each slide's `screen_text`, and reference their keys in each beat's `screen_text`. Register final README/report prose in `audience_text` when it is delivered with the project. Keep `slide.notes` audience-facing; export's canonical notes are the newline-joined beat `narration` values.

Apply installed `humanizer`, then `humanizer-zh`; if unavailable, perform and name the two manual passes using the reference rules. Export the actual copy with `audit_text.py`; review every entry and keep before/after edits, reviewer/skill version or hash and unresolved findings. Only then record both approvals for the current copy hash. The tool creates neither review pass nor approval. Text edits invalidate prior hashes, affected audio and affected layout approval.

## Verified audio, then frozen timing

Run from the project directory. All CLI arguments are caller-relative; resources inside the spec are project-relative. `planning/deck.yaml` implies the project is `planning/`'s parent. Use a separate `build/` directory, not an input or final-output path, for `--out`.

```bash
python "$SKILL_DIR/scripts/build_research.py" voice --spec planning/deck.yaml --out build/audio.json
python "$SKILL_DIR/scripts/build_research.py" timeline --spec planning/deck.yaml --audio build/audio.json --out build/timeline.json --profile final
```

Voice exit 2 means the observation timed out, not the detached job. Retain `build/audio.pending.json` and repeat the **identical** voice command to observe that job; do not reinstall, resubmit changed settings or kill processes as an automatic retry. Exit 1 needs diagnosis. Job/cue identities cover text, voice settings and exact model content. Verified unchanged cues can be reused. No cloud or local-model fallback is implicit.

The client verifies returned PCM16 WAV bytes, sample counts/rates, hashes, IDs and spoken text. Frozen cue frames come from actual samples, rounded up to whole frames; only end padding fills the remainder. `duration_seconds` is a planning budget, not permission to trim audio. If measured total misses the agreed duration, revise content/voice and regenerate timing. Pronunciation substitutions may make `spoken_text` differ from canonical narration; preserve both in the manuscript.

Offline timeline/publication admission uses the same synthesis defaults as the SSH client and checks model, speaker, language, instruction, pronunciation, generation and seed against the current request. It retains and verifies recorded model-content, job and cue identities without contacting SSH; observation timeout and transport changes do not change the requested voice. Rebuilding a timeline cannot bless old voice settings. Exact digital silence is rejected in cue caches/results, retained WAVs and the decoded final soundtrack; legal tail padding remains. These signal checks do not establish pronunciation or listening quality. The manuscript labels `spoken_text` **合成输入文本**, not heard transcription.

## Scene authoring and full-frame QA

Use [the generic scene](../assets/research-template/src/scenes.py) as the API example. Import `ResearchScene` from `research.scene`; the build CLI makes its scripts importable. One stable subclass corresponds to each slide's `scene_class`.

- `self.text(key, role="body", parent=container_id)` creates and tracks final registered copy. Roles are `title`, `body`, `caption`. Use explicit line breaks or split content instead of scaling to fit.
- `self.track(id, mobject, kind, ...)` registers semantic shapes individually. Use actual container boundaries and explicit parents. A `VGroup` does not exempt its children from registration or collisions.
- Track straight lines/arrows as `kind="connector", endpoints=(id0,id1)`. Endpoints must touch the target boundaries and leave their interiors. Real arrow tips and painted envelopes are checked. Curves need registered segments; conservative bounds may require simpler geometry.
- Call `self.beat(beat_id, animations, motion_seconds)` exactly once per frozen beat, in order. Audio determines the available frames; the scene holds the rest. Keep text identity stable during translation/fades. Text-changing glyph morphs are unsupported: use separate registered text objects with FadeOut/FadeIn.

The Cairo/no-cache bridge inspects **every emitted frame**, including intermediate animations and holds. It records actual geometry, text sizes, opacity and registrations in `slide-NNNN/audit/frames.jsonl`, with `qa.json`. Defaults are a 5% viewport safe margin, .1 scene-unit gap and .15 container padding; parent links are deliberate containment, not blanket collision exceptions. Text/formulas/subtitles require roles. If subtitles are used, explicitly configure a subtitle zone in the scene layout and keep other foreground outside it. Missing registrations, bad endpoints, shrinking, overflow and non-exempt overlaps fail rendering. Inspect the reported frame/object IDs and failure screenshot; fix the composition rather than suppressing checks.

Paint bounds include each frame's visible normal/background strokes, actual Cairo cap/join state and camera transform. Container usable bounds shrink inward from the path boundary while painted borders grow outward. Connector endpoint exemptions remain narrow: observed connector and target-border paint radii must not exceed .05 scene units; thick decorative lines need ordinary shape collision checks. Generated relative partial filenames keep caller directory names out of both native concatenation passes; frame-derived durations and stream copy are retained.

```bash
python "$SKILL_DIR/scripts/build_research.py" render --spec planning/deck.yaml --audio build/audio.json --timeline build/timeline.json --source src/scenes.py --out build/rendered --profile final
```

For a sample, use a small coherent spec with its own audio/timeline/output directory; `--slides` is a **reuse** operation requiring verified previous masters for every unselected page. Draft iteration needs a separately generated draft timeline and output directory. Final delivery always needs a fresh final-profile validation. Review all scenes in motion, dense states, text/equation readability and narrative pacing. Geometry traces do not prove research correctness or pleasant motion. Record human findings with slide, frame/time, severity, repair and status.

## Export and acceptance

```bash
python "$SKILL_DIR/scripts/build_research.py" export --spec planning/deck.yaml --audio build/audio.json --timeline build/timeline.json --out build/rendered --profile final
python "$SKILL_DIR/scripts/build_research.py" verify --spec planning/deck.yaml --audio build/audio.json --timeline build/timeline.json --out build/rendered --profile final
```

Export stages under `build/rendered/export/` and publishes to **exactly** `spec.outputs.video`, `pptx` and `speech` under the project root. Template destinations are `deliverables/research-video.mp4`, `deliverables/presentation.pptx` and `deliverables/speech.md`. The exporter reserves its entire `export/` directory for internal clips, posters and audio. Only `outputs.video` may use that directory's `narrated.mp4`, and only `outputs.pptx` may use its `silent-slides.pptx`. Other destinations inside staging fail before export writes any files. Keep outputs distinct from source/audio/render inputs. `export-manifest.json` records the actual delivered paths/hashes and frame/sample mappings. A staging-only Python API export is not the CLI delivery contract.

Collision protection covers the required evidence map, actual CLI spec/audio/timeline inputs, effective theme/font files, sources and retained media/QA, including symlink and hardlink aliases, before staging or publication writes. Rendering records the effective theme file's lexical path, resolved target and content hash, including `--theme-file` overrides; editing, removing or retargeting that file requires rerendering before export/verify/reuse. A legitimate CLI override need not match the theme name in the project spec.

The MP4 has the ordered scene visuals and AAC narration. PPTX contains those same scene masters as embedded clips with **zero audio tracks**, automatic playback settings, stable visible posters/static fallbacks and canonical narration notes. A poster can be an earlier stable frame when the ending is blank. The manuscript uses real frame/sample intervals and pronunciation correspondence, not notes-based word estimates.

`verify` exits 0 only with no findings, otherwise 1. It checks current audio/text approvals/timeline dependencies, decoded frame identity across masters/full video/external and embedded clips, every frame PTS, AAC reference timing, PPT order/relationships/posters/fallback/notes and actual declared deliverables. Report findings rather than changing a stored `ok` flag. Structural checks do not establish timed autoplay in PowerPoint or human listening quality. Open the final PPT on the target player, play every clip, and listen to the complete MP4 for pronunciation, clarity, cutoffs and synchronization. Record each check as `pass`, `fail` or `not_checked`, with evidence; never mark unseen or unheard content passed.

## Local revision

Change the spec first. For a scene-local emphasis color, keep it in `slide.presentation` and read it through `self.slide_spec`; for example merge `{**self.theme["colors"], **self.slide_spec.get("presentation", {})}` in the original source. A common Python/theme/config edit can conservatively invalidate every scene; do not promise AST-level dependency isolation.

After narration/copy changes, repeat both real text-review passes, rerun voice (unchanged cues reuse verified cache), then rebuild the timeline. Render selected changed pages against the previous complete render:

```bash
python "$SKILL_DIR/scripts/build_research.py" render --spec planning/deck.yaml --audio build/audio.json --timeline build/timeline.json --source src/scenes.py --out build/rendered --profile final --slides s03
```

Then rerun export and verify for the whole deliverable set. Unselected scenes must pass dependency and byte/media checks before selected masters are touched. Their original master/trace/QA/native JSON stay unchanged; a new frame map records shifted global offsets without pretending they were newly observed. Reordering pages or changing shared dependencies can require selecting all affected pages or a full render. Undeclared mutable external reads require explicit dependency modeling or a full render. Report preserved hashes, necessary timing changes and the exact scope actually reused.

## Reproducible handoff

Keep source code, public evidence records, spec, brief/outline, copy manifest and both review records, actual audio/model-content identity, frozen timeline, render/export manifests, QA findings and exact rebuild commands with software/font versions and hashes. Keep working audio/media outside a source-only release when the user has not authorized their redistribution. A separately requested course or reproducibility sample can explicitly include verified WAV/media after a rights review; it is a different artifact from the source-only Skill. The template ignores private inputs, credentials, environments and caches in Git, not in arbitrary ZIP copies. Keep original papers in `.private/`; no blanket PDF ignore hides legitimate PDF deliverables. Explain how an authorized recipient obtains any omitted private input before running validation; do not silently leave broken `source_files`.

Write `deliverables/rebuild.md` with project-relative arguments, required local licensed-font setup, remote prerequisites and the commands above. Record external model `upstream_revision: null` honestly when only content identity is pinned; a model-card commit is not the installed weight revision. Render reproducibility and independent primary-source verification are separate claims. Report real duration/settings and all unchecked playback/listening/source checks. Do not publish or push merely because local export succeeded.
