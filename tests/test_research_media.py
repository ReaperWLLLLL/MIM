"""Real encoded-media contracts; no fabricated MP4/PPT bytes or remote TTS."""
import copy
import hashlib
import importlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import wave
import xml.etree.ElementTree as ET
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research.spec import audience_copy, content_hash
from research.timeline import build_timeline
from build_research import render_project
from voice_fixture import bind_audio


def api():
    try:
        return importlib.import_module("research.media")
    except ModuleNotFoundError:
        pytest.fail("research.media export and verification are not implemented")


def approve_fixture(spec):
    # Synthetic approval records are ONLY test data, never release approvals.
    digest = content_hash(audience_copy(spec))
    spec["text_review"] = {"content_hash": digest, **{name: {
        "status": "approved", "content_hash": digest} for name in ("humanizer", "humanizer-zh")}}


def test_final_soundtrack_digest_rejects_silent_aac_even_as_its_own_reference(tmp_path):
    silent = tmp_path / "silent.wav"
    with wave.open(str(silent), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(bytes(48000))
    aac = tmp_path / "silent.m4a"
    api()._aac(silent, aac)
    with pytest.raises(ValueError, match="signal|silent"):
        api()._audio_digest(aac)


@pytest.mark.parametrize("change", ["edit", "remove", "symlink"])
def test_effective_theme_file_must_remain_current_before_export(project, change):
    root, out, spec, audio, timeline, old = project
    theme = root / "override.yaml"
    theme.write_text("line_width: 2\n")
    # Explicit custom override is legitimate even though spec declares midnight.
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out,
                   profile="draft", root=root, theme_name="custom", theme_file=theme)
    result = api().export_media(spec, timeline, out, "draft")
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in out.rglob("*") if p.is_file()}
    if change == "edit":
        theme.write_text("line_width: 5\n")
    elif change == "remove":
        theme.unlink()
    else:
        other = root / "other.yaml"
        other.write_bytes(theme.read_bytes())
        theme.unlink()
        theme.symlink_to(other)
    with pytest.raises(ValueError, match="theme"):
        api().export_media(spec, timeline, out, "draft")
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before
    assert any("theme" in f["message"] for f in api().verify_research_outputs(spec, timeline, out))


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_evidence_map_output_collision_is_rejected_before_any_write(project, alias):
    root, out, spec, audio, timeline, old = project
    evidence = root / "planning/evidence-map.md"
    target = evidence if alias == "direct" else root / "evidence-alias.md"
    if alias == "symlink":
        target.symlink_to(evidence)
    elif alias == "hardlink":
        target.hardlink_to(evidence)
    spec["outputs"]["speech"] = str(target.relative_to(root))
    timeline = build_timeline(spec, audio, 15)
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out, profile="draft", root=root)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="protected"):
        publish((root, out, spec, audio, timeline, old))
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before
    assert {p for p in root.rglob("*") if p.is_file()} == set(before)


def test_frozen_publication_rechecks_voice_not_only_rehashed_timeline(project):
    root, out, spec, audio, timeline, old = project
    spec["voice"]["speaker"] = "Ryan"
    timeline["spec_hash"] = content_hash(spec)
    timeline["timeline_hash"] = content_hash({k: v for k, v in timeline.items() if k != "timeline_hash"})
    with pytest.raises(ValueError, match="voice|synthesis"):
        api().validate_frozen(spec, timeline)


def test_frozen_publication_rejects_self_consistent_silent_source(project):
    root, out, spec, audio, timeline, old = project
    cue = timeline["slides"][0]["beats"][0]
    path = Path(cue["path"])
    with wave.open(str(path), "wb") as wav:
        wav.setparams((1, 2, cue["sample_rate"], 0, "NONE", "not compressed"))
        wav.writeframes(bytes(cue["sample_count"] * 2))
    cue["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    timeline["timeline_hash"] = content_hash({k: v for k, v in timeline.items() if k != "timeline_hash"})
    with pytest.raises(ValueError, match="signal|silent"):
        api().validate_frozen(spec, timeline)


@pytest.mark.parametrize("kind", ["explicit", "theme", "staging_alias"])
def test_consumed_input_aliases_are_protected_before_publication(project, kind):
    root, out, spec, audio, timeline, old = project
    consumed = root / "explicit-input.md"
    consumed.write_text("line_width: 2\n")
    extra = {}
    if kind == "staging_alias":
        (out / "export").mkdir()
        (out / "export/narration.wav").symlink_to(consumed)
    else:
        spec["outputs"]["speech"] = "explicit-input.md"
    if kind == "theme":
        extra = {"theme_name": "custom", "theme_file": consumed}
    timeline = build_timeline(spec, audio, 15)
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out,
                   profile="draft", root=root, **extra)
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="protected"):
        api().publish_research_outputs(spec, timeline, audio, out, root, "draft",
                                      input_paths=(consumed,) if kind != "theme" else ())
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before
    assert {p for p in root.rglob("*") if p.is_file()} == set(before)


