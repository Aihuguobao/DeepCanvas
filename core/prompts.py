"""提示词编译器。

分工是硬约束：
  生图（Krea2）吃「画面」——谁、多大、在哪、光怎么打、构图。
  生视频（H3）不吃画面细节——主体和风格已经被首帧钉死，再描述一遍等于让它站住不动。

这里只做两件事：按证据拼句子，以及把违反硬规则的写法当场拦下来。
"""
from __future__ import annotations

import json
import os
import re

from core import engines, vocab

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES = os.path.join(HERE, "styles")

# 运镜词表：写进 video.camera 就会被判为「有运动」
MOVE_WORDS = re.compile(
    r"\b(push(es|ing)? in|pull(s|ing)? back|pan(s|ning)?|tilt(s|ing)?|dolly|dollies|"
    r"track(s|ing)?|orbit(s|ing)?|arc(s|ing)?|crane(s|d)?|zoom(s|ing)?|shake|shakes|"
    r"handheld|whip|rise|rises|dive|dives|drift|drifts)\b", re.I)
STATIC_WORDS = re.compile(r"\b(static|locked[- ]off|still camera|no camera move(ment)?)\b", re.I)
GENDERED = re.compile(r"\b(he|she|his|her|him|hers)\b", re.I)
CHINESE = re.compile(r"[\u4e00-\u9fff]")
# 视频提示词里不该出现的「画面细节」：会跟动作抢注意力，还会把景别拉近
DETAIL_WORDS = re.compile(
    r"\b(sweat|sweating|breath|breathing|pores?|skin texture|fabric weave|hair strand|"
    r"veins?|saliva|tears)\b", re.I)


def style_names() -> list[str]:
    if not os.path.isdir(STYLES):
        return []
    return sorted(f[:-5] for f in os.listdir(STYLES) if f.endswith(".json"))


def render_text(name: str) -> str:
    name = str(name or "").strip()
    if not name:
        return _fallback_style()
    path = os.path.join(STYLES, f"{name}.json")
    if not os.path.isfile(path):
        # 不是预设 id，可能是两种东西，靠形状区分：
        #   ① 老项目里存过的、已经被删掉的画风 id（krea_old 这种短标识符）→ 回落，别让出片崩
        #   ② 用户自己在「自定义」里写的一句画风描述（有空格/逗号、或者明显更长）→ 原样用
        if len(name) > 20 or " " in name or "," in name or "，" in name:
            print(f"  · 画风用自定义句（{len(name)} 字）：{name[:60]}")
            return name
        print(f"  ! 画风 {name!r} 不存在，已回落")
        return _fallback_style()
    with open(path, encoding="utf-8") as f:
        return json.load(f)["render"].strip()


def _fallback_style() -> str:
    """画风不认识时的兜底句：写实照片。"""
    fallback = os.path.join(STYLES, "photoreal.json")
    if os.path.isfile(fallback):
        with open(fallback, encoding="utf-8") as f:
            return json.load(f)["render"].strip()
    raise FileNotFoundError(f"一个画风都没有：{STYLES}")


def style_label(name: str) -> str:
    """画风的中文名（下拉框显示用）；文件不在就退回 id。"""
    path = os.path.join(STYLES, f"{name}.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("zh", name)
    except (OSError, json.JSONDecodeError):
        return name


def style_options() -> list[dict]:
    """给前端的画风清单：[{id, zh, note}]，按文件名排序。"""
    out = []
    for sid in style_names():
        path = os.path.join(STYLES, f"{sid}.json")
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, json.JSONDecodeError):
            out.append({"id": sid, "zh": sid, "note": ""})
            continue
        out.append({"id": sid, "zh": d.get("zh", sid), "note": d.get("note", "")})
    return out


def _join(parts) -> str:
    out = []
    for p in parts:
        p = str(p or "").strip().rstrip(".")
        if p:
            out.append(p)
    return ". ".join(out) + "." if out else ""


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", text))


# ---------------------------------------------------------------- 生图
def framing_text(img: dict) -> str:
    """景别/机位/焦距：下拉里有就用固定英文短语，没有才回退到手写描述。"""
    bits = [vocab.english("size", img.get("size", "")),
            vocab.english("angle", img.get("angle", "")),
            vocab.english("lens", img.get("lens", ""))]
    bits = [b for b in bits if b]
    if bits:
        return ", ".join(bits)
    return str(img.get("shot") or "medium shot").strip()


def composition_text(img: dict) -> str:
    """构图三件套：站哪、看哪、前景是什么。

    依据：AI 默认会给"居中 + 看镜头 + 背景糊"的保底构图，成品精致但像 PPT。
    这几条必须显式写，否则模型一定走保底。
    """
    bits = [vocab.english("position", img.get("position", "")),
            vocab.english("gaze", img.get("gaze", "")),
            vocab.english("foreground", img.get("foreground", ""))]
    return ", ".join(b for b in bits if b)


def light_text(img: dict) -> str:
    """光/景深/色调：同样是下拉优先，回退到手写 light。"""
    bits = [vocab.english("light", img.get("light_key", "")),
            vocab.english("depth", img.get("depth", "")),
            vocab.english("tone", img.get("tone", ""))]
    bits = [b for b in bits if b]
    if bits:
        return ", ".join(bits)
    return str(img.get("light") or "").strip()


