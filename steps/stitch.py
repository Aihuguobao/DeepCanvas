"""拼成片：按镜头顺序拼接，字幕按镜头时间轴排。"""
from __future__ import annotations

import os
import time

from core import media, store

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")


def run(ep: str, subs: bool = False, out: str = "") -> dict:
    items = [s for s in store.shots(ep) if (s.get("state") or {}).get("video")]
    if not items:
        raise RuntimeError(f"{ep} 还没有能拼的视频")

    clips, rows, t = [], [], 0.0
    for s in items:
        p = s["state"]["video"]
        dur = media.probe(p)["duration"]
        clips.append(p)
        text = (s.get("subtitle") or "").strip()
        if text:
            rows.append((t + 0.05, t + max(dur - 0.1, 0.4), text))
        t += dur

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = out or os.path.join(OUT, f"{store.slug(ep)}_成片_{stamp}.mp4")
    srt = ""
    if subs and rows:
        srt = media.make_srt(rows, os.path.join(OUT, f"{store.slug(ep)}_{stamp}.srt"))
    print(f"拼接 {len(clips)} 段 / {t:.1f}s → {out}")
    media.concat(clips, out, subtitle=srt)
    info = media.probe(out)
    print(f"✓ {out}  {info['duration']}s {info['size']} 音频{'有' if info['has_audio'] else '无'}")
    if srt and not subs:
        print(f"字幕文件：{srt}")
    return {"path": out, "seconds": info["duration"], "clips": len(clips), "srt": srt}
