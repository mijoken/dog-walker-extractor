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
from app_runtime import build_script_command


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


def new_files_batch_state(
    *,
    entries: list[dict],
    plan: list[tuple],
) -> dict:
    if len(entries) != len(plan):
        raise RuntimeError(
            "Files batch_state entries / plan "
            "length mismatch."
        )

    now = (
        datetime.now()
        .astimezone()
        .isoformat()
    )

    videos = []

    for entry, plan_item in zip(
        entries,
        plan,
        strict=True,
    ):
        (
            index,
            video,
            identifier,
            run_dir,
        ) = plan_item

        source_path = Path(
            entry["source_path"]
        ).resolve()

        if source_path != video.resolve():
            raise RuntimeError(
                "Files batch_state source_path "
                "does not match plan."
            )

        videos.append(
            {
                "index": index,
                "entry_id": entry["entry_id"],
                "identifier": identifier,
                "logical_path":
                    entry["logical_path"],
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
        "schema_version": 2,
        "pipeline":
            "dog_walker_folder_pipeline",
        "input_mode": "files",
        "created_at": now,
        "updated_at": now,
        "status": "running",
        "videos": videos,
    }


def validate_files_batch_state(
    *,
    state: dict,
    entries: list[dict],
    plan: list[tuple],
) -> None:
    if state.get("schema_version") != 2:
        raise RuntimeError(
            "Files batch_state requires "
            "schema_version 2."
        )

    if state.get("input_mode") != "files":
        raise RuntimeError(
            "Files batch_state input_mode "
            "must be 'files'."
        )

    stored_videos = state.get("videos")

    if not isinstance(stored_videos, list):
        raise RuntimeError(
            "Files batch_state videos "
            "must be a list."
        )

    if (
        len(stored_videos) != len(entries)
        or len(entries) != len(plan)
    ):
        raise RuntimeError(
            "Files batch_state plan length "
            "does not match current selection."
        )

    for stored, entry, plan_item in zip(
        stored_videos,
        entries,
        plan,
        strict=True,
    ):
        (
            index,
            _video,
            identifier,
            _run_dir,
        ) = plan_item

        if stored.get("index") != index:
            raise RuntimeError(
                "Files batch_state index "
                "does not match current plan."
            )

        if (
            stored.get("entry_id")
            != entry["entry_id"]
        ):
            raise RuntimeError(
                "Files batch_state entry_id "
                "does not match current plan."
            )

        stored_logical = (
            canonical_files_logical_path(
                stored.get("logical_path")
            )
        )

        if stored_logical != entry["logical_path"]:
            raise RuntimeError(
                "Files batch_state logical_path "
                "does not match current plan."
            )

        if stored.get("identifier") != identifier:
            raise RuntimeError(
                "Files batch_state identifier "
                "does not match current plan."
            )


def sync_files_batch_state_sources(
    *,
    state: dict,
    entries: list[dict],
    plan: list[tuple],
) -> bool:
    validate_files_batch_state(
        state=state,
        entries=entries,
        plan=plan,
    )

    stored_videos = state["videos"]
    changed = False

    for stored, entry, plan_item in zip(
        stored_videos,
        entries,
        plan,
        strict=True,
    ):
        (
            _index,
            video,
            _identifier,
            run_dir,
        ) = plan_item

        current_source = str(
            Path(entry["source_path"]).resolve()
        )
        current_run_dir = str(
            run_dir.resolve()
        )

        if stored.get("source_path") != current_source:
            stored["source_path"] = current_source
            changed = True

        if stored.get("run_dir") != current_run_dir:
            stored["run_dir"] = current_run_dir
            changed = True

        if video.resolve() != Path(
            current_source
        ).resolve():
            raise RuntimeError(
                "Files batch_state source sync "
                "does not match current plan."
            )

    if changed:
        state["updated_at"] = (
            datetime.now()
            .astimezone()
            .isoformat()
        )

    return changed


def load_or_create_batch_state(
    *,
    state_path: Path,
    input_mode: str,
    plan: list[tuple],
    source_root: Path | None = None,
    entries: list[dict] | None = None,
) -> dict:
    if input_mode not in {
        "folder",
        "files",
    }:
        raise RuntimeError(
            f"Unsupported input_mode: {input_mode}"
        )

    if state_path.exists():
        state = load_json(state_path)

        if input_mode == "folder":
            if state.get("schema_version") != 1:
                raise RuntimeError(
                    "Folder batch_state requires "
                    "schema_version 1."
                )

            if source_root is None:
                raise RuntimeError(
                    "Folder batch_state requires "
                    "source_root."
                )

            expected_plan = []

            for (
                _index,
                video,
                identifier,
                _run_dir,
            ) in plan:
                expected_plan.append(
                    {
                        "identifier": identifier,
                        "relative_path": str(
                            video.relative_to(
                                source_root
                            )
                        ),
                    }
                )

            stored_plan = [
                {
                    "identifier":
                        item.get("identifier"),
                    "relative_path":
                        item.get("relative_path"),
                }
                for item in state.get(
                    "videos",
                    [],
                )
            ]

            if stored_plan != expected_plan:
                raise RuntimeError(
                    "Stored folder batch_state "
                    "plan does not match current plan."
                )

            return state

        if entries is None:
            raise RuntimeError(
                "Files batch_state requires entries."
            )

        validate_files_batch_state(
            state=state,
            entries=entries,
            plan=plan,
        )

        changed = sync_files_batch_state_sources(
            state=state,
            entries=entries,
            plan=plan,
        )

        if changed:
            write_json_atomic(
                state_path,
                state,
            )

        return state

    if input_mode == "folder":
        if source_root is None:
            raise RuntimeError(
                "Folder batch_state requires "
                "source_root."
            )

        state = new_batch_state(
            source_root=source_root,
            plan=plan,
        )
    else:
        if entries is None:
            raise RuntimeError(
                "Files batch_state requires entries."
            )

        state = new_files_batch_state(
            entries=entries,
            plan=plan,
        )

    write_json_atomic(
        state_path,
        state,
    )

    return state


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


def resume_decision_for_video(
    *,
    video: Path,
    run_dir: Path,
    state_video: dict | None,
) -> tuple[str, str]:
    if state_video is None:
        return (
            "REPROCESS",
            "state entry missing",
        )

    status = state_video.get("status")

    if status != "completed":
        return (
            "REPROCESS",
            f"state status is {status!r}",
        )

    state_sha256 = state_video.get(
        "sha256"
    )

    if (
        not isinstance(
            state_sha256,
            str,
        )
        or not state_sha256
    ):
        return (
            "REPROCESS",
            "state SHA-256 missing",
        )

    (
        proof_ok,
        manifest_sha256,
        proof_reason,
    ) = manifest_completion_proof(
        video=video,
        run_dir=run_dir,
    )

    if not proof_ok:
        return (
            "REPROCESS",
            proof_reason,
        )

    if manifest_sha256 != state_sha256:
        return (
            "REPROCESS",
            "batch_state / manifest "
            "SHA-256 mismatch",
        )

    current_sha256 = file_sha256(
        video
    )

    if current_sha256 != manifest_sha256:
        return (
            "REPROCESS",
            "current file SHA-256 changed",
        )

    return (
        "SKIP",
        "completed state and "
        "SHA-256 verified",
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



def canonical_files_logical_path(
    value: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        raise RuntimeError(
            "logical_path must be "
            "a non-empty string."
        )

    logical_path = (
        value.strip()
        .replace(
            "\\",
            "/",
        )
    )

    if logical_path.startswith("/"):
        raise RuntimeError(
            "logical_path must be relative: "
            f"{value}"
        )

    if ":" in logical_path:
        raise RuntimeError(
            "logical_path must not contain "
            "a drive or URI prefix: "
            f"{value}"
        )

    parts = logical_path.split("/")

    if any(
        part in {
            "",
            ".",
            "..",
        }
        for part in parts
    ):
        raise RuntimeError(
            "logical_path contains an "
            "invalid path component: "
            f"{value}"
        )

    return "/".join(
        parts
    ).casefold()


def load_files_manifest(
    manifest_path: Path,
) -> list[dict]:
    manifest_path = (
        manifest_path.resolve()
    )

    if not manifest_path.exists():
        raise FileNotFoundError(
            manifest_path
        )

    if not manifest_path.is_file():
        raise RuntimeError(
            "Input manifest is not a file: "
            f"{manifest_path}"
        )

    data = load_json(
        manifest_path
    )

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "Input manifest root "
            "must be an object."
        )

    if (
        data.get("schema_version")
        != 2
    ):
        raise RuntimeError(
            "Structured files mode requires "
            "schema_version 2."
        )

    if (
        data.get("input_mode")
        != "files"
    ):
        raise RuntimeError(
            "Input manifest input_mode "
            "must be 'files'."
        )

    values = data.get(
        "files"
    )

    if not isinstance(
        values,
        list,
    ):
        raise RuntimeError(
            "Input manifest files "
            "must be a list."
        )

    if not values:
        raise RuntimeError(
            "Input manifest contains "
            "no files."
        )

    entries = []

    seen_entry_ids = set()
    seen_logical_paths = set()
    seen_source_paths = set()

    for index, value in enumerate(
        values,
        start=1,
    ):
        if not isinstance(
            value,
            dict,
        ):
            raise RuntimeError(
                "Input manifest file "
                f"entry {index} must be "
                "an object."
            )

        entry_id = value.get(
            "entry_id"
        )

        if (
            not isinstance(
                entry_id,
                str,
            )
            or not entry_id.strip()
        ):
            raise RuntimeError(
                "entry_id must be a "
                "non-empty string."
            )

        entry_id = entry_id.strip()

        if not re.fullmatch(
            r"[A-Za-z0-9._-]+",
            entry_id,
        ):
            raise RuntimeError(
                "Invalid entry_id: "
                f"{entry_id}"
            )

        entry_key = (
            entry_id.casefold()
        )

        if (
            entry_key
            in seen_entry_ids
        ):
            raise RuntimeError(
                "Duplicate entry_id: "
                f"{entry_id}"
            )

        logical_path = (
            canonical_files_logical_path(
                value.get(
                    "logical_path"
                )
            )
        )

        if (
            logical_path
            in seen_logical_paths
        ):
            raise RuntimeError(
                "Duplicate logical_path: "
                f"{logical_path}"
            )

        source_value = value.get(
            "source_path"
        )

        if (
            not isinstance(
                source_value,
                str,
            )
            or not source_value.strip()
        ):
            raise RuntimeError(
                "source_path must be a "
                "non-empty string."
            )

        video = Path(
            source_value
        ).resolve()

        if not video.exists():
            raise FileNotFoundError(
                video
            )

        if not video.is_file():
            raise RuntimeError(
                "Selected video is "
                "not a file: "
                f"{video}"
            )

        if (
            video.suffix.lower()
            not in VIDEO_EXTENSIONS
        ):
            raise RuntimeError(
                "Unsupported selected "
                "video extension: "
                f"{video}"
            )

        source_key = str(
            video
        ).casefold()

        if (
            source_key
            in seen_source_paths
        ):
            raise RuntimeError(
                "Duplicate source_path: "
                f"{video}"
            )

        seen_entry_ids.add(
            entry_key
        )

        seen_logical_paths.add(
            logical_path
        )

        seen_source_paths.add(
            source_key
        )

        entries.append(
            {
                "entry_id": entry_id,
                "logical_path": logical_path,
                "source_path": video,
            }
        )

    return entries


def build_files_plan(
    *,
    entries: list[dict],
    batch_dir: Path,
) -> list[tuple]:
    plan = []

    for index, entry in enumerate(
        entries,
        start=1,
    ):
        video = entry[
            "source_path"
        ]

        logical_path = entry[
            "logical_path"
        ]

        logical_hash = hashlib.sha1(
            logical_path.encode(
                "utf-8",
                errors="replace",
            )
        ).hexdigest()[:8]

        identifier = (
            f"{index:04d}_"
            f"{safe_name(
                Path(logical_path).stem
            )}_"
            f"{logical_hash}"
        )

        run_dir = (
            batch_dir
            / "videos"
            / identifier
        )

        # Keep the existing four-item plan
        # contract intact. Structured identity
        # remains in entries for schema-v2 state.
        plan.append(
            (
                index,
                video,
                identifier,
                run_dir,
            )
        )

    return plan


