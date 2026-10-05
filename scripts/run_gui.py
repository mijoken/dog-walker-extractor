from __future__ import annotations

import cv2
import json
import hashlib
import os
import queue
import re
import subprocess
import sys
import threading
import winsound
from datetime import datetime

from app_paths import assets_dir, default_output_dir
from app_runtime import build_script_command
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


REPO = Path(__file__).resolve().parents[1]
ASSETS = assets_dir()
DEFAULT_OUTPUT = default_output_dir()

APP_NAME = "Dog Walker Extractor"
APP_VERSION = "0.3.0"
APP_AUTHOR = "Kentaro.M"
APP_EDITION = "BLUE HARBOR TOWER MINATOMIRAI Edition"

BG = "#F4F8FB"
CARD_BG = "#FFFFFF"
HEADER_BG = "#EAF4FB"
PRIMARY = "#1677C8"
PRIMARY_DARK = "#0F5D99"
TEXT = "#18364A"
MUTED = "#647B8B"
BORDER = "#D7E2EA"
SUCCESS = "#28A745"
ERROR = "#C0392B"


class DogWalkerApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title(APP_NAME)
        self.configure(bg=BG)

        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self.cancel_requested = False
        self.close_after_cancel = False

        self.last_batch_dir: Path | None = None
        self.current_run_dir: Path | None = None
        self.preview_path: Path | None = None

        self.logo_image = None
        self.preview_image = None

        self.input_var = tk.StringVar()
        self.input_mode_var = tk.StringVar(
            value="files"
        )
        self.selected_files: list[Path] = []
        self.input_summary_var = tk.StringVar(
            value="動画ファイルを選択してください"
        )
        self.output_var = tk.StringVar(
            value=str(DEFAULT_OUTPUT)
        )
        self.roi_var = tk.StringVar()

        self.status_var = tk.StringVar(
            value="待機中"
        )
        self.stage_var = tk.StringVar(
            value="解析は開始されていません"
        )
        self.progress_text_var = tk.StringVar(
            value="0%"
        )

        self.admin_visible = False
        self.preview_visible = True

        self.scan_total_frames = 0
        self.scan_stride = 5

        self.candidate_count = 0
        self.candidate_index = 0

        self._configure_style()
        self._build_ui()

        self.protocol(
            "WM_DELETE_WINDOW",
            self._on_window_close,
        )

        self._center_window(
            width=900,
            height=650,
        )

        self.minsize(
            780,
            560,
        )

        self.after(
            100,
            self._drain_log_queue,
        )

        self.after(
            700,
            self._poll_preview,
        )

    # ============================================================
    # Window / style
    # ============================================================

    def _center_window(
        self,
        *,
        width: int,
        height: int,
    ) -> None:
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()

        x = max(
            0,
            (screen_width - width) // 2,
        )

        y = max(
            0,
            (screen_height - height) // 2,
        )

        self.geometry(
            f"{width}x{height}+{x}+{y}"
        )

    def _configure_style(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        style.configure(
            "Compact.Horizontal.TProgressbar",
            thickness=13,
        )

    # ============================================================
    # UI
    # ============================================================

    def _build_ui(self) -> None:
        self._build_header()

        main = tk.Frame(
            self,
            bg=BG,
            padx=16,
            pady=12,
        )
        main.pack(
            fill=tk.BOTH,
            expand=True,
        )

        self._build_io_card(main)
        self._build_admin_card(main)
        self._build_action_card(main)
        self._build_work_card(main)
        self._build_footer()

    def _build_header(self) -> None:
        header = tk.Frame(
            self,
            bg=HEADER_BG,
            padx=18,
            pady=11,
        )
        header.pack(fill=tk.X)

        left = tk.Frame(
            header,
            bg=HEADER_BG,
        )
        left.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )

        tk.Label(
            left,
            text=APP_NAME,
            bg=HEADER_BG,
            fg=TEXT,
            font=(
                "Segoe UI",
                21,
                "bold",
            ),
        ).pack(
            anchor=tk.W,
        )

        badge = tk.Label(
            left,
            text=APP_EDITION,
            bg=PRIMARY,
            fg="white",
            padx=9,
            pady=2,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        )
        badge.pack(
            anchor=tk.W,
            pady=(5, 4),
        )

        tk.Label(
            left,
            text=(
                "動画ファイルまたはフォルダから、"
                "犬連れ歩行イベント候補を自動抽出します。"
            ),
            bg=HEADER_BG,
            fg=MUTED,
            font=(
                "Segoe UI",
                9,
            ),
        ).pack(
            anchor=tk.W,
        )

        right = tk.Frame(
            header,
            bg=HEADER_BG,
        )
        right.pack(
            side=tk.RIGHT,
            padx=(15, 0),
        )

        self.logo_label = tk.Label(
            right,
            text="🐕",
            bg=HEADER_BG,
            fg=PRIMARY_DARK,
            font=(
                "Segoe UI Emoji",
                26,
            ),
        )
        self.logo_label.pack()

        tk.Label(
            right,
            text=f"Created by {APP_AUTHOR}",
            bg=HEADER_BG,
            fg=PRIMARY_DARK,
            font=(
                "Yu Gothic UI",
                10,
                "bold",
            ),
        ).pack(
            pady=(2, 0),
        )

        tk.Label(
            right,
            text=f"Version {APP_VERSION}",
            bg=HEADER_BG,
            fg=MUTED,
            font=(
                "Segoe UI",
                8,
            ),
        ).pack()

        self._load_logo_if_available()

    def _build_io_card(
        self,
        parent,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=CARD_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=14,
            pady=10,
        )
        card.pack(
            fill=tk.X,
            pady=(0, 8),
        )

        tk.Label(
            card,
            text="入力・出力設定",
            bg=CARD_BG,
            fg=TEXT,
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).grid(
            row=0,
            column=0,
            sticky=tk.W,
            pady=(0, 3),
        )

        card.grid_columnconfigure(
            0,
            weight=0,
            minsize=240,
        )
        card.grid_columnconfigure(
            1,
            weight=1,
        )

        mode_frame = tk.Frame(
            card,
            bg=CARD_BG,
        )
        mode_frame.grid(
            row=1,
            column=0,
            sticky=tk.NW,
            padx=(0, 24),
        )

        tk.Label(
            mode_frame,
            text="入力方法",
            bg=CARD_BG,
            fg=TEXT,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
        ).pack(
            anchor=tk.W,
            pady=(0, 2),
        )

        tk.Radiobutton(
            mode_frame,
            text="動画ファイル",
            variable=self.input_mode_var,
            value="files",
            command=self._on_input_mode_changed,
            bg=CARD_BG,
            fg=TEXT,
        ).pack(
            anchor=tk.W,
        )

        tk.Radiobutton(
            mode_frame,
            text="フォルダ",
            variable=self.input_mode_var,
            value="folder",
            command=self._on_input_mode_changed,
            bg=CARD_BG,
            fg=TEXT,
        ).pack(
            anchor=tk.W,
        )

        paths_frame = tk.Frame(
            card,
            bg=CARD_BG,
        )
        paths_frame.grid(
            row=0,
            column=1,
            rowspan=2,
            sticky=tk.NSEW,
        )

        paths_frame.grid_columnconfigure(
            1,
            weight=1,
        )

        self._path_row(
            paths_frame,
            row=0,
            label="解析対象",
            variable=self.input_var,
            command=self._choose_input,
        )

        tk.Label(
            paths_frame,
            textvariable=self.input_summary_var,
            bg=CARD_BG,
            fg=MUTED,
            anchor="w",
        ).grid(
            row=1,
            column=1,
            columnspan=2,
            sticky=tk.W,
            pady=(1, 3),
        )

        self._path_row(
            paths_frame,
            row=2,
            label="保存先フォルダ",
            variable=self.output_var,
            command=self._choose_output,
        )

    def _build_admin_card(
        self,
        parent,
    ) -> None:
        self.admin_outer = tk.Frame(
            parent,
            bg=CARD_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.admin_outer.pack(
            fill=tk.X,
            pady=(0, 8),
        )

        self.admin_button = tk.Button(
            self.admin_outer,
            text="⚙  管理者向け設定  ▼",
            command=self._toggle_admin,
            bg=CARD_BG,
            fg=TEXT,
            activebackground="#F7FAFC",
            relief=tk.FLAT,
            anchor="w",
            padx=13,
            pady=7,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
            cursor="hand2",
        )
        self.admin_button.pack(
            fill=tk.X,
        )

        self.admin_frame = tk.Frame(
            self.admin_outer,
            bg=CARD_BG,
            padx=13,
            pady=7,
        )

        self._path_row(
            self.admin_frame,
            row=0,
            label="ROI profile",
            variable=self.roi_var,
            command=self._choose_roi,
        )

        tk.Label(
            self.admin_frame,
            text=(
                "固定カメラ導入後に使用する管理者向け設定です。"
                "通常は空欄で構いません。"
            ),
            bg=CARD_BG,
            fg=MUTED,
            font=(
                "Segoe UI",
                8,
            ),
        ).grid(
            row=1,
            column=1,
            columnspan=2,
            sticky=tk.W,
            pady=(0, 2),
        )

    def _build_action_card(
        self,
        parent,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=CARD_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=14,
            pady=10,
        )
        card.pack(
            fill=tk.X,
            pady=(0, 8),
        )

        top = tk.Frame(
            card,
            bg=CARD_BG,
        )
        top.pack(
            fill=tk.X,
        )

        self.start_button = tk.Button(
            top,
            text="▶  解析を開始",
            command=self._start_analysis,
            bg=PRIMARY,
            fg="white",
            activebackground=PRIMARY_DARK,
            activeforeground="white",
            disabledforeground="#D7E8F4",
            relief=tk.FLAT,
            padx=20,
            pady=7,
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
            cursor="hand2",
        )
        self.start_button.pack(
            side=tk.LEFT,
        )

        self.input_var.trace_add(
            "write",
            self._on_input_changed,
        )
        self._refresh_start_button_state()

        self.cancel_button = tk.Button(
            top,
            text="■  解析を中止",
            command=self._cancel_analysis,
            bg="#F7FAFC",
            fg=ERROR,
            disabledforeground="#B8C2C8",
            relief=tk.GROOVE,
            padx=13,
            pady=6,
            font=(
                "Segoe UI",
                9,
                "bold",
            ),
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.cancel_button.pack(
            side=tk.LEFT,
            padx=(9, 0),
        )

        self.open_button = tk.Button(
            top,
            text="結果フォルダを開く",
            command=self._open_results,
            bg="#F7FAFC",
            fg=TEXT,
            relief=tk.GROOVE,
            padx=13,
            pady=6,
            font=(
                "Segoe UI",
                9,
            ),
            state=tk.DISABLED,
            cursor="hand2",
        )
        self.open_button.pack(
            side=tk.LEFT,
            padx=(9, 0),
        )

        status_row = tk.Frame(
            card,
            bg=CARD_BG,
        )
        status_row.pack(
            fill=tk.X,
            pady=(9, 0),
        )

        self.status_dot = tk.Label(
            status_row,
            text="●",
            bg=CARD_BG,
            fg=SUCCESS,
            font=(
                "Segoe UI",
                11,
                "bold",
            ),
        )
        self.status_dot.pack(
            side=tk.LEFT,
        )

        tk.Label(
            status_row,
            textvariable=self.status_var,
            bg=CARD_BG,
            fg=TEXT,
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        ).pack(
            side=tk.LEFT,
            padx=(5, 10),
        )

        self.progress = ttk.Progressbar(
            status_row,
            mode="determinate",
            maximum=100,
            value=0,
            style="Compact.Horizontal.TProgressbar",
        )
        self.progress.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )

        tk.Label(
            status_row,
            textvariable=self.progress_text_var,
            bg=CARD_BG,
            fg=MUTED,
            width=5,
            font=(
                "Segoe UI",
                8,
                "bold",
            ),
        ).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )

        tk.Label(
            card,
            textvariable=self.stage_var,
            bg=CARD_BG,
            fg=MUTED,
            font=(
                "Segoe UI",
                8,
            ),
        ).pack(
            anchor=tk.W,
            pady=(4, 0),
        )

    def _build_work_card(
        self,
        parent,
    ) -> None:
        card = tk.Frame(
            parent,
            bg=CARD_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=8,
        )
        card.pack(
            fill=tk.BOTH,
            expand=True,
        )

        head = tk.Frame(
            card,
            bg=CARD_BG,
        )
        head.pack(
            fill=tk.X,
            pady=(0, 6),
        )

        self.work_title = tk.Label(
            head,
            text="解析モニター",
            bg=CARD_BG,
            fg=TEXT,
            font=(
                "Segoe UI",
                10,
                "bold",
            ),
        )
        self.work_title.pack(
            side=tk.LEFT,
        )

        self.clear_log_button = tk.Button(
            head,
            text="ログをクリア",
            command=self._clear_log,
            bg="#F7FAFC",
            fg=MUTED,
            relief=tk.FLAT,
            font=(
                "Segoe UI",
                8,
            ),
            cursor="hand2",
        )
        self.clear_log_button.pack(
            side=tk.RIGHT,
        )

        self.preview_toggle_button = tk.Button(
            head,
            text="プレビュー非表示",
            command=self._toggle_preview,
            bg="#F7FAFC",
            fg=PRIMARY_DARK,
            relief=tk.FLAT,
            font=(
                "Segoe UI",
                8,
                "bold",
            ),
            cursor="hand2",
        )
        self.preview_toggle_button.pack(
            side=tk.RIGHT,
            padx=(0, 8),
        )

        self.work_body = tk.Frame(
            card,
            bg=CARD_BG,
        )
        self.work_body.pack(
            fill=tk.BOTH,
            expand=True,
        )

        self.preview_frame = tk.Frame(
            self.work_body,
            bg="#F5F8FA",
            highlightthickness=1,
            highlightbackground=BORDER,
            width=360,
        )
        self.preview_frame.pack(
            side=tk.LEFT,
            fill=tk.Y,
            padx=(0, 8),
        )
        self.preview_frame.pack_propagate(False)

        tk.Label(
            self.preview_frame,
            text="プレビュー",
            bg="#F5F8FA",
            fg=MUTED,
            font=(
                "Segoe UI",
                8,
                "bold",
            ),
        ).pack(
            anchor=tk.W,
            padx=8,
            pady=(7, 3),
        )

        self.preview_label = tk.Label(
            self.preview_frame,
            text=(
                "プレビュー待機中\n\n"
                "粗スキャン開始後に\n"
                "低頻度で更新されます"
            ),
            bg="#F5F8FA",
            fg=MUTED,
            justify=tk.CENTER,
            font=(
                "Segoe UI",
                9,
            ),
        )
        self.preview_label.pack(
            fill=tk.BOTH,
            expand=True,
            padx=6,
            pady=(0, 6),
        )

        self.log_frame = tk.Frame(
            self.work_body,
            bg=CARD_BG,
        )
        self.log_frame.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True,
        )

        self.log_text = tk.Text(
            self.log_frame,
            wrap="word",
            font=(
                "Consolas",
                8,
            ),
            bg="#FBFCFD",
            fg="#263746",
            relief=tk.FLAT,
            padx=8,
            pady=7,
        )
        self.log_text.pack(
            side=tk.LEFT,
            fill=tk.BOTH,
            expand=True,
        )

        scrollbar = ttk.Scrollbar(
            self.log_frame,
            orient=tk.VERTICAL,
            command=self.log_text.yview,
        )
        scrollbar.pack(
            side=tk.RIGHT,
            fill=tk.Y,
        )

        self.log_text.configure(
            yscrollcommand=scrollbar.set,
        )

    def _build_footer(self) -> None:
        footer = tk.Frame(
            self,
            bg="#EEF3F7",
            padx=16,
            pady=5,
        )
        footer.pack(
            fill=tk.X,
        )

        tk.Label(
            footer,
            text=(
                f"{APP_NAME}  |  "
                f"Version {APP_VERSION}"
            ),
            bg="#EEF3F7",
            fg=MUTED,
            font=(
                "Segoe UI",
                8,
            ),
        ).pack(
            side=tk.LEFT,
        )

    # ============================================================
    # Generic controls
    # ============================================================

    def _path_row(
        self,
        parent,
        *,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> None:
        tk.Label(
            parent,
            text=label,
            bg=CARD_BG,
            fg=TEXT,
            font=(
                "Segoe UI",
                8,
                "bold",
            ),
        ).grid(
            row=row,
            column=0,
            sticky=tk.W,
            padx=(0, 10),
            pady=4,
        )

        entry = ttk.Entry(
            parent,
            textvariable=variable,
        )
        entry.grid(
            row=row,
            column=1,
            sticky="ew",
            pady=4,
        )

        tk.Button(
            parent,
            text="選択...",
            command=command,
            bg="#F4F8FB",
            fg=TEXT,
            relief=tk.GROOVE,
            padx=10,
            pady=2,
            cursor="hand2",
        ).grid(
            row=row,
            column=2,
            padx=(8, 0),
            pady=4,
        )

        parent.columnconfigure(
            1,
            weight=1,
        )

    def _toggle_admin(self) -> None:
        if self.admin_visible:
            self.admin_frame.pack_forget()
            self.admin_button.configure(
                text="⚙  管理者向け設定  ▼"
            )
            self.admin_visible = False
        else:
            self.admin_frame.pack(
                fill=tk.X,
            )
            self.admin_button.configure(
                text="⚙  管理者向け設定  ▲"
            )
            self.admin_visible = True

    def _toggle_preview(self) -> None:
        if self.preview_visible:
            self.preview_frame.pack_forget()

            self.preview_toggle_button.configure(
                text="プレビュー表示"
            )

            self.work_title.configure(
                text="実行ログ"
            )

            self.preview_visible = False

        else:
            self.preview_frame.pack(
                side=tk.LEFT,
                fill=tk.Y,
                padx=(0, 8),
                before=self.log_frame,
            )

            self.preview_toggle_button.configure(
                text="プレビュー非表示"
            )

            self.work_title.configure(
                text="解析モニター"
            )

            self.preview_visible = True

    def _on_input_changed(
        self,
        *_args,
    ) -> None:
        self._refresh_start_button_state()

    def _refresh_start_button_state(self) -> None:
        if not hasattr(
            self,
            "start_button",
        ):
            return

        if self.process is not None:
            self.start_button.configure(
                state=tk.DISABLED,
            )
            return

        input_text = (
            self.input_var
            .get()
            .strip()
        )

        if not input_text:
            self.start_button.configure(
                state=tk.DISABLED,
            )
            return

        if self.input_mode_var.get() == "files":
            valid_input = bool(
                self.selected_files
            ) and all(
                path.exists()
                and path.is_file()
                for path in self.selected_files
            )
        else:
            input_path = Path(
                input_text
            )
            valid_input = (
                input_path.exists()
                and input_path.is_dir()
            )

        self.start_button.configure(
            state=(
                tk.NORMAL
                if valid_input
                else tk.DISABLED
            ),
        )

    def _on_input_mode_changed(self) -> None:
        self.selected_files = []
        self.input_var.set("")

        if self.input_mode_var.get() == "files":
            self.input_summary_var.set(
                "動画ファイルを選択してください"
            )
        else:
            self.input_summary_var.set(
                "動画フォルダを選択してください"
            )

        self._refresh_start_button_state()

    @staticmethod
    def _video_duration_seconds(
        video_path: Path,
    ) -> float | None:
        capture = cv2.VideoCapture(
            str(video_path)
        )

        try:
            if not capture.isOpened():
                return None

            fps = capture.get(
                cv2.CAP_PROP_FPS
            )
            frame_count = capture.get(
                cv2.CAP_PROP_FRAME_COUNT
            )

            if fps <= 0 or frame_count < 0:
                return None

            return frame_count / fps
        finally:
            capture.release()

    @staticmethod
    def _format_duration(
        total_seconds: float,
    ) -> str:
        seconds = max(
            0,
            int(round(total_seconds)),
        )

        hours, remainder = divmod(
            seconds,
            3600,
        )
        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours:
            return (
                f"{hours}時間"
                f"{minutes:02d}分"
                f"{seconds:02d}秒"
            )

        return (
            f"{minutes}分"
            f"{seconds:02d}秒"
        )

    def _choose_input(self) -> None:
        if self.input_mode_var.get() == "files":
            paths = filedialog.askopenfilenames(
                title="解析する動画ファイルを選択",
                filetypes=[
                    (
                        "Video files",
                        (
                            "*.mp4",
                            "*.mov",
                            "*.avi",
                            "*.mkv",
                            "*.mts",
                            "*.m2ts",
                        ),
                    ),
                    ("All files", "*.*"),
                ],
            )

            if paths:
                self.selected_files = [
                    Path(path).resolve()
                    for path in paths
                ]

                if len(self.selected_files) == 1:
                    self.input_var.set(
                        str(self.selected_files[0])
                    )
                else:
                    self.input_var.set(
                        f"{len(self.selected_files)}個の動画ファイル"
                    )

                durations = [
                    self._video_duration_seconds(
                        video_path
                    )
                    for video_path
                    in self.selected_files
                ]

                known_durations = [
                    duration
                    for duration in durations
                    if duration is not None
                ]

                if (
                    known_durations
                    and len(known_durations)
                    == len(self.selected_files)
                ):
                    total_duration = sum(
                        known_durations
                    )

                    self.input_summary_var.set(
                        (
                            f"選択動画数："
                            f"{len(self.selected_files)}本"
                            " ｜ 合計再生時間："
                            f"{self._format_duration(total_duration)}"
                        )
                    )
                else:
                    self.input_summary_var.set(
                        (
                            f"選択動画数："
                            f"{len(self.selected_files)}本"
                            " ｜ 合計再生時間：取得できません"
                        )
                    )

        else:
            path = filedialog.askdirectory(
                title="SDカードまたは動画フォルダを選択",
            )

            if path:
                self.selected_files = []
                self.input_var.set(path)
                self.input_summary_var.set(
                    "フォルダ一括処理"
                )

        self._refresh_start_button_state()

    def _choose_output(self) -> None:
        path = filedialog.askdirectory(
            title="保存先フォルダを選択",
        )

        if path:
            self.output_var.set(path)

    def _choose_roi(self) -> None:
        path = filedialog.askopenfilename(
            title="ROI profile JSONを選択",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.roi_var.set(path)

    def _clear_log(self) -> None:
        self.log_text.delete(
            "1.0",
            tk.END,
        )

    # ============================================================
    # Logo / preview
    # ============================================================

    def _load_logo_if_available(self) -> None:
        logo_path = (
            ASSETS
            / "dog_logo.png"
        )

        if not logo_path.exists():
            return

        try:
            image = tk.PhotoImage(
                file=str(logo_path)
            )

            max_size = 72

            factor = max(
                1,
                max(
                    image.width() // max_size,
                    image.height() // max_size,
                ),
            )

            if factor > 1:
                image = image.subsample(
                    factor,
                    factor,
                )

            self.logo_image = image

            self.logo_label.configure(
                image=self.logo_image,
                text="",
            )

        except Exception:
            pass

    def _poll_preview(self) -> None:
        try:
            path = self.preview_path

            if (
                self.preview_visible
                and path is not None
                and path.exists()
            ):
                image = tk.PhotoImage(
                    file=str(path)
                )

                self.preview_image = image

                self.preview_label.configure(
                    image=self.preview_image,
                    text="",
                )

        except Exception:
            pass

        self.after(
            700,
            self._poll_preview,
        )

    # ============================================================
    # Log / progress parser
    # ============================================================

    def _append_log(
        self,
        text: str,
    ) -> None:
        self.log_text.insert(
            tk.END,
            text,
        )

        self.log_text.see(
            tk.END,
        )

    def _set_stage(
        self,
        stage: str,
    ) -> None:
        self.stage_var.set(
            stage
        )

    def _set_progress(
        self,
        value: float,
    ) -> None:
        value = max(
            0.0,
            min(
                100.0,
                float(value),
            ),
        )

        self.progress.configure(
            value=value,
        )

        self.progress_text_var.set(
            f"{value:.0f}%"
        )

    def _handle_runtime_line(
        self,
        line: str,
    ) -> None:
        text = line.strip()

        if not text:
            return

        # --------------------------------------------------------
        # Resolve the active per-video output directory.
        # --------------------------------------------------------

        if text.startswith("GUI_RUN_DIR:"):
            value = text.partition(":")[2].strip()

            if value:
                self.current_run_dir = Path(
                    value
                )

                self.preview_path = (
                    self.current_run_dir
                    / "dog_scan"
                    / "preview"
                    / "latest.png"
                )

                self.preview_label.configure(
                    image="",
                    text=(
                        "粗スキャン開始待ち\n\n"
                        "プレビューは低頻度で更新されます"
                    ),
                )

            return

        if text.startswith(
            "output root    :"
        ):
            value = text.partition(":")[2].strip()

            if value:
                self.current_run_dir = Path(
                    value
                )

                self.preview_path = (
                    self.current_run_dir
                    / "dog_scan"
                    / "preview"
                    / "latest.png"
                )

                self.preview_label.configure(
                    image="",
                    text=(
                        "粗スキャン開始待ち\n\n"
                        "プレビューは低頻度で更新されます"
                    ),
                )

            return

        # --------------------------------------------------------
        # Stage detection
        # --------------------------------------------------------

        if "STAGE 1 -" in text:
            self._set_stage(
                "粗スキャン"
            )
            self._set_progress(0)
            return

        if "STAGE 2 -" in text:
            self._set_stage(
                "候補精密解析"
            )
            self._set_progress(0)
            return

        if "STAGE 3 -" in text:
            self._set_stage(
                "トラック品質確認"
            )
            return

        if "STAGE 4/5 -" in text:
            self._set_stage(
                "犬散歩イベント判定"
            )
            return

        if text.startswith(
            "CREATE REVIEW CLIP EVENT"
        ):
            self._set_stage(
                "確認動画を作成中"
            )
            return

        # --------------------------------------------------------
        # Coarse-scan metadata
        # --------------------------------------------------------

        match = re.match(
            r"frames\s*:\s*(\d+)",
            text,
        )

        if match:
            self.scan_total_frames = int(
                match.group(1)
            )
            return

        match = re.match(
            r"stride\s*:\s*(\d+)",
            text,
        )

        if match:
            self.scan_stride = max(
                1,
                int(match.group(1)),
            )
            return

        match = re.search(
            r"analyzed=(\d+)",
            text,
        )

        if (
            match
            and self.scan_total_frames > 0
        ):
            analyzed = int(
                match.group(1)
            )

            source_frames = (
                analyzed
                * self.scan_stride
            )

            percent = (
                source_frames
                / self.scan_total_frames
                * 100.0
            )

            self._set_stage(
                "粗スキャン"
            )

            self._set_progress(
                percent
            )

            return

        # --------------------------------------------------------
        # Candidate metadata
        # --------------------------------------------------------

        match = re.search(
            r"candidate windows\s*:\s*(\d+)",
            text,
            re.IGNORECASE,
        )

        if match:
            self.candidate_count = int(
                match.group(1)
            )
            return

        match = re.search(
            r"===== CANDIDATE\s+(\d+)",
            text,
        )

        if match:
            self.candidate_index = int(
                match.group(1)
            )

            if self.candidate_count:
                self._set_stage(
                    (
                        "候補精密解析 "
                        f"{self.candidate_index}"
                        f"/{self.candidate_count}"
                    )
                )

            return

        match = re.search(
            r"processed=(\d+)/(\d+)",
            text,
        )

        if (
            match
            and self.candidate_count > 0
            and self.candidate_index > 0
        ):
            processed = int(
                match.group(1)
            )

            total = max(
                1,
                int(match.group(2)),
            )

            within = (
                processed
                / total
            )

            overall = (
                (
                    self.candidate_index
                    - 1
                    + within
                )
                / self.candidate_count
                * 100.0
            )

            self._set_stage(
                (
                    "候補精密解析 "
                    f"{self.candidate_index}"
                    f"/{self.candidate_count}"
                )
            )

            self._set_progress(
                overall
            )

    def _drain_log_queue(self) -> None:
        try:
            while True:
                line = (
                    self.log_queue
                    .get_nowait()
                )

                self._handle_runtime_line(
                    line
                )

                self._append_log(
                    line
                )

        except queue.Empty:
            pass

        self.after(
            100,
            self._drain_log_queue,
        )

    # ============================================================
    # Resume
    # ============================================================

    def _find_resume_candidate(
        self,
        *,
        input_dir: Path,
        output_dir: Path,
    ) -> Path | None:
        if not output_dir.exists():
            return None

        try:
            input_resolved = input_dir.resolve()
        except OSError:
            input_resolved = input_dir

        candidates = []

        for batch_dir in output_dir.iterdir():
            if not batch_dir.is_dir():
                continue

            state_path = (
                batch_dir
                / "batch_state.json"
            )

            if not state_path.is_file():
                continue

            try:
                state = json.loads(
                    state_path.read_text(
                        encoding="utf-8"
                    )
                )
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
            ):
                continue

            if state.get("schema_version") != 1:
                continue

            if state.get("status") == "completed":
                continue

            source_root = state.get(
                "source_root"
            )

            if not isinstance(
                source_root,
                str,
            ):
                continue

            try:
                stored_root = Path(
                    source_root
                ).resolve()
            except OSError:
                stored_root = Path(
                    source_root
                )

            if stored_root != input_resolved:
                stored_videos = state.get(
                    "videos"
                )

                if not isinstance(
                    stored_videos,
                    list,
                ):
                    continue

                if not all(
                    isinstance(item, dict)
                    for item in stored_videos
                ):
                    continue

                current_videos = []

                for path in input_dir.rglob("*"):
                    if (
                        path.is_file()
                        and path.suffix.lower()
                        in {
                            ".mp4",
                            ".mov",
                            ".avi",
                            ".mkv",
                            ".mts",
                            ".m2ts",
                        }
                    ):
                        current_videos.append(
                            path.resolve()
                        )

                current_videos.sort(
                    key=lambda item: str(
                        item
                    ).lower()
                )

                current_plan = []

                for index, video in enumerate(
                    current_videos,
                    start=1,
                ):
                    relative = video.relative_to(
                        input_resolved
                    )

                    safe_stem = re.sub(
                        r"[^A-Za-z0-9._-]+",
                        "_",
                        video.stem,
                    )

                    safe_stem = safe_stem.strip(
                        "._-"
                    )

                    if not safe_stem:
                        safe_stem = "video"

                    short_hash = hashlib.sha1(
                        str(relative).encode(
                            "utf-8",
                            errors="replace",
                        )
                    ).hexdigest()[:8]

                    identifier = (
                        f"{index:04d}_"
                        f"{safe_stem}_"
                        f"{short_hash}"
                    )

                    current_plan.append(
                        {
                            "identifier":
                                identifier,
                            "relative_path":
                                str(relative),
                        }
                    )

                stored_plan = [
                    {
                        "identifier":
                            item.get(
                                "identifier"
                            ),
                        "relative_path":
                            item.get(
                                "relative_path"
                            ),
                    }
                    for item in stored_videos
                ]

                if stored_plan != current_plan:
                    continue

            updated_at = state.get(
                "updated_at"
            )

            if not isinstance(
                updated_at,
                str,
            ):
                updated_at = ""

            candidates.append(
                (
                    updated_at,
                    batch_dir,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return candidates[0][1]

    def _ask_resume_choice(self, batch_dir: Path):
        dialog = tk.Toplevel(self)
        dialog.title('未完了の解析があります')
        dialog.transient(self)
        dialog.resizable(False, False)
        result = {'value': None}

        def finish(value):
            result['value'] = value
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
        dialog.protocol('WM_DELETE_WINDOW', lambda: finish(None))
        outer = ttk.Frame(dialog, padding=(28, 24, 28, 22))
        outer.pack(fill='both', expand=True)
        title = ttk.Label(outer, text='未完了の解析があります', font=('Yu Gothic UI', 16, 'bold'))
        title.pack(anchor='w')
        message = ttk.Label(outer, text='前回完了していない解析が見つかりました。\n続きから再開しますか？', font=('Yu Gothic UI', 11), justify='left')
        message.pack(anchor='w', pady=(14, 18))
        info = ttk.LabelFrame(outer, text=' 対象 ', padding=(14, 10))
        info.pack(fill='x')
        batch_label = ttk.Label(info, text=batch_dir.name, font=('Yu Gothic UI', 12, 'bold'))
        batch_label.pack(anchor='w')
        path_label = ttk.Label(info, text=str(batch_dir), font=('Yu Gothic UI', 9), foreground='#5f6b76', wraplength=500, justify='left')
        path_label.pack(anchor='w', pady=(6, 0))
        explanation = ttk.Label(outer, text='「続きから再開」では、完了済みの動画を再利用し、未完了の動画から処理します。', font=('Yu Gothic UI', 9), foreground='#5f6b76', wraplength=500, justify='left')
        explanation.pack(anchor='w', pady=(14, 18))
        buttons = ttk.Frame(outer)
        buttons.pack(fill='x')

        resume_style = ttk.Style(dialog)
        resume_style.configure(
            'ResumeDialog.TButton',
            font=('Yu Gothic UI', 10),
            padding=(12, 8),
        )
        cancel_button = ttk.Button(
            buttons,
            text='キャンセル',
            command=lambda: finish(None),
            width=14,
            style='ResumeDialog.TButton',
        )
        cancel_button.pack(side='right')
        new_button = ttk.Button(
            buttons,
            text='最初から解析',
            command=lambda: finish(False),
            width=16,
            style='ResumeDialog.TButton',
        )
        new_button.pack(side='right', padx=(0, 10))
        resume_button = ttk.Button(
            buttons,
            text='▶ 続きから再開',
            command=lambda: finish(True),
            width=18,
            style='ResumeDialog.TButton',
        )
        resume_button.pack(side='right', padx=(0, 10))
        dialog.update_idletasks()
        width = 600
        height = 360
        root_x = self.winfo_rootx()
        root_y = self.winfo_rooty()
        root_w = self.winfo_width()
        root_h = self.winfo_height()
        x = root_x + max(0, (root_w - width) // 2)
        y = root_y + max(0, (root_h - height) // 2)
        dialog.geometry(f'{width}x{height}+{x}+{y}')
        dialog.minsize(width, height)
        dialog.grab_set()
        resume_button.focus_set()
        dialog.bind('<Escape>', lambda event: finish(None))
        self.wait_window(dialog)
        return result['value']

    # ============================================================
    # Analysis
    # ============================================================

    def _start_analysis(self) -> None:
        if self.process is not None:
            messagebox.showinfo(
                "実行中",
                "現在解析中です。",
            )
            return

        input_text = (
            self.input_var
            .get()
            .strip()
        )

        output_text = (
            self.output_var
            .get()
            .strip()
        )

        roi_text = (
            self.roi_var
            .get()
            .strip()
        )

        if not input_text:
            messagebox.showerror(
                "入力エラー",
                (
                    "SDカードまたは動画フォルダを"
                    "選択してください。"
                ),
            )
            return

        if not output_text:
            messagebox.showerror(
                "入力エラー",
                "保存先フォルダを選択してください。",
            )
            return

        input_mode = self.input_mode_var.get()

        input_dir = None

        if input_mode == "files":
            if not self.selected_files:
                messagebox.showerror(
                    "入力エラー",
                    "解析する動画ファイルを選択してください。",
                )
                return

            for video_path in self.selected_files:
                if (
                    not video_path.exists()
                    or not video_path.is_file()
                ):
                    messagebox.showerror(
                        "入力エラー",
                        (
                            "選択した動画ファイルが"
                            "見つかりません。\n"
                            f"{video_path}"
                        ),
                    )
                    return
        else:
            input_dir = Path(
                input_text
            )

            if not input_dir.exists():
                messagebox.showerror(
                    "入力エラー",
                    "指定した入力フォルダが存在しません。",
                )
                return

            if not input_dir.is_dir():
                messagebox.showerror(
                    "入力エラー",
                    "入力先はフォルダを指定してください。",
                )
                return

        output_dir = Path(
            output_text
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        resume_batch = None

        if input_mode == "folder":
            resume_candidate = (
                self._find_resume_candidate(
                    input_dir=input_dir,
                    output_dir=output_dir,
                )
            )

            if resume_candidate is not None:
                resume_choice = (
                    self._ask_resume_choice(
                        resume_candidate
                    )
                )

                if resume_choice is None:
                    return

                if resume_choice:
                    resume_batch = (
                        resume_candidate
                    )

        batch_id = (
            datetime.now()
            .strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        if resume_batch is not None:
            batch_id = resume_batch.name

        self.last_batch_dir = (
            output_dir
            / batch_id
        )

        self.current_run_dir = None
        self.preview_path = None

        self.scan_total_frames = 0
        self.scan_stride = 5
        self.candidate_count = 0
        self.candidate_index = 0

        cmd = build_script_command(
            "run_folder_pipeline.py"
        )

        if input_mode == "files":
            self.last_batch_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            manifest_path = (
                self.last_batch_dir
                / "input_manifest.json"
            )

            manifest = {
                "schema_version": 2,
                "input_mode": "files",
                "files": [
                    {
                        "entry_id": f"item-{index:04d}",
                        "logical_path": (
                            video_path.name
                        ),
                        "source_path": str(
                            video_path
                        ),
                    }
                    for index, video_path
                    in enumerate(
                        self.selected_files,
                        start=1,
                    )
                ],
            }

            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            cmd.extend([
                "--input-manifest",
                str(manifest_path),
            ])
        else:
            cmd.extend([
                "--input",
                str(input_dir),
            ])

        cmd.extend([
            "--output",
            str(output_dir),
            "--batch-id",
            batch_id,
            "--continue-on-error",
        ])

        if resume_batch is not None:
            cmd.extend([
                "--resume-batch",
                str(resume_batch),
            ])

        if roi_text:
            roi_path = Path(
                roi_text
            )

            if not roi_path.exists():
                messagebox.showerror(
                    "ROIエラー",
                    "ROI profile が存在しません。",
                )
                return

            cmd.extend([
                "--roi-profile",
                str(roi_path),
            ])

        self.cancel_requested = False
        self.close_after_cancel = False

        self._clear_log()

        self.preview_label.configure(
            image="",
            text=(
                "プレビュー待機中\n\n"
                "粗スキャン開始後に\n"
                "低頻度で更新されます"
            ),
        )

        self.status_var.set(
            "解析中"
        )

        self.stage_var.set(
            "開始準備中"
        )

        self.status_dot.configure(
            fg=PRIMARY
        )

        self._set_progress(0)

        self.start_button.configure(
            state=tk.DISABLED,
        )

        self.cancel_button.configure(
            state=tk.NORMAL,
        )

        self.clear_log_button.configure(
            state=tk.DISABLED,
        )

        self.open_button.configure(
            state=tk.DISABLED,
        )

        if resume_batch is not None:
            self._append_log(
                "前回の未完了解析を続きから再開します。\n"
                f"Resume batch: {resume_batch}\n\n"
            )
        else:
            self._append_log(
                "解析を開始します。\n\n"
            )

        thread = threading.Thread(
            target=self._run_process,
            args=(cmd,),
            daemon=True,
        )

        thread.start()

    def _run_process(
        self,
        cmd: list[str],
    ) -> None:
        try:
            child_env = os.environ.copy()
            child_env["PYTHONUNBUFFERED"] = "1"

            self.process = subprocess.Popen(
                cmd,
                cwd=REPO,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=child_env,
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )

            assert (
                self.process.stdout
                is not None
            )

            if self.cancel_requested:
                self._terminate_process_tree(
                    self.process.pid
                )

            for line in (
                self.process.stdout
            ):
                self.log_queue.put(
                    line
                )

            rc = self.process.wait()

            if self.cancel_requested:
                self.after(
                    0,
                    self._finish_cancelled,
                )
                return

            if rc != 0:
                self.after(
                    0,
                    lambda:
                    self._finish_failed(
                        rc
                    ),
                )
                return

            self.after(
                0,
                self._finish_success,
            )

        except Exception as exc:
            if self.cancel_requested:
                self.after(
                    0,
                    self._finish_cancelled,
                )
            else:
                self.log_queue.put(
                    f"\nERROR: {exc}\n"
                )

                self.after(
                    0,
                    lambda:
                    self._finish_failed(
                        -1
                    ),
                )

        finally:
            self.process = None

    def _terminate_process_tree(
        self,
        pid: int,
    ) -> None:
        try:
            result = subprocess.run(
                [
                    "taskkill",
                    "/PID",
                    str(pid),
                    "/T",
                    "/F",
                ],
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                ),
            )

            if result.stdout.strip():
                self.log_queue.put(
                    result.stdout.strip()
                    + "\n"
                )

            if (
                result.returncode != 0
                and result.stderr.strip()
            ):
                self.log_queue.put(
                    "taskkill: "
                    + result.stderr.strip()
                    + "\n"
                )

        except Exception as exc:
            self.log_queue.put(
                "プロセス停止処理エラー: "
                f"{exc}\n"
            )

            process = self.process

            if (
                process is not None
                and process.poll() is None
            ):
                try:
                    process.terminate()
                except Exception:
                    pass

    def _cancel_analysis(self) -> None:
        if self.cancel_requested:
            return

        process = self.process

        if (
            process is not None
            and process.poll() is not None
        ):
            return

        confirmed = messagebox.askyesno(
            "解析を中止",
            (
                "現在の解析を中止しますか？\n\n"
                "完了済み・途中生成された解析データは"
                "削除しません。"
            ),
        )

        if not confirmed:
            return

        self.cancel_requested = True

        self.cancel_button.configure(
            state=tk.DISABLED,
        )

        self.status_var.set(
            "中止処理中"
        )

        self.stage_var.set(
            "解析を停止しています..."
        )

        self.status_dot.configure(
            fg=ERROR
        )

        self._append_log(
            "\nユーザー操作により解析の中止を要求しました。\n"
        )

        process = self.process

        if (
            process is not None
            and process.poll() is None
        ):
            threading.Thread(
                target=self._terminate_process_tree,
                args=(process.pid,),
                daemon=True,
            ).start()

    def _on_window_close(self) -> None:
        process = self.process

        analysis_active = (
            (
                process is not None
                and process.poll() is None
            )
            or (
                hasattr(
                    self,
                    "cancel_button",
                )
                and str(
                    self.cancel_button.cget(
                        "state"
                    )
                ) == str(tk.NORMAL)
            )
        )

        if not analysis_active:
            self.destroy()
            return

        confirmed = messagebox.askyesno(
            "解析中",
            (
                "現在解析中です。\n\n"
                "解析を中止してアプリを終了しますか？"
            ),
        )

        if not confirmed:
            return

        self.close_after_cancel = True
        self.cancel_requested = True

        self.cancel_button.configure(
            state=tk.DISABLED,
        )

        self.status_var.set(
            "終了処理中"
        )

        self.stage_var.set(
            "解析を停止しています..."
        )

        process = self.process

        if (
            process is not None
            and process.poll() is None
        ):
            threading.Thread(
                target=self._terminate_process_tree,
                args=(process.pid,),
                daemon=True,
            ).start()

    def _finish_cancelled(self) -> None:
        if self.close_after_cancel:
            self.destroy()
            return

        self.status_var.set(
            "中止済み"
        )

        self.stage_var.set(
            "解析はユーザー操作により中止されました"
        )

        self.status_dot.configure(
            fg=ERROR
        )

        self.cancel_button.configure(
            state=tk.DISABLED,
        )

        self.cancel_button.configure(
            state=tk.DISABLED,
        )

        self.clear_log_button.configure(
            state=tk.NORMAL,
        )

        self._refresh_start_button_state()

        if (
            self.last_batch_dir
            and self.last_batch_dir.exists()
        ):
            self.open_button.configure(
                state=tk.NORMAL,
            )

        self._append_log(
            "\n解析を中止しました。"
            "生成済みデータは保持されています。\n"
        )

    @staticmethod
    def _play_completion_chime() -> None:
        try:
            sound_path = ASSETS / "completion_chime.wav"

            if not sound_path.is_file():
                return

            winsound.PlaySound(
                str(sound_path),
                winsound.SND_FILENAME
                | winsound.SND_ASYNC,
            )
        except Exception:
            pass

    def _finish_success(self) -> None:
        self.status_var.set(
            "完了"
        )

        self.stage_var.set(
            "解析が完了しました"
        )

        self.status_dot.configure(
            fg=SUCCESS
        )

        self._set_progress(
            100
        )

        summary = None

        if self.last_batch_dir:
            path = (
                self.last_batch_dir
                / "batch_summary.json"
            )

            if path.exists():
                try:
                    summary = json.loads(
                        path.read_text(
                            encoding="utf-8-sig"
                        )
                    )
                except Exception:
                    summary = None

        if summary:
            videos = summary.get(
                "video_count",
                0,
            )

            successful = summary.get(
                "successful_video_count",
                0,
            )

            failed = summary.get(
                "failed_video_count",
                0,
            )

            events = summary.get(
                "total_dog_walker_events",
                0,
            )

        else:
            videos = None
            successful = None
            failed = None
            events = None

        self.cancel_button.configure(
            state=tk.DISABLED,
        )

        self.clear_log_button.configure(
            state=tk.NORMAL,
        )

        self._refresh_start_button_state()

        self.open_button.configure(
            state=tk.NORMAL,
        )

        threading.Thread(
            target=self._play_completion_chime,
            daemon=True,
        ).start()

        self._show_completion_dialog(
            videos=videos,
            successful=successful,
            failed=failed,
            events=events,
        )

    def _show_completion_dialog(
        self,
        *,
        videos,
        successful,
        failed,
        events,
    ) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("解析完了")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(bg="white")

        width = 560
        height = 390

        self.update_idletasks()

        x = (
            self.winfo_rootx()
            + max(
                0,
                (
                    self.winfo_width()
                    - width
                ) // 2,
            )
        )

        y = (
            self.winfo_rooty()
            + max(
                0,
                (
                    self.winfo_height()
                    - height
                ) // 2,
            )
        )

        dialog.geometry(
            f"{width}x{height}+{x}+{y}"
        )

        dialog.grab_set()

        body = tk.Frame(
            dialog,
            bg="white",
            padx=30,
            pady=24,
        )
        body.pack(
            fill=tk.BOTH,
            expand=True,
        )

        header = tk.Frame(
            body,
            bg="white",
        )
        header.pack(
            fill=tk.X,
        )

        tk.Label(
            header,
            text="✓",
            font=(
                "Segoe UI",
                28,
                "bold",
            ),
            fg=SUCCESS,
            bg="white",
        ).pack(
            side=tk.LEFT,
            padx=(0, 14),
        )

        title_area = tk.Frame(
            header,
            bg="white",
        )
        title_area.pack(
            side=tk.LEFT,
            fill=tk.X,
            expand=True,
        )

        tk.Label(
            title_area,
            text="解析が完了しました",
            font=(
                "Yu Gothic UI",
                16,
                "bold",
            ),
            fg=TEXT,
            bg="white",
            anchor="w",
        ).pack(
            anchor="w",
        )

        tk.Label(
            title_area,
            text="すべての動画の解析が終了しました。",
            font=(
                "Yu Gothic UI",
                9,
            ),
            fg=MUTED,
            bg="white",
            anchor="w",
        ).pack(
            anchor="w",
            pady=(3, 0),
        )

        result_box = tk.Frame(
            body,
            bg="#F5F9FC",
            highlightthickness=1,
            highlightbackground="#D6E2EA",
            padx=20,
            pady=14,
        )
        result_box.pack(
            fill=tk.X,
            pady=(20, 14),
        )

        if videos is not None:
            stats = tk.Frame(
                result_box,
                bg="#F5F9FC",
            )
            stats.pack(
                fill=tk.X,
            )

            items = (
                ("動画数", f"{videos}本"),
                ("正常終了", f"{successful}本"),
                ("エラー", f"{failed}本"),
            )

            for label_text, value_text in items:
                row = tk.Frame(
                    stats,
                    bg="#F5F9FC",
                )
                row.pack(
                    fill=tk.X,
                    pady=1,
                )

                tk.Label(
                    row,
                    text=label_text,
                    width=12,
                    anchor="w",
                    font=(
                        "Yu Gothic UI",
                        9,
                    ),
                    fg=MUTED,
                    bg="#F5F9FC",
                ).pack(
                    side=tk.LEFT,
                )

                tk.Label(
                    row,
                    text=value_text,
                    anchor="w",
                    font=(
                        "Yu Gothic UI",
                        9,
                        "bold",
                    ),
                    fg=TEXT,
                    bg="#F5F9FC",
                ).pack(
                    side=tk.LEFT,
                )

            event_row = tk.Frame(
                result_box,
                bg="#F5F9FC",
            )
            event_row.pack(
                fill=tk.X,
                pady=(9, 0),
            )

            tk.Label(
                event_row,
                text="犬連れ候補",
                font=(
                    "Yu Gothic UI",
                    11,
                    "bold",
                ),
                fg=TEXT,
                bg="#F5F9FC",
            ).pack(
                side=tk.LEFT,
            )

            tk.Label(
                event_row,
                text=f"{events}件",
                font=(
                    "Yu Gothic UI",
                    20,
                    "bold",
                ),
                fg=PRIMARY,
                bg="#F5F9FC",
            ).pack(
                side=tk.RIGHT,
            )

        else:
            tk.Label(
                result_box,
                text="解析は正常に完了しました。",
                font=(
                    "Yu Gothic UI",
                    10,
                ),
                fg=TEXT,
                bg="#F5F9FC",
            ).pack(
                anchor="w",
            )

        tk.Label(
            body,
            text="保存先",
            font=(
                "Yu Gothic UI",
                9,
                "bold",
            ),
            fg=TEXT,
            bg="white",
        ).pack(
            anchor="w",
        )

        batch_text = (
            str(self.last_batch_dir)
            if self.last_batch_dir
            else "結果フォルダ"
        )

        path_label = tk.Label(
            body,
            text=batch_text,
            font=(
                "Segoe UI",
                8,
            ),
            fg=MUTED,
            bg="white",
            anchor="w",
            justify=tk.LEFT,
            wraplength=490,
        )
        path_label.pack(
            fill=tk.X,
            pady=(4, 16),
        )

        buttons = tk.Frame(
            body,
            bg="white",
        )
        buttons.pack(
            fill=tk.X,
            side=tk.BOTTOM,
        )

        def open_results() -> None:
            self._open_results()

        tk.Button(
            buttons,
            text="結果フォルダを開く",
            command=open_results,
            bg=PRIMARY,
            fg="white",
            activebackground=PRIMARY_DARK,
            activeforeground="white",
            relief=tk.FLAT,
            padx=18,
            pady=7,
            font=(
                "Yu Gothic UI",
                9,
                "bold",
            ),
            cursor="hand2",
        ).pack(
            side=tk.LEFT,
        )

        close_button = tk.Button(
            buttons,
            text="閉じる",
            command=dialog.destroy,
            padx=22,
            pady=7,
            font=(
                "Yu Gothic UI",
                9,
            ),
        )
        close_button.pack(
            side=tk.RIGHT,
        )

        dialog.bind(
            "<Escape>",
            lambda _event: dialog.destroy(),
        )

        dialog.bind(
            "<Return>",
            lambda _event: dialog.destroy(),
        )

        dialog.protocol(
            "WM_DELETE_WINDOW",
            dialog.destroy,
        )

        close_button.focus_set()

    def _finish_failed(
        self,
        returncode: int,
    ) -> None:
        self.status_var.set(
            "エラー"
        )

        self.stage_var.set(
            "解析中にエラーが発生しました"
        )

        self.status_dot.configure(
            fg=ERROR
        )

        self.progress_text_var.set(
            "ERR"
        )

        self.cancel_button.configure(
            state=tk.DISABLED,
        )

        self.clear_log_button.configure(
            state=tk.NORMAL,
        )

        self._refresh_start_button_state()

        if (
            self.last_batch_dir
            and self.last_batch_dir.exists()
        ):
            self.open_button.configure(
                state=tk.NORMAL,
            )

        messagebox.showerror(
            "解析エラー",
            (
                "解析中にエラーが発生しました。\n"
                f"終了コード: {returncode}\n\n"
                "実行ログを確認してください。"
            ),
        )

    def _open_results(self) -> None:
        if (
            self.last_batch_dir is None
            or not self.last_batch_dir.exists()
        ):
            messagebox.showinfo(
                "結果",
                "結果フォルダがまだありません。",
            )
            return

        os.startfile(
            str(
                self.last_batch_dir
            )
        )


def main() -> int:
    app = DogWalkerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