def image_prompt(shot: dict, style: str, which: str = "head") -> str:
    """画面描述 + 画风尾句。which=tail 时取 image.tail（尾帧该到的状态）。"""
    img = shot.get("image") or {}
    if which == "tail":
        # 主体必须带：少了 subject，模型会连人带景一起重编，尾帧就成了另一条片子
        body = _join([framing_text(img), img.get("scene"), img.get("subject"),
                      img.get("tail"), light_text(img)])
    else:
        body = _join([
            framing_text(img),
            img.get("scene"),
            img.get("subject"),
            img.get("action"),
            light_text(img),
        ])
    render = render_text(style)
    return f"{body} {render}".strip()


def check_causality(shot: dict) -> list[str]:
    """动作因果自检（文章：写因果，不写形容词）。

    四问：谁先动手 / 接触点 / 道具落点 / 结尾状态。
    缺了不报错，只提醒——写不写是用户的自由，但要让他知道缺什么。
    """
    v = shot.get("video") or {}
    text = " ".join([str(v.get("summary") or v.get("action") or "")]
                    + [str(b) for b in (shot.get("beats") or [])])
    text = text.strip()
    if not text:
        return []

    contact = re.search(r"抓|攥|拽|拉|推|抱|碰|触|贴|递|接|按|握|拍|推|撞|"
                        r"奔|跑|冲|逃|追|跃|跳|摔|滑|跌|蹬|踩|扑|翻|滚|"
                        r"grab|grip|pull|push|hold|touch|hand|reach|hug|"
                        r"run|sprint|flee|chase|leap|jump|fall|slip|stumble|land|roll", text, re.I)
    prop = re.search(r"扳手|刀|枪|杯|包|门|钥匙|手电|检查板|箱|绳|管|"
                     r"wrench|knife|gun|cup|bag|door|key|torch|clipboard|rope|pipe", text, re.I)
    result = re.search(r"停|落|掉|松|倒|碎|响|关|开|垂|坐|蹲|转身|退|"
                       r"stops|lands|drops|closes|opens|falls|turns|settles", text, re.I)
    order = re.search(r"先|然后|接着|随即|随后|一…就|"
                      r"then|after|before|first|finally", text, re.I)

    issues = []
    if len(shot.get("beats") or []) >= 2 and not order:
        issues.append("拍子有两拍以上，但没有先后词（先/然后/接着）——模型可能把两拍并成一拍")
    if contact is None:
        issues.append("没写接触点：谁碰到谁、碰到哪里。只写情绪模型不知道怎么动")
    if prop is not None and result is None:
        issues.append("提到了道具，但没说道具最后落在哪（放下/落地/被接过）")
    return issues


def check_image_prompt(text: str) -> list[str]:
    issues = []
    # 中文本身没问题（Qwen 官方支持简中/英文，实测同种子出图一致），
    # 只有"多人互动 + 中文"这一种组合会丢人，那条检查在 build() 里单独做。
    if _words(text) > 220:
        issues.append(f"生图提示词 {_words(text)} 词，偏长；细节词一多，跨镜头的画风会散")
    return issues


def image_prompt_ref(shot: dict, style: str, refs: list[tuple[str, str]] | None = None,
                     char_refs: int = 1, scene_refs: int = 0) -> str:
    """挂了参考图时的写法：编号 + **角色标签**绑定，不再复述长相。

    refs: [(标签, "char"|"scene")]，顺序就是图片顺序（角色在前、场景在后）。
    官方示例是 "the girl from Image 1, wearing the dress from Image 2"——
    编号负责指认，标签负责说明"这张是谁"，两者缺一模型就会自己乱配。
    """
    img = shot.get("image") or {}
    framing = framing_text(img)
    refs = refs or ([("the subject", "char")] * char_refs
                    + [("the location", "scene")] * scene_refs)

    char_bits, scene_bits = [], []
    for i, (label, kind) in enumerate(refs, start=1):
        # 没有自定义标签时只用编号+中性名词，绝不猜"这是什么"——
        # 猜错（把男人叫成 cat）会让文字压过参考图。
        fallback = "the location" if kind == "scene" else "the subject"
        bit = f"{label or fallback} from Image {i}"
        (scene_bits if kind == "scene" else char_bits).append(bit)

    subject = ""
    if char_bits:
        subject = char_bits[0] if len(char_bits) == 1 else " and ".join(char_bits)

    # 场景只有两个来源，二选一，不混：
    #   勾了带参考图的场景卡 → 场景完全由图决定（不再读文字）
    #   没有场景参考图       → 才用文字
    if scene_bits:
        place = " and ".join(scene_bits)
    else:
        place = str(img.get("scene") or "").strip()
    if place:
        subject = f"{subject} in {place}" if subject else f"in {place}"
    head = f"{framing}, of {subject}."
    # 光/景深/色调是"怎么看"的参数，用户选了就必须进提示词——
    # 场景参考图只替代"场景长什么样"，不替代打光和色调。
    look = light_text(img)
    comp = composition_text(img)
    fields = [img.get("action"), comp, look]
    body = _join(fields)
    if body:
        body = body[0].upper() + body[1:]
    keep = ("Keep every subject exactly as in the reference images: same face, hair, "
            "clothing and proportions.")
    # 声明画面人数：不写就会多画人（实测：两张角色参考图，出了三个身影，
    # 甚至是同一个人的复制体）。所以要逐个点名"一个实例"，而不是只写总数。
    n = len(char_bits)
    if n == 1:
        keep += (" Exactly one person in frame, no other figures, no duplicate of them.")
    elif n >= 2:
        who = " and ".join(f"one instance of the subject from Image {i}"
                           for i in range(1, n + 1))
        keep += (f" The frame contains exactly {who} — no third person, "
                 f"no duplicate or copy of any of them.")
    return " ".join(p for p in (head, body, keep, render_text(style)) if p).strip()


