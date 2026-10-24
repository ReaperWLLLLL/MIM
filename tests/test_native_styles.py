import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_release import audit, inspect_blob

spec = importlib.util.spec_from_file_location("native_styles", ROOT / "assets/native-example/styles.py")
styles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(styles)


def luminance(code):
    rgb = [int(code[i:i+2], 16) / 255 for i in (1, 3, 5)]
    rgb = [x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in rgb]
    return sum(x*w for x, w in zip(rgb, (.2126, .7152, .0722)))


@pytest.mark.parametrize("name", ["midnight", "daylight", "notebook"])
def test_readable_text_colors_and_independent_values(name):
    style = styles.load_style(name)
    bg = luminance(style["background"])
    for role in ("foreground", "primary", "secondary", "accent", "muted"):
        fg = luminance(style[role])
        assert (max(fg,bg)+.05)/(min(fg,bg)+.05) >= 4.5, role
    style["primary"] = "changed"
    assert styles.load_style(name)["primary"] != "changed"


def test_unknown_style_is_not_silent_fallback():
    with pytest.raises(ValueError):
        styles.load_style("typo")


def test_private_sources_and_secrets_are_flagged():
    assert inspect_blob(".private/sources/lecture.pdf", b"source")
    assert inspect_blob("notes.md", ("/Users/" + "someone/private/file").encode())
    assert inspect_blob("config.txt", ("ghp_" + "x"*36).encode())
    assert inspect_blob("assets/source-page.png", b"\x89PNG\xff")
    assert not inspect_blob("assets/demo/style-daylight.png", b"\x89PNG\xff")
    assert not inspect_blob("references/guide.md", b"Keep papers in .private/")


def test_audit_reads_staged_blob_not_working_copy(tmp_path):
    import subprocess
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)
    git("init")
    path = tmp_path / "notes.md"
    path.write_text("/Users/" + "someone/private/file")
    git("add", "notes.md")
    path.write_text("clean working copy")
    count, findings = audit(tmp_path, "INDEX")
    assert count == 1
    assert findings == [("notes.md", "personal absolute path")]
