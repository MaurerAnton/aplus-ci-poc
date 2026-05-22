#!/usr/bin/env python3
"""
Grammar-based fuzzer for the A+ programming language interpreter.

Generates valid A+ programs with KAPL encoding and runs them through
the interpreter to find crashes, hangs, and unexpected behavior.

Usage:
    python3 fuzz_aplus.py /path/to/a+ [--seed SEED] [--count N]
    python3 fuzz_aplus.py /path/to/a+ --quick        # basic smoke test
    python3 fuzz_aplus.py /path/to/a+ --seed 42 -n 100

This has never been done for A+ before.
"""

import random
import subprocess
import sys
import time
import os
import tempfile
from pathlib import Path

# ── KAPL encoding ──────────────────────────────────────────────
# A+ uses KAPL font encoding (not UTF-8) for APL glyphs in .a+ files
KAPL = {
    "assign": b"\xfb",   # ←
    "print":  b"\xd5",   # ⎕
    "comment": b"\xe3",  # ⍝
    "rho":    b"\xce",   # ⍴
    "divide": b"\xdf",   # ÷
    "multiply": b"\xc1", # ×
    "iota":   b"\xa2",   # ⍳
    "max":    b"\xab",   # ⌈
    "member": b"\xa8",   # ∊
}

# ── Grammar ─────────────────────────────────────────────────────
# AST-like grammar for valid A+ programs

def lit_int():
    """Random integer literal."""
    return str(random.randint(0, 9999))

def lit_float():
    """Random float literal."""
    return f"{random.uniform(0.0, 100.0):.4f}"

def lit_scalar():
    """Random numeric scalar."""
    if random.random() < 0.5:
        return lit_int()
    return lit_float()

def expr_atom(depth=0):
    """Atom: literal or variable reference."""
    if depth > 3 or random.random() < 0.3:
        return lit_scalar()
    return random.choice(["a", "b", "c", "x", "y", "z"])

BINOPS = {
    "+": b"+",
    "-": b"-",
    "*": b"*",
    "divide": KAPL["divide"],
    "max": KAPL["max"],
}

def expr_binary(depth=0):
    """Binary expression: atom OP atom."""
    left = expr_atom(depth + 1)
    op_name, op_byte = random.choice(list(BINOPS.items()))
    right = expr_atom(depth + 1)
    # Use bytes only for non-ASCII operators
    if isinstance(op_byte, bytes):
        return f"{left}".encode() + op_byte + f"{right}".encode()
    else:
        return f"{left}{op_byte}{right}".encode()

def expr(depth=0):
    """General expression."""
    if depth > 5:
        return expr_atom(depth).encode() if isinstance(expr_atom(depth), str) else expr_atom(depth)
    return expr_binary(depth)

def statement_assign():
    """x←expr"""
    var = random.choice(["a", "b", "c", "x", "y", "z", "tmp"])
    e = expr()
    return var.encode() + KAPL["assign"] + (e if isinstance(e, bytes) else e.encode())

def statement_print():
    """⎕"string" """
    msg = random.choice([
        "hello", "test", "ok", "value:", "result",
        "pass", "running", "check", "done", "A+ fuzz"
    ])
    return KAPL["print"] + b'"' + msg.encode() + b'"'

def statement_if():
    """if (cond) { stmt } """
    cond = expr()
    body = statement_assign()
    return (b"if (" + (cond if isinstance(cond, bytes) else cond.encode()) +
            b") { " + (body if isinstance(body, bytes) else body.encode()) + b" }")

def statement(depth=0):
    """Random A+ statement."""
    if depth > 8:
        return statement_print()
    kind = random.choice(["assign", "print", "if"])
    if kind == "assign":
        return statement_assign()
    elif kind == "print":
        return statement_print()
    else:
        return statement_if()

def generate_program(num_statements=None):
    """Generate a complete A+ program with KAPL encoding."""
    if num_statements is None:
        num_statements = random.randint(2, 15)

    lines = [KAPL["comment"] + b" fuzz-generated A+ program"]
    for _ in range(num_statements):
        stmt = statement()
        if isinstance(stmt, bytes):
            lines.append(stmt + b";")
        else:
            lines.append(stmt.encode() + b";")
    lines.append(KAPL["print"] + b'"fuzz done"')

    return b"\n".join(lines)

def run_aplus(interpreter_path, program_bytes, timeout=5):
    """Run A+ interpreter on a program and return result."""
    with tempfile.NamedTemporaryFile(
        mode="wb", suffix=".a+", delete=False
    ) as f:
        f.write(program_bytes)
        tmpfile = f.name

    try:
        start = time.time()
        result = subprocess.run(
            [interpreter_path, tmpfile],
            capture_output=True,
            timeout=timeout,
            text=False,
        )
        elapsed = time.time() - start

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed": elapsed,
            "file": tmpfile,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": b"",
            "stderr": b"TIMEOUT",
            "elapsed": timeout,
            "file": tmpfile,
            "timeout": True,
        }
    finally:
        try:
            os.unlink(tmpfile)
        except OSError:
            pass

