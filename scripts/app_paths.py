from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "Dog Walker Extractor"


def is_frozen() -> bool:
    return bool(
        getattr(sys, "frozen", False)
    )


def resource_root() -> Path:
    if is_frozen():
        bundle_root = getattr(
            sys,
            "_MEIPASS",
            None,
        )

        if bundle_root is None:
            raise RuntimeError(
                "Frozen resource root is unavailable."
            )

        return Path(bundle_root)

    return Path(__file__).resolve().parents[1]


def scripts_dir() -> Path:
    return resource_root() / "scripts"


def assets_dir() -> Path:
    return resource_root() / "assets"


def source_dir() -> Path:
    return resource_root() / "src"


def model_path() -> Path:
    return resource_root() / "yolo11n.pt"


def user_data_root() -> Path:
    if not is_frozen():
        return (
            Path(__file__).resolve().parents[1]
            / "output"
        )

    local_app_data = os.environ.get(
        "LOCALAPPDATA"
    )

    if not local_app_data:
        raise RuntimeError(
            "LOCALAPPDATA is unavailable."
        )

    return (
        Path(local_app_data)
        / APP_NAME
    )


def default_output_dir() -> Path:
    return (
        user_data_root()
        / "output"
        / "app_runs"
        if is_frozen()
        else user_data_root()
        / "app_runs"
    )
