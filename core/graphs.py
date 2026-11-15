"""引擎图：加载 templates、按类名注入参数。

设计约束：**不写死节点号**。所有定位都按 class_type 找，模板换一版也不用改这里。
"""
from __future__ import annotations

import copy
import json
import os

from . import comfy, settings

ENGINES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engines")

FPS = 24
H3_GRID = 17          # H3: 17k+5


def load(engine: str) -> dict:
    path = os.path.join(ENGINES, f"{engine}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"没有引擎模板 {path}")
    with open(path, encoding="utf-8") as f:
        return copy.deepcopy(json.load(f))


def find(graph: dict, class_type: str) -> list[str]:
    return [nid for nid, n in graph.items() if n.get("class_type") == class_type]


_SAGE_NODE = "PathchSageAttentionKJ"
_sage_ok: bool | None = None


def sage_available() -> bool:
    """KJNodes 的 sage 补丁节点在不在。查一次就缓存，避免每次出片都打接口。"""
    global _sage_ok
    if _sage_ok is None:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{comfy.base()}/object_info/{_SAGE_NODE}", timeout=15) as r:
                _sage_ok = _SAGE_NODE in json.load(r)
        except Exception:  # noqa: BLE001 - 查不到就当没有，出片退回 SDPA
            _sage_ok = False
    return bool(_sage_ok)


def apply_h3_turbo(graph: dict, *, sigma_video: float = 12.0, sigma_audio: float = 6.0,
                   spectrum: bool = True, sampler: str = "er_sde") -> dict:
    """给 H3 采样链插上 turbo 专用调度（对照官方高级工作流）。

    我们简易图一直缺这三样，导致 turbo 4 步出来是"抽象图"：
      1) MiniMaxH3SigmaShift(12,6) —— turbo LoRA 必需的 sigma 位移
      2) SpectrumApplyMiniMaxH3 —— 压掉少步数的高频糊块
      3) KSamplerSelect → er_sde —— 官方高级流用的采样器
    插入点：LoRA/Sage 之后、BasicGuider / BasicScheduler 之前（它们共用 model 输入）。
    """
    hosts = find(graph, "BasicGuider") + find(graph, "BasicScheduler")
    if not hosts:
        return graph
    cur = graph[hosts[0]]["inputs"].get("model")
    nid = "996"
    graph[nid] = {"class_type": "MiniMaxH3SigmaShift",
                  "inputs": {"model": cur, "shift_video": float(sigma_video),
                             "shift_audio": float(sigma_audio)}}
    if spectrum:
        nid2 = "997"
        graph[nid2] = {"class_type": "SpectrumApplyMiniMaxH3",
                       "inputs": {"model": [nid, 0], "enabled": True, "blend_weight": 0.5,
                                  "degree": 4, "ridge_lambda": 0.1, "window_size": 2.0,
                                  "flex_window": 0.75, "warmup_steps": 5, "tail_actual_steps": 1,
                                  "max_history": 8, "debug": False, "history_storage": "system_ram",
                                  "bootstrap_first_forecast": False}}
        cur = [nid2, 0]
    else:
        cur = [nid, 0]
    for h in hosts:
        if isinstance(graph[h]["inputs"].get("model"), list):
            graph[h]["inputs"]["model"] = cur
    sel = find(graph, "KSamplerSelect")
    if sel:
        graph[sel[0]]["inputs"]["sampler_name"] = sampler
    print(f"  turbo 调度：SigmaShift({sigma_video},{sigma_audio}) + Spectrum={spectrum} + {sampler}")
    return graph


def _drop_lora(graph: dict) -> dict:
    """摘掉所有 LoraLoaderModelOnly，把它的下游改接到上游模型。
    用于高步数（>12）时避开 8 步 turbo LoRA —— 挂着它跑 20 步会过火。"""
    for lid in find(graph, "LoraLoaderModelOnly"):
        up = graph[lid]["inputs"].get("model")
        for node in graph.values():
            for k, v in list((node.get("inputs") or {}).items()):
                if isinstance(v, list) and len(v) == 2 and str(v[0]) == str(lid):
                    node["inputs"][k] = up
        graph.pop(lid, None)
    return graph


def apply_sage(graph: dict, value: str = "auto") -> dict:
    """在 BasicGuider / BasicScheduler 前插一个 sage 注意力补丁。

    实测（H3 FL2VA，5 秒 8 步 1344×768）：
      SDPA 448.9s → SageAttention(auto) 201.1s，**提速 55.2%**；
      帧差 16.59→16.76、边缘 1.25→1.24，画质无可见变化。
    value 可取 disabled / auto / sageattn_qk_int8_pv_fp16_cuda / …（见节点选项）。
    """
    if not value or str(value).lower() == "disabled":
        return graph
    hosts = find(graph, "BasicGuider") + find(graph, "BasicScheduler")
    if not hosts:
        return graph
    if not sage_available():
        print("  ! 没装 PathchSageAttentionKJ，忽略加速，按要求走 SDPA")
        return graph
    model_ref = graph[hosts[0]]["inputs"].get("model")
    # 不能写死 "995"：latent 桥接那套自己用了 990–995，会被这里覆盖掉，
    # 结果 CreateVideo.images 指向一个 MODEL 节点
    _sid = 9001
    while str(_sid) in graph:
        _sid += 1
    sage_id = str(_sid)
    graph[sage_id] = {"class_type": _SAGE_NODE,
                    "inputs": {"model": model_ref, "sage_attention": str(value),
                               "allow_compile": False}}
    for nid in hosts:
        if isinstance(graph[nid]["inputs"].get("model"), list):
            graph[nid]["inputs"]["model"] = [sage_id, 0]
    return graph


def strip_sage(graph: dict) -> bool:
    """把 sage 补丁节点从图里摘掉（谁用它的输出就改回用它的输入 model）。

    为什么要这个：那台 ComfyUI 装了 KJNodes 但没装 sageattention 模块时，
    节点注册得上（`sage_available()` 返回 True），一执行到 patch 才
    `ModuleNotFoundError: No module named 'sageattention'`。
    摘掉重提能出片，只是慢一半。
    """
    ids = [k for k, v in graph.items() if str(v.get("class_type")) == _SAGE_NODE]
    if not ids:
        return False
    for sid in ids:
        src = (graph.get(sid) or {}).get("inputs", {}).get("model")
        if isinstance(src, list):
            for node in graph.values():
                inputs = node.get("inputs") or {}
                for key, val in list(inputs.items()):
                    if isinstance(val, list) and len(val) == 2 and val[0] == sid:
                        inputs[key] = src
        graph.pop(sid, None)
    return True


def _comfy_root() -> str:
    """ComfyUI 根目录：问 core.settings（设置面板 > COMFY_DIR > 从 _agent 往上找）。"""
    from . import settings
    return settings.comfy_root()


def one(graph: dict, class_type: str) -> dict:
    ids = find(graph, class_type)
    if not ids:
        raise KeyError(f"模板里没有 {class_type}")
    return graph[ids[0]]


def set_inputs(graph: dict, class_type: str, **kv) -> dict:
    node = one(graph, class_type)
    node["inputs"].update(kv)
    return node


def link(graph: dict, from_id: str, from_slot: int, into_class: str, field: str) -> None:
    one(graph, into_class)["inputs"][field] = [from_id, from_slot]


# ---------------------------------------------------------------- 帧数换算
def h3_frames(seconds: float) -> int:
    n = max(5, round(seconds * FPS))
    return n + ((5 - n % H3_GRID) % H3_GRID)


# ---------------------------------------------------------------- 生图
def krea2(prompt: str, *, seed: int, prefix: str, width: int = 0, height: int = 0,
          megapixels: float = 2.0, aspect: str = "9:16 (Portrait Widescreen)",
          steps: int = 8) -> dict:
    g = load("krea2")
    set_inputs(g, "CLIPTextEncode", text=prompt)
    set_inputs(g, "KSamplerAdvanced", noise_seed=int(seed), steps=int(steps))
    set_inputs(g, "SaveImage", filename_prefix=prefix)
    if width and height:
        # 固定尺寸：绕开 ResolutionSelector，直接给 latent
        set_inputs(g, "EmptyLatentImage", width=int(width), height=int(height), batch_size=1)
    else:
        set_inputs(g, "ResolutionSelector", aspect_ratio=aspect, megapixels=float(megapixels))
    return g


# ---------------------------------------------------------------- H3
LATENT_DIR = "片子/{ep}/{scene}/续镜/lat"        # 续镜 latent 目录（与手工跑的一致）

def _pick_h3_weights(kind: str) -> tuple[str, str]:
    """按用途挑 H3 权重：ref2va 图和 fl2va 图用的不是同一个 checkpoint。

    官方技能包原话：Ref2VA "runs on the ref2va checkpoint"。
    拿 fl2va 的权重跑 ReferenceToVideo，参考图基本不生效（实测：人、场景全跑掉）。
    返回 (unet_name, lora_name)，lora_name 为空表示不加。
    """
    try:
        info = comfy.object_info("UNETLoader")
        unets = info["UNETLoader"]["input"]["required"]["unet_name"][0] or []
    except Exception as exc:  # noqa: BLE001 - 离线时不该打断构图，但要出声
        print(f"  ! 查不到 UNETLoader 列表（{type(exc).__name__}: {exc}）")
        unets = []
    try:
        linfo = comfy.object_info("LoraLoaderModelOnly")
        loras = linfo["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0] or []
    except Exception as exc:  # noqa: BLE001
        print(f"  ! 查不到 LoRA 列表（{type(exc).__name__}: {exc}）")
        loras = []

    if kind == "ref2va":
        unet = (next((n for n in unets if "ref2va" in n and "int8" in n), "")
                or next((n for n in unets if "ref2va" in n), ""))
        lora = (next((n for n in loras if "ref2v" in n and "8step" in n), "")
                or next((n for n in loras if "ref2v" in n and "turbo" in n), "")
                or next((n for n in loras if "ref2v" in n), ""))
    else:
        unet = next((n for n in unets if "fl2va" in n and "int8" in n), "")
        lora = next((n for n in loras if "fl2v" in n and "turbo" in n), "")
    return unet, lora


def h3_ref(*, ref_images: list[str], prompt: str, seconds: float, width: int, height: int,
           seed: int, prefix: str, steps: int = 0, ref_size: str = "max",
           guide_images: list | None = None,
           ref_videos: list | None = None, guide_clips: list | None = None,
           ref_audios: list | None = None,
           relay: dict | None = None,
           lora_extra: str = "", lora_extra_strength: float = 0.9,
           lora_main: str = "",
           lora_strength: float = 0.6, sampler: str = "er_sde", scheduler: str = "beta",
           turbo_patch: bool = False,   # 查证：社区工作流里这两个节点是禁用(mode=4)的
           sigma_video: float = 12.0, sigma_audio: float = 6.0, spectrum: bool = False,
           interpolate: bool = False, crf: int = 14, sage: str = "auto",
           control_video: str = "", control_mode: str = "pose",
           control_strength: float = 1.0, model: str = "",
           lowvram: bool = False) -> dict:
    """Ref2VA：多参考图 → 音视频。

    和 h3() 共用同一条采样链，只把 `MiniMaxH3ImageToVideo` 换成
    `MiniMaxH3ReferenceToVideo`。该节点的 ref_images 是 autogrow 字典，
    键名 `ref_image_0..8`，值指向 LoadImage。
    提示词里用 `<Picture 1>` / `<Picture 2>` 指代，序号从 1 开始。
    """
    if not ref_images:
        raise ValueError("Ref2VA 至少要一张参考图")
    g = load("h3")
    # 模板自带的那张 LoadImage 改成参考图 0，其余按需补
    host_id = find(g, "LoadImage")[0]
    refs = {}
    for i, name in enumerate(ref_images[:9]):
        nid = host_id if i == 0 else str(900 + i)
        if i == 0:
            g[nid]["inputs"]["image"] = name
        else:
            g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        refs[f"ref_image_{i}"] = [nid, 0]

    # 参考音频（音色锁定）：官方跨镜锁音色的手段是 `<Audio N>`，节点 ref_audios 最多 3 段。
    # 注意 audio_vae 必须接上，否则节点 tooltip 说得很清楚：参考音频只会去影响文本编码器，进不了音频 latent。
    aud_refs = {}
    for i, name in enumerate((ref_audios or [])[:3]):
        nid = str(930 + i)
        g[nid] = {"class_type": "LoadAudio", "inputs": {"audio": name}}
        aud_refs[f"ref_audio_{i}"] = [nid, 0]

    # 关键：换成 ref2va 的权重。没有就用模板默认（fl2va），并明确警告
    if lowvram:
        # 8 GB 显存方案（社区实测）：W4A8 主模型（11.7 GiB）+ Qwen3-VL 4B 编码器（4.9 GB）
        # + ClipProj 投影矩阵。CLIPLoader 要改成 krea2 类型，输出再经 ClipProjApply 投影回 5120 维。
        unet, lora = settings.model("w4a8_unet"), ""
        _uids = find(g, "UNETLoader")
        if _uids:
            g[_uids[0]]["inputs"]["unet_name"] = unet
        _cids = find(g, "CLIPLoader")
        if _cids:
            _cid = _cids[0]
            g[_cid]["inputs"]["clip_name"] = settings.model("w4a8_clip")
            g[_cid]["inputs"]["type"] = "krea2"
            _pid = 9100
            while str(_pid) in g:
                _pid += 1
            _proj_id = str(_pid)
            g[_proj_id] = {"class_type": "ClipProjApply",
                           "inputs": {"clip": [_cid, 0],
                                      "projection": settings.model("w4a8_proj")}}
            # 所有原本吃 CLIPLoader 的地方改吃投影节点（投影节点自己的 clip 输入不能改）
            for _nid, _node in g.items():
                if str(_nid) == _proj_id:
                    continue
                for _k, _v in list((_node.get("inputs") or {}).items()):
                    if isinstance(_v, list) and len(_v) == 2 and str(_v[0]) == str(_cid):
                        _node["inputs"][_k] = [_proj_id, 0]
            print(f"  模型档位：W4A8 低显存  unet={unet}")
            print(f"    clip={settings.model('w4a8_clip')}（type=krea2）→ ClipProj {settings.model('w4a8_proj')}")
        for lid in list(find(g, "LoraLoaderModelOnly")):
            src = (g.get(lid) or {}).get("inputs", {}).get("model")
            for node in g.values():
                for k, v in list((node.get("inputs") or {}).items()):
                    if isinstance(v, list) and len(v) == 2 and str(v[0]) == str(lid):
                        node["inputs"][k] = src
            g.pop(lid, None)
        print("  （W4A8 档不挂 turbo LoRA：按 20 步 + euler + simple 跑）")
        if not steps:
            steps = 20
        unet_id, lora_id = None, []
    else:
        unet, lora = _pick_h3_weights("ref2va")
        # 只走官方 ref2va 权重（_pick_h3_weights 按关键词从 ComfyUI 实际清单里匹配）。
        if unet:
            print(f"  模型：{unet}")
        # 指定主 LoRA 时覆盖自动选择（用于对比 4step / 8step 等不同加速档）
        if lora_main:
            lora = lora_main
        _uids = find(g, "UNETLoader")
        unet_id = _uids[0] if _uids else None
        if unet_id and unet:
            g[unet_id]["inputs"]["unet_name"] = unet
        elif not unet:
            print("⚠ 没有 ref2va 权重：参考图不会真正生效，请下载 minimax_h3_ref2va_pruned_int8_convrot.safetensors")
        lora_id = find(g, "LoraLoaderModelOnly")
        _base = [unet_id, 0] if unet_id else None
        if lora_id and lora:
            # 只走 turbo 路径（25 步全量已废弃）：挂 turbo LoRA，步数按 LoRA 名定
            g[lora_id[0]]["inputs"]["lora_name"] = lora
            if not steps:
                steps = 4 if "4step" in lora else (8 if "8step" in lora else 8)
            elif int(steps) > 12 and _base:
                # 步数明显超过 turbo 的训练档（8 步）时，turbo LoRA 会过火 → 摘掉走原生采样
                for node in g.values():
                    for k, v in list((node.get("inputs") or {}).items()):
                        if isinstance(v, list) and len(v) == 2 and str(v[0]) == str(lora_id[0]):
                            node["inputs"][k] = _base
                for nid in lora_id:
                    g.pop(nid, None)
                print(f"  高步数 {steps}：已摘 turbo LoRA，走原生采样")
            print(f"  turbo：{steps} 步、LoRA={lora if lora_id and lora_id[0] in g else '（已摘）'}")
        elif lora_id:
            # 没装 ref2v turbo LoRA：摘掉模板里硬编码的 fl2v LoRA，避免串权重
            if _base:
                for node in g.values():
                    for k, v in list((node.get("inputs") or {}).items()):
                        if isinstance(v, list) and len(v) == 2 and str(v[0]) == str(lora_id[0]):
                            node["inputs"][k] = _base
            for nid in lora_id:
                g.pop(nid, None)
            print("  ⚠ 没装 ref2v turbo LoRA，已摘 LoRA 节点（画质会差）")
    if not steps:
        steps = 8

    # 实测结论（ECC 仿射测量，同提示词同种子同背景）：
    #   turbo LoRA 强度 1.0 -> 横移 244~267 px；0.6 -> 52 px（推近 7.7%）
    #   采样器 res_multistep -> er_sde 再减一半；调度器 simple -> beta 同步
    #   所以这里默认用 0.6 + er_sde + beta；要运镜时另挂 lora_extra。
    for _nid in find(g, "LoraLoaderModelOnly"):
        g[_nid]["inputs"]["strength_model"] = float(lora_strength)
    for _nid in find(g, "KSamplerSelect"):
        g[_nid]["inputs"]["sampler_name"] = sampler
    for _nid in find(g, "BasicScheduler"):
        g[_nid]["inputs"]["scheduler"] = scheduler
        try:
            g[_nid]["inputs"]["steps"] = int(steps) if steps else 8
        except Exception:
            pass

    # 非蒸馏档（推荐 20–25 步）必须摘掉 turbo LoRA，
    # 挂着它跑 25 步会过火（画面死黑/糊）。h3_ref 以前没有这个保护，补上。
    if steps and int(steps) > 12:
        _drop_lora(g)
        print(f"  高步数 {int(steps)}：已摘 turbo LoRA，走非蒸馏采样")

    # 社区工作流（H3 高级全家桶）里有两件我们漏了的东西——
    #   MiniMaxH3SigmaShift(12,6)：turbo LoRA 必需的 sigma 位移
    #   SpectrumApplyMiniMaxH3：压少步数的高频糊块
    # 缺了它们等于在错位的 sigma 调度上采样，画面/运镜都会乱。
    # 非蒸馏档（>12 步）也要 SigmaShift：Shift Video 10-12 / Audio 3-5，
    # 不挂的话画面死黑。所以这里按「turbo 补丁」或「高步数」任一条件挂上。
    if turbo_patch or (steps and int(steps) > 12):
        try:
            apply_h3_turbo(g, sigma_video=float(sigma_video), sigma_audio=float(sigma_audio),
                           spectrum=bool(spectrum), sampler=sampler)
        except Exception as _exc:      # 节点不存在时不要整条挂掉
            print(f"  ! turbo 补丁没挂上（{type(_exc).__name__}: {_exc}）")

    # 额外运镜 LoRA（如 camera_motion_h3_lora_v1）：串在 turbo 之后，改 Guider 的 model 来源
    if lora_extra:
        prev = str(lora_id[0]) if lora_id else str(unet_id)
        g["952"] = {"class_type": "LoraLoaderModelOnly",
                    "inputs": {"model": [prev, 0], "lora_name": lora_extra,
                               "strength_model": float(lora_extra_strength)}}
        for node in g.values():
            for k, v in list((node.get("inputs") or {}).items()):
                if isinstance(v, list) and len(v) == 2 and str(v[0]) == prev and node.get("class_type") in ("BasicGuider",):
                    node["inputs"][k] = ["952", 0]
        print(f"  运镜 LoRA：{lora_extra} @{lora_extra_strength}")

    node = g[find(g, "MiniMaxH3ImageToVideo")[0]]
    node["class_type"] = "MiniMaxH3ReferenceToVideo"
    node["inputs"].pop("first_frame", None)
    node["inputs"].pop("last_frame", None)
    node["inputs"].update({
        "prompt": prompt,
        "width": int(width),
        "height": int(height),
        "length": h3_ref_frames(seconds),
        "ref_image_size": ref_size,
        # autogrow 输入在 API 里是点号键：ref_images.ref_image_0
        # 传嵌套字典不会被识别，节点收到空的 ref_images（参考图等于没传）
        **{f"ref_images.{k}": v for k, v in refs.items()},
        # 参考音频同样用点号键；audio_vae 接上才真正进音频 latent
        **{f"ref_audios.{k}": v for k, v in aud_refs.items()},
        "audio_vae": ["120", 0],
    })
    set_inputs(g, "RandomNoise", noise_seed=int(seed))
    set_inputs(g, "BasicScheduler", steps=int(steps))
    set_inputs(g, "SaveVideo", filename_prefix=prefix)

    # ---- 路线 B：latent 桥接（ComfyUI-H3-Latent-Relay）
    # 接法照抄该包 examples/seed_from_video_ui.json：
    #   上一段 mp4 → SeedFromVideo(stage-1) → 桥(context_latent)
    #   桥.latent → 采样器；桥.conditioning → guider；桥.trim_frames → TrimAV
    #   采样后 → LatentSave → 解码 → TrimAV → CreateVideo
    if relay:
        rd = str(relay.get("run_id") or "ep")
        stage = int(relay.get("stage") or 0)
        r2v_id = find(g, "MiniMaxH3ReferenceToVideo")[0]
        guider_id = find(g, "BasicGuider")[0]
        sampler_id = find(g, "SamplerCustomAdvanced")[0]
        vae_id = find(g, "VAELoader")[0]
        audio_vae_id = find(g, "VAELoader")[1]
        cur_cond = g[guider_id]["inputs"]["conditioning"]

        bridge_inputs = {
            "latent": [r2v_id, 1],
            "context_frames": int(relay.get("context_frames") or 22),
            "mask_mode": "hard",
            "conditioning": cur_cond,
            "run_id": rd,
            "stage_index": stage,
        }
        if stage > 0 and relay.get("prev_video"):
            g["990"] = {"class_type": "LoadVideo", "inputs": {"file": relay["prev_video"]}}
            g["991"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["990", 0]}}
            g["992"] = {
                "class_type": "H3RelaySeedFromVideo",
                "inputs": {
                    "video": ["991", 0],
                    "video_vae": [vae_id, 0],
                    "audio_vae": [audio_vae_id, 0],
                    "width": int(width), "height": int(height),
                    "run_id": rd, "stage_index": stage - 1,
                    "audio": ["991", 1], "snap": "trim",
                },
            }
            bridge_inputs["context_latent"] = ["992", 0]
        g["993"] = {"class_type": "H3RelayCopyBridge", "inputs": bridge_inputs}
        g[guider_id]["inputs"]["conditioning"] = ["993", 3]
        g[sampler_id]["inputs"]["latent_image"] = ["993", 0]

        g["994"] = {"class_type": "H3RelayLatentSave",
                    "inputs": {"latent": [sampler_id, 0], "run_id": rd,
                               "stage_index": stage, "note": ""}}
        for ct in ("VAEDecode", "VAEDecodeAudio"):
            nid = find(g, ct)[0]
            g[nid]["inputs"]["samples"] = ["994", 0]

        g["995"] = {"class_type": "H3RelayTrimAV",
                    "inputs": {"images": [find(g, "VAEDecode")[0], 0],
                               "trim_frames": ["993", 2], "fps": float(FPS),
                               "audio": [find(g, "VAEDecodeAudio")[0], 0],
                               "run_id": rd}}
        cvid = find(g, "CreateVideo")[0]
        g[cvid]["inputs"]["images"] = ["995", 0]     # ← TrimAV，不能动
        g[cvid]["inputs"]["audio"] = ["995", 1]

    # ---- C 方案：上一镜视频作为 <Video N> 语义参考
    # LoadVideo(file) → GetVideoComponents(IMAGE) → ref_videos.ref_video_N
    if ref_videos:
        base = 950
        for i, fname in enumerate(ref_videos[:3]):
            vid_id, comp_id = str(base + i * 2), str(base + i * 2 + 1)
            g[vid_id] = {"class_type": "LoadVideo", "inputs": {"file": fname}}
            g[comp_id] = {"class_type": "GetVideoComponents",
                          "inputs": {"video": [vid_id, 0]}}
            node["inputs"][f"ref_videos.ref_video_{i}"] = [comp_id, 0]

    # ---- B' 方案：把上一镜最后 N 帧做成片段喂进 Add Guide（真接续）
    # 官方 Multiframe 文档：单帧只能钉构图，喂 22 帧片段才能让动作续上
    if guide_clips:
        host_id = find(g, "BasicGuider")[0]
        prev_pos = g[host_id]["inputs"]["conditioning"]
        base = 980
        for i, (fname, frame_idx, start, length) in enumerate(guide_clips):
            vid_id, comp_id = str(base + i * 4), str(base + i * 4 + 1)
            slice_id, guide_id = str(base + i * 4 + 2), str(base + i * 4 + 3)
            g[vid_id] = {"class_type": "LoadVideo", "inputs": {"file": fname}}
            g[comp_id] = {"class_type": "GetVideoComponents",
                          "inputs": {"video": [vid_id, 0]}}
            g[slice_id] = {"class_type": "ImageFromBatch",
                           "inputs": {"image": [comp_id, 0],
                                      "batch_index": int(start), "length": int(length)}}
            g[guide_id] = {
                "class_type": "MiniMaxH3AddGuide",
                "inputs": {
                    "positive": prev_pos,
                    "latent": [find(g, "MiniMaxH3ReferenceToVideo")[0], 1],
                    "vae": ["119", 0],
                    "audio_vae": ["120", 0],
                    "image": [slice_id, 0],
                    "frame_idx": int(frame_idx),
                },
            }
            prev_pos = [guide_id, 0]
        g[host_id]["inputs"]["conditioning"] = prev_pos

    # ---- B 方案：上一镜末帧钉在第 0 帧（Add Guide 链）
    # 官方接线：R2V.positive → AddGuide(frame_idx, image) → BasicGuider.conditioning
    if guide_images:
        host_id = find(g, "BasicGuider")[0]
        prev_pos = g[host_id]["inputs"]["conditioning"]
        base = 970
        for i, (img, frame_idx) in enumerate(guide_images):
            img_id, guide_id = str(base + i * 2), str(base + i * 2 + 1)
            g[img_id] = {"class_type": "LoadImage", "inputs": {"image": img}}
            g[guide_id] = {
                "class_type": "MiniMaxH3AddGuide",
                "inputs": {
                    "positive": prev_pos,
                    "latent": [find(g, "MiniMaxH3ReferenceToVideo")[0], 1],
                    "vae": ["119", 0],
                    "audio_vae": ["120", 0],
                    "image": [img_id, 0],
                    "frame_idx": int(frame_idx),
                },
            }
            prev_pos = [guide_id, 0]
        g[host_id]["inputs"]["conditioning"] = prev_pos

    # 码率：H.264 重编码 + CRF（SaveVideo 默认 auto 只有 ~3Mbps）
    sv_id = find(g, "SaveVideo")
    if sv_id and crf:
        g[sv_id[0]]["inputs"]["codec"] = {
            "codec": "h264", "encoding": {"encoding": "re-encode", "crf": float(crf)}}

    # 插帧：24 → 48 fps（RIFE VFI ×2），CreateVideo 的 fps 必须同步翻倍
    if interpolate:
        dec_id = find(g, "VAEDecode")
        cv_id = find(g, "CreateVideo")
        if dec_id and cv_id:
            g["953"] = {"class_type": "RIFE VFI", "inputs": {
                "ckpt_name": "rife49.pth", "frames": [dec_id[0], 0],
                "clear_cache_after_n_frames": 10, "multiplier": 2,
                "fast_mode": True, "ensemble": True, "scale_factor": 1.0,
                "dtype": "float32", "torch_compile": False, "batch_size": 1}}
            g[cv_id[0]]["inputs"]["images"] = ["953", 0]
            base_fps = float(g[cv_id[0]]["inputs"].get("fps") or 24.0)
            g[cv_id[0]]["inputs"]["fps"] = base_fps * 2
            print(f"  插帧：{base_fps:g} → {base_fps * 2:g} fps")

    g = apply_sage(g, sage)
    return apply_controlnet(g, control_video, mode=control_mode, strength=control_strength)


def apply_controlnet(graph: dict, video: str, *, mode: str = "pose",
                     strength: float = 1.0, start_percent: float = 0.0,
                     end_percent: float = 1.0, patch: str = "",
                     batch_size: int = 8) -> dict:
    """给 H3 挂 Fun ControlNet Union（官方 patch，支持 canny/depth/hed/mlsd/pose）。

    依据 docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet：
      ModelPatchLoader → MiniMaxH3FunControlNetApply(model, model_patch, vae, control_video, strength)
      节点插在模型链与 guider/scheduler 之间。模板要求 ComfyUI ≥ 0.35（本机 0.42.1）。

    mode="pose" 时先走 SDPose 抽骨架——这才是"按真人动作驱动姿势"的正路；
    mode="raw" 直接把视频帧当控制图。
    """
    if not video:
        return graph
    hosts = find(graph, "BasicGuider") + find(graph, "BasicScheduler")
    if not hosts:
        return graph
    patch = patch or "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"
    dec = find(graph, "VAEDecode")
    vae_ref = graph[dec[0]]["inputs"].get("vae") if dec else ["119", 0]

    graph["940"] = {"class_type": "LoadVideo", "inputs": {"file": video}}
    graph["941"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["940", 0]}}
    ctrl = ["941", 0]
    if str(mode).lower() == "pose":
        graph["942"] = {"class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "sdpose_wholebody_fp16.safetensors"}}
        graph["943"] = {"class_type": "SDPoseKeypointExtractor",
                        "inputs": {"model": ["942", 0], "vae": ["942", 2],
                                   "image": ["941", 0], "batch_size": int(batch_size)}}
        graph["944"] = {"class_type": "SDPoseDrawKeypoints",
                        "inputs": {"keypoints": ["943", 0], "draw_body": True, "draw_hands": False,
                                   "draw_face": False, "draw_feet": True, "stick_width": 4,
                                   "face_point_size": 2, "score_threshold": 0.3, "draw_head": True}}
        ctrl = ["944", 0]
    graph["945"] = {"class_type": "ModelPatchLoader", "inputs": {"name": patch}}
    model_ref = graph[hosts[0]]["inputs"].get("model")
    graph["946"] = {"class_type": "MiniMaxH3FunControlNetApply",
                    "inputs": {"model": model_ref, "model_patch": ["945", 0], "vae": vae_ref,
                               "strength": float(strength), "start_percent": float(start_percent),
                               "end_percent": float(end_percent), "control_video": ctrl}}
    for nid in hosts:
        if isinstance(graph[nid]["inputs"].get("model"), list):
            graph[nid]["inputs"]["model"] = ["946", 0]
    print(f"  控制网：{mode} 控制片={os.path.basename(video)} 强度={strength}")
    return graph


def h3_ref_frames(seconds: float) -> int:
    """Ref2VA 的帧数：17k+5。

    节点硬约束（object_info / nodes_minimax_h3.py:38-51）：**min 5 / step 17 / max 3600**，
    `align_frame_count()` 会把 n 抬到 `n % 17 == 5`。
    节点 tooltip 只写 "trained range is ~124-362"，**那是训练区间，不是硬下限**——
    我之前把 124 当死线、把 2 秒悄悄抬成 5.17 秒，是**错的**。
    现在：<124 帧照做，下限放到 39 帧（1.6 秒），并在低于训练区间时打印提示。
    """
    raw = max(1, round(seconds * FPS))
    k = max(0, round((raw - 5) / H3_GRID))
    frames = k * H3_GRID + 5
    frames = max(39, min(362, frames))       # 39 = 1.6 s；再短模型几乎没信息可演
    if frames < 124:
        print(f"  ! {frames} 帧（{frames / FPS:.2f} 秒）低于官方训练区间 124–362，质量未验证")
    return frames


def h3(*, first_image: str, prompt: str, seconds: float, width: int, height: int,
       seed: int, prefix: str, steps: int = 8, last_image: str = "",
       sage: str = "auto", control_video: str = "", control_mode: str = "pose",
       control_strength: float = 1.0) -> dict:
    g = load("h3")
    first_id = find(g, "LoadImage")[0]
    g[first_id]["inputs"]["image"] = first_image
    if last_image:                      # 模板只有一张 LoadImage，末帧按需补一张
        g["901"] = {"class_type": "LoadImage", "inputs": {"image": last_image}}
        link(g, "901", 0, "MiniMaxH3ImageToVideo", "last_frame")
    set_inputs(g, "MiniMaxH3ImageToVideo", prompt=prompt, width=int(width), height=int(height),
               length=h3_frames(seconds))
    set_inputs(g, "RandomNoise", noise_seed=int(seed))
    set_inputs(g, "BasicScheduler", steps=int(steps))
    set_inputs(g, "SaveVideo", filename_prefix=prefix)
    if int(steps) > 12:
        # 和 h3_ref 一致：步数远超 turbo 训练档时摘掉 LoRA，走原生采样
        _drop_lora(g)
        print(f"  高步数 {steps}：已摘 turbo LoRA，走原生采样")
    g = apply_sage(g, sage)
    return apply_controlnet(g, control_video, mode=control_mode, strength=control_strength)
