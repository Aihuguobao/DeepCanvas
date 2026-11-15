"""参考图槽位解析：画布预览和出片必须用同一份顺序，否则编号会对不上。

多参考（复杂参考图）：每个角色除主参考外，还会把「三视图 / 服装 / 道具」的图一起喂进去，
每张图在提示词里各占一个 <Subject N>，由模型自己决定怎么组合。
顺序规则（决定 <Picture N> 编号）：
  角色1 主参考 → 角色1 多角度 → 角色2 主参考 → 角色2 多角度 → 场景主参考 → 道具卡
道具卡**排在场景之后**是硬要求：S01–S26 已经按"场景=第 3 张"跑完，
把道具插在中间会让所有既有镜头的 <Picture 3> 从场景变成道具。
"""

import os

from . import store

# 每个角色最多带几张辅助图（不含主参考），免得一口气吃满 9 张上限
_MAX_VIEWS_PER_CHAR = 6


def _ok(path: str) -> bool:
    return bool(path) and os.path.isfile(path)


def shot_refs(ep: str, shot: dict) -> list[dict]:
    """角色在前、场景居中、道具在后，只算真的挂了参考图的。顺序 = <Picture 1..N>。"""
    out: list[dict] = []
    chars = store.characters(ep)
    cids = [cid for cid in (shot.get("characters") or []) if chars.get(cid)]
    n_scenes = len(shot.get("scenes") or [])
    n_props = len(shot.get("props") or [])
    # 总上限 9 张（H3 的 ref_images 上限），而且场景图和道具卡必须留得下——
    # 否则两人各带 6 张辅助图时，末尾的场景/道具会被 out[:9] 直接截掉。
    # 每个角色的辅助图预算 = (9 - 场景数 - 道具数) / 角色数 - 自己的主参考 1 张。
    max_views = min(_MAX_VIEWS_PER_CHAR,
                    max(0, (9 - n_scenes - n_props) // max(1, len(cids)) - 1)) if cids else 0

    for cid in cids:
        c = chars[cid]
        main_idx = 0
        if _ok(c.get("ref")):
            out.append({
                "name": c.get("name") or "", "label": c.get("label") or "",
                "kind": "char", "role": "main", "path": c["ref"],
                "look": c.get("look") or "", "outfit": c.get("outfit") or "",
                "props": c.get("props") or "",
            })
            main_idx = len(out)

        # 同一个人的多角度 / 表情 / 服装 / 道具：只用来保持一致，不当第二个人
        # 注意：画布 UI 有 4 个分组（turnaround / expression / costume / props），
        # 这里必须全部覆盖，否则「表情」槽里放的图不会进参考组。
        sheets = c.get("sheets") or {}
        views = 0
        for group in ("turnaround", "poses", "expression", "costume", "props"):
            for item in sheets.get(group) or []:
                if views >= max_views:
                    break
                p = str(item.get("path") or "")
                if not _ok(p) or p == c.get("ref"):
                    continue
                if any(x["path"] == p for x in out):
                    continue
                out.append({
                    "name": c.get("name") or "", "label": item.get("label") or "",
                    "kind": "char", "role": "view", "path": p, "of": main_idx,
                    "look": "", "outfit": "", "props": "",
                })
                views += 1

    data = store.read(ep, "scenes", {"scenes": []})
    for sid in shot.get("scenes") or []:
        hit = next((x for x in data["scenes"] if x.get("id") == sid), None)
        if hit and _ok(hit.get("ref")):
            out.append({"name": hit.get("name") or "", "label": hit.get("label") or "",
                        "kind": "scene", "role": "main", "path": hit["ref"],
                        "look": hit.get("look") or "", "light": hit.get("light") or "",
                        "outfit": "", "props": ""})

    # 道具卡：排在场景之后（见文件头注释），一件道具 = 一个 <Subject N>
    pdata = store.read(ep, "props", {"props": []})
    for pid in shot.get("props") or []:
        hit = next((x for x in pdata["props"] if x.get("id") == pid), None)
        if hit and _ok(hit.get("ref")):
            out.append({"name": hit.get("name") or "", "label": hit.get("label") or "",
                        "kind": "prop", "role": "main", "path": hit["ref"],
                        "look": hit.get("look") or "", "outfit": "", "props": ""})
    return out[:9]
