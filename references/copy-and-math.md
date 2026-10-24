# Audience explanation and inline mathematics

Use for titles, labels, captions, subtitles and narration, including native drafts. Decide what belongs in the explanation before polishing its voice.

## Separate the writing layers

| Layer | Purpose and content |
| --- | --- |
| Screen | What the audience is observing, the operation being performed and the relationship it explains |
| Speaker notes / optional narration | The spoken reasoning, with useful assumptions and examples |
| Evidence / production notes | Source corrections, applicability inventory, implementation choices and verification status |

Introduce the working model once, in the section where it matters. Attach an assumption directly to a claim if omitting it would change its meaning. Discuss a counterexample when it is the learning objective. Other source-audit and production qualifications stay in notes rather than becoming a running defensive commentary.

Write the positive, local explanation first: “在这张电阻网中，…” followed by what happens and why. Avoid appending unrelated replies to imagined objections. Humanizer editing comes after this content-placement pass; making a disclaimer sound smoother does not make it useful teaching copy.

Examples:

| Working draft | Screen explanation | Notes |
| --- | --- | --- |
| 本例有接地且为电阻网，Y可逆；交流网还要排除谐振等退化 | 接地固定了参考电位，这个电阻网的节点电压有唯一解 | The current model is a connected positive-conductance network; AC resonance conditions belong to the applicable later topic |
| 分流先看电压差，不能在任意网络中只按相邻导纳比例分配 | 先求两端电压差，再乘这条支路的导纳 | Keep the source's overgeneralized current-divider claim in evidence notes |
| 不是声称Z的其余项为零 | 高亮的是本次回代要计算的位置 | Distinguish selected entries from the full inverse where that distinction is taught |

Edit for natural technical Chinese with installed `humanizer`, then `humanizer-zh`. Preserve necessary conditions and meaningful contrasts, not every defensive sentence. Re-read the line while looking at the action it accompanies.

## Give mathematical meaning a mathematical representation

`Text` renders characters; it does not parse TeX, Markdown mathematics or programming notation. A formula inside a sentence is still a formula. Compose ordinary prose objects with `MathTex` objects in the same line, or use a TeX/CJK setup that has actually been verified in the target environment. Do not silently replace subscripts/superscripts with flat identifiers to avoid layout work.

| Meaning | Mathematical object |
| --- | --- |
| Tree-column submatrix | `MathTex(r"A_T")` |
| Transpose of A | `MathTex(r"A^T")` |
| Node subblock | `MathTex(r"Y_{nn}")` |
| Reciprocal diagonal element | `MathTex(r"\frac{1}{d_i}")` |
| Matrix inverse | `MathTex(r"Y^{-1}")` |

Confirm notation from the source before choosing the glyphs: the subscript T in a tree block is not a transpose. Keep the same symbol conventions across diagrams, inline copy and standalone equations. Internal IDs and code may retain ASCII names; exported visible prose uses their intended mathematical notation.

For native Manim, a short line can be composed directly:

```python
line = VGroup(
    Text("树支列组成", font="Microsoft YaHei", font_size=27),
    MathTex(r"A_T", font_size=32),
    Text("，连支列组成", font="Microsoft YaHei", font_size=27),
    MathTex(r"A_L", font_size=32),
).arrange(RIGHT, buff=0.08)
```

Inspect the actual line for optical alignment, spacing, fraction height and readable size. Split long sentences at semantic boundaries; keep each mathematical expression intact. If an existing caption helper accepts only strings and converts all of them to `Text`, adapt or bypass that helper for mixed text instead of flattening the formula. The runnable [mixed-caption example](../assets/native-example/mixed_math.py) shows subscripts, transpose and inverse inline with Chinese.

In strict v0.2 projects retain text registration and font-role contracts: compose through registered prose/math objects and record the visible formula's source expression. The native example is not a way to bypass strict registration.
