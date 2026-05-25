#!/usr/bin/env python3
"""
A+ Benchmark Suite
==================
Runs all .a+ files through the interpreter, times each execution, and
generates JSON + Markdown reports.

Usage:
    python3 benchmark.py [--interpreter PATH] [--seed SEED]
                         [--compare] [--output-dir DIR]
                         [--warmup N]

Optional: --compare transpiles to Python/JS and times those too.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────

def git_commit(repo: Path) -> str:
    """Return current git commit hash (short), or 'unknown'."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo, capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def line_count(path: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(path, "rb") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def run_interpreter(interpreter: str, src: Path, timeout: int = 30) -> dict:
    """Run a single .a+ file through the interpreter. Returns result dict."""
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [interpreter, str(src)],
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "file": str(src.name),
            "time_ms": round(elapsed_ms, 3),
            "exit_code": proc.returncode,
            "stdout_lines": len(proc.stdout.splitlines()) if proc.stdout else 0,
            "stderr_lines": len(proc.stderr.splitlines()) if proc.stderr else 0,
            "timeout": False,
            "error": proc.stderr[:500] if proc.returncode != 0 and proc.stderr else None,
        }
    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "file": str(src.name),
            "time_ms": round(elapsed_ms, 3),
            "exit_code": -1,
            "stdout_lines": 0,
            "stderr_lines": 0,
            "timeout": True,
            "error": "timeout",
        }


