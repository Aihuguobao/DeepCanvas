"""出首帧：Krea2。生图只吃画面，不吃动作逻辑。

一个镜头可以有两张图：
  kf         首帧，钉在 0 秒
  tail_frame 尾帧，钉在 70% 处（尾锚点贴到片尾会让模型"到了就不动"）
尾帧不是"下一个姿势"，是"这一段结束时该到的状态"——比直觉再远一点，动作才跑得起来。
"""
from __future__ import annotations

import time

from PIL import Image

from core import comfy, graphs, prompts, store


def _one(ep: str, sid: str, text: str, seed: int, prefix: str, label: str) -> str:
    proj = store.read(ep, "project")
    graph = graphs.krea2(text, seed=seed, prefix=prefix,
                         width=proj.get("width", 0), height=proj.get("height", 0))
    print(f"  [{ep}/{sid}] Krea2 出{label}  种子 {seed}")
    pid = comfy.submit(graph, f"{ep}/{sid} {label}")
    hist = comfy.wait(pid, f"{ep}/{sid} {label}",
                      on_tick=lambda t, s: print(f"    … {t:>4}s {s}", flush=True))
    files = [f for f in comfy.produced(hist, ("images",)) if f["filename"].endswith(".png")]
    if not files:
        raise RuntimeError("跑完了但没有图，看 ComfyUI 控制台")
    path = comfy.local_path(files[0])
    with Image.open(path) as im:
        print(f"  ✓ {label} {path}  ({im.width}x{im.height})")
    return path


def run(ep: str, sid: str, dry: bool = False, force: bool = False, seed: int = 0,
        only: str = "") -> dict:
    """only 可选 kf / tail：只重出其中一张，不动另一张。"""
    proj = store.read(ep, "project")
    shot = store.shot(ep, sid)
    style = shot.get("style") or proj.get("style") or "gamecg"
    text = prompts.image_prompt(shot, style)
    tail_text = prompts.image_prompt(shot, style, which="tail") if shot.get("image", {}).get("tail") else ""

    problems = prompts.check_image_prompt(text)
    if problems:
        print("⚠ 提示词自检：", *problems, sep="\n  - ")
    if dry:
        print(f"[{ep}/{sid}] 首帧提示词（{len(text.split())} 词）：\n{text}")
        if tail_text:
            print(f"\n[尾帧提示词]（{len(tail_text.split())} 词）：\n{tail_text}")
        return {"dry": True, "prompt": text, "tail_prompt": tail_text, "problems": problems}

    st = shot.get("state") or {}
    seed = seed or int(time.time()) % 1_000_000_007
    base = f"keyframes/{proj['episode']}_{sid}"
    fields = {}

    want_kf = only in ("", "kf")
    if want_kf and (not st.get("kf") or force):
        kf = _one(ep, sid, text, seed, f"{base}_kf", "首帧")
        fields.update(kf=kf, kf_prompt=text, kf_seed=seed, kf_style=style,
                      kf_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    elif want_kf:
        print(f"{ep}/{sid} 已有首帧：{st['kf']}（要重出加 --force）")

    want_tail = only in ("", "tail") and bool(tail_text)
    if want_tail and (not st.get("tail_frame") or force):
        tail = _one(ep, sid, tail_text, seed + 1, f"{base}_tail", "尾帧")
        fields.update(tail_frame=tail, tail_prompt=tail_text,
                      tail_at=float(shot.get("tail_at", 0.7)))
    elif want_tail:
        print(f"{ep}/{sid} 已有尾帧：{st['tail_frame']}（要重出加 --force）")

    if fields:
        store.set_state(ep, sid, **fields)
    print(f"✓ {ep}/{sid} 就绪")
    return {"path": fields.get("kf", st.get("kf", "")),
            "tail": fields.get("tail_frame", st.get("tail_frame", "")),
            "prompt": text, "seed": seed, "problems": problems}
