# 注意力怎样分配权重

这段 55 秒的无声动画用单个 query、两组 key/value 演示注意力计算。数据为讲解设定。

先提高第二项的匹配分数，再让匹配偏向第一项，随后回到偏向第二项的状态。最后固定 query 和 key，把 v₂ 从 6 改到 10，观察输出怎样移动。

左侧显示可以为负的匹配分数。中部的指数项始终为正，使用共同的固定刻度；下方双色条的总长为 1，表示归一化权重。右侧数轴固定覆盖 2 到 10，三个点分别表示 v₁、v₂ 和输出。数字保留在固定位置，不随点移动。

## 复现

先按仓库根目录的 README 配置 Manim、FFmpeg 和 Python 环境，并准备合法取得的微软雅黑字体。在仓库根目录运行：

```bash
python scripts/build_research.py silent-preview \
  --spec assets/attention-preview/planning/preview.yaml \
  --authored-timeline assets/attention-preview/planning/timing-draft.json \
  --source assets/attention-preview/src/scenes.py \
  --out /absolute/path/to/attention-preview-v1 \
  --profile draft \
  --font-file /absolute/path/to/msyh.ttc
```

把输出和字体路径改为自己的路径。输出目录必须尚不存在，也不能经过符号链接；程序不会覆盖已有结果。字体已可用时可省略 `--font-file`。

低清规格为 960×540、15 fps、825 帧，无音轨。高清使用 `timing-final.json` 和 `--profile final`，规格为 1920×1080、60 fps、3300 帧；两者都是 55 秒。每帧重新计算权重和输出，不对终点答案直接插值。

## 文件

`src/model.py` 计算状态，`src/scenes.py` 绘制动画；`planning/` 保存屏幕文字和定时，`qa/text-review.md` 记录文案编辑。算例、公式和来源见 `source/README.md`。字体和生成视频不随源码分发。

当前交付是独立样片。完整论文介绍、内嵌无声切片的 PPT 和课程材料另行制作；教学效果需观看连续视频后审阅。
