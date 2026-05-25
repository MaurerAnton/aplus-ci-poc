#!/usr/bin/env python3
"""
Enhanced fuzzer for the A+ programming language interpreter.

Supports:
  - Grammar-based generation (existing)
  - Dictionary-based generation (--dict): guided by A+/APL primitive dictionary
  - Mutation-based fuzzing (--mutate N): mutate existing .a+ files
  - Crash minimization (--minimize): delta-debug a crashing program to minimal form
  - Smoke tests, reporting, stats (existing)

Usage:
    python3 fuzz_aplus.py /path/to/a+ [--seed SEED] [--count N]
    python3 fuzz_aplus.py /path/to/a+ --quick
    python3 fuzz_aplus.py /path/to/a+ --dict --count 100
    python3 fuzz_aplus.py /path/to/a+ --mutate ./corpus --count 200
    python3 fuzz_aplus.py /path/to/a+ --minimize crash.a+

This has never been done for A+ before.
"""

import random
import subprocess
import sys
import time
import os
import tempfile
import argparse
from pathlib import Path

# ── KAPL encoding ──────────────────────────────────────────────
# A+ uses KAPL font encoding (not UTF-8) for APL glyphs in .a+ files
KAPL = {
    "assign":    b"\xfb",   # ←
    "print":     b"\xd5",   # ⎕
    "comment":   b"\xe3",   # ⍝
    "rho":       b"\xce",   # ⍴
    "divide":    b"\xdf",   # ÷
    "multiply":  b"\xc1",   # ×
    "iota":      b"\xa2",   # ⍳
    "max":       b"\xab",   # ⌈
    "member":    b"\xa8",   # ∊
    # Additional APL operators (KAPL encoding)
    "each":      b"\xac",   # ¨
    "transpose": b"\xcd",   # ⍉
    "grade_up":  b"\xb9",   # ⍋
    "grade_down":b"\xba",   # ⍒
    "format":    b"\xcf",   # ⍕
    "execute":   b"\xcc",   # ⍎
    "reverse":   b"\xf2",   # ⌽
    "floor":     b"\xac",   # ⌊ (same byte as each in some KAPL variants)
    "not":       b"\x7e",   # ~
    "roll":      b"\x3f",   # ?
    "log":       b"\xe7",   # ⍟
    "circle":    b"\xcb",   # ○
    "power":     b"\xc3",   # ⋆
    "drop":      b"\xd3",   # ↓
    "take":      b"\xd4",   # ↑
}

# ── Dictionary of A+/APL primitives ────────────────────────────
# Organised by usage: monadic (one argument), dyadic (two arguments), control flow
APL_DICT = {
    "monadic": {
        # name -> KAPL byte
        "rho":        KAPL["rho"],
        "iota":       KAPL["iota"],
        "each":       KAPL["each"],
        "reverse":    KAPL["reverse"],
        "transpose":  KAPL["transpose"],
        "grade_up":   KAPL["grade_up"],
        "grade_down": KAPL["grade_down"],
        "format":     KAPL["format"],
        "execute":    KAPL["execute"],
        "max":        KAPL["max"],
        "member":     KAPL["member"],
        "not":        KAPL["not"],
        "roll":       KAPL["roll"],
        "floor":      KAPL.get("floor", KAPL["each"]),
    },
    "dyadic": {
        "+":          b"+",
        "-":          b"-",
        "*":          b"*",
        "divide":     KAPL["divide"],
        "multiply":   KAPL["multiply"],
        "max":        KAPL["max"],
        "member":     KAPL["member"],
        "rho":        KAPL["rho"],
        "power":      KAPL["power"],
        "drop":       KAPL["drop"],
        "take":       KAPL["take"],
        "log":        KAPL["log"],
        "circle":     KAPL["circle"],
    },
    "control": {
        "assign":     KAPL["assign"],
        "print":      KAPL["print"],
        "comment":    KAPL["comment"],
    },
}

# Flattened list of all KAPL operator bytes (for mutation, insertion, deletion)
ALL_KAPL_BYTES = []
for _cat in APL_DICT.values():
    for _b in _cat.values():
        if _b not in ALL_KAPL_BYTES:
            ALL_KAPL_BYTES.append(_b)

# ── Grammar-based generation (existing) ───────────────────────

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
    if isinstance(op_byte, bytes):
        return f"{left}".encode() + op_byte + f"{right}".encode()
    else:
        return f"{left}{op_byte}{right}".encode()

