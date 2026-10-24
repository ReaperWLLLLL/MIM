"""Three native-Manim art directions. No renderer or font assets bundled."""
from copy import deepcopy

STYLES = {
    "midnight": {
        "label": "深色几何", "background": "#101724", "foreground": "#EDF3FA",
        "primary": "#66E0C2", "secondary": "#B8AEFF", "accent": "#F1D38A",
        "muted": "#AAB6C8", "rule": "#29364A", "layout": "centered",
        "line_width": 3.0, "title_size": 38, "body_size": 25, "math_size": 34,
    },
    "daylight": {
        "label": "浅色学术", "background": "#F8FAFC", "foreground": "#192B42",
        "primary": "#006C70", "secondary": "#6942A0", "accent": "#A64418",
        "muted": "#506278", "rule": "#CDD7E2", "layout": "columns",
        "line_width": 2.4, "title_size": 36, "body_size": 25, "math_size": 34,
    },
    "notebook": {
        "label": "暖纸手稿", "background": "#F6EEDD", "foreground": "#352E29",
        "primary": "#216A55", "secondary": "#7851A0", "accent": "#A33E27",
        "muted": "#6B5C4D", "rule": "#DED3BE", "layout": "notebook",
        "line_width": 3.4, "title_size": 36, "body_size": 25, "math_size": 34,
    },
}


def load_style(name="midnight"):
    """Return an independent style mapping; unknown names are errors."""
    if name not in STYLES:
        raise ValueError(f"Unknown native style {name!r}; choose {', '.join(STYLES)}")
    return deepcopy(STYLES[name])
