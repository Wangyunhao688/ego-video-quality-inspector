#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ego 视频质检 Pipeline —— 逐帧清晰度检测 + 批量质检报告

对一段或一批视频逐帧计算清晰度（拉普拉斯方差），标记模糊帧，
输出结构化质检报告（CSV），并可收集疑似模糊帧供人工复核。

背景：具身智能 Ego 视角数据采集后，人工逐帧抽检效率低、易漏检。
本工具将抽帧、清晰度计算、模糊判定、报告产出整条链路自动化，
支持单视频或整个采集目录一键质检。

输出（默认写入 qc_output/）：
    quality_report.csv     全部实测帧的清晰度明细（含 is_blur 标记）
    blur_frames.csv        模糊帧清单（无模糊帧时不生成）
    summary_report.csv     每个视频的汇总统计（帧数/模糊率/清晰度均值等）
    frames/<视频名>/        全部抽帧图片（需 --save-frames）
    blur_frames/<视频名>/   模糊帧图片，供人工复核（需 --save-blur-frames）

用法示例：
    # 单个视频
    python video_quality_inspector.py --input test.mp4

    # 批量质检整个文件夹（含子目录）
    python video_quality_inspector.py --input ./videos --recursive

    # 自定义模糊阈值 80、每 5 帧抽检一帧、保存模糊帧图片
    python video_quality_inspector.py --input ./videos -t 80 -s 5 --save-blur-frames
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2
import pandas as pd
from tqdm import tqdm

# 支持的视频扩展名（统一按小写比较）
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}

logger = logging.getLogger("video_qc")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量计算视频逐帧清晰度（拉普拉斯方差），输出质检报告 CSV",
    )
    parser.add_argument("--input", "-i", required=True,
                        help="视频文件路径，或包含视频的文件夹路径")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="递归搜索子文件夹（仅当 --input 为文件夹时生效）")
    parser.add_argument("--output-dir", "-o", default="qc_output",
                        help="报告与图片的输出目录（默认: qc_output）")
    parser.add_argument("--blur-threshold", "-t", type=float, default=50.0,
                        help="清晰度阈值，低于该值判定为模糊帧（默认: 50.0）")
    parser.add_argument("--frame-step", "-s", type=int, default=1,
                        help="抽检间隔：每 N 帧实测一帧（默认: 1，即逐帧全检）")
    parser.add_argument("--save-frames", action="store_true",
                        help="保存全部读取到的帧图片")
    parser.add_argument("--save-blur-frames", action="store_true",
                        help="额外把模糊帧图片保存到输出目录，供人工复核")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="输出 DEBUG 级日志（含每个模糊帧的逐条记录）")
    return parser.parse_args()


def find_videos(input_path: Path, recursive: bool) -> list[Path]:
    """收集待质检的视频文件，按路径排序保证处理顺序可复现。"""
    if input_path.is_file():
        if input_path.suffix.lower() not in VIDEO_EXTS:
            raise ValueError(f"不支持的文件类型: {input_path}（支持: {' '.join(sorted(VIDEO_EXTS))}）")
        return [input_path]
    if input_path.is_dir():
        pattern = "**/*" if recursive else "*"
        return sorted(
            p for p in input_path.glob(pattern)
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS
        )
    raise FileNotFoundError(f"输入路径不存在: {input_path}")


