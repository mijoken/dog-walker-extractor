from __future__ import annotations

import runpy
import sys

from app_paths import scripts_dir


SCRIPTS = scripts_dir()

WORKERS = {
    "run_folder_pipeline.py",
    "validation_runner.py",
    "scan_dogs.py",
    "analyze_candidates.py",
    "audit_track_quality_param.py",
    "run_frozen_validation.py",
    "analyze_roi_behavior.py",
}


def run_worker(
    script_name: str,
    worker_args: list[str],
) -> int:
    if script_name not in WORKERS:
        raise ValueError(
            f"Unknown worker: {script_name}"
        )

    script_path = SCRIPTS / script_name

    if not script_path.is_file():
        raise FileNotFoundError(
            script_path
        )

    sys.argv = [
        str(script_path),
        *worker_args,
    ]

    try:
        runpy.run_path(
            str(script_path),
            run_name="__main__",
        )
    except SystemExit as exc:
        if exc.code is None:
            return 0

        if isinstance(exc.code, int):
            return exc.code

        raise

    return 0


def main() -> int:
    args = sys.argv[1:]

    if args and args[0] == "--worker":
        if len(args) < 2:
            raise ValueError(
                "--worker requires a script name"
            )

        return run_worker(
            args[1],
            args[2:],
        )

    from run_gui import main as gui_main

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
