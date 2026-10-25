#!/usr/bin/env python3
"""Inspect actual Git blobs, not ignored working files, before publication.

Use --ref INDEX for staged files, HEAD (default) for a commit, or any commit ref.
This source-only repository allows reviewed demo PNG/GIFs under assets/demo/.
The scan flags likely private material; it cannot decide copyright ownership.
"""
import argparse
from pathlib import Path
import re
import subprocess


def inspect_blob(path, data):
    findings = []
    parts = Path(path).parts
    suffix = Path(path).suffix.lower()
    if any(p in {".private", ".venv", "venv", "models", "media", "cache",
                 ".worktrees", ".superpowers", "coursework", "social"} for p in parts):
        findings.append("private/generated directory")
    if path.startswith(("docs/research/", "docs/superpowers/")):
        findings.append("local development record")
    if Path(path).name.startswith(".env") and Path(path).name != ".env.example":
        findings.append("environment configuration")
    if suffix in {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".ttf", ".ttc", ".otf",
                  ".woff", ".woff2", ".wav", ".mp3", ".mp4", ".mov", ".zip", ".tar",
                  ".gz", ".safetensors", ".ckpt", ".pem", ".key"}:
        findings.append("document, media, font, archive, credential or model")
    approved_images = {
        "attention-deck-overview.png", "qkv-attention.gif",
        "style-midnight.png", "style-daylight.png", "style-notebook.png",
        "style-midnight.gif", "style-daylight.gif", "style-notebook.gif",
        "deepinfer-cluster-scheduling.gif",
    }
    if suffix in {".png", ".gif", ".jpg", ".jpeg", ".webp"}:
        if str(Path(path).parent) != "assets/demo" or Path(path).name not in approved_images:
            findings.append("image outside reviewed demo inventory")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if suffix not in {".png", ".gif"}:
            findings.append("unreviewed binary")
        return findings
    patterns = [
        (r"/" + r"Users/[^/\s]+/", "personal absolute path"),
        (r"gh[pousr]_[A-Za-z0-9]{30,}", "GitHub credential"),
        (r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----", "private key"),
    ]
    for pattern, reason in patterns:
        if re.search(pattern, text):
            findings.append(reason)
    return findings


def audit(repo, ref):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])
    if ref == "INDEX":
        entries = []
        for record in git("ls-files", "--stage", "-z").split(b"\0"):
            if record:
                meta, path = record.split(b"\t", 1)
                mode, oid, stage = meta.split()
                if stage != b"0":
                    raise ValueError("Resolve unmerged index entries before publishing")
                entries.append((mode, oid, path))
    else:
        entries = []
        for record in git("ls-tree", "-rz", ref).split(b"\0"):
            if record:
                meta, path = record.split(b"\t", 1)
                mode, kind, oid = meta.split()
                entries.append((mode, oid, path))
    findings = []
    for mode, oid, raw_path in entries:
        path = raw_path.decode("utf-8")
        if mode not in {b"100644", b"100755"}:
            findings.append((path, "symlink/submodule is outside source-only release"))
            continue
        data = git("cat-file", "blob", oid.decode())
        findings.extend((path, reason) for reason in inspect_blob(path, data))
    return len(entries), findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    count, findings = audit(args.repo, args.ref)
    for path, reason in findings:
        print(f"{path}: {reason}")
    print(f"{args.ref}: {count} Git entries checked; {len(findings)} findings")
    return bool(findings)


if __name__ == "__main__":
    raise SystemExit(main())
