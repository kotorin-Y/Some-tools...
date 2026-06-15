from __future__ import annotations

import copy
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from windows_motion_studio import __version__
from windows_motion_studio.models import (
    InstalledApp,
    MotionProfile,
    PRESET_DESCRIPTIONS,
    PRESET_LABELS,
    PRESETS,
    ScenarioSettings,
)
from windows_motion_studio.motion_engine import apply_profile, open_config_folder, windows_animation_hint
from windows_motion_studio.profile_store import ProfileStore
from windows_motion_studio.scanner import scan_installed_apps
from windows_motion_studio.system_tweaks import (
    SystemAnimationSettings,
    apply_system_animation_settings,
    describe_visual_fx,
    read_system_animation_settings,
    recommended_system_settings,
)


BG = "#F4F8FF"
SURFACE = "#FFFFFF"
SURFACE_SOFT = "#EEF6FF"
LINE = "#D8E6F7"
TEXT = "#102033"
MUTED = "#607086"
BLUE = "#126BFF"
BLUE_DARK = "#0848B8"
BLUE_SOFT = "#DCEBFF"
CYAN = "#25A8FF"
GREEN = "#16A37A"
ORANGE = "#D98127"


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / relative


class MotionStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Windows Motion Studio {__version__}")
        self.geometry("1240x780")
        self.minsize(1040, 700)
        self.configure(bg=BG)
        icon = resource_path("assets/windows_motion_studio_icon.ico")
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

        self.store = ProfileStore()
        self.apps: list[InstalledApp] = []
        self.selected_app: InstalledApp | None = None
        self.current_profile = MotionProfile()
        self.scan_queue: queue.Queue[list[InstalledApp]] = queue.Queue()
        self.animation_job: str | None = None
        self.animation_step = 0
        self.loading_apps = False

        self._setup_style()
        self._build_ui()
        self._load_system_settings()
        self._start_scan()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("Soft.TFrame", background=SURFACE_SOFT)
        style.configure("Sidebar.TFrame", background=SURFACE)
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), background=BG, foreground=TEXT)
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), background=BG, foreground=MUTED)
        style.configure("CardTitle.TLabel", font=("Segoe UI", 13, "bold"), background=SURFACE, foreground=TEXT)
        style.configure("CardText.TLabel", font=("Segoe UI", 9), background=SURFACE, foreground=MUTED)
        style.configure("SoftText.TLabel", font=("Segoe UI", 9), background=SURFACE_SOFT, foreground=MUTED)
        style.configure("SidebarTitle.TLabel", font=("Segoe UI", 15, "bold"), background=SURFACE, foreground=TEXT)
        style.configure("SidebarText.TLabel", font=("Segoe UI", 9), background=SURFACE, foreground=MUTED)
        style.configure("Blue.TButton", background=BLUE, foreground="#FFFFFF", padding=(16, 8), borderwidth=0)
        style.map("Blue.TButton", background=[("active", BLUE_DARK)], foreground=[("active", "#FFFFFF")])
        style.configure("TButton", padding=(12, 7), borderwidth=0)
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT)
        style.configure("TRadiobutton", background=SURFACE, foreground=TEXT)
        style.configure("Horizontal.TScale", background=SURFACE)
        style.configure("Treeview", rowheight=34, background="#FFFFFF", fieldbackground="#FFFFFF", foreground=TEXT, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=SURFACE_SOFT, foreground=TEXT)
        style.map("Treeview", background=[("selected", BLUE_SOFT)], foreground=[("selected", TEXT)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 8), background=SURFACE_SOFT, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", BLUE)])

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(18, 18))
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.columnconfigure(0, weight=1)
        self.sidebar.rowconfigure(5, weight=1)

        logo = tk.Canvas(self.sidebar, width=44, height=44, bg=SURFACE, highlightthickness=0)
        logo.grid(row=0, column=0, sticky="w")
        self._draw_small_logo(logo)
        ttk.Label(self.sidebar, text="Motion Studio", style="SidebarTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(self.sidebar, text="离线应用动效与系统动画调节", style="SidebarText.TLabel").grid(row=2, column=0, sticky="w", pady=(2, 16))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_apps())
        self.search_entry = ttk.Entry(self.sidebar, textvariable=self.search_var)
        self.search_entry.grid(row=3, column=0, sticky="ew", pady=(0, 10))

        filter_row = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        filter_row.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        filter_row.columnconfigure((0, 1, 2), weight=1)
        self.filter_var = tk.StringVar(value="all")
        for col, (label, value) in enumerate((("全部", "all"), ("Win32", "win32"), ("Store", "store"))):
            ttk.Radiobutton(filter_row, text=label, value=value, variable=self.filter_var, command=self._filter_apps).grid(
                row=0, column=col, sticky="w"
            )

        self.app_tree = ttk.Treeview(self.sidebar, columns=("name", "type"), show="headings", selectmode="browse")
        self.app_tree.heading("name", text="应用")
        self.app_tree.heading("type", text="类型")
        self.app_tree.column("name", width=240, minwidth=190, stretch=True)
        self.app_tree.column("type", width=70, minwidth=60, stretch=False)
        self.app_tree.grid(row=5, column=0, sticky="nsew")
        self.app_tree.bind("<<TreeviewSelect>>", self._on_app_selected)

        ttk.Button(self.sidebar, text="重新扫描应用", command=self._start_scan).grid(row=6, column=0, sticky="ew", pady=(12, 0))

        self.main = ttk.Frame(self, padding=(24, 18))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        header = ttk.Frame(self.main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(header, text="正在扫描本机应用", style="Title.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.status_label = ttk.Label(header, text="正在初始化", style="Subtitle.TLabel")
        self.status_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        action_bar = ttk.Frame(header)
        action_bar.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Button(action_bar, text="导入", command=self._import_profiles).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_bar, text="导出", command=self._export_profiles).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(action_bar, text="配置目录", command=open_config_folder).grid(row=0, column=2)

        self.notebook = ttk.Notebook(self.main)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.app_tab = ttk.Frame(self.notebook, padding=0)
        self.system_tab = ttk.Frame(self.notebook, padding=0)
        self.notebook.add(self.app_tab, text="应用动效")
        self.notebook.add(self.system_tab, text="系统动画")

        self._build_app_tab()
        self._build_system_tab()

        bottom = ttk.Frame(self.main)
        bottom.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        bottom.columnconfigure(0, weight=1)
        ttk.Button(bottom, text="播放预览", command=self._play_preview).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(bottom, text="保存当前应用", command=self._save_current_profile).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(bottom, text="应用到本地策略库", style="Blue.TButton", command=self._apply_current_profile).grid(row=0, column=3)

        self.after(200, self._poll_scan)

    def _build_app_tab(self) -> None:
        self.app_tab.columnconfigure(0, weight=1)
        self.app_tab.columnconfigure(1, weight=1)
        self.app_tab.rowconfigure(0, weight=1)

        self.settings_panel = ttk.Frame(self.app_tab, style="Surface.TFrame", padding=18)
        self.settings_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.settings_panel.columnconfigure(0, weight=1)

        ttk.Label(self.settings_panel, text="动效档位", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.settings_panel, text="以应用为单位保存操作节奏，不修改第三方二进制文件。", style="CardText.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 10)
        )

        self.profile_var = tk.StringVar(value="balanced")
        self.profile_frame = ttk.Frame(self.settings_panel, style="Surface.TFrame")
        self.profile_frame.grid(row=2, column=0, sticky="ew")
        self.profile_frame.columnconfigure((0, 1), weight=1)
        for index, key in enumerate(("balanced", "efficient", "calm", "expressive", "minimal")):
            ttk.Radiobutton(
                self.profile_frame,
                text=f"{PRESET_LABELS[key]}\n{PRESET_DESCRIPTIONS[key]}",
                value=key,
                variable=self.profile_var,
                command=self._on_preset_changed,
            ).grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)

        self.speed_var = tk.DoubleVar(value=1.0)
        self.spring_var = tk.IntVar(value=34)
        self.distance_var = tk.IntVar(value=42)
        self._add_slider("速度倍率", self.speed_var, 0.6, 1.4, 3, "{:.2f}x")
        self._add_slider("弹性强度", self.spring_var, 0, 100, 4, "{}%")
        self._add_slider("位移幅度", self.distance_var, 0, 100, 5, "{}%")

        ttk.Separator(self.settings_panel).grid(row=6, column=0, sticky="ew", pady=14)
        ttk.Label(self.settings_panel, text="场景设置", style="CardTitle.TLabel").grid(row=7, column=0, sticky="w")
        self.scenario_vars = {
            "page": tk.StringVar(value="标准"),
            "overlay": tk.StringVar(value="标准"),
            "drag": tk.StringVar(value="精准"),
            "notify": tk.StringVar(value="标准"),
        }
        self._add_scenario("页面切换", "导航、返回、标签切换", "page", ("标准", "快速", "柔和"), 8)
        self._add_scenario("浮层弹窗", "菜单、对话框、右键面板", "overlay", ("标准", "轻量", "弹性"), 9)
        self._add_scenario("拖拽吸附", "窗口、文件、时间线对象", "drag", ("精准", "柔和", "弹性"), 10)
        self._add_scenario("通知反馈", "完成、失败、系统提示", "notify", ("标准", "轻量", "明显"), 11)

        self.preview_panel = ttk.Frame(self.app_tab, style="Surface.TFrame", padding=18)
        self.preview_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.preview_panel.columnconfigure(0, weight=1)
        self.preview_panel.rowconfigure(2, weight=1)
        ttk.Label(self.preview_panel, text="清新动效预览", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self.hint_label = ttk.Label(self.preview_panel, text="选择应用后显示建议。", style="CardText.TLabel", wraplength=460)
        self.hint_label.grid(row=1, column=0, sticky="ew", pady=(2, 12))
        self.preview = tk.Canvas(self.preview_panel, bg=SURFACE_SOFT, highlightthickness=1, highlightbackground=LINE)
        self.preview.grid(row=2, column=0, sticky="nsew")

        policy = ttk.Frame(self.preview_panel, style="Surface.TFrame")
        policy.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        policy.columnconfigure(0, weight=1)
        self.follow_accessibility_var = tk.BooleanVar(value=True)
        self.battery_var = tk.BooleanVar(value=True)
        self.refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(policy, text="跟随 Windows 辅助功能", variable=self.follow_accessibility_var, command=self._on_custom_changed).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Checkbutton(policy, text="电池模式自动降级", variable=self.battery_var, command=self._on_custom_changed).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Checkbutton(policy, text="高刷新率增强", variable=self.refresh_var, command=self._on_custom_changed).grid(row=2, column=0, sticky="w", pady=2)

    def _build_system_tab(self) -> None:
        self.system_tab.columnconfigure(0, weight=1)
        self.system_tab.columnconfigure(1, weight=1)
        self.system_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(self.system_tab, style="Surface.TFrame", padding=18)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="系统动画注册表调节", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            left,
            text="仅修改当前用户 HKCU 项，可通过 Windows 设置或本工具再次调整。部分设置需要注销或重启 Explorer 后完全生效。",
            style="CardText.TLabel",
            wraplength=460,
        ).grid(row=1, column=0, sticky="ew", pady=(2, 14))

        self.sys_min_animate_var = tk.BooleanVar(value=True)
        self.sys_taskbar_var = tk.BooleanVar(value=True)
        self.sys_menu_delay_var = tk.IntVar(value=120)
        self.sys_visual_fx_var = tk.StringVar(value="由 Windows 自动选择")

        ttk.Checkbutton(left, text="启用窗口最小化/最大化动画", variable=self.sys_min_animate_var).grid(row=2, column=0, sticky="w", pady=6)
        ttk.Checkbutton(left, text="启用任务栏动画", variable=self.sys_taskbar_var).grid(row=3, column=0, sticky="w", pady=6)
        self._add_system_delay_slider(left, 4)

        visual_row = ttk.Frame(left, style="Surface.TFrame")
        visual_row.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        visual_row.columnconfigure(0, weight=1)
        ttk.Label(visual_row, text="视觉效果策略", style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        self.visual_combo = ttk.Combobox(
            visual_row,
            textvariable=self.sys_visual_fx_var,
            values=("由 Windows 自动选择", "最佳外观", "最佳性能", "自定义"),
            state="readonly",
            width=18,
        )
        self.visual_combo.grid(row=0, column=1, sticky="e")

        actions = ttk.Frame(left, style="Surface.TFrame")
        actions.grid(row=6, column=0, sticky="ew", pady=(18, 0))
        actions.columnconfigure(0, weight=1)
        ttk.Button(actions, text="读取当前系统值", command=self._load_system_settings).grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="按当前档位推荐", command=self._apply_recommended_system_settings_to_controls).grid(row=0, column=1, padx=8)
        ttk.Button(actions, text="写入注册表", style="Blue.TButton", command=self._apply_system_settings).grid(row=0, column=2)

        right = ttk.Frame(self.system_tab, style="Surface.TFrame", padding=18)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="操作说明", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        text = (
            "可调项目\n"
            "1. MinAnimate：窗口最小化和最大化动画。\n"
            "2. MenuShowDelay：菜单出现延迟，范围 0-400 ms。\n"
            "3. VisualFXSetting：Windows 视觉效果策略。\n"
            "4. TaskbarAnimations：任务栏动画开关。\n\n"
            "安全边界\n"
            "这些设置均写入当前用户注册表，不需要管理员权限。工具不会修改系统文件、不会注入进程，也不会更改第三方应用二进制。"
        )
        self.system_info = tk.Text(right, height=14, wrap="word", bg=SURFACE_SOFT, fg=TEXT, relief="flat", padx=14, pady=12)
        self.system_info.grid(row=1, column=0, sticky="nsew", pady=(10, 14))
        self.system_info.insert("1.0", text)
        self.system_info.configure(state="disabled")
        self.system_state_label = ttk.Label(right, text="尚未读取系统值。", style="CardText.TLabel", wraplength=460)
        self.system_state_label.grid(row=2, column=0, sticky="ew")

    def _draw_small_logo(self, canvas: tk.Canvas) -> None:
        canvas.create_rectangle(4, 4, 40, 40, fill=BLUE, outline="")
        canvas.create_rectangle(10, 11, 34, 17, fill="#DCEBFF", outline="")
        canvas.create_rectangle(10, 20, 27, 26, fill="#FFFFFF", outline="")
        canvas.create_rectangle(10, 29, 34, 35, fill="#A8D5FF", outline="")
        canvas.create_oval(27, 10, 37, 20, fill=BLUE_DARK, outline="")
        canvas.create_oval(20, 19, 30, 29, fill="#0066CC", outline="")

    def _add_slider(self, label: str, var: tk.Variable, from_: float, to: float, row: int, fmt: str) -> None:
        frame = ttk.Frame(self.settings_panel, style="Surface.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        frame.columnconfigure(1, weight=1)
        value_label = ttk.Label(frame, text="", style="CardText.TLabel")
        ttk.Label(frame, text=label, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        value_label.grid(row=0, column=2, sticky="e")
        scale = ttk.Scale(frame, from_=from_, to=to, variable=var, command=lambda _=None: self._on_slider_changed())
        scale.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        def update_label(*_: object) -> None:
            value = var.get()
            if "{:.2f}" in fmt:
                value_label.configure(text=fmt.format(float(value)))
            else:
                value_label.configure(text=fmt.format(int(float(value))))

        var.trace_add("write", update_label)
        update_label()

    def _add_system_delay_slider(self, parent: ttk.Frame, row: int) -> None:
        frame = ttk.Frame(parent, style="Surface.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        frame.columnconfigure(1, weight=1)
        self.sys_delay_label = ttk.Label(frame, text="120 ms", style="CardText.TLabel")
        ttk.Label(frame, text="菜单出现延迟", style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        self.sys_delay_label.grid(row=0, column=2, sticky="e")
        ttk.Scale(frame, from_=0, to=400, variable=self.sys_menu_delay_var, command=lambda _=None: self._update_system_delay_label()).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(4, 0)
        )
        self.sys_menu_delay_var.trace_add("write", lambda *_: self._update_system_delay_label())

    def _add_scenario(self, title: str, subtitle: str, key: str, values: tuple[str, ...], row: int) -> None:
        frame = ttk.Frame(self.settings_panel, style="Surface.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="CardText.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=subtitle, style="CardText.TLabel").grid(row=1, column=0, sticky="w")
        combo = ttk.Combobox(frame, textvariable=self.scenario_vars[key], values=values, state="readonly", width=10)
        combo.grid(row=0, column=1, rowspan=2, sticky="e")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._on_custom_changed())
        combo.current(0)

    def _start_scan(self) -> None:
        self.loading_apps = True
        self.status_label.configure(text="正在扫描已安装应用...")
        self.app_tree.delete(*self.app_tree.get_children())
        threading.Thread(target=lambda: self.scan_queue.put(scan_installed_apps(include_store=True)), daemon=True).start()

    def _poll_scan(self) -> None:
        try:
            apps = self.scan_queue.get_nowait()
        except queue.Empty:
            self.after(200, self._poll_scan)
            return
        self.apps = apps
        self.loading_apps = False
        self.status_label.configure(text=f"已识别 {len(apps)} 个应用。请选择一个应用进行配置。")
        self._filter_apps()
        children = self.app_tree.get_children()
        if children:
            self.app_tree.selection_set(children[0])
            self.app_tree.focus(children[0])

    def _filter_apps(self) -> None:
        if self.loading_apps:
            return
        term = self.search_var.get().strip().casefold()
        app_type = self.filter_var.get()
        self.app_tree.delete(*self.app_tree.get_children())
        for app in self.apps:
            if app_type != "all" and app.app_type != app_type:
                continue
            text = " ".join([app.name, app.publisher, app.version, app.app_type]).casefold()
            if term and term not in text:
                continue
            self.app_tree.insert("", "end", iid=app.app_id, values=(app.name, app.app_type.upper()))

    def _on_app_selected(self, _event: object | None = None) -> None:
        selected = self.app_tree.selection()
        if not selected:
            return
        app = next((item for item in self.apps if item.app_id == selected[0]), None)
        if app is None:
            return
        self.selected_app = app
        self.current_profile = copy.deepcopy(self.store.get(app.app_id))
        self._load_profile_to_controls(self.current_profile)
        self.title_label.configure(text=app.name)
        meta = " · ".join(part for part in (app.app_type.upper(), app.publisher, app.version) if part)
        self.status_label.configure(text=meta or "已选择应用")
        self._update_hint()
        self._play_preview()

    def _load_profile_to_controls(self, profile: MotionProfile) -> None:
        self.profile_var.set(profile.profile if profile.profile in PRESETS else "balanced")
        self.speed_var.set(profile.speed)
        self.spring_var.set(profile.spring)
        self.distance_var.set(profile.distance)
        self.follow_accessibility_var.set(profile.follow_windows_accessibility)
        self.battery_var.set(profile.battery_saver_fallback)
        self.refresh_var.set(profile.high_refresh_enhancement)
        maps = {
            "page": {"standard": "标准", "fast": "快速", "soft": "柔和"},
            "overlay": {"standard": "标准", "quiet": "轻量", "elastic": "弹性"},
            "drag": {"precise": "精准", "soft": "柔和", "elastic": "弹性"},
            "notify": {"standard": "标准", "quiet": "轻量", "clear": "明显"},
        }
        for key, var in self.scenario_vars.items():
            var.set(maps[key].get(getattr(profile.scenario, key), next(iter(maps[key].values()))))

    def _controls_to_profile(self) -> MotionProfile:
        reverse = {
            "page": {"标准": "standard", "快速": "fast", "柔和": "soft"},
            "overlay": {"标准": "standard", "轻量": "quiet", "弹性": "elastic"},
            "drag": {"精准": "precise", "柔和": "soft", "弹性": "elastic"},
            "notify": {"标准": "standard", "轻量": "quiet", "明显": "clear"},
        }
        return MotionProfile(
            profile=self.current_profile.profile,
            speed=round(float(self.speed_var.get()), 2),
            spring=int(float(self.spring_var.get())),
            distance=int(float(self.distance_var.get())),
            scenario=ScenarioSettings(
                page=reverse["page"].get(self.scenario_vars["page"].get(), "standard"),
                overlay=reverse["overlay"].get(self.scenario_vars["overlay"].get(), "standard"),
                drag=reverse["drag"].get(self.scenario_vars["drag"].get(), "precise"),
                notify=reverse["notify"].get(self.scenario_vars["notify"].get(), "standard"),
            ),
            follow_windows_accessibility=self.follow_accessibility_var.get(),
            battery_saver_fallback=self.battery_var.get(),
            high_refresh_enhancement=self.refresh_var.get(),
        )

    def _on_preset_changed(self) -> None:
        key = self.profile_var.get()
        preset = PRESETS.get(key)
        if not preset:
            return
        self.current_profile = copy.deepcopy(preset)
        self.current_profile.profile = key
        self.speed_var.set(preset.speed)
        self.spring_var.set(preset.spring)
        self.distance_var.set(preset.distance)
        self._update_hint()
        self._play_preview()

    def _on_slider_changed(self) -> None:
        self.current_profile = self._controls_to_profile()
        if self.current_profile.profile in PRESETS:
            preset = PRESETS[self.current_profile.profile]
            changed = (
                abs(self.current_profile.speed - preset.speed) > 0.01
                or self.current_profile.spring != preset.spring
                or self.current_profile.distance != preset.distance
            )
            if changed:
                self.current_profile.profile = "custom"
        self._update_hint()
        self._draw_preview_frame(0)

    def _on_custom_changed(self) -> None:
        self.current_profile = self._controls_to_profile()
        self._update_hint()
        self._play_preview()

    def _update_hint(self) -> None:
        profile = self._controls_to_profile()
        self.current_profile = profile
        label = PRESET_LABELS.get(profile.profile, "自定义")
        desc = PRESET_DESCRIPTIONS.get(profile.profile, PRESET_DESCRIPTIONS["custom"])
        self.hint_label.configure(text=f"{label}: {desc}\n{windows_animation_hint(profile)}")

    def _save_current_profile(self) -> None:
        if not self.selected_app:
            messagebox.showinfo("未选择应用", "请先从左侧选择一个应用。")
            return
        profile = self._controls_to_profile()
        self.store.set(self.selected_app.app_id, profile)
        messagebox.showinfo("已保存", f"已保存 {self.selected_app.name} 的动效配置。")

    def _apply_current_profile(self) -> None:
        if not self.selected_app:
            messagebox.showinfo("未选择应用", "请先从左侧选择一个应用。")
            return
        profile = self._controls_to_profile()
        self.store.set(self.selected_app.app_id, profile)
        result = apply_profile(self.selected_app, profile)
        messagebox.showinfo(result.title, f"{result.message}\n\n报告位置:\n{result.report_path}")

    def _export_profiles(self) -> None:
        path = filedialog.asksaveasfilename(title="导出配置", defaultextension=".json", filetypes=(("JSON 配置", "*.json"), ("所有文件", "*.*")))
        if path:
            self.store.export_to(Path(path))
            messagebox.showinfo("已导出", f"配置已导出到:\n{path}")

    def _import_profiles(self) -> None:
        path = filedialog.askopenfilename(title="导入配置", filetypes=(("JSON 配置", "*.json"), ("所有文件", "*.*")))
        if not path:
            return
        try:
            self.store.import_from(Path(path))
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        if self.selected_app:
            self.current_profile = copy.deepcopy(self.store.get(self.selected_app.app_id))
            self._load_profile_to_controls(self.current_profile)
            self._update_hint()
        messagebox.showinfo("已导入", "配置已导入。")

    def _load_system_settings(self) -> None:
        try:
            settings = read_system_animation_settings()
        except Exception as exc:
            messagebox.showerror("读取失败", str(exc))
            return
        self._system_settings_to_controls(settings)
        self._update_system_state_label(settings)

    def _system_settings_to_controls(self, settings: SystemAnimationSettings) -> None:
        self.sys_min_animate_var.set(settings.min_animate)
        self.sys_taskbar_var.set(settings.taskbar_animations)
        self.sys_menu_delay_var.set(settings.menu_show_delay)
        self.sys_visual_fx_var.set(describe_visual_fx(settings.visual_fx_setting))
        self._update_system_delay_label()

    def _controls_to_system_settings(self) -> SystemAnimationSettings:
        visual_map = {"由 Windows 自动选择": 0, "最佳外观": 1, "最佳性能": 2, "自定义": 3}
        return SystemAnimationSettings(
            min_animate=self.sys_min_animate_var.get(),
            menu_show_delay=max(0, min(400, int(float(self.sys_menu_delay_var.get())))),
            visual_fx_setting=visual_map.get(self.sys_visual_fx_var.get(), 0),
            taskbar_animations=self.sys_taskbar_var.get(),
        )

    def _apply_recommended_system_settings_to_controls(self) -> None:
        profile_key = self.profile_var.get()
        self._system_settings_to_controls(recommended_system_settings(profile_key))
        self.notebook.select(self.system_tab)

    def _apply_system_settings(self) -> None:
        settings = self._controls_to_system_settings()
        detail = (
            f"窗口动画: {'开启' if settings.min_animate else '关闭'}\n"
            f"任务栏动画: {'开启' if settings.taskbar_animations else '关闭'}\n"
            f"菜单延迟: {settings.menu_show_delay} ms\n"
            f"视觉效果: {describe_visual_fx(settings.visual_fx_setting)}\n\n"
            "这些设置将写入当前用户注册表 HKCU。部分变化可能需要注销或重启 Explorer 后完全生效。"
        )
        if not messagebox.askyesno("确认写入注册表", detail):
            return
        try:
            changes = apply_system_animation_settings(settings)
        except Exception as exc:
            messagebox.showerror("写入失败", str(exc))
            return
        self._update_system_state_label(settings)
        summary = "\n".join(f"{item.path}\\{item.name}: {item.old_value} -> {item.new_value}" for item in changes)
        messagebox.showinfo("已写入注册表", f"已完成当前用户动画设置写入。\n\n{summary}")

    def _update_system_delay_label(self) -> None:
        if hasattr(self, "sys_delay_label"):
            self.sys_delay_label.configure(text=f"{int(float(self.sys_menu_delay_var.get()))} ms")

    def _update_system_state_label(self, settings: SystemAnimationSettings) -> None:
        self.system_state_label.configure(
            text=(
                f"当前控件值: 窗口动画 {'开' if settings.min_animate else '关'}，"
                f"任务栏动画 {'开' if settings.taskbar_animations else '关'}，"
                f"菜单延迟 {settings.menu_show_delay} ms，视觉效果 {describe_visual_fx(settings.visual_fx_setting)}。"
            )
        )

    def _play_preview(self) -> None:
        if self.animation_job:
            self.after_cancel(self.animation_job)
            self.animation_job = None
        self.animation_step = 0
        self._animate_preview()

    def _animate_preview(self) -> None:
        total = max(10, int(24 / max(0.6, float(self.speed_var.get()))))
        progress = min(1.0, self.animation_step / total)
        eased = 1 - (1 - progress) ** 3
        self._draw_preview_frame(eased)
        self.animation_step += 1
        if progress < 1:
            self.animation_job = self.after(16, self._animate_preview)

    def _draw_preview_frame(self, eased: float) -> None:
        canvas = self.preview
        canvas.delete("all")
        width = max(canvas.winfo_width(), 440)
        height = max(canvas.winfo_height(), 300)
        canvas.create_rectangle(0, 0, width, height, fill=SURFACE_SOFT, outline="")
        canvas.create_polygon(0, 0, width * 0.55, 0, 0, height * 0.6, fill="#DDEFFF", outline="")
        canvas.create_polygon(width, height, width * 0.46, height, width, height * 0.45, fill="#CFE6FF", outline="")

        distance = 10 + self.distance_var.get() * 0.38
        spring = self.spring_var.get() * 0.1
        y_offset = (1 - eased) * distance - spring * (1 - eased) * 0.28
        scale = 0.965 + eased * 0.035

        main_w, main_h = width * 0.58 * scale, height * 0.48 * scale
        main_x, main_y = width * 0.09, height * 0.18 + y_offset
        self._rounded_rect(canvas, main_x, main_y, main_x + main_w, main_y + main_h, 10, fill="#FFFFFF", outline="#C7DBF4")
        canvas.create_rectangle(main_x, main_y, main_x + main_w, main_y + 32, fill="#F7FBFF", outline="#C7DBF4")
        for i, color in enumerate((BLUE, CYAN, BLUE_DARK)):
            canvas.create_oval(main_x + 14 + i * 16, main_y + 11, main_x + 23 + i * 16, main_y + 20, fill=color, outline="")
        canvas.create_rectangle(main_x + 24, main_y + 58, main_x + main_w * 0.82, main_y + 70, fill=BLUE, outline="")
        canvas.create_rectangle(main_x + 24, main_y + 88, main_x + main_w * 0.58, main_y + 100, fill="#8BA4C4", outline="")
        tile_y = main_y + 126
        for i, color in enumerate(("#DCEBFF", "#B8DCFF", "#88C4FF")):
            x = main_x + 24 + i * (main_w * 0.25)
            self._rounded_rect(canvas, x, tile_y, x + main_w * 0.2, tile_y + 54, 8, fill=color, outline="")

        float_progress = max(0, min(1, eased * 1.15 - 0.1))
        fx, fy = width * 0.68, height * 0.24 + (1 - float_progress) * -distance
        fw, fh = width * 0.22, height * 0.25
        self._rounded_rect(canvas, fx, fy, fx + fw, fy + fh, 10, fill="#FFFFFF", outline="#C7DBF4")
        canvas.create_rectangle(fx + 16, fy + 22, fx + fw * 0.72, fy + 33, fill=BLUE, outline="")
        canvas.create_rectangle(fx + 16, fy + 58, fx + fw * 0.86, fy + 68, fill="#8BA4C4", outline="")
        canvas.create_rectangle(fx + 16, fy + 82, fx + fw * 0.58, fy + 92, fill="#8BA4C4", outline="")

        task_w = 178
        tx, ty = (width - task_w) / 2, height - 58
        self._rounded_rect(canvas, tx, ty, tx + task_w, ty + 42, 10, fill="#FFFFFF", outline="#C7DBF4")
        for i, color in enumerate((BLUE, CYAN, BLUE_DARK)):
            size = 24 * (1 + (self.spring_var.get() / 100) * 0.07 * (1 - abs(eased - 0.65)))
            ix = tx + 30 + i * 46
            self._rounded_rect(canvas, ix, ty + 9, ix + size, ty + 9 + size, 7, fill=color, outline="")

        if eased > 0.18:
            toast_y = height * 0.75 - min(1, (eased - 0.18) / 0.3) * 10
            self._rounded_rect(canvas, width * 0.64, toast_y, width * 0.93, toast_y + 34, 10, fill=BLUE_DARK, outline="")
            canvas.create_text(width * 0.785, toast_y + 17, text="配置已保存", fill="#FFFFFF", font=("Segoe UI", 9))

    @staticmethod
    def _rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs: object) -> None:
        canvas.create_polygon(
            [
                x1 + radius,
                y1,
                x2 - radius,
                y1,
                x2,
                y1,
                x2,
                y1 + radius,
                x2,
                y2 - radius,
                x2,
                y2,
                x2 - radius,
                y2,
                x1 + radius,
                y2,
                x1,
                y2,
                x1,
                y2 - radius,
                x1,
                y1 + radius,
                x1,
                y1,
            ],
            smooth=True,
            **kwargs,
        )


def main() -> None:
    app = MotionStudioApp()
    app.mainloop()
