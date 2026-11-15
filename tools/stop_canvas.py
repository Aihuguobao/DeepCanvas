"""关掉画布服务（8765 端口上那个 python）。

为什么单独一个脚本而不是纯 bat：纯 bat 里解析 netstat 输出 + 判断进程名 + 等端口释放
写出来是一堆 findstr 魔法，改一次坏一次。逻辑放 Python 里可读、可测、可干跑。

用法：
    python tools/stop_canvas.py          # 找到就杀，等端口释放
    python tools/stop_canvas.py --dry    # 只看它找到了哪个进程，不动手

只动 8765 端口上、进程名是 python 的那个进程。
不碰 ComfyUI（8188）。注意：关画布**不会**停掉 ComfyUI 里已经提交的任务，
那些任务在 ComfyUI 那边继续跑完——想停得去 ComfyUI 点取消。
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time

PORT = 8766
NO_WINDOW = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW


def _decode(raw: bytes) -> str:
    """netstat / tasklist 的输出跟系统代码页走（中文 Windows 是 GBK），不是 UTF-8。"""
    for enc in ("oem", "gbk", "mbcs", "utf-8"):
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def port_open(port: int = PORT, timeout: float = 0.6) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def listening_pid(port: int = PORT) -> int:
    """从 netstat 里挑出占着这个端口、状态 LISTENING 的 PID。"""
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "tcp"],
                           capture_output=True, creationflags=NO_WINDOW)
    except OSError:
        return 0
    for line in _decode(r.stdout or b"").splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        if parts[3].upper() != "LISTENING":
            continue
        if not parts[1].endswith(":" + str(port)):
            continue
        if parts[4].isdigit():
            return int(parts[4])
    return 0


def proc_name(pid: int) -> str:
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, creationflags=NO_WINDOW)
    except OSError:
        return ""
    text = _decode(r.stdout or b"").strip()
    # 没匹配时是 "信息: 没有运行的任务…"，CSV 行则一定以引号开头
    if not text.startswith('"'):
        return ""
    return text.split(",")[0].strip().strip('"')


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--dry", action="store_true", help="只报告，不杀")
    a = ap.parse_args()

    port = a.port
    if not port_open(port):
        print(f"画布没在跑（{port} 端口是空的），不用关。")
        return 0

    pid = listening_pid(port)
    if not pid:
        print(f"{port} 端口有人占着，但 netstat 里找不到对应 PID。")
        print("可能是权限不够，或者被别的程序抢了这个端口——我没动它。")
        return 1

    name = proc_name(pid)
    print(f"{port} 端口 → PID {pid}（{name or '名字查不到'}）")
    if not name.lower().startswith("python"):
        print("这个进程不是 python，不是我们的画布服务，**我没动它**。")
        print("（可能是别的程序占了 8765，改端口再起画布）")
        return 1

    if a.dry:
        print("--dry：到此为止，没有杀任何进程。")
        return 0

    r = subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, creationflags=NO_WINDOW)
    ok = (r.returncode == 0)
    out = _decode(r.stdout or b"").strip()
    err = _decode(r.stderr or b"").strip()

    for _ in range(20):                      # 最多等 10 秒端口释放
        if not port_open(port):
            break
        time.sleep(0.5)

    if port_open(port):
        print("杀过了，但端口还占着。")
        if out:
            print(out)
        if err:
            print(err)
        return 1

    print(f"已关闭（原 PID {pid}）。再启动双击「启动画布.bat」。")
    print("提示：ComfyUI 里已经提交的任务不受影响，会继续跑完。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
