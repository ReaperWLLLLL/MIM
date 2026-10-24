# Visual styles for native Manim

Use when discussing art direction or starting a native scene. Offer these three
directions when the user has no established style. Record the chosen name in the
brief; an explicit delegation permits choosing with a short reason. Preserve an
existing project's agreed style. The presets guide composition; layouts should
still follow the explanation.

| Preset | Composition and motion | Suitable use |
| --- | --- | --- |
| `midnight` / 深色几何 | Dark blue field, centered objects, generous empty space; mint and violet distinguish roles, gold marks the active operation. Move or transform matching objects, then hold. | Geometry, mechanisms, focused video viewing |
| `daylight` / 浅色学术 | Cool white field, left-aligned heading and thin rules; diagram and derivation can share two columns. Reveal aligned equations in reading order. Teal and purple preserve object roles. | Research presentations, conference projection, light-background slides |
| `notebook` / 暖纸手稿 | Warm paper field, ink-like strokes, optional faint ruled guides, margin annotations and curved pointers. Write a relation, connect it to the diagram, carry it into the next line. | Method walkthroughs, derivations and reasoning in progress |

Do not add paper texture images, shaky formulas or decorative dashboards by
default. Notebook uses precise typeset mathematics and vector rules. All three
use real `MathTex`, semantic colors and a locally licensed Chinese font. A style
does not determine example size or scientific depth. Distinguish meaning with
labels/positions as well as color.

## Reusable values and rendered examples

[styles.py](../assets/native-example/styles.py) contains independent mappings for
background, foreground, semantic colors, line width, font sizes and layout.
Copy it beside project scenes and call `load_style("daylight")`, or adapt it
while retaining the chosen direction. This is a native-scene helper, not a
global theme switch for every legacy exporter.

[style_showcase.py](../assets/native-example/style_showcase.py) renders the same
original branch-to-matrix explanation in all three directions. From the skill
repository with a prepared Manim environment:

```bash
python -m manim -ql --disable_caching --media_dir build/style-demo \
  assets/native-example/style_showcase.py Midnight Daylight Notebook
```

Chinese defaults to Microsoft YaHei. If discovery misses a licensed local font,
set `MANIM_CHINESE_FONT_FILE` to its path. For a different installed family also
set `MANIM_CHINESE_FONT`; no fonts are distributed. The demo fails clearly when
the requested family is unavailable. Render dense states in the chosen style,
check labels and mathematical signs, and review the actual animation.

The older strict v0.2 presets (`midnight`, `paper`, `slate`, `custom`) in
`scripts/research/themes.py` remain compatible. Their names are separate from
this native preset set; do not silently reinterpret an existing project's theme.
