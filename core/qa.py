"""质检：出片之后先量，再说话。

两条曲线各有各的用处：
  运动曲线 —— 判断"这一镜到底动没动"（低潮太长=慢动作）
  风格曲线 —— 判断"这一镜的画风有没有掉出整集"（灰度/边缘统计的漂移）
"""
from __future__ import annotations

import cv2
import numpy as np


def _sample(path: str, step: float = 0.25):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    every = max(1, int(round(fps * step)))
    idx, out = 0, []
    while True:
        if not cap.grab():
            break
        if idx % every == 0:
            ok, frame = cap.retrieve()
            if ok:
                out.append(frame)
        idx += 1
    cap.release()
    return out


def motion(path: str, step: float = 0.25, lull_threshold: float = 2.0) -> dict:
    frames = _sample(path, step)
    if len(frames) < 2:
        return {"samples": len(frames)}
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    diffs = [float(np.mean(cv2.absdiff(grays[i], grays[i - 1]))) for i in range(1, len(grays))]
    low = [i for i, v in enumerate(diffs) if v < lull_threshold]
    longest = run = 1 if low else 0
    for i in range(1, len(low)):
        run = run + 1 if low[i] == low[i - 1] + 1 else 1
        longest = max(longest, run)
    half = diffs[len(diffs) // 2:]
    return {
        "samples": len(frames),
        "mean": round(float(np.mean(diffs)), 2),
        "peak": round(float(np.max(diffs)), 2),
        "tail_ratio": round(float(np.mean(half) / max(np.mean(diffs), 1e-6)), 2),
        "longest_lull_s": round(longest * step, 2),
    }


def style_stats(path: str, step: float = 0.5) -> dict:
    """整段视频的风格指纹：亮度、对比度、边缘密度。跨镜头比较，差值大的要重出。"""
    frames = _sample(path, step)
    if not frames:
        return {}
    lum, contrast, edges = [], [], []
    for f in frames:
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        lum.append(float(np.mean(g)))
        contrast.append(float(np.std(g)))
        edges.append(float(np.mean(cv2.Canny(g, 60, 160) > 0)))
    return {
        "luma": round(float(np.mean(lum)), 1),
        "contrast": round(float(np.mean(contrast)), 1),
        "edge": round(float(np.mean(edges)) * 100, 2),
        "frames": len(frames),
    }


def compare(a: dict, b: dict) -> list[str]:
    """两镜之间的风格差；超过 20% 就点名。"""
    out = []
    for key, label in (("luma", "亮度"), ("contrast", "对比"), ("edge", "边缘密度")):
        if not a.get(key) or not b.get(key):
            continue
        base = max(a[key], b[key])
        diff = abs(a[key] - b[key]) / base
        if diff > 0.2:
            out.append(f"{label}差 {diff * 100:.0f}%（{a[key]} vs {b[key]}）")
    return out
