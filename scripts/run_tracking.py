from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dogwalker.tracking.engine import run_tracking


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect and track people and dogs in arbitrary video."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Input video path",
    )

    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "output" / "stage2"),
        help="Output directory",
    )

    parser.add_argument(
        "--model",
        default="yolo11n.pt",
        help="Ultralytics YOLO model",
    )

    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="YOLO inference image size",
    )

    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Detection confidence threshold",
    )

    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Only process the first N seconds",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    run_tracking(
        input_video=args.input,
        output_dir=args.output,
        model_name=args.model,
        image_size=args.imgsz,
        confidence=args.conf,
        max_seconds=args.max_seconds,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