def run_transpiled(language: str, src: Path, transpiler: str,
                   timeout: int = 30) -> dict:
    """
    Transpile a .a+ file to Python or JS, then run the generated code.
    Returns timing data, or error info.
    """
    suffix = ".py" if language == "python" else ".js"
    runner = "python3" if language == "python" else "node"

    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix,
                                     delete=False) as tmp:
        out_path = tmp.name

    try:
        # Transpile
        flag = "--output-py" if language == "python" else "--output-js"
        r = subprocess.run(
            [sys.executable, transpiler, "--input", str(src), flag, out_path],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            return {
                "language": language,
                "transpile_ok": False,
                "time_ms": 0,
                "exit_code": -1,
                "error": f"transpile failed: {r.stderr[:200]}",
            }

        # Run
        start = time.perf_counter()
        proc = subprocess.run(
            [runner, out_path],
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "language": language,
            "transpile_ok": True,
            "time_ms": round(elapsed_ms, 3),
            "exit_code": proc.returncode,
            "error": proc.stderr[:300] if proc.returncode != 0 and proc.stderr else None,
        }
    except subprocess.TimeoutExpired:
        return {
            "language": language,
            "transpile_ok": True,
            "time_ms": round(timeout * 1000, 0),
            "exit_code": -1,
            "error": "timeout",
        }
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


# ── report generators ────────────────────────────────────────────

def write_json_report(results: list[dict], meta: dict, path: Path):
    """Write the JSON report."""
    report = {
        "meta": meta,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "summary": {
            "total_files": len(results),
            "passed": sum(1 for r in results if r.get("exit_code") == 0),
            "failed": sum(1 for r in results if r.get("exit_code", 0) != 0),
            "timeout": sum(1 for r in results if r.get("timeout", False)),
            "total_time_ms": round(sum(r.get("time_ms", 0) for r in results), 3),
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"  JSON report  → {path}")


def write_markdown_report(results: list[dict], meta: dict, path: Path,
                          compare_results: dict[str, list[dict]] | None = None):
    """Write a Markdown table report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# A+ Benchmark Report",
        "",
        f"**Generated:** {now}",
        f"**Interpreter:** `{meta['interpreter']}`",
        f"**Seed:** `{meta['seed']}`",
        f"**Commit:** `{meta['commit']}`",
        f"**Total files:** {len(results)}",
        "",
        "## Results",
        "",
        "| # | File | Time (ms) | Exit | Lines | Status |",
        "|---|------|-----------|------|-------|--------|",
    ]

    for i, r in enumerate(results, 1):
        status = "✅" if r["exit_code"] == 0 else ("⏱️" if r.get("timeout") else "❌")
        lines.append(
            f"| {i} | `{r['file']}` | {r['time_ms']:.2f} | {r['exit_code']} "
            f"| {r.get('lines', line_count(Path(meta.get('corpus_dir', '.')) / r['file']))} "
            f"| {status} |"
        )

    # Summary
    passed = sum(1 for r in results if r["exit_code"] == 0)
    failed = sum(1 for r in results if r.get("exit_code", 0) != 0 and not r.get("timeout"))
    timed_out = sum(1 for r in results if r.get("timeout"))
    total_ms = sum(r["time_ms"] for r in results)

    lines += [
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total files | {len(results)} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Timeouts | {timed_out} |",
        f"| Total time | {total_ms:.1f} ms |",
        f"| Mean time | {total_ms / max(len(results), 1):.2f} ms |",
        f"| Min time | {min(r['time_ms'] for r in results):.2f} ms |",
        f"| Max time | {max(r['time_ms'] for r in results):.2f} ms |",
    ]

    # Comparison section
    if compare_results:
        lines += [
            "",
            "## Comparison with Transpiled Outputs",
            "",
        ]
        for lang, comps in compare_results.items():
            if not comps:
                continue
            lines += [
                f"### {lang.capitalize()}",
                "",
                "| # | File | A+ (ms) | " + f"{lang.capitalize()} (ms) | Ratio |",
                "|---|------|----------|" + "-" * (len(lang) + 7) + "|-------|",
            ]
            # Build a lookup
            aplus_by_file = {r["file"]: r["time_ms"] for r in results}
            for c in comps:
                aplus_ms = aplus_by_file.get(c.get("file", ""), 0)
                trans_ms = c.get("time_ms", 0)
                ratio = f"{trans_ms / aplus_ms:.2f}x" if aplus_ms > 0 else "N/A"
                status = "✅" if c.get("transpile_ok") else "❌"
                lines.append(
                    f"| {c.get('file', '?')} | "
                    f"{aplus_ms:.2f} | {trans_ms:.2f} | {ratio} | {status}"
                )

    lines += [
        "",
        "---",
        "*Generated by `benchmark.py`*",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Markdown report → {path}")


# ── main ─────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="A+ Benchmark Suite — run all .a+ files and generate reports"
    )
    ap.add_argument(
        "--interpreter", "-i", default="./aplus-install/bin/a+",
        help="Path to the A+ interpreter binary (default: ./aplus-install/bin/a+)",
    )
    ap.add_argument(
        "--corpus-dir", "-d", default=".",
        help="Directory containing .a+ files (default: current dir)",
    )
    ap.add_argument(
        "--output-dir", "-o", default=".",
        help="Directory for report output files (default: current dir)",
    )
    ap.add_argument(
        "--seed", "-s", type=int, default=None,
        help="Random seed for reproducibility (if any fuzzing/randomization is needed)",
    )
    ap.add_argument(
        "--warmup", "-w", type=int, default=1,
        help="Number of warmup runs per file before timing (default: 1)",
    )
    ap.add_argument(
        "--timeout", "-t", type=int, default=30,
        help="Timeout per file in seconds (default: 30)",
    )
    ap.add_argument(
        "--compare", action="store_true",
        help="Also transpile to Python/JS and compare timing",
    )
    ap.add_argument(
        "--transpiler", default="./transpile_aplus.py",
        help="Path to transpile_aplus.py (default: ./transpile_aplus.py)",
    )
    ap.add_argument(
        "--json-only", action="store_true",
        help="Only produce JSON report (skip Markdown)",
    )
    ap.add_argument(
        "--files", nargs="*",
        help="Specific .a+ files to run (default: all *.a+ in corpus-dir)",
    )
    args = ap.parse_args()

    # Resolve paths
    repo = Path(args.corpus_dir).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    interpreter = args.interpreter
    transpiler = args.transpiler

    # Check interpreter
    if not os.path.isfile(interpreter) and not args.compare:
        print(f"Warning: interpreter not found at {interpreter}")
        # Continue anyway — CI may download it later

    # Gather files
    if args.files:
        aplus_files = [repo / f for f in args.files if f.endswith(".a+")]
    else:
        aplus_files = sorted(repo.glob("*.a+"))

    if not aplus_files:
        print(f"No .a+ files found in {repo}")
        sys.exit(1)

    # Metadata
    commit = git_commit(repo)
    seed = args.seed if args.seed is not None else int(time.time())
    meta = {
        "interpreter": interpreter,
        "corpus_dir": str(repo),
        "seed": seed,
        "commit": commit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    print(f"Benchmark Suite — {len(aplus_files)} files")
    print(f"  Interpreter: {interpreter}")
    print(f"  Seed: {seed}")
    print(f"  Commit: {commit}")
    print()

    # ── Benchmark A+ native ──────────────────────────────────────
    results = []
    for i, src in enumerate(aplus_files, 1):
        name = src.name.ljust(35)
        print(f"  [{i:2d}/{len(aplus_files)}] {name}", end=" ", flush=True)

        # Warmup
        for _ in range(args.warmup):
            run_interpreter(interpreter, src, timeout=args.timeout)

        # Timed run
        r = run_interpreter(interpreter, src, timeout=args.timeout)
        r["lines"] = line_count(src)
        results.append(r)

        status = "✅" if r["exit_code"] == 0 else ("⏱️" if r["timeout"] else "❌")
        print(f"{r['time_ms']:8.2f}ms  exit={r['exit_code']}  {status}")

    # ── Comparison mode (transpile + run) ────────────────────────
    compare_results = None
    if args.compare:
        compare_results = {"python": [], "javascript": []}
        print("\n── Comparison mode (transpile → Python / JS) ──")
        for lang in ("python", "javascript"):
            lang_label = "Python" if lang == "python" else "JavaScript"
            print(f"\n  [{lang_label}]")
            for i, src in enumerate(aplus_files, 1):
                name = src.name.ljust(35)
                print(f"    [{i:2d}/{len(aplus_files)}] {name}", end=" ", flush=True)
                r = run_transpiled(lang, src, transpiler, timeout=args.timeout)
                r["file"] = src.name
                compare_results[lang].append(r)
                status = "✅" if r.get("exit_code") == 0 else "❌"
                print(f"{r.get('time_ms', 0):8.2f}ms  {status}")

    # ── Generate reports ─────────────────────────────────────────
    print()
    json_path = out_dir / "benchmark_report.json"
    write_json_report(results, meta, json_path)

    if not args.json_only:
        md_path = out_dir / "benchmark_report.md"
        write_markdown_report(results, meta, md_path, compare_results)

    # Set output for CI
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"json_report={json_path}\n")
            if not args.json_only:
                f.write(f"md_report={out_dir / 'benchmark_report.md'}\n")

    # Summary
    passed = sum(1 for r in results if r["exit_code"] == 0)
    if passed == len(results):
        print("\n✓ All files passed!")
    else:
        print(f"\n⚠ {passed}/{len(results)} passed ({len(results) - passed} failed/timeout)")


if __name__ == "__main__":
    main()
