r"""弹一个 Windows 原生「选择文件夹」对话框，把选中的路径打到 stdout。

为什么要单独开一个进程：tkinter 的 Tk 必须在创建它的那个线程里跑，
而画布后端活在 uvicorn 的线程池里，直接在那儿开窗在 Windows 上会静默退出（实测过的坑）。
子进程 + 主线程开窗最稳。

用法：
    python tools/pick_dir.py --title "选择 ComfyUI 文件夹" --initial "路径"
输出：
    stdout 一行 UTF-8 绝对路径；用户取消则什么都不输出，退出码 1。
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="选择文件夹")
    ap.add_argument("--initial", default="")
    a = ap.parse_args()

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001
        print(f"tkinter 不可用：{exc}", file=sys.stderr)
        return 2

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    root.update()

    initial = a.initial if a.initial and os.path.isdir(a.initial) else os.path.expanduser("~")
    try:
        path = filedialog.askdirectory(title=a.title, initialdir=initial, mustexist=True)
    except Exception as exc:  # noqa: BLE001
        print(f"打开对话框失败：{exc}", file=sys.stderr)
        root.destroy()
        return 2
    root.destroy()

    if not path:
        return 1
    print(os.path.abspath(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
