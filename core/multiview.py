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

from . import settings

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


# ---------------------------------------------------------------- 四视角参考表（sheet）

# 这个 LoRA 把一张参考图转成「脸特写 + 正面 + 侧面 + 背面」四格参考表。
# 触发句是它训练时的固定句式，删了就不出四格布局。
QUADVIEW_LORA = "QuadView_krea2_v1.safetensors"
QUADVIEW_TRIGGER = ("Convert the character in the image to a Character Sheet showing a face close-up, "
                    "front full body, side full body and back full body views")


def build_quadview_from_text(front_prompt: str, sheet_prompt: str, *, seed: int = 0,
                             unet: str = "", width: int = 1088, height: int = 1920,
                             steps: int = 8, sheet_steps: int = 10, ref_boost: float = 1.0,
                             prefix: str = "canvas/sheet/from_text") -> dict:
    """一次提交出整张四格表：前半段文生图，后半段用它自己的输出当 source_latent。

    整条链在一个图里，中间图不落盘、不返回，只有最后一张四格保存：

        UNET ─┬─ 文生图 ─ VAEDecode → ImageScale → VAEEncode → source_latent
              └─ QuadView LoRA → Krea2EditModelPatch → 采样 → 四格

    两段提示词分开编码（都从同一份人设拼出来）：第一段是「画风句 + 人设 + 构图尾巴」，
    第二段是「人设 + 四格触发句」。不共用一个文本节点，是因为把四格触发句塞进第一段
    会把正面图往拼版方向带，第一步就画歪。
    """
    unet = unet or settings.model("krea2_unet")
    g: dict = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": unet, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly",
              "inputs": {"model": ["1", 0], "lora_name": QUADVIEW_LORA, "strength_model": 1.0}},
        "3": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": settings.model("krea2_clip"), "type": "krea2",
                         "device": "default"}},
        "4": {"class_type": "VAELoader",
              "inputs": {"vae_name": settings.model("krea2_vae")}},

        # ---- 前半段：文生图出正面图（不保存）
        "20": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": front_prompt}},
        "21": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["20", 0]}},
        "22": {"class_type": "EmptyLatentImage",
               "inputs": {"width": int(width), "height": int(height), "batch_size": 1}},
        "23": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["1", 0], "positive": ["20", 0], "negative": ["21", 0],
                          "latent_image": ["22", 0], "add_noise": "enable",
                          "noise_seed": int(seed), "steps": int(steps), "cfg": 1.0,
                          "sampler_name": "euler_ancestral", "scheduler": "beta",
                          "start_at_step": 0, "end_at_step": int(steps),
                          "return_with_leftover_noise": "disable"}},
        "24": {"class_type": "VAEDecode", "inputs": {"samples": ["23", 0], "vae": ["4", 0]}},

        # ---- 后半段：拿前半段的图当 source_latent，出四格
        "30": {"class_type": "ImageScale",
               "inputs": {"image": ["24", 0], "upscale_method": "lanczos",
                          "width": 1024, "height": 1024, "crop": "center"}},
        "31": {"class_type": "VAEEncode", "inputs": {"pixels": ["30", 0], "vae": ["4", 0]}},
        "32": {"class_type": "Krea2EditModelPatch",
               "inputs": {"model": ["2", 0], "source_latent": ["31", 0],
                          "source_image": ["30", 0], "vae": ["4", 0],
                          "ref_boost": float(ref_boost), "fit_mode": "fit",
                          "ref_position": "aligned (trained)"}},
        "33": {"class_type": "Krea2EditGroundedEncode",
               "inputs": {"clip": ["3", 0], "prompt": sheet_prompt, "image": ["30", 0],
                          "grounding_px": 768}},
        "34": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["3", 0], "text": ""}},
        "35": {"class_type": "EmptySD3LatentImage",
               "inputs": {"width": 1536, "height": 1024, "batch_size": 1}},
        "36": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["32", 0], "positive": ["33", 0], "negative": ["34", 0],
                          "latent_image": ["35", 0], "add_noise": "enable",
                          "noise_seed": int(seed) + 1, "steps": int(sheet_steps), "cfg": 1.0,
                          "sampler_name": "euler", "scheduler": "simple",
                          "start_at_step": 0, "end_at_step": int(sheet_steps),
                          "return_with_leftover_noise": "disable"}},
        "37": {"class_type": "VAEDecode", "inputs": {"samples": ["36", 0], "vae": ["4", 0]}},
        "38": {"class_type": "SaveImage",
               "inputs": {"images": ["37", 0], "filename_prefix": prefix}},
    }
    return g
