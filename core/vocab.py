"""镜头词汇表：中文下拉 → 固定英文短语。

来源：
  《帧图描述完整元素表》26 项（景别/机位角度/光线类型/景深/色温/焦距）
  《多格分镜提示词》景别缩写体系 ELS/LS/FS/MS/MCU/CU/ECU
做法和原则：下拉只提供选项，选完直接把**固定的英文短语**写进提示词，
不做二次翻译——翻译会漂，固定短语不会。
"""
from __future__ import annotations

SIZE = {
    "": ("自动", ""),
    "els": ("大远景", "extreme long shot, the subject tiny in a vast space"),
    "ls": ("远景", "long shot, the whole space visible"),
    "fs": ("全景", "full shot, the subject head to toe"),
    "ms": ("中景", "medium shot, waist up"),
    "mcu": ("近景", "medium close-up, chest up"),
    "cu": ("特写", "close-up, the face filling the frame"),
    "ecu": ("大特写", "extreme close-up of a single detail"),
}

ANGLE = {
    "": ("自动", ""),
    "eye": ("平视", "eye level"),
    "low": ("低角度", "low angle looking up"),
    "high": ("高角度", "high angle looking down"),
    "top": ("俯拍", "top-down overhead view"),
    "dutch": ("荷兰角", "dutch angle, the horizon tilted"),
    "ots": ("过肩", "over-the-shoulder shot"),
    "pov": ("主观视角", "first-person point of view"),
}

LENS = {
    "": ("自动", ""),
    "24": ("广角 24mm", "24mm wide lens"),
    "35": ("35mm", "35mm lens"),
    "50": ("标准 50mm", "50mm lens"),
    "85": ("人像 85mm", "85mm lens"),
    "135": ("长焦 135mm", "135mm telephoto, compressed background"),
    "macro": ("微距", "macro lens"),
}

LIGHT = {
    "": ("自动", ""),
    "hard": ("硬光", "hard key light, sharp shadows"),
    "soft": ("柔光", "soft diffused light"),
    "rim": ("轮廓光", "strong rim light outlining the subject"),
    "back": ("逆光", "backlit, the subject rimmed and half silhouetted"),
    "side": ("侧光", "side light, half the face in shadow"),
    "top": ("顶光", "overhead light, eyes falling into shadow"),
    "bottom": ("底光", "light from below, unsettling"),
    "window": ("窗光", "soft window light from one side"),
    "neon": ("霓虹", "neon spill, magenta and cyan"),
    "candle": ("烛光", "warm candlelight"),
    "moon": ("月光", "cold moonlight"),
    "overcast": ("阴天", "flat overcast light"),
    "golden": ("黄金时刻", "golden hour, warm low sun"),
    "blue": ("蓝调时刻", "blue hour, deep blue ambient"),
}

DEPTH = {
    "": ("自动", ""),
    "shallow": ("浅景深", "shallow depth of field, background blurred"),
    "medium": ("中景深", "medium depth of field"),
    "deep": ("深景深", "deep focus, everything sharp"),
}

TONE = {
    "": ("自动", ""),
    "neutral": ("自然", ""),
    "cold": ("冷蓝灰", "cool blue-grey grade, low saturation"),
    "warm": ("暖橙", "warm amber grade"),
    "desat": ("低饱和", "desaturated palette"),
    "contrast": ("高对比", "high contrast, crushed blacks"),
}

MOVE = {
    "": ("自动", ""),
    "push": ("推进", "push in slowly, ending tight on the subject"),
    "snap": ("急推", "fast snap push in"),
    "pull": ("拉远", "pull back, revealing the space around them"),
    "pan": ("摇镜", "pan across to the second figure"),
    "track": ("跟拍", "tracking shot following from behind"),
    "orbit": ("环绕", "the camera arcs around the pair"),
    "up": ("升降", "crane up from ground level"),
    "down": ("俯冲", "the camera dives down to the ground"),
    "handheld": ("手持", "handheld camera, shaking with each impact"),
    "zoom": ("变焦推拉", "dolly zoom, the background stretching"),
    "static": ("固定", "locked-off static camera, only the action moves"),
}

