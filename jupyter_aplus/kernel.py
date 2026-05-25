#!/usr/bin/env python3
"""
A+ Jupyter Kernel
=================
ipykernel-based kernel for the A+ programming language.
Accepts A+ code cells, writes them to a temporary .a+ file,
runs them via the a+ interpreter, and returns stdout/stderr
as execute_result.

Usage:
    python kernel.py -f {connection_file}
"""

import sys
import os
import tempfile
import subprocess
import shutil
from pathlib import Path

from ipykernel.kernelbase import Kernel


def find_aplus_interpreter() -> str:
    """Locate the a+ interpreter on PATH."""
    aplus = shutil.which("a+")
    if aplus:
        return aplus
    # Common fallback paths
    for candidate in [
        "/opt/aplus/bin/a+",
        "/usr/local/bin/a+",
        "/usr/bin/a+",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "a+"  # try PATH anyway


class APlusKernel(Kernel):
    implementation = "A+"
    implementation_version = "0.1.0"
    language = "aplus"
    language_version = "A+"
    language_info = {
        "name": "aplus",
        "mimetype": "text/plain",
        "file_extension": ".a+",
        "codemirror_mode": "apl",
        "pygments_lexer": "apl",
    }
    banner = "A+ Jupyter Kernel — APL descendant (1988)\n"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._aplus_bin = find_aplus_interpreter()

    def do_execute(
        self, code: str, silent: bool, store_history: bool = True,
        user_expressions=None, allow_stdin: bool = False
    ):
        """Execute A+ code in a subprocess and return output."""
        if not code.strip():
            return {
                "status": "ok",
                "execution_count": self.execution_count,
                "payload": [],
                "user_expressions": {},
            }

        # Write code to a temp .a+ file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".a+", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [self._aplus_bin, tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.getcwd(),
                env={**os.environ, "HOME": os.environ.get("HOME", "/tmp")},
            )

            stdout = result.stdout
            stderr = result.stderr

            if stderr:
                if stdout:
                    stdout += "\n"
                stdout += f"[stderr]\n{stderr}"

            if not silent:
                stream_content = {"name": "stdout", "text": stdout}
                self.send_response(self.iopub_socket, "stream", stream_content)

        except subprocess.TimeoutExpired:
            stdout = "Error: A+ execution timed out (30 seconds)"
            if not silent:
                self.send_response(
                    self.iopub_socket,
                    "stream",
                    {"name": "stderr", "text": stdout},
                )
        except FileNotFoundError:
            stdout = (
                f"Error: a+ interpreter not found at '{self._aplus_bin}'. "
                "Install A+ (https://www.aplusdev.org/) or set PATH."
            )
            if not silent:
                self.send_response(
                    self.iopub_socket,
                    "stream",
                    {"name": "stderr", "text": stdout},
                )
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return {
            "status": "ok",
            "execution_count": self.execution_count,
            "payload": [],
            "user_expressions": {},
        }


if __name__ == "__main__":
    from ipykernel.kernelapp import IPKernelApp
    IPKernelApp.launch_instance(kernel_class=APlusKernel)