# ---------------------------------------------------------------- 视频
def video_prompt(shot: dict, style: str, engine: str = "h3ref") -> str:
    """按引擎出视频提示词。

    输入统一是"六段"（见 _sections），输出按引擎变：
      H3 / Ref2VA → **官方三字段格式**（见 reference/h3_official_prompt_guide.md）
    """
    v = shot.get("video") or {}
    move = v.get("move") or ""
    return _h3_official(shot, style, move)


def _h3_official(shot: dict, style: str, move: str) -> str:
    """H3 官方格式：指令行 + 三个核心字段。

    依据 `_agent/reference/h3_official_prompt_guide.md`：
      1. 第一行是对齐指令（I2VA / FL2VA），后跟一个空行
      2. integrated_multimodal_description：先立风格/景别/主体锚点，再写动作链和运镜
      3. overall_soundscape：环境声 + 动作声 + 非语言人声
      4. non_diegetic_music：只写配器/速度/力度，没有写 N/A
    """
    v = shot.get("video") or {}
    # 首帧模式手写整段（画布「首帧提示词」框）：有就原样用，不再拼六段。
    # 但保留项要接上——用户填了「哪些东西不能变」，不该因为改用整段就被丢掉。
    # 顺序：项目级全剧保留项在前，本镜保留项在后；两者相同只留一份。
    if str(v.get("fl2v_text") or "").strip():
        base = str(v["fl2v_text"]).strip()
        keeps = []
        for item in (str(shot.get("_retention") or "").strip(),
                     str(v.get("retention") or "").strip()):
            if item and item not in keeps:
                keeps.append(item)
        if keeps:
            base = (base.rstrip().rstrip("。.") + ".\n\n"
                    + "Keep unchanged throughout: "
                    + "; ".join(k.rstrip().rstrip("。.") for k in keeps) + ".")
        return base
    s6 = _sections(shot, style, framing=False)
    img = shot.get("image") or {}
    seconds = float(shot.get("seconds") or 6)
    has_tail = bool((shot.get("state") or {}).get("tail_frame"))

    # ---- 1. 指令行
    if has_tail:
        instr = ("How the reference pictures align with the target video — "
                 "Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
                 f"Picture 2 (from Shot 1) aligns with the {seconds:.2f}-second mark of the target video.")
    else:
        instr = ("For the target video, at 0.00 seconds into the target video, "
                 "<Picture 1> (from [Shot 1]) is fully referenced.")

    # ---- 2. 多模态描述：风格 → 景别 → 主体锚点 → 动作链 → 运镜
    parts = []
    framing = (str(v.get("shot") or "").strip()
               or vocab.english("size", img.get("size", ""))
               or "medium shot")
    parts.append(f"[Shot 1] {engines.h3_style(style)}, {framing}.")
    parts.append("The subjects shown in <Picture 1> keep their appearance, clothing and the "
                 "layout of the scene unchanged.")
    if s6["summary"]:
        parts.append(s6["summary"].rstrip("。.") + ".")
    beats = s6.get("_beats") or []
    if len(beats) > 1:
        parts.append("In order: " + "; ".join(b.rstrip("。.") for b in beats) + ".")
    cam = engines.h3_move(move)
    if cam:
        parts.append(f"The camera {cam}.")

    music = (v.get("music") or "").strip()
    if not music or music.lower() in ("none", "no music", "无"):
        music = "N/A"

    return "\n".join([
        instr,
        "",
        "integrated_multimodal_description: " + " ".join(parts),
        "overall_soundscape: " + s6["overall_soundscape"],
        "non_diegetic_music: " + music,
    ])


# 需求：场景参考图引入视频时，把镜头锁在这场戏的这个房间里。
# 允许简单运镜（推进 / 拉远 / 小幅转动），但不许把相机带到别的空间。
def _sections(shot: dict, style: str, framing: bool = True) -> dict[str, str]:
    """把一镜拆成六段。这是输入层的唯一真相，两个引擎都从这里取。

    subject_definitions     谁/在哪（来自角色卡、场景卡，或手填）
    summary                 这段要发生什么（一句话）
    retention_analysis      跨镜必须保留什么（自动 + 手填补充）
    detailed_description    逐拍画面/表演/机位/运镜
    overall_soundscape      环境声
    non_diegetic_music      配乐
    """
    v = shot.get("video") or {}
    img = shot.get("image") or {}
    beats = [str(b).strip() for b in (shot.get("beats") or []) if str(b).strip()]
    move = v.get("move") or ""

    subject = str(v.get("subject_definitions") or "").strip()
    if not subject:
        parts = [str(v.get("character") or "").strip(), str(v.get("scene") or "").strip()]
        subject = "; ".join(p for p in parts if p) or "the subjects already in the first frame"

    summary = str(v.get("summary") or v.get("action") or "").strip()
    if not summary and beats:
        summary = ", ".join(beats) if engines.get("h3") else " ".join(beats)

    # 保留项：身份/服装/道具/一镜到底，是硬底；再叠"全剧保留"和"本镜补充"。
    # 文章原话：先决定哪些特征必须跨镜保留，再开始写场面。
    # 全剧清单由 server 注入到 shot["_retention"]（项目级），本镜的写在 video.retention。
    keep = ("faces, hair, clothing and props stay identical to the first frame; "
            "one continuous take, no cut")
    if img.get("subject"):
        keep += f"; {img['subject']}"
    story_keep = str(shot.get("_retention") or "").strip()
    if story_keep:
        keep += f"; {story_keep}"
    extra_keep = str(v.get("retention") or "").strip()
    if extra_keep and extra_keep != story_keep:
        keep += f"; {extra_keep}"

    detail = "; ".join(beats) if beats else summary
    if framing and v.get("shot"):
        detail = f"framing {v['shot']}; {detail}"
    extra_detail = str(v.get("description") or "").strip()
    if extra_detail:
        detail += f"; {extra_detail}"

    return {
        "_beats": beats,
        "subject_definitions": subject,
        "summary": summary,
        "retention_analysis": keep,
        "detailed_description": detail,
        "overall_soundscape": str(v.get("soundscape") or v.get("audio")
                                  or "ambient sound of the location").strip(),
        "non_diegetic_music": str(v.get("music") or "none").strip() or "none",
    }


