from __future__ import annotations

import os
import sys
import time

from core import settings, store

AGENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_BITRATE = "256k"
CRF = 16


def _relay():
    root = settings.comfy_root()
    if not root:
        raise RuntimeError("找不到 ComfyUI 目录：先在「设置」里指定 ComfyUI 文件夹")
    pkg = os.path.join(root, "custom_nodes", "ComfyUI-H3-Latent-Relay")
    if not os.path.isdir(pkg):
        raise RuntimeError(f"找不到 ComfyUI-H3-Latent-Relay：{pkg}")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from relay_core.concat import assemble_mp4_segments, probe_mp4
    return assemble_mp4_segments, probe_mp4


def _fps_tol(ref_fps: float) -> float:
    ref = float(ref_fps or 0.0)
    return max(0.02, ref * 0.005)


def plan(ep: str) -> dict:
    try:
        _, probe_mp4 = _relay()
        relay_err = ""
    except RuntimeError as exc:
        probe_mp4 = None
        relay_err = str(exc)

    rows, ref = [], None
    seq = 0
    for s in store.shots(ep):
        st = s.get("state") or {}
        path = st.get("chosen_video") or st.get("video") or ""
        row = {"id": s["id"], "path": path, "name": os.path.basename(path) if path else "",
               "exists": bool(path) and os.path.isfile(path), "problems": []}
        run = next((x for x in (st.get("video_runs") or []) if x.get("path") == path), {})
        row["poster"] = run.get("poster") or ""
        if row["exists"] and probe_mp4:
            try:
                pr = probe_mp4(path)
            except Exception as exc:  # noqa: BLE001 - 探不动就当坏文件
                row["problems"].append(f"读不出来：{type(exc).__name__}: {exc}")
            else:
                row.update({
                    "width": pr["width"], "height": pr["height"], "fps": round(float(pr["fps"]), 3),
                    "frames": pr["frames"], "seconds": round(float(pr["v_seconds"]), 3),
                    "has_audio": bool(pr.get("has_audio")),
                    "a_rate": pr.get("a_rate"), "a_layout": pr.get("a_layout"),
                    "av_delta": round(float(pr.get("a_v_delta") or 0.0), 4),
                })
                seq += 1
                if ref is None:
                    ref = row
                else:
                    if (row["width"], row["height"]) != (ref["width"], ref["height"]):
                        row["problems"].append(
                            f"分辨率 {row['width']}×{row['height']}，和 {ref['id']} 的 "
                            f"{ref['width']}×{ref['height']} 不一致")
                    if abs(row["fps"] - ref["fps"]) > _fps_tol(ref["fps"]):
                        row["problems"].append(
                            f"帧率 {row['fps']}，和 {ref['id']} 的 {ref['fps']} 不一致")
                    if row["has_audio"] != ref["has_audio"]:
                        row["problems"].append("音轨有无和第一段不一致")
                    elif row["has_audio"]:
                        for key, label in (("a_rate", "采样率"), ("a_layout", "声道")):
                            if row[key] != ref[key]:
                                row["problems"].append(f"{label} {row[key]}，和第一段 {ref[key]} 不一致")
                    if row["has_audio"] and row["fps"] and row["av_delta"] > 1.0 / row["fps"] + 0.02:
                        row["problems"].append(
                            f"音频比画面长 {row['av_delta']:.3f}s（超过 1 帧）")
        elif row["exists"] is False and relay_err:
            row["problems"].append(relay_err)
        rows.append(row)

    total = round(sum(float(r.get("seconds") or 0) for r in rows if r["exists"]), 3)
    bad = [r["id"] for r in rows if r["problems"]]
    return {"episode": ep, "shots": rows, "seconds": total,
            "problems": bad, "relay_error": relay_err}


def run(ep: str, seq: list[str], out: str = "", on_log=None) -> dict:
    _, probe_mp4 = _relay()
    shots = {s["id"]: s for s in store.shots(ep)}
    paths = []
    for sid in seq:
        shot = shots.get(sid)
        if not shot:
            raise ValueError(f"{ep} 没有镜头 {sid}")
        st = shot.get("state") or {}
        p = st.get("chosen_video") or st.get("video") or ""
        if not p or not os.path.isfile(p):
            raise ValueError(f"{sid} 还没有成片")
        paths.append(p)
    if not paths:
        raise ValueError("没有可拼的段")

    if not out:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = os.path.join(AGENT, "out", "成片", store.slug(ep), f"{store.slug(ep)}_成片_{stamp}.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    assemble, _ = _relay()
    t0 = time.time()
    rep = assemble(paths, out, audio_codec="aac", audio_bitrate=AUDIO_BITRATE, crf=CRF,
                   on_log=on_log)
    took = round(time.time() - t0, 1)
    info = probe_mp4(out) if os.path.isfile(out) else {}
    return {"ok": bool(rep.get("ok")), "out": out, "mode": rep.get("mode"),
            "seconds": info.get("v_seconds"), "frames": info.get("frames"),
            "fps": round(float(info.get("fps") or 0), 3) if info else None,
            "mb": round(os.path.getsize(out) / 2**20, 2) if os.path.isfile(out) else 0,
            "took": took, "asserts": rep.get("asserts"), "report": rep.get("report") or "",
            "clips": len(paths), "seq": list(seq)}
