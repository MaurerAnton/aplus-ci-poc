# A+ Jupyter Kernel

Run A+ code cells directly in Jupyter Notebook or Jupyter Lab.

## Requirements

- Python 3.7+
- `ipykernel` (`pip install ipykernel`)
- `a+` interpreter installed and in PATH

## Installation

```bash
cd jupyter_aplus
bash install.sh
```

The installer will:
1. Install `ipykernel` if missing
2. Install this kernel as a Python package
3. Register the kernel with Jupyter

## Usage

Launch Jupyter:

```bash
jupyter notebook
# or
jupyter lab
```

Create a new notebook and select **A+** from the kernel picker.

Each cell's code is written to a temporary `.a+` file and executed via the `a+` interpreter. Output (stdout/stderr) is captured and displayed inline.

## Example

```apl
⍝ Hello world in A+
⎕"Hello, Jupyter!"
x←2+3*2
⎕x
```

## License

MIT
