# -*- coding: utf-8 -*-
r"""角色拼接参考图生成（画布按钮调用 / 命令行也能用）。

一条链路 = 今天验证过的那套：
  同一颗种子 + 同一份人设提示词 → 只改「姿态/视角」段 → 出 4 视角 + 4 姿势 + 服装单品 → 拼成 4×3 一张图。

规矩（见 skills\refsheet）：
· **脸部由种子决定**，禁止图生图改姿势、禁止抠真人/成片帧；
· 姿势只给通用人体姿势（站 / 坐 / 蹲 / 跑）；
· 背景纯浅灰，无道具、无器材、无文字；
· 左侧视角 = 右侧水平镜像。
"""
from __future__ import annotations

import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
sys.path.insert(0, AGENT)
from core import comfy, graphs  # noqa: E402

UNET = "krea2_turbo_fp8_scaled.safetensors"
CLIP = "qwen3vl_4b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"

CELL_W, CELL_H, GAP, LABEL_H = 390, 520, 8, 30
BAND_BG = 216

VIEWS = {
    "front": "全身站姿，身体正面朝向镜头（正视图），双脚与肩同宽，双臂自然垂在身体两侧，表情平静，全身入镜。",
    "right": "严格的 90 度右侧视图，只能看到她的右侧轮廓：右肩、右侧脸、右手臂和右腿，"
             "身体另一侧完全被自身挡住，鼻尖朝向画面左方，双脚并拢，双臂自然垂在身体两侧。",
    "back": "全身站姿，背对镜头（正背视图），双脚与肩同宽，双臂自然垂在身体两侧，看不到脸。",
}
POSES = {
    "stand": "全身站姿，身体正面朝向镜头（正视图），双脚与肩同宽，双臂自然垂在身体两侧，表情平静。",
    "sit": "跪坐姿势，双膝跪地、小腿贴地、臀部坐在脚跟上，身体与镜头成 45 度侧身，"
           "双手自然放在大腿上，上身挺直；画面底部能看到地面。",
    "squat": "徒手深蹲，双脚与肩同宽、脚尖朝前，膝盖弯曲，臀部向后下方坐到接近大腿与地面平行，"
             "上身略前倾、背部平直、胸口抬起，双臂在身前自然下垂；正侧面对镜头（90 度侧视图），"
             "全身入画，不带任何器械。",
    "run": "全身跑姿，向前奔跑中，身体略前倾，一只脚着地、另一只脚离地向后，双臂自然摆动，表情专注。",
}
COSTUME_TAIL = ("平铺产品图，纯浅灰无缝背景，俯视角，柔光，无人、无模特、无文字；"
                "整件完整入画、四周留白、边缘不接触画面边界。")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _read(p: str):
    return cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)


def _cover(img, w, h):
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih)
    r = cv2.resize(img, (max(1, int(iw * s)), max(1, int(ih * s))))
    y0, x0 = (r.shape[0] - h) // 2, (r.shape[1] - w) // 2
    return r[y0:y0 + h, x0:x0 + w]


def _cell(img, label):
    t = _cover(img, CELL_W, CELL_H)
    t = cv2.copyMakeBorder(t, LABEL_H, GAP, GAP, GAP, cv2.BORDER_CONSTANT, value=(20, 20, 20))
    cv2.putText(t, label, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1)
    return t


def _trim(img, pad=8):
    bg = np.median(img[0:10, 0:10].reshape(-1, 3), axis=0)
    diff = np.abs(img.astype(np.int16) - bg.astype(np.int16)).sum(axis=2)
    ys, xs = np.where(diff > 30)
    if not len(xs):
        return img
    y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad)
    x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad)
    return img[y0:y1, x0:x1]


def _swap_pose(base_prompt: str, pose_text: str) -> str:
    i, j = base_prompt.find("姿态："), base_prompt.find("背景：")
    if i < 0 or j <= i:
        return base_prompt.rstrip() + "\n\n姿态：\n" + pose_text
    return base_prompt[:i] + "姿态：\n" + pose_text + "\n\n" + base_prompt[j:]


