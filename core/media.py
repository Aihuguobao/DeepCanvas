"""媒体处理：抽末帧、探参数、拼接、烧字幕。全部走本机自带的 ffmpeg（imageio_ffmpeg）。"""
from __future__ import annotations

import os
import re
import subprocess


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def imread_unicode(path: str):
    """cv2.imread 在 Windows 读不了中文路径，统一走这条。"""
    import cv2
    import numpy as np
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def imwrite_unicode(path: str, img) -> str:
    import cv2
    ok, buf = cv2.imencode(os.path.splitext(path)[1] or ".png", img)
    if not ok:
        raise RuntimeError(f"写不出 {path}")
    buf.tofile(path)
    return path


def fit_to_canvas(src: str, out: str, width: int = 832, height: int = 1248,
                  fill: tuple = (236, 236, 236)) -> str:
    """把图等比缩放到目标画布内并居中留白（不裁切、不拉伸）。

    用在"生成之后"——生成时保持源图比例（零畸变），排版时再统一尺寸，
    这样补边痕迹只出现在版式层，不会进模型。
    """
    import cv2
    import numpy as np
    img = imread_unicode(src)
    if img is None:
        raise RuntimeError(f"读不出 {src}")
    ih, iw = img.shape[:2]
    scale = min(width / iw, height / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.full((height, width, 3), fill, dtype=np.uint8)
    x, y = (width - nw) // 2, (height - nh) // 2
    canvas[y:y + nh, x:x + nw] = resized
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return imwrite_unicode(out, canvas)


def pad_to_aspect(src: str, out: str, aspect: float = 2 / 3,
                  fill: tuple = (236, 236, 236)) -> str:
    """把图补边到指定宽高比，**不拉伸**。

    拉伸会让人物比例变形——832x1216 硬套 1088x1920 的源图，人被横向压扁。
    fill 固定浅灰：试过"从边缘取色"，源图底边是人物躯干时会把补边补成深色带（用户否掉）。
    """
    import cv2
    img = imread_unicode(src)
    if img is None:
        raise RuntimeError(f"读不出 {src}")
    h, w = img.shape[:2]
    if abs(w / h - aspect) < 0.01:
        return src
    if w / h > aspect:                     # 太宽 → 上下补
        new_h = int(round(w / aspect))
        top = (new_h - h) // 2
        img = cv2.copyMakeBorder(img, top, new_h - h - top, 0, 0, cv2.BORDER_CONSTANT, value=fill)
    else:                                  # 太高 → 左右补
        new_w = int(round(h * aspect))
        left = (new_w - w) // 2
        img = cv2.copyMakeBorder(img, 0, 0, left, new_w - w - left, cv2.BORDER_CONSTANT, value=fill)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    return imwrite_unicode(out, img)


def _run(args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
    # pythonw 下没有控制台：不给 CREATE_NO_WINDOW，控制台程序会闪窗、甚至 0xc0000142
    kw = {}
    if os.name == "nt":
        kw = {"creationflags": 0x08000000, "stdin": subprocess.DEVNULL}
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, **kw)
    return r


def probe(path: str) -> dict:
    r = _run([ffmpeg(), "-i", path], timeout=120)
    info = {"path": path, "duration": 0.0, "size": "", "fps": "", "has_audio": False}
    text = r.stderr or ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            info["duration"] = round(int(h) * 3600 + int(m) * 60 + float(s), 2)
        if "Video:" in line:
            for token in line.split(","):
                token = token.strip()
                if re.fullmatch(r"\d{2,5}x\d{2,5}", token):
                    info["size"] = token
                if token.endswith("fps"):
                    info["fps"] = token
        if "Audio:" in line:
            info["has_audio"] = True
    return info


def last_frame(clip: str, out_png: str, back: float = 0.0) -> str:
    """抽最后一帧（真末帧）。

    旧版默认 back=0.1 往回抽 0.1s，实测会把倒数第 2 帧当末帧：
    S01 母版 141 帧 @24fps，back=0.1 抽到第 139 帧，真末帧是第 140 帧，
    而动作在末帧还在动（139→140 帧差 6.0），接缝因此跳 7.4。
    这里改成按帧数精确取最后一帧；back>0 时保留旧的按时间回抽行为。
    """
    dur = probe(clip)["duration"] or 0
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    if back > 0:
        seek = max(0.0, dur - back)
        r = _run([ffmpeg(), "-y", "-ss", f"{seek:.3f}", "-i", clip, "-frames:v", "1",
                  "-update", "1", "-q:v", "2", out_png], timeout=180)
    else:
        # 先数帧（流拷贝，快），再 select 精确取最后一帧
        cnt = _run([ffmpeg(), "-i", clip, "-map", "0:v", "-c", "copy",
                    "-f", "null", "-"], timeout=300)
        n = 0
        for line in (cnt.stderr or "").splitlines():
            if "frame=" in line:
                n = int(line.split("frame=")[1].split()[0])
                break
        if n > 1:
            r = _run([ffmpeg(), "-y", "-i", clip, "-vf", f"select=eq(n\\,{n - 1})",
                      "-vsync", "vfr", "-frames:v", "1", "-q:v", "2", out_png], timeout=300)
        else:
            # 数帧失败：退回按时间抽最后一帧（一帧 ≈ 0.04s）
            r = _run([ffmpeg(), "-y", "-ss", f"{max(0.0, dur - 0.04):.3f}", "-i", clip,
                      "-frames:v", "1", "-update", "1", "-q:v", "2", out_png], timeout=180)
    if r.returncode != 0 or not os.path.isfile(out_png):
        raise RuntimeError(f"抽末帧失败：{clip}\n{(r.stderr or '')[-800:]}")
    return out_png


def poster(clip: str, out_png: str, at: float = 1.0) -> str:
    """抽一张封面帧给画布节点用（默认第 1 秒）。"""
    dur = probe(clip)["duration"] or 0
    seek = min(at, max(0.0, dur / 2))
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    r = _run([ffmpeg(), "-y", "-ss", f"{seek:.3f}", "-i", clip, "-frames:v", "1",
              "-update", "1", "-q:v", "2", out_png], timeout=180)
    return out_png if r.returncode == 0 and os.path.isfile(out_png) else ""


def concat(clips: list[str], out: str, subtitle: str = "") -> str:
    if not clips:
        raise ValueError("没有片段可拼")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    listfile = out + ".txt"
    with open(listfile, "w", encoding="utf-8") as f:
        for c in clips:
            f.write("file '%s'\n" % c.replace("\\", "/"))
    args = [ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", listfile,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart"]
    if subtitle and os.path.isfile(subtitle):
        esc = subtitle.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        args += ["-vf", f"subtitles='{esc}'"]
    args.append(out)
    r = _run(args)
    if r.returncode != 0:
        raise RuntimeError(f"拼接失败\n{(r.stderr or '')[-1500:]}")
    return out


def make_srt(rows: list[tuple[float, float, str]], path: str) -> str:
    """rows: (开始秒, 结束秒, 文本)。"""
    def ts(sec: float) -> str:
        ms = int(round(sec * 1000))
        return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)
    lines = []
    for i, (a, b, text) in enumerate(rows, 1):
        if not text.strip():
            continue
        lines.append(f"{i}\n{ts(a)} --> {ts(b)}\n{text.strip()}\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    return path


def _label_img(path: str, text: str, size: int = 34) -> str:
    """在图左上角烧一个中文标签，返回新文件路径。

    ffmpeg 的 drawtext 在 Windows 配中文字体很麻烦，直接用 PIL 画更稳。
    对照图不标注 = 没对比：两张图长得像的时候根本分不清谁是谁。
    """
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for fp in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.isfile(fp):
            try:
                font = ImageFont.truetype(fp, size)
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()

    im = Image.open(path).convert("RGB")
    draw = ImageDraw.Draw(im, "RGBA")
    pad = max(6, int(size * 0.35))
    try:
        box = draw.textbbox((0, 0), text, font=font)
        w, h = box[2] - box[0], box[3] - box[1]
    except AttributeError:
        w, h = len(text) * size // 2, size
    draw.rectangle([0, 0, w + pad * 2, h + pad * 2], fill=(0, 0, 0, 175))
    draw.text((pad, pad), text, font=font, fill=(255, 255, 255))

    out = os.path.splitext(path)[0] + "_lab.png"
    im.save(out)
    return out


def contact_sheet(pngs: list[str], out: str, height: int = 640,
                  labels: list[str] | None = None) -> str:
    """把若干张图横排拼成一张对照图。

    labels: 与 pngs 等长的文字，烧在每张图左上角。
    """
    if not pngs:
        raise ValueError("没有图")
    if labels:
        if len(labels) != len(pngs):
            raise ValueError(f"labels {len(labels)} 条，图 {len(pngs)} 张，对不上")
        pngs = [_label_img(p, lab) for p, lab in zip(pngs, labels)]
    inputs = []
    for p in pngs:
        inputs += ["-i", p]
    scaled = "".join(f"[{i}:v]scale=-1:{height}[s{i}];" for i in range(len(pngs)))
    joins = "".join(f"[s{i}]" for i in range(len(pngs)))
    graph = scaled + f"{joins}hstack=inputs={len(pngs)}[out]"
    r = _run([ffmpeg(), "-y", *inputs, "-filter_complex", graph, "-map", "[out]", out])
    if r.returncode != 0:
        raise RuntimeError(f"拼对照图失败\n{(r.stderr or '')[-800:]}")
    return out

def compose_grid(pngs: list[str], out: str, cols: int = 3, height: int = 520,
                 gap: int = 12, bg: tuple[int, int, int] = (232, 232, 232)) -> str:
    """把若干张图按 cols 列拼成网格，每张按高度等比缩放、列内水平居中。

    和 contact_sheet 的区别：contact_sheet 是横向一条（hstack），
    这个是多行多列，适合「6 表情 / 10 姿势 / 若干服饰」这种一整套参考板。
    """
    if not pngs:
        raise ValueError("没有图")
    from PIL import Image
    cols = max(1, int(cols))
    tiles = []
    for p in pngs:
        im = Image.open(p).convert("RGB")
        w = max(1, round(im.width * height / im.height))
        tiles.append(im.resize((w, height), Image.LANCZOS))
    rows = (len(tiles) + cols - 1) // cols
    cw = max(t.width for t in tiles)
    W = gap * (cols + 1) + cw * cols
    H = gap * (rows + 1) + height * rows
    sheet = Image.new("RGB", (W, H), bg)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        x = gap + c * (cw + gap) + (cw - t.width) // 2
        y = gap + r * (height + gap)
        sheet.paste(t, (x, y))
    sheet.save(out)
    return out


def grade_cinematic(clip: str, out: str, top: float = 1.10, bottom: float = 0.34,
                    crf: int = 16) -> str:
    """电影感调色：垂直渐变压暗下半幅，拉出「亮天 / 黑地」的上下分离。

    实测（对照官方样例）：模型自己最多把上/下亮度差拉到 19.5，
    样例是 34.3。差值主要来自地面——竹林湿地的反光天生偏亮，靠提示词压不下去。
    一条垂直渐变（顶部 ×top，底部 ×(top-bottom)）可以稳定做到 32.7–35.0，且完全确定性。
    """
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    expr = (f"geq=lum='clip(lum(X,Y)*({top:.3f}-{bottom:.3f}*Y/H),0,255)'"
            f":cb='cb(X,Y)':cr='cr(X,Y)'")


def fade_edges(clip: str, out: str, seconds: float = 0.3, crf: int = 16,
               audio: bool = True) -> str:
    """首尾淡入淡出到黑：给片段头尾各加一段渐黑，拼起来就是黑场过渡。

    为什么要这个：画布上那档「黑场 / 硬切」以前只是「不承接上一镜」——
    既不喂末帧也不传 latent，拼接走的 ffmpeg concat 直接首尾相接，
    **一帧黑场都没有**，名字是空头支票。这里在出片收尾时真的做淡入淡出。

    时长太短的片会自动把过渡减到 dur/3，避免整段全黑。
    """
    info = probe(clip)
    dur = float(info.get("duration") or 0)
    if dur <= 0:
        raise RuntimeError("淡入淡出：读不到片段时长")
    d = min(float(seconds), dur / 3.0, 1.0)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    # setpts 归零很重要：ComfyUI 输出的 mp4 起始 PTS 不一定是 0，
    # 不归零的话 fade=t=out 的 st 会错位——实测首帧淡入生效、末尾却一点没黑。
    vf = (f"setpts=PTS-STARTPTS,"
          f"fade=t=in:st=0:d={d:.3f},"
          f"fade=t=out:st={max(0.0, dur - d):.3f}:d={d:.3f}")
    args = [ffmpeg(), "-y", "-i", clip, "-vf", vf]
    if audio:
        args += ["-af", (f"asetpts=PTS-STARTPTS,"
                         f"afade=t=in:st=0:d={d:.3f},"
                         f"afade=t=out:st={max(0.0, dur - d):.3f}:d={d:.3f}")]
    args += ["-c:v", "libx264", "-crf", str(crf), "-c:a", "aac", "-b:a", "192k", out]
    r = _run(args, timeout=1200)
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError("淡入淡出失败：\n" + (r.stderr or "")[-600:])
    return out
    r = _run([ffmpeg(), "-y", "-i", clip, "-vf",
              f"format=yuv444p,{expr},format=yuv420p",
              "-c:v", "libx264", "-crf", str(crf), "-c:a", "copy", out], timeout=1200)
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError("调色失败：\n" + (r.stderr or "")[-600:])
    return out
