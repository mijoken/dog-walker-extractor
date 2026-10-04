# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve()

datas = [
    (str(ROOT / "scripts"), "scripts"),
    (str(ROOT / "src"), "src"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "yolo11n.pt"), "."),
]

binaries = []
hiddenimports = []

for package in (
    "ultralytics",
    "imageio_ffmpeg",
    "torchvision",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package
    )

    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    ["scripts/app_entry.py"],
    pathex=[
        str(ROOT / "scripts"),
        str(ROOT / "src"),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)


exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dog Walker Extractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)


coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Dog Walker Extractor",
)
