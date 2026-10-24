# Licensing and publication

Use this checklist before publishing the skill or a generated example. It is an
engineering release check, not a substitute for legal advice.

## Separate working evidence from public artifacts

- Put third-party originals under `.private/sources/` and extraction output under
  `.private/extracted/`. Keep `.private/` out of Git and release archives.
- Track a small citation record instead: title, authors, venue, year, official URL,
  content hash when useful, page or section locators, and an independently written
  evidence summary.
- Do not publish a downloaded paper, extracted full text, page screenshots, tables,
  or original figures merely because the source is publicly readable.
- Keep user-owned or permissively licensed sources in `source/` only when their
  provenance and redistribution terms are recorded.

## Rebuild without redistributing private inputs

For a public research-video project, `project.source_files` can point to a real
public citation record containing bibliographic metadata, locators and original
evidence summaries. Retain the primary paper privately for evidence verification.
Do not ship a spec whose required input points to a removed PDF. If lawful local
access to the private paper is required to build, document that setup explicitly
before the validation command. A reproducible render from public records is not
an independent check of the primary source. Do not use full-text extracts as a
redistribution workaround.

## Transform with attribution

- Prefer original Manim diagrams that explain relationships in a new visual grammar.
- Cite the source and locator on the slide and in `planning/evidence-map.md`.
- Label a recreated architecture or chart as an explanatory redraw. Do not reproduce
  distinctive artwork pixel for pixel unless the license permits it.
- Quote only the minimum needed. Preserve authorship and license notices for copied
  material; facts and equations still need scholarly attribution even when copyright
  does not protect the underlying idea.

## Review software and assets

- Keep the repository's `LICENSE` separate from dependency licenses. Preserve
  `THIRD_PARTY_NOTICES.md` in releases.
- Do not vendor Python packages, FFmpeg, TeX, fonts, or their binaries without a
  component-level license review. A requirements file is not permission to relicense
  dependencies under the project license.
- Reference proprietary fonts by family name only. Require the user to supply a
  licensed local installation; never copy font files into the project.
- If creating a Docker image, standalone installer, or hosted service, generate a
  complete dependency inventory and re-audit transitive and system components.
- Keep TTS dependencies and model assets on the authorized remote host. Preserve
  exact model-content and runtime records separately; a model-card revision is
  evidence of its declaration, not proof of the installed checkpoint revision.
- Distinguish the Skill's MIT code from external runtime code, model weights and
  user input/output rights. Optional Whisper ASR remains QA-only, not a core
  generation dependency. See [third-party notices](../THIRD_PARTY_NOTICES.md).

## Release scan

For this source-only Skill repository, run `python scripts/audit_release.py --ref INDEX`
before committing and `--ref HEAD` afterward. Inspect each newly introduced
commit before pushing, not only the final tree: removing a private file later
does not remove it from Git history. The scanner reads Git blobs and permits only
the recorded demo image inventory. Review their provenance separately; a clean
scan is not a determination of rights.

Before publishing, inspect tracked and packaged files for `.pdf`, `.docx`, `.pptx`,
font files, extracted Markdown, page images, archives, media copied from sources, and
absolute local paths. Confirm that every retained third-party artifact has a recorded
license or permission. Remove ignored working material from any staging archive.

Run the same absence/permission scan on the actual final archive, not just
`git ls-files`: ignored environments, model caches, fonts, binaries and private
originals can enter a copied directory. Record the archive's hash and inventory,
what was checked, and any unresolved rights. Earlier upstream-license research
does not clear a later release artifact. Do not push or publish without authority.

Git ignore rules do not automatically filter ZIP or directory copies. Keep the
source-only Skill release distinct from a requested course/reproducibility sample:
the latter may explicitly include verified WAV/media with reviewed rights and
hashes. Ignoring a voice cache in Git does not prohibit that authorized handoff.
