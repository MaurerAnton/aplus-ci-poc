#!/usr/bin/env bash
# install.sh — Install the A+ Jupyter kernel
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KERNEL_NAME="aplus"
KERNEL_DIR="${HOME}/.local/share/jupyter/kernels/${KERNEL_NAME}"

echo "=== A+ Jupyter Kernel Installer ==="
echo ""

# Check for a+ interpreter
if ! command -v a+ &>/dev/null && [ ! -x /opt/aplus/bin/a+ ]; then
    echo "WARNING: 'a+' interpreter not found in PATH or /opt/aplus/bin/a+."
    echo "         The kernel will not work until A+ is installed."
    echo "         Install from: https://www.aplusdev.org/"
    echo ""
fi

# Check for ipykernel
if ! python3 -c "import ipykernel" 2>/dev/null; then
    echo "Installing ipykernel..."
    pip3 install ipykernel
fi

# Install as a proper Python package (editable, so kernel.json argv works)
echo "Installing jupyter_aplus package..."
pip3 install -e "${SCRIPT_DIR}" --break-system-packages 2>/dev/null || \
    pip3 install -e "${SCRIPT_DIR}" --user 2>/dev/null || \
    pip3 install -e "${SCRIPT_DIR}"

# Create kernel directory and copy kernel.json
mkdir -p "${KERNEL_DIR}"
cp "${SCRIPT_DIR}/kernel.json" "${KERNEL_DIR}/kernel.json"

echo ""
echo "Kernel installed to: ${KERNEL_DIR}"
echo "Kernel name: ${KERNEL_NAME}"
echo ""
echo "To use: jupyter notebook  or  jupyter lab"
echo "Then select 'A+' from the kernel picker."
echo ""
echo "Done!"