def bind_names(text: str, refs: list[dict]) -> tuple[str, list[str]]:
    """把角色名换成 `<Subject N>`。

    名字是给人看的，模型不认识具体人名：没定义就是噪声，
    定义了又等于多塞一个身份源。官方规范里主体一律用标签指代。
    返回 (新文本, 被替换掉的名字列表)。
    """
    hits = []
    # 名字 → <Subject N>：按"第几个不同名字"编号，和 subject_definitions 的主体序号一致。
    # 以前用参考图序号，两人时会变成 <Subject 5>（剑修主图是第 5 张图），
    # 而正文/动作写的是 <Subject 2>，两套编号互相打架。
    seen: dict[str, int] = {}
    for r in refs:
        nm = str(r.get("name") or "").strip()
        if nm and nm not in seen:
            seen[nm] = len(seen) + 1
    pairs = sorted(seen.items(), key=lambda x: -len(x[0]))
    for name, i in pairs:
        if name and name in text:
            text = text.replace(name, f"<Subject {i}>")
            hits.append(name)
    # 翻译产物里常见的 @1 / Image 1，一并归一成标签（视频端只认标签）
    for i in range(1, len(refs) + 1):
        for pat in (f"@{i}", f"the subject in Image {i}", f"Image {i}"):
            if pat in text:
                text = text.replace(pat, f"<Subject {i}>")
    return text, hits


PLACEHOLDER_NAME = re.compile(r"^(角色|场景|人物|镜头|char|character|scene|person|subject)\s*\d*$", re.I)


def useful_name(name: str) -> str:
    """占位名（角色1/场景2/Character 1）对模型没有信息量，不写进提示词。"""
    n = str(name or "").strip()
    return "" if PLACEHOLDER_NAME.match(n) else n


def _speech_breaks(text: str) -> str:
    """在每对 </d> 之后强制断句。

    官方 4.4：`<d>` 内**只放语言标签和原话**。实测：如果 </d> 后面直接
    跟舞台指示，模型会把后面的描述当成台词一起念出来——观测到的发音是
    「哎，等一下！突然一愣的表情，停下脚步没有转头。」
    所以这里补一个句号加换行，把台词和后续动作切成两句。
    """
    if "</d>" not in text:
        return text
    out, i = [], 0
    while True:
        j = text.find("</d>", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j + 4])
        nxt = text[j + 4:j + 5]
        if nxt and nxt not in "。．.！？!?；;，,\n":
            out.append("。\n")
        i = j + 4
    return "".join(out)


