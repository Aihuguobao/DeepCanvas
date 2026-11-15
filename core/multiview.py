"""多角度设定图：Qwen-Image-Edit 2511 + fal 多角度 LoRA。

接线和提示词格式都来自 ComfyTV 的 multiview / multiangle 工作流（同作者、同模型栈）：
  https://github.com/jtydhr88/comfytv/blob/main/workflows/multiview/README.zh.md

要点（照抄，别自创）：
  1. 一张源图 → N 条并行分支，**一次提交跑完**，model/clip/vae/latent 全部共享；
  2. 每条分支只换提示词，格式固定：`<sks> [方位角] [俯仰] [距离], [补充说明]`
  3. 采样固定 4 步、cfg 1.0、euler、simple，靠 Lightning LoRA 撑住；
  4. 输出用源图尺寸回缩，方便拼设定集。
"""
from __future__ import annotations

AZIMUTH = {
    "front": "front view",
    "front_right": "front-right quarter view",
    "right": "right side view",
    "back_right": "back-right quarter view",
    "back": "back view",
    "back_left": "back-left quarter view",
    "left": "left side view",
    "front_left": "front-left quarter view",
}
ELEVATION = {
    "low": "low-angle shot",
    "eye": "eye-level shot",
    "elevated": "elevated shot",
    "high": "high-angle shot",
}
DISTANCE = {"close": "close-up", "medium": "medium shot", "wide": "wide shot"}

UNET = "qwen_image_edit_2511_fp8mixed.safetensors"
CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"
LORA_ANGLES = "qwen-image-edit-2511-multiple-angles-lora.safetensors"
LORA_LIGHTNING = "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"


def angle_prompt(azimuth: str = "front", elevation: str = "eye", distance: str = "wide",
                 extra: str = "full body, plain light grey background, no text, no annotations") -> str:
    a = AZIMUTH.get(azimuth, azimuth)
    e = ELEVATION.get(elevation, elevation)
    d = DISTANCE.get(distance, distance)
    return f"<sks> {a} {e} {d}, {extra}" if extra else f"<sks> {a} {e} {d}"


