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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            chunk = f.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def write_json_atomic(
    path: Path,
    payload: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = path.with_name(
        path.name + ".tmp"
    )

    with temp_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

        f.write("\n")
        f.flush()

    temp_path.replace(path)


def new_batch_state(
    *,
    source_root: Path,
    plan: list[tuple],
) -> dict:
    now = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    videos = []

    for (
        index,
        video,
        identifier,
        run_dir,
    ) in plan:
        relative = video.relative_to(
            source_root
        )

        videos.append(
            {
                "index": index,
                "identifier": identifier,
                "relative_path": str(relative),
                "source_path": str(video),
                "run_dir": str(run_dir),
                "status": "pending",
                "sha256": None,
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
        )

    return {
        "schema_version": 1,
        "pipeline": "dog_walker_folder_pipeline",
        "source_root": str(source_root),
        "created_at": now,
        "updated_at": now,
        "status": "running",
        "videos": videos,
    }


def update_batch_state_video(
    *,
    state: dict,
    identifier: str,
    status: str,
    sha256: str | None = None,
    error: str | None = None,
) -> None:
    now = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    matches = [
        item
        for item in state.get(
            "videos",
            [],
        )
        if item.get("identifier")
        == identifier
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "batch_state video lookup failed "
            f"for {identifier}: "
            f"{len(matches)} matches"
        )

    item = matches[0]

    item["status"] = status
    item["error"] = error

    if status == "running":
        item["started_at"] = now
        item["finished_at"] = None

    elif status in {
        "completed",
        "failed",
    }:
        item["finished_at"] = now

    if sha256 is not None:
        item["sha256"] = sha256

    state["updated_at"] = now


def get_batch_state_video(
    *,
    state: dict,
    identifier: str,
) -> dict | None:
    matches = [
        item
        for item in state.get(
            "videos",
            [],
        )
        if item.get("identifier")
        == identifier
    ]

    if len(matches) > 1:
        raise RuntimeError(
            "Duplicate batch_state identifier: "
            f"{identifier}"
        )

    if not matches:
        return None

    return matches[0]


def manifest_completion_proof(
    *,
    video: Path,
    run_dir: Path,
) -> tuple[bool, str | None, str]:
    manifest_path = (
        run_dir
        / "run_manifest.json"
    )

    if not manifest_path.exists():
        return (
            False,
            None,
            "no completed manifest",
        )

    try:
        manifest = load_json(
            manifest_path
        )

        manifest_input = (
            manifest.get(
                "input",
                {},
            )
        )

        stored_sha256 = (
            manifest_input.get(
                "sha256"
            )
        )

        finished_at = (
            manifest.get(
                "timing",
                {},
            ).get(
                "finished_at"
            )
        )

        if not stored_sha256:
            return (
                False,
                None,
                "manifest SHA-256 missing",
            )

        if not finished_at:
            return (
                False,
                stored_sha256,
                "manifest finished_at missing",
            )

        return (
            True,
            stored_sha256,
            "completed manifest",
        )

    except Exception as exc:
        return (
            False,
            None,
            "manifest validation failed: "
            f"{exc}",
        )


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

    parser.add_argument(
        "--resume-batch",
        help=(
            "Resume an existing batch directory. "
            "Completed videos with matching SHA-256 "
            "are reused."
        ),
    )

    parser.add_argument(
        "--resume-check",
        action="store_true",
        help=(
            "Inspect resume eligibility without "
            "processing any video."
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

    if args.resume_batch:
        batch_dir = Path(
            args.resume_batch
        ).resolve()

        if not batch_dir.exists():
            raise FileNotFoundError(
                batch_dir
            )

        if not batch_dir.is_dir():
            raise NotADirectoryError(
                batch_dir
            )

        batch_id = batch_dir.name

    else:
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

    resume_items = {}

    if args.resume_batch:
        print("")
        print("RESUME INSPECTION")

        resume_state_path = (
            batch_dir
            / "batch_state.json"
        )

        resume_state = None

        if resume_state_path.exists():
            resume_state = load_json(
                resume_state_path
            )

            if (
                resume_state.get(
                    "schema_version"
                )
                != 1
            ):
                raise RuntimeError(
                    "Unsupported batch_state "
                    "schema version."
                )

            print(
                "  mode: batch_state v1"
            )

        else:
            print(
                "  mode: legacy manifest"
            )

        for (
            index,
            video,
            identifier,
            run_dir,
        ) in plan:

            status = "REPROCESS"
            reason = "not verified"

            proof_ok, manifest_sha256, proof_reason = (
                manifest_completion_proof(
                    video=video,
                    run_dir=run_dir,
                )
            )

            if resume_state is not None:
                state_item = (
                    get_batch_state_video(
                        state=resume_state,
                        identifier=identifier,
                    )
                )

                relative_path = str(
                    video.relative_to(
                        source_root
                    )
                )

                if state_item is None:
                    reason = (
                        "batch_state entry missing"
                    )

                elif (
                    state_item.get("relative_path")
                    != relative_path
                ):
                    reason = (
                        "relative path changed"
                    )

                elif (
                    state_item.get("status")
                    != "completed"
                ):
                    reason = (
                        "batch_state status is "
                        f"{state_item.get('status')}"
                    )

                elif not state_item.get(
                    "sha256"
                ):
                    reason = (
                        "batch_state SHA-256 missing"
                    )

                elif not proof_ok:
                    reason = proof_reason

                elif (
                    manifest_sha256
                    != state_item.get(
                        "sha256"
                    )
                ):
                    reason = (
                        "batch_state / manifest "
                        "SHA-256 mismatch"
                    )

                else:
                    current_sha256 = (
                        file_sha256(
                            video
                        )
                    )

                    if (
                        current_sha256
                        == manifest_sha256
                    ):
                        status = "SKIP"
                        reason = (
                            "completed state, "
                            "relative path and "
                            "SHA-256 verified"
                        )

                        resume_items[
                            identifier
                        ] = (
                            collect_run_summary(
                                source_video=video,
                                run_dir=run_dir,
                                roi_enabled=(
                                    roi_profile
                                    is not None
                                ),
                            )
                        )

                    else:
                        reason = (
                            "current video "
                            "SHA-256 changed"
                        )

            else:
                # Legacy Phase-1 compatibility.
                if proof_ok:
                    try:
                        manifest = load_json(
                            run_dir
                            / "run_manifest.json"
                        )

                        stored_path = (
                            manifest.get(
                                "input",
                                {},
                            ).get(
                                "path"
                            )
                        )

                        current_sha256 = (
                            file_sha256(
                                video
                            )
                        )

                        if (
                            current_sha256
                            == manifest_sha256
                        ):
                            status = "SKIP"
                            reason = (
                                "legacy completed "
                                "manifest and SHA-256 match"
                            )

                            resume_items[
                                identifier
                            ] = (
                                collect_run_summary(
                                    source_video=video,
                                    run_dir=run_dir,
                                    roi_enabled=(
                                        roi_profile
                                        is not None
                                    ),
                                )
                            )

                        else:
                            reason = (
                                "SHA-256 changed"
                            )

                        if (
                            stored_path
                            and Path(
                                stored_path
                            ).resolve()
                            != video.resolve()
                        ):
                            status = "REPROCESS"
                            reason = (
                                "legacy manifest "
                                "input path changed"
                            )

                            resume_items.pop(
                                identifier,
                                None,
                            )

                    except Exception as exc:
                        status = "REPROCESS"
                        reason = (
                            "legacy manifest "
                            "validation failed: "
                            f"{exc}"
                        )

                        resume_items.pop(
                            identifier,
                            None,
                        )

                else:
                    reason = proof_reason

            print(
                f"  {index:04d} "
                f"{status:<9} "
                f"{video}"
            )

            print(
                f"       {reason}"
            )

        if args.resume_check:
            skip_count = len(
                resume_items
            )

            reprocess_count = (
                len(plan)
                - skip_count
            )

            print("")
            print(
                "RESUME CHECK ONLY - "
                "no video processing performed."
            )

            print(
                f"completed / skip : {skip_count}"
            )

            print(
                f"needs processing : {reprocess_count}"
            )

            print(
                "FOLDER_PIPELINE_RESUME_CHECK_OK"
            )

            return 0

    elif args.resume_check:
        raise ValueError(
            "--resume-check requires --resume-batch"
        )

    batch_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    batch_state_path = (
        batch_dir
        / "batch_state.json"
    )

    if batch_state_path.exists():
        batch_state = load_json(
            batch_state_path
        )

        if (
            batch_state.get(
                "schema_version"
            )
            != 1
        ):
            raise RuntimeError(
                "Unsupported batch_state "
                "schema version."
            )

        expected_plan = [
            {
                "identifier": identifier,
                "relative_path": str(
                    video.relative_to(
                        source_root
                    )
                ),
            }
            for (
                index,
                video,
                identifier,
                run_dir,
            ) in plan
        ]

        stored_plan = [
            {
                "identifier":
                    item.get("identifier"),
                "relative_path":
                    item.get("relative_path"),
            }
            for item in batch_state.get(
                "videos",
                [],
            )
        ]

        if stored_plan != expected_plan:
            raise RuntimeError(
                "Resume batch does not match "
                "the current input video plan."
            )

    else:
        batch_state = new_batch_state(
            source_root=source_root,
            plan=plan,
        )

        write_json_atomic(
            batch_state_path,
            batch_state,
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

        if identifier in resume_items:
            print("")
            print("#" * 76)
            print(
                f"VIDEO {index:04d}/{len(plan):04d}"
            )
            print(video)
            print("#" * 76)
            print(
                "RESUME SKIP - completed video "
                "verified by SHA-256."
            )

            results.append(
                resume_items[
                    identifier
                ]
            )

            continue

        print("")
        print("#" * 76)
        print(
            f"VIDEO {index:04d}/{len(plan):04d}"
        )
        print(video)
        print("#" * 76)

        try:
            update_batch_state_video(
                state=batch_state,
                identifier=identifier,
                status="running",
            )

            write_json_atomic(
                batch_state_path,
                batch_state,
            )

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

            if (
                args.force
                or (
                    args.resume_batch
                    and run_dir.exists()
                )
            ):
                cmd.append(
                    "--force"
                )

                if (
                    args.resume_batch
                    and run_dir.exists()
                    and not args.force
                ):
                    print(
                        "RESUME REPROCESS - "
                        "partial run directory will "
                        "be replaced."
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

            completed_manifest = load_json(
                run_dir
                / "run_manifest.json"
            )

            completed_sha256 = (
                completed_manifest.get(
                    "input",
                    {},
                ).get(
                    "sha256"
                )
            )

            if not completed_sha256:
                raise RuntimeError(
                    "Completed manifest SHA-256 "
                    "is missing."
                )

            update_batch_state_video(
                state=batch_state,
                identifier=identifier,
                status="completed",
                sha256=completed_sha256,
            )

            write_json_atomic(
                batch_state_path,
                batch_state,
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

            update_batch_state_video(
                state=batch_state,
                identifier=identifier,
                status="failed",
                error=str(exc),
            )

            write_json_atomic(
                batch_state_path,
                batch_state,
            )

            if not args.continue_on_error:
                finished_at = (
                    datetime.now()
                    .astimezone()
                    .isoformat()
                )

                batch_state["status"] = "incomplete"
                batch_state["finished_at"] = None
                batch_state["updated_at"] = finished_at

                write_json_atomic(
                    batch_state_path,
                    batch_state,
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

    if all(
        item.get("status") == "completed"
        for item in batch_state.get(
            "videos",
            [],
        )
    ):
        batch_state["status"] = "completed"
        batch_state["finished_at"] = finished_at

    else:
        batch_state["status"] = "incomplete"
        batch_state["finished_at"] = None

    batch_state["updated_at"] = finished_at

    write_json_atomic(
        batch_state_path,
        batch_state,
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
