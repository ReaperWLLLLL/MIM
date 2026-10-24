"""Contract tests: invalid specs fail before rendering; stale copy cannot be approved."""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_text
import preflight
import validate_deck


@pytest.fixture
def contract(tmp_path):
    (tmp_path / "planning").mkdir()
    (tmp_path / "planning/evidence-map.md").write_text(
        "| ID | Source |\n|---|---|\n| E1 | paper, p. 3 |\n", encoding="utf-8"
    )
    (tmp_path / "source").mkdir()
    (tmp_path / "source/paper.md").write_text("Original paper", encoding="utf-8")
    data = {
        "schema_version": "0.2",
        "project": {"title": "注意力机制", "kind": "research-talk", "language": "zh-CN",
                    "audience": "研究生", "theme": "midnight", "duration_minutes": 1,
                    "aspect_ratio": "16:9", "source_files": ["source/paper.md"]},
        "narrative": {"thesis": "注意力按相关性汇聚信息。", "takeaways": ["权重由输入决定。"]},
        "voice": {"backend": "ssh", "host": "tts-host", "remote_root": "/mnt/data/tts",
                  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "speaker": "Uncle_Fu"},
        "slides": [{"id": "s01", "section": "机制", "title": "按相关性汇聚",
                    "claim": "每个词查询整句话。", "scene_class": "Attention", "notes": "权重和为一。",
                    "purpose": "explain", "duration_seconds": 60, "visual_mode": "manim",
                    "source_refs": ["E1"], "screen_text": {"query": "查询", "example": "计算示例"},
                    "beats": [{"id": "b1", "narration": "查询和键的相似度决定权重。",
                               "action": "FadeIn(query)", "screen_text": ["query", "example"]}]}],
        "outputs": {"video": "deliverables/research-video.mp4", "pptx": "deliverables/presentation.pptx",
                    "speech": "deliverables/speech.md"},
    }
    return data, tmp_path


def api():
    # Missing public contract is an assertion failure, not a collection/import error.
    try:
        return importlib.import_module("research.spec")
    except ModuleNotFoundError:
        pytest.fail("research.spec public contract has not been implemented")


def test_v02_validates_via_existing_cli_boundary(contract):
    data, root = contract
    findings = validate_deck.validate_deck(data, deck_path=root / "planning/deck.yaml", check_paths=True)
    assert not [f for f in findings if f.severity == "error"]


def test_render_defaults_drive_validated_media_settings_without_mutation(contract):
    data, root = contract
    original = copy.deepcopy(data)
    spec = api()
    assert spec.validate_spec(data, root) == []
    assert spec.render_settings(data) == {"width": 1920, "height": 1080, "fps": 60}
    assert data == original


@pytest.mark.parametrize("value", ["../outside.mp4", "/tmp/outside.mp4", "C:\\temp\\outside.mp4", "deliverables/../outside.mp4"])
def test_escaping_output_paths_are_rejected(contract, value):
    data, root = contract
    data["outputs"]["video"] = value
    assert any("outputs.video" in e for e in api().validate_spec(data, root))


def test_symlink_cannot_escape_project(contract, tmp_path):
    data, root = contract
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    data["outputs"]["video"] = "escape/video.mp4"
    assert any("outputs.video" in e for e in api().validate_spec(data, root))


def test_unknown_evidence_is_rejected(contract):
    data, root = contract
    data["slides"][0]["source_refs"] = ["missing"]
    assert any("not declared" in e for e in api().validate_spec(data, root))


def test_screen_text_registry_and_beat_references_are_required(contract):
    data, root = contract
    del data["slides"][0]["screen_text"]
    assert any("screen_text" in e for e in api().validate_spec(data, root))


def test_unknown_screen_text_key_is_rejected(contract):
    data, root = contract
    data["slides"][0]["beats"][0]["screen_text"] = ["not-registered"]
    assert any("not-registered" in e for e in api().validate_spec(data, root))


@pytest.mark.parametrize("field,value", [("fps", 0), ("width", True), ("height", 720.5)])
def test_render_rejects_nonpositive_or_noninteger_dimensions(contract, field, value):
    data, root = contract
    data["render"] = {field: value}
    assert any("render." + field in e for e in api().validate_spec(data, root))


@pytest.mark.parametrize("field,value", [("backend", "local"), ("host", "user@host"), ("remote_root", "../tts"), ("speaker", "")])
def test_voice_requires_ssh_alias_and_remote_configuration(contract, field, value):
    data, root = contract
    data["voice"][field] = value
    assert any("voice." + field in e for e in api().validate_spec(data, root))


@pytest.mark.parametrize("host", ["-oProxyCommand=bad", "tts-host other", "tts-host\nother", "tts-host;other", "tts-host$(other)"])
def test_ssh_host_alias_cannot_be_an_option_or_shell_command(contract, host):
    data, root = contract
    data["voice"]["host"] = host
    assert any("voice.host" in e for e in api().validate_spec(data, root))


@pytest.mark.parametrize("remote_root", ["/", "/home", "/home/alice", "/Users", "/Users/alice", "/root", "/var/root"])
def test_ssh_root_cannot_target_a_broad_home_directory(contract, remote_root):
    data, root = contract
    data["voice"]["remote_root"] = remote_root
    assert any("voice.remote_root" in e for e in api().validate_spec(data, root))