def compute_sharpness(frame) -> float:
    """拉普拉斯方差法：灰度图求 Laplacian 后取方差，数值越大越清晰。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def process_video(video_path: Path, args: argparse.Namespace) -> tuple[list[dict], int]:
    """处理单个视频，返回 (实测帧记录列表, 实际读取帧数)。"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error("无法打开视频，已跳过: %s", video_path)
        return [], 0

    # 元数据帧数只作为进度条参考，部分编码/流媒体场景可能拿到 0 或不准
    total_hint = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out_dir = Path(args.output_dir)
    frames_dir = out_dir / "frames" / video_path.stem
    blur_dir = out_dir / "blur_frames" / video_path.stem
    if args.save_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    frames_read = 0
    blur_count = 0

    pbar = tqdm(total=total_hint if total_hint > 0 else None,
                desc=f"质检 {video_path.name}", unit="帧", dynamic_ncols=True)
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            pbar.update(1)
            frame_idx = frames_read          # 从 0 开始编号，与历史报告兼容
            frames_read += 1
            frame_name = f"frame_{frame_idx:04d}.jpg"

            if args.save_frames:
                cv2.imwrite(str(frames_dir / frame_name), frame)

            # 抽检模式：不在采样点上的帧只跳过检测，不中断读取
            if frame_idx % args.frame_step != 0:
                continue

            sharpness = compute_sharpness(frame)
            is_blur = sharpness < args.blur_threshold
            if is_blur:
                blur_count += 1
                logger.debug("模糊帧 %s / %s  sharpness=%.2f", video_path.name, frame_name, sharpness)
                if args.save_blur_frames:
                    blur_dir.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(blur_dir / frame_name), frame)

            records.append({
                "video": video_path.name,
                "frame_name": frame_name,
                "frame_idx": frame_idx,
                "sharpness": sharpness,
                "is_blur": is_blur,
            })
            pbar.set_postfix(模糊=blur_count)
    finally:
        cap.release()
        pbar.close()

    if total_hint > 0 and frames_read < total_hint:
        logger.warning("%s: 实际解码 %d 帧 < 元数据 %d 帧，视频可能损坏或提前结束",
                       video_path.name, frames_read, total_hint)

    log_level = logging.WARNING if blur_count else logging.INFO
    logger.log(log_level, "%s: 读取 %d 帧 / 实测 %d 帧 / 模糊 %d 帧 (%.1f%%)",
               video_path.name, frames_read, len(records), blur_count,
               blur_count / len(records) * 100 if records else 0.0)
    return records, frames_read


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.frame_step < 1:
        logger.error("--frame-step 必须 >= 1")
        sys.exit(1)

    input_path = Path(args.input)
    try:
        videos = find_videos(input_path, args.recursive)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("%s", exc)
        sys.exit(1)

    if not videos:
        logger.error("未在 %s 中找到视频文件（支持: %s）",
                     input_path, " ".join(sorted(VIDEO_EXTS)))
        sys.exit(1)

    logger.info("共发现 %d 个待质检视频 | 模糊阈值 %.1f | 抽检间隔 %d 帧",
                len(videos), args.blur_threshold, args.frame_step)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    frames_read_map: dict[str, int] = {}
    t0 = time.perf_counter()
    for video in videos:
        records, frames_read = process_video(video, args)
        all_records.extend(records)
        frames_read_map[video.name] = frames_read
    elapsed = time.perf_counter() - t0

    if not all_records:
        logger.error("所有视频均未能解码出任何帧，请检查文件是否损坏")
        sys.exit(1)

    # 1) 全量明细报告
    df = pd.DataFrame(all_records,
                      columns=["video", "frame_name", "frame_idx", "sharpness", "is_blur"])
    report_csv = out_dir / "quality_report.csv"
    df.to_csv(report_csv, index=False, encoding="utf-8-sig")

    # 2) 模糊帧清单（无模糊时不生成，保持输出干净）
    if df["is_blur"].any():
        blur_csv = out_dir / "blur_frames.csv"
        df[df["is_blur"]].to_csv(blur_csv, index=False, encoding="utf-8-sig")
        logger.warning("共发现 %d 个模糊帧，清单已写入 %s", int(df["is_blur"].sum()), blur_csv)
    else:
        logger.info("未发现模糊帧，不生成 blur_frames.csv")

    # 3) 每视频汇总统计：帧数、模糊率、清晰度分布
    summary = (df.groupby("video", sort=False)
                 .agg(frames_checked=("frame_idx", "size"),
                      blur_count=("is_blur", "sum"),
                      sharpness_mean=("sharpness", "mean"),
                      sharpness_min=("sharpness", "min"),
                      sharpness_max=("sharpness", "max"))
                 .reset_index())
    summary["frames_read"] = summary["video"].map(frames_read_map)
    summary["blur_ratio_pct"] = (summary["blur_count"] / summary["frames_checked"] * 100).round(2)
    summary = summary[["video", "frames_read", "frames_checked",
                       "blur_count", "blur_ratio_pct",
                       "sharpness_mean", "sharpness_min", "sharpness_max"]]
    summary_csv = out_dir / "summary_report.csv"
    summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    logger.info("================ 质检汇总 ================")
    logger.info("\n%s", summary.to_string(index=False))
    logger.info("质检完成：%d 个视频 / 实测 %d 帧 / 耗时 %.1f 秒",
                len(videos), len(df), elapsed)
    logger.info("明细报告: %s", report_csv)
    logger.info("汇总报告: %s", summary_csv)


if __name__ == "__main__":
    main()