def _graph(prompt: str, seed: int, prefix: str, size=(832, 1248)) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": size[0], "height": size[1], "batch_size": 1}},
        "6": {"class_type": "KSamplerAdvanced", "inputs": {
            "add_noise": "enable", "noise_seed": int(seed), "steps": 8, "cfg": 1.0,
            "sampler_name": "euler_ancestral", "scheduler": "beta",
            "start_at_step": 0, "end_at_step": 8, "return_with_leftover_noise": "disable",
            "model": ["1", 0], "positive": ["4", 0], "negative": ["4", 0], "latent_image": ["5", 0]}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": prefix}},
    }


def _gen(prompt: str, seed: int, prefix: str, size=(832, 1248), timeout: int = 1800) -> str:
    pid = comfy.submit(_graph(prompt, seed, prefix, size), prefix.split("/")[-1])
    hist = comfy.wait(pid, prefix.split("/")[-1], timeout=timeout)
    for o in (hist.get("outputs") or {}).values():
        for it in (o.get("images") or []):
            if str(it.get("filename", "")).lower().endswith(".png"):
                return comfy.local_path(it) or ""
    return ""



def costume_from_prompt(prompt: str) -> list[tuple[str, str]]:
    """从人设提示词里抽服装单品。

    两种写法都要认（踩过的坑：只认「- 上身：」这种条目式，单行散文就会抽不到，
    于是永远回退成「整套服装」一张图，看起来就是"每个角色都是同一套衣服"）：
      ① 条目式：`- 上身：黑色工字背运动内衣` / `- 鞋：白色低帮运动鞋`
      ② 散文式：`身穿宽松T恤，牛仔短裙。光脚穿人字拖。`
    """
    body_words = ("胸", "腰", "臀", "腿", "身高", "身材", "罩杯", "皮肤", "面部", "脸")
    cloth_keys = [("上身", "top"), ("上衣", "top"), ("下装", "bottom"), ("下身", "bottom"),
                  ("裙", "skirt"), ("裤", "pants"), ("袜", "socks"), ("鞋", "shoes"),
                  ("拖", "shoes"), ("靴", "shoes"), ("帽", "hat"), ("眼镜", "glasses")]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def push(text: str, tag: str) -> None:
        t = text.strip().strip("。；;，,、").replace("**", "")
        if not (2 <= len(t) <= 40) or t in seen:
            return
        seen.add(t)
        out.append((f"item_{len(out) + 1}_{tag}", t))

    # ① 条目式
    for line in prompt.splitlines():
        raw = line.strip()
        if not raw.startswith(("-", "*", "•")):
            continue
        t = raw.lstrip("-*• ").strip()
        head = t.split("：", 1)[0]
        tag = next((en for k, en in cloth_keys if k in head), None)
        if not tag or any(w in head for w in body_words):
            continue
        val = t.split("：", 1)[1] if "：" in t else t
        for piece in val.split("，")[0].split("；")[0].split("、"): 
            push(piece, tag)
            break

    # ② 散文式：找带"穿/戴"的句子
    if not out:
        for sentence in prompt.replace("。", "。\n").splitlines():
            if not any(k in sentence for k in ("穿", "戴", "系")):
                continue
            for piece in sentence.replace("，", "、").replace("；", "、").split("、"):
                piece = piece.strip()
                if len(piece) < 2:
                    continue
                if any(w in piece for w in ("身穿", "穿着", "脚穿", "光脚", "戴着")):
                    piece = piece.split("穿", 1)[-1].split("戴", 1)[-1].strip()
                tag = next((en for k, en in cloth_keys if k in piece), "outfit")
                push(piece, tag)
            if len(out) >= 5:
                break
    return out[:5]

