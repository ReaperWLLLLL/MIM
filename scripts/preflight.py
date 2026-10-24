#!/usr/bin/env python3
"""Check system and Python dependencies required by the selected workflow."""

from __future__ import annotations

import argparse
import importlib.util
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass


@dataclass
class Check:
    name: str
    required: bool
    ok: bool
    detail: str


def command_check(name: str, *, required: bool) -> Check:
    path = shutil.which(name)
    if not path:
        return Check(name, required, False, "not found on PATH")
    try:
        result = subprocess.run(
            [path, "-version" if name in {"ffmpeg", "ffprobe"} else "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first_line = (result.stdout or result.stderr).splitlines()
        detail = first_line[0] if first_line else path
        if result.returncode != 0:
            return Check(name, required, False, f"exit {result.returncode}: {detail}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, required, False, f"cannot run {path}: {exc}")
    return Check(name, required, True, detail)


def module_check(module: str, label: str, *, required: bool) -> Check:
    ok = importlib.util.find_spec(module) is not None
    return Check(label, required, ok, "available" if ok else f"missing Python module: {module}")


def distribution_version_check(
    distribution: str, label: str, pattern: str, expected: str
) -> Check:
    try:
        installed = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return Check(label, True, False, f"missing Python distribution: {distribution}")
    ok = re.fullmatch(pattern, installed) is not None
    detail = f"{installed} ({'compatible' if ok else f'expected {expected}'})"
    return Check(label, True, ok, detail)


def collect_checks(args: argparse.Namespace) -> list[Check]:
    checks = [
        Check(
            "python",
            True,
            sys.version_info >= (3, 10),
            f"{platform.python_implementation()} {platform.python_version()}",
        ),
        command_check("ffmpeg", required=True),
        command_check("ffprobe", required=True),
        command_check("manim", required=True),
        command_check("manim-slides", required=True),
        distribution_version_check("manim", "Manim package", r"0\.20(?:\.\d+)?", "0.20.x"),
        distribution_version_check(
            "manim-slides", "Manim Slides package", r"5\.6\.0", "5.6.0"
        ),
        command_check("latex", required=args.need_latex),
        module_check("yaml", "PyYAML", required=True),
        module_check("PIL", "Pillow", required=True),
        module_check("pypdf", "pypdf", required=args.need_pdf_input),
    ]
    if args.need_pptx:
        checks.append(module_check("pptx", "python-pptx", required=True))
    return checks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--need-latex", action="store_true", help="Require a LaTeX executable")
    parser.add_argument(
        "--need-pdf-input", action="store_true", help="Require pypdf for PDF extraction"
    )
    parser.add_argument("--need-pptx", action="store_true", help="Require python-pptx")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checks = collect_checks(args)
    failed_required = [check for check in checks if check.required and not check.ok]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not failed_required,
                    "checks": [asdict(check) for check in checks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for check in checks:
            status = "OK" if check.ok else ("MISSING" if check.required else "OPTIONAL")
            requirement = "required" if check.required else "optional"
            print(f"[{status:8}] {check.name} ({requirement}) - {check.detail}")
        if failed_required:
            print("\nPreflight failed. Install the missing required dependencies.", file=sys.stderr)
        else:
            print("\nPreflight passed.")
    return 1 if failed_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
