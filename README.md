# A+ CI — Proof of Concept

Demonstrates building and running the [A+ programming language](http://www.aplusdev.org/) (APL descendant by Arthur Whitney, Morgan Stanley, 1988) in GitHub Actions CI.

## What's here

### Programs (KAPL-encoded `.a+` files)

| File | Description |
|------|-------------|
| `hello.a+` | Basic arithmetic, exponentiation, array summation, conditionals |
| `convert.a+` | Temperature conversion (Celsius to Fahrenheit) with verification |
| `test.a+` | **Unit testing framework for A+** (first ever) — `ok{}`, `fail{}`, `check{cond}`, `summary{}` |
| `nn.a+` | **2-Layer Neural Network in pure A+** — sigmoid activation, matrix inner product, XOR forward pass (first ever) |
| `nn_backprop.a+` | **Backpropagation training in pure A+** — gradient descent, MSE loss, sigmoid derivative, 5000-epoch training loop on XOR (first ever) |
| `quicksort.a+` | **Quicksort** — recursive partitioning on arrays |
| `sieve.a+` | **Sieve of Eratosthenes** — prime generation up to N |
| `binary_search.a+` | **Binary search** — iterative O(log n) search on sorted arrays |
| `matrix.a+` | **Matrix operations** — LU decomposition (Doolittle), power iteration for dominant eigenvalue |
| `graph.a+` | **Graph algorithms** — BFS and DFS on adjacency matrix |

### Machine Learning in A+

| File | Description |
|------|-------------|
| `transformer.a+` | **Single-head scaled dot-product attention** — Q/K/V matrices, softmax, 4 samples, 2-dim embeddings (first ever) |
| `kmeans.a+` | **K-means clustering** — 2D points, assignment/update steps, 10 iterations |
| `linear_regression.a+` | **Linear regression with gradient descent** — synthetic data y=2x+1, MSE loss, 500 epochs |
| `decision_tree.a+` | **Decision tree (stump)** — gini impurity, 2D binary classification |
| `autodiff.a+` | **Reverse-mode automatic differentiation** — Value graph, add/mul/relu, backward gradient propagation (first ever) |

### Standard Library

| File | Description |
|------|-------------|
| `math.a+` | **Math functions** — sqrt (Newton), exp/log (Taylor series), sin/cos (Taylor), pow |
| `stats.a+` | **Statistics** — mean, variance, stddev, correlation, histogram |
| `strings.a+` | **String manipulation** — split, join, substr, strlen, concat |
| `sorting.a+` | **Advanced sorting** — mergesort, heapsort, countingsort |

### Competitive Programming

| File | Description |
|------|-------------|
| `project_euler.a+` | **Project Euler #1-5** — sum of multiples, even Fibonacci, largest prime factor, palindrome product, smallest multiple (first-ever Euler solutions in A+) |

### Tools

| File | Description |
|------|-------------|
| `fuzz_aplus.py` | **Enhanced grammar-based fuzzer** — 1017 lines: grammar, dictionary-based, mutation-based modes + crash minimization via delta debugging (first ever) |
| `transpile_aplus.py` | **A+ transpiler** — 1800+ lines: KAPL decoder, recursive-descent parser, 5 targets (Python, JavaScript, Go, Rust, C), constant folding, source maps (first ever) |
| `aplus_pm.py` | **Package manager** — install/list/init/update/remove for A+ libraries, `$load` directive resolution |
| `Dockerfile` | Multi-stage Docker build producing a runnable A+ container |
| `Dockerfile.wasm` | **WebAssembly build** — Emscripten-based, produces `aplus.js` + `aplus.wasm` (first ever) |
| `index.html` | **Browser REPL** — interactive A+ programming environment running on WASM |
| `build_wasm.sh` | Build script for WASM artifacts (Docker build + extract + serve) |
| `Makefile.wasm` | Convenience Makefile wrapping `build_wasm.sh` |

### Ecosystem

| Directory | Description |
|-----------|-------------|
| `vscode-aplus/` | **VSCode extension** — TextMate grammar (40+ built-ins, KAPL glyphs, operators), Run/Transpile commands, TypeScript source |
| `jupyter_aplus/` | **Jupyter kernel** — ipykernel-based, subprocess execution, install script |

## CI Pipeline

```
push ->  build-interpreter  ->  run-programs (all .a+ files)
       (g++, autotools)    ->  neural-network (forward + backprop)
                           ->  benchmarks (quicksort, sieve, binary search, matrix, graph)
                           ->  fuzz (grammar + dictionary modes)
                           
       transpiler          ->  A+ -> Python/JS, run generated code
       
       wasm                ->  Emscripten Docker build, extract aplus.js/aplus.wasm
       
       build-arm64         ->  Native ARM64 build (ubuntu-24.04-arm runner)
       
       coverage            ->  gcov/lcov code coverage report
       
       compare             ->  Benchmark vs J, K, BQN (sum, matmul, sieve)
```

### Features demonstrated

- **Building** a 2008-era C/C++ interpreter from source on modern Linux
- **Unit testing** — custom test framework written in A+ itself
- **Neural network with backprop** — forward pass + gradient descent training on XOR
- **Transformer attention** — Q/K/V, scaled dot-product, softmax in pure A+
- **AutoDiff** — reverse-mode automatic differentiation with computation graph
- **Machine learning** — k-means, linear regression, decision tree
- **Classic algorithms** — quicksort, sieve, binary search, LU decomposition, power iteration, BFS, DFS
- **Advanced sorting** — mergesort, heapsort, countingsort
- **Math library** — sqrt, exp, log, sin, cos via Taylor series / Newton's method
- **Statistics** — mean, stddev, correlation, histogram
- **Project Euler** — first 5 problems solved in A+
- **Fuzz testing** — grammar, dictionary, and mutation-based random program generation with crash minimization
- **Transpilation** — A+ to Python, JavaScript, Go, Rust, and C with full recursive-descent parser + constant folding
- **WebAssembly** — browser-based interactive REPL via Emscripten
- **VSCode extension** — syntax highlighting, run, transpile commands
- **Jupyter kernel** — interactive notebook support
- **Package manager** — dependency management via git + `$load` resolution
- **Multi-platform** — x86_64 and ARM64 native builds
- **Code coverage** — gcov/lcov instrumentation
- **Cross-language benchmarks** — performance comparison with J and BQN
- **Docker** — reproducible build environments (native + WASM)
- **CI matrix** — parallel jobs for build, test, NN, benchmarks, fuzz, transpiler, WASM, coverage, comparison

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
| `⌈`       | `0xab`    | Ceiling (max) |
| `∊`       | `0xa8`    | Member |
| `⌊`       | `0xac`    | Floor |

## License

- A+ interpreter — GNU GPL v2.0 (Morgan Stanley, `louyx/aplus`)
- This PoC — MIT
