"""视频引擎能力表 + 每种引擎的运镜/提示词适配。

两个引擎的写法差别很大，不能共用同一套选项：
  MiniMax H3 · Ref2VA  多参考图，六段式，中文可用
  MiniMax H3 · FL2VA   首帧驱动，指令行 + 三字段
两者运镜都用**官方封闭的 15 个英文指令**；没有 orbit。

依据：
  Hailuo 官方 15 个运镜指令（英文，封闭列表，[Orbit]/[Dolly]/[Crane] 无效）
"""
from __future__ import annotations

ENGINES = {
    "h3": {
        "id": "h3",
        "name": "MiniMax H3 · FL2VA（首帧）",
        "lang": "zh",
        "camera": "phrase",         # 运镜是"类型+幅度+速度"的英文短语，不是方括号
        "anchors": "first_last",
        "durations": [5, 6, 8],     # 实测：5s=436.6s；8s 是当前封顶
        "max_words": 200,
        "audio": True,
        "note": "首帧驱动：画布确认过首帧才能出片。实测镜头真的会动"
                "（平移中位 4.56px），比 Ref2VA 快约 2 倍。",
    },
    "h3ref": {
        "id": "h3ref",
        "name": "MiniMax H3 · Ref2VA（参考图）",
        "lang": "zh",
        "camera": "phrase",
        "anchors": "refs",          # 多张参考图，不需要首帧
        "durations": [5, 6, 8, 10],  # 训练区间 124–362 帧（约 5–15 秒）；8 秒是当前封顶
        "max_words": 260,
        "audio": True,
        "note": "多参考图（最多 9 张）→ 音视频；提示词用 <Picture N> 指代，"
                "不再依赖首帧。实测这个模式镜头基本不动（平移 0.00px），要运镜请用首帧模式。",
    },
}

# ---------------------------------------------------------------- H3：官方 15 个指令
# 官方列表是封闭的，写别的不会报错、也不会生效
H3_CAMERA = {
    "truck_left": ("左移", "[Truck left]"),
    "truck_right": ("右移", "[Truck right]"),
    "pan_left": ("左摇", "[Pan left]"),
    "pan_right": ("右摇", "[Pan right]"),
    "push": ("推进", "[Push in]"),
    "pull": ("拉远", "[Pull out]"),
    "pedestal_up": ("上升", "[Pedestal up]"),
    "pedestal_down": ("下降", "[Pedestal down]"),
    "tilt_up": ("上摇", "[Tilt up]"),
    "tilt_down": ("下摇", "[Tilt down]"),
    "zoom_in": ("变焦推近", "[Zoom in]"),
    "zoom_out": ("变焦拉远", "[Zoom out]"),
    "shake": ("晃动", "[Shake]"),
    "tracking": ("跟随", "[Tracking shot]"),
    "static": ("固定", "[Static shot]"),
}

# H3 没有指令的运镜：写成散文（官方说 free-form 也能懂，只是不准）
H3_PROSE = {
    "orbit": "the camera slowly circles around them",
    "orbit_rise": "the camera circles around them while rising",
    "dolly_zoom": "the background stretches as the subject stays the same size",
    "rack_focus": "the focus moves from one subject to the other",
    "handheld": "the camera shakes slightly as it follows",
}

# 视频尾句：只讲质感，**不写速度词**。
# 实测：`natural motion` 这类中性词会被模型读成"慢慢来"，动作更肉。速度交给动作动词。
VIDEO_TAIL = {
    "photoreal": "consistent lighting, photographic realism",
    "cinema": "consistent lighting, film grain",
    "film": "film grain, consistent lighting",
    "phone": "handheld realism",
    "editorial": "clean studio lighting",
    "docu": "available light",
    "gamecg": "pre-rendered cinematic",
    "anime": "2D animation, consistent line weight",
    "ink": "ink wash consistency",
}


def get(engine: str) -> dict:
    return ENGINES.get(engine) or ENGINES["h3ref"]


def camera_options(engine: str) -> list[tuple[str, str]]:
    """这个引擎能选的运镜：[(key, 中文)]。"""
    return [(k, v[0]) for k, v in H3_CAMERA.items()]