def wav_record(project, slide, beat, samples=9601):
    path = project / f"{slide['id']}-{beat['id']}.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
        out.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * n / 24000)))
                                 for n in range(samples)))
    return {"slide_id": slide["id"], "beat_id": beat["id"], "path": str(path),
        "sample_count": samples, "sample_rate": 24000,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "narration": beat["narration"], "spoken_text": beat["narration"],
        "text_hash": content_hash(beat["narration"]), "narration_hash": content_hash(beat["narration"])}


@pytest.fixture
def project(tmp_path):
    import yaml
    template = Path(__file__).resolve().parents[1] / "assets/research-template"
    root = tmp_path / "project"
    shutil.copytree(template, root)
    spec = yaml.safe_load((root / "planning/deck.yaml").read_text())
    second = copy.deepcopy(spec["slides"][0])
    second["id"] = "s02"
    second["scene_class"] = "ExampleSecond"
    second["screen_text"]["title"] = "第二页"
    spec["slides"].append(second)
    spec["project"]["duration_minutes"] = .4
    scene_source = root / "src/scenes.py"
    scene_source.write_text(scene_source.read_text().replace('colors = self.theme["colors"]',
        'colors = {**self.theme["colors"], **self.slide_spec.get("presentation", {})}')
        + "\nclass ExampleSecond(Example):\n    pass\n")
    approve_fixture(spec)
    audio = {"job_id": "fixture", "settings": {}, "audio": [
        wav_record(root, slide, beat) for slide in spec["slides"] for beat in slide["beats"]]}
    bind_audio(spec, audio)
    timeline = build_timeline(spec, audio, 15)
    out = root / "rendered"
    manifest = render_project(spec, audio, timeline, source=root / "src/scenes.py",
                              out=out, profile="draft", root=root)
    return root, out, spec, audio, timeline, manifest


def test_real_export_preserves_visual_frames_and_silent_ppt_with_canonical_notes(project):
    root, out, spec, audio, timeline, render = project
    result = api().export_media(spec, timeline, out, "draft")
    assert result["ok"] is True
    assert [(s["start_frame"], s["end_frame"]) for s in result["slides"]] == [(0, 14), (14, 28)]
    assert result["audio"]["sample_count"] == 44800
    assert result["audio"]["codec_priming_samples"] == 1024
    assert result["audio"]["codec_tail_samples"] == 256
    with wave.open(result["audio"]["path"], "rb") as wav:
        data = wav.readframes(wav.getnframes())
    assert data[9601 * 2:11200 * 2] == bytes((11200 - 9601) * 2)
    assert data[11200 * 2:11201 * 2] == b"\0\0"  # second sine begins at exact cue boundary
    assert any(data[11201 * 2:11220 * 2])
    assert api().verify_research_outputs(spec, timeline, out) == []
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", result["mp4"]]))
    assert [s["codec_type"] for s in probe["streams"]] == ["video", "audio"]
    assert int(probe["streams"][0]["nb_frames"]) == 28
    assert result["slides"][0]["notes"] == "\n".join(b["narration"] for b in spec["slides"][0]["beats"])
    assert all(s["poster_local_frame"] < 14 for s in result["slides"])