def build_video_plan(
    *,
    videos: list[Path],
    source_root: Path,
    batch_dir: Path,
) -> list[tuple]:
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

    return plan


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
        required=False,
        help=(
            "Input folder or SD-card root."
        ),
    )
    parser.add_argument(
        "--input-manifest",
        help=(
            "JSON manifest containing "
            "an explicit ordered "
            "video-file selection. "
            "Phase 4H supports files "
            "mode with --plan only."
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

    if bool(
        args.input
    ) == bool(
        args.input_manifest
    ):
        raise RuntimeError(
            "Specify exactly one of "
            "--input or "
            "--input-manifest."
        )

    input_mode = (
        "files"
        if args.input_manifest
        else "folder"
    )

    source_root = None
    selected_entries = None

    if input_mode == "folder":
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

    else:
        selected_entries = (
            load_files_manifest(
                Path(
                    args.input_manifest
                )
            )
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

    if input_mode == "folder":
        videos = discover_videos(
            source_root
        )
    else:
        videos = [
            entry["source_path"]
            for entry in selected_entries
        ]

    print("")
    print("=" * 76)
    print(
        "DOG WALKER EXTRACTOR "
        "- FOLDER PIPELINE"
    )
    print("=" * 76)

    if input_mode == "folder":
        print(
            f"input root : "
            f"{source_root}"
        )
    else:
        print(
            "input mode : explicit files"
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

    if input_mode == "folder":
        plan = build_video_plan(
            videos=videos,
            source_root=source_root,
            batch_dir=batch_dir,
        )
    else:
        plan = build_files_plan(
            entries=selected_entries,
            batch_dir=batch_dir,
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

    batch_state = load_or_create_batch_state(
        state_path=batch_state_path,
        input_mode=input_mode,
        plan=plan,
        source_root=source_root,
        entries=selected_entries,
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

        print(
            f"GUI_RUN_DIR: {run_dir}",
            flush=True,
        )

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

            cmd = build_script_command(
                "validation_runner.py",
                "--input",
                str(video),
                "--validation-id",
                identifier,
                "--output-root",
                str(run_dir),
            )

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
                    build_script_command(
                        "analyze_roi_behavior.py",
                        "--root",
                        str(
                            precision_root
                        ),
                        "--profile",
                        str(
                            roi_profile
                        ),
                    ),
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