# ── Pre-defined smoke tests ─────────────────────────────────────
SMOKE_TESTS = [
    (b"2+3", "basic addition"),
    (b"x" + KAPL["assign"] + b"42; x", "assign and read"),
    (KAPL["print"] + b'"hello fuzz"', "print string"),
    (b"4 2 " + KAPL["rho"] + b" 1 2 3 4 5 6 7 8", "matrix reshape"),
    (b"x" + KAPL["assign"] + b"100; if (x>50) { y" + KAPL["assign"] + b"1 }", "if statement"),
    (b"a" + KAPL["assign"] + b"1" + KAPL["multiply"] + b"2", "scalar multiply"),
    (b"b" + KAPL["assign"] + b"10" + KAPL["divide"] + b"3", "scalar divide"),
    (b"m" + KAPL["assign"] + b"2 2 " + KAPL["rho"] + b" 1 2 3 4", "2x2 matrix"),
    (b"n" + KAPL["assign"] + b"5; n" + KAPL["assign"] + b"n+3", "reassignment"),
    (b"v" + KAPL["assign"] + b"2 3 " + KAPL["iota"] + b"6", "iota generate"),
]

def run_smoke_tests(interpreter_path):
    """Run predefined smoke tests to verify interpreter works."""
    print("=== Smoke tests ===")
    passed = 0
    failed = 0
    for code, name in SMOKE_TESTS:
        # Wrap in a complete program
        full_prog = (
            KAPL["comment"] + b" smoke: " + name.encode() + b"\n"
            + code + b"\n"
            + KAPL["print"] + b'"smoke done"'
        )
        res = run_aplus(interpreter_path, full_prog, timeout=5)
        ok = res["exit_code"] == 0 and b"TIMEOUT" not in res.get("stderr", b"")
        if ok:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name} (exit={res['exit_code']})")
    print(f"Smoke: {passed}/{passed+failed} passed\n")
    return failed == 0

def main():
    import argparse
    parser = argparse.ArgumentParser(description="A+ grammar fuzzer")
    parser.add_argument("interpreter", help="Path to A+ interpreter binary")
    parser.add_argument("--seed", type=int, help="Random seed")
    parser.add_argument("-n", "--count", type=int, default=20,
                        help="Number of fuzz iterations (default: 20)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: smoke tests only")
    parser.add_argument("--timeout", type=int, default=5,
                        help="Timeout per test in seconds (default: 5)")
    parser.add_argument("--stats", action="store_true",
                        help="Show statistics only")
    parser.add_argument("--report", type=str,
                        help="Write fuzz report to file")
    args = parser.parse_args()

    interp = args.interpreter
    if not os.path.isfile(interp):
        print(f"ERROR: interpreter not found: {interp}")
        sys.exit(1)

    if args.seed:
        random.seed(args.seed)
        print(f"Seed: {args.seed}")

    # Smoke tests first
    smoke_ok = run_smoke_tests(interp)

    if args.quick:
        if smoke_ok:
            print("All smoke tests passed.")
        sys.exit(0 if smoke_ok else 1)

    # ── Fuzz testing ──────────────────────────────────────────
    print(f"=== Fuzzing: {args.count} iterations, timeout={args.timeout}s ===")
    crashes = []
    timeouts = []
    failures = []
    ok_count = 0

    for i in range(args.count):
        prog = generate_program()
        res = run_aplus(interp, prog, timeout=args.timeout)

        if res.get("timeout"):
            timeouts.append(res)
            status = "TIMEOUT"
        elif res["exit_code"] < 0:
            crashes.append(res)
            status = f"CRASH (signal {-res['exit_code']})"
        elif res["exit_code"] != 0:
            failures.append(res)
            status = f"FAIL (exit={res['exit_code']})"
        else:
            ok_count += 1
            status = "OK"

        print(f"  [{i+1:3d}/{args.count}] {status}  {res['elapsed']:.2f}s")

    # ── Summary ────────────────────────────────────────────────
    print()
    print("=" * 50)
    print(f"  Total:    {args.count}")
    print(f"  OK:       {ok_count}")
    print(f"  Failures: {len(failures)}")
    print(f"  Crashes:  {len(crashes)}")
    print(f"  Timeouts: {len(timeouts)}")
    print("=" * 50)

    if crashes:
        print("\n!!! CRASHES DETECTED !!!")
        for i, c in enumerate(crashes):
            print(f"\nCrash #{i+1}: exit={c['exit_code']}")
            print("  stderr:", c["stderr"][:200].decode(errors="replace"))

    if timeouts:
        print(f"\n{len(timeouts)} timeout(s) detected (may be infinite loops)")

    # Write report if requested
    if args.report:
        with open(args.report, "w") as f:
            f.write(f"A+ Fuzzer Report\n")
            f.write(f"Seed: {args.seed if args.seed else 'random'}\n")
            f.write(f"Iterations: {args.count}\n")
            f.write(f"OK: {ok_count}, Fail: {len(failures)}, ")
            f.write(f"Crash: {len(crashes)}, Timeout: {len(timeouts)}\n")

    # Exit with error if crashes found
    sys.exit(1 if crashes else 0)


if __name__ == "__main__":
    main()