def test_unknown_theme_is_rejected(contract):
    data, root = contract
    data["project"]["theme"] = "invented"
    assert any("project.theme" in e for e in api().validate_spec(data, root))


@pytest.mark.parametrize("theme", [["midnight"], {"name": "midnight"}], ids=["list", "mapping"])
def test_malformed_theme_api_returns_findings(contract, theme):
    data, root = contract
    data["project"]["theme"] = theme
    assert any("project.theme" in e for e in api().validate_spec(data, root))


@pytest.mark.parametrize("theme", [["midnight"], {"name": "midnight"}], ids=["list", "mapping"])
def test_malformed_theme_cli_returns_json_findings(contract, theme, capsys):
    data, root = contract
    data["project"]["theme"] = theme
    deck = root / "planning/deck.json"
    deck.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert validate_deck.main([str(deck), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert any(f["path"] == "project.theme" and f["severity"] == "error" for f in report["findings"])


@pytest.mark.parametrize("text", ["本页将展示我们的核心机制。", "这些数值并不代表真实测量，避免误解。",
                                  "实验结果表明，本方法具有显著优势。", "This slide will show our mechanism."])
def test_internal_defensive_and_report_narration_is_rejected(contract, text):
    data, root = contract
    data["slides"][0]["beats"][0]["narration"] = text
    assert any("narration" in e for e in api().validate_spec(data, root))


def test_scientific_scope_is_not_removed_or_rejected(contract):
    data, root = contract
    data["slides"][0]["beats"][0]["narration"] = "在 WMT14 英德翻译中，BLEU 提高 2.0；该结果仅适用于这一数据集。"
    assert api().validate_spec(data, root) == []


def test_registered_labels_documents_subtitles_and_notes_are_audited(contract):
    data, _ = contract
    data["audience_text"] = {"readme": "README 正文", "report": "报告正文"}
    data["slides"][0]["labels"] = {"axis": "横轴"}
    data["slides"][0]["subtitles"] = ["字幕"]
    texts = api().audience_copy(data)
    assert texts["audience_text.readme"] == "README 正文"
    assert texts["audience_text.report"] == "报告正文"
    assert texts["slides[0].labels.axis"] == "横轴"
    assert texts["slides[0].screen_text.query"] == "查询"
    assert texts["slides[0].subtitles[0]"] == "字幕"
    assert "FadeIn(query)" not in texts.values()
    data["slides"][0]["screen_text"]["query"] = "本页将展示机制"
    data["audience_text"]["report"] = "这充分证明本方法具有显著优势。"
    paths = {f.path for f in audit_text.audit(data) if f.severity == "error"}
    assert "slides[0].screen_text.query" in paths
    assert "audience_text.report" in paths


def test_nested_document_keys_cannot_hide_an_audience_string(contract):
    data, _ = contract
    data["audience_text"] = {"readme.title": "本页将展示机制", "readme": {"title": "文档标题"}}
    texts = api().audience_copy(data)
    assert "本页将展示机制" in texts.values()
    assert "文档标题" in texts.values()
    assert any(f.severity == "error" and f.path.startswith("audience_text") for f in audit_text.audit(data))


def test_copy_hash_is_canonical_and_any_audience_edit_invalidates_approvals(contract):
    data, _ = contract
    spec = api()
    assert spec.content_hash({"b": 2, "a": 1}) == "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    assert spec.content_hash({"a": 1, "b": 2}) == spec.content_hash({"b": 2, "a": 1})
    digest = spec.content_hash(spec.audience_copy(data))
    data["text_review"] = {"content_hash": digest, **{
        skill: {"status": "approved", "content_hash": digest} for skill in ("humanizer", "humanizer-zh")}}
    assert spec.validate_text_review(data) == []
    data["slides"][0]["screen_text"]["query"] = "查询向量"
    assert spec.validate_text_review(data)


def test_plain_approved_does_not_count_as_versioned_review(contract):
    data, _ = contract
    data["text_review"] = {"status": "approved"}
    assert api().validate_text_review(data)


def test_audit_cli_exports_actual_copy_and_current_hash(contract):
    data, root = contract
    deck = root / "planning/deck.json"
    deck.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert audit_text.main([str(deck)]) == 0
    manifest_path = root / "qa/audience-copy.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["copy"]["slides[0].screen_text.example"] == "计算示例"
    assert manifest["content_hash"] == api().content_hash(manifest["copy"])
    assert manifest["content_hash"] in (root / "qa/text-review.md").read_text(encoding="utf-8")


def test_existing_but_broken_executable_is_not_available(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_text("#!/bin/sh\necho 'broken library' >&2\nexit 17\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    check = preflight.command_check("ffmpeg", required=True)
    assert check.ok is False
    assert "17" in check.detail
    assert "broken library" in check.detail


def test_successful_executable_version_is_available(tmp_path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_text("#!/bin/sh\necho 'ffmpeg version test'\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert preflight.command_check("ffmpeg", required=True).ok is True
