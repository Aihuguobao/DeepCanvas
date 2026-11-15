"""场景空镜（plate）的提示词与清人提示词。

空镜 = 没有人物的空间图，用来当镜头卡的场景参考。
两条路：
  build_plate : 文生图造一张新的（Krea2，写实）
  clean_prompt: 把已有场景图里的人/人影擦掉（Qwen-Image-Edit）
"""
from __future__ import annotations

from core import vocab

# 空镜必须是"无人"，这是唯一硬约束：
# 参考图里只要有个人形，出图就会把它当场景元素搬进画面（实测：玻璃倒影被放大成巨人）。
PLATE_RENDER = ("empty scene, no people, no figures, no silhouettes, "
                "architectural photography, 35mm, natural perspective, "
                "cinematic still, fine film grain")


# LIGHT 词表是给"有主体"的镜头写的；空镜没有主体，这些人体说法必须换掉。
# 不换的话提示词会一边写"没有人"一边写"the subject"，模型就会画一个人
# （实测：逆光 → 空镜里生成了一个裸女）。
_LIGHT_FIX = {
    "the subject rimmed and half silhouetted": "the room rimmed and half silhouetted",
    "outlining the subject": "outlining the room",
    "half the face in shadow": "half the room in shadow",
    "eyes falling into shadow": "the floor falling into shadow",
}


def _sentence(text: str) -> str:
    """去尾标点、首字母大写、补句号。"""
    text = str(text or "").strip().rstrip(".。")
    if not text:
        return ""
    return text[0].upper() + text[1:] + "."


def build_plate(gen: dict) -> str:
    """gen: {space, time, weather, light, tone, angle, note}，值都是 vocab 的 key。

    Krea2 官方要自然语言（连贯句子），不是逗号关键词堆砌，所以这里拼成句。
    """
    gen = gen or {}
    space = vocab.english("space", gen.get("space", ""))
    time = vocab.english("time", gen.get("time", ""))
    weather = vocab.english("weather", gen.get("weather", ""))
    angle = vocab.english("angle", gen.get("angle", ""))
    light = vocab.english("light", gen.get("light", ""))
    for bad, good in _LIGHT_FIX.items():
        light = light.replace(bad, good)
    tone = vocab.english("tone", gen.get("tone", ""))
    note = str(gen.get("note") or "").strip()

    parts = [f"A photograph of an empty scene: {space or 'a plain empty interior'}."]
    parts.append("There are no people, no figures and no silhouettes anywhere in the frame.")
    if time:
        parts.append(f"It is {time}.")
    if weather:
        parts.append(f"{weather[0].upper()}{weather[1:]}.")
    if note:
        parts.append(_sentence(note))
    if angle:
        parts.append(f"The camera is at {angle}.")
    if light:
        parts.append(f"{light[0].upper()}{light[1:]}.")
    if tone:
        parts.append(f"{tone[0].upper()}{tone[1:]}.")
    parts.append("Architectural photography, natural 35mm perspective, cinematic still, "
                 "fine film grain, no text, no watermark.")
    return " ".join(p for p in parts if p).strip()


CLEAN = (
    "Remove every person, human figure, human silhouette and reflection of a person "
    "from this image. Keep the architecture, furniture, windows, lighting, colour and "
    "the camera framing exactly as they are. Fill the removed areas with the surface "
    "that should be behind them. The result must contain no people at all."
)


def clean_prompt(extra: str = "") -> str:
    extra = str(extra or "").strip()
    return f"{CLEAN} {extra}".strip() if extra else CLEAN