@pytest.mark.parametrize("fault", ["corrupt", "audible_ppt", "extra_audio", "missing_scene", "missing_size", "old_review", "notes", "poster", "wrong_visual"])
def test_verifier_rejects_real_output_corruption_and_stale_approval(project, fault):
    root, out, spec, audio, timeline, render = project
    result = api().export_media(spec, timeline, out, "draft")
    if fault == "corrupt":
        Path(result["mp4"]).write_bytes(b"corrupt")
    elif fault == "old_review":
        spec["text_review"]["humanizer-zh"]["content_hash"] = "0" * 64
    else:
        ppt = Path(result["pptx"])
        with zipfile.ZipFile(ppt) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        videos = [name for name in members if name.startswith("ppt/media/") and name.endswith(".mp4")]
        if fault == "audible_ppt":
            members[videos[0]] = Path(result["mp4"]).read_bytes()
        elif fault == "extra_audio":
            members["ppt/media/stray-narration.wav"] = Path(audio["audio"][0]["path"]).read_bytes()
        elif fault == "wrong_visual":
            members[videos[0]] = members[videos[1]]
        elif fault == "missing_scene":
            del members["ppt/slides/slide2.xml"]
        elif fault == "missing_size":
            xml = ET.fromstring(members["ppt/presentation.xml"])
            xml.remove(xml.find("{http://schemas.openxmlformats.org/presentationml/2006/main}sldSz"))
            members["ppt/presentation.xml"] = ET.tostring(xml)
        elif fault == "notes":
            members["ppt/notesSlides/notesSlide1.xml"] = members["ppt/notesSlides/notesSlide1.xml"].replace("输入".encode(), "错误".encode())
        else:
            key = "ppt/media/manim-poster-1.png"
            members[key] = members["ppt/media/manim-poster-2.png"]
        with zipfile.ZipFile(ppt, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
    findings = api().verify_research_outputs(spec, timeline, out)
    assert findings, fault
    assert all(f["code"] and f["message"] for f in findings)


def test_export_rejects_missing_scene_and_stale_review_before_publishing(project):
    root, out, spec, audio, timeline, render = project
    spec["text_review"]["humanizer"]["status"] = "pending"
    with pytest.raises(ValueError, match="humanizer"):
        api().export_media(spec, timeline, out, "draft")
    approve_fixture(spec)
    render["slides"].pop()
    (out / "render-manifest.json").write_text(json.dumps(render))
    with pytest.raises(ValueError, match="slide|scene"):
        api().export_media(spec, timeline, out, "draft")


def test_partial_render_reuses_unchanged_master_and_retains_original_frame_evidence(project):
    root, out, spec, audio, timeline, old = project
    unchanged = old["slides"][1]
    before = {key: (Path(unchanged[key]).read_bytes(), Path(unchanged[key]).stat().st_mtime_ns)
              for key in ("master", "trace", "qa", "slides_json")}
    spec["slides"][0]["beats"][0]["narration"] += "这是一处局部修改。"
    approve_fixture(spec)
    audio["audio"][0] = wav_record(root, spec["slides"][0], spec["slides"][0]["beats"][0], samples=14401)
    bind_audio(spec, audio)
    relocated = root / "relocated"
    relocated.mkdir()
    for item in audio["audio"][1:]:
        target = relocated / Path(item["path"]).name
        shutil.copyfile(item["path"], target)
        item["path"] = str(target)
    changed = build_timeline(spec, audio, 15)
    new = render_project(spec, audio, changed, source=root / "src/scenes.py",
                         out=out, profile="draft", root=root, slides=["s01"])
    assert new["slides"][0]["reused"] is False
    reused = new["slides"][1]
    assert reused["reused"] is True
    assert (reused["start_frame"], reused["end_frame"]) == (17, 31)
    for key, (payload, mtime) in before.items():
        assert Path(reused[key]).read_bytes() == payload
        assert Path(reused[key]).stat().st_mtime_ns == mtime
    mapping = [json.loads(line) for line in Path(reused["frame_mapping"]).read_text().splitlines()]
    assert [r["frame"] for r in mapping] == list(range(17, 31))
    assert [r["observed_frame"] for r in mapping] == list(range(14, 28))
    assert [r["local_frame"] for r in mapping] == list(range(14))
    result = api().export_media(spec, changed, out, "draft")
    assert result["slides"][1]["start_frame"] == 17
    assert api().verify_research_outputs(spec, changed, out) == []
    Path(reused["frame_mapping"]).write_text("{}\n")
    assert api().verify_research_outputs(spec, changed, out), "derived offset evidence must be validated"


@pytest.mark.parametrize("fault", ["master", "trace", "qa", "missing", "source", "local_spec"])
def test_partial_render_fails_before_work_when_unselected_dependencies_or_evidence_are_stale(project, fault):
    root, out, spec, audio, timeline, old = project
    unaffected = old["slides"][1]
    if fault in {"master", "trace", "qa"}:
        path = Path(unaffected[fault])
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "missing":
        Path(unaffected["trace"]).unlink()
    elif fault == "source":
        source = root / "src/scenes.py"
        source.write_text(source.read_text() + "\n# changed common source\n")
    else:
        spec["slides"][1]["screen_text"]["title"] = "未选页的新文本"
        approve_fixture(spec)
        timeline = build_timeline(spec, audio, 15)
    original = Path(old["slides"][0]["master"]).stat().st_mtime_ns
    with pytest.raises(ValueError, match="reuse|stale|sha256|missing"):
        render_project(spec, audio, timeline, source=root / "src/scenes.py",
                       out=out, profile="draft", root=root, slides=["s01"])
    assert Path(old["slides"][0]["master"]).stat().st_mtime_ns == original


def test_cli_exports_and_verifies_in_explicit_render_directory(project):
    root, out, spec, audio, timeline, old = project
    specfile, timefile = root / "spec.json", root / "timeline.json"
    specfile.write_text(json.dumps(spec))
    timefile.write_text(json.dumps(timeline))
    audiofile = root / "audio.json"
    audiofile.write_text(json.dumps(audio))
    cli = Path(__file__).resolve().parents[1] / "scripts/build_research.py"
    for operation in ("export", "verify"):
        result = subprocess.run([sys.executable, str(cli), operation, "--spec", str(specfile),
            "--timeline", str(timefile), "--audio", str(audiofile), "--out", str(out), "--profile", "draft"], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "export/silent-slides.pptx").is_file()
    assert all((root / spec["outputs"][name]).is_file() for name in ("video", "pptx", "speech"))
    result = subprocess.run([sys.executable, str(cli), "render", "--spec", str(specfile),
        "--timeline", str(timefile), "--out", str(out), "--profile", "draft", "--audio", str(audiofile),
        "--source", str(root / "src/scenes.py"), "--slides", "s01"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((out / "render-manifest.json").read_text())["slides"][1]["reused"] is True


def test_local_presentation_change_only_rerenders_selected_visual(project):
    root, out, spec, audio, timeline, old = project
    first_hashes = api().frame_hashes(old["slides"][0]["master"])
    spec["slides"][0]["presentation"] = {"accent": "#FF4466"}
    changed = build_timeline(spec, audio, 15)
    new = render_project(spec, audio, changed, source=root / "src/scenes.py", out=out,
                         profile="draft", root=root, slides=["s01"])
    assert api().frame_hashes(new["slides"][0]["master"]) != first_hashes
    assert new["slides"][1]["master_sha256"] == old["slides"][1]["master_sha256"]
    assert new["slides"][1]["reused"] is True


def test_blank_terminal_frames_use_earlier_stable_content_poster(project):
    root, out, spec, audio, timeline, old = project
    source = root / "src/scenes.py"
    source.write_text(source.read_text() + '\nclass BlankEnd(ResearchScene):\n'
        '    def construct(self):\n'
        '        self.add(self.text("title", role="title"))\n'
        '        self.beat("observe", [], 0)\n'
        '        self.clear()\n'
        '        self.beat("compare", [], 0)\n')
    spec["slides"][0]["scene_class"] = "BlankEnd"
    timeline = build_timeline(spec, audio, 15)
    render_project(spec, audio, timeline, source=source, out=out, profile="draft", root=root)
    result = api().export_media(spec, timeline, out, "draft")
    assert result["slides"][0]["poster_local_frame"] == 6
    assert api().verify_research_outputs(spec, timeline, out) == []


def test_final_export_keeps_default_1080p60_profile_with_real_media(project):
    root, out, spec, audio, timeline, old = project
    timeline = build_timeline(spec, audio, 60)
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out, profile="final", root=root)
    result = api().export_media(spec, timeline, out, "final")
    video = next(s for s in api().probe(result["mp4"])["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["avg_frame_rate"], int(video["nb_read_frames"])) == (1920, 1080, "60/1", 100)


def test_verifier_detects_audio_cut_without_cutting_visuals(project):
    root, out, spec, audio, timeline, old = project
    result = api().export_media(spec, timeline, out, "draft")
    truncated = out / "truncated.m4a"
    api().ffmpeg("-i", result["audio"]["aac"], "-t", .5, "-c", "copy", truncated)
    replacement = out / "truncated-narration.mp4"
    api().ffmpeg("-i", result["visual"], "-i", truncated, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", replacement)
    shutil.copyfile(replacement, result["mp4"])
    findings = api().verify_research_outputs(spec, timeline, out)
    assert findings and "AAC" in findings[0]["message"]


def test_export_rejects_source_changed_since_render(project):
    root, out, spec, audio, timeline, old = project
    source = root / "src/scenes.py"
    source.write_text(source.read_text() + "\n# newer scene implementation\n")
    with pytest.raises(ValueError, match="source|depend"):
        api().export_media(spec, timeline, out, "draft")


def test_verifier_checks_movie_playback_relationship_not_only_inventory(project):
    root, out, spec, audio, timeline, old = project
    result = api().export_media(spec, timeline, out, "draft")
    with zipfile.ZipFile(result["pptx"]) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    key = "ppt/slides/slide1.xml"
    xml = ET.fromstring(members[key])
    video = xml.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}videoFile")
    video.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}link", "rId999")
    members[key] = ET.tostring(xml)
    with zipfile.ZipFile(result["pptx"], "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    assert api().verify_research_outputs(spec, timeline, out)


@pytest.mark.parametrize("missing", ["cNvPr", "blip"])
def test_public_verifier_reports_missing_real_ppt_picture_nodes(project, missing):
    root, out, spec, audio, timeline, old = project
    result = api().export_media(spec, timeline, out, "draft")
    with zipfile.ZipFile(result["pptx"]) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    key = "ppt/slides/slide1.xml"
    xml = ET.fromstring(members[key])
    picture = xml.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pic")
    for parent in picture.iter():
        for node in list(parent):
            if node.tag.endswith("}" + missing):
                parent.remove(node)
    members[key] = ET.tostring(xml)
    with zipfile.ZipFile(result["pptx"], "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    findings = api().verify_research_outputs(spec, timeline, out)
    assert findings and findings[0]["code"] == "research_output_invalid"
    assert missing in findings[0]["message"]


@pytest.mark.parametrize("destination", ["rendered/export/slide-0001.mp4", "rendered/export/visual.mp4",
                                         "rendered/export/narrated.mp4"])
def test_publication_reserves_staging_inputs_before_mutation(project, destination):
    root, out, spec, audio, timeline, old = project
    spec["outputs"]["video"] = destination
    timeline = build_timeline(spec, audio, 15)
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out, profile="draft", root=root)
    result = api().export_media(spec, timeline, out, "draft")
    if destination.endswith("narrated.mp4"):
        # An apparent final-slot identity must not alias an internal clip.
        Path(result["mp4"]).unlink()
        Path(result["mp4"]).symlink_to(result["slides"][0]["clip"])
    protected = [out / "export-manifest.json", out / "render-manifest.json", Path(result["visual"]),
        *[Path(s["clip"]) for s in result["slides"]], *[Path(s["master"]) for s in old["slides"]]]
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in protected}
    with pytest.raises(ValueError, match="staging|protected"):
        publish((root, out, spec, audio, timeline, old))
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in protected} == before


def test_publication_allows_its_final_staged_output_identity(project):
    root, out, spec, audio, timeline, old = project
    spec["outputs"].update(video="rendered/export/narrated.mp4", pptx="rendered/export/silent-slides.pptx")
    timeline = build_timeline(spec, audio, 15)
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out, profile="draft", root=root)
    result = publish((root, out, spec, audio, timeline, old))
    assert result["ok"] is True
    assert api().verify_research_outputs(spec, timeline, out) == []


def publish(project):
    root, out, spec, audio, timeline, old = project
    operation = getattr(api(), "publish_research_outputs", None)
    assert operation is not None, "declared deliverable publication is not implemented"
    return operation(spec, timeline, audio, out, root, "draft")


def test_publication_uses_declared_paths_and_real_spoken_text_and_sample_timing(project):
    root, out, spec, audio, timeline, old = project
    spec["outputs"] = {"video": "chosen/movie.mp4", "pptx": "chosen/deck.pptx", "speech": "chosen/script.md"}
    spec["voice"]["pronunciation"] = {"测量": "测亮"}
    audio["settings"]["pronunciation"] = {"测量": "测亮"}
    for cue in audio["audio"]:
        cue["spoken_text"] = cue["narration"].replace("测量", "测亮")
        cue["text_hash"] = content_hash(cue["spoken_text"])
    bind_audio(spec, audio)
    timeline = build_timeline(spec, audio, 15)
    render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out, profile="draft", root=root)
    result = publish((root, out, spec, audio, timeline, old))
    assert result["mp4"] == str(root / spec["outputs"]["video"])
    assert result["pptx"] == str(root / spec["outputs"]["pptx"])
    speech = (root / spec["outputs"]["speech"]).read_text()
    canonical = spec["slides"][0]["beats"][0]["narration"]
    spoken = audio["audio"][0]["spoken_text"]
    assert canonical != spoken
    assert canonical in speech
    assert spoken in speech
    assert f"合成输入文本：\n\n{spoken}" in speech
    assert "9601/24000" in speech and "0.400042" in speech and "0.466667" in speech
    assert "1.866667" in speech and "[14,28)" in speech
    assert all(beat["action"] not in speech for slide in spec["slides"] for beat in slide["beats"])
    assert all(slide["notes"] not in speech for slide in spec["slides"])
    # Final verification must not silently depend on or substitute staging main outputs.
    (out / "export/narrated.mp4").unlink()
    (out / "export/silent-slides.pptx").unlink()
    assert api().verify_research_outputs(spec, timeline, out) == []


