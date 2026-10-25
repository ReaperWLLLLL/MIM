---
name: mim
description: Use when turning research results, papers, technical ideas, scripts or other material into a Manim explanatory animation or animated presentation, or revising an existing Manim project. Not for text-only summaries or native-editable static slides.
---

# MIM: Make Ideas Move

The skill identifier and installation directory name are `mim`; invoke it as `$mim`.

Explain through objects and meaningful transformations. The audience should see why a relationship holds, not just watch statements appear. Visual reasoning is the default; narration and export machinery are separate, requested capabilities.

Support research presentations, paper discussions, technical proposals, public explanations and course material. Start from what the speaker wants the audience to understand. For research results, organize the problem, contribution, method and supporting evidence around the actual work; a concrete process or result comparison can anchor the animation. Match the audience's prior knowledge and use worked examples when they serve the explanation.

## Choose the route

Treat this directory as `SKILL_DIR`; keep generated projects outside it. Reuse established audience, language, source, style and scope. Inspect original scenes before revisions.

- New animation or silent video: read [creative workflow](references/creative-first.md). For a multi-section talk or long-form explanation, also read [section production](references/chapter-production.md).
- Native scene implementation: read [native Manim](references/native-manim.md), not legacy authoring.
- Requested narration, sound, PPT or other formats: read [optional post-production](references/post-production.md).
- Existing `schema_version: "0.1"`: retain `references/workflow.md` and its tools. Preserve the project unless migration is requested.
- Continuing an existing `schema_version: "0.2"` synchronized delivery, or explicitly requested strict audio/frame synchronization and provenance: read `references/research-video.md`. Its CLI contracts remain intact. A separate native creative sample can coexist with that archived delivery; do not claim it passed the strict pipeline.
- Review/diagnosis or planning only: deliver that work without starting repairs or rendering.
- Ambiguous "presentation materials": clarify format, audience and duration before expensive production.

## Creative defaults and optional production tools

For new material or a changed explanation scope, first follow the design conversation in [creative-first.md](references/creative-first.md): agree on the main message, depth, central objects or examples, and simplifications before scene production. Reuse confirmed answers. Style approval and lighter QA do not settle content choices. Explicitly delegated choices can proceed after stating them; wording-only revisions within an agreed brief need no new design round.

Use 16:9 and a low-resolution representative segment. Discuss [visual styles](references/visual-styles.md): `midnight` (dark geometry), `daylight` (light academic), or `notebook` (warm paper), preserving an already agreed style. Use locally licensed Microsoft YaHei for Chinese, or the user's chosen installed font; never bundle font files. Minimal style concerns composition, not minimum node count. Use [copy and inline mathematics](references/copy-and-math.md) for audience text; mixed sentences combine prose with real mathematical objects.

Establish the visual explanation before narration timing. Audio is optional. Hosts, voices and backend permissions belong to the project, not this generic Skill. Follow the user's backend instructions; do not install models or silently substitute services. The existing strict v0.2 voice implementation retains its own remote-only contract.

For creative drafts, render real media, inspect dense states and confirm decoding. Check the agreed example complexity, explanatory copy and mathematical typography as well as clipping. Human review judges the explanation. Exhaustive frame/provenance audits are optional; existing strict CLI checks remain intact.

Separate screen explanation from evidence/production notes before applying installed `humanizer` and `humanizer-zh`. Preserve necessary assumptions; write direct explanations. The [text review](references/text-humanization.md) reference distinguishes native copy review from strict versioned records.

Add requested audio and exports after establishing the visuals. Keep silent PPT clips, useful posters and notes; do not promise native-editable Manim objects. Distinguish structural verification from playback/listening and report unchecked items.

## Sources and handoff

Read only references needed by the chosen route. Use [source ingestion](references/source-ingestion.md) for extraction and [release boundaries](references/licensing-and-publication.md) before packaging. Keep third-party originals private, retain source locators and original explanations, and deliver editable source with reproducible commands. Never overwrite source material, install models, publish or push without the required authorization.
