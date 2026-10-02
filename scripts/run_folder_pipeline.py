from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".mts",
    ".m2ts",
}


def run_command(cmd: list[str], label: str) -> None:
    print("")
    print("=" * 76)
    print(label)
    print("=" * 76)
    print(" ".join(str(x) for x in cmd))
    print("")

    result = subprocess.run(
        cmd,
        cwd=REPO,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code "
            f"{result.returncode}"
        )


def load_json(path: Path) -> dict:
    return json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )


def safe_name(value: str) -> str:
    value = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    )

    value = value.strip("._-")

    return value or "video"


def short_path_hash(path: Path) -> str:
    return hashlib.sha1(
        str(path).encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()[:8]


def discover_videos(root: Path) -> list[Path]:
    videos = []

    for path in root.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower()
            in VIDEO_EXTENSIONS
        ):
            videos.append(
                path.resolve()
            )

    videos.sort(
        key=lambda p: str(p).lower()
    )

    return videos


def validate_roi_profile(
    path: Path,
) -> dict:
    profile = load_json(path)

    if not profile.get(
        "enabled",
        False,
    ):
        raise ValueError(
            "ROI profile was supplied but "
            "enabled=false."
        )

    required = (
        "frame_width",
        "frame_height",
        "target_polygon_norm",
        "near_polygon_norm",
        "thresholds",
    )

    missing = [
        key
        for key in required
        if key not in profile
    ]

    if missing:
        raise ValueError(
            "ROI profile missing fields: "
            + ", ".join(missing)
        )

    return profile


def collect_run_summary(
    *,
    source_video: Path,
    run_dir: Path,
    roi_enabled: bool,
) -> dict:

    manifest_path = (
        run_dir
        / "run_manifest.json"
    )

    manifest = load_json(
        manifest_path
    )

    result = manifest.get(
        "result",
        {},
    )

    review_clips = manifest.get(
        "review_clips",
        [],
    )

    item = {
        "source_video":
            str(source_video),

        "run_dir":
            str(run_dir),

        "status":
            "OK",

        "coarse_candidate_count":
            int(
                result.get(
                    "coarse_candidate_count",
                    0,
                )
            ),

        "dog_walker_event_count":
            int(
                result.get(
                    "final_event_count",
                    0,
                )
            ),

        "review_clip_count":
            len(review_clips),

        "roi_enabled":
            roi_enabled,

        "roi_target_event_count":
            0,

        "roi_dwell_event_count":
            0,

        "roi_stop_event_count":
            0,

        "review_clips": [
            x.get("file")
            for x in review_clips
        ],
    }

    if roi_enabled:
        roi_path = (
            run_dir
            / "precision_candidates"
            / "roi_behavior_events.json"
        )

        roi = load_json(
            roi_path
        )

        roi_results = [
            x
            for x in roi.get(
                "results",
                [],
            )
            if x.get(
                "available",
                False,
            )
        ]

        item[
            "roi_target_event_count"
        ] = sum(
            1
            for x in roi_results
            if x.get(
                "dog_at_target",
                False,
            )
        )

        item[
            "roi_dwell_event_count"
        ] = sum(
            1
            for x in roi_results
            if x.get(
                "dog_dwell",
                False,
            )
        )

        item[
            "roi_stop_event_count"
        ] = sum(
            1
            for x in roi_results
            if x.get(
                "dog_stop",
                False,
            )
        )

    return item


