# 算例与源码说明

设单个 query、两组 key/value，维度 dₖ = 1。取 k₁ = 0、k₂ = 1、v₁ = 2，初始 v₂ = 6，匹配分数便是 s₁ = 0、s₂ = q。

指数项为 e₁ = exp(s₁)、e₂ = exp(s₂)。计算权重时先减去两个分数的最大值，再取指数并归一化，这是数值稳定的 softmax。画面的指数条显示未平移的指数项，使用共同的固定刻度；权重条的总长则为 1。

输入用 smoothstep 插值，h(u) = 3u² − 2u³。0 到 10 秒保持 q = 0；10 到 25 秒从 0 变到 ln 3；25 到 38 秒从 ln 3 变到 −ln 3；38 到 42 秒回到 ln 3；42 到 50 秒保持 q 不变，让 v₂ 从 6 变到 10；50 到 55 秒保持末态并显示加权和公式。

输出为 y = a₁v₁ + a₂v₂，各阶段端点依次为 4、5、3、5、8。最后一段把 Q/K 固定，只改变 V，用来区分匹配权重与被加权的内容。

model.py 计算每帧状态，scenes.py 用它更新位置、长度和两位小数。帧区间采用半开区间，非法帧号或帧率会报错。这里是一维教学算例；向量推广采用原论文的行向量约定，按行计算 softmax。

## 来源

计算依据为 Vaswani 等人的 [Attention Is All You Need，§3.2.1，式 (1)](https://arxiv.org/html/1706.03762v7#S3.SS2.SSS1)。教学次序参考 3Blue1Brown 的 [Attention in transformers, step-by-step](https://www.3blue1brown.com/lessons/attention/)，从具体计算引出抽象表示。本目录的算例、源码和图形为本项目编写，未使用参考课程的视频、配音、音乐或图像。
