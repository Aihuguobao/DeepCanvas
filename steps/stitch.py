"""拼成片：按镜头顺序拼接。"""
from __future__ import annotations

import os
import time

from core import media, store

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "运行数据")


def run(ep: str, out: str = "") -> dict:
    items = [s for s in store.shots(ep) if (s.get("state") or {}).get("video")]
    if not items:
        raise RuntimeError(f"{ep} 还没有能拼的视频")

    clips, t = [], 0.0
    for s in items:
        p = s["state"]["video"]
        dur = media.probe(p)["duration"]
        clips.append(p)
        t += dur

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = out or os.path.join(OUT, f"{store.slug(ep)}_成片_{stamp}.mp4")
    print(f"拼接 {len(clips)} 段 / {t:.1f}s → {out}")
    media.concat(clips, out)
    info = media.probe(out)
    print(f"✓ {out}  {info['duration']}s {info['size']} 音频{'有' if info['has_audio'] else '无'}")
    return {"path": out, "seconds": info["duration"], "clips": len(clips)}