def h3_ref_prompt(shot: dict, style: str, move: str, refs: list[dict]) -> str:
    """Ref2VA 六段式（官方全参考模式）。

    来源：`_agent/reference/h3_ref2va_official.md`（MiniMax VIDEO_PROMPT_WRITING_GUIDE_ref_en）。
    三条关键规矩：
      1. `<Subject N>` 承载"会在片子里出现的内容"（人/物/场景/服装），
         `<Picture N>` **只用于帧锚点**（首帧/关键帧/末帧）。拿 <Picture> 承载脸是头号结构错误。
      2. 外观细节要**点名**：落在身体部位上、说明左右、能拿帧核对；图不会自己描述自己。
      3. Ref2VA 用 `detailed_description`（不是 integrated_multimodal_description），
         风格句写在 `[Shot 1]` **之前**。
    """
    v = shot.get("video") or {}
    img = shot.get("image") or {}
    seconds = float(shot.get("seconds") or 6)
    # 手写优先：镜头上直接写了 subject_definitions / description 时原样用，不再自己重拼
    manual_subj = str(v.get("subject_definitions") or "").strip()
    if manual_subj.lower().startswith("subject_definitions:"):
        manual_subj = manual_subj.split(":", 1)[1].strip()
    manual_detail = str(v.get("description") or "").strip()
    beats = [str(b).strip() for b in (shot.get("beats") or []) if str(b).strip()]
    summary = str(v.get("summary") or v.get("action") or "").strip()

    # ---- subject_definitions：一个主体一行（官方 Ref2VA 的规定）
    # 一张图只承担一个主要职责。同一人的多角度/表情/服装是同一主体的**补充素材**，
    # 不能各自成为 <Subject N>——否则模型会把 9 张图当成 9 个实体，身份互相竞争：
    # 实测表现为编码变慢、细节被平均掉（发冠消失）、两个人各站画面一边。
    views_of: dict[int, list[int]] = {}
    for i, r in enumerate(refs, start=1):
        if str(r.get("role") or "main") == "view":
            views_of.setdefault(int(r.get("of") or 0) or 1, []).append(i)

    subj_lines = []
    narr = []      # 只收主体，正文指代用
    narr_refs = [] # 主体的 (标签, 参考) 对，summary 用（不能拿 zip 硬对，中间有 view）
    subj_no = 0
    for i, r in enumerate(refs, start=1):
        role = str(r.get("role") or "main")
        if role == "view":
            continue
        subj_no += 1
        look = str(r.get("look") or "").strip()
        outfit = str(r.get("outfit") or "").strip()
        props = str(r.get("props") or "").strip()
        if r.get("kind") == "scene":
            kind = "the location"
        elif r.get("kind") == "prop":
            kind = "the prop"
        else:
            kind = "the person"
        # 人名一律不写进提示词：模型只需要 <Subject N>，名字只留在界面上
        extra = views_of.get(i) or []
        pics = f"<Picture {i}>" + "".join(f", <Picture {j}>" for j in extra)
        # 说话人 ID 必须挂在这个人物身上（官方 4.4：首次出现要交代音高/音色/语速）。
        # 只写一句 "(S2) says:" 而不绑定，双人场景里模型不知道是谁在说，会把动作也念进去。
        spk = str(r.get("speaker") or "").strip()
        what = f"<Subject {subj_no}>" + (f" ({spk})" if spk else "") + f" is {kind} defined by {pics}"
        detail_parts = [x for x in (look, outfit, props) if x]
        voice = str(r.get("voice") or "").strip()
        if voice:
            detail_parts.append(f"说话{voice}")
        detail = "; ".join(detail_parts)
        if detail:
            what += f": {detail}"
        # 角色参考是棚拍图，那张图的无缝背景会和场景参考抢背景权——
        # 官方 reference-mode 明说"无缝背景也是与目标场景竞争的可见内容"。
        if r.get("kind") == "scene":
            pass   # 场景不追加任何硬编码锁
        elif r.get("kind") == "prop":
            # 道具卡是棚拍产品图，它的纯色背景同样会抢场景权，必须点名排除
            what += (". Only this single object is taken from this picture; it is one object, "
                     "never duplicated, and its plain studio backdrop is not part of the scene.")
        else:
            what += ". Only the person is taken from this picture; its plain studio backdrop is not part of the scene."
        subj_lines.append(what)
        narr.append(f"<Subject {subj_no}>")
        narr_refs.append((f"<Subject {subj_no}>", r))

    # ---- retention_analysis：每个 Subject 一行，用官方受控词
    keep_lines = []
    subj_no = 0
    for i, r in enumerate(refs, start=1):
        if str(r.get("role") or "main") == "view":
            continue
        subj_no += 1
        # 人写"身份/服装/道具"，场景写"是唯一场景、不引入额外房间"——
        # 场景套用人的模板等于没给职责（官方：没有明确职责的参考是头号失败）。
        if r.get("kind") == "scene":
            keep_lines.append(f"<Subject {subj_no}> (appears in [Shot 1]): fully_preserved - "
                              f"this location is the only set: its surfaces, materials and "
                              f"lighting are retained, and no additional room, backdrop or "
                              f"studio is introduced.")
        elif r.get("kind") == "prop":
            keep_lines.append(f"<Subject {subj_no}> (appears in [Shot 1]): fully_preserved - "
                              f"object identity, size, material, colour and surface wear are "
                              f"retained; it stays one single object throughout the shot.")
        else:
            keep_lines.append(f"<Subject {subj_no}> (appears in [Shot 1]): fully_preserved - "
                              f"identity, clothing and props as defined above are retained.")

    # ---- detailed_description：风格句在 [Shot 1] 之前
    framing = (str(v.get("shot") or "").strip()
               or vocab.english("size", img.get("size", "")) or "medium shot")
    style_line = f"The target video is in a {engines.h3_style(style).lower()} style."
    # 这一镜里有没有"人"：只有场景参考时，整段必须走纯环境文案（见下方注释）
    # 道具卡不算"人"——否则只有场景+道具的空镜会被写成人镜
    has_char = any(str(r.get("kind") or "") == "char" for r in refs)
    # 几个"人"：单人/多人要换人称，复数会暗示画面里还有别人（实测背景多出人影）
    n_chars = sum(1 for r in refs if str(r.get("kind") or "") == "char"
                  and str(r.get("role") or "main") != "view")
    who = " and ".join(narr) or "the subject"
    scene_first = next((i for i, r in enumerate(refs, start=1) if r.get("kind") == "scene"), 0)
    if has_char:
        shot_bits = [f"[Shot 1] A {framing} of {who}."]
    else:
        # 纯场景镜：景别字段常是中文（"竹林"），拼进英文句子会成病句
        shot_bits = [f"[Shot 1] The location shown in <Picture {scene_first}>, seen from a new angle."]
    for lbl in narr:
        shot_bits.append(f"{lbl} keeps the appearance defined above.")
    # 站位/相对大小：参考图各自取景松紧不同，模型会把这当成"人真的更大"
    staging = str(v.get("staging") or "").strip()
    if staging:
        shot_bits.append(bind_names(staging, refs)[0].rstrip("。.") + ".")
    if has_char:
        # 单人镜头不能写 "All subjects… they…"：复数人称会暗示画面里还有别人，
        # 实测背景里多出一个疑似人影。单人就全用单数。
        if n_chars <= 1:
            shot_bits.append("The subject keeps one consistent body scale in frame; the reference picture "
                             "only defines appearance, never a different body size.")
        else:
            shot_bits.append("All subjects share one consistent body scale in the frame, whether they sit or "
                             "stand; each reference picture only defines appearance, never a different body "
                             "size.")
    if summary:
        shot_bits.append(bind_names(summary, refs)[0].rstrip("。.") + ".")
    if len(beats) > 1:
        shot_bits.append("In order: " + "; ".join(bind_names(b, refs)[0].rstrip("。.")
                                                       for b in beats) + ".")
    # 角色参考是棚拍图，背景会被一起抄走；明确要求背景只来自场景参考
    scene_idx = next((i for i, r in enumerate(refs, start=1)
                      if r.get("kind") == "scene"), 0)
    # 这一镜里有没有"人"：只有场景参考时，光照段必须走纯环境文案（见下方注释）
    has_char = any(str(r.get("kind") or "") == "char" for r in refs)
    if scene_idx:
        if has_char:
            shot_bits.append(
                f"The background is the space shown in <Picture {scene_idx}>, and only that place "
                f"appears behind the subject; the plain backdrops of the other pictures never appear.")
        else:
            # 纯场景镜里不能再出现 "behind the subject"——subject 就是"人"
            shot_bits.append(
                f"The frame shows only the space in <Picture {scene_idx}>; the plain backdrops of "
                f"any other picture never appear.")
        # 官方硬要求 detailed_description 写 "environment and lighting"。
        # 缺这一段，人物会沿用参考图的棚拍光、场景是另一个光，看着像贴上去的。
        scene_ref = next((r for r in refs if r.get("kind") == "scene"), {}) or {}
        scene_light = str(scene_ref.get("light") or "").strip()
        light_line = f"The environment and lighting come from <Picture {scene_idx}>."
        if scene_light:
            light_line += f" {scene_light.rstrip('。.')}."
        # 纯场景镜（没有人物主体）必须换一段文案：原来的光照段里有 "the person's face"、
        # "the person must look lit"、"body scale" 等 6 处把人当前提的说法。
        # 实测：只有场景参考时，这段话会让模型凭空造一个人出来——
        # 去掉这 6 处之后同种子同场景板，画面全空。见 runs/_2151_empty-probe/。
        if has_char:
            if n_chars <= 1:
                light_line += (" The scene's light falls on her face, hair and clothing so her skin and "
                               "fabric take the scene's colour temperature. She casts a real contact "
                               "shadow onto the ground and nearby surfaces, the shadow falls away from "
                               "the main light source, and the surfaces around her bounce their own colour "
                               "back onto her shadow side. Use one dominant key light from the scene and "
                               "match the scene's exposure exactly; never lift the exposure on the face. "
                               "She must look lit by this place, not by a photo studio.")
            else:
                light_line += (" The scene's light falls on the person's face, hair and clothing so their "
                               "skin and fabric take the scene's colour temperature. They cast a real "
                               "contact shadow onto the ground and nearby surfaces, the shadow falls away "
                               "from the main light source, and the surfaces around them bounce their own "
                               "colour back onto their shadow side. Use one dominant key light from the "
                               "scene and match the scene's exposure exactly; never lift the exposure on "
                               "the face. The person must look lit by this place, not by a photo studio.")
        else:
            light_line += (" The light falls on the surfaces of this place — the trunks, the leaves, "
                           "the wet ground and the puddles — so their colour and texture read clearly. "
                           "Soft shadows move across them as the air moves. Use one dominant key light "
                           "from the scene and match the reference's exposure exactly; keep the mood, "
                           "the palette and the depth of the place.")
        shot_bits.append(light_line)
    cam = engines.h3_move(move)
    if cam:
        shot_bits.append(f"The camera {cam}.")
    # 与上一镜的衔接（B 钉末帧 / C 参考视频）：文案必须和实际接线一致
    link = str(v.get("link") or "none").lower()
    if link in ("frame", "both", "latent"):
        shot_bits.append("This shot starts exactly on the last frame of the previous shot; "
                         "keep the same camera direction, lighting and prop positions.")
    if link in ("video", "both"):
        shot_bits.append("Use <Video 1> as the motion and camera reference and continue from it.")
    if has_char:
        shot_bits.append("One continuous take, no cuts, nobody looks into the lens.")
    else:
        # 纯场景镜里 "nobody looks into the lens" 本身就在暗示有张脸
        shot_bits.append("One continuous take, no cuts.")

    music = (v.get("music") or "").strip()
    if not music or music.lower() in ("none", "no music", "无"):
        music = "N/A"

    return "\n".join([
        "subject_definitions:",
        manual_subj or "\n".join(subj_lines),
        "",
        "summary:",
        "[reference generation] "
        + " ".join(f"{lbl} is the reference for the {'location' if r.get('kind') == 'scene' else 'person'}."
                   for lbl, r in narr_refs)
        + ((" " + bind_names(summary, refs)[0].rstrip("。.") + ".") if summary else ""),
        "",
        "retention_analysis:",
        "\n".join(keep_lines),
        "",
        "detailed_description:",
        _speech_breaks(manual_detail or (style_line + " " + " ".join(shot_bits))),
        "",
        "overall_soundscape:",
        _sections(shot, style, framing=False)["overall_soundscape"],
        "",
        "non_diegetic_music:",
        music,
    ])


