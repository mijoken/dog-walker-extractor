from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import csv
import json
import time

import cv2
from ultralytics import YOLO


PERSON_CLASS_ID = 0
DOG_CLASS_ID = 16


@dataclass
class TrackRecord:
    frame_index: int
    timestamp_sec: float
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float
    center_x: float
    center_y: float
    width: float
    height: float


def _draw_box(frame, rec: TrackRecord) -> None:
    x1, y1, x2, y2 = map(int, (rec.x1, rec.y1, rec.x2, rec.y2))

    if rec.class_name == "person":
        label_prefix = "PERSON"
    else:
        label_prefix = "DOG"

    label = f"{label_prefix} #{rec.track_id} {rec.confidence:.2f}"

    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)

    text_y = max(20, y1 - 8)
    cv2.putText(
        frame,
        label,
        (x1, text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )


def run_tracking(
    input_video: str | Path,
    output_dir: str | Path,
    model_name: str = "yolo11n.pt",
    image_size: int = 640,
    confidence: float = 0.25,
    max_seconds: Optional[float] = None,
) -> dict:

    input_video = Path(input_video).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_video.exists():
        raise FileNotFoundError(f"Input video not found: {input_video}")

    print(f"Loading model: {model_name}")
    model = YOLO(model_name)

    cap = cv2.VideoCapture(str(input_video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {input_video}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps if fps > 0 else 0.0
    cap.release()

    if fps <= 0:
        raise RuntimeError("Invalid FPS reported by video.")

    process_frames = total_frames
    if max_seconds is not None:
        process_frames = min(
            total_frames,
            int(max_seconds * fps),
        )

    debug_path = output_dir / "tracking_debug.mp4"
    csv_path = output_dir / "tracks.csv"
    json_path = output_dir / "summary.json"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(
        str(debug_path),
        fourcc,
        fps,
        (width, height),
    )

    if not writer.isOpened():
        raise RuntimeError(f"Could not create debug video: {debug_path}")

    records: list[TrackRecord] = []

    unique_person_ids: set[int] = set()
    unique_dog_ids: set[int] = set()

    detected_person_frames = 0
    detected_dog_frames = 0

    started = time.perf_counter()

    print("")
    print("===== VIDEO INFO =====")
    print(f"input        : {input_video}")
    print(f"resolution   : {width}x{height}")
    print(f"fps          : {fps:.3f}")
    print(f"frames       : {total_frames}")
    print(f"duration_sec : {duration_sec:.3f}")
    print(f"process      : {process_frames} frames")

    results = model.track(
        source=str(input_video),
        stream=True,
        persist=True,
        tracker="bytetrack.yaml",
        classes=[PERSON_CLASS_ID, DOG_CLASS_ID],
        conf=confidence,
        imgsz=image_size,
        device="cpu",
        verbose=False,
    )

    processed = 0

    for frame_index, result in enumerate(results):
        if frame_index >= process_frames:
            break

        frame = result.orig_img.copy()
        timestamp_sec = frame_index / fps

        frame_has_person = False
        frame_has_dog = False

        boxes = result.boxes

        if boxes is not None and len(boxes) > 0:
            xyxy = boxes.xyxy.cpu().numpy()
            cls = boxes.cls.cpu().numpy()
            confs = boxes.conf.cpu().numpy()

            if boxes.id is not None:
                ids = boxes.id.cpu().numpy().astype(int)
            else:
                ids = [-1] * len(xyxy)

            for box, class_id_raw, conf_raw, track_id_raw in zip(
                xyxy, cls, confs, ids
            ):
                class_id = int(class_id_raw)
                track_id = int(track_id_raw)

                if class_id not in (PERSON_CLASS_ID, DOG_CLASS_ID):
                    continue

                x1, y1, x2, y2 = map(float, box)

                width_box = max(0.0, x2 - x1)
                height_box = max(0.0, y2 - y1)

                center_x = (x1 + x2) / 2.0
                center_y = (y1 + y2) / 2.0

                class_name = (
                    "person"
                    if class_id == PERSON_CLASS_ID
                    else "dog"
                )

                rec = TrackRecord(
                    frame_index=frame_index,
                    timestamp_sec=timestamp_sec,
                    track_id=track_id,
                    class_id=class_id,
                    class_name=class_name,
                    confidence=float(conf_raw),
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    center_x=center_x,
                    center_y=center_y,
                    width=width_box,
                    height=height_box,
                )

                records.append(rec)

                if class_name == "person":
                    frame_has_person = True
                    if track_id >= 0:
                        unique_person_ids.add(track_id)
                else:
                    frame_has_dog = True
                    if track_id >= 0:
                        unique_dog_ids.add(track_id)

                _draw_box(frame, rec)

        if frame_has_person:
            detected_person_frames += 1

        if frame_has_dog:
            detected_dog_frames += 1

        cv2.putText(
            frame,
            f"t={timestamp_sec:8.2f}s  frame={frame_index}",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        writer.write(frame)
        processed += 1

        if processed % max(1, int(fps * 5)) == 0:
            elapsed = time.perf_counter() - started
            speed = processed / elapsed if elapsed > 0 else 0
            realtime_ratio = speed / fps

            print(
                f"processed={processed}/{process_frames} "
                f"speed={speed:.2f} fps "
                f"realtime={realtime_ratio:.2f}x"
            )

    writer.release()

    elapsed = time.perf_counter() - started
    processing_fps = processed / elapsed if elapsed > 0 else 0.0

    fieldnames = list(TrackRecord.__annotations__.keys())

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer_csv = csv.DictWriter(f, fieldnames=fieldnames)
        writer_csv.writeheader()

        for rec in records:
            writer_csv.writerow(asdict(rec))

    summary = {
        "input_video": str(input_video),
        "model": model_name,
        "image_size": image_size,
        "confidence": confidence,
        "video": {
            "width": width,
            "height": height,
            "fps": fps,
            "total_frames": total_frames,
            "duration_sec": duration_sec,
        },
        "processing": {
            "processed_frames": processed,
            "elapsed_sec": elapsed,
            "processing_fps": processing_fps,
            "realtime_ratio": processing_fps / fps if fps > 0 else 0.0,
            "max_seconds": max_seconds,
        },
        "detections": {
            "track_records": len(records),
            "unique_person_track_ids": sorted(unique_person_ids),
            "unique_dog_track_ids": sorted(unique_dog_ids),
            "unique_person_count": len(unique_person_ids),
            "unique_dog_count": len(unique_dog_ids),
            "frames_with_person": detected_person_frames,
            "frames_with_dog": detected_dog_frames,
        },
        "outputs": {
            "csv": str(csv_path),
            "debug_video": str(debug_path),
        },
    }

    json_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("===== TRACKING RESULT =====")
    print(f"processed frames   : {processed}")
    print(f"elapsed sec        : {elapsed:.2f}")
    print(f"processing fps     : {processing_fps:.2f}")
    print(f"unique person IDs  : {len(unique_person_ids)}")
    print(f"unique dog IDs     : {len(unique_dog_ids)}")
    print(f"track records      : {len(records)}")
    print("")
    print(f"CSV   : {csv_path}")
    print(f"JSON  : {json_path}")
    print(f"VIDEO : {debug_path}")

    return summary
