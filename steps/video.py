"""出视频：MiniMax H3（参考图 / 首帧两种模式）。视频只吃「接下来发生什么」，画面细节一律不进。"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time

from core import comfy, graphs, media, prompts, store

CLIP_DIR = "canvas/video"   # 画布出的片统一进 output\canvas\，和我脚本跑的 output\runs\ 分开
ENGINE_NAME = {"h3": "MiniMax H3 · FL2VA", "h3ref": "MiniMax H3 · Ref2VA"}


def _anchors(ep: str, shot: dict, prev: dict | None, seconds: float) -> list[dict]:
    """锚点来源，按优先级：镜头自己写的 → 承接上一镜末帧 → 本镜首帧。

    尾锚点的 tail_at 是**比例**不是秒：0.7 = 时长的 70%。贴到片尾会让模型到了就不动。
    """
    explicit = shot.get("anchors")
    if explicit:
        return [{"image": comfy.upload_image(a["image"]), "at": float(a.get("at", 0))}
                for a in explicit]

    st = shot.get("state") or {}
    first = st.get("kf")
    if shot.get("link") and prev:
        pv = (prev.get("state") or {}).get("last_frame")
        if pv and os.path.isfile(pv):
            first = pv
            print(f"  · 首帧承接 {prev['id']} 末帧")
        elif shot.get("link"):
            print(f"  ! {prev['id']} 还没有末帧，先用本镜首帧")
    if not first:
        raise RuntimeError(f"{ep}/{shot['id']} 还没有首帧，先跑 frame")

    anchors = [{"image": comfy.upload_image(first), "at": 0.0}]
    tail = st.get("tail_frame")
    if tail and os.path.isfile(tail):
        frac = float(shot.get("tail_at", 0.7))
        anchors.append({"image": comfy.upload_image(tail), "at": round(frac * seconds, 2)})
    return anchors


def _log_claim(ep: str, sid: str, path: str, text: str, refs: list[dict], seed: int) -> None:
    """每次成功出片自动记一条台账：产物 + 提示词哈希 + 参考图。

    这样"这次到底跑了什么"永远有据可查，不靠我事后回忆。
    """
    import hashlib
    import json as _json
    from pathlib import Path

    store_file = Path(__file__).resolve().parent.parent / "out" / "claims.jsonl"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    rows = []
    if store_file.is_file():
        for line in store_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(_json.loads(line))
    rows.append({
        "id": max([r["id"] for r in rows], default=0) + 1,
        "ts": time.strftime("%Y-%m-%d %H:%M"),
        "claim": f"{ep}/{sid} 用 Ref2VA 跑出一条成片（{len(refs)} 张参考）",
        "kind": "experiment",
        "evidence": f"{path} | prompt_sha={sha} | refs={[r.get('kind') for r in refs]} | seed={seed}",
        "status": "verified",
    })
    store_file.parent.mkdir(parents=True, exist_ok=True)
    store_file.write_text("\n".join(_json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                          encoding="utf-8")


def _ordered(items: list[dict]) -> list[dict]:
    """按镜头号排：衔接的"上一镜"必须按 S01→S02 算，不能按数组里存的顺序。

    shots.json 里数组顺序可能是创建顺序（实测出现过 S02,S03,S01,S04），
    照数组取 prev 会让 S02 认不到 S01。
    """
    import re as _re
    ids = [str(it.get("id") or "") for it in items]
    if all(_re.fullmatch(r"S\d+", i) for i in ids):
        return sorted(items, key=lambda it: int(str(it["id"])[1:]))
    return list(items)


# 首帧出片（fl2v）的输出尺寸上限：按面积算，等于 1088×1920 那块（2.09 MP），防 OOM。
H3_FL2V_MAX_MP = 2.09


def _align16(v: float) -> int:
    """H3 的 latent 按 16 对齐；向下取整，宁可小一点也不要超出。"""
    return max(16, int(v) // 16 * 16)


def _fl2v_size(shot: dict, proj: dict) -> tuple[int, int]:
    """首帧模式出片尺寸：跟首帧图的实际像素走，不读项目里写死的值。

    首帧图已经定了构图和比例，再拿项目尺寸去套等于让模型把图拉伸一遍。
    读不到图才回落到项目尺寸，再没有就落到 1088×1920。
    """
    kf = str((shot.get("state") or {}).get("kf") or "")
    w = h = 0
    if kf and os.path.isfile(kf):
        try:
            from PIL import Image  # 局部导入：别的路径用不到 PIL
            with Image.open(kf) as im:
                w, h = im.size
        except Exception as exc:  # noqa: BLE001 - 读不到就走回落
            print(f"  ! 读首帧尺寸失败（{exc}），回落到项目尺寸")
            w = h = 0
    if not (w and h):
        w = int(proj.get("width") or 1088)
        h = int(proj.get("height") or 1920)
    ow, oh = _align16(w), _align16(h)
    mp = ow * oh / 1e6
    if mp > H3_FL2V_MAX_MP:
        k = (H3_FL2V_MAX_MP / mp) ** 0.5
        ow, oh = _align16(ow * k), _align16(oh * k)
        print(f"  首帧 {w}x{h} 面积 {mp:.2f} MP 超过上限 {H3_FL2V_MAX_MP}，等比缩到 {ow}x{oh}")
    else:
        print(f"  首帧 {w}x{h} → 出片 {ow}x{oh}（16 对齐）")
    return ow, oh


def _preflight(ep: str, sid: str, text: str, refs: list[dict],
               allow_free: bool = False) -> list[str]:
    """出片前的硬检查：配置不对就直接拒绝，不许靠我"觉得没问题"。

    这几条都是真实翻车换来的：
      · 拿 fl2va 权重跑 ReferenceToVideo → 参考图不生效，人和场景全跑掉
      · 没有参考图 → 模型只能编
      · 六段不齐 → 不是官方格式
    """
    bad = []
    unet, lora = graphs._pick_h3_weights("ref2va")
    if not unet:
        bad.append("没装 ref2va 权重（当前只有 fl2va）→ 参考图不会生效。"
                   "请下载 minimax_h3_ref2va_pruned_int8_convrot.safetensors 到 models/diffusion_models")
    if not lora:
        bad.append("没装 ref2v turbo LoRA → 会沿用 fl2v 的加速 LoRA，步数与权重不匹配")
    if not refs:
        bad.append("这一镜没有挂参考图：Ref2VA 至少需要一张")
    heads = [l.split(":")[0] for l in text.splitlines() if l.rstrip().endswith(":")]
    need = ["subject_definitions", "summary", "retention_analysis",
            "detailed_description", "overall_soundscape", "non_diegetic_music"]
    if allow_free:
        # 用户自己在「整段覆盖」里写了完整提示词（镜头卡/分镜格式），
        # 那是**明确覆盖**，不该拿官方六段格式去拦。
        # 只提醒"缺主体定义"，不拒绝。
        if "<Subject" not in text:
            print("  ! 整段覆盖里没有 <Subject N>：人物身份不会绑定参考图（空镜无所谓）")
    elif heads[:6] != need:
        bad.append(f"提示词不是六段：实际 {heads}")
    return bad


def _save_sent(ep: str, sid: str, text: str, refs: list[dict]) -> None:
    """记下这一镜真正发给模型的提示词和槽位，供画布核对。"""
    shots = store.shots(ep)
    for sh in shots:
        if sh.get("id") == sid:
            st = dict(sh.get("state") or {})
            st["sent_prompt"] = text
            st["sent_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            st["sent_refs"] = [{"kind": r.get("kind"), "name": r.get("name")} for r in refs]
            sh["state"] = st
            store.save_shots(ep, shots)
            return


def _shot_refs(ep: str, shot: dict) -> list[dict]:
    """槽位顺序单一来源：直接调 core.refs.shot_refs（角色 → 场景 → 道具）。

    以前这里自己拼一遍，和 prompts.video_text_for 用的 refs.shot_refs 是两份实现：
    两份一旦有差异（比如这里不认角色辅助图、也不认道具卡），上传的图片顺序就和
    提示词里的 `<Picture N>` 编号对不上，模型会按错图去绑主体。
    """
    from core import refs as _refs_mod
    return _refs_mod.shot_refs(ep, shot)


def _to_english(text: str, beats: list[str], where: str) -> tuple[str, list[str], str]:
    """正文里有中文就翻成英文，翻不了直接报错——不许把中文塞进去白跑一轮。"""
    import re
    from core import llm, settings

    has_cn = bool(re.search(r"[\u4e00-\u9fff]", text)) or any(
        re.search(r"[\u4e00-\u9fff]", str(b)) for b in beats)
    if not has_cn:
        return text, beats, ""

    cfg = settings.load()["llm"]
    if not cfg.get("api_key"):
        raise RuntimeError(
            f"{where}：提示词里有中文，而画布「设置」里还没配翻译密钥。\n"
            f"  要么填密钥，要么切到 MiniMax H3（它能直接吃中文）。")
    try:
        text_en = llm.translate_video(text, cfg)
        beats_en = [llm.translate_video(str(b), cfg) for b in beats]
    except llm.LLMError as e:
        raise RuntimeError(f"{where}：翻译失败，拒绝把中文塞进提示词 —— {e}") from None
    return text_en, beats_en, text_en


def _oom_advice() -> str:
    v = comfy.device_vram()
    head = ""
    if v.get("total_gb"):
        head = f"（这台机器显存 {v['total_gb']} GB，当前空闲 {v.get('free_gb', 0)} GB）"
    return ("显存不够：ComfyUI 报 out of memory" + head + "。\n"
            "H3 出片的主模型约 19.5 GB、文本编码器约 14.6 GB，8 GB 显存塞不进去。按顺序试：\n"
            "  1) 启动 ComfyUI 时加 --lowvram（更狠用 --novram），让它把权重放内存/磁盘换进换出；\n"
            "  2) 这一镜缩短（比如 3 秒）——帧数要满足 17k+5；\n"
            "  3) 关掉别的吃显存的程序；\n"
            "  4) 仍然不行就把「出片模型档位」切到低显存档（W4A8 + 4B 编码器，显存小很多）。\n"
            "详见 README「显存不够（OOM）」一节。")


def _submit_with_sage_fallback(graph: dict, label: str, dump: str, meta: dict) -> dict:
    """提交并等结果；缺 sageattention 时摘节点重提，OOM 时给可执行建议。"""
    def once() -> dict:
        return comfy.wait(comfy.submit(graph, label), label,
                          on_tick=lambda t, s: print(f"    … {t:>4}s {s}", flush=True))

    try:
        return once()
    except comfy.ComfyError as exc:
        low = str(exc).lower()
        if "not currently supported" in low or "unknown model architecture" in low:
            raise RuntimeError(
                "这个权重文件 ComfyUI 认不出来（Unknown model architecture）：\n"
                "常见原因是文本编码器/主模型版本不配套。\n"
                "请把「出片模型档位」切回「标准」，或检查设置里的权重文件名。") from exc
        if "out of memory" in low:
            raise RuntimeError(_oom_advice()) from exc
        if "sageattention" not in low or not graphs.strip_sage(graph):
            raise
        print("  ! ComfyUI 没装 sageattention，已摘掉加速节点重提（只是慢一些）")
        try:
            with open(dump, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)
        except OSError:
            pass
        return once()


def run(ep: str, sid: str, dry: bool = False, engine: str = "", force: bool = False,
        seed: int = 0, seconds_override: float = 0) -> dict:
    proj = store.read(ep, "project")
    items = store.shots(ep)
    shot = store.shot(ep, sid)
    # 两种模式：h3ref = 参考图模式（Ref2VA）；h3fl2v = 首帧模式（FL2VA，从画布确认的首帧往下演）。
    # 白名单之外的历史值（含已下线的引擎名）一律回落到 h3ref，避免老数据悄悄改变出片路径。
    req = str(engine or "").strip().lower()
    if req not in ("h3ref", "h3fl2v"):
        req = str(shot.get("video_engine") or proj.get("video_engine") or "h3ref").strip().lower()
    engine = "h3" if req == "h3fl2v" else "h3ref"
    style = shot.get("style") or proj.get("style") or "gamecg"
    # SageAttention 加速。
    # 可取 disabled / auto / sageattn_qk_int8_pv_fp16_cuda / …；项目级设置优先，单镜可覆盖。
    _sage = str(shot.get("sage") or proj.get("sage") or "auto")
    # Fun ControlNet Union（姿态/深度/整图控制）。shot.video.control = 本地视频绝对路径；
    # 模式 pose = 先抽骨架（推荐），raw = 直接把视频帧当控制图。
    _vcfg0 = shot.get("video") or {}
    _ctrl_path = str(_vcfg0.get("control") or "").strip()
    _ctrl_mode = str(_vcfg0.get("control_mode") or "pose").strip().lower()
    _ctrl_strength = float(_vcfg0.get("control_strength") or 1.0)
    _ctrl = ""
    if _ctrl_path:
        if os.path.isfile(_ctrl_path):
            _ctrl = comfy.put_file(_ctrl_path, prefix="ctl")
            print(f"  控制视频：{os.path.basename(_ctrl_path)}（模式 {_ctrl_mode} 强度 {_ctrl_strength}）")
        else:
            print(f"  ! 控制视频不存在，忽略：{_ctrl_path}")

    items = _ordered(items)
    prev = None
    for i, s in enumerate(items):
        if s["id"] == sid and i > 0:
            prev = items[i - 1]

    st = shot.get("state") or {}
    # 闸门：首帧没被确认过，不许直接烧 GPU（AGENTS 第 4 节）
    if not st.get("confirmed_kf") and not force:
        raise RuntimeError(
            f"{ep}/{sid} 的首帧还没确认。先在画布上确认这张图，或加 --force 强制。")
    if st.get("video") and not force:
        print(f"{ep}/{sid} 已有视频：{st['video']}（要重出加 --force）")
        return {"skipped": True, "path": st["video"]}

    beats = [b for b in (shot.get("beats") or []) if str(b).strip()]
    # 三样里有一样就够：拍子 / 摘要 / 整段覆盖（raw_prompt 补上，
    # 之前只看前两样，用户把整段提示词粘进「整段覆盖」后被这条拦死）
    _summary = str((shot.get("video") or {}).get("summary") or "").strip()
    _raw = str((shot.get("video") or {}).get("raw_prompt") or "").strip()
    if not beats and not _summary and not _raw:
        raise RuntimeError(
            f"{ep}/{sid} 既没写摘要、也没写拍子、也没有整段覆盖：视频不知道要发生什么")

    # 秒数可被调用方覆盖（画布出片弹窗里的时长下拉，需求）
    seconds = float(seconds_override or shot.get("seconds") or 4)
    # 尺寸只在首帧模式（h3）用到，按首帧图定；ref2v 走的 _vw/_vh 在下面单独算
    width, height = _fl2v_size(shot, proj)
    # 种子策略：显式给了就用；-1 强制随机；0/缺省 = 复用这一镜上次的种子
    # 理由：对比实验必须能复现，随机种子会让"改了 A 结果变了"变得不可归因
    prev_seed = int((shot.get("state") or {}).get("video_seed") or 0)
    if seed == -1:
        seed = int(time.time()) % 1_000_000_007
    elif not seed:
        seed = prev_seed or (int(time.time()) % 1_000_000_007)
    print(f"  种子 {seed}" + ("（复用上次）" if seed == prev_seed and prev_seed else ""))
    # 文件名带时间戳 + 种子，方便一次跑多条时区分
    # 目录按「集/镜」分层：output\video\EP01\S19\20261103-165736_h3ref_s123.mp4
    # 用户反馈：全平铺在 video\ 下 24 个文件，找不回是哪一镜
    stamp = time.strftime("%Y%m%d-%H%M%S")
    prefix = f"{CLIP_DIR}/{proj['episode']}/{sid}/{stamp}_{engine}_s{seed}"

    # 全剧保留项：和画布预览保持同一份注入逻辑
    shot = dict(shot)
    shot["_retention"] = str(proj.get("retention") or "").strip()

    # 视频动作/拍子里可能写着 @1/@2（翻译产出的槽位），统一换成模型能读的名词短语
    _refs = _shot_refs(ep, shot)
    if _refs:
        shot = dict(shot)
        _v = dict(shot.get("video") or {})
        _v["action"] = prompts.expand_refs(_v.get("action"), _refs)
        shot["video"] = _v
        beats = [prompts.expand_refs(b, _refs) for b in beats]

    if engine == "h3":
        st0 = shot.get("state") or {}
        # 尾帧锚点只认用户显式给的 tail_frame。
        # 绝对不能用 last_frame：那是本镜上一轮自动抽出来的末帧，
        # 拿它当尾帧会形成回授——第一轮定死结尾，之后每轮都往同一个画面上撞。
        last_src = st0.get("tail_frame") or ""
        first = comfy.upload_image(st0["kf"])
        last = comfy.upload_image(last_src) if last_src and os.path.isfile(last_src) else ""
        print(f"  首帧锚点：本镜首帧；尾帧锚点：{('有 ' + os.path.basename(last_src)) if last else '无（自由结束）'}")
        # H3 不分段：整段一句话 + 方括号运镜
        text = prompts.video_prompt(shot, style, "h3")
        # 首帧模式吃不到参考图（I2V 节点没有 ref_images），角色卡就完全没用上。
        # 实测：首帧只到腿、正文没写脚 → 模型自己给她编了一双鞋（参考图里是赤足）。
        # 补救：翻译之后再单独拼一句英文服装保持句（先拼中文会被整体改写、冲掉官方字段标签）。
        _cards = [r for r in _shot_refs(ep, shot) if str(r.get("kind")) == "char"]
        _wear = "；".join(x for x in (str(r.get("outfit") or "").strip().rstrip("。.") for r in _cards) if x)
        _body = "；".join(x for x in (str(r.get("look") or "").strip().rstrip("。.") for r in _cards) if x)
        # 首帧模式没有 <d> 台词时，正文先翻成英文；翻不动就保留并警告，不硬拦。
        try:
            text2, _b2, translated = _to_english(text, beats, f"{ep}/{sid}")
            if translated:
                print(f"  译(FL2VA)：{translated}")
                text = text2
        except Exception as exc:  # noqa: BLE001 - 翻译不是出片的硬前提
            print(f"  ! 翻译失败，保留原文（可能被念出来）：{exc}")
        # 名字是给人看的：模型不认识具体人名，换成 <Subject N> 这类标签
        _refs = _shot_refs(ep, shot)
        text, _hits = prompts.bind_names(text, _refs)
        if _hits:
            print(f"  已把角色名换成标签：{_hits}")
        # 服装/身体保持句：翻译完之后拼，且只翻这一小段，别动主提示词的结构
        if _wear or _body:
            _keep = "；".join(x for x in (_body, _wear) if x)
            try:
                _keep_en, _b3, _ = _to_english(_keep, [], f"{ep}/{sid}")
                _keep = _keep_en or _keep
            except Exception:  # noqa: BLE001 - 翻不动就用中文，至少信息在
                pass
            _has_bare = ("赤足" in _keep) or ("barefoot" in _keep.lower())
            text = text.rstrip() + ("\n\nHer look and clothing stay exactly as designed: " + _keep + "."
                                    + (" Her feet stay bare; do not add shoes." if _has_bare else ""))
            print(f"  已拼服装保持句：{_keep[:60]}", flush=True)
        problems = prompts.check_video_prompt(text)
        if problems:
            print("⚠ 提示词自检：", *problems, sep="\n  - ")
        graph = graphs.h3(first_image=first, prompt=text, seconds=seconds,
                          width=int(width), height=int(height),
                          seed=seed, prefix=prefix, last_image=last,
                          steps=int((shot.get("video") or {}).get("steps") or 8),
                          sage=_sage, control_video=_ctrl, control_mode=_ctrl_mode,
                          control_strength=_ctrl_strength)
    elif engine == "h3ref":
        # Ref2VA：角色主参考 + 场景参考一起喂，提示词用 <Picture N> 指代
        refs = _shot_refs(ep, shot)
        if not refs:
            raise RuntimeError(
                f"{ep}/{sid} 没有可用的参考图：Ref2VA 至少需要一张角色或场景参考")
        names = [comfy.upload_image(r["path"], prefix="h3ref") for r in refs]
        # 和画布预览走同一个函数：预览显示的就是这里发出去的
        text, refs = prompts.video_text_for(ep, shot, proj)
        _free = bool(str((shot.get("video") or {}).get("raw_prompt") or "").strip())
        _bad = _preflight(ep, sid, text, refs, allow_free=_free)
        if _bad:
            raise RuntimeError("出片前置检查没过：\n  - " + "\n  - ".join(_bad))
        _save_sent(ep, sid, text, refs)
        problems = prompts.check_video_prompt(text, engine="h3")
        if problems:
            print("⚠ 提示词自检：", *problems, sep="\n  - ")
        print(f"  参考图 {len(names)} 张：" + " / ".join(
            f"<Picture {i}>={r.get('name') or r['kind']}" for i, r in enumerate(refs, 1)))
        print(f"  已复制进 input：{comfy.input_dir()}  → " + " / ".join(names))
        _sha = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        print(f"  prompt sha256[:16]={_sha}")

        # 与上一镜的衔接：B=钉末帧（AddGuide@0），C=参考视频（ref_videos.ref_video_0）
        link = str((shot.get("video") or {}).get("link") or "none").lower()
        guide_imgs: list = []
        guide_clips: list = []
        ref_vids: list = []
        prev_shot = None
        for _i, _s in enumerate(items):
            if _s.get("id") == sid and _i > 0:
                prev_shot = items[_i - 1]
        pst = (prev_shot or {}).get("state") or {}
        # 母版优先：一次跑多条时，衔接必须接你选中的那条，而不是碰巧最后一条
        prev_video = pst.get("chosen_video") or pst.get("video") or ""
        prev_last = pst.get("chosen_last_frame") or pst.get("last_frame") or ""
        if prev_video:
            print(f"  母版 {os.path.basename(prev_video)}")
        if link in ("frame", "both"):
            if prev_video and os.path.isfile(prev_video):
                # 接续只喂片段（1 帧档已去掉）
                info = media.probe(prev_video)
                # probe 返回的 fps 是 "24 fps" 这种字符串，得解析出数字
                import re as _re
                _m = _re.search(r"(\d+(?:\.\d+)?)", str(info.get("fps") or ""))
                fps = int(round(float(_m.group(1)))) if _m else 24
                total = int(round(float(info.get("duration") or 0) * fps))
                # 钉多少帧可配：5/22/39（都必须满足 17k+5）
                want = int((shot.get("video") or {}).get("link_frames") or 5)
                want = min(want, total)
                if want < 22:
                    want = 5
                elif want < 39:
                    want = 22
                else:
                    want = 39
                length = min(want, max(5, total))
                start = max(0, total - length)
                clip_name = comfy.put_file(prev_video, prefix="linkclip")
                guide_clips.append((clip_name, 0, start, length))
                print(f"  B' 接续 {prev_shot['id']} 最后 {length} 帧（第 {start}–{start + length - 1} 帧）")
            else:
                print("  ! 上一镜没有视频，B 方案跳过")
        if link in ("video", "both"):
            pv = prev_video
            if pv and os.path.isfile(pv):
                ref_vids.append(comfy.put_file(pv, prefix="linkvid"))
                print(f"  C 参考视频 {prev_shot['id']}：{os.path.basename(pv)}")
            else:
                print("  ! 上一镜没有视频，C 方案跳过")

        # 路线 B：latent 桥接。stage = 本镜在集内的序号；run_id 用集名
        relay = None
        # 衔接只留两档：none / latent。
        # 老数据里的 frame / video / both 一律按 none 处理，免得悄悄走没人用的分支。
        # 衔接两档 + 链头：latent=承接上一镜；latent_head=只给下一镜提供 latent（不承接）
        if link not in ("latent", "latent_head", "none", "black", ""):
            print(f"  ! 衔接方式 {link} 已停用，按「硬切」处理")
            link = "none"
        if link in ("latent", "latent_head"):
            # stage 必须按「这条链里的第几段」算，不能用绝对镜号——
            # 否则第一段（stage 0）不会存 latent，第二段就永远找不到上一段。
            idx = next((i for i, _s in enumerate(items) if _s.get("id") == sid), 0)
            stage = 0
            head_id = sid
            for back in range(idx - 1, -1, -1):
                back_link = str(((items[back].get("video") or {}).get("link") or "none")).lower()
                if back_link in ("latent", "latent_head"):
                    stage += 1
                    head_id = items[back].get("id")
                else:
                    break
            pv = ((prev_shot or {}).get("state") or {})
            pv = pv.get("chosen_video") or pv.get("video") or ""
            relay = {
                # run_id 带链头镜号：不同链互不污染，重跑链头会覆盖自己的缓存
                "run_id": f"{store.slug(ep)}_c{head_id}",
                "stage": stage,
                # 桥的 context_frames 只认 5+17k，最小值 5；单帧模式的 1 不能直接用
                "context_frames": max(5, int((shot.get("video") or {}).get("link_frames") or 22)),
            }
            if link == "latent" and stage > 0 and pv and os.path.isfile(pv):
                relay["prev_video"] = comfy.put_file(pv, prefix="relay")
                print(f"  B latent 桥接：run_id={relay['run_id']} stage={stage} "
                      f"上一段={os.path.basename(pv)} context={relay['context_frames']} 帧")
            elif link == "latent" and stage > 0:
                print("  ! 承接镜但拿不到上一镜成片：本次只存 latent，不读上一段")
            else:
                print(f"  B latent 链头：run_id={relay['run_id']} stage={stage}（只存 latent，给下一镜用）")

        # 步数可单镜覆盖；默认 0 = 按 turbo LoRA 名自动定（4/8 步）。25 步全量已废弃。
        _vcfg = shot.get("video") or {}
        # 步数固定 8，老数据存着 20 也压回 8
        # 步数改成可配（镜头 video.steps → 项目 steps → 25 步非蒸馏）
        _tier = str(proj.get("model_tier") or "default").strip().lower()
        # 默认 8 步：用户不特意选就是 8。实测同提示词同种子同帧数，
        # 8 步 298 秒、20 步 582 秒，画质和动作没有明显变好；25 步还容易 OOM。
        _steps = int(_vcfg.get("steps") or proj.get("steps") or 8)
        # 横竖屏：项目级 orientation 决定输出尺寸（用 H3 原生 768 短边）
        # 默认必须和前端、_aspect_of 一致 —— 都按竖屏。以前这里默认横屏，
        # 于是顶栏写着竖屏、出片却是 1344×768。
        _orient = str(proj.get("orientation") or "portrait").lower()
        _vw, _vh = (1344, 768) if _orient == "landscape" else (768, 1344)
        if _tier in ("w4a8", "low"):
            # 社区实测的 8 GB 档尺寸：横 608×352 / 竖 480×864（再大就 OOM）
            _vw, _vh = (608, 352) if _orient == "landscape" else (480, 864)
        # 模型：留空即走官方 ref2va 权重（由 graphs._pick_h3_weights 从 ComfyUI 实际清单里匹配）
        _model = str(proj.get("model") or "").lower()
        print(f"  出片：{_model or '官方 ref2va'}  档位 {_tier}  步数 {_steps}  尺寸 {_vw}x{_vh}")
        # 空镜自动锚定：没有人物参考图时，把场景图钉在第 0 帧，
        # 横移 52px -> 31px、推镜 7.7% -> 4.7%。有人的镜头不锚定（锚死构图会挡住动作）。
        if not guide_imgs and not any(r.get("kind") == "char" for r in refs):
            _scene = next((r for r in refs if r.get("kind") == "scene" and r.get("path")), None)
            if _scene and os.path.isfile(_scene["path"]):
                guide_imgs.append((comfy.upload_image(_scene["path"], prefix="anchor"), 0))
                print("  空镜锚定：场景图钉在第 0 帧")

        graph = graphs.h3_ref(ref_images=names, prompt=text, seconds=seconds, width=_vw,
                              height=_vh, seed=seed, prefix=prefix, steps=_steps,
                              lowvram=(_tier in ("w4a8", "low")),
                              guide_images=guide_imgs, ref_videos=ref_vids,
                              guide_clips=guide_clips, relay=relay,
                              interpolate=bool(_vcfg.get("interpolate")),
                              crf=int(_vcfg.get("crf") or 14), sage=_sage,
                              control_video=_ctrl, control_mode=_ctrl_mode,
                              control_strength=_ctrl_strength, model=_model)
    else:
        raise ValueError(f"未知引擎 {engine}，可选 h3 / h3ref")

    print(f"[{ep}/{sid}] {ENGINE_NAME.get(engine, engine)}  {seconds}s  {len(beats)} 拍  种子 {seed}")
    if dry:
        print(f"  提示词（{len(text.split())} 词）：\n{text}")
        return {"dry": True, "prompt": text, "problems": problems, "engine": engine}

    # 落一份"真提交出去的那张图"，出问题可以直接查节点接线
    try:
        _dump = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "out", "last_canvas_graph.json")
        with open(_dump, "w", encoding="utf-8") as _f:
            json.dump({"ep": ep, "sid": sid, "engine": engine, "graph": graph}, _f,
                      ensure_ascii=False)
    except Exception as _exc:  # noqa: BLE001 - 落盘失败不影响出片
        print(f"  ! 存图失败：{_exc}")

    _v = comfy.device_vram()
    if _v and _v.get("total_gb", 99) < 12:
        print(f"  ! 显存只有 {_v.get('total_gb')} GB（空闲 {_v.get('free_gb')} GB）：H3 很可能 OOM，"
              f"建议给 ComfyUI 加 --lowvram，详见 README「显存不够（OOM）」")

    hist = _submit_with_sage_fallback(
        graph, f"{ep}/{sid} 视频", _dump,
        {"ep": ep, "sid": sid, "engine": engine, "graph": graph})
    _all = comfy.produced(hist, ("videos", "gifs", "images"))
    # 只认 output 目录里、文件名带本镜前缀的产物。
    # relay 接线会把 input 里的上一段 mp4 也列进 outputs（kind=images），
    # 之前直接取 files[0] 就把那条旧片当成了产物（实测 11:53）。
    _tag = f"{ep}_{sid}_"
    files = [f for f in _all
             if f["filename"].lower().endswith((".mp4", ".webm", ".gif"))
             and f.get("type") == "output"
             and _tag in f["filename"]]
    if not files:
        files = [f for f in _all
                 if f["filename"].lower().endswith((".mp4", ".webm", ".gif"))
                 and f.get("type") == "output"]
    if not files:
        raise RuntimeError("跑完了但没有视频，看 ComfyUI 控制台")
    path = comfy.local_path(files[0])

    last_png = os.path.join(store.PROJECTS, store.slug(ep), "assets", f"{sid}_last.png")
    try:
        media.last_frame(path, last_png)
    except RuntimeError as e:
        print(f"  ! 抽末帧失败：{e}")
        last_png = ""

    # 首帧模式（FL2VA）没有参考图，refs 不会在上面被赋值——这里兜底，
    # 否则出完片在记账那一步抛 UnboundLocalError
    refs = locals().get("refs") or _shot_refs(ep, shot)
    _log_claim(ep, sid, path, text, refs, seed)

    # 黑场过渡（衔接选「黑场」时）：头尾各淡入淡出到黑，拼起来就是黑场转场。
    # 放在调色之前，这样调色处理的是已经带黑场的版本。
    raw_path = path
    if str((shot.get("video") or {}).get("link") or "").lower() == "black":
        try:
            faded = os.path.splitext(path)[0] + "_fade.mp4"
            media.fade_edges(path, faded, 0.3)
            path = faded
            print(f"✓ 黑场过渡（头尾各 0.3 秒）{os.path.basename(faded)}")
        except Exception as exc:  # noqa: BLE001 - 淡入淡出失败不该毁掉已生成的片
            print(f"  ! 黑场过渡失败，保留原片：{exc}")

    # 电影感调色（项目级 grade=cinematic 时自动做）：垂直渐变把地面压黑，
    # 这是模型自己做不到的（上/下亮度差模型最高 19.5，样例 34.3）。
    if str(proj.get("grade") or "").lower() == "cinematic":
        try:
            graded = os.path.splitext(path)[0] + "_graded.mp4"
            media.grade_cinematic(path, graded)
            path = graded
            print(f"✓ 电影感调色 {os.path.basename(graded)}")
        except Exception as exc:  # noqa: BLE001 - 调色失败不该毁掉已生成的片
            print(f"  ! 调色失败，保留原片：{exc}")

    info = media.probe(path)

    # 每镜再放一份 latest.mp4（同名覆盖）：不用记时间戳也能找到"这一镜最新的片"
    try:
        latest = os.path.join(os.path.dirname(path), "latest.mp4")
        shutil.copy2(path, latest)
        if raw_path != path:
            shutil.copy2(raw_path, os.path.join(os.path.dirname(path), "latest_raw.mp4"))
        path = latest
    except Exception as exc:  # noqa: BLE001 - 复制失败不该毁掉记录
        print(f"  ! latest 副本失败：{exc}")

    store.set_state(ep, sid, video=path, video_raw=raw_path, video_engine=engine, video_seed=seed,
                    video_mode=("fl2v" if engine == "h3" else "ref2v"),
                    video_prompt=text, video_seconds=info["duration"],
                    last_frame=last_png,
                    video_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"✓ 视频 {path}  {info['duration']}s {info['size']}")
    if last_png:
        print(f"✓ 末帧 {last_png}")
    return {"path": path, "prompt": text, "engine": engine, "seed": seed,
            "last_frame": last_png, "problems": problems}
