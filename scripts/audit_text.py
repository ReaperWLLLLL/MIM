#!/usr/bin/env python3
"""Audit audience-facing deck copy for mechanical AI-writing patterns."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from common import SkillInputError, load_structured_file, project_root_for
from research.spec import audience_copy as registered_audience_copy, content_hash


@dataclass(frozen=True)
class Finding:
    severity: str
    path: str
    label: str
    excerpt: str


HARD_PATTERNS = (
    (re.compile(r"[–—]"), "em or en dash"),
    (
        re.compile(
            r"(?:希望这对您有帮助|请告诉我|您想要|当然！|"
            r"I hope this helps|let me know|would you like)",
            flags=re.IGNORECASE,
        ),
        "chat-assistant artifact",
    ),
    (re.compile(r"(?:本页|本段|本视频|这张幻灯片)(?:将|主要|旨在|用于)?(?:展示|介绍|讲解|说明)|"
                r"\b(?:this slide|this video|on this slide)\s+(?:will|shows?|presents?)\b", re.IGNORECASE),
     "internal presentation instruction"),
    (re.compile(r"避免误解|为免误解|需要(?:强调|指出|说明)的是|仅供(?:演示|说明|参考)|"
                r"(?:这些|上述)(?:数值|数据|结果).{0,12}(?:并不|不)(?:代表|是)真实|"
                r"\b(?:to avoid (?:any )?confusion|for illustrative purposes only)\b", re.IGNORECASE),
     "defensive production language"),
    (re.compile(r"实验结果表明|实验结果显示|这(?:充分)?证明|本(?:方法|研究|系统).{0,10}(?:显著优势|优越性)|"
                r"\b(?:experimental results (?:show|demonstrate)|this (?:fully )?proves)\b", re.IGNORECASE),
     "formulaic report or unsupported promotional language"),
)

SUGGESTION_PATTERNS = (
    (re.compile(r"真正值得|这才是|更重要的是|关键是"), "manufactured emphasis"),
    (re.compile(r"不(?:只|仅|是)[^\n。！？]{0,80}而是"), "negative parallelism"),
    (re.compile(r"不仅[^\n。！？]{0,80}而且"), "not-only-but-also parallelism"),
    (re.compile(r"有说服力|至关重要|标志着|不断演变的格局|深入探讨"), "inflated or stock phrasing"),
    (re.compile(r"让我们|接下来我们|现在让我们"), "announced transition"),
    (
        re.compile(
            r"\b(?:delve|pivotal|crucial|landscape|testament|showcase)\b",
            flags=re.IGNORECASE,
        ),
        "high-frequency AI vocabulary",
    ),
)


def audience_copy(data: dict[str, Any]) -> Iterable[tuple[str, str]]:
    """Compatibility iterator over the shared complete audience-text registry."""
    yield from registered_audience_copy(data).items()


def excerpt_for(text: str, match: re.Match[str], radius: int = 32) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    excerpt = re.sub(r"\s+", " ", text[start:end]).strip()
    if start:
        excerpt = "..." + excerpt
    if end < len(text):
        excerpt += "..."
    return excerpt


def audit(data: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for path, text in audience_copy(data):
        for pattern, label in HARD_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(Finding("error", path, label, excerpt_for(text, match)))
        for pattern, label in SUGGESTION_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(Finding("review", path, label, excerpt_for(text, match)))
    return findings


def markdown_report(deck: Path, findings: list[Finding], *, digest: str | None = None) -> str:
    errors = [item for item in findings if item.severity == "error"]
    suggestions = [item for item in findings if item.severity == "review"]
    lines = [
        "# Text humanization review",
        "",
        "Text review: pending",
        *([f"Audience copy SHA-256: `{digest}`"] if digest else []),
        f"Deck: `{deck.name}`",
        f"Hard findings: {len(errors)}",
        f"Review candidates: {len(suggestions)}",
        "",
        "Mechanical checks do not approve the writing. Compare every rewrite with the",
        "evidence map, read the notes aloud, synchronize visible Manim strings, and",
        "re-render all affected slides before changing the status to `approved`.",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No mechanical findings. Manual language review is still required.")
    else:
        lines.extend(
            [
                "| Severity | Path | Pattern | Excerpt |",
                "|---|---|---|---|",
            ]
        )
        for item in findings:
            excerpt = item.excerpt.replace("|", "\\|")
            lines.append(
                f"| {item.severity} | `{item.path}` | {item.label} | {excerpt} |"
            )
    lines.extend(
        [
            "",
            "## Manual acceptance",
            "",
            "- [ ] Claims, numbers, equations, citations, and scope still match the evidence map.",
            "- [ ] Titles state concrete claims without slogan-like or promotional phrasing.",
            "- [ ] Notes sound natural when read aloud in the requested language.",
            "- [ ] Standard technical terms remain consistent across slides and narration.",
            "- [ ] Visible scene text matches `deck.yaml` and has been re-rendered.",
            "- [ ] Updated renders pass text-fit and visual QA checks.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Markdown report path; defaults to PROJECT_DIR/qa/text-review.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data = load_structured_file(args.deck)
    except SkillInputError as exc:
        print(exc, file=sys.stderr)
        return 1

    deck = args.deck.resolve()
    findings = audit(data)
    root = project_root_for(deck)
    output = args.output.resolve() if args.output else root / "qa" / "text-review.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    copy = registered_audience_copy(data)
    digest = content_hash(copy)
    manifest = {"schema_version": "0.2", "content_hash": digest, "copy": copy}
    (output.parent / "audience-copy.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.write_text(markdown_report(deck, findings, digest=digest) + "\n", encoding="utf-8")

    errors = [item for item in findings if item.severity == "error"]
    suggestions = [item for item in findings if item.severity == "review"]
    print(f"Wrote text review: {output}")
    print(f"Hard findings: {len(errors)}")
    print(f"Review candidates: {len(suggestions)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
