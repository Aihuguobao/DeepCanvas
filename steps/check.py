"""体检：时长/分辨率/运动曲线/风格漂移。出片之后先量，再下结论。"""
from __future__ import annotations

from core import media, qa, store


def run(ep: str, motion: bool = True) -> dict:
    items = store.shots(ep)
    done = [s for s in items if (s.get("state") or {}).get("video")]
    if not done:
        raise RuntimeError(f"{ep} 还没有能体检的视频")

    rows = []
    print(f"{'镜头':<6}{'时长':>7}{'分辨率':>12}{'运动':>7}{'峰值':>7}{'尾/中':>7}{'最长低潮':>9}")
    for s in done:
        p = s["state"]["video"]
        info = media.probe(p)
        m = qa.motion(p) if motion else {}
        st = qa.style_stats(p, step=0.5) if motion else {}
        rows.append({"id": s["id"], "info": info, "motion": m, "style": st})
        print(f"{s['id']:<6}{info['duration']:>6}s{info['size']:>12}"
              f"{m.get('mean', 0):>7}{m.get('peak', 0):>7}{m.get('tail_ratio', 0):>7}"
              f"{str(m.get('longest_lull_s', 0)) + 's':>9}")

    total = sum(r["info"]["duration"] for r in rows)
    print(f"\n合计 {total:.1f}s / {len(rows)} 镜")

    slow = [r["id"] for r in rows if r["motion"].get("longest_lull_s", 0) > 1.5]
    if slow:
        print(f"低潮超过 1.5 秒：{', '.join(slow)}　→ 这一段在慢动作，缩短时长或把动作前置")

    if len(rows) > 1:
        base = rows[0]
        for r in rows[1:]:
            diff = qa.compare(base["style"], r["style"])
            if diff:
                print(f"画风漂移 {base['id']} ↔ {r['id']}：{'；'.join(diff)}")
        if all(not qa.compare(base["style"], r["style"]) for r in rows[1:]):
            print("画风：整集在 20% 以内，稳")
    return {"rows": rows, "total": total}
