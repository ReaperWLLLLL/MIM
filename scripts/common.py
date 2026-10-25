"""Shared helpers for mim scripts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SkillInputError(ValueError):
    """Raised when a user-authored input cannot be processed safely."""


def load_structured_file(path: Path) -> dict[str, Any]:
    """Load YAML or JSON and require a mapping at the document root."""
    path = path.resolve()
    if not path.is_file():
        raise SkillInputError(f"File does not exist: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SkillInputError(f"Invalid JSON in {path}: {exc}") from exc
    else:
        try:
            import yaml
        except ImportError as exc:
            raise SkillInputError(
                "PyYAML is required for YAML files. Install requirements.txt first."
            ) from exc
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SkillInputError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise SkillInputError(f"Expected a mapping at the root of {path}")
    return data


def to_python_class(value: str, *, fallback: str = "DeckScene") -> str:
    """Convert arbitrary text into a valid CamelCase Python class name."""
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    result = "".join(part[:1].upper() + part[1:] for part in parts)
    if not result:
        result = fallback
    if not result[0].isalpha():
        result = "Scene" + result
    return result


def to_project_slug(value: str, *, fallback: str = "manim-deck") -> str:
    """Convert text into a conservative Python project/package name."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def project_root_for(deck_path: Path) -> Path:
    """Infer the project root from planning/deck.yaml or a root-level deck file."""
    resolved = deck_path.resolve()
    if resolved.parent.name == "planning":
        return resolved.parent.parent
    return resolved.parent


def is_relative_output(path_text: str) -> bool:
    """Return true for safe project-relative output paths."""
    path = Path(path_text)
    return bool(path_text.strip()) and not path.is_absolute() and ".." not in path.parts