def h3_prompt(shot: dict, style: str) -> str:
    """H3 要一整段散文：动作在前，外观环境在后，画风单独一段。"""
    v = shot.get("video") or {}
    head = _join([v.get("action"), v.get("character")])
    scene = _join([v.get("scene"), v.get("camera"), v.get("audio")])
    return " ".join(x for x in (head, scene, render_text(style), "One continuous take, no cuts.") if x)


def check_video_prompt(text: str, has_beats: bool = True, engine: str = "h3ref") -> list[str]:
    """提示词自检：H3 中文可用，英文更稳；画面细节词不该出现在视频提示词里。"""
    issues = []
    n = _words(text)
    if n > 80:
        issues.append(f"提示词 {n} 词，偏长；删场景修饰、留动作（官方建议正文 350–500 英文词，Ref2VA 六段合计）")
    hits = sorted({m.group(0).lower() for m in DETAIL_WORDS.finditer(text)})
    if hits:
        issues.append(f"视频提示词里有画面细节词 {hits}：会和动作抢注意力，把它挪到生图那边")
    if STATIC_WORDS.search(text) and MOVE_WORDS.search(text):
        m = MOVE_WORDS.search(text).group(0)
        issues.append(f"自相矛盾：写了静态机位，又写了运动词「{m}」")
    return issues