def write_batch_outputs(
    *,
    batch_dir: Path,
    source_root: Path,
    results: list[dict],
    started_at: str,
    finished_at: str,
) -> None:

    summary_json = {
        "pipeline":
            "dog-walker-folder-pipeline-v0.1",

        "dog_walker_detector":
            "v0.2.0",

        "source_root":
            str(source_root),

        "started_at":
            started_at,

        "finished_at":
            finished_at,

        "video_count":
            len(results),

        "successful_video_count":
            sum(
                1
                for x in results
                if x["status"] == "OK"
            ),

        "failed_video_count":
            sum(
                1
                for x in results
                if x["status"] != "OK"
            ),

        "total_dog_walker_events":
            sum(
                int(
                    x.get(
                        "dog_walker_event_count",
                        0,
                    )
                )
                for x in results
            ),

        "videos":
            results,
    }

    json_path = (
        batch_dir
        / "batch_summary.json"
    )

    json_path.write_text(
        json.dumps(
            summary_json,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    csv_path = (
        batch_dir
        / "batch_summary.csv"
    )

    fields = [
        "source_video",
        "run_dir",
        "status",
        "coarse_candidate_count",
        "dog_walker_event_count",
        "review_clip_count",
        "roi_enabled",
        "roi_target_event_count",
        "roi_dwell_event_count",
        "roi_stop_event_count",
        "error",
    ]

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()

        for item in results:
            writer.writerow({
                key: item.get(
                    key,
                    "",
                )
                for key in fields
            })

    print("")
    print("BATCH SUMMARY")
    print(f"  JSON: {json_path}")
    print(f"  CSV : {csv_path}")


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Process all supported videos in a "
            "folder or trail-camera SD card "
            "with the official dog-walker "
            "detector v0.2.0."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help=(
            "Input folder or SD-card root."
        ),
    )

    parser.add_argument(
        "--output",
        default=str(
            REPO
            / "output"
            / "app_runs"
        ),
        help=(
            "Root directory for app runs."
        ),
    )

    parser.add_argument(
        "--roi-profile",
        help=(
            "Optional enabled ROI profile JSON. "
            "Omit until a real camera profile exists."
        ),
    )

    parser.add_argument(
        "--batch-id",
        help=(
            "Optional batch identifier. "
            "Default: timestamp."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Replace an existing per-video "
            "run directory."
        ),
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help=(
            "Continue with remaining videos "
            "when one video fails."
        ),
    )

    parser.add_argument(
        "--plan",
        action="store_true",
        help=(
            "List discovered videos and planned "
            "outputs without processing video."
        ),
    )

    args = parser.parse_args()

    source_root = Path(
        args.input
    ).resolve()

    if not source_root.exists():
        raise FileNotFoundError(
            source_root
        )

    if not source_root.is_dir():
        raise NotADirectoryError(
            source_root
        )

    output_root = Path(
        args.output
    ).resolve()

    roi_profile = None

    if args.roi_profile:
        roi_profile = Path(
            args.roi_profile
        ).resolve()

        if not roi_profile.exists():
            raise FileNotFoundError(
                roi_profile
            )

        validate_roi_profile(
            roi_profile
        )

    videos = discover_videos(
        source_root
    )

    print("")
    print("=" * 76)
    print(
        "DOG WALKER EXTRACTOR "
        "- FOLDER PIPELINE"
    )
    print("=" * 76)

    print(
        f"input root : {source_root}"
    )

    print(
        f"videos     : {len(videos)}"
    )

    print(
        "ROI        : "
        + (
            str(roi_profile)
            if roi_profile
            else "disabled"
        )
    )

    if not videos:
        print("")
        print(
            "No supported videos found."
        )
        return 0

    batch_id = (
        safe_name(
            args.batch_id
        )
        if args.batch_id
        else datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    batch_dir = (
        output_root
        / batch_id
    )

    print(
        f"batch dir  : {batch_dir}"
    )

    plan = []

    for index, video in enumerate(
        videos,
        start=1,
    ):
        relative = video.relative_to(
            source_root
        )

        identifier = (
            f"{index:04d}_"
            f"{safe_name(video.stem)}_"
            f"{short_path_hash(relative)}"
        )

        run_dir = (
            batch_dir
            / identifier
        )

        plan.append(
            (
                index,
                video,
                identifier,
                run_dir,
            )
        )

    print("")
    print("DISCOVERED VIDEOS")

    for (
        index,
        video,
        identifier,
        run_dir,
    ) in plan:

        print(
            f"  {index:04d} "
            f"{video}"
        )

        print(
            f"       -> {run_dir}"
        )

    if args.plan:
        print("")
        print(
            "PLAN ONLY - no video processing performed."
        )
        print(
            "FOLDER_PIPELINE_PLAN_OK"
        )
        return 0

    batch_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    started_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    results = []

    for (
        index,
        video,
        identifier,
        run_dir,
    ) in plan:

        print("")
        print("#" * 76)
        print(
            f"VIDEO {index:04d}/{len(plan):04d}"
        )
        print(video)
        print("#" * 76)

        try:
            cmd = [
                sys.executable,
                str(
                    SCRIPTS
                    / "validation_runner.py"
                ),
                "--input",
                str(video),
                "--validation-id",
                identifier,
                "--output-root",
                str(run_dir),
            ]

            if args.force:
                cmd.append(
                    "--force"
                )

            run_command(
                cmd,
                (
                    f"OFFICIAL v0.2 "
                    f"VIDEO {index:04d}"
                ),
            )

            if roi_profile is not None:

                precision_root = (
                    run_dir
                    / "precision_candidates"
                )

                run_command(
                    [
                        sys.executable,
                        str(
                            SCRIPTS
                            / "analyze_roi_behavior.py"
                        ),
                        "--root",
                        str(
                            precision_root
                        ),
                        "--profile",
                        str(
                            roi_profile
                        ),
                    ],
                    (
                        f"ROI ANALYSIS "
                        f"VIDEO {index:04d}"
                    ),
                )

            item = collect_run_summary(
                source_video=video,
                run_dir=run_dir,
                roi_enabled=(
                    roi_profile
                    is not None
                ),
            )

            results.append(
                item
            )

        except Exception as exc:

            failed = {
                "source_video":
                    str(video),

                "run_dir":
                    str(run_dir),

                "status":
                    "FAILED",

                "error":
                    str(exc),

                "coarse_candidate_count":
                    0,

                "dog_walker_event_count":
                    0,

                "review_clip_count":
                    0,

                "roi_enabled":
                    roi_profile
                    is not None,

                "roi_target_event_count":
                    0,

                "roi_dwell_event_count":
                    0,

                "roi_stop_event_count":
                    0,
            }

            results.append(
                failed
            )

            if not args.continue_on_error:
                finished_at = (
                    datetime.now()
                    .astimezone()
                    .isoformat()
                )

                write_batch_outputs(
                    batch_dir=batch_dir,
                    source_root=source_root,
                    results=results,
                    started_at=started_at,
                    finished_at=finished_at,
                )

                raise

    finished_at = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    write_batch_outputs(
        batch_dir=batch_dir,
        source_root=source_root,
        results=results,
        started_at=started_at,
        finished_at=finished_at,
    )

    success = sum(
        1
        for x in results
        if x["status"] == "OK"
    )

    failed = (
        len(results) - success
    )

    total_events = sum(
        int(
            x.get(
                "dog_walker_event_count",
                0,
            )
        )
        for x in results
    )

    print("")
    print("=" * 76)
    print("FOLDER PIPELINE COMPLETE")
    print("=" * 76)

    print(
        f"videos OK        : {success}"
    )

    print(
        f"videos failed    : {failed}"
    )

    print(
        f"dog-walker events: {total_events}"
    )

    print(
        f"batch directory  : {batch_dir}"
    )

    print("")
    print(
        "FOLDER_PIPELINE_OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
