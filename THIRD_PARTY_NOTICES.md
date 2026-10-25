# Third-party notices

`mim` is original orchestration, validation, QA, and export code built
on separately licensed open-source tools. Their source code and binaries are not
vendored in this repository. Installing or bundling dependencies does not place them
under this repository's MIT license.

## Runtime and development dependencies

| Project | Use | License and copyright | Upstream |
|---|---|---|---|
| Manim Community Edition | Animation and rendering | MIT; Copyright (c) 2018 3Blue1Brown LLC and Copyright (c) 2024 Manim Community Developers | https://github.com/ManimCommunity/manim |
| Manim Slides | Slide manifests and PPTX/PDF conversion | MIT; Copyright (c) 2022-2024 Jérome Eertmans | https://github.com/jeertmans/manim-slides |
| PyYAML | `deck.yaml` parsing | MIT; Copyright (c) 2006-2021 Kirill Simonov, Ingy döt Net, and contributors | https://github.com/yaml/pyyaml |
| Pillow | Image inspection and contact sheets | MIT-CMU; Copyright (c) Secret Labs AB, Fredrik Lundh, Jeffrey A. Clark, and contributors | https://github.com/python-pillow/Pillow |
| pypdf | PDF text/image extraction and structural verification | BSD-3-Clause; Copyright (c) Mathieu Fenniak and contributors | https://github.com/py-pdf/pypdf |
| python-pptx | PowerPoint support used by Manim Slides | MIT; Copyright (c) 2013 Steve Canny | https://github.com/scanny/python-pptx |
| pytest | Development tests | MIT; Copyright (c) 2004 Holger Krekel and others | https://github.com/pytest-dev/pytest |
| PyAV (`av==18.0.0` tested) | Direct encoded-packet stream copy in audited silent-MP4 concatenation; also used by Manim | BSD-3-Clause; copyright retained by original committers | [Official v18.0.0 license](https://raw.githubusercontent.com/PyAV-Org/PyAV/v18.0.0/LICENSE.txt) |
| Pycairo (`pycairo==1.29.0` tested) | Direct per-frame Cairo context and stroke-extents observations for painted geometry; installed as a Manim dependency | `LGPL-2.1-only OR MPL-1.1`; see individual upstream files for copyright and licensing | [Official v1.29.0 COPYING](https://github.com/pygobject/pycairo/blob/v1.29.0/COPYING) |
| FFmpeg | External video/frame command-line tools | Build-dependent LGPL/GPL, including version-3 configurations; see below | https://ffmpeg.org/legal.html |

The tested PyAV version is an observed runtime version, not a claim that every
version allowed by the dependency ranges has been tested. PyAV's BSD-3-Clause
code license is distinct from the licenses of its linked FFmpeg libraries and
from the separately invoked FFmpeg executable below. No PyAV wheel, shared
library or FFmpeg binary is bundled. This measured version is not a complete
dependency lockfile.

The observed Pycairo binding is 1.29.0 and the native Cairo library is 1.18.4.
The alternative license expression above applies to the binding. Inventory
native Cairo and other system components separately if bundling them. This
source-only package contains no Pycairo wheel or Cairo binary; these version
and license observations do not establish redistribution clearance.

The tested external FFmpeg 9.0.2 executable enables `--enable-gpl`,
`--enable-version3`, `libx264` and `libx265`. It is not an LGPL-only build.
No FFmpeg binary or linked libraries are distributed here. Any bundled build
needs its own linked-library, source, notice and redistribution review; these
observed flags do not settle all component or codec-patent questions.

## Remote voice code and model weights

These optional components are separately installed on the user's authorized remote host. The source-only
Skill does not include their code, model/tokenizer files, CUDA environment or
caches. Code licenses and model licenses are distinct; neither grants rights to
arbitrary input papers, narration, fonts or output content.

| Component | Scope | License | Primary source |
| --- | --- | --- | --- |
| Qwen3-TTS-12Hz-1.7B-CustomVoice | Model repository and weights | Apache-2.0 declaration | [Official model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/raw/f00cf133b78d3c2c35857faba3b1be9b98c4f971/README.md) |
| qwen-tts 0.1.1 | Inference code, Alibaba Qwen Team; upstream LICENSE copyright Alibaba Cloud, 2026 | Apache-2.0 | [Publisher metadata](https://pypi.org/project/qwen-tts/0.1.1/), [code license](https://github.com/QwenLM/Qwen3-TTS/blob/main/LICENSE) |
| torch 2.8.0 | PyTorch code; preserve its full upstream copyright list if redistributed | BSD-3-Clause / BSD-style | [Tagged license](https://github.com/pytorch/pytorch/blob/v2.8.0/LICENSE) |
| torchaudio 2.8.0 | TorchAudio code, Facebook Inc. (Soumith Chintala), 2017 | BSD-2-Clause | [Tagged license](https://github.com/pytorch/audio/blob/v2.8.0/LICENSE) |
| transformers 4.57.3 | Model loading/generation code | Apache-2.0 | [Tagged license](https://github.com/huggingface/transformers/blob/v4.57.3/LICENSE) |
| modelscope 1.40.2 | Download/SDK code, not hosted model rights | Apache-2.0 | [Tagged license](https://github.com/modelscope/modelscope/blob/v1.40.2/LICENSE) |
| accelerate 1.12.0 | Runtime acceleration code | Apache-2.0 | [Tagged license](https://github.com/huggingface/accelerate/blob/v1.12.0/LICENSE) |
| huggingface-hub 0.36.0 | Hub client code, not hosted model rights | Apache-2.0 | [Tagged license](https://github.com/huggingface/huggingface_hub/blob/v0.36.0/LICENSE) |

The model-card commit above pins the inspected license declaration, not the
installed weight revision. Preserve actual model-content manifests in the
individual project's private reproducibility records. Do not relabel a content
digest as an upstream revision.

The [official CUDA 12.8 installation listing](https://pytorch.org/get-started/previous-versions/#v280)
supports the selected torch/torchaudio pair. Their code-license labels are not
a license inventory of an assembled CUDA wheel environment. If any upstream
material is redistributed later, retain its actual license, copyright,
applicable NOTICE and required modification notices; inventory transitive and
system components separately.

## Optional QA-only diagnostics

The evaluation may use separately installed `openai-whisper==20250625` on
tts-host. It is not required for synthesis, rendering or export and is absent
from the core requirements. Its [publisher metadata](https://pypi.org/project/openai-whisper/20250625/)
states MIT for code and model weights ([license](https://github.com/openai/whisper/blob/v20250625/LICENSE),
OpenAI, 2022). Diagnostic helpers include [tiktoken 0.12.0](https://github.com/openai/tiktoken/blob/0.12.0/LICENSE)
(MIT, OpenAI and Shantanu Jain, 2022) and [more-itertools 10.8.0](https://github.com/more-itertools/more-itertools/blob/v10.8.0/LICENSE)
(MIT, Erik Rose, 2012). No diagnostic environments, tokenizer caches or weights
are included. ASR output cannot replace human listening acceptance.

LaTeX and system fonts are optional external tools. They are not distributed by this
repository and must be reviewed under the licenses of the user's chosen distribution.
This source notice covers direct and workflow-relevant components. A binary bundle,
container, or installer must inventory and preserve notices for every transitive and
system dependency actually included.

## Writing-review methodology

The text-review workflow was independently implemented for this skill, with
methodological inspiration from the following projects. No upstream skill file is
vendored.

- Humanizer, MIT, Copyright (c) 2025 Siqi Chen:
  https://github.com/blader/humanizer
- Humanizer-zh, MIT, Copyright (c) 2026 歸藏:
  https://github.com/op7418/Humanizer-zh
- Stop Slop, MIT, by Hardik Pandya:
  https://github.com/hardikpandya/stop-slop
- Wikipedia's "Signs of AI writing," the upstream reference used by those projects:
  https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing

Wikimedia text is generally available under CC BY-SA 4.0 and GFDL. This repository
does not reproduce the Wikipedia article; it uses independently worded review rules.

## Non-bundled proprietary assets

The project may name Microsoft YaHei or another locally installed font. No Microsoft
font file is included. Generated bitmap/video output and font redistribution have
different terms; never add `.ttf`, `.otf`, `.ttc`, or similar proprietary font files
to a release without explicit redistribution rights.
