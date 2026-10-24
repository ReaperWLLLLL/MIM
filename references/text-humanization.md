# Text humanization and spoken-copy QA

Apply this review to audience-facing copy before synthesis and scene production. Keep research facts, terminology, equations and source locators unchanged unless evidence supports a correction. Technical documentation should stay plain and neutral.

First use [copy-and-math.md](copy-and-math.md) to place content in the right layer and represent mathematics correctly. Screen copy explains the visible operation; source-audit and production qualifications belong in notes. Necessary mathematical hypotheses remain with the relevant claim. Native drafts need a lightweight actual copy/render review, not the strict hash/approval records below.

## Two actual editing passes

Read and apply installed `humanizer` first. Produce a draft rewrite, identify remaining formulaic or promotional wording, then revise it. Next read and apply `humanizer-zh` to Chinese copy: remove translation-like constructions, unnecessary announcements and slogans; vary sentence rhythm without inventing an author's personal experience. If either skill is unavailable, name that limitation and perform the corresponding manual pass using these rules. Do not vendor upstream skill files to satisfy availability.

Review titles, thesis, takeaways, every registered label/formula/caption/subtitle, beat narration, audience-facing notes, README and report prose. Internal `action` strings describe production and stay outside audience copy. Put source conditions and calculation scope next to the actual data or example, rather than repeating generic disclaimers. Keep meaningful technical repetition.

Record concrete before/draft/final edits, the remaining-tells audit, evidence checks, reviewer and skill version/file hash. A status field or pattern scan cannot stand in for either pass. Read the final narration aloud; listening to synthesized output remains a later separate check.

## v0.2 copy manifest and approvals

Store final scene text in `slide.screen_text`, beat narration in `beats[].narration`, and delivered extra prose in nested `audience_text`. Keep subtitles registered and audit their actual rendered objects. Export current copy:

```bash
python "$SKILL_DIR/scripts/audit_text.py" planning/deck.yaml
```

The command writes `qa/text-review.md` and `qa/audience-copy.json`, including path-to-copy entries and a canonical content hash. It resets the Markdown status to pending; save actual manual review evidence separately before rerunning it. Synchronize external README/report files with the strings registered in `audience_text`; hashing the registry alone cannot detect an unregistered external edit.

After both real passes and fact checks, manually record the **current final** manifest hash in the spec:

```yaml
text_review:
  content_hash: "<actual final audience-copy hash>"
  humanizer:
    status: "approved"
    content_hash: "<same actual hash>"
  humanizer-zh:
    status: "approved"
    content_hash: "<same actual hash>"
```

This illustrates the contract, not a reusable approval. Preserve reviewer/version/edit evidence in `qa/`; do not paste approvals into the distributed generic template. Release validation rejects missing or stale hashes. Any audience edit requires review again; narration edits also require verified audio and a new timeline. Export uses newline-joined canonical beat narration for PPT notes, never internal actions or `slide.notes` as a substitute. The manuscript uses actual spoken text, frame/sample timing and pronunciation correspondence.

## v0.1 compatibility

Existing v0.1 projects still use `qa/text-review.md` and their old render/speech commands. Apply the same two literary passes, synchronize scene strings and regenerate the legacy manuscript, but do not mistake its estimated timing for v0.2 audio-derived timing. Re-render text changes and inspect final-size evidence frames.

For either route, copy changes invalidate the affected visual approval. Check full-frame registration/layout evidence for v0.2, inspect composition in real motion and repeat final delivery verification. A clean audit is a useful diagnostic, not approval of facts, writing, layout or listening quality.