@pytest.mark.parametrize("fault", ["video", "pptx", "speech", "snapshot", "redirect"])
def test_final_verifier_rejects_declared_delivery_damage_even_with_good_staging(project, fault):
    root, out, spec, audio, timeline, old = project
    result = publish(project)
    if fault in {"video", "pptx", "speech"}:
        target = root / spec["outputs"][fault]
        if fault == "speech":
            target.write_text(target.read_text() + "未经批准的额外讲稿。\n")
        else:
            target.write_bytes(b"broken actual delivery")
    else:
        manifest = json.loads((out / "export-manifest.json").read_text())
        if fault == "snapshot":
            manifest["delivery"]["audio_manifest"]["audio"][0]["spoken_text"] = "错误发音"
        else:
            manifest["mp4"] = str(out / "export/narrated.mp4")
        (out / "export-manifest.json").write_text(json.dumps(manifest))
    assert (out / "export/narrated.mp4").is_file()
    assert api().verify_research_outputs(spec, timeline, out)


def test_publication_rejects_stale_audio_manifest_before_writing_declared_files(project):
    root, out, spec, audio, timeline, old = project
    audio["audio"][0]["spoken_text"] = "与真实时间轴不符"
    operation = getattr(api(), "publish_research_outputs", None)
    assert operation is not None, "declared deliverable publication is not implemented"
    with pytest.raises(ValueError, match="audio|text_hash|timeline"):
        operation(spec, timeline, audio, out, root, "draft")
    assert not (root / spec["outputs"]["video"]).exists()


