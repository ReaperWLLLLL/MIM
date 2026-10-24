#!/usr/bin/env python3
"""Validate the narrative, timing, evidence, and output contract in deck.yaml."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from common import SkillInputError, is_relative_output, load_structured_file, project_root_for


VALID_KINDS = {"research-talk", "thesis-defense", "technical-lesson"}
VALID_PURPOSES = {
    "open",
    "motivate",
    "explain",
    "derive",
    "compare",
    "evidence",
    "transition",
    "recap",
    "close",
}
VALID_VISUAL_MODES = {"manim", "static", "media", "hybrid"}
EVIDENCE_PURPOSES = {"explain", "derive", "compare", "evidence"}
REQUIRED_OUTPUTS = {"html", "pptx", "pdf", "speech"}
OUTPUT_SUFFIXES = {"html": ".html", "pptx": ".pptx", "pdf": ".pdf", "speech": ".md"}


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def evidence_ids_from_markdown(path: Path) -> tuple[set[str], set[str]]:
    """Extract first-column evidence IDs and report duplicates from a Markdown table."""
    ids: set[str] = set()
    duplicates: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*`?([A-Za-z0-9][A-Za-z0-9._-]*)`?\s*\|", line)
        if not match:
            continue
        evidence_id = match.group(1)
        if evidence_id.lower() == "id" or set(evidence_id) == {"-"}:
            continue
        if evidence_id in ids:
            duplicates.add(evidence_id)
        ids.add(evidence_id)
    return ids, duplicates


def _validate_deck(data: dict[str, Any], *, deck_path: Path, check_paths: bool,
                   schema_version: str = "0.1", required_outputs: set[str] = REQUIRED_OUTPUTS) -> list[Finding]:
    findings: list[Finding] = []

    def error(path: str, message: str) -> None:
        findings.append(Finding("error", path, message))

    def warning(path: str, message: str) -> None:
        findings.append(Finding("warning", path, message))

    root = project_root_for(deck_path)
    evidence_map_path = root / "planning" / "evidence-map.md"
    evidence_ids: set[str] = set()
    if not evidence_map_path.is_file():
        error("planning.evidence-map", f"required file does not exist: {evidence_map_path}")
    else:
        try:
            evidence_ids, duplicate_evidence_ids = evidence_ids_from_markdown(evidence_map_path)
        except OSError as exc:
            error("planning.evidence-map", f"cannot read evidence map: {exc}")
        else:
            if not evidence_ids:
                error("planning.evidence-map", "must declare at least one evidence ID")
            if duplicate_evidence_ids:
                error(
                    "planning.evidence-map",
                    f"duplicate evidence IDs: {sorted(duplicate_evidence_ids)}",
                )

    if str(data.get("schema_version")) != schema_version:
        error("schema_version", f'must be "{schema_version}"')

    project = data.get("project")
    if not isinstance(project, dict):
        error("project", "must be a mapping")
        project = {}

    for field in ("title", "language", "audience", "theme"):
        if not non_empty_string(project.get(field)):
            error(f"project.{field}", "must be a non-empty string")
    if project.get("kind") not in VALID_KINDS:
        error("project.kind", f"must be one of {sorted(VALID_KINDS)}")
    if not positive_number(project.get("duration_minutes")):
        error("project.duration_minutes", "must be a positive number")
    if project.get("aspect_ratio") != "16:9":
        error("project.aspect_ratio", 'v0.1 requires "16:9"')

    source_files = project.get("source_files")
    if not isinstance(source_files, list) or not source_files:
        error("project.source_files", "must be a non-empty list")
        source_files = []
    elif any(not non_empty_string(item) for item in source_files):
        error("project.source_files", "all entries must be non-empty strings")

    for index, path_text in enumerate(source_files):
        if non_empty_string(path_text) and not is_relative_output(path_text):
            error(
                f"project.source_files[{index}]",
                "must stay inside the project and may not contain '..'",
            )

    if check_paths:
        for index, path_text in enumerate(source_files):
            if non_empty_string(path_text) and not (root / path_text).is_file():
                error(f"project.source_files[{index}]", f"file does not exist: {path_text}")

    narrative = data.get("narrative")
    if not isinstance(narrative, dict):
        error("narrative", "must be a mapping")
        narrative = {}
    if not non_empty_string(narrative.get("thesis")):
        error("narrative.thesis", "must be a non-empty string")
    takeaways = narrative.get("takeaways")
    if not isinstance(takeaways, list) or not (1 <= len(takeaways) <= 5):
        error("narrative.takeaways", "must contain one to five takeaways")
    elif any(not non_empty_string(item) for item in takeaways):
        error("narrative.takeaways", "all takeaways must be non-empty strings")

    slides = data.get("slides")
    if not isinstance(slides, list) or not slides:
        error("slides", "must be a non-empty list")
        slides = []

    seen_ids: set[str] = set()
    seen_scene_classes: set[str] = set()
    total_seconds = 0.0

    for index, slide in enumerate(slides):
        base = f"slides[{index}]"
        if not isinstance(slide, dict):
            error(base, "must be a mapping")
            continue

        slide_id = slide.get("id")
        if not non_empty_string(slide_id) or not re.fullmatch(r"s\d{2,3}", slide_id):
            error(f"{base}.id", "must match sNN or sNNN")
        elif slide_id in seen_ids:
            error(f"{base}.id", f"duplicate slide id: {slide_id}")
        else:
            seen_ids.add(slide_id)

        for field in ("section", "title", "claim", "scene_class", "notes"):
            if not non_empty_string(slide.get(field)):
                error(f"{base}.{field}", "must be a non-empty string")

        scene_class = slide.get("scene_class")
        if non_empty_string(scene_class):
            if not scene_class.isidentifier():
                error(f"{base}.scene_class", "must be a valid Python identifier")
            elif scene_class in seen_scene_classes:
                error(f"{base}.scene_class", f"must be unique: {scene_class}")
            else:
                seen_scene_classes.add(scene_class)

        purpose = slide.get("purpose")
        if purpose not in VALID_PURPOSES:
            error(f"{base}.purpose", f"must be one of {sorted(VALID_PURPOSES)}")

        duration = slide.get("duration_seconds")
        if not positive_number(duration):
            error(f"{base}.duration_seconds", "must be a positive number")
        else:
            total_seconds += float(duration)

        visual_mode = slide.get("visual_mode")
        if visual_mode not in VALID_VISUAL_MODES:
            error(f"{base}.visual_mode", f"must be one of {sorted(VALID_VISUAL_MODES)}")

        source_refs = slide.get("source_refs")
        if not isinstance(source_refs, list) or any(
            not non_empty_string(item) for item in source_refs
        ):
            error(f"{base}.source_refs", "must be a list of non-empty strings")
        elif purpose in EVIDENCE_PURPOSES and not source_refs:
            error(f"{base}.source_refs", "evidence-bearing slides require at least one source ref")
        if isinstance(source_refs, list):
            unknown_refs = sorted(
                ref
                for ref in source_refs
                if non_empty_string(ref) and ref not in evidence_ids
            )
            if unknown_refs:
                error(
                    f"{base}.source_refs",
                    f"IDs are not declared in planning/evidence-map.md: {unknown_refs}",
                )

        beats = slide.get("beats")
        if visual_mode in {"manim", "hybrid"}:
            if not isinstance(beats, list) or not beats:
                error(f"{base}.beats", "manim and hybrid slides require at least one beat")
                beats = []
        elif beats is None:
            beats = []
        elif not isinstance(beats, list):
            error(f"{base}.beats", "must be a list")
            beats = []

        beat_ids: set[str] = set()
        for beat_index, beat in enumerate(beats):
            beat_base = f"{base}.beats[{beat_index}]"
            if not isinstance(beat, dict):
                error(beat_base, "must be a mapping")
                continue
            beat_id = beat.get("id")
            if not non_empty_string(beat_id):
                error(f"{beat_base}.id", "must be a non-empty string")
            elif beat_id in beat_ids:
                error(f"{beat_base}.id", f"duplicate beat id: {beat_id}")
            else:
                beat_ids.add(beat_id)
            for field in ("narration", "action"):
                if not non_empty_string(beat.get(field)):
                    error(f"{beat_base}.{field}", "must be a non-empty string")

        qa = slide.get("qa")
        if not isinstance(qa, dict):
            warning(f"{base}.qa", "recommended mapping is missing")
        else:
            for field in ("must_show", "avoid"):
                values = qa.get(field)
                if not isinstance(values, list) or any(
                    not non_empty_string(item) for item in values
                ):
                    warning(f"{base}.qa.{field}", "should be a list of non-empty strings")

    duration_minutes = project.get("duration_minutes")
    if positive_number(duration_minutes) and total_seconds:
        target_seconds = float(duration_minutes) * 60.0
        delta = abs(total_seconds - target_seconds) / target_seconds
        if delta > 0.10:
            error(
                "slides.duration_seconds",
                f"sum is {total_seconds:g}s, outside 10% of target {target_seconds:g}s",
            )

    outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        error("outputs", "must be a mapping")
        outputs = {}
    missing_outputs = required_outputs - set(outputs)
    if missing_outputs:
        error("outputs", f"missing required outputs: {sorted(missing_outputs)}")
    seen_output_paths: set[str] = set()
    for name, path_text in outputs.items():
        if not isinstance(name, str) or not non_empty_string(path_text):
            error(f"outputs.{name}", "must be a non-empty relative path")
        elif not is_relative_output(path_text):
            error(f"outputs.{name}", "must stay inside the project and may not contain '..'")
        else:
            suffixes = {**OUTPUT_SUFFIXES, **({"video": ".mp4"} if schema_version == "0.2" else {})}
            if name in suffixes and Path(path_text).suffix.lower() != suffixes[name]:
                error(f"outputs.{name}", f"must end with {suffixes[name]}")
            normalized = Path(path_text).as_posix()
            if normalized in seen_output_paths:
                error(f"outputs.{name}", f"duplicates another output path: {path_text}")
            seen_output_paths.add(normalized)

    return findings


def validate_deck(data: dict[str, Any], *, deck_path: Path, check_paths: bool) -> list[Finding]:
    """Dispatch legacy and research contracts while preserving the CLI finding API."""
    if str(data.get("schema_version")) == "0.2":
        from research.spec import _validate
        errors = _validate(data, project_root_for(deck_path), check_paths=check_paths)
        return [Finding("error", *message.split(": ", 1)) for message in errors]
    return _validate_deck(data, deck_path=deck_path, check_paths=check_paths)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path, help="Path to deck.yaml or deck.json")
    parser.add_argument("--check-paths", action="store_true", help="Verify source files exist")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        data = load_structured_file(args.deck)
        findings = validate_deck(data, deck_path=args.deck, check_paths=args.check_paths)
    except SkillInputError as exc:
        findings = [Finding("error", str(args.deck), str(exc))]

    errors = [finding for finding in findings if finding.severity == "error"]
    if args.json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "errors": len(errors),
                    "warnings": sum(f.severity == "warning" for f in findings),
                    "findings": [asdict(finding) for finding in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for finding in findings:
            print(f"[{finding.severity.upper():7}] {finding.path}: {finding.message}")
        if errors:
            print(f"\nDeck validation failed with {len(errors)} error(s).", file=sys.stderr)
        else:
            warning_count = sum(f.severity == "warning" for f in findings)
            print(f"Deck validation passed with {warning_count} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
