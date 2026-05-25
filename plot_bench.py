#!/usr/bin/env python3
"""
Plot benchmark results — SVG or ASCII.
=======================================
Reads benchmark_report.json and generates visualisations.

If matplotlib is available → real SVG/PNG plots.
Otherwise → pure-Python SVG builder (no dependencies).
Also supports --ascii mode for terminal bar charts.

Usage:
    python3 plot_bench.py benchmark_report.json [--output-dir DIR]
                                               [--ascii] [--svg]
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path

HAS_MPL = False
try:
    import matplotlib
    matplotlib.use("Agg")  # headless
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════════
# Pure-Python SVG builder
# ═══════════════════════════════════════════════════════════════════

def _svg_bar_chart(data: list[dict], width: int = 800, height: int = 500,
                   title: str = "A+ Benchmark — Execution Time") -> str:
    """Build an SVG bar chart from benchmark results."""
    if not data:
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'

    names = [d["file"].replace(".a+", "") for d in data]
    values = [d["time_ms"] for d in data]

    margin_left = 180
    margin_right = 30
    margin_top = 60
    margin_bottom = 80

    chart_w = width - margin_left - margin_right
    chart_h = height - margin_top - margin_bottom

    max_val = max(values) if values else 1
    bar_w = max(8, (chart_w / len(names)) * 0.7)
    gap = chart_w / len(names)

    # Colors
    passed = [d["exit_code"] == 0 for d in data]
    green = "#4CAF50"
    red = "#F44336"

    rects = ""
    labels = ""
    for i, (name, val, ok) in enumerate(zip(names, values, passed)):
        x = margin_left + i * gap + (gap - bar_w) / 2
        bar_h = max(2, (val / max_val) * chart_h)
        y = margin_top + chart_h - bar_h
        color = green if ok else red
        rects += (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" fill="{color}" opacity="0.85">'
            f'<title>{name}: {val:.2f}ms ({"pass" if ok else "fail"})</title>'
            f'</rect>\n'
        )
        # time label above bar
        rects += (
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 4:.1f}" '
            f'text-anchor="middle" font-size="10" fill="#333">{val:.1f}ms</text>\n'
        )
        # x-axis label (rotated)
        labels += (
            f'<text x="{x + bar_w / 2:.1f}" y="{height - margin_bottom + 16:.1f}" '
            f'transform="rotate(-45,{x + bar_w / 2:.1f},{height - margin_bottom + 16:.1f})" '
            f'text-anchor="end" font-size="9" fill="#555">{name[:20]}</text>\n'
        )

    grid = ""
    for i in range(6):
        y = margin_top + chart_h * (i / 5)
        val = max_val * (1 - i / 5)
        grid += (
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" '
            f'y2="{y:.1f}" stroke="#ddd" stroke-width="0.5"/>\n'
        )
        grid += (
            f'<text x="{margin_left - 6}" y="{y + 4:.1f}" '
            f'text-anchor="end" font-size="9" fill="#888">{val:.1f}</text>\n'
        )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="{width / 2}" y="{margin_top / 2 + 5}" text-anchor="middle"
        font-size="16" font-weight="bold" fill="#222">{title}</text>
  <!-- axes -->
  <line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}"
        y2="{height - margin_bottom}" stroke="#333" stroke-width="1.5"/>
  <line x1="{margin_left}" y1="{height - margin_bottom}"
        x2="{width - margin_right}" y2="{height - margin_bottom}"
        stroke="#333" stroke-width="1.5"/>
  <!-- y-axis label -->
  <text x="16" y="{margin_top + chart_h / 2}" text-anchor="middle"
        transform="rotate(-90,16,{margin_top + chart_h / 2})"
        font-size="12" fill="#555">Time (ms)</text>
  {grid}
  {rects}
  {labels}
  <!-- legend -->
  <rect x="{width - 180}" y="{margin_top - 30}" width="14" height="14" fill="{green}" opacity="0.85"/>
  <text x="{width - 160}" y="{margin_top - 18}" font-size="11" fill="#333">Pass</text>
  <rect x="{width - 130}" y="{margin_top - 30}" width="14" height="14" fill="{red}" opacity="0.85"/>
  <text x="{width - 110}" y="{margin_top - 18}" font-size="11" fill="#333">Fail/Timeout</text>
</svg>'''
    return svg


def _svg_summary_pie(passed: int, failed: int, timeouts: int,
                     width: int = 400, height: int = 400) -> str:
    """Build a simple donut chart showing pass/fail/timeout breakdown."""
    total = passed + failed + timeouts
    if total == 0:
        return '<svg xmlns="http://www.w3.org/2000/svg"></svg>'

    slices = []
    if passed > 0:
        slices.append((passed, "#4CAF50", "Pass"))
    if failed > 0:
        slices.append((failed, "#F44336", "Fail"))
    if timeouts > 0:
        slices.append((timeouts, "#FF9800", "Timeout"))

    cx, cy, r = width / 2, height / 2, min(width, height) / 3
    ir = r * 0.55  # inner radius for donut

    paths = ""
    start_angle = -90  # start from top
    for count, color, label in slices:
        angle = (count / total) * 360
        pct = count / total * 100
        # Calculate arc
        rad = math.radians(start_angle)
        rad2 = math.radians(start_angle + angle)

        x1 = cx + r * math.cos(rad)
        y1 = cy + r * math.sin(rad)
        x2 = cx + r * math.cos(rad2)
        y2 = cy + r * math.sin(rad2)
        ix1 = cx + ir * math.cos(rad)
        iy1 = cy + ir * math.sin(rad)
        ix2 = cx + ir * math.cos(rad2)
        iy2 = cy + ir * math.sin(rad2)

        large = 1 if angle > 180 else 0

        if angle >= 359.99:
            # Full circle
            path = (
                f'M {cx} {cy - r} '
                f'A {r} {r} 0 1 1 {cx - 0.001} {cy - r} '
                f'L {cx - 0.001} {cy - ir} '
                f'A {ir} {ir} 0 1 0 {cx} {cy - ir} Z'
            )
        else:
            path = (
                f'M {x1:.2f} {y1:.2f} '
                f'A {r} {r} 0 {large} 1 {x2:.2f} {y2:.2f} '
                f'L {ix2:.2f} {iy2:.2f} '
                f'A {ir} {ir} 0 {large} 0 {ix1:.2f} {iy1:.2f} Z'
            )
        paths += f'<path d="{path}" fill="{color}" opacity="0.85"/>\n'

        # Label
        mid = math.radians(start_angle + angle / 2)
        lx = cx + (r * 1.3) * math.cos(mid)
        ly = cy + (r * 1.3) * math.sin(mid)
        paths += (
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
            f'font-size="11" fill="#333">{label}: {pct:.0f}%</text>\n'
        )

        start_angle += angle

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"
     viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="white"/>
  <text x="{width / 2}" y="24" text-anchor="middle"
        font-size="14" font-weight="bold" fill="#222">Pass/Fail Breakdown</text>
  {paths}
  <text x="{cx}" y="{cy + 4}" text-anchor="middle"
        font-size="18" font-weight="bold" fill="#333">{total}</text>
  <text x="{cx}" y="{cy + 18}" text-anchor="middle"
        font-size="11" fill="#666">total</text>
</svg>'''
    return svg


# ═══════════════════════════════════════════════════════════════════
# ASCII bar chart (terminal-friendly)
# ═══════════════════════════════════════════════════════════════════

def ascii_bar_chart(data: list[dict], width: int = 60):
    """Print an ASCII bar chart to stdout."""
    if not data:
        print("(no data)")
        return

    names = [d["file"].replace(".a+", "") for d in data]
    values = [d["time_ms"] for d in data]
    max_val = max(values) if values else 1
    max_name = max(len(n) for n in names)

    print(f"\n{'─' * (width + max_name + 20)}")
    print("  A+ Benchmark — Execution Time (ms)")
    print(f"{'─' * (width + max_name + 20)}")

    for name, val, d in zip(names, values, data):
        bar_len = int((val / max_val) * width) if max_val > 0 else 0
        bar = "█" * bar_len + "░" * (width - bar_len)
        status = "✅" if d["exit_code"] == 0 else ("⏱️" if d.get("timeout") else "❌")
        print(f"  {name:<{max_name}} {bar} {val:8.2f}ms {status}")

    print(f"{'─' * (width + max_name + 20)}")
    print(f"  Total: {len(data)} files  |  Mean: {sum(values) / max(len(values), 1):.2f}ms")


# ═══════════════════════════════════════════════════════════════════
# Matplotlib plots (if available)
# ═══════════════════════════════════════════════════════════════════

def mpl_bar_chart(data: list[dict], out_path: str):
    """Generate a matplotlib bar chart."""
    if not data:
        return

    names = [d["file"].replace(".a+", "") for d in data]
    values = [d["time_ms"] for d in data]
    colors = ["#4CAF50" if d["exit_code"] == 0 else "#F44336" for d in data]

    fig, ax = plt.subplots(figsize=(14, 6))
    bars = ax.bar(range(len(names)), values, color=colors, edgecolor="#333", linewidth=0.5)

    # Value labels on top
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.01,
                f"{val:.1f}", ha="center", va="bottom", fontsize=8, color="#333")

    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Time (ms)")
    ax.set_title("A+ Benchmark — Execution Time per File")
    ax.set_ylim(0, max(values) * 1.15)
    ax.grid(axis="y", alpha=0.3)

    # Legend
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color="#4CAF50", label="Pass"),
        Patch(color="#F44336", label="Fail/Timeout"),
    ], loc="upper right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    print(f"  Matplotlib chart → {out_path}")


def mpl_summary_pie(passed: int, failed: int, timeouts: int, out_path: str):
    """Generate a matplotlib donut chart."""
    labels = ["Pass", "Fail", "Timeout"]
    sizes = [passed, failed, timeouts]
    colors = ["#4CAF50", "#F44336", "#FF9800"]
    # Filter out zero entries
    filtered = [(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0]
    if not filtered:
        return
    labels, sizes, colors = zip(*filtered)

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, pctdistance=0.75,
    )
    # Donut
    centre_circle = plt.Circle((0, 0), 0.55, fc="white")
    ax.add_artist(centre_circle)
    ax.text(0, 0, str(sum(sizes)), ha="center", va="center",
            fontsize=20, fontweight="bold")
    ax.text(0, -0.15, "total", ha="center", va="center", fontsize=10, color="#666")
    ax.set_title("Pass/Fail Breakdown")

    fig.tight_layout()
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    print(f"  Matplotlib pie → {out_path}")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Plot A+ benchmark results from JSON report"
    )
    ap.add_argument("json_report", help="Path to benchmark_report.json")
    ap.add_argument("--output-dir", "-o", default=".",
                    help="Directory for output plots (default: current dir)")
    ap.add_argument("--ascii", action="store_true",
                    help="Print ASCII bar chart to terminal")
    ap.add_argument("--svg", action="store_true",
                    help="Generate SVG plots (pure Python, no deps)")
    ap.add_argument("--format", choices=["svg", "png"], default="svg",
                    help="Output format for matplotlib (default: svg)")
    args = ap.parse_args()

    # Load data
    report_path = Path(args.json_report)
    if not report_path.exists():
        print(f"Error: {report_path} not found")
        sys.exit(1)

    with open(report_path) as f:
        report = json.load(f)

    results = report.get("results", [])
    summary = report.get("summary", {})

    if not results:
        print("No results in report.")
        sys.exit(0)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ASCII mode
    if args.ascii:
        ascii_bar_chart(results)
        # Also print summary
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        timeouts = summary.get("timeout", 0)
        print(f"\n  Pass: {passed} | Fail: {failed} | Timeout: {timeouts}")
        print(f"  Total time: {summary.get('total_time_ms', 0):.1f}ms")

    # Matplotlib mode
    if HAS_MPL and not args.ascii:
        ext = args.format
        # Bar chart
        bar_path = out_dir / f"benchmark_times.{ext}"
        mpl_bar_chart(results, str(bar_path))

        # Pie/donut
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0) - summary.get("timeout", 0)
        timeouts = summary.get("timeout", 0)
        pie_path = out_dir / f"benchmark_summary.{ext}"
        mpl_summary_pie(passed, failed, timeouts, str(pie_path))

        # Comparison if present
        if "python" in report:
            # Plot comparison bar chart
            py_times = {c["file"]: c.get("time_ms", 0)
                         for c in report.get("python", [])}
            js_times = {c["file"]: c.get("time_ms", 0)
                         for c in report.get("javascript", [])}
            aplus_times = {r["file"]: r.get("time_ms", 0) for r in results}

            indices = []
            aplus_data = []
            py_data = []
            js_data = []
            names_cmp = []
            for i, r in enumerate(results):
                f = r["file"]
                if f in py_times or f in js_times:
                    indices.append(i)
                    aplus_data.append(aplus_times.get(f, 0))
                    py_data.append(py_times.get(f, 0))
                    js_data.append(js_times.get(f, 0))
                    names_cmp.append(f.replace(".a+", ""))

            if indices:
                fig, ax = plt.subplots(figsize=(14, 6))
                x = range(len(names_cmp))
                w = 0.25
                ax.bar([i - w for i in x], aplus_data, w, label="A+", color="#4CAF50", alpha=0.85)
                ax.bar(x, py_data, w, label="Python", color="#2196F3", alpha=0.85)
                ax.bar([i + w for i in x], js_data, w, label="JavaScript", color="#FFC107", alpha=0.85)
                ax.set_xticks(x)
                ax.set_xticklabels(names_cmp, rotation=45, ha="right", fontsize=8)
                ax.set_ylabel("Time (ms)")
                ax.set_title("A+ vs Python vs JavaScript — Execution Time")
                ax.legend()
                ax.grid(axis="y", alpha=0.3)
                fig.tight_layout()
                cmp_path = out_dir / f"benchmark_comparison.{ext}"
                fig.savefig(str(cmp_path), dpi=100)
                plt.close(fig)
                print(f"  Matplotlib comparison → {cmp_path}")

    # Pure-Python SVG mode (no matplotlib)
    elif args.svg or (not HAS_MPL and not args.ascii):
        print("  Generating pure-Python SVGs (no matplotlib available)")

        bar_svg = _svg_bar_chart(results)
        bar_path = out_dir / "benchmark_times.svg"
        with open(bar_path, "w", encoding="utf-8") as f:
            f.write(bar_svg)
        print(f"  SVG bar chart → {bar_path}")

        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0) - summary.get("timeout", 0)
        timeouts = summary.get("timeout", 0)
        pie_svg = _svg_summary_pie(passed, failed, timeouts)
        pie_path = out_dir / "benchmark_summary.svg"
        with open(pie_path, "w", encoding="utf-8") as f:
            f.write(pie_svg)
        print(f"  SVG donut chart → {pie_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
