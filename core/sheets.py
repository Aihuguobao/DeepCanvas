"""角色/场景设定集的视角模板。

写法的依据（同一台机器、同一个 TextEncodeQwenImageEditPlus 节点的实测记录）：
  1. 改图模型只听第一句 —— 第一句必须是「视角/构图要改成什么」，后面才写一致性。
  2. 正脸要写几何（肩/髋/脚正对镜头、鼻子中线、两耳等可见），否则会自己转成微侧身。
  3. 侧面必须写「不看镜头」，否则会回头看；背面必须写「只有背面看得到的东西」，否则会出正面。
  4. 一致性清单要短，一句话，别把整段外形描述重复进来。
  5. 不要出现 model sheet / turnaround / character sheet 三个词——它们会让模型在一张图里画好几个视图。

本机特殊：Krea2 的负向被 ConditioningZeroOut 清零（cfg=1），负面词完全无效，
所以上面所有约束都写成正面句，不靠「不要 xxx」。
"""
from __future__ import annotations

SHEET = ("The background of the reference image is removed and replaced with plain light grey "
         "seamless paper. Soft even studio light, no text, no watermark")

VIEWS = {
    "front": {
        "zh": "正面全身",
        "size": (1024, 1536),
        "prompt": (
            "Full-body front view. The character stands facing the camera squarely, shoulders, hips "
            "and both feet square to the lens, the nose on the centre line of the face, both ears "
            "equally visible. Keep exactly the same person, face, hair and clothing as the reference "
            "image. " + SHEET + ", the whole figure inside the frame with margin on every side."
        ),
    },
    "three_quarter": {
        "zh": "四分之三侧",
        "size": (1024, 1536),
        "prompt": (
            "Full-body three-quarter view, the body turned about 45 degrees. The tip of the nose "
            "points toward the left edge of the image, the left ear is visible and the right ear is "
            "hidden behind the head. Keep exactly the same person, face, hair and clothing as the "
            "reference image. " + SHEET + ", the whole figure inside the frame with margin."
        ),
    },
    "side": {
        "zh": "右侧面",
        "size": (1024, 1536),
        "prompt": (
            "Full-body side profile view. The face and the body both face the right edge of the "
            "image, only the right half of the face is visible, the character is not looking at the "
            "camera. Keep exactly the same person, face, hair and clothing as the reference image. "
            + SHEET + ", the whole figure inside the frame with margin."
        ),
    },
    "back": {
        "zh": "背面",
        "size": (1024, 1536),
        "prompt": (
            "Rotate the camera 180 degrees around the character, full-body back view. Only the back "
            "is visible: the back of the head and the hair, the back of the coat, the heels of the "
            "boots. Keep exactly the same person, hair and clothing as the reference image. "
            + SHEET + ", the whole figure inside the frame with margin."
        ),
    },
    "closeup": {
        "zh": "正脸大特写",
        "size": (1024, 1024),
        "prompt": (
            "Zoom in to an extreme close-up head-and-shoulders portrait, passport-photo framing: the "
            "top of the head near the top edge of the image, the chin at the vertical middle, the "
            "bottom edge cutting at the collarbone. The face is square to the camera, the nose on the "
            "centre line, both ears equally visible. Keep exactly the same face, hair and upper "
            "garment as the reference image. " + SHEET + "."
        ),
    },
    "costume": {
        "zh": "服装细节",
        "size": (1024, 1024),
        "prompt": (
            "Zoom in to an extreme close-up of only the collar of the coat and the chest, the collar "
            "filling the frame. Same person, same clothing and materials as in the reference image. "
            + SHEET + "."
        ),
    },
}


def default_views(kind: str = "char") -> list[str]:
    if kind == "char":
        return ["front", "three_quarter", "side", "back", "closeup", "costume"]
    return ["front", "side", "back", "three_quarter"]


def prompt_for(view: str) -> str:
    if view not in VIEWS:
        raise KeyError(f"没有这个视角 {view}，可选：{', '.join(VIEWS)}")
    return VIEWS[view]["prompt"]


def size_for(view: str) -> tuple[int, int]:
    return VIEWS[view]["size"]


def label_for(view: str) -> str:
    return VIEWS[view]["zh"]


# ---------------------------------------------------------------- 表情 / 服装 / 姿势 / 道具
# 都挂角色的主参考图，一次提交、每项一条分支，出图后由 canvas/server.py 拼成一张参考板。
#
# 表情的两条实测教训：
#   1. 表情描述必须放**最前面**，一句一个具体的肌肉动作；只写"smiling"会得到 2–3 个重复表情。
#   2. 角色描述里**不许出现** serene / calm / composed 这类神情词——它会把所有表情压平
#      （写了 serene calm expression，6 张表情全变成同一个平静脸）。
_HEAD = ("Close-up head-and-shoulders portrait, straight on, the face filling most of the frame.")
_KEEP = "Same person, same face, same hair and same outfit as in the reference image."
_BG = "Plain pale grey seamless background, soft even studio light, no text, no watermark."