def camera_text(engine: str, move: str) -> str:
    """把运镜 key 变成这个引擎能读的写法。"""
    if not move:
        return ""
    if get(engine)["camera"] == "phrase":
        # H3 的"类型+幅度+速度"短语
        return h3_move(move)
    if move in H3_CAMERA:
        return H3_CAMERA[move][1]
    return H3_PROSE.get(move, "")


def video_tail(style: str) -> str:
    return VIDEO_TAIL.get(style or "", VIDEO_TAIL["photoreal"])


# ---------------------------------------------------------------- H3 官方规范用词
# 官方要求：运镜 = 类型 + 幅度 + 速度，写进句子里，不在句尾堆标签。
H3_OFFICIAL_MOVE = {
    "push": "pushes in with small amplitude at slow speed",
    "pull": "pulls out with small amplitude at slow speed",
    "pan_left": "pans left with large amplitude at slow speed",
    "pan_right": "pans right with large amplitude at slow speed",
    "truck_left": "trucks left with small amplitude at slow speed",
    "truck_right": "trucks right with small amplitude at slow speed",
    "tilt_up": "tilts up with small amplitude at slow speed",
    "tilt_down": "tilts down with small amplitude at slow speed",
    "pedestal_up": "pedestals up with small amplitude at slow speed",
    "pedestal_down": "pedestals down with small amplitude at slow speed",
    "zoom_in": "zooms in with small amplitude at slow speed",
    "zoom_out": "zooms out with small amplitude at slow speed",
    "tracking": "tracks the subject with small amplitude at normal speed",
    "shake": "shakes slightly",
    "static": "holds a static shot",
    # 官方列表之外，用最接近的自然语言，不硬编方括号
    "orbit": "moves in a slow arc around the subject",
    "orbit_rise": "moves in a slow arc around the subject while rising",
    "dolly_zoom": "dollies in while zooming out, stretching the background",
    "rack_focus": "holds static while focus shifts between the two",
    "crane_up": "pedestals up with small amplitude at slow speed",
    "crane_down": "pedestals down with small amplitude at slow speed",
    # 侧向跟拍：镜头和人同速平移，人保持侧身
    "side_track": ("tracks sideways alongside her at the same speed, keeping her in profile at fast "
                   "speed, she keeps the same size in the frame"),
}

# 别名：老数据/口误里的写法，统一映射到正式键。
# 发现：`move=track` 在表里没有，h3_move() 静默返回空串，
# 于是整句运镜根本没进提示词——出片后镜头一动不动，被误判成"模型不听指令"。
H3_MOVE_ALIAS = {
    "track": "tracking",
    "follow": "tracking",
    "following": "tracking",
    "handheld": "tracking",
    "dolly": "tracking",
    "pan": "pan_right",
    "tilt": "tilt_up",
    "static_shot": "static",
    "side": "side_track",
    "sideways": "side_track",
    "侧跟": "side_track",
}

# 官方要求：[Shot 1] 开头先声明风格
H3_STYLE_WORD = {
    "photoreal": "Live-action, cinematic",
    # 确定：CG 人物 + 真实背景。人物是 CG（材质/轮廓清楚、768 下不糊），
    # 环境是实拍照片。只写 photorealistic 会把人物也做成照片，CG 味就没了。
    "cgphoto": "3D CG character in a photorealistic live-action environment",
    "cinema": "Live-action, cinematic",
    "film": "Live-action, vintage film",
    "phone": "Live-action, handheld documentary",
    "editorial": "Live-action, cinematic",
    "docu": "Live-action, documentary",
    "gamecg": "3D CG, cinematic",
    "xianxia": "3D-animated, Chinese xianxia animation",
    "anime": "2D-animated, cinematic",
    "ink": "Watercolor, 2D-animated",
}


def h3_move(move: str) -> str:
    key = (move or "").strip()
    if not key:
        return ""
    key = H3_MOVE_ALIAS.get(key, key)
    text = H3_OFFICIAL_MOVE.get(key, "")
    if not text:
        # 不再静默吞掉：写错了要能看见，否则又会把"没运镜"归因到模型头上
        print(f"  ! 未知运镜 move={move!r}，H3 运镜句为空。可用："
              f"{'/'.join(sorted(H3_OFFICIAL_MOVE))}")
    return text


def h3_style(style: str) -> str:
    return H3_STYLE_WORD.get(style or "", "Live-action, cinematic")


def durations(engine: str) -> list[int]:
    return list(get(engine).get("durations") or [4])
