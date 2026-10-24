"""Renderer-independent theme values; no font installation or rendering claims.

load_theme(name, overrides=None) returns a fresh JSON-serializable mapping.
Names: midnight, paper, slate, custom. Custom starts from midnight and requires
a nonempty structured override. Overrides can replace colors by key; font_sizes
must replace the entire title/body/caption group. Unknown fields are rejected.
All text-bearing colors must have >=4.5:1 WCAG sRGB contrast with background.
Fixed role floors (36/24/18) are project readability policy, not font metrics.
No fitting/shrinking option exists: rewrite, wrap, or split a scene instead.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re


_PALETTES = {
    "midnight": {"background": "#0B1220", "foreground": "#F8FAFC", "primary": "#67E8F9",
                 "secondary": "#A5B4FC", "accent": "#FDE68A"},
    "paper": {"background": "#FAF7F0", "foreground": "#202733", "primary": "#1D4ED8",
              "secondary": "#475569", "accent": "#9A3412"},
    "slate": {"background": "#272B30", "foreground": "#FAF3E8", "primary": "#FDBA74",
              "secondary": "#CBD5E1", "accent": "#A7F3D0"},
}
_ROLES = {"title": 48, "body": 30, "caption": 20}


def _number(value: object) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def validate_font_sizes(value: object) -> dict:
    """Validate a complete fixed role group; return a fresh mapping or ValueError."""
    if not isinstance(value, dict) or set(value) != set(_ROLES):
        raise ValueError("font_sizes: requires exactly title, body, caption")
    floors = {"title": 36, "body": 24, "caption": 18}
    if any(not _number(value[k]) or value[k] < floors[k] for k in floors):
        raise ValueError("font_sizes: finite title/body/caption must be at least 36/24/18")
    if not value["title"] > value["body"] > value["caption"]:
        raise ValueError("font_sizes: must have title > body > caption")
    return dict(value)


def _luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(v * w for v, w in zip(channels, (.2126, .7152, .0722)))


def load_theme(name: str, overrides: dict | None = None) -> dict:
    """Load validated preset/custom values; raise field-specific ValueError.

    Schema: name, colors={background,foreground,primary,secondary,accent},
    font_family, font_sizes={title,body,caption}, line_width, spacing.
    Only the latter five fields are accepted as overrides. Sizes use Manim font
    units; spacing uses scene units; line_width uses Manim stroke-width units.
    """
    if not isinstance(name, str) or name not in {*_PALETTES, "custom"}:
        raise ValueError("name: must be midnight, paper, slate or custom")
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("overrides: must be a mapping")
    if name == "custom" and not overrides:
        raise ValueError("overrides: custom theme requires a nonempty mapping")
    theme = {"name": name, "colors": deepcopy(_PALETTES["midnight" if name == "custom" else name]),
             "font_family": "Microsoft YaHei", "font_sizes": dict(_ROLES),
             "line_width": 2, "spacing": .25}
    for key, value in (overrides or {}).items():
        if key not in theme or key == "name":
            raise ValueError(f"overrides.{key}: unknown theme field")
        if key == "colors":
            if not isinstance(value, dict):
                raise ValueError("colors: must be a mapping")
            for color, code in value.items():
                if color not in theme["colors"]:
                    raise ValueError(f"colors.{color}: unknown color field")
                theme["colors"][color] = code
        else:
            theme[key] = deepcopy(value)
    theme["font_sizes"] = validate_font_sizes(theme["font_sizes"])
    for key in ("line_width", "spacing"):
        if not _number(theme[key]) or theme[key] <= 0:
            raise ValueError(f"{key}: must be a finite positive number")
    if not isinstance(theme["font_family"], str) or not theme["font_family"].strip():
        raise ValueError("font_family: must be a nonempty string")
    for color, code in theme["colors"].items():
        if not isinstance(code, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", code):
            raise ValueError(f"colors.{color}: requires #RRGGBB")
    background = _luminance(theme["colors"]["background"])
    for color, code in theme["colors"].items():
        if color == "background":
            continue
        level = _luminance(code)
        ratio = (max(background, level) + .05) / (min(background, level) + .05)
        if ratio < 4.5:
            raise ValueError(f"colors.{color}: contrast {ratio:.2f}:1 is below 4.5:1 against background")
    return theme