def build_edit(images: list[str], prompt: str, *, seed: int = 0, width: int = 832,
               height: int = 1248, steps: int = 4, cfg: float = 1.0,
               prefix: str = "edit") -> dict:
    """多参考图生成一张（镜头首帧用）：image1..3 分别是角色/场景/道具参考。

    TextEncodeQwenImageEditPlus 本身支持 image1..3，不需要拼图——
    拼成一张大图会被模型当成"多个人"（实测记录里写过）。
    """
    if not images:
        raise ValueError("至少要一张参考图")
    g: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": LORA_ANGLES, "strength_model": 1.0}},
        "3": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["2", 0], "lora_name": LORA_LIGHTNING, "strength_model": 1.0}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["3", 0], "shift": 3.1}},
        "5": {"class_type": "CFGNorm", "inputs": {"model": ["4", 0], "strength": 1.0}},
        "6": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "default"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "11": {"class_type": "GetImageSize", "inputs": {"image": ["20", 0]}},
    }
    enc_inputs: dict = {"clip": ["6", 0], "vae": ["7", 0], "prompt": prompt}
    for i, name in enumerate(images[:3]):
        nid = str(20 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        enc_inputs[f"image{i + 1}"] = [nid, 0]
    g["30"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": enc_inputs}
    g["31"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["30", 0], "reference_latents_method": "index"}}
    # 负向：空提示词，同样挂参考图
    neg_inputs = dict(enc_inputs, prompt="")
    g["32"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": neg_inputs}
    g["33"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["32", 0], "reference_latents_method": "index"}}
    g["40"] = {"class_type": "EmptyLatentImage",
               "inputs": {"width": int(width), "height": int(height), "batch_size": 1}}
    g["41"] = {"class_type": "KSampler",
               "inputs": {"model": ["5", 0], "positive": ["31", 0], "negative": ["33", 0],
                          "latent_image": ["40", 0], "seed": int(seed), "steps": int(steps),
                          "cfg": float(cfg), "sampler_name": "euler", "scheduler": "simple",
                          "denoise": 1.0}}
    g["42"] = {"class_type": "VAEDecode", "inputs": {"samples": ["41", 0], "vae": ["7", 0]}}
    g["43"] = {"class_type": "SaveImage",
               "inputs": {"images": ["42", 0], "filename_prefix": prefix}}
    return g


def three_view_prompts(extra: str = "full body, plain light grey background, no text, no annotations") -> list[tuple[str, str]]:
    """返回 [(标签, 提示词)]。正面/右侧/背面是最小可用集。"""
    return [
        ("front", angle_prompt("front", "eye", "wide", extra)),
        ("side", angle_prompt("right", "eye", "wide", extra)),
        ("back", angle_prompt("back", "eye", "wide", extra)),
    ]


def nine_cam_prompts(extra: str = "full body, plain light grey background, no text, no annotations") -> list[tuple[str, str]]:
    """每 45° 一个方位角，全部平视中景。"""
    order = ["front", "front_right", "right", "back_right", "back", "back_left", "left", "front_left"]
    return [(k, angle_prompt(k, "eye", "medium", extra)) for k in order]


def build(ref_filename: str, prompts: list[tuple[str, str]], *, seed: int = 0,
          steps: int = 4, cfg: float = 1.0, prefix: str = "multiview",
          save_prefix: str = "", width: int = 0, height: int = 0) -> dict:
    """prompts: [(标签, 提示词)]，每个标签一条分支，一次提交全出。

    width/height 填了就用固定尺寸（半身图要出全身时用竖版），
    不填就跟源图走（默认，和 ComfyTV 工作流一致）。
    """
    g: dict = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": LORA_ANGLES, "strength_model": 1.0}},
        "3": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["2", 0], "lora_name": LORA_LIGHTNING, "strength_model": 1.0}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["3", 0], "shift": 3.1}},
        "5": {"class_type": "CFGNorm", "inputs": {"model": ["4", 0], "strength": 1.0}},
        "6": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "qwen_image", "device": "default"}},
        "7": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "8": {"class_type": "LoadImage", "inputs": {"image": ref_filename}},
        "9": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["8", 0]}},
        "10": {"class_type": "VAEEncode", "inputs": {"pixels": ["9", 0], "vae": ["7", 0]}},
        "11": {"class_type": "GetImageSize", "inputs": {"image": ["8", 0]}},
    }
    # 负向：同一条空提示词，也要过参考图编码
    g["12"] = {"class_type": "TextEncodeQwenImageEditPlus",
               "inputs": {"clip": ["6", 0], "vae": ["7", 0], "image1": ["9", 0], "prompt": ""}}
    g["13"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
               "inputs": {"conditioning": ["12", 0], "reference_latents_method": "index"}}

    for i, (label, prompt) in enumerate(prompts):
        base = 100 + i * 10
        enc, ref, ks, dec, scale, save = (str(base + k) for k in range(6))
        g[enc] = {"class_type": "TextEncodeQwenImageEditPlus",
                  "inputs": {"clip": ["6", 0], "vae": ["7", 0], "image1": ["9", 0], "prompt": prompt}}
        g[ref] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                  "inputs": {"conditioning": [enc, 0], "reference_latents_method": "index"}}
        g[ks] = {"class_type": "KSampler",
                 "inputs": {"model": ["5", 0], "positive": [ref, 0], "negative": ["13", 0],
                            "latent_image": ["10", 0], "seed": int(seed) + i, "steps": int(steps),
                            "cfg": float(cfg), "sampler_name": "euler", "scheduler": "simple",
                            "denoise": 1.0}}
        g[dec] = {"class_type": "VAEDecode", "inputs": {"samples": [ks, 0], "vae": ["7", 0]}}
        scale_args = {"image": [dec, 0], "upscale_method": "lanczos", "crop": "disabled"}
        if width and height:
            scale_args["width"] = int(width)
            scale_args["height"] = int(height)
        else:
            scale_args["width"] = ["11", 0]
            scale_args["height"] = ["11", 1]
        g[scale] = {"class_type": "ImageScale", "inputs": scale_args}
        g[save] = {"class_type": "SaveImage",
                   "inputs": {"images": [scale, 0],
                              "filename_prefix": f"{prefix}/{save_prefix or ''}{i:02d}_{label}"}}
    return g
