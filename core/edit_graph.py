"""角色设定集的图像编辑图：Krea2 + Qwen-Image-Edit 编码器。

和 `krea2()` 的区别：这里挂参考图，模型是「照着参考图改构图」，不是凭空画。
所以提示词第一句必须写清楚要改成什么视角——只写形容词它不会动。
"""
from __future__ import annotations

import copy


def krea2_edit(ref_filename: str, prompt: str, *, seed: int, prefix: str,
               width: int = 1024, height: int = 1536, steps: int = 8,
               base: str = "moody", method: bool = False, lora: bool = True,
               lora_strength: float = 0.4, ref2_filename: str = "") -> dict:
    """base: moody（写实）= moodyKrea2Mix；turbo = krea2_turbo_fp8_scaled。

    实测矩阵（同参考图、同提示词、同种子，只改这三项）：

        | 变体 | 底模  | method | LoRA | 结果       |
        | A    | moody | 关     | 关   | 马赛克块   |
        | B    | moody | 开     | 关   | 马赛克块   |
        | C    | turbo | 开     | 开   | 干净       |
        | D    | turbo | 关     | 开   | 干净       |
        | E    | moody | 关     | 开   | 干净       |

    和结果唯一对齐的变量是 **LoRA**：没挂就出方块纹理，挂了就干净。
    method 不是变量（C 开着也干净，B 开着不干净，差别在 LoRA）。

    但 LoRA 强度直接决定"是不是同一个人"（同种子，front 视角）：
        0.4 → 保留参考图的人和猫，灰底干净
        0.7 → 猫消失，人换成另一个
        1.0 → 换成另一个人，雨衣细节也变了
    所以默认 0.4：够压掉方块纹理和背景，又不会把身份冲掉。
    """
    unet = ("krea2_turbo_fp8_scaled.safetensors" if base == "turbo"
            else "krea2_turbo_fp8_scaled.safetensors")
    g = {
        "78": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "79": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors",
                                                      "type": "krea2", "device": "default"}},
        "80": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "100": {"class_type": "LoadImage", "inputs": {"image": ref_filename}},
        "90": {"class_type": "TextEncodeQwenImageEditPlus",
               "inputs": {"clip": ["79", 0], "vae": ["80", 0], "image1": ["100", 0], "prompt": prompt}},        "81": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["79", 0], "text": ""}},
        "99": {"class_type": "ModelSamplingFlux",
               "inputs": {"model": ["78", 0], "max_shift": 1.15, "base_shift": 0.5,
                          "width": int(width), "height": int(height)}},
        "92": {"class_type": "CFGGuider", "inputs": {"model": ["99", 0], "positive": ["90", 0],
                                                     "negative": ["81", 0], "cfg": 1.0}},
        "98": {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}},
        "94": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "95": {"class_type": "BasicScheduler",
               "inputs": {"model": ["99", 0], "scheduler": "simple", "steps": int(steps), "denoise": 1.0}},
        "96": {"class_type": "EmptyLatentImage",
               "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
        "93": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["98", 0], "guider": ["92", 0], "sampler": ["94", 0],
                          "sigmas": ["95", 0], "latent_image": ["96", 0]}},
        "97": {"class_type": "VAEDecode", "inputs": {"samples": ["93", 0], "vae": ["80", 0]}},
        "732": {"class_type": "SaveImage", "inputs": {"images": ["97", 0], "filename_prefix": prefix}},
    }
    if ref2_filename:
        # 第二张参考图：例如「裸体素体 + 服装参考组」→ 生成穿衣版
        g["101"] = {"class_type": "LoadImage", "inputs": {"image": ref2_filename}}
        g["90"]["inputs"]["image2"] = ["101", 0]
    if lora:
        g["82"] = {"class_type": "LoraLoaderModelOnly",
                   "inputs": {"model": ["78", 0], "lora_name": "krea2_style_reference.safetensors",
                              "strength_model": float(lora_strength)}}
        g["99"]["inputs"]["model"] = ["82", 0]
    if method:
        g["91"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["90", 0],
                              "reference_latents_method": "index_timestep_zero"}}
        g["92"]["inputs"]["positive"] = ["91", 0]
    return g
