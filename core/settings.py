"""本机设置：LLM 接口 / ComfyUI 路径 / 权重文件名。

存在 `_agent/settings.json`（明文，只在本机）。密钥不回传前端全文，只回报"是否已设"。

三段：
    llm     —— 翻译用的 OpenAI 兼容接口
    comfy   —— ComfyUI 根目录（留空=自动探测）+ 服务地址
    models  —— 权重文件名（留空=用 DEFAULT_MODELS；别人装的名字不一样就改这里，不必改代码）
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(HERE, "settings.json")

DEFAULTS = {
    "llm": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
    },
    # root 留空 = 自动探测（环境变量 COMFY_DIR > 从 _agent 往上找 ComfyUI\models）
    # url 留空 = 环境变量 COMFY_BASE / COMFY_URL > http://127.0.0.1:8188
    # 这两个默认值必须是空串：写死默认值会把环境变量永久遮蔽掉。
    "comfy": {"root": "", "url": ""},
    "models": {},
}

# 发布基线：别人的文件名和这里不同，只需要在设置里覆盖对应键，代码不用动。
DEFAULT_MODELS = {
    # Krea2 —— 出首帧、角色设定图、场景空镜
    "krea2_unet": "krea2_turbo_fp8_scaled.safetensors",
    "krea2_clip": "qwen3vl_4b_fp8_scaled.safetensors",
    "krea2_vae": "qwen_image_vae.safetensors",
    # Qwen-Image-Edit 2511 —— 多角度三视图、场景去人
    "qwen_edit_unet": "qwen_image_edit_2511_fp8mixed.safetensors",
    "qwen_edit_clip": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
    "qwen_edit_vae": "qwen_image_vae.safetensors",
    "qwen_lora_angles": "qwen-image-edit-2511-multiple-angles-lora.safetensors",
    "qwen_lora_lightning": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
    # MiniMax H3 —— 出片。unet 与 turbo LoRA 由 object_info 关键词自动匹配，
    # 这里只配顺序敏感、名字写死的那三个（文本编码器 + 两个 VAE）。
    "h3_clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "h3_video_vae": "minimax_h3_video_vae_int8_convrot.safetensors",
    "h3_audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
    # 8 GB 低显存方案（社区实测）：W4A8 主模型 + 4B 编码器 + ClipProj 矩阵。
    # 低配档只走这一条；GGUF 那条路已废弃（ComfyUI-GGUF 至今不支持 MiniMax H3）。
    "w4a8_unet": "minimax_h3_ref2va_pruned_w4a8_mixed.safetensors",
    "w4a8_clip": "qwen3vl_4b_int8_convrot.safetensors",
    "w4a8_proj": "mmh3-4b-ClipProj-v3-mlp.safetensors",
}

# 每一项对应的模型子目录，体检时按它拼路径
MODEL_SUBDIR = {
    "krea2_unet": "diffusion_models", "krea2_clip": "text_encoders", "krea2_vae": "vae",
    "qwen_edit_unet": "diffusion_models", "qwen_edit_clip": "text_encoders",
    "qwen_edit_vae": "vae", "qwen_lora_angles": "loras", "qwen_lora_lightning": "loras",
    "h3_clip": "text_encoders", "h3_video_vae": "vae", "h3_audio_vae": "vae",
    "w4a8_unet": "diffusion_models", "w4a8_clip": "text_encoders", "w4a8_proj": "clip_projections",
}

_CACHE: dict | None = None
_CACHE_MTIME: float = 0.0


def _merge(base: dict, extra: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update({kk: vv for kk, vv in v.items() if vv is not None})
        else:
            out[k] = v
    return out


def load() -> dict:
    """读设置。按 mtime 缓存：路径查询很频繁（每次取产物都要问根目录）。"""
    global _CACHE, _CACHE_MTIME
    try:
        mt = os.path.getmtime(PATH)
    except OSError:
        mt = 0.0
    if _CACHE is not None and mt == _CACHE_MTIME:
        return _CACHE
    data = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    if mt:
        try:
            with open(PATH, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data = _merge(data, raw)
        except (OSError, json.JSONDecodeError):
            pass
    _CACHE, _CACHE_MTIME = data, mt
    return data


def save(patch: dict) -> dict:
    """写设置。三种收法都兼容：

    - 老前端直接给 {"base_url","api_key","model"} → 当 llm 段
    - 新前端给 {"llm":{...}} / {"comfy":{...}} / {"models":{...}} → 按段合并
    """
    patch = dict(patch or {})
    data = load()
    if any(k in patch for k in ("llm", "comfy", "models")):
        for seg in ("llm", "comfy", "models"):
            if isinstance(patch.get(seg), dict):
                data[seg] = _merge(data.get(seg) or {}, patch[seg])
    else:
        data["llm"] = _merge(data.get("llm") or {}, patch)
    # 只留三段，别把垃圾键写进文件
    out = {k: data.get(k) for k in ("llm", "comfy", "models")}
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    global _CACHE, _CACHE_MTIME
    _CACHE = None
    _CACHE_MTIME = 0.0
    _ROOT_CACHE.clear()          # 路径可能改了，旧缓存的纠正结果作废
    load()
    return data


# ---------------------------------------------------------------- ComfyUI 位置
def _is_root(p: str) -> bool:
    """认 ComfyUI 根目录。

    **不能只查 models\\**：
      - 整合包外壳目录 ComfyUI-aki-v3\\ 下面留了个空 models\\
      - ComfyUI\\models\\ 里面还套了个空的 models\\
    这两个都会让"只看 models"的判据误判。Combined 判据是：
      models\\ + input\\ + （custom_nodes\\ 或 main.py）——只有真正的 ComfyUI 根全都有。
    """
    if not p or not os.path.isdir(os.path.join(p, "models")):
        return False
    if not os.path.isdir(os.path.join(p, "input")):
        return False
    return (os.path.isdir(os.path.join(p, "custom_nodes"))
            or os.path.isfile(os.path.join(p, "main.py")))


def _clean(p: str) -> str:
    r"""去引号、去尾部斜杠、转绝对路径。

    注意别把盘符根削没了：`"E:\\"` 直接 rstrip 会变成 `"E:"`，
    而 `os.path.abspath("E:")` 指的是"E 盘的当前工作目录"，不是盘符根。
    """
    s = str(p or "").strip().strip('"').strip("'")
    if not s:
        return ""
    s = os.path.abspath(s)
    if len(s) > 3:                      # "E:\" 长度就是 3，不削
        s = s.rstrip("\\/")
    return s


def normalize_root(raw: str) -> tuple[str, str]:
    """把你选的文件夹纠正成真正的 ComfyUI 根目录，返回 (路径, 说明)。

    只在**选中路径的上下几层**里找，不扫盘。因为选错层级才是真正的坑：
      选 ComfyUI-aki-v3（外壳）        → 往下进 ComfyUI\\
      选 ComfyUI\\models（深一层）      → 往上退到它的父目录
      选 ComfyUI\\models\\loras（太深） → 一路往上找到 models 的父
      选 ComfyUI\\output（兄弟目录）    → 同上
    纠正不了就返回 ("", 原因)，让前端说实话，不要假装找着了。
    """
    p = _clean(raw)
    if not p or not os.path.isdir(p):
        return "", f"这个文件夹不存在：{raw}"
    if _is_root(p):
        return p, ""

    # 1) 往上退一层（"选深了"比"选浅了"常见：手一滑就点进 models\ 或 output\）
    par = os.path.dirname(p)
    if par != p and _is_root(par):
        return par, f"你选深了一层，已经退回到 {os.path.basename(par)}\\"

    # 2) 下一层就是 ComfyUI（整合包外壳目录：ComfyUI-aki-v3\ComfyUI）
    direct = os.path.join(p, "ComfyUI")
    if _is_root(direct):
        return direct, "你选的是外壳目录，真正的 ComfyUI 在它的 ComfyUI\\ 子目录里"

    # 3) 一路往上退，撞到某个 models 的父目录（最多 5 层）
    cur = p
    for _ in range(5):
        if os.path.basename(cur).lower() == "models" and _is_root(os.path.dirname(cur)):
            up = os.path.dirname(cur)
            return up, f"你选到 models 里面了，已经退回到 {os.path.basename(up)}\\"
        nxt = os.path.dirname(cur)
        if nxt == cur:
            break
        if _is_root(nxt):
            return nxt, f"你选深了，已经退回到 {os.path.basename(nxt)}\\"
        cur = nxt

    # 4) 直接子目录里有唯一一个像 ComfyUI 的（整合包被改过名也能认）
    subs: list[str] = []
    try:
        for e in os.scandir(p):
            if e.is_dir() and _is_root(e.path):
                subs.append(e.path)
    except OSError:
        pass
    if len(subs) == 1:
        return subs[0], f"你选的目录下面找到了 ComfyUI：{os.path.basename(subs[0])}"
    if len(subs) > 1:
        names = "、".join(os.path.basename(x) for x in subs[:5])
        return "", f"这个目录下有多个像 ComfyUI 的文件夹（{names}），请选具体那一个"

    return "", f"这不是 ComfyUI 目录：{p} 里没有 models\\ + input\\，上下几层也没找到（要选有 main.py 的那一层）"


_ROOT_CACHE: dict[str, tuple[str, str]] = {}   # 设置里填的原值 → (纠正后的根, 说明)


def _resolve_cfg_root(cfg: str) -> tuple[str, str]:
    """把设置里存的路径解析成根目录，结果缓存（避免每次取产物都 scandir 一遍）。"""
    if cfg not in _ROOT_CACHE:
        _ROOT_CACHE[cfg] = normalize_root(cfg) if cfg else ("", "")
    return _ROOT_CACHE[cfg]


def resolve_root(simulate_fresh: bool = False) -> tuple[str, str, str]:
    """返回 (路径, 来源, 说明)。来源：setting / env / auto / ""。

    为什么要暴露"来源"：自动探测在本机几乎永远成功，体检就永远全绿，
    路径配置那条链路等于被藏起来了。
    把来源摆出来，才能分清"我配的"和"它自己猜的"。

    simulate_fresh=True 时**三者全忽略**（设置也不看），完全等价于一台全新机器：
    全新机器上 settings.json 里根本没有 root，所以这里也必须忽略已存的值，
    否则"模拟未配置"模拟不出未配置。
    """
    if simulate_fresh:
        return "", "", ""
    cfg = str((load().get("comfy") or {}).get("root") or "").strip().strip('"')
    if cfg:
        got, note = _resolve_cfg_root(cfg)
        if got:
            return got, "setting", note
        # 设了但无效：把原因带出去，**不悄悄回落到自动探测**
        # （否则用户以为自己的设置生效了，实际跑的是猜出来的那条路）
        return "", "setting", note
    env = os.environ.get("COMFY_DIR", "").strip().strip('"')
    if env and _is_root(env):
        return _clean(env), "env", ""
    cur = HERE
    for _ in range(8):
        cand = os.path.join(cur, "ComfyUI")
        if _is_root(cand):
            return cand, "auto", ""
        if _is_root(cur):
            return cur, "auto", ""
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return "", "", ""


def comfy_root() -> str:
    """ComfyUI 根目录：设置 > 环境变量 COMFY_DIR > 从 _agent 往上找。找不到返回空串。"""
    return resolve_root()[0]


def comfy_url() -> str:
    """ComfyUI 服务地址：设置 > COMFY_BASE / COMFY_URL 环境变量 > 127.0.0.1:8188。"""
    cfg = str((load().get("comfy") or {}).get("url") or "").strip()
    for val in (cfg, os.environ.get("COMFY_BASE", ""), os.environ.get("COMFY_URL", "")):
        if val and val.strip():
            return val.strip().rstrip("/")
    return "http://127.0.0.1:8188"


def model(key: str) -> str:
    """取权重文件名：设置里覆盖过就用覆盖值，否则用 DEFAULT_MODELS。"""
    val = str((load().get("models") or {}).get(key) or "").strip()
    return val or DEFAULT_MODELS.get(key, "")


_EXTRA_CACHE: dict[str, tuple[float, dict]] = {}


def _extra_paths() -> dict[str, list[str]]:
    """解析 ComfyUI\\extra_model_paths.yaml，返回 {子目录名: [候选绝对目录]}。

    为什么要它：模型不一定都在 ComfyUI\\models，很多人挂在别的盘
    。

    手写解析不引 pyyaml：只为读一份格式固定的配置，不值得多一个依赖。
    支持 `key: 路径` 和 `key: |` + 缩进多行，相对路径按 base_path 展开，
    不存在的目录直接丢掉。
    """
    root = resolve_root()[0]
    if not root:
        return {}
    yml = os.path.join(root, "extra_model_paths.yaml")
    try:
        mt = os.path.getmtime(yml)
    except OSError:
        return {}
    hit = _EXTRA_CACHE.get(yml)
    if hit and hit[0] == mt:
        return hit[1]

    raw_map: dict[str, list[str]] = {}
    # 只认这几个已知 key。**不能**用"含冒号就当 key"来判：
    #   base_path: 是缩进的
    #   D:/路径/xxx 里的 D: 会被误认成 key
    KNOWN = {
        "checkpoints", "text_encoders", "diffusion_models", "loras", "vae", "clip",
        "clip_vision", "controlnet", "upscale_models", "embeddings", "unet",
        "audio_encoders", "model_patches", "facerestore_models", "insightface",
        "sam", "sams", "ultralytics", "RMBG", "style_models", "photomaker",
    }
    base = root
    key = ""
    try:
        with open(yml, encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\r\n")
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("base_path:"):
                    base = s.split(":", 1)[1].strip().strip('"').strip("'") or base
                    continue
                if ":" in s:
                    k, v = s.split(":", 1)
                    k = k.strip()
                    if k in KNOWN:
                        key = k
                        v = v.strip()
                        if v and v not in ("|", ">"):
                            raw_map.setdefault(key, []).append(v)
                        continue
                if key:
                    raw_map.setdefault(key, []).append(s)
    except OSError:
        return {}

    out: dict[str, list[str]] = {}
    for k, vals in raw_map.items():
        dirs: list[str] = []
        for v in vals:
            p = v if os.path.isabs(v) else os.path.join(base, v)
            p = os.path.normpath(p)
            if os.path.isdir(p) and p not in dirs:
                dirs.append(p)
        if dirs:
            out[k] = dirs
    _EXTRA_CACHE[yml] = (mt, out)
    return out


def model_dirs(subdir: str) -> list[str]:
    """某个模型子目录的所有候选位置：ComfyUI\\models\\<subdir> + extra_model_paths 里配的。"""
    root = resolve_root()[0]
    dirs: list[str] = []
    if root:
        d = os.path.join(root, "models", subdir)
        if os.path.isdir(d):
            dirs.append(d)
    for d in _extra_paths().get(subdir, []):
        if d not in dirs:
            dirs.append(d)
    return dirs


def public() -> dict:
    """给前端的版本：密钥只报有没有，不回显。路径与文件名都明文（本机，不是秘密）。"""
    d = load()
    llm = d.get("llm") or {}
    root, root_source, root_note = resolve_root()
    raw_root = str((d.get("comfy") or {}).get("root") or "").strip()
    models = {k: model(k) for k in DEFAULT_MODELS}
    overrides = {k for k in DEFAULT_MODELS
                 if str((d.get("models") or {}).get(k) or "").strip()}
    return {
        "base_url": llm.get("base_url", ""),
        "model": llm.get("model", ""),
        "has_key": bool(llm.get("api_key")),
        "key_hint": ("…" + llm["api_key"][-4:]) if llm.get("api_key") else "",
        "comfy": {
            "root": raw_root,
            "url": comfy_url(),
            "root_effective": root,
            "root_source": root_source,      # setting / env / auto / ""
            "root_note": root_note,
            "detected": bool(root),
        },
        "models": models,
        "models_overridden": sorted(overrides),
    }