def test_publication_rejects_escaping_declared_output_before_writes(project):
    root, out, spec, audio, timeline, old = project
    spec["outputs"]["video"] = "../escape.mp4"
    operation = getattr(api(), "publish_research_outputs", None)
    assert operation is not None, "declared deliverable publication is not implemented"
    with pytest.raises(ValueError, match="outputs|relative|escape"):
        operation(spec, timeline, audio, out, root, "draft")
    assert not (root.parent / "escape.mp4").exists()


def test_partial_reorder_fails_before_indexed_output_directories_can_collide(project):
    root, out, spec, audio, timeline, old = project
    before = {s["slide_id"]: (Path(s["master"]).read_bytes(), Path(s["master"]).stat().st_mtime_ns)
              for s in old["slides"]}
    spec["slides"].reverse()
    approve_fixture(spec)
    audio["audio"] = [cue for slide in spec["slides"] for cue in audio["audio"] if cue["slide_id"] == slide["id"]]
    bind_audio(spec, audio)
    timeline = build_timeline(spec, audio, 15)
    with pytest.raises(ValueError, match="reuse|stale|full render"):
        render_project(spec, audio, timeline, source=root / "src/scenes.py", out=out,
                       profile="draft", root=root, slides=["s01"])
    for slide in old["slides"]:
        assert (Path(slide["master"]).read_bytes(), Path(slide["master"]).stat().st_mtime_ns) == before[slide["slide_id"]]