def build(prompt: str, seed: int, front_path: str, out_path: str,
          workdir: str, costume_items: list[tuple[str, str]] | None = None,
          progress=None, size: tuple[int, int] = (832, 1248)) -> str:
    """生成并拼成一张参考图，返回 out_path。costume_items=[(英文名, 中文描述)]

    size 是**每张视角图**的生成尺寸，由调用方按项目横竖屏传进来（默认 832×1248）。
    拼盘本身的输出比例由列数×格高决定，不会等于 size —— 它是一张多视角排版图。
    """
    os.makedirs(workdir, exist_ok=True)
    made: dict[str, str] = {}

    def step(msg: str) -> None:
        _log(msg)
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    for key, text in VIEWS.items():
        step(f"视角 {key}")
        p = _gen(_swap_pose(prompt, text), seed, f"canvas/refsheet/{key}", size=size)
        if p:
            made[key] = p
            cv2.imencode(".png", _read(p))[1].tofile(os.path.join(workdir, f"{key}.png"))
    for key, text in POSES.items():
        step(f"姿势 {key}")
        p = _gen(_swap_pose(prompt, text), seed, f"canvas/refsheet/{key}", size=size)
        if p:
            made[key] = p
            cv2.imencode(".png", _read(p))[1].tofile(os.path.join(workdir, f"{key}.png"))

    items = []
    # 抽不到服装就不放服装条——宁可没有，也别塞一张"通用套装"误导（用户反馈：每个角色都长一样）
    items_def = costume_items or costume_from_prompt(prompt) or []
    for key, zh in items_def:
        step(f"单品 {key}")
        p = _gen(f"{zh}，{COSTUME_TAIL}", seed + 1, f"canvas/refsheet/item_{key}", size=size)
        if p:
            items.append((key, _read(p)))
            cv2.imencode(".png", _read(p))[1].tofile(os.path.join(workdir, f"item_{key}.png"))

    if "right" not in made or "back" not in made:
        raise RuntimeError("右侧或背面没出图，无法拼盘")

    # 正面格：**优先用这次现生成的 front**，不拿旧主参考图，避免"删掉的图又出现在拼盘里"
    if "front" in made:
        front = _read(made["front"])
    elif front_path and os.path.isfile(front_path):
        front = _read(front_path)
        fh, fw = front.shape[:2]
        if fw / fh > 1.15:
            front = front[0:int(fh * 0.34), 0:int(fw * 0.25)]
    else:
        raise RuntimeError("正面图没生成出来")
    right = _read(made["right"])
    left = cv2.flip(right, 1)

    row1 = [_cell(front, "turnaround 正面"), _cell(left, "turnaround 左侧"),
            _cell(right, "turnaround 右侧"), _cell(_read(made["back"]), "turnaround 背面")]
    row2 = []
    for k, lab in (("stand", "poses 站"), ("sit", "poses 坐"), ("squat", "poses 蹲"), ("run", "poses 跑")):
        if k in made:
            row2.append(_cell(_read(made[k]), lab))
    rows = []
    for r in (row1, row2):
        while len(r) < 4:
            r.append(np.full_like(r[0], 20))
        rows.append(np.hstack(r))
    width = rows[0].shape[1]

    if items:
        band = np.full((CELL_H, width, 3), BAND_BG, np.uint8)
        slot = width // len(items)
        for i, (lab, img) in enumerate(items):
            t = _trim(img)
            ih, iw = t.shape[:2]
            s = (CELL_H - 50) / ih
            t = cv2.resize(t, (max(1, int(iw * s)), max(1, int(ih * s))))
            if t.shape[1] > slot - 24:
                s2 = (slot - 24) / t.shape[1]
                t = cv2.resize(t, (slot - 24, max(1, int(t.shape[0] * s2))))
            y0 = (CELL_H - t.shape[0]) // 2
            x0 = i * slot + (slot - t.shape[1]) // 2
            band[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t
            cv2.putText(band, lab, (i * slot + 10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 190, 190), 1)
        rows.append(band)

    sheet = np.vstack(rows)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imencode(".png", sheet)[1].tofile(out_path)
    step(f"拼好 {sheet.shape[1]}x{sheet.shape[0]}")
    return out_path
