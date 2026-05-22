# A+ CI — Proof of Concept

Demonstrates building and running the [A+ programming language](http://www.aplusdev.org/) (APL descendant by Arthur Whitney, Morgan Stanley, 1988) in GitHub Actions CI.

## 🧠 What's here

### Programs (KAPL-encoded `.a+` files)

| File | Description |
|------|-------------|
| `hello.a+` | Basic arithmetic, exponentiation, array summation, conditionals |
| `convert.a+` | Temperature conversion (Celsius → Fahrenheit) with verification |
| `test.a+` | **Unit testing framework for A+** (first ever) — `test.ok{}`, `test.fail{}`, `test.check{cond}`, `test.summary{}` |
| `nn.a+` | **2-Layer Neural Network in pure A+** — sigmoid activation, matrix inner product, XOR forward pass (first ever) |

### Tools

| File | Description |
|------|-------------|
| `fuzz_aplus.py` | **Grammar-based fuzzer** — generates random valid A+ programs in KAPL encoding to find interpreter crashes (first ever) |
| `Dockerfile` | Multi-stage Docker build producing a runnable A+ container |

## 🔬 CI Pipeline

```
push →  build-interpreter  →  run-programs (hello, convert, test, nn)
       (g++, autotools)   →  neural-network (separate job, prominent)
       docker             →  fuzz (smoke test + 100 random programs)
```

### Features demonstrated

- **Building** a 2008-era C/C++ interpreter from source on modern Linux
- **Unit testing** — custom test framework written in A+ itself
- **Neural network** — forward pass with sigmoid, matrix multiplication, XOR problem
- **Fuzz testing** — grammar-based random program generation with crash detection
- **Docker** — reproducible build environment
- **CI matrix** — parallel jobs for build, test, NN, fuzz, and Docker

## Encoding

A+ source files use the KAPL encoding (not UTF-8). Key bytes:

| Character | KAPL Byte | Meaning |
|-----------|-----------|---------|
| `←`       | `0xfb`    | Assignment |
| `⎕`       | `0xd5`    | Print (quad) |
| `⍝`       | `0xe3`    | Comment (lamp) |
| `⍴`       | `0xce`    | Shape (rho) |
| `÷`       | `0xdf`    | Divide |
| `×`       | `0xc1`    | Multiply (inner product `+.×`) |
| `⍳`       | `0xa2`    | Iota (index generator) |

## License

- A+ interpreter — GNU GPL v2.0 (Morgan Stanley, `louyx/aplus`)
- This PoC — MIT
