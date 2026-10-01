from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dogwalker.tracking.engine import run_tracking


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", required=True)
    parser.add_argument("--scan-summary", required=True)
    parser.add_argument("--output", required=True)

    parser.add_argument(
        "--model",
        default="yolo11n.pt",
    )

    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
    )

    parser.add_argument(
        "--conf",
        type=float,
        default=0.10,
    )

    args = parser.parse_args()

    input_video = Path(args.input).resolve()
    scan_summary = Path(args.scan_summary).resolve()
    output_root = Path(args.output).resolve()

    output_root.mkdir(parents=True, exist_ok=True)

    if not input_video.exists():
        raise FileNotFoundError(input_video)

    if not scan_summary.exists():
        raise FileNotFoundError(scan_summary)

    scan = json.loads(
        scan_summary.read_text(encoding="utf-8")
    )

    windows = scan.get("candidate_windows", [])

    if not windows:
        print("NO CANDIDATE WINDOWS")
        return 0

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    overall = []

    print("")
    print("===== PRECISION CANDIDATE ANALYSIS =====")
    print(f"candidate windows : {len(windows)}")
    print(f"model             : {args.model}")
    print(f"imgsz             : {args.imgsz}")
    print(f"confidence        : {args.conf}")

    for index, window in enumerate(windows, 1):

        start = float(window["start_sec"])
        end = float(window["end_sec"])
        duration = end - start

        candidate_dir = output_root / f"candidate_{index:03d}"
        candidate_dir.mkdir(parents=True, exist_ok=True)

        clip_path = candidate_dir / "source_clip.mp4"

        print("")
        print(
            f"===== CANDIDATE {index:03d} "
            f"{start:.2f}s - {end:.2f}s ====="
        )

        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(input_video),
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            str(clip_path),
        ]

        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        tracking_output = candidate_dir / "tracking"

        summary = run_tracking(
            input_video=clip_path,
            output_dir=tracking_output,
            model_name=args.model,
            image_size=args.imgsz,
            confidence=args.conf,
            max_seconds=None,
        )

        summary["candidate_index"] = index
        summary["source_start_sec"] = start
        summary["source_end_sec"] = end

        overall.append(summary)

    output_summary = {
        "input_video": str(input_video),
        "model": args.model,
        "image_size": args.imgsz,
        "confidence": args.conf,
        "candidate_count": len(windows),
        "candidates": overall,
    }

    summary_path = output_root / "precision_summary.json"

    summary_path.write_text(
        json.dumps(
            output_summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("===== PRECISION SUMMARY =====")

    for item in overall:
        d = item["detections"]

        print(
            f"candidate {item['candidate_index']:03d}: "
            f"persons={d['unique_person_count']} "
            f"dogs={d['unique_dog_count']} "
            f"dog_frames={d['frames_with_dog']} "
            f"records={d['track_records']}"
        )

    print("")
    print(f"SUMMARY: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