def expr(depth=0):
    """General expression."""
    if depth > 5:
        atom = expr_atom(depth)
        return atom.encode() if isinstance(atom, str) else atom
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

# ── Dictionary-based generation (new) ─────────────────────────

def dict_lit():
    """Generate a literal, sometimes using vector/matrix literals."""
    kind = random.random()
    if kind < 0.4:
        return str(random.randint(0, 9999)).encode()
    elif kind < 0.7:
        return f"{random.uniform(0.0, 100.0):.4f}".encode()
    elif kind < 0.9:
        # Vector literal: "1 2 3"
        n = random.randint(2, 5)
        return " ".join(str(random.randint(0, 99)) for _ in range(n)).encode()
    else:
        # Matrix literal: "2 2 rho 1 2 3 4"
        rows = random.randint(2, 4)
        cols = random.randint(2, 4)
        elems = " ".join(str(random.randint(0, 99)) for _ in range(rows * cols))
        return f"{rows} {cols} ".encode() + KAPL["rho"] + b" " + elems.encode()

def dict_var():
    """Generate a variable name (weighted toward common names)."""
    return random.choice(["a", "b", "c", "x", "y", "z", "tmp", "v", "m",
                          "r", "result", "data", "n", "i", "j"]).encode()

def dict_monadic_expr(depth=0):
    """Generate a monadic expression: OP expr  (e.g., rho data, iota 10)"""
    if depth > 4:
        return dict_lit()
    op_name = random.choice(list(APL_DICT["monadic"].keys()))
    op_byte = APL_DICT["monadic"][op_name]
    operand = dict_atom(depth + 1)
    return op_byte + operand

def dict_dyadic_expr(depth=0):
    """Generate a dyadic expression: left OP right"""
    if depth > 4:
        return dict_lit()
    op_name = random.choice(list(APL_DICT["dyadic"].keys()))
    op_byte = APL_DICT["dyadic"][op_name]
    left = dict_atom(depth + 1)
    right = dict_atom(depth + 1)
    return left + op_byte + right

def dict_atom(depth=0):
    """Dictionary-guided atom: literal, variable, or simple expression."""
    if depth > 5:
        return dict_lit()
    r = random.random()
    if r < 0.25:
        return dict_lit()
    elif r < 0.50:
        return dict_var()
    elif r < 0.75:
        return dict_monadic_expr(depth)
    else:
        return dict_dyadic_expr(depth)

def dict_statement_assign():
    """x←expr using dictionary-guided generation."""
    var = dict_var()
    e = dict_atom()
    return var + KAPL["assign"] + e

def dict_statement_print():
    """Print with dictionary style."""
    msg = random.choice([
        "hello", "test", "ok", "value:", "result",
        "pass", "running", "check", "done", "A+ fuzz",
        "dict", "primitives", "grade", "shape"
    ])
    return KAPL["print"] + b'"' + msg.encode() + b'"'

def dict_statement_if():
    """if-statement with dictionary atoms."""
    cond = dict_atom()
    body = dict_statement_assign()
    return b"if (" + cond + b") { " + body + b" }"

def dict_statement(depth=0):
    """Random A+ statement using dictionary-guided primitives."""
    if depth > 8:
        return dict_statement_print()
    kind = random.choice(["assign", "print", "if"])
    if kind == "assign":
        return dict_statement_assign()
    elif kind == "print":
        return dict_statement_print()
    else:
        return dict_statement_if()

def dict_generate_program(num_statements=None):
    """Generate a complete A+ program using dictionary-guided generation."""
    if num_statements is None:
        num_statements = random.randint(3, 20)

    lines = [KAPL["comment"] + b" dict-fuzz-generated A+ program"]
    for _ in range(num_statements):
        stmt = dict_statement()
        lines.append(stmt + b";")
    lines.append(KAPL["print"] + b'"dict fuzz done"')

    return b"\n".join(lines)

# ── Mutation-based fuzzing (new) ──────────────────────────────

def find_aplus_files(directory):
    """Find all .a+ (and .a, .apl) files recursively."""
    files = []
    target = Path(directory)
    if not target.exists():
        print(f"WARNING: directory not found: {directory}")
        return files
    for ext in ["*.a+", "*.a", "*.apl"]:
        files.extend(target.rglob(ext))
    # Deduplicate and sort
    files = sorted(set(files), key=lambda p: str(p))
    return files

def read_program_file(filepath):
    """Read a program file as bytes."""
    with open(filepath, "rb") as f:
        return f.read()

