# A+ CI Proof of Concept

Demonstrates building and running the [A+ programming language](http://www.aplusdev.org/) (APL descendant by Arthur Whitney, Morgan Stanley) in GitHub Actions CI.

## What's here

- `hello.a+` — simple A+ program testing arithmetic, exponentiation, and array reduction
- `.github/workflows/aplus-ci.yml` — CI pipeline that:
  1. Builds the A+ interpreter from [louyx/aplus](https://github.com/louyx/aplus)
  2. Runs `hello.a+` against the built interpreter
  3. Validates exit codes and output

## How it works

The CI checks out the original A+ 4.22-1 source (C/C++, autotools), compiles it with GCC, then executes A+ programs using the resulting `a+` binary.

```
./aplus-install/bin/a+ hello.a+
```

## Encoding note

A+ source files use the KAPL encoding (not UTF-8). Key bytes:

| Character | Symbol | Byte  |
|-----------|--------|-------|
| Comment   | `⍝`    | `0xe3`|
| Assign    | `←`    | `0xfb`|
| Print     | `⎕`    | `0xd5`|

## License

A+ interpreter — GNU GPL v2.0. This PoC — MIT.
