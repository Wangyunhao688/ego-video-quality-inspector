#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质检报告可视化：把 quality_report.csv 画成清晰度趋势图。

功能：
    - X 轴：帧序号；Y 轴：清晰度分数（拉普拉斯方差）
    - 低于 --threshold 的帧标红点，并画红色虚线阈值线
    - 同时画出「均值 - 3σ」自适应基线（橙色点线），用于校准固定阈值
    - CSV 包含多个视频时，每个视频生成一张子图，输出独立 PNG

兼容两种报告格式：
    - 新版（video_quality_inspector.py）：video, frame_name, frame_idx, sharpness, is_blur
    - 旧版（test3.py）：帧文件名, 清晰度分数

图内文字使用英文：Matplotlib 默认字体不含中文，跨平台（Windows/Linux）渲染
中文需额外配置字体；英文标签可保证任何环境一键复现、不出现方块乱码。

用法：
    python plot_quality_curve.py --csv qc_output/quality_report.csv
    python plot_quality_curve.py --csv quality_report.csv --threshold 80
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无显示器环境（服务器/CI）也能出图
import matplotlib.pyplot as plt
import pandas as pd

LINE_COLOR = "#4C72B0"
ALERT_COLOR = "#C44E52"
BASELINE_COLOR = "#DD8452"


def load_report(csv_path: Path) -> pd.DataFrame:
    """读取质检 CSV，自动兼容新版/旧版列名，统一为 frame_idx + sharpness + video。"""
    df = pd.read_csv(csv_path)

    if "sharpness" in df.columns:                      # 新版格式
        if "frame_idx" not in df.columns:
            df["frame_idx"] = range(len(df))
        return df

    if "清晰度分数" in df.columns:                     # 旧版格式（test3.py 产出）
        df = df.rename(columns={"清晰度分数": "sharpness"})

        def name_to_idx(name: str) -> int:
            digits = "".join(ch for ch in Path(str(name)).stem if ch.isdigit())
            return int(digits) if digits else 0

        df["frame_idx"] = df["帧文件名"].map(name_to_idx)
        df["video"] = "video"
        return df

    raise SystemExit(f"无法识别的 CSV 列名: {list(df.columns)}，请用质检脚本重新生成报告")


def plot_video(ax: plt.Axes, sub: pd.DataFrame, threshold: float, video: str) -> None:
    """在给定子图上绘制单个视频的清晰度趋势。"""
    ax.plot(sub["frame_idx"], sub["sharpness"],
            color=LINE_COLOR, lw=1.2, label="sharpness")

    # 固定阈值线
    ax.axhline(threshold, color=ALERT_COLOR, ls="--", lw=1.0,
               label=f"fixed threshold = {threshold:g}")

    # 自适应基线：均值 - 3σ（正常段的统计下界）
    mean, std = sub["sharpness"].mean(), sub["sharpness"].std()
    baseline = mean - 3 * std
    ax.axhline(baseline, color=BASELINE_COLOR, ls=":", lw=1.4,
               label=f"adaptive baseline (mean-3std) = {baseline:.1f}")

    # 模糊帧红点
    blur = sub[sub["sharpness"] < threshold]
    if not blur.empty:
        ax.scatter(blur["frame_idx"], blur["sharpness"],
                   color=ALERT_COLOR, s=26, zorder=3,
                   label=f"below threshold ({len(blur)} frames)")

    ax.set_title(f"{video}   |   frames checked: {len(sub)}, "
                 f"below threshold: {len(blur)}", fontsize=10)
    ax.set_xlabel("Frame Index", fontsize=9)
    ax.set_ylabel("Sharpness (Laplacian variance)", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7, loc="upper right")


def grid_shape(n: int) -> tuple[int, int]:
    """根据视频数量决定子图行列数（1→1x1，2→2x1，3-4→2x2）。"""
    if n <= 1:
        return 1, 1
    if n == 2:
        return 2, 1
    return 2, math.ceil(n / 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="绘制清晰度趋势图（质检报告可视化）")
    parser.add_argument("--csv", required=True, help="质检报告 CSV 路径")
    parser.add_argument("--threshold", "-t", type=float, default=50.0,
                        help="模糊阈值，低于该值的帧标红（默认: 50）")
    parser.add_argument("--out", "-o", default="quality_curve.png",
                        help="单视频时的输出文件名（默认: quality_curve.png）")
    args = parser.parse_args()

    df = load_report(Path(args.csv))
    videos = list(dict.fromkeys(df["video"]))          # 保持出现顺序、去重
    rows, cols = grid_shape(len(videos))
    fig, axes = plt.subplots(rows, cols, figsize=(10 * cols, 3.6 * rows), squeeze=False)

    for ax, video in zip(axes.flat, videos):
        plot_video(ax, df[df["video"] == video], args.threshold, video)

    # 多余的空子图直接关闭
    for ax in axes.flat[len(videos):]:
        ax.axis("off")

    fig.tight_layout()

    if len(videos) == 1:
        out_path = Path(args.out)
        fig.savefig(out_path, dpi=150)
        print(f"已生成: {out_path}")
    else:
        stem = Path(args.out).with_suffix("")
        for video in videos:
            out_path = Path(f"{stem}_{Path(video).stem}.png")
            # 只保留当前视频的子图重新出图，文件名互不干扰
            sub_fig, sub_ax = plt.subplots(figsize=(10, 3.6))
            plot_video(sub_ax, df[df["video"] == video], args.threshold, video)
            sub_fig.tight_layout()
            sub_fig.savefig(out_path, dpi=150)
            plt.close(sub_fig)
            print(f"已生成: {out_path}")


if __name__ == "__main__":
    main()