def check_beats(beats: list[str], engine: str = "h3ref") -> list[str]:
    issues = []
    for i, b in enumerate(beats, 1):
        if _words(b) > 45:
            issues.append(f"第 {i} 拍 {_words(b)} 词，太长；一段里塞太多动作会互相抵消")
    return issues


# ---------------------------------------------------------------- 汇总
def expand_refs(text: str, refs: list[dict]) -> str:
    """把各种人类叫法统一换成模型能读的槽位指代。

    refs: [{"name": "角色1", "label": "...", "kind": "char"}, ...]，顺序 = 图片顺序。
    认这些写法：`@1`、`角色1`、卡片英文标签、`Character 1` / `character1` /
    `Person 1` / 裸 `Image 1`。为什么连英文都要管：LLM 翻译会把"角色1"译成
    "Character 1"，模型不认识这个词，槽位就断了（实测：方向直接反过来）。
    """
    out = str(text or "")
    n = len(refs)

    def token(i: int) -> str:
        return ("the location in Image %d" % i) if refs[i - 1].get("kind") == "scene" \
            else ("the subject in Image %d" % i)

    # 1) 先把已经是规范写法的片段保护起来，避免二次替换
    out = re.sub(r"(?i)the (?:subject|location) in Image (\d)",
                 lambda m: f"\x00IMG{m.group(1)}\x00", out)

    # 2) 裸 Image N（先做：后两步会生成 "the subject in Image N"，再做就会二次替换）
    out = re.sub(r"(?i)\bImage\s*[-_]?\s*(\d)\b",
                 lambda m: token(int(m.group(1))) if 1 <= int(m.group(1)) <= n else m.group(0), out)

    # 3) 英文角色写法：Character 1 / character1 / Person 2 / Subject 3
    out = re.sub(r"(?i)\b(?:character|person|subject)\s*[-_]?\s*(\d)\b",
                 lambda m: token(int(m.group(1))) if 1 <= int(m.group(1)) <= n else m.group(0), out)

    # 4) @N
    for i in range(1, n + 1):
        out = out.replace(f"@{i}", token(i))

    # 5) 卡片名 / 英文短标签
    for i, r in enumerate(refs, start=1):
        for key in ("name", "label"):
            v = str(r.get(key) or "").strip()
            if v:
                out = out.replace(v, token(i))

    # 6) 还原保护过的片段
    return re.sub(r"\x00IMG(\d)\x00",
                  lambda m: token(int(m.group(1))) if 1 <= int(m.group(1)) <= n else f"Image {m.group(1)}",
                  out)


