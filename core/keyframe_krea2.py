# -*- coding: utf-8 -*-
"""镜头首帧：Krea2 + krea2_identity_edit_v2 双参考。

为什么不复用 multiview.build_edit：
  那套是 Qwen-Image-Edit 2511 + 多角度 LoRA + 4 步 Lightning，本职是
  「同一角色转几个角度」的设定图。拿它演镜头，它只会照着参考图摆桩，
  人物和背景是两张皮（它不声明背景怎么来）。

为什么不复用 edit_graph.krea2_edit：
  那套挂的是 krea2_style_reference LoRA，做设定集改视角用的；锁人靠的是
  krea2_identity_edit_v2，两者不是同一个 LoRA，不能混。

接线与参数：
  UNETLoader → LoraLoaderModelOnly(identity) → Krea2EditModelPatch.model
  LoadImage → ImageScale → VAEEncode → Krea2EditModelPatch.source_latent
  角色图 + 场景图 → Krea2EditGroundedEncode.image / image_b
  ref_position 三档：aligned 钉死构图姿势 / beside 可换但人偏右 /
                     bag of features 居中且姿势自由
  首帧用 aligned：镜头要的是「这一镜的构图」，让模型自由重建会自己补道具。

权重名一律走 settings.model()，不写死：换机器、换量化档都能用；
查不到就回落到默认值，别让首帧因为一个文件名报错。
"""
from __future__ import annotations

from . import settings

UNET = settings.model("krea2_unet") or "krea2_turbo_fp8_scaled.safetensors"
CLIP = settings.model("krea2_clip") or "qwen3vl_4b_fp8_scaled.safetensors"
VAE = settings.model("krea2_vae") or "qwen_image_vae.safetensors"
# 这个 LoRA 在 DEFAULT_MODELS 里没有登记，所以走"设置里填了就覆盖"的写法：
# 没填就用约定文件名，填了就用设置里的。
LORA_IDENTITY = settings.model("krea2_identity_lora") or "krea2_identity_edit_v2.safetensors"

REF_POSITIONS = ("aligned (trained)", "beside (right of target)", "bag of features")


def _fit(w: int, h: int, long_edge: int = 1024) -> tuple[int, int]:
    """参考图等比缩到长边 long_edge，并对齐 8 的倍数。"""
    if max(w, h) <= long_edge:
        return max(64, int(w) // 8 * 8), max(64, int(h) // 8 * 8)
    k = long_edge / max(w, h)
    return max(64, int(round(w * k)) // 8 * 8), max(64, int(round(h * k)) // 8 * 8)


def build(char_file: str, scene_file: str, prompt: str, *, seed: int,
          width: int, height: int, prefix: str,
          char_size: tuple[int, int] = (1024, 1024),
          scene_size: tuple[int, int] = (1344, 768),
          ref_position: str = "aligned (trained)",
          ref_boost: float = 2.0, steps: int = 12) -> dict:
    """char_file / scene_file：已上传到 ComfyUI input 的文件名。

    char_size / scene_size：两张参考图的原始像素，用来算 ImageScale 的尺寸
    （传错只是参考图缩放不准，不会崩）。scene_file 传空串则只用角色单参考。
    """
    if ref_position not in REF_POSITIONS:
        raise ValueError(f"ref_position 只能是 {REF_POSITIONS}，收到 {ref_position!r}")
    cw, ch = _fit(*char_size)
    sw, sh = _fit(*scene_size, long_edge=1344)

    g: dict = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": LORA_IDENTITY,
                         "strength_model": 1.0}},
        "4": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "krea2", "device": "default"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},

        # 参考 1：角色（锁人）
        "12": {"class_type": "LoadImage", "inputs": {"image": char_file}},
        "10": {"class_type": "ImageScale",
               "inputs": {"image": ["12", 0], "upscale_method": "lanczos",
                          "width": cw, "height": ch, "crop": "disabled"}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["7", 0]}},

        "3": {"class_type": "Krea2EditModelPatch",
              "inputs": {"model": ["2", 0],
                         "source_latent": ["11", 0], "source_image": ["10", 0],
                         "vae": ["7", 0], "ref_boost": float(ref_boost),
                         "fit_mode": "fit", "ref_position": ref_position}},

        "30": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["4", 0], "prompt": prompt,
                          "image": ["10", 0], "grounding_px": 768}},
        "31": {"class_type": "CLIPTextEncode",
               "inputs": {"clip": ["4", 0], "text": ""}},

        "40": {"class_type": "EmptyLatentImage",
               "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
        "41": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["3", 0], "positive": ["30", 0], "negative": ["31", 0],
                          "latent_image": ["40", 0], "add_noise": "enable",
                          "noise_seed": int(seed), "steps": int(steps), "cfg": 1.0,
                          "sampler_name": "euler_ancestral", "scheduler": "beta",
                          "start_at_step": 0, "end_at_step": int(steps),
                          "return_with_leftover_noise": "enable"}},
        "42": {"class_type": "VAEDecode", "inputs": {"samples": ["41", 0], "vae": ["7", 0]}},
        "43": {"class_type": "SaveImage",
               "inputs": {"images": ["42", 0], "filename_prefix": prefix}},
    }

    if scene_file:
        g["22"] = {"class_type": "LoadImage", "inputs": {"image": scene_file}}
        g["20"] = {"class_type": "ImageScale",
                   "inputs": {"image": ["22", 0], "upscale_method": "lanczos",
                              "width": sw, "height": sh, "crop": "disabled"}}
        g["21"] = {"class_type": "VAEEncode",
                   "inputs": {"pixels": ["20", 0], "vae": ["7", 0]}}
        g["3"]["inputs"].update(source_latent_b=["21", 0], source_image_b=["20", 0])
        g["30"]["inputs"].update(image_b=["20", 0])
    return g
