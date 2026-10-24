# Source ingestion and evidence mapping

## Supported inputs

Use the bundled extractor for PDF papers and reports, Markdown, LaTeX source, and plain-text outlines:

```bash
python scripts/extract_source.py SOURCE... --output-dir PROJECT/.private/extracted
```

Add `--extract-images` only when figures must be inspected. The script never modifies
the original, records SHA-256 hashes, writes page-delimited Markdown, and creates
`source-manifest.json`. Treat that output as private working material unless the
source license permits republication. Read `licensing-and-publication.md` before
moving any extracted text or image into a tracked directory.

## Reading strategy

For the speaker's own research, use the supplied manuscript, method descriptions
and result tables as working inputs. Identify the author's contribution and the
prior work it builds on. Preserve experimental conditions and distinguish actual
measurements from illustrative examples; ask for missing evidence when a central
claim depends on it.

Do not summarize the whole source indiscriminately. Extract the research question or communication objective, gap, mechanism, key definitions, experimental setup, strongest result, uncertainty, limitation, and reusable visual evidence. For long papers, read the abstract, introduction, method overview, figure captions, central results, and conclusion first. Return to detailed sections only when a planned slide needs them.

## Evidence map

Create stable IDs before planning slides:

| ID pattern | Use |
|---|---|
| `src-paper-p12` | page-level source text |
| `fig-03` | paper or generated figure |
| `tbl-02` | result table |
| `eq-04` | equation or formal definition |
| `claim-05` | source-backed textual claim |

Record the bibliographic source, page or section locator, a concise paraphrase, and
the allowed transformation. Do not copy a complete caption unless quotation is
necessary and permitted. If a figure is redrawn with Manim, cite the original
evidence and mark the new visual as an explanatory reconstruction.
Keep each ID in backticks in the first column of the Markdown table. `validate_deck.py` reads this column and rejects duplicate or unregistered slide references.

## Scientific integrity

- Preserve units, denominators, baselines, confidence intervals, and experimental conditions.
- Do not infer causality from correlation unless the source supports it.
- Do not turn a qualitative statement into a fabricated numeric result.
- Separate source claims, presenter interpretation, and illustrative analogy.
- Surface conflicting evidence instead of silently selecting the convenient result.
- Mark unavailable or ambiguous evidence as unresolved in the planning artifacts.