def _find_kapL_positions(prog_bytes):
    """Find all positions of known KAPL operator bytes in the program."""
    positions = []
    for i, b in enumerate(prog_bytes):
        if bytes([b]) in ALL_KAPL_BYTES:
            positions.append(i)
    return positions

def _find_digit_positions(prog_bytes):
    """Find all positions of digit characters (for literal replacement)."""
    positions = []
    for i, b in enumerate(prog_bytes):
        if 0x30 <= b <= 0x39:  # '0'-'9'
            positions.append(i)
    return positions

def _find_semicolons(prog_bytes):
    """Find all semicolon positions (statement boundaries)."""
    return [i for i, b in enumerate(prog_bytes) if b == 0x3b]  # ';'

def mutate_swap_bytes(prog_bytes):
    """Swap two random bytes in the program."""
    if len(prog_bytes) < 2:
        return prog_bytes
    result = bytearray(prog_bytes)
    i = random.randrange(len(result))
    j = random.randrange(len(result))
    result[i], result[j] = result[j], result[i]
    return bytes(result)

def mutate_insert_operator(prog_bytes):
    """Insert a random KAPL operator byte at a random position."""
    if not ALL_KAPL_BYTES:
        return prog_bytes
    result = bytearray(prog_bytes)
    pos = random.randint(0, len(result))
    op = random.choice(ALL_KAPL_BYTES)
    result[pos:pos] = op
    return bytes(result)

def mutate_delete_operator(prog_bytes):
    """Delete a random KAPL operator byte from the program."""
    positions = _find_kapL_positions(prog_bytes)
    if not positions:
        return prog_bytes
    pos = random.choice(positions)
    result = bytearray(prog_bytes)
    del result[pos]
    return bytes(result)

def mutate_replace_literal(prog_bytes):
    """Replace a digit with another random digit."""
    positions = _find_digit_positions(prog_bytes)
    if not positions:
        return prog_bytes
    pos = random.choice(positions)
    result = bytearray(prog_bytes)
    result[pos] = random.randint(0x30, 0x39)  # random digit
    return bytes(result)

def mutate_duplicate_statement(prog_bytes):
    """Duplicate a random statement (semicolon-delimited chunk)."""
    semis = _find_semicolons(prog_bytes)
    if len(semis) < 2:
        return prog_bytes
    # Pick a random semicolon index
    semi_idx = random.randrange(len(semis))
    semi_pos = semis[semi_idx]
    # Find start of this statement (after previous semicolon or start)
    if semi_idx == 0:
        stmt_start = 0
    else:
        stmt_start = semis[semi_idx - 1] + 1
    stmt_end = semi_pos + 1  # include the semicolon
    stmt = prog_bytes[stmt_start:stmt_end]
    # Insert after the semicolon
    result = bytearray(prog_bytes)
    result[semi_pos + 1:semi_pos + 1] = stmt
    return bytes(result)

def mutate_insert_noise(prog_bytes):
    """Insert random ASCII/KAPL byte noise at a random position."""
    result = bytearray(prog_bytes)
    pos = random.randint(0, len(result))
    # Mix of KAPL operators and random bytes
    if random.random() < 0.5 and ALL_KAPL_BYTES:
        noise = random.choice(ALL_KAPL_BYTES)
    else:
        noise = bytes([random.randint(0x01, 0xfe)])
    result[pos:pos] = noise
    return bytes(result)

# Registry of mutation functions with weights
MUTATION_OPS = [
    (mutate_swap_bytes,          3, "swap_bytes"),
    (mutate_insert_operator,     4, "insert_operator"),
    (mutate_delete_operator,     3, "delete_operator"),
    (mutate_replace_literal,     2, "replace_literal"),
    (mutate_duplicate_statement, 2, "duplicate_statement"),
    (mutate_insert_noise,        2, "insert_noise"),
]

