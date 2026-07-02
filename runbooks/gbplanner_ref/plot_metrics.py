#!/usr/bin/env python3
"""把探索指标 CSV(ros_time,x,y,z,tsdf_points,homing)画成 SVG 曲线图(纯标准库,无 matplotlib)。
用法: python3 plot_metrics.py <csv> <out.svg>
之后: rsvg-convert -w 1400 <out.svg> -o <out.png>   (WSL 已装 fonts-noto-cjk)
"""
import csv, math, sys


def main():
    csv_path, out_svg = sys.argv[1], sys.argv[2]
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((float(r["ros_time"]), float(r["x"]), float(r["y"]),
                             float(r["z"]), float(r["tsdf_points"]), int(r["homing"])))
            except (ValueError, KeyError):
                continue
    if len(rows) < 3:
        raise SystemExit("样本太少: %d" % len(rows))

    t0 = rows[0][0]
    ts = [r[0] - t0 for r in rows]
    # 累计路径长度
    path = [0.0]
    for i in range(1, len(rows)):
        d = math.dist(rows[i][1:4], rows[i - 1][1:4])
        path.append(path[-1] + (d if d < 30 else 0))
    tsdf = [r[4] for r in rows]
    homing_t = next((ts[i] for i, r in enumerate(rows) if r[5] > 0), None)

    W, H, ML, MR, MT, MB = 1400, 640, 90, 90, 70, 70
    pw, ph = W - ML - MR, H - MT - MB
    tmax = max(ts) or 1
    pmax = max(path) or 1
    mmax = max(tsdf) or 1

    def X(t): return ML + t / tmax * pw
    def Y1(v): return MT + ph - v / pmax * ph          # 路径长度(左轴)
    def Y2(v): return MT + ph - v / mmax * ph          # 地图点数(右轴)

    def poly(pts): return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'font-family="Noto Sans CJK SC, sans-serif" font-size="20">')
    s.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    s.append(f'<text x="{W/2}" y="40" text-anchor="middle" font-size="26" font-weight="bold">'
             f'GBPlanner 自主探索实测曲线(box 迷宫,时间预算 480s)</text>')
    # 坐标框 + 网格
    s.append(f'<rect x="{ML}" y="{MT}" width="{pw}" height="{ph}" fill="none" stroke="#94a3b8"/>')
    for k in range(1, 5):
        gy = MT + ph * k / 5
        s.append(f'<line x1="{ML}" y1="{gy}" x2="{ML+pw}" y2="{gy}" stroke="#e2e8f0"/>')
    # 曲线
    s.append(f'<polyline points="{poly(list(zip(map(X, ts), map(Y1, path))))}" '
             f'fill="none" stroke="#2563eb" stroke-width="3"/>')
    s.append(f'<polyline points="{poly(list(zip(map(X, ts), map(Y2, tsdf))))}" '
             f'fill="none" stroke="#16a34a" stroke-width="3"/>')
    # 返航标记
    if homing_t is not None:
        s.append(f'<line x1="{X(homing_t)}" y1="{MT}" x2="{X(homing_t)}" y2="{MT+ph}" '
                 f'stroke="#dc2626" stroke-width="2" stroke-dasharray="8,5"/>')
        s.append(f'<text x="{X(homing_t)+8}" y="{MT+26}" fill="#dc2626">返航触发</text>')
    # 轴标注
    s.append(f'<text x="{ML}" y="{H-25}">0s</text>')
    s.append(f'<text x="{ML+pw-40}" y="{H-25}">{tmax:.0f}s</text>')
    s.append(f'<text x="{ML-10}" y="{MT+14}" text-anchor="end" fill="#2563eb">{pmax:.1f}m</text>')
    s.append(f'<text x="{ML+pw+10}" y="{MT+14}" fill="#16a34a">{mmax:.0f}点</text>')
    s.append(f'<text x="{ML}" y="{MT-14}" fill="#2563eb">━ 累计飞行路径长度(左轴)</text>')
    s.append(f'<text x="{ML+430}" y="{MT-14}" fill="#16a34a">━ voxblox 地图规模/表面点数(右轴)</text>')
    s.append('</svg>')
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write("\n".join(s))
    print(f"OK {out_svg}  样本={len(rows)} 路径={path[-1]:.1f}m 地图峰值={mmax:.0f} 返航t={homing_t}")


if __name__ == "__main__":
    main()
