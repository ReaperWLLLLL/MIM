# Demo provenance

All images and animations here are rendered from project-authored Manim scenes.
No lecture pages, paper screenshots, source figures, voice recordings or font
files are included.

## Published full videos

The three silent videos use the same ordered names in the main README and
in the [downloadable release](https://github.com/ReaperWLLLLL/MIM/releases/tag/demo-videos-2026-10-25).
MP4s are release attachments, not tracked source files. Existing inline GitHub
attachments remain available for the circuit and neural-network examples.

### 01 · 高网：树支、连支与 A/B/Q 矩阵

Filename: `mim-demo-01-circuit-network.mp4`.
The main README embeds the publicly uploaded chapter-one video:
https://github.com/user-attachments/assets/8bffd351-8f4e-4719-930c-e759f818a6c2
It shows an original four-node example explaining trees, links, cutsets and
the A/B/Q matrices. The uploaded file has exactly one H.264 video stream,
1280×720 at 30 fps, duration 222.266016 seconds, and no audio stream.
Size: 6,254,705 bytes. SHA256:
`ad9d0eec03ed8ab9ec8c75593ab50e3c2dbb1ea47bd752643d1614ca48803fe0`.
The attachment contains no lecture pages, source PDF, voice recordings or fonts.

### 02 · DeepInfer：生产集群调度

Filename: `mim-demo-02-deepinfer.mp4`.
This project-authored explanatory redraw follows three illustrative requests
through prefix reuse, Prefill assignment and chunking, KV handoff, Decode
recipient selection and streaming output. It is based on DeepSeek-AI's
[production deployment Q&A](https://github.com/deepseek-ai/DeepInfer/blob/9bd9cf243fc53ef9afbf8f04d391d989117d6ab9/doc/inference_deployment_qa.md),
particularly data-parallel load balancing, KV cache storage and output parsing.
No original architecture artwork or DeepInfer implementation is included.
The request lengths and background load snapshots are illustrative, not measured
performance. This video is not a validation of the undisclosed serving components.

One H.264 video stream, 1280×720 at 30 fps, duration 180 seconds, no audio.
Size: 4,852,036 bytes. SHA256:
`bcc4e8933aebac92ce91329bbade3d1a572b1c2950f02d83161c0b5f454efc1a`.
No private PDFs, source-page screenshots, voices, models or font binaries are
included in the attachment.

`deepinfer-cluster-scheduling.gif` is a 720×405, 8 fps preview made from the
same final video: 00:34–00:38, 01:10–01:14 and 01:57–02:01, in that order.
It is a 12-second excerpt montage, not another full video or a benchmark.

### 03 · 神经网络：两路梯度回传

Filename: `mim-demo-03-neural-network.mp4`.
The README also embeds the silent neural-network/backpropagation video:
https://github.com/user-attachments/assets/a3df5c9e-c3d4-4d22-8d98-9f2a1678818f
It follows a weight through forward computation, two backward paths, signed
gradient accumulation and synchronous parameter updates. Network graphics and
example parameters were authored for the explanation, not copied from lecture
pages or reported as experimental data. The file contains one H.264 video stream,
1280×720 at 30 fps, duration 180 seconds, with no audio.
Size: 4,198,443 bytes. SHA256:
`66084ad08f15cb4aafec01e4bede8cde74f217637303ad7ce34bb9eb0eaf160b`.
No private source PDF, lecture screenshots, institution branding, voices or font
files are included in the uploaded video.

## Other previews

- The three style PNGs/GIFs show the original local branch stamp in
  ../native-example/style_showcase.py. This standard relation between two
  terminal currents and voltages requires no course document to reproduce.
  Commands: [visual-styles.md](../../references/visual-styles.md).
- qkv-attention.gif and attention-deck-overview.png are previously published
  project-authored explanatory redraws for Vaswani et al., *Attention Is All
  You Need* (2017), particularly §3.2.1. They are older deck-workflow examples.
  [Paper reference](https://papers.nips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html).

Font rendering used a locally installed font; no font binary is distributed.
MIT covers this project's original source and demo artwork. External software
and fonts retain their own terms.
