from __future__ import annotations

import copy
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import render_deck
import scaffold_project
import audit_text
import extract_source
import validate_deck
import verify_outputs
import write_speech
from export_html import export_html
from postprocess_pptx import (
    add_static_fallback,
    resolve_target,
    update_relationship_xml,
)
from common import load_structured_file, to_project_slug, to_python_class


class SkillPackageTest(unittest.TestCase):
    def test_portable_frontmatter_and_resource_map(self) -> None:
        skill_path = REPO_ROOT / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = yaml.safe_load(match.group(1))
        self.assertEqual(set(frontmatter), {"name", "description"})
        self.assertEqual(frontmatter["name"], "mim")
        self.assertLess(len(text.splitlines()), 500)
        # References must be discoverable, not all injected into the entry.
        # Follow existing relative links/code paths through progressive disclosure.
        reached: set[Path] = set()
        pending = [skill_path.resolve()]
        while pending:
            page = pending.pop()
            if page in reached:
                continue
            reached.add(page)
            body = page.read_text(encoding="utf-8")
            targets = re.findall(r"\]\(([^)\s]+\.md)(?:#[^)]*)?\)", body)
            targets += re.findall(r"`([^`\s]+\.md)`", body)
            for target in targets:
                if "://" in target:
                    continue
                candidate = (page.parent / target).resolve()
                if candidate.is_relative_to(REPO_ROOT.resolve()) and candidate.is_file():
                    pending.append(candidate)
        references = {p.resolve() for p in (REPO_ROOT / "references").glob("*.md")}
        self.assertFalse(references - reached, f"Undiscoverable references: {references - reached}")

        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for path in (
            "assets/demo/style-midnight.gif",
            "assets/demo/style-daylight.gif",
            "assets/demo/style-notebook.gif",
        ):
            self.assertIn(path, readme)
            self.assertTrue((REPO_ROOT / path).exists())

    def test_openai_interface_matches_skill(self) -> None:
        data = yaml.safe_load((REPO_ROOT / "agents" / "openai.yaml").read_text())
        interface = data["interface"]
        self.assertIn("$mim", interface["default_prompt"])
        self.assertLessEqual(len(interface["short_description"]), 64)

    def test_release_provenance_and_private_source_defaults(self) -> None:
        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        scripts = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "scripts").glob("*.py")
        )
        notices = (REPO_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        project_ignore = (
            REPO_ROOT / "assets" / "project-template" / ".gitignore"
        ).read_text(encoding="utf-8")

        self.assertIn("pypdf", requirements)
        self.assertIn("pypdf", workflow)
        self.assertNotIn("PyMuPDF", requirements + workflow)
        self.assertNotIn("import fitz", scripts)
        for item in ("Manim Community Edition", "pypdf", "Humanizer-zh", "FFmpeg"):
            self.assertIn(item, notices)
        for pattern in (".private/", "planning/extracted/", "source/*.pdf"):
            self.assertIn(pattern, project_ignore)


class HelpersTest(unittest.TestCase):
    def test_class_and_slug_normalization(self) -> None:
        self.assertEqual(to_python_class("2026 research talk"), "Scene2026ResearchTalk")
        self.assertEqual(to_project_slug("Research Talk 2026"), "research-talk-2026")
        self.assertEqual(to_project_slug("科研演讲"), "manim-deck")

    def test_pptx_relationship_retargets_unique_poster(self) -> None:
        relationships = b"""<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/video" Target="../media/media2.mp4"/>
  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>
</Relationships>"""
        updated, video, poster = update_relationship_xml(
            relationships,
            rel_path="ppt/slides/_rels/slide2.xml.rels",
            poster_number=2,
        )
        self.assertEqual(video, "ppt/media/media2.mp4")
        self.assertEqual(poster, "ppt/media/manim-poster-2.png")
        self.assertIn(b"manim-poster-2.png", updated)
        self.assertEqual(
            resolve_target("ppt/slides/_rels/slide2.xml.rels", "../media/media2.mp4"),
            "ppt/media/media2.mp4",
        )

    def test_pptx_static_fallback_is_behind_video_and_idempotent(self) -> None:
        slide = b"""<?xml version='1.0' encoding='UTF-8'?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
       xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld><p:spTree>
    <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
    <p:pic>
      <p:nvPicPr><p:cNvPr id="2" name="video"><a:videoFile r:link="rId3"/></p:cNvPr><p:cNvPicPr/><p:nvPr><a:videoFile r:link="rId3"/></p:nvPr></p:nvPicPr>
      <p:blipFill><a:blip r:embed="rId4"/></p:blipFill>
    </p:pic>
  </p:spTree></p:cSld>
</p:sld>"""
        updated, count = add_static_fallback(slide, slide_number=2)
        self.assertEqual(count, 1)
        root = ET.fromstring(updated)
        p_ns = "http://schemas.openxmlformats.org/presentationml/2006/main"
        a_ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        pictures = root.findall(f".//{{{p_ns}}}pic")
        self.assertEqual(len(pictures), 2)
        self.assertEqual(
            pictures[0].find(f".//{{{p_ns}}}cNvPr").get("name"),
            "manim-static-poster-2",
        )
        self.assertIsNone(pictures[0].find(f".//{{{a_ns}}}videoFile"))
        repeated, repeated_count = add_static_fallback(updated, slide_number=2)
        self.assertEqual(repeated_count, 0)
        self.assertEqual(repeated, updated)

    def test_mixed_chinese_timing_counts_latin_terms(self) -> None:
        estimate = write_speech.estimate_minutes("算力调度 GPU SLA", "zh-CN")
        self.assertGreater(estimate, 4 / 240)

    def test_text_audit_separates_hard_and_judgment_findings(self) -> None:
        data = {
            "project": {"title": "A — B"},
            "narrative": {
                "thesis": "真正值得带走的不是口号，而是细节。",
                "takeaways": [],
            },
            "slides": [],
        }
        findings = audit_text.audit(data)
        self.assertTrue(any(item.severity == "error" for item in findings))
        self.assertTrue(any(item.severity == "review" for item in findings))

    def test_pdf_extraction_and_page_verification_use_pypdf(self) -> None:
        from PIL import Image
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source.pdf"
            extracted = root / "source.extracted.md"
            writer = PdfWriter()
            writer.add_blank_page(width=1280, height=720)
            with source.open("wb") as handle:
                writer.write(handle)

            details = extract_source.extract_pdf_source(
                source, extracted, image_dir=None
            )
            pages, sizes = verify_outputs.pdf_page_info(source)

            self.assertEqual(details["pages"], 1)
            self.assertEqual(pages, 1)
            self.assertEqual(sizes, [(1280.0, 720.0)])
            self.assertIn("## Page 1", extracted.read_text(encoding="utf-8"))

            image_source = root / "image-source.pdf"
            image_output = root / "image-source.extracted.md"
            image_dir = root / "images"
            Image.new("RGB", (64, 32), "red").save(image_source, "PDF")
            image_details = extract_source.extract_pdf_source(
                image_source, image_output, image_dir=image_dir
            )
            self.assertEqual(len(image_details["images"]), 1)
            self.assertTrue(Path(image_details["images"][0]).is_file())


class ScaffoldAndValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "demo"
        code = scaffold_project.main([str(self.root), "--title", "Research Demo"])
        self.assertEqual(code, 0)
        self.deck_path = self.root / "planning" / "deck.yaml"
        self.data = load_structured_file(self.deck_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_starter_validates(self) -> None:
        findings = validate_deck.validate_deck(
            self.data, deck_path=self.deck_path, check_paths=True
        )
        self.assertFalse([item for item in findings if item.severity == "error"])
        text_report = self.root / "qa" / "text-review.md"
        self.assertIn("Text review: pending", text_report.read_text(encoding="utf-8"))

    def test_duplicate_slide_and_scene_fail(self) -> None:
        invalid = copy.deepcopy(self.data)
        invalid["slides"][1]["id"] = invalid["slides"][0]["id"]
        invalid["slides"][1]["scene_class"] = invalid["slides"][0]["scene_class"]
        findings = validate_deck.validate_deck(
            invalid, deck_path=self.deck_path, check_paths=False
        )
        messages = "\n".join(item.message for item in findings)
        self.assertIn("duplicate slide id", messages)
        self.assertIn("must be unique", messages)

    def test_unknown_evidence_reference_fails(self) -> None:
        invalid = copy.deepcopy(self.data)
        invalid["slides"][1]["source_refs"] = ["claim-not-registered"]
        findings = validate_deck.validate_deck(
            invalid, deck_path=self.deck_path, check_paths=False
        )
        self.assertTrue(
            any(
                item.path == "slides[1].source_refs"
                and "not declared" in item.message
                for item in findings
            )
        )

    def test_output_escape_fails(self) -> None:
        invalid = copy.deepcopy(self.data)
        invalid["outputs"]["html"] = "../presentation.html"
        findings = validate_deck.validate_deck(
            invalid, deck_path=self.deck_path, check_paths=False
        )
        self.assertTrue(any(item.path == "outputs.html" for item in findings))

    def test_output_suffix_and_external_source_fail(self) -> None:
        invalid = copy.deepcopy(self.data)
        invalid["outputs"]["pptx"] = "deliverables/presentation.zip"
        invalid["project"]["source_files"] = ["../paper.pdf"]
        findings = validate_deck.validate_deck(
            invalid, deck_path=self.deck_path, check_paths=False
        )
        paths = {item.path for item in findings if item.severity == "error"}
        self.assertIn("outputs.pptx", paths)
        self.assertIn("project.source_files[0]", paths)

    def test_partial_render_uses_preview_outputs(self) -> None:
        selected = render_deck.parse_selection(self.data, "s02")
        command = render_deck.convert_command(
            output_type="html",
            output_path=self.root / "build" / "draft" / "preview.html",
            selected=selected,
            slides_folder=self.root / "build" / "draft" / "slides",
        )
        self.assertIn("CoreMechanism", command)
        self.assertIn("--one-file", command)
        self.assertNotIn("Opening", command)

    def test_final_render_uses_unambiguous_quality_flag(self) -> None:
        selected = render_deck.parse_selection(self.data, None)
        command = render_deck.render_command(
            root=self.root,
            profile="final",
            selected=selected,
            slides_folder=self.root / "build" / "final" / "slides",
        )
        self.assertIn("--quality=h", command)
        self.assertNotIn("-qh", command)

    def test_rerender_cleans_only_selected_scene_outputs(self) -> None:
        slides_folder = self.root / "build" / "final" / "slides"
        selected = render_deck.parse_selection(self.data, "s02")
        selected_name = selected[0]["scene_class"]
        untouched_name = self.data["slides"][0]["scene_class"]
        for scene_name in (selected_name, untouched_name):
            scene_dir = slides_folder / "files" / scene_name
            scene_dir.mkdir(parents=True, exist_ok=True)
            (scene_dir / "segment.mp4").write_bytes(b"generated")
            (slides_folder / f"{scene_name}.json").write_text("{}", encoding="utf-8")

        render_deck.clean_selected_scene_outputs(slides_folder, selected)

        self.assertFalse((slides_folder / "files" / selected_name).exists())
        self.assertFalse((slides_folder / f"{selected_name}.json").exists())
        self.assertTrue((slides_folder / "files" / untouched_name).is_dir())
        self.assertTrue((slides_folder / f"{untouched_name}.json").is_file())

    def test_speech_contains_all_slide_sections(self) -> None:
        manuscript, warnings = write_speech.build_speech(self.data)
        self.assertEqual(manuscript.count("\n## s"), len(self.data["slides"]))
        self.assertIn("## s01 |", manuscript)
        self.assertNotIn("—", manuscript)
        self.assertIn("## Timing summary", manuscript)
        self.assertFalse(warnings)

    def test_html_export_is_self_contained(self) -> None:
        slides_folder = self.root / "build" / "draft" / "slides"
        media = slides_folder / "files" / "Opening" / "opening.mp4"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"fake-mp4-for-structural-test")
        manifest = {
            "slides": [
                {
                    "file": str(media),
                    "notes": "Opening notes",
                    "loop": False,
                    "playback_rate": 1.0,
                }
            ]
        }
        import json

        (slides_folder / "Opening.json").write_text(json.dumps(manifest), encoding="utf-8")
        output = self.root / "deliverables" / "presentation.html"
        count = export_html(
            title="Research Demo",
            scene_names=["Opening"],
            slides_folder=slides_folder,
            output_path=output,
        )
        text = output.read_text(encoding="utf-8")
        self.assertEqual(count, 1)
        self.assertIn("data:video/mp4;base64,", text)
        self.assertIn('<link rel="icon" href="data:,">', text)
        self.assertNotIn('src="https://', text)

    def test_rebuild_template_is_complete_but_visual_approval_starts_pending(self) -> None:
        rebuild_checks = verify_outputs.check_rebuild(self.root)
        self.assertTrue(all(check.ok for check in rebuild_checks))
        rebuild_path = self.root / "deliverables" / "rebuild.md"
        rebuild_path.write_text(
            rebuild_path.read_text(encoding="utf-8") + "\nC:\\Users\\alice\\deck\n",
            encoding="utf-8",
        )
        self.assertFalse(all(check.ok for check in verify_outputs.check_rebuild(self.root)))
        qa_checks = verify_outputs.check_qa(self.root, len(self.data["slides"]))
        self.assertFalse(all(check.ok for check in qa_checks))
        self.assertTrue(any("approval" in check.message for check in qa_checks if not check.ok))


if __name__ == "__main__":
    unittest.main()
