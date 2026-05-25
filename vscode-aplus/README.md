# A+ Language Support for VSCode

Syntax highlighting and tooling for the [A+ programming language](https://www.aplusdev.org/) (APL descendant, 1988).

## Features

- **Syntax highlighting** for `.a+`, `.a`, and `.aplus` files
  - KAPL-encoded files (0xE3 `⍝` comment marker, 0xFB `←` assignment)
  - Plaintext APL symbol files
  - Numbers, strings, comments (`⍝` and `#`)
  - Keywords: `if`, `while`, `else`, `do`, `for`, `goto`
  - Built-in functions: `rho`, `iota`, `divide`, `multiply`, `sigmoid`, `reshape`, `quad`, etc.
  - Operators: `←` assign, `+` `-` `*` `×` `÷`
  - Lambda/function definition blocks
- **A+: Run** — execute current file with the `a+` interpreter (must be in PATH)
- **A+: Transpile** — transpile current file to Python and JavaScript via `transpile_aplus.py`

## Requirements

- VSCode 1.60+
- `a+` interpreter in PATH (for Run command)
- `python3` and `transpile_aplus.py` in workspace root (for Transpile command)

## Installation

```bash
cd vscode-aplus
npm install
npm run compile
```

Then copy or symlink the `vscode-aplus` directory into your VSCode extensions folder:

```bash
cp -r vscode-aplus ~/.vscode/extensions/aplus-language-0.1.0
```

## Usage

Open any `.a+` file. Use the command palette (`Ctrl+Shift+P`):
- `A+: Run current file` — runs `a+` on the current file
- `A+: Transpile current file to Python/JS` — generates `.py` and `.js` outputs

## License

MIT
