from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

# ----------------------------------------------------------------------
# OFFICIAL v0.2 PARAMETERS
#
# These are intentionally copied from the validated pipeline.
# Do not change them during blind validation without creating a new
# algorithm version and documenting why.
# ----------------------------------------------------------------------

MODEL = "yolo11n.pt"

SCAN_IMGSZ = 640
SCAN_CONF = 0.15
SCAN_STRIDE = 5

PRECISION_IMGSZ = 640
PRECISION_CONF = 0.10

REVIEW_PAD_BEFORE_SEC = 5.0
REVIEW_PAD_AFTER_SEC = 5.0


def run_command(cmd: list[str], stage: str) -> None:
    print("")
    print("=" * 72)
    print(stage)
    print("=" * 72)
    print("COMMAND:")
    print(" ".join(str(x) for x in cmd))
    print("")

    completed = subprocess.run(
        cmd,
        cwd=REPO,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"{stage} failed with exit code "
            f"{completed.returncode}"
        )


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)

    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()


def sec_to_label(value: float) -> str:
    value = max(0.0, float(value))

    minutes = int(value // 60)
    seconds = value - minutes * 60

    return f"{minutes:02d}m{seconds:05.2f}s"


def make_review_clips(
    *,
    input_video: Path,
    event_json: Path,
    review_dir: Path,
) -> list[dict]:

    review_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = load_json(event_json)

    events = data.get("events", [])

    if not events:
        print("")
        print("NO FINAL EVENTS -> no event review clips created.")
        return []

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    outputs = []

    for event in events:
        event_id = int(event["event_id"])

        event_start = float(event["start_sec"])
        event_end = float(event["end_sec"])

        clip_start = max(
            0.0,
            event_start - REVIEW_PAD_BEFORE_SEC,
        )

        clip_end = (
            event_end
            + REVIEW_PAD_AFTER_SEC
        )

        duration = max(
            0.1,
            clip_end - clip_start,
        )

        output = (
            review_dir
            / (
                f"event_{event_id:03d}_"
                f"{sec_to_label(event_start)}_"
                f"{sec_to_label(event_end)}.mp4"
            )
        )

        cmd = [
            ffmpeg,
            "-y",
            "-ss",
            f"{clip_start:.3f}",
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
            str(output),
        ]

        run_command(
            cmd,
            f"CREATE REVIEW CLIP EVENT {event_id:03d}",
        )

        outputs.append(
            {
                "event_id": event_id,
                "event_start_sec": event_start,
                "event_end_sec": event_end,
                "clip_start_sec": clip_start,
                "clip_end_sec": clip_end,
                "file": str(output),
            }
        )

    return outputs


def write_zero_event_result(
    *,
    output_root: Path,
    scan_summary: dict,
) -> Path:

    final_dir = (
        output_root
        / "precision_candidates"
    )

    final_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = (
        final_dir
        / "dog_walker_events.json"
    )

    result = {
        "parameters": {
            "pipeline": "official_v0.2",
            "note": (
                "No coarse dog candidate windows were produced. "
                "Precision analysis and association were not required."
            ),
        },
        "scan_candidate_count": 0,
        "raw_evidence": [],
        "events": [],
        "scan_summary": scan_summary,
    }

    output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return output


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the official Dog Walker Extractor "
            "v0.2 validation pipeline."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Input video file.",
    )

    parser.add_argument(
        "--validation-id",
        required=True,
        help='Validation ID, e.g. "003".',
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Delete an existing output directory "
            "for the same validation ID."
        ),
    )

    parser.add_argument(
        "--plan",
        action="store_true",
        help=(
            "Validate paths and print the planned run "
            "without processing the video."
        ),
    )

    args = parser.parse_args()

    input_video = Path(args.input).resolve()

    if not input_video.exists():
        raise FileNotFoundError(
            f"Input video not found: {input_video}"
        )

    validation_id = str(
        args.validation_id
    ).strip()

    if not validation_id:
        raise ValueError(
            "validation-id must not be empty."
        )

    output_root = (
        REPO
        / "output"
        / f"blind_test_{validation_id}"
    )

    scan_dir = (
        output_root
        / "dog_scan"
    )

    precision_dir = (
        output_root
        / "precision_candidates"
    )

    review_dir = (
        output_root
        / "review"
    )

    print("")
    print("=" * 72)
    print("DOG WALKER EXTRACTOR - OFFICIAL v0.2 VALIDATION RUNNER")
    print("=" * 72)

    print(f"repository     : {REPO}")
    print(f"input video    : {input_video}")
    print(f"validation id  : {validation_id}")
    print(f"output root    : {output_root}")

    print("")
    print("OFFICIAL v0.2 PARAMETERS")
    print(f"model          : {MODEL}")
    print(f"scan imgsz     : {SCAN_IMGSZ}")
    print(f"scan conf      : {SCAN_CONF}")
    print(f"scan stride    : {SCAN_STRIDE}")
    print(f"precision imgsz: {PRECISION_IMGSZ}")
    print(f"precision conf : {PRECISION_CONF}")

    if args.plan:
        print("")
        print("PLAN ONLY - no video processing performed.")
        print("")
        print("Stages:")
        print("  1. coarse dog scan")
        print("  2. precision candidate analysis")
        print("  3. track quality audit")
        print("  4. frozen association V2")
        print("  5. frozen event generation")
        print("  6. review clip generation")
        print("  7. run manifest")
        return 0

    if output_root.exists():

        if not args.force:
            raise RuntimeError(
                f"Output already exists: {output_root}\n"
                "Use --force only when you intentionally "
                "want to rerun this validation."
            )

        print("")
        print(
            f"Removing existing output: "
            f"{output_root}"
        )

        shutil.rmtree(output_root)

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    started_at = datetime.now().astimezone()

    input_hash = sha256_file(
        input_video
    )

    # ==============================================================
    # STAGE 1
    # Coarse dog scan
    # ==============================================================

    run_command(
        [
            sys.executable,
            str(SCRIPTS / "scan_dogs.py"),
            "--input",
            str(input_video),
            "--output",
            str(scan_dir),
            "--model",
            MODEL,
            "--imgsz",
            str(SCAN_IMGSZ),
            "--conf",
            str(SCAN_CONF),
            "--stride",
            str(SCAN_STRIDE),
        ],
        "STAGE 1 - FROZEN COARSE DOG SCAN",
    )

    scan_summary_path = (
        scan_dir
        / "dog_scan_summary.json"
    )

    scan_summary = load_json(
        scan_summary_path
    )

    windows = scan_summary.get(
        "candidate_windows",
        [],
    )

    print("")
    print(
        f"COARSE CANDIDATE WINDOWS: "
        f"{len(windows)}"
    )

    # ==============================================================
    # VALID ZERO-CANDIDATE PATH
    # ==============================================================

    if len(windows) == 0:

        print("")
        print(
            "No coarse candidate windows found."
        )

        event_json = write_zero_event_result(
            output_root=output_root,
            scan_summary=scan_summary,
        )

        review_outputs = []

    else:

        # ==========================================================
        # STAGE 2
        # Precision tracking
        # ==========================================================

        run_command(
            [
                sys.executable,
                str(
                    SCRIPTS
                    / "analyze_candidates.py"
                ),
                "--input",
                str(input_video),
                "--scan-summary",
                str(scan_summary_path),
                "--output",
                str(precision_dir),
                "--model",
                MODEL,
                "--imgsz",
                str(PRECISION_IMGSZ),
                "--conf",
                str(PRECISION_CONF),
            ],
            "STAGE 2 - FROZEN PRECISION ANALYSIS",
        )

        # ==========================================================
        # STAGE 3
        # Track-quality audit
        # ==========================================================

        run_command(
            [
                sys.executable,
                str(
                    SCRIPTS
                    / "audit_track_quality_param.py"
                ),
                "--root",
                str(precision_dir),
            ],
            "STAGE 3 - TRACK QUALITY AUDIT",
        )

        # ==========================================================
        # STAGES 4 + 5
        # Frozen Association V2 + Event Generation
        # ==========================================================

        run_command(
            [
                sys.executable,
                str(
                    SCRIPTS
                    / "run_frozen_validation.py"
                ),
                "--root",
                str(precision_dir),
            ],
            (
                "STAGE 4/5 - FROZEN ASSOCIATION "
                "AND EVENT GENERATION"
            ),
        )

        event_json = (
            precision_dir
            / "dog_walker_events.json"
        )

        if not event_json.exists():
            raise FileNotFoundError(
                event_json
            )

        # ==========================================================
        # STAGE 6
        # Review clips
        # ==========================================================

        review_outputs = make_review_clips(
            input_video=input_video,
            event_json=event_json,
            review_dir=review_dir,
        )

    # ==============================================================
    # STAGE 7
    # Manifest
    # ==============================================================

    final_result = load_json(
        event_json
    )

    final_events = final_result.get(
        "events",
        [],
    )

    finished_at = datetime.now().astimezone()

    manifest = {
        "validation_id": validation_id,
        "pipeline_version": "official_v0.2",
        "input": {
            "path": str(input_video),
            "filename": input_video.name,
            "sha256": input_hash,
        },
        "frozen_parameters": {
            "dog_walker_detector_version": "v0.2.0",
            "model": MODEL,
            "scan_imgsz": SCAN_IMGSZ,
            "scan_conf": SCAN_CONF,
            "scan_stride": SCAN_STRIDE,
            "precision_imgsz": PRECISION_IMGSZ,
            "precision_conf": PRECISION_CONF,
            "association": "V2",
            "duration_saturation_sec": 2.5,
            "persistence_saturation_sec": 3.0,
            "min_pair_score": 0.55,
            "min_pair_span_sec": 1.0,
            "min_dog_frames": 5,
            "merge_gap_sec": 1.5,
        },
        "result": {
            "coarse_candidate_count": len(windows),
            "final_event_count": len(final_events),
            "events": final_events,
        },
        "review_clips": review_outputs,
        "timing": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        },
        "artifacts": {
            "scan_summary": str(scan_summary_path),
            "event_json": str(event_json),
        },
    }

    manifest_path = (
        output_root
        / "run_manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("=" * 72)
    print("VALIDATION COMPLETE")
    print("=" * 72)

    print(
        f"candidate windows : "
        f"{len(windows)}"
    )

    print(
        f"final events      : "
        f"{len(final_events)}"
    )

    if final_events:
        print("")
        print("FINAL EVENTS")

        for event in final_events:
            print(
                f"  EVENT {event['event_id']:03d} "
                f"{event['start_time']} - "
                f"{event['end_time']} "
                f"score="
                f"{event['mean_pair_score']:.3f}"
            )

    else:
        print("")
        print("FINAL RESULT: 0 DOG-WALKER EVENTS")

    print("")
    print(
        f"manifest: "
        f"{manifest_path}"
    )

    print("")
    print("VALIDATION_RUNNER_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