_POSE_HEAD = ("The same person as the reference image, shown full body from head to feet with the "
              "whole figure inside the frame.")
_POSE_TAIL = ("Same face, same hair, same outfit and same colours as the reference image. "
              "Plain pale grey seamless background, soft even studio light, no text, no watermark.")

_EXPR: list[tuple[str, str, str]] = [
    ("neutral", "平静",
     "Her face is completely relaxed: eyebrows level and still, eyes calm and open at a normal "
     "width, lips pressed together in a flat line, absolutely no smile."),
    ("smile", "大笑",
     "A big warm open-mouthed smile: mouth open wide with the upper teeth showing, mouth corners "
     "pulled up high, eyes narrowed by raised cheeks, small creases at the outer eye corners."),
    ("surprise", "惊讶",
     "Startled: both eyebrows raised very high and arched, eyes opened very wide with white showing "
     "above the iris, lips parted in a small round O, chin slightly dropped."),
    ("angry", "愤怒",
     "Furious: both eyebrows pulled down hard toward the nose into a deep vertical crease, eyes "
     "narrowed to hard slits, nostrils flared, lips pressed thin and turned down."),
    ("sad", "悲伤",
     "About to cry: the inner ends of the eyebrows tilted sharply upward, eyes glossy and looking "
     "down, lower lip pushed out and trembling, mouth corners pulled down."),
    ("shy", "害羞",
     "Deeply embarrassed: heavy pink blush across both cheeks and the bridge of the nose, eyes "
     "glancing away to one side, small closed-mouth smile, head tilted slightly down."),
]

_POSES: list[tuple[str, str, str]] = [
    ("pose01_orb", "施法（托球）",
     "standing with one palm held up in front of her chest as if holding a small glowing orb"),
    ("pose02_walk", "御空行走",
     "walking forward as if treading on air, her sleeves and sash trailing behind"),
    ("pose03_seal", "结印",
     "standing in a sword-finger hand seal, one hand raised in front of her face"),
    ("pose04_lotus", "打坐",
     "sitting cross-legged in a lotus meditation pose with her hands resting on her knees"),
    ("pose05_lookback", "回望",
     "standing with her back three-quarters to the camera, looking back over her shoulder"),
    ("pose06_spread", "展袖",
     "standing with both arms spread wide, her robes and hair billowing outward"),
    ("pose07_kneel", "单膝跪",
     "kneeling on one knee with one hand touching the ground"),
    ("pose08_spin", "旋身",
     "caught mid-turn, her long hair and wide sleeves swirling around her"),
    ("pose09_pendant", "持玉坠",
     "standing and holding the jade pendant at her waist with one hand, looking down at it"),
    ("pose10_reach", "抬手",
     "standing on tiptoe and reaching upward with one arm, her sleeve falling back"),
]

GROUPS: dict[str, list[tuple[str, str, int, int, str]]] = {
    "expression": [
        (key, zh, 1024, 1024, f"{desc} {_HEAD} {_KEEP} {_BG}.")
        for key, zh, desc in _EXPR
    ],
    "poses": [
        (key, zh, 1024, 1536, f"{desc}. {_POSE_HEAD} {_POSE_TAIL}")
        for key, zh, desc in _POSES
    ],
    # 服装：全身正 / 全身背 / 纹样细节。
    # 背面靠改图模型把角色转 180 度——参考图是正面时它只能"推断"背面，
    # 想拿到真实的服装背面，用三视图里的 back 视角更准。
    "costume": [
        ("outfit_front", "服装正面", 1024, 1536,
         "The complete outfit worn in the reference image, seen from the front, full length from "
         "collar to hem, the arms held slightly away from the body so the whole garment is visible. "
         f"{_KEEP} {_BG}."),
        ("outfit_back", "服装背面", 1024, 1536,
         "Rotate the camera 180 degrees around the person, the complete outfit seen from behind: "
         "the back of the collar, the back panel, the hem and the back of the sleeves, the person "
         f"facing away from the camera. {_KEEP} {_BG}."),
        ("trim", "纹样细节", 1024, 1024,
         "Close-up of the embroidery and trim of the garment in the reference image, the pattern "
         f"filling the frame. Same colours, materials and pattern as the reference image. {_BG}."),
        ("boots", "鞋靴细节", 1024, 1024,
         "Close-up of the footwear worn in the reference image, both boots shown whole from ankle "
         f"to sole with empty background around them. {_KEEP} {_BG}."),
    ],
    "props": [
        ("item", "道具", 1024, 1024,
         "The object held in Image 1, shown alone and centred on a plain light grey background, "
         "the whole object inside the frame with margin, same design, colour and material as "
         "in the reference image, no hands, no person, no text."),
    ],
}


def group_items(group: str) -> list[tuple[str, str, int, int, str]]:
    if group not in GROUPS:
        raise KeyError(f"没有这个分组 {group}，可选：{', '.join(GROUPS)}")
    return GROUPS[group]
