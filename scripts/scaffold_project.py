#!/usr/bin/env python3
"""Create a new mim project from the bundled template."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import to_project_slug, to_python_class


SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "project-template"
TEXT_SUFFIXES = {"", ".md", ".py", ".toml", ".yaml", ".yml", ".txt"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--title", required=True, help="Human-facing project title")
    parser.add_argument("--force", action="store_true", help="Overwrite colliding template files")
    return parser.parse_args(argv)


def render_placeholders(root: Path, substitutions: dict[str, str]) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        rendered = text
        for key, value in substitutions.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        if "{{" in rendered or "}}" in rendered:
            raise ValueError(f"Unresolved template placeholder in {path}")
        path.write_text(rendered, encoding="utf-8")


def scaffold(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    if not TEMPLATE_ROOT.is_dir():
        print(f"Template directory is missing: {TEMPLATE_ROOT}", file=sys.stderr)
        return 1
    if target.exists() and not target.is_dir():
        print(f"Target exists and is not a directory: {target}", file=sys.stderr)
        return 1
    if target.exists() and any(target.iterdir()) and not args.force:
        print(f"Refusing to scaffold into non-empty directory: {target}", file=sys.stderr)
        print("Use --force only when overwriting the generated template is intended.", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEMPLATE_ROOT, target, dirs_exist_ok=True)
    project_slug = to_project_slug(args.title)
    substitutions = {
        "PROJECT_TITLE": args.title,
        "PROJECT_CLASS": to_python_class(args.title, fallback="ResearchTalk"),
        "PROJECT_SLUG": project_slug,
    }
    render_placeholders(target, substitutions)

    print(f"Scaffolded project: {target}")
    print("Next steps:")
    print(f"  1. Add sources under {target / 'source'}")
    print(f"  2. Edit {target / 'planning' / 'design-brief.md'}")
    print(f"  3. Edit and validate {target / 'planning' / 'deck.yaml'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return scaffold(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
