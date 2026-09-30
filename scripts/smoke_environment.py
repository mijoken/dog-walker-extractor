from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import ultralytics
import imageio_ffmpeg


def main() -> int:
    print("===== PYTHON =====")
    print(sys.version)
    print(sys.executable)

    print("\n===== TORCH =====")
    print("torch:", torch.__version__)
    print("cuda_available:", torch.cuda.is_available())
    print("device:", "cuda" if torch.cuda.is_available() else "cpu")

    print("\n===== ULTRALYTICS =====")
    print("ultralytics:", ultralytics.__version__)

    print("\n===== OPENCV =====")
    print("opencv:", cv2.__version__)

    print("\n===== NUMPY =====")
    print("numpy:", np.__version__)

    print("\n===== FFMPEG (PYTHON-BUNDLED) =====")
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    print(ffmpeg_path)

    if not Path(ffmpeg_path).exists():
        raise RuntimeError("imageio-ffmpeg executable was not found")

    print("\n===== RESULT =====")
    print("STAGE1_ENVIRONMENT_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
