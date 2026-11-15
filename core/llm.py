"""用 OpenAI 兼容接口做翻译（用户自己填密钥）。

两种翻译：
  translate       生图用：把"角色1"这类指代翻成 @N 槽位标记（2511 只认 the subject in Image N）
  translate_video 生视频用：提示词正文里有中文时翻成英文（英文更稳；中文会被当台词念出来）
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

SYSTEM = (
    "You translate Chinese film-direction notes into English for an image/video generation model.\n"
    "HARD RULES:\n"
    "1. Every numbered character reference (角色1, 角色2, 人物1, 图1, 第一张图, Character 1 ...) "
    "MUST be written as a bare slot token: @1, @2, @3. Never write 'Character 1', 'person 1', "
    "'the first character', or a name. Just @N.\n"
    "2. Existing tokens like @1, <image1>, Image 1 must be kept as @N too (normalise them).\n"
    "3. Keep directions explicit: if the Chinese says A 把手放在 B 腰上, output "
    "'@1 puts a hand on @2's waist' — keep who-does-what-to-whom in the same order.\n"
    "4. One or two sentences, concrete verbs, physical detail, no explanations, no quotes, no markdown.\n"
    "5. NEVER invent a gender: do not write he, she, his, her or him for a subject unless the "
    "Chinese text itself says 男/女/男性/女性. 角色1 is neutral — keep it neutral, refer to it only as @N.\n"
    "6. Output English only."
)

SYSTEM_VIDEO = (
    "You translate Chinese shot descriptions into English for a video generation model. "
    "Rules: one continuous action, present tense, concrete verbs and physical detail; keep camera "
    "movement words (push in, pull back, pan, follow, handheld, locked off); no style words, no skin "
    "or fabric detail, no explanations, no quotes, no markdown. Keep any 'Image N' or '@N' tokens "
    "unchanged. Output English only."
)


SYSTEM_IMAGE = (
    "You translate Chinese descriptions of a person's appearance, clothing and props into plain English "
    "for an image generation model. Rules: write natural language, keep every physical detail "
    "(colours, materials, lengths, layers, left/right); never add character-reference tokens such as "
    "@1, @2 or 'Image 1' — the image model does not use them; do not explain, no quotes, no markdown. "
    "Output English only."
)


class LLMError(RuntimeError):
    pass


def _chat(text: str, cfg: dict, system: str, timeout: int = 60) -> str:
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        raise LLMError("还没填 API Key：点画布右上角「设置」填一个")
    base = str(cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise LLMError("还没填接口地址（例如 https://api.deepseek.com/v1）")
    model = str(cfg.get("model") or "").strip()
    if not model:
        raise LLMError("还没填模型名（例如 deepseek-chat）")

    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"接口返回 HTTP {e.code}：{detail}") from None
    except urllib.error.URLError as e:
        raise LLMError(f"连不上接口：{e.reason}") from None

    try:
        data = json.loads(raw)
        out = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        raise LLMError(f"返回格式看不懂：{raw.decode('utf-8', 'replace')[:300]}") from None
    return str(out).strip().strip('"')


def translate_video(text: str, cfg: dict, timeout: int = 60) -> str:
    """视频描述翻英文。已经是英文就原样返回，不浪费一次请求。"""
    text = str(text or "").strip()
    if not text:
        return ""
    if not re.search(r"[\u4e00-\u9fff]", text):
        return text
    return _chat(text, cfg, SYSTEM_VIDEO, timeout)


def translate(text: str, cfg: dict, slots: list[dict] | None = None,
              timeout: int = 60) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    user = text
    if slots:
        table = ", ".join(f"@{s.get('i')} = {s.get('name')}" for s in slots)
        user = f"Reference slots: {table}.\n\nText to translate:\n{text}"
    return _chat(user, cfg, SYSTEM, timeout)


def translate_image(text: str, cfg: dict, timeout: int = 60) -> str:
    """生图用：中文 → 自然语言英文，不带 @N 槽位标记（生图模型不认）。"""
    text = str(text or "").strip()
    if not text:
        return ""
    if not re.search(r"[\u4e00-\u9fff]", text):
        return text
    return _chat(text, cfg, SYSTEM_IMAGE, timeout)
