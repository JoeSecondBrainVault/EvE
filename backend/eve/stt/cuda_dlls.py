"""Make pip-installed NVIDIA CUDA 12 DLLs (cuBLAS, cuDNN) loadable by ctranslate2 on Windows.

``nvidia-cublas-cu12`` / ``nvidia-cudnn-cu12`` put their DLLs under
``site-packages/nvidia/<lib>/bin``, which is not on the DLL search path. ctranslate2 loads
them lazily with ``LoadLibrary``, which honours ``PATH``, so both PATH and
``os.add_dll_directory`` are updated. Must run before the first CUDA model load.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_registered: list[str] = []


def register_cuda_dlls() -> list[str]:
    if sys.platform != "win32" or _registered:
        return list(_registered)
    spec = importlib.util.find_spec("nvidia")
    if spec is None or not spec.submodule_search_locations:
        return []
    for root in spec.submodule_search_locations:
        for bin_dir in sorted(Path(root).glob("*/bin")):
            if not any(bin_dir.glob("*.dll")):
                continue
            path = str(bin_dir)
            os.add_dll_directory(path)
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
            _registered.append(path)
    return list(_registered)