def video_text_for(ep: str, shot: dict, proj: dict) -> tuple[str, list[dict]]:
    """唯一入口：算出这一镜**真正发给 ComfyUI** 的视频提示词。

    画布预览和 steps/video.py 都调这个函数，任何一方改格式，另一方立刻同步——
    以前预览走 prompts.build、出片走 steps/video.py，两边各拼一遍，
    结果预览显示三字段、实际发的是六段。
    """
    from . import refs as refs_mod  # 局部导入避免 core 内部循环

    ref_list = refs_mod.shot_refs(ep, shot)
    s = dict(shot)
    # 允许整段覆盖：填了 raw_prompt 就原样发（只做标签归一），
    # 用来对照官方模板那种行内指派写法
    raw = str((shot.get("video") or {}).get("raw_prompt") or "").strip()
    if raw:
        text, _ = bind_names(raw, ref_list)
        # 手写整段通常一个 <Subject> / <Picture> 都不提 → 8 张图等于没有任何文字绑定，
        # 模型对它们的取用完全自由（实测：同一张哑铃卡，S05 用上了、S12 没用上）。
        #
        # 第二次修：第一版把 subject_definitions 整块放在**最前面**，
        # 结果道具的长描述占了开头、被模型当成重点——S12 里哑铃被放大、男主只剩半个身子、
        # 脑袋还接错位置。改成：
        #   ① 绑定块放**末尾**，开头仍然是用户写的动作和景别；
        #   ② 道具只写"是哪张图里的那一件"，不复述外观长描述（图自己会描述）；
        #   ③ 末尾补一句优先级：人物和动作是本镜重点，道具只是陪衬、不许改构图。
        if "<Subject" not in text and ref_list:
            _s = dict(s)
            _s["_retention"] = str(proj.get("retention") or "").strip()
            _style = shot.get("style") or proj.get("style") or "cgphoto"
            _move = (shot.get("video") or {}).get("move") or ""
            _full = h3_ref_prompt(_s, _style, _move, ref_list)
            _hit = re.search(r"subject_definitions:\n(.*?)\n\n", _full, re.S)
            if _hit:
                _lines = []
                for _ln in _hit.group(1).strip().splitlines():
                    if " is the prop defined by " in _ln:
                        _ln = re.sub(r": .*?\. Only this single object",
                                     ". Only this single object", _ln)
                    _lines.append(_ln)
                text = (text.rstrip() + "\n\nsubject_definitions:\n" + "\n".join(_lines)
                        + "\n\npriority: the people and the action described above are the subject of "
                          "this shot; framing, faces and bodies follow that description. The prop is a "
                          "supporting object only and never changes the framing.")
        return text, ref_list
    s["_retention"] = str(proj.get("retention") or "").strip()
    style = shot.get("style") or proj.get("style") or "cgphoto"
    move = (shot.get("video") or {}).get("move") or ""
    text = h3_ref_prompt(s, style, move, ref_list)
    text, _ = bind_names(text, ref_list)
    return text, ref_list


def build(shot: dict, style: str, char_refs: int = 0, scene_refs: int = 0,
          refs: list[tuple[str, str]] | None = None, engine: str = "h3ref",
          ref_full: list[dict] | None = None) -> dict:
    """返回这一镜要送进模型的两段文字 + 全部告警。

    refs: [(标签, "char"|"scene")]，由调用方按图片顺序给出。
    ref_full: 完整参考信息（带 look/outfit/props），Ref2VA 与标签归一要用它。
    engine: 视频引擎，决定视频那段怎么拼（h3ref 六段 / h3 三字段）。
    """
    total = (len(refs) if refs else char_refs + scene_refs)
    image_text = image_prompt(shot, style)
    image_ref = (image_prompt_ref(shot, style, refs=refs, char_refs=char_refs,
                                  scene_refs=scene_refs) if total else "")
    img = image_ref or image_text
    if engine == "h3ref":
        vid = h3_ref_prompt(shot, style, (shot.get("video") or {}).get("move") or "",
                            ref_full or [])
    else:
        vid = video_prompt(shot, style, engine)
    # 预览和出片走同一个归一：名字 / @N / Image N → <Subject N>
    if ref_full:
        vid, _ = bind_names(vid, ref_full)
    beats = [b for b in shot.get("beats") or [] if str(b).strip()]
    problems = (check_image_prompt(img) + check_video_prompt(vid, engine=engine)
                + check_beats(beats, engine=engine) + check_causality(shot))
    action = str((shot.get("image") or {}).get("action") or "")
    if total >= 2 and CHINESE.search(action):
        problems.append(
            "多主体互动时，动作句子要用**英文**：实测中文谓语 + 名词短语仍会丢掉一个主体。"
            "模板：the subject in Image 1 puts a hand on the waist of the subject in Image 2")
    if total >= 2 and re.search(r"<\s*image\s*\d\s*>", action, re.I):
        problems.append(
            "动作里用了 <image1> 语法：那是 Qwen-Image-2.1 的写法，本机 2511 不认（实测只出 1 人）。"
            "改成 the subject in Image 1 / the subject in Image 2")
    if total >= 2 and re.search(r"(?<!the subject in )\bImage \d\b", action) and "the subject in" not in action:
        problems.append(
            "动作里用了裸编号（Image 1 / Image 2）：模型不把它当主语，会只留一个人。"
            "要写成 the subject in Image 1 … the subject in Image 2 …")
    if total and (shot.get("image") or {}).get("size") in ("cu", "mcu", "ecu") and char_refs >= 2:
        problems.append(
            "景别是特写/近景，但这一镜有两个角色：画面装不下两个人，模型会丢掉一个。"
            "改成中景（ms）或全景（fs）")
    scene_text = str((shot.get("image") or {}).get("scene") or "").strip()
    if scene_refs and scene_text:
        scene_source = "ref+text"      # 图打底，文字是改动
    elif scene_refs:
        scene_source = "ref"
    elif scene_text:
        scene_source = "text"
    else:
        scene_source = "none"
    if image_ref and GENDERED.search(str((shot.get("image") or {}).get("action") or "")):
        problems.append("画面描述里用了 he/she：参考图的人未必对得上这个性别，建议改成中性写法"
                        "（the character / 被动句），否则模型会按性别去改脸")
    return {"image": img, "image_ref": image_ref, "image_text": image_text,
            "mode": "ref" if image_ref else "text", "refs": total,
            "char_refs": char_refs, "scene_refs": scene_refs,
            "scene_source": scene_source, "engine": engine,
            "video": vid, "beats": beats, "problems": problems,
            "image_words": _words(img), "video_words": _words(vid)}
