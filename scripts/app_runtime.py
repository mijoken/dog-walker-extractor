from __future__ import annotations

import sys

from app_paths import scripts_dir


SCRIPTS = scripts_dir()


def is_frozen() -> bool:
    return bool(
        getattr(sys, "frozen", False)
    )


def build_script_command(
    script_name: str,
    *args: str,
) -> list[str]:
    script_path = (
        SCRIPTS
        / script_name
    )

    if not script_path.is_file():
        raise FileNotFoundError(
            script_path
        )

    if is_frozen():
        return [
            sys.executable,
            "--worker",
            script_name,
            *args,
        ]

    return [
        sys.executable,
        str(script_path),
        *args,
    ]
