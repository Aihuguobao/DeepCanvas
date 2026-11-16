from __future__ import annotations

import os
import time

from core import media, store

AGENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(ep: str, sid: str, src: str = "") -> dict:
    shot = store.shot(ep, sid)
    st = shot.get("state") or {}
    src = src or st.get("chosen_video") or st.get("video") or ""
    if not src or not os.path.isfile(src):
        raise ValueError("这一镜还没有成片，先出视频再补帧")
    chk = media.probe(src)
    if "48" in str(chk.get("fps") or ""):
        raise ValueError("这条母版已经是 48fps 了")

    out_dir = os.path.join(AGENT, "out", "单片", store.slug(ep))
    out = os.path.join(out_dir, f"{sid}_48fps.mp4")
    t0 = time.time()
    media.interpolate(src, out)
    took = round(time.time() - t0, 1)
    info = media.probe(out)

    runs = list(st.get("video_runs") or [])
    src_run = next((r for r in runs if r.get("path") == src), {})
    poster = ""
    try:
        poster = media.poster(out, os.path.join(
            AGENT, "projects", store.slug(ep), "assets", f"{sid}_poster_48fps.png"))
    except Exception as exc:  # noqa: BLE001 - 封面失败不该挡补帧
        print(f"  ! 补帧版抽封面失败：{exc}")
    runs = [r for r in runs if r.get("path") != out]          # 重跑补帧别叠重复项
    runs.append({"path": out, "seed": src_run.get("seed") or st.get("video_seed"),
                 "prompt": src_run.get("prompt") or "", "poster": poster,
                 "interpolated_from": src,
                 "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    store.set_state(ep, sid, video_runs=runs, video=out, chosen_video=out,
                    interpolated_from=src)
    mb = round(os.path.getsize(out) / 2**20, 2)
    print(f"  补帧 {ep}/{sid}：{os.path.basename(src)} → {os.path.basename(out)} "
          f"{info.get('duration')}s {info.get('fps')} 用了 {took}s")
    return {"ok": True, "path": out, "seconds": info.get("duration"),
            "fps": info.get("fps"), "took": took, "mb": mb}
