#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成演示视频，用于在没有真实数据时演示/测试质检 Pipeline。

生成两个视频到 demo_data/（可用 --out 改）：
    demo_sharp.mp4   全程清晰（随机纹理 + 平移运动）
    demo_blur.mp4    前 40 帧清晰、后 20 帧失焦（高斯模糊）

这样开源仓库的使用者无需任何业务数据即可一键复现结果：
    python make_demo_video.py
    python video_quality_inspector.py --input demo_data --recursive
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT, FPS = 640, 360, 30
TOTAL_FRAMES = 60
BLUR_FROM = 40          # demo_blur.mp4 从该帧开始失焦
BLUR_KERNEL = 51        # 失焦强度（核越大越糊）


def write_video(path: Path, blur_from: int | None) -> None:
    """写入一段随机纹理平移的视频；blur_from 不为 None 时，其后帧做高斯模糊。"""
    rng = np.random.default_rng(42)
    # 生成一块比画幅更大的随机纹理（三通道 BGR），通过移动采样窗口制造"运动"
    texture = rng.integers(0, 256, (HEIGHT + 80, WIDTH + 80, 3), dtype=np.uint8)

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError(f"VideoWriter 打开失败（缺编码器）: {path}")

    for i in range(TOTAL_FRAMES):
        x = (i * 3) % 80
        y = (i * 2) % 80
        frame = texture[y:y + HEIGHT, x:x + WIDTH].copy()
        cv2.putText(frame, f"demo frame {i:03d}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        if blur_from is not None and i >= blur_from:
            frame = cv2.GaussianBlur(frame, (BLUR_KERNEL, BLUR_KERNEL), 0)
        writer.write(frame)

    writer.release()
    print(f"已生成: {path}（{TOTAL_FRAMES} 帧，{'全程清晰' if blur_from is None else f'{BLUR_FROM} 帧后失焦'}）")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成质检 Pipeline 的演示视频")
    parser.add_argument("--out", default="demo_data", help="输出目录（默认: demo_data）")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_video(out_dir / "demo_sharp.mp4", blur_from=None)
    write_video(out_dir / "demo_blur.mp4", blur_from=BLUR_FROM)


if __name__ == "__main__":
    main()
