from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
from ultralytics import YOLO


DOG_CLASS_ID = 16


def format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - minutes * 60
    return f"{minutes:02d}:{secs:05.2f}"


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument("--input", required=True)
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
        default=0.15,
    )

    parser.add_argument(
        "--stride",
        type=int,
        default=5,
        help="Analyze every Nth frame.",
    )

    args = parser.parse_args()

    input_video = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_video.exists():
        raise FileNotFoundError(input_video)

    model = YOLO(args.model)

    cap = cv2.VideoCapture(str(input_video))

    if not cap.isOpened():
        raise RuntimeError(f"Could not open: {input_video}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    duration_sec = total_frames / fps

    print("")
    print("===== DOG SCAN =====")
    print(f"video       : {input_video}")
    print(f"resolution  : {width}x{height}")
    print(f"fps         : {fps:.3f}")
    print(f"frames      : {total_frames}")
    print(f"duration    : {duration_sec:.2f} sec")
    print(f"stride      : {args.stride}")
    print(f"confidence  : {args.conf}")
    print(f"model       : {args.model}")

    rows = []

    frame_index = 0
    analyzed = 0
    dog_frames = 0

    started = time.perf_counter()

    while True:
        ok, frame = cap.read()

        if not ok:
            break

        if frame_index % args.stride != 0:
            frame_index += 1
            continue

        result = model.predict(
            source=frame,
            classes=[DOG_CLASS_ID],
            conf=args.conf,
            imgsz=args.imgsz,
            device="cpu",
            verbose=False,
        )[0]

        analyzed += 1

        boxes = result.boxes

        if boxes is not None and len(boxes) > 0:

            timestamp = frame_index / fps

            for box in boxes:
                conf = float(box.conf[0].cpu())

                xyxy = box.xyxy[0].cpu().tolist()

                x1, y1, x2, y2 = map(float, xyxy)

                rows.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_sec": timestamp,
                        "timestamp": format_time(timestamp),
                        "confidence": conf,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                    }
                )

            dog_frames += 1

        if analyzed % 300 == 0:
            elapsed = time.perf_counter() - started

            source_seconds = frame_index / fps

            print(
                f"analyzed={analyzed} "
                f"source={format_time(source_seconds)} "
                f"dog_frames={dog_frames} "
                f"elapsed={elapsed:.1f}s"
            )

        frame_index += 1

    cap.release()

    elapsed = time.perf_counter() - started

    csv_path = output_dir / "dog_scan.csv"
    json_path = output_dir / "dog_scan_summary.json"

    fieldnames = [
        "frame_index",
        "timestamp_sec",
        "timestamp",
        "confidence",
        "x1",
        "y1",
        "x2",
        "y2",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    timestamps = [
        row["timestamp_sec"]
        for row in rows
    ]

    # ----------------------------------------------------------
    # Consolidate detections into candidate temporal windows
    # ----------------------------------------------------------

    windows = []

    if timestamps:
        sorted_times = sorted(set(timestamps))

        start = sorted_times[0]
        previous = sorted_times[0]

        # detections separated by <= 3 sec belong to same event
        for t in sorted_times[1:]:

            if t - previous <= 3.0:
                previous = t
                continue

            windows.append(
                {
                    "start_sec": max(0.0, start - 5.0),
                    "end_sec": min(duration_sec, previous + 5.0),
                }
            )

            start = t
            previous = t

        windows.append(
            {
                "start_sec": max(0.0, start - 5.0),
                "end_sec": min(duration_sec, previous + 5.0),
            }
        )

    summary = {
        "input_video": str(input_video),
        "model": args.model,
        "image_size": args.imgsz,
        "confidence": args.conf,
        "stride": args.stride,
        "video": {
            "fps": fps,
            "total_frames": total_frames,
            "duration_sec": duration_sec,
        },
        "scan": {
            "analyzed_frames": analyzed,
            "dog_positive_frames": dog_frames,
            "dog_detections": len(rows),
            "elapsed_sec": elapsed,
        },
        "candidate_windows": windows,
    }

    json_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("")
    print("===== RESULT =====")
    print(f"analyzed frames : {analyzed}")
    print(f"dog frames      : {dog_frames}")
    print(f"dog detections  : {len(rows)}")
    print(f"elapsed sec     : {elapsed:.2f}")
    print("")

    if windows:
        print("Candidate dog windows:")

        for i, window in enumerate(windows, 1):
            print(
                f"{i:03d}: "
                f"{format_time(window['start_sec'])}"
                f" - "
                f"{format_time(window['end_sec'])}"
            )
    else:
        print("NO DOG CANDIDATE WINDOWS FOUND")

    print("")
    print(f"CSV  : {csv_path}")
    print(f"JSON : {json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