def mutate_program(prog_bytes, num_mutations=None):
    """Apply random mutations to a program.
    
    Args:
        prog_bytes: Original program as bytes.
        num_mutations: Number of mutations to apply (default: random 1-5).
    
    Returns:
        (mutated_bytes, [list of applied mutation names])
    """
    if num_mutations is None:
        num_mutations = random.randint(1, min(5, max(1, len(prog_bytes) // 4)))
    
    result = prog_bytes
    applied = []
    for _ in range(num_mutations):
        # Weighted random selection
        total_weight = sum(w for _, w, _ in MUTATION_OPS)
        r = random.randint(1, total_weight)
        cumulative = 0
        chosen = MUTATION_OPS[0]
        for op, weight, name in MUTATION_OPS:
            cumulative += weight
            if r <= cumulative:
                chosen = (op, weight, name)
                break
        op_fn, _, op_name = chosen
        result = op_fn(result)
        applied.append(op_name)
    
    return result, applied

def mutate_fuzz_loop(interpreter_path, corpus_dir, count, timeout):
    """Fuzz by mutating existing .a+ files from a corpus directory."""
    files = find_aplus_files(corpus_dir)
    if not files:
        print(f"ERROR: No .a+ files found in '{corpus_dir}'")
        print("  Provide a corpus directory with .a+ files, or use --dict/grammar mode.")
        sys.exit(1)
    
    print(f"Corpus: {len(files)} file(s) from {corpus_dir}")
    
    crashes = []
    timeouts = []
    failures = []
    ok_count = 0
    
    for i in range(count):
        # Pick a random corpus file
        src_file = random.choice(files)
        try:
            original = read_program_file(src_file)
        except OSError as e:
            print(f"  [{i+1:3d}/{count}] SKIP: cannot read {src_file.name}: {e}")
            continue
        
        if len(original) < 4:
            # Too small to meaningfully mutate
            continue
        
        # Mutate
        mutated, applied_ops = mutate_program(original)
        res = run_aplus(interpreter_path, mutated, timeout=timeout)
        
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
        
        ops_str = "+".join(applied_ops)
        print(f"  [{i+1:3d}/{count}] {status}  {res['elapsed']:.2f}s  "
              f"src={src_file.name}  mut=[{ops_str}]")
    
    return crashes, timeouts, failures, ok_count

# ── Crash minimization / delta debugging (new) ────────────────

def test_program(interpreter_path, program_bytes, timeout=5):
    """Test if a program triggers a crash (exit_code < 0 or timeout).
    
    Returns True if the program crashes/times out, False otherwise.
    """
    res = run_aplus(interpreter_path, program_bytes, timeout=timeout)
    if res.get("timeout"):
        return True, res
    if res["exit_code"] < 0:
        return True, res
    return False, res

def _has_crash(interpreter_path, program_bytes, timeout, expected_signal=None):
    """Check if program still produces the same crash signal.
    
    If expected_signal is None, any crash counts.
    """
    res = run_aplus(interpreter_path, program_bytes, timeout=timeout)
    if res.get("timeout"):
        return expected_signal is None or expected_signal == -1
    if res["exit_code"] < 0:
        if expected_signal is None:
            return True
        return res["exit_code"] == expected_signal
    return False

def ddmin(program_bytes, interpreter_path, timeout, expected_signal=None):
    """Delta debugging minimization (ddmin algorithm).
    
    Zeller's ddmin: repeatedly try to remove chunks,
    keeping any reduced version that still triggers the crash.
    
    Args:
        program_bytes: The crashing program as bytes.
        interpreter_path: Path to A+ interpreter.
        timeout: Timeout per test.
        expected_signal: If set, only count programs that crash with this signal.
    
    Returns:
        Minimized program bytes (hopefully shorter).
    """
    original = program_bytes
    
    def test(p):
        return _has_crash(interpreter_path, p, timeout, expected_signal)
    
    n = 2  # granularity
    iterations = 0
    max_iterations = 100  # safety limit
    
    current = original
    
    while len(current) >= 2 and iterations < max_iterations:
        iterations += 1
        chunk_size = max(1, len(current) // n)
        if chunk_size == 0:
            break
        
        # Try complement: remove each chunk
        progress_made = False
        for i in range(n):
            start = i * chunk_size
            end = min(start + chunk_size, len(current))
            if start >= len(current):
                break
            
            # Complement: everything EXCEPT this chunk
            complement = current[:start] + current[end:]
            
            if len(complement) < 2:
                continue
            
            if test(complement):
                current = complement
                n = max(n - 1, 2)
                progress_made = True
                break
        
        if not progress_made:
            # Try each chunk alone
            for i in range(n):
                start = i * chunk_size
                end = min(start + chunk_size, len(current))
                if start >= len(current):
                    break
                
                chunk = current[start:end]
                if len(chunk) < 2:
                    continue
                
                if test(chunk):
                    current = chunk
                    n = max(n - 1, 2)
                    progress_made = True
                    break
        
        if not progress_made:
            if n * 2 <= len(current):
                n = n * 2
            else:
                break
    
    return current

def minimize_crash(interpreter_path, program_bytes, timeout=5, 
                    expected_signal=None, verbose=True):
    """Minimize a crashing program using delta debugging.
    
    Args:
        interpreter_path: Path to A+ interpreter.
        program_bytes: The crashing program.
        timeout: Timeout per test.
        expected_signal: If set, ensure minimized program crashes with same signal.
        verbose: Print progress.
    
    Returns:
        (minimized_bytes, original_len, minimized_len, reduction_pct)
    """
    import math
    
    original_len = len(program_bytes)
    
    if verbose:
        print(f"\n=== Delta Debugging Minimization ===")
        print(f"  Original size: {original_len} bytes")
    
    # Phase 1: Remove trailing bytes one at a time (fast path)
    current = program_bytes
    while len(current) > 1:
        candidate = current[:-1]
        crashing, _ = test_program(interpreter_path, candidate, timeout)
        # For signal-specific, check exact signal
        if expected_signal is not None:
            res = run_aplus(interpreter_path, candidate, timeout=timeout)
            crashing = (res.get("timeout") and expected_signal == -1) or \
                       (res["exit_code"] < 0 and res["exit_code"] == expected_signal)
        if crashing:
            current = candidate
        else:
            break
    
    if verbose and len(current) < original_len:
        print(f"  After trailing trim: {len(current)} bytes "
              f"({(1 - len(current)/original_len)*100:.0f}% reduction)")
    
    # Phase 2: Remove leading bytes one at a time
    while len(current) > 1:
        candidate = current[1:]
        crashing, _ = test_program(interpreter_path, candidate, timeout)
        if expected_signal is not None:
            res = run_aplus(interpreter_path, candidate, timeout=timeout)
            crashing = (res.get("timeout") and expected_signal == -1) or \
                       (res["exit_code"] < 0 and res["exit_code"] == expected_signal)
        if crashing:
            current = candidate
        else:
            break
    
    if verbose and len(current) < original_len:
        print(f"  After leading trim: {len(current)} bytes "
              f"({(1 - len(current)/original_len)*100:.0f}% reduction)")
    
    # Phase 3: ddmin proper
    if len(current) >= 4:
        minimized = ddmin(current, interpreter_path, timeout, expected_signal)
        current = minimized
    
    minimized_len = len(current)
    reduction_pct = (1 - minimized_len / original_len) * 100 if original_len > 0 else 0
    
    if verbose:
        print(f"  Minimized size:  {minimized_len} bytes "
              f"({reduction_pct:.1f}% reduction)")
    
    return current, original_len, minimized_len, reduction_pct

def minimize_mode(interpreter_path, program_path, timeout=5):
    """Run minimization on a program file. Writes minimized version to disk.
    
    Args:
        interpreter_path: Path to A+ interpreter.
        program_path: Path to the crashing .a+ program.
        timeout: Timeout per test.
    """
    if not os.path.isfile(program_path):
        print(f"ERROR: program file not found: {program_path}")
        sys.exit(1)
    
    with open(program_path, "rb") as f:
        program_bytes = f.read()
    
    # First, verify it actually crashes
    crashing, crash_res = test_program(interpreter_path, program_bytes, timeout)
    if not crashing:
        print(f"ERROR: program does not crash! exit_code={crash_res['exit_code']}")
        print(f"  stdout: {crash_res['stdout'][:200].decode(errors='replace')}")
        sys.exit(1)
    
    expected_signal = crash_res["exit_code"] if crash_res["exit_code"] < 0 else None
    if crash_res.get("timeout"):
        expected_signal = -1
    
    print(f"Program crashes: exit={crash_res['exit_code']}")
    if crash_res.get("timeout"):
        print("  (timeout detected)")
    
    minimized, orig_len, min_len, pct = minimize_crash(
        interpreter_path, program_bytes, timeout, expected_signal, verbose=True
    )
    
    # Write minimized version
    out_path = program_path.replace(".a+", ".min.a+")
    if out_path == program_path:
        out_path = program_path + ".min"
    with open(out_path, "wb") as f:
        f.write(minimized)
    
    print(f"\nMinimized program written to: {out_path}")
    print(f"  {orig_len} -> {min_len} bytes ({pct:.1f}% reduction)")
    
    # Show the minimized program (hex dump)
    print(f"\nMinimized program hex:")
    hex_str = " ".join(f"{b:02x}" for b in minimized[:64])
    print(f"  {hex_str}")
    if len(minimized) > 64:
        print(f"  ... ({len(minimized) - 64} more bytes)")
    
    # Try to show as text
    try:
        text = minimized.decode("ascii", errors="replace")
        print(f"\nAs text: {text[:200]}")
    except Exception:
        pass
    
    return minimized


# ── Interpreter runner ────────────────────────────────────────

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


# ── Pre-defined smoke tests ───────────────────────────────────

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


# ── Main ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enhanced A+ fuzzer — grammar, dictionary, mutation, minimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 fuzz_aplus.py ./a+ --quick                  # Smoke tests only
  python3 fuzz_aplus.py ./a+ --seed 42 -n 100         # Grammar fuzzing
  python3 fuzz_aplus.py ./a+ --dict --count 200       # Dictionary-based fuzzing
  python3 fuzz_aplus.py ./a+ --mutate ./corpus -n 200 # Mutation fuzzing
  python3 fuzz_aplus.py ./a+ --mutate ./corpus --dict -n 500  # Combined
  python3 fuzz_aplus.py ./a+ --minimize crash.a+      # Minimize a crash
        """
    )
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

    # New modes
    parser.add_argument("--dict", action="store_true",
                        help="Use dictionary-guided generation mode")
    parser.add_argument("--mutate", type=str, metavar="CORPUS_DIR",
                        help="Mutation mode: mutate .a+ files from CORPUS_DIR")
    parser.add_argument("--minimize", type=str, metavar="CRASH_FILE",
                        help="Minimize a crashing .a+ program")

    args = parser.parse_args()

    interp = args.interpreter
    if not os.path.isfile(interp):
        print(f"ERROR: interpreter not found: {interp}")
        sys.exit(1)

    if args.seed:
        random.seed(args.seed)
        print(f"Seed: {args.seed}")

    # ── Minimize mode (standalone) ──────────────────────────
    if args.minimize:
        # Smoke tests optional in minimize mode
        run_smoke_tests(interp)
        minimize_mode(interp, args.minimize, timeout=args.timeout)
        sys.exit(0)

    # ── Smoke tests (always run first) ──────────────────────
    smoke_ok = run_smoke_tests(interp)

    if args.quick:
        if smoke_ok:
            print("All smoke tests passed.")
        sys.exit(0 if smoke_ok else 1)

    # ── Determine fuzzing mode ──────────────────────────────
    mode = "grammar"
    if args.dict and args.mutate:
        mode = "dict+mutation"
    elif args.dict:
        mode = "dictionary"
    elif args.mutate:
        mode = "mutation"

    print(f"=== Fuzzing: {args.count} iterations, mode={mode}, timeout={args.timeout}s ===")

    crashes = []
    timeouts = []
    failures = []
    ok_count = 0

    if mode == "mutation" or mode == "dict+mutation":
        # Mutation mode
        corpus_dir = args.mutate
        crashes, timeouts, failures, ok_count = mutate_fuzz_loop(
            interp, corpus_dir, args.count, args.timeout
        )
        if mode == "dict+mutation":
            # Also mix in some dictionary-generated programs
            print(f"\n=== Mixed dict generation (additional {args.count//4} iterations) ===")
            extra = args.count // 4
            for i in range(extra):
                prog = dict_generate_program()
                res = run_aplus(interp, prog, timeout=args.timeout)
                if res.get("timeout"):
                    timeouts.append(res)
                elif res["exit_code"] < 0:
                    crashes.append(res)
                elif res["exit_code"] != 0:
                    failures.append(res)
                else:
                    ok_count += 1
    elif mode == "dictionary":
        # Dictionary-based fuzzing loop
        for i in range(args.count):
            prog = dict_generate_program()
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
    else:
        # Grammar-based fuzzing loop (original)
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

    # ── Summary ──────────────────────────────────────────────
    total = args.count + (args.count // 4 if mode == "dict+mutation" else 0)
    print()
    print("=" * 50)
    print(f"  Mode:     {mode}")
    print(f"  Total:    {total}")
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
            f.write(f"Mode: {mode}\n")
            f.write(f"Seed: {args.seed if args.seed else 'random'}\n")
            f.write(f"Iterations: {args.count}\n")
            f.write(f"OK: {ok_count}, Fail: {len(failures)}, ")
            f.write(f"Crash: {len(crashes)}, Timeout: {len(timeouts)}\n")
            if crashes:
                f.write(f"\nCrashes:\n")
                for i, c in enumerate(crashes):
                    f.write(f"  {i+1}. signal={c['exit_code']} "
                            f"stderr={c['stderr'][:100].decode(errors='replace')}\n")

    # Exit with error if crashes found
    sys.exit(1 if crashes else 0)


if __name__ == "__main__":
    main()
