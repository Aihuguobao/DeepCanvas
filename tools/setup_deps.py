# -*- coding: utf-8 -*-
r"""一键装画布依赖（由 安装依赖.bat 调用，也可以手动跑 python tools\setup_deps.py）。

做三件事：
 1. 用**当前这个解释器**检查 requirements.txt 里的包；
 2. 缺了就 pip install：先默认源，失败自动换清华 / 阿里镜像再试；
 3. 装完再验一遍，把结果说清楚（成功 / 还缺哪几个 / 手动补的命令）。

不假设 Python 装在哪：bat 负责找解释器，这里只认 sys.executable。
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.dirname(HERE)
REQ = os.path.join(AGENT, "requirements.txt")

# (import 名, pip 包名, 备选 import 名)
CHECKS = [
    ("fastapi", "fastapi", None),
    ("uvicorn", "uvicorn", None),
    ("pydantic", "pydantic", None),
    ("python_multipart", "python-multipart", "multipart"),
    ("numpy", "numpy", None),
    ("cv2", "opencv-python", None),
    ("PIL", "Pillow", None),
    ("websockets", "websockets", None),
    ("imageio_ffmpeg", "imageio-ffmpeg", None),
]

# 第一个是默认源；失败就按顺序换镜像（国内直连 PyPI 经常超时）
INDEXES = [
    None,
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple/",
]


def _say(msg: str = "") -> None:
    print(msg, flush=True)


def missing_packages() -> list[str]:
    """返回缺的 pip 包名（去重、保序）；空列表 = 齐了。"""
    bad: list[str] = []
    for mod, pkg, alt in CHECKS:
        ok = False
        for name in (mod, alt):
            if not name:
                continue
            try:
                importlib.import_module(name)
                ok = True
                break
            except Exception:  # noqa: BLE001 - 缺包 / 导入炸都算没装
                continue
        if not ok and pkg not in bad:
            bad.append(pkg)
    return bad


def _pip_ok() -> bool:
    r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0


def _ensure_pip() -> bool:
    if _pip_ok():
        return True
    _say("pip 不在，先用 ensurepip 装一个……")
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return _pip_ok()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

    _say("=" * 58)
    _say(" 画布依赖安装")
    _say(f" 解释器  : {sys.executable}")
    _say(f" 依赖清单: {REQ}")
    _say("=" * 58)

    if not os.path.isfile(REQ):
        _say(f"找不到 {REQ}")
        _say("请确认在项目根目录（有 启动画布.bat 的那一层）运行。")
        return 1

    if not _ensure_pip():
        _say("pip 装不上。手动执行这一行后重试：")
        _say(f'  "{sys.executable}" -m ensurepip --upgrade')
        return 1

    missing = missing_packages()
    if not missing:
        _say(f"✔ 依赖已经齐了（{len(CHECKS)} 项都在），不用装。")
        _say("  现在可以双击 启动画布.bat。")
        return 0

    _say(f"缺 {len(missing)} 个：{', '.join(missing)}")
    _say("")

    for idx, index in enumerate(INDEXES, 1):
        args = [sys.executable, "-m", "pip", "install", "-r", REQ]
        label = "默认源" if index is None else index
        if index:
            args += ["-i", index]
        _say(f"[第 {idx} 次尝试] {label}")
        code = subprocess.call(args)
        if code == 0:
            break
        _say(f"  这次失败（返回码 {code}），换个源再试。")
        _say("")

    missing = missing_packages()
    if not missing:
        _say("")
        _say("✔ 装完了，全部依赖都在。现在可以双击 启动画布.bat。")
        return 0

    _say("")
    _say(f"✘ 还差：{', '.join(missing)}")
    _say("手动补（复制整行到 cmd 里跑）：")
    _say(f'  "{sys.executable}" -m pip install ' + " ".join(missing)
         + " -i https://pypi.tuna.tsinghua.edu.cn/simple")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        import traceback
        _say("安装脚本自己崩了：")
        _say(traceback.format_exc())
        sys.exit(1)
