"""Theme validation rejects unreadable or unstructured scene settings."""
import copy
import importlib
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def load(name, overrides=None):
    try:
        module = importlib.import_module("research.themes")
    except ModuleNotFoundError:
        pytest.fail("research.themes.load_theme is not implemented")
    return module.load_theme(name, overrides)


@pytest.mark.parametrize("name", ["midnight", "paper", "slate"])
def test_presets_supply_three_readable_fixed_font_roles(name):
    theme = load(name)
    assert theme["name"] == name
    assert theme["font_sizes"] == {"title": 48, "body": 30, "caption": 20}
    assert set(theme["colors"]) == {"background", "foreground", "primary", "secondary", "accent"}
    assert theme["font_family"] == "Microsoft YaHei"
    assert theme["line_width"] > 0 and theme["spacing"] > 0
    assert theme["colors"]["foreground"] != theme["colors"]["background"]


def test_custom_nested_overrides_do_not_mutate_inputs_or_future_loads():
    overrides = {"colors": {"accent": "#FFFFFF"},
                 "font_sizes": {"title": 50, "body": 32, "caption": 22}}
    before = copy.deepcopy(overrides)
    theme = load("custom", overrides)
    assert theme["colors"]["accent"] == "#FFFFFF"
    assert theme["font_sizes"] == {"title": 50, "body": 32, "caption": 22}
    theme["colors"]["background"] = "#FFFFFF"
    assert load("midnight")["colors"]["background"] != "#FFFFFF"
    assert overrides == before


@pytest.mark.parametrize("name,overrides,field", [
    ("unknown", None, "name"),
    ([], None, "name"),
    ("custom", None, "overrides"),
    ("custom", [], "overrides"),
    ("custom", {"auto_shrink": True}, "auto_shrink"),
    ("custom", {"colors": {"background": "red"}}, "background"),
    ("custom", {"colors": {"foreground": "#112233", "background": "#112234"}}, "contrast"),
    ("custom", {"colors": {"accent": "#000000"}}, "contrast"),
    ("custom", {"colors": {"bogus": "#FFFFFF"}}, "bogus"),
    ("custom", {"font_sizes": {"title": 48}}, "font_sizes"),
    ("custom", {"font_sizes": {"title": 48, "body": 30, "caption": 20, "small": 12}}, "font_sizes"),
    ("custom", {"font_sizes": {"title": 48, "body": 12, "caption": 10}}, "font_sizes"),
    ("custom", {"font_sizes": {"title": 48, "body": 50, "caption": 20}}, "font_sizes"),
    ("custom", {"font_sizes": {"title": 48, "body": float("nan"), "caption": 20}}, "font_sizes"),
    ("custom", {"spacing": -1}, "spacing"),
    ("custom", {"line_width": True}, "line_width"),
    ("custom", {"font_family": ""}, "font_family"),
    ("custom", {"line_width": 10**999}, "line_width"),
])
def test_bad_theme_settings_fail_with_actionable_field(name, overrides, field):
    with pytest.raises(ValueError, match=field):
        load(name, overrides)


def test_srgb_contrast_threshold_rejects_barely_unreadable_colors():
    colors = {"background": "#FFFFFF", "foreground": "#767676", "primary": "#767676",
              "secondary": "#767676", "accent": "#767676"}
    assert load("custom", {"colors": colors})["colors"]["foreground"] == "#767676"
    colors["foreground"] = "#777777"
    with pytest.raises(ValueError, match="contrast"):
        load("custom", {"colors": colors})
