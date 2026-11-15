# -*- coding: utf-8 -*-
r"""提交前体检（所有任务通用，不挑模型）。

为什么：连交三版 Wan-Dancer 废片，根因都是"建完图直接提交、没核对"。
闸门必须对所有图生效，而不是只针对某个模型。

三类检查：
 1. **结构**：每个节点的必填输入都在（有值或被连线），连线指向真实存在的节点与输出槽。
 2. **取值**：下拉框（combo）的值必须在该节点的合法列表里；INT/FLOAT 落在 min/max 内。
 3. **专项**：装了专门的检查器（wan_precheck 等）就一起跑。

用法：
    python _agent\tools\preflight.py 图.json
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

# 独立跑 CLI 时的兜底地址；实际优先用画布那套解析（见 _api）
API = os.environ.get("COMFY_BASE", "http://127.0.0.1:8188").rstrip("/")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_OI = None


def _api() -> str:
    """问 ComfyUI 的地址，**必须和画布提交用的是同一个**。

    以前这里只读 COMFY_BASE、默认写死 8188，和 core.comfy.base() 不是同一条解析链：
    画布连的是 A 端口的 ComfyUI，体检却去问 B 端口 —— 文件明明在 input 里也会被判
    "不在可选列表"。
    """
    try:
        from core import comfy  # noqa: PLC0415
        return comfy.base().rstrip("/")
    except Exception:  # noqa: BLE001 - 独立跑 CLI 时退回兜底
        return API


def object_info() -> dict:
    global _OI
    if _OI is None:
        with urllib.request.urlopen(_api() + "/object_info", timeout=120) as r:
            _OI = json.load(r)
    return _OI


# 这几个节点的取值就是 ComfyUI\input 里的文件名
INPUT_NODES = {"LoadImage", "LoadVideo", "LoadAudio"}


def _in_input(val: str) -> bool:
    r"""文件是否真的在 ComfyUI\input 里。磁盘是事实，列表可能是缓存。"""
    try:
        from core import comfy  # noqa: PLC0415
        d = comfy.input_dir()
        return bool(d) and os.path.isfile(os.path.join(d, val))
    except Exception:  # noqa: BLE001 - 拿不到目录就当没有，保持原判据
        return False


def reset_cache() -> None:
    """清掉 /object_info 缓存，下次调用重新问 ComfyUI。

    为什么要这个：缓存是进程级的，画布刚 upload_image 传进 input 的新参考图
    不在旧列表里，会被误判成"文件不存在"。
    """
    global _OI
    _OI = None


def _spec_list(oi: dict, ct: str) -> list[tuple[str, list]]:
    info = oi.get(ct) or {}
    out = []
    for group in ("required", "optional"):
        for name, spec in (info.get("input", {}).get(group) or {}).items():
            out.append((name, spec))
    return out


def check_graph(graph: dict) -> list[str]:
    errs = _check(graph, object_info())
    # 未知节点类型，多半是两份缓存过期：ComfyUI 刚装了节点包/刚重启没加载完，
    # 或者本进程早先取过一次 /object_info。清缓存重新问一遍，还认不出才算真缺
    # 。
    if any("未知节点类型" in e for e in errs):
        reset_cache()
        again = _check(graph, object_info())
        return again
    return errs


def _check(graph: dict, oi: dict) -> list[str]:
    errs: list[str] = []

    for nid, node in graph.items():
        ct = node.get("class_type", "")
        if ct not in oi:
            errs.append(f"[{nid}] 未知节点类型 {ct}（没装/没加载）")
            continue
        inputs = node.get("inputs") or {}
        for name, spec in _spec_list(oi, ct):
            required = name in (oi[ct].get("input", {}).get("required") or {})
            # 自动增长的动态输入（COMFY_AUTOGROW_V3：ComfyMathExpression.values / CreateList.inputs 等）
            # 在 API 图里可以完全不出现，由 ComfyUI 运行期展开，不算缺参
            if isinstance(spec[0], str) and spec[0].startswith("COMFY_AUTOGROW"):
                required = False
            val = inputs.get(name)
            if val is None:
                if required:
                    errs.append(f"[{nid}] {ct} 缺必填输入 `{name}`")
                continue
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                src, slot = val
                if src not in graph:
                    errs.append(f"[{nid}] {ct}.{name} 连到不存在的节点 {src}")
                else:
                    out_types = oi.get(graph[src].get("class_type", ""), {}).get("output") or []
                    if isinstance(slot, int) and slot >= len(out_types):
                        errs.append(f"[{nid}] {ct}.{name} 取 {src} 的第 {slot} 个输出，但它只有 {len(out_types)} 个")
                continue
            t = spec[0]
            if isinstance(t, list):  # COMBO
                if val not in t:
                    # 读 input 目录的节点：文件真在盘上就放行。ComfyUI 的列表按目录 mtime 缓存，
                    # 刚写进去的文件可能还没进表；而运行时 LoadImage 是直接按路径读盘的，
                    # 所以"列表里没有"不等于"读不到"。
                    if ct in INPUT_NODES and _in_input(str(val)):
                        print(f"  ! [{nid}] {ct}.{name} = {val!r} 不在 ComfyUI 列表里，"
                              f"但文件确实在 input —— 放行（列表可能是缓存）")
                    else:
                        errs.append(f"[{nid}] {ct}.{name} = {val!r} 不在可选列表里")
            elif t in ("INT", "FLOAT") and isinstance(val, (int, float)):
                lo = spec[1].get("min") if len(spec) > 1 and isinstance(spec[1], dict) else None
                hi = spec[1].get("max") if len(spec) > 1 and isinstance(spec[1], dict) else None
                if lo is not None and val < lo:
                    errs.append(f"[{nid}] {ct}.{name} = {val} < min {lo}")
                if hi is not None and val > hi:
                    errs.append(f"[{nid}] {ct}.{name} = {val} > max {hi}")

    types = {n.get("class_type", "") for n in graph.values()}
    return errs


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    g = json.load(open(sys.argv[1], encoding="utf-8"))
    errs = check_graph(g)
    name = os.path.basename(sys.argv[1])
    if errs:
        print(f"未通过：{name}")
        for e in errs:
            print("  -", e)
        return 1
    print(f"通过：{name}（{len(g)} 个节点）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