# ---------------------------------------------------------------- 场景空镜
SPACE = {
    "": ("自动", ""),
    "office": ("高层办公室", "a high-rise office interior, floor-to-ceiling windows"),
    "apartment": ("公寓客厅", "a small apartment living room"),
    "corridor": ("走廊", "a long narrow corridor"),
    "stairwell": ("楼梯间", "a concrete stairwell"),
    "store": ("便利店", "a small convenience store interior"),
    "street": ("城市街道", "a city street between buildings"),
    "alley": ("后巷", "a narrow back alley"),
    "rooftop": ("天台", "a rooftop with the skyline behind"),
    "subway": ("地铁车厢", "an empty subway car"),
    "platform": ("地铁站台", "a subway platform"),
    "parking": ("地下车库", "an underground parking garage"),
    "hospital": ("医院走廊", "a hospital corridor"),
    "warehouse": ("废弃仓库", "an abandoned warehouse"),
    "forest": ("树林", "a forest clearing"),
    "shrine": ("祠堂", "a small ancestral shrine interior"),
    "castle": ("哥特大厅", "a gothic hall with arched windows"),
}

TIME = {
    "": ("自动", ""),
    "dawn": ("清晨", "early morning, low sun"),
    "day": ("白天", "midday"),
    "dusk": ("黄昏", "dusk, orange sky"),
    "night": ("夜晚", "night"),
    "deep": ("深夜", "deep night, almost no light"),
}

WEATHER = {
    "": ("自动", ""),
    "clear": ("晴", "clear sky"),
    "rain": ("雨", "heavy rain, wet surfaces"),
    "storm": ("暴雨", "storm, rain streaks across the frame"),
    "snow": ("雪", "falling snow"),
    "fog": ("雾", "thick fog"),
}

# ---------------------------------------------------------------- 构图（治"假人感"）
# 依据：AI 默认会给"居中 + 看镜头 + 背景糊"的保底构图，精致但假。
# 必须显式写"站哪、看哪"，再补前景和引导线。
POSITION = {
    "": ("自动", ""),
    # 这里只写"取景位置"，绝不写体位动作。
    # 原来写的是 "the subject stands on the right third"——用户只是选了「主体在右三分」，
    # 模型却收到一句"站在右边"，和动作里写的「坐在床沿」直接打架。
    "left": ("主体在左三分", "the subject framed on the left third, open space on the right"),
    "right": ("主体在右三分", "the subject framed on the right third, open space on the left"),
    "left_close": ("贴左近景", "close on the subject at the left edge, the rest falling away"),
    "center": ("居中对称", "symmetrical composition, the subject dead centre"),
    "frame_in_frame": ("框中框", "framed through a doorway, a frame within the frame"),
}

GAZE = {
    "": ("自动", ""),
    "camera": ("看镜头", "looking straight into the lens"),
    "other": ("看对方", "looking at the other person, not at the lens"),
    "off": ("望向画外", "gazing off frame to the side"),
    "down": ("低头", "head lowered, eyes down"),
    "away": ("侧脸背对", "seen in profile, half turned away from the lens"),
}

FOREGROUND = {
    "": ("自动", ""),
    "none": ("无前景", ""),
    "blur": ("前景虚化", "a blurred object in the near foreground, out of focus"),
    "doorway": ("门框前景", "shooting past a doorframe in the foreground"),
    "pipes": ("管道前景", "out-of-focus pipes crossing the near foreground"),
}

SETS = {"size": SIZE, "angle": ANGLE, "lens": LENS, "light": LIGHT,
        "depth": DEPTH, "tone": TONE,
        "space": SPACE, "time": TIME, "weather": WEATHER,
        "position": POSITION, "gaze": GAZE, "foreground": FOREGROUND}
# 运镜不在这里：它是封闭 15 个英文指令，见 core/engines.py


def english(group: str, key: str) -> str:
    if not key:
        return ""
    item = SETS.get(group, {}).get(key)
    return item[1] if item else ""


def options(group: str) -> list[tuple[str, str]]:
    """[(key, 中文)]，给前端渲染下拉用。"""
    return [(k, v[0]) for k, v in SETS.get(group, {}).items()]
