"""项目数据：一套 JSON 就是唯一真相源。画布、CLI、质检都读它，不各自维护状态。

目录结构：
    agent/projects/<EP>/
        project.json      集信息 + 画布布局
        characters.json   角色设定（含参考图）
        scenes.json       场景设定
        shots.json        分镜（镜头列表，带 state 记录产物）
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
import unicodedata
import uuid

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS = os.path.join(HERE, "projects")
_WRITE_LOCK = threading.RLock()   # 必须可重入：update_shot 持锁后会再调 write() 也拿这把锁


def slug(name: str) -> str:
    """集号统一成 EP01 这种形式；中文标题不进目录名。"""
    s = unicodedata.normalize("NFKC", str(name)).strip()
    return s.upper() if s.lower().startswith("ep") else f"EP{s}"


def path(ep: str, kind: str) -> str:
    return os.path.join(PROJECTS, slug(ep), f"{kind}.json")


def read(ep: str, kind: str, default=None):
    p = path(ep, kind)
    if not os.path.isfile(p):
        if default is not None:
            return default
        raise FileNotFoundError(f"缺 {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write(ep: str, kind: str, data) -> str:
    p = path(ep, kind)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    # 原子写 + 加锁 + 唯一 tmp：前端一次改动会并发触发多次保存，
    # 原来固定用 `xxx.json.tmp` 会互相踩掉（[WinError 2] tmp -> json），修。
    with _WRITE_LOCK:
        tmp = f"{p}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            # 覆盖之前，把"当前这份能解析的文件"留一份 .lastgood：
            # EP01 的 shots.json 被写坏过一次（合法 JSON 尾巴上粘了垃圾字节），
            # 有了这份就能一键回滚，不用去翻几天前的 .bak。
            if os.path.exists(p):
                try:
                    with open(p, "rb") as g:
                        json.loads(g.read().decode("utf-8"))
                    shutil.copyfile(p, p + ".lastgood")
                except (OSError, ValueError):
                    # .lastgood 只是保险，撞到并发读被锁就算了，不能因为做备份而让保存失败
                    pass
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # os.replace 在 Windows 上遇到「目标文件正被别的句柄打开」会抛 PermissionError，
            # 这是并发读写撞车，不是权限被改。重试几次即可。
            for attempt in range(6):
                try:
                    os.replace(tmp, p)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.05)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return p


def episodes() -> list[str]:
    if not os.path.isdir(PROJECTS):
        return []
    return sorted(d for d in os.listdir(PROJECTS)
                  if os.path.isfile(os.path.join(PROJECTS, d, "project.json")))


def create(ep: str, title: str = "", style: str = "gamecg", engine: str = "h3ref",
           width: int = 1088, height: int = 1920) -> dict:
    proj = {
        "episode": slug(ep),
        "title": title or slug(ep),
        "style": style,
        "engine": engine,
        # 方向必须落盘：前端在缺字段时按竖屏显示，后端 _aspect_of 也默认竖屏。
        # 以前不写这个字段，顶栏显示竖屏、后端却按横屏算。
        "orientation": "portrait",
        "fps": 24,
        "width": width,
        "height": height,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "canvas": {"viewport": {"x": 0, "y": 0, "zoom": 0.8}, "nodes": {}},
        "workflow_groups": [],
    }
    write(ep, "project", proj)
    if not os.path.isfile(path(ep, "characters")):
        write(ep, "characters", {"characters": []})
    if not os.path.isfile(path(ep, "scenes")):
        write(ep, "scenes", {"scenes": []})
    if not os.path.isfile(path(ep, "shots")):
        write(ep, "shots", {"shots": []})
    return proj


def shots(ep: str) -> list[dict]:
    return read(ep, "shots", {"shots": []})["shots"]


def shot(ep: str, sid: str) -> dict:
    for s in shots(ep):
        if s.get("id") == sid:
            return s
    raise KeyError(f"{slug(ep)} 里没有镜头 {sid}")


def save_shots(ep: str, items: list[dict]) -> str:
    return write(ep, "shots", {"shots": items})


def update_shot(ep: str, sid: str, **fields) -> dict:
    """读-改-写整体加锁。

    原来 write() 只锁了"写"，读→改→写这一段没锁：前端一次「自动填六段」会并发发 5 个
    PATCH，五个线程各自读到同一份旧 shots.json，最后写的那个把别人改的字段覆盖掉
    （压测：8 个请求全 200，落盘只剩 1 个字段）。
    """
    with _WRITE_LOCK:
        items = shots(ep)
        for s in items:
            if s.get("id") == sid:
                for k, v in fields.items():
                    # 子字典（video / image / state）在**锁内**合并：
                    # 服务端若在锁外先合并，会拿读到的旧快照把别人刚写的键覆盖掉
                    if isinstance(v, dict) and isinstance(s.get(k), dict):
                        cur = dict(s[k])
                        cur.update(v)
                        s[k] = cur
                    else:
                        s[k] = v
                save_shots(ep, items)
                return s
    raise KeyError(f"没有镜头 {sid}")


def set_state(ep: str, sid: str, **kv) -> dict:
    """只改 state 里的键，不让一次生成把别的产物记录冲掉。"""
    with _WRITE_LOCK:
        items = shots(ep)
        for s in items:
            if s.get("id") == sid:
                st = s.setdefault("state", {})
                st.update(kv)
                save_shots(ep, items)
                return st
    raise KeyError(f"没有镜头 {sid}")


def characters(ep: str) -> dict:
    data = read(ep, "characters", {"characters": []})
    return {c["id"]: c for c in data.get("characters", []) if "id" in c}


def character_prompt(ep: str, cid: str) -> str:
    """角色锚点句：本机实测颜色就是身份，所以把外形写死在角色卡里复用。"""
    c = characters(ep).get(cid)
    if not c:
        raise KeyError(f"没有角色 {cid}")
    bits = [c.get("name_en") or cid, c.get("look"), c.get("outfit"), c.get("props")]
    return ", ".join(b for b in bits if b)


def scene_prompt(ep: str, sid: str) -> str:
    data = read(ep, "scenes", {"scenes": []})
    for s in data.get("scenes", []):
        if s.get("id") == sid:
            return ", ".join(b for b in (s.get("name_en"), s.get("look"), s.get("light")) if b)
    raise KeyError(f"没有场景 {sid}")


def next_id(ep: str) -> str:
    """新镜号取最小的空号。

    旧实现是 max+1，于是删过 S01–S18 之后新镜头永远从 S19 起跳，看着像丢了 18 个。
    改成找空号：有 S01–S03 就出 S04；中间有洞就补洞。
    """
    used = {int(s["id"][1:]) for s in shots(ep)
            if str(s.get("id", "")).startswith("S") and str(s["id"][1:]).isdigit()}
    n = 1
    while n in used:
        n += 1
    return f"S{n:02d}"
