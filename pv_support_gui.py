# -*- coding: utf-8 -*-
"""
光伏支架线模生成器 V1.2.4 — 界面骨架（MVP M1，2026-08-12 第七版）

运行方式：
    python pv_support_gui.py

V1.2.4 改动（按界面标注 + 口述调整）：
    1. 自定义窗口图标（光伏面板样式）；
    2. ② 支架形式：参数标签改短、去掉冗余单位字，整体更紧凑，右侧不再被遮挡；
       复位后示意图严格居中显示；
    3. ③ 构件截面表：型号下拉占满所在列宽；
    4. ⑤ 荷载参数：新增【沿海风压放大系数】（默认 1.10，规范取 1.1 倍）；
       地面粗糙度选项改为 A类/B类/C类/D类（与规范表述一致）；
    5. 界面固定尺寸、布局饱满紧凑，不新增左右拖动；
    6. ④ 3D 预览改为“转盘式”：绕模型中心旋转（固定支点）、Z 轴保持竖直向上、
       俯仰角限制小范围，模型自动放大居中填满画布。

单位约定：mm / kN，荷载 kN/m²，功率 W。
"""

import base64
import json
import math
import os
import struct
import tkinter as tk
import zlib
from tkinter import filedialog, messagebox, ttk


# --------------------------------------------------------------------------
# 常量与默认值
# --------------------------------------------------------------------------

COMPONENT_LIB = {
    "高科545W":     (2278, 1134, 35, 28.5, 545),
    "正泰550W":     (2384, 1303, 35, 34.8, 550),
    "锦州阳光545W": (2134, 1150, 30, 28.0, 545),
    "自定义":       (2134, 1150, 30, 28.0, 545),
}

SUPPORT_TYPES = ["单立柱", "单桩双立柱"]

SPEC_TYPES = ["C型钢", "Z型钢", "U型钢", "槽钢", "角钢", "圆钢/圆管", "方钢管", "矩形钢管", "自定义"]
SECTION_MODELS = {
    "C型钢":   ["C80×40×15×2.0", "C100×50×20×2.0", "C100×50×20×2.5",
                "C110×70×50×2.0", "C110×45×15×1.8", "C120×60×20×2.5",
                "C140×50×20×2.5", "41系列C型钢(41×41)", "自定义"],
    "Z型钢":   ["Z100×50×20×2.0", "Z120×60×20×2.5", "Z140×60×20×2.5", "自定义"],
    "U型钢":   ["U100×50×20×2.0", "U120×60×20×2.5", "U150×75×6.5", "自定义"],
    "槽钢":    ["槽8", "槽10", "槽12", "槽14a", "槽16a", "自定义"],
    "角钢":    ["L40×4", "L50×5", "L63×6", "L70×6", "L90×65×6", "自定义"],
    "圆钢/圆管": ["圆钢φ16", "圆钢φ20", "圆管48×3", "圆管60×3.5", "自定义"],
    "方钢管":  ["方管40×40×2.5", "方管60×60×3", "方管80×80×3", "自定义"],
    "矩形钢管": ["矩形管80×40×3", "矩形管100×50×3", "矩形管120×60×3", "自定义"],
    "自定义":  ["自定义"],
}

MATERIAL_OPTIONS = ["Q235B", "Q355B", "Q460B", "6061-T6", "6063-T5", "6005-T5", "自定义"]
ROUGHNESS_OPTIONS = ["A类", "B类", "C类", "D类"]

MEMBER_ROLES = [
    ("立柱", "槽钢",   "槽8",                "Q235B"),
    ("斜梁", "C型钢",  "C110×70×50×2.0",    "Q355B"),
    ("檩条", "C型钢",  "41系列C型钢(41×41)", "Q235B"),
    ("斜撑", "角钢",   "L50×5",              "Q235B"),
    ("檩托", "角钢",   "L40×4",              "Q235B"),
    ("抱箍", "自定义", "自定义",             "Q235B"),
    ("横担", "方钢管", "方管60×60×3",        "Q235B"),
]

MEMBER_COLORS = {
    "立柱": "#f9a825",
    "斜梁": "#1e88e5",
    "檩条": "#43a047",
    "斜撑": "#e53935",
    "支座": "#ffffff",
}

DEFAULT_PARAMS = {
    "project": {"name": "某光伏项目", "unit": "mm/kN"},
    "support_type": "单立柱",
    "module": {"lib": "高科545W", "L": 2278, "W": 1134, "T": 35,
               "weight": 28.5, "power": 545},
    "layout": {"rows": 2, "cols": 15, "tilt": 20, "gap": 20, "ground_gap": 1000},
    "structure": {"type": "单立柱", "bay": 2000, "bays": 8, "array_rows": 1,
                  "purlin_interval": 1500, "purlin_end_offset": 150,
                  "brace_front": 960, "brace_rear": 1808},
    "sections": {
        role: {"spec": spec, "model": model, "material": mat}
        for role, spec, model, mat in MEMBER_ROLES
    },
    "loads": {"dead": 0.05, "wind_base": 0.35, "snow": 0.20, "roughness": "B类",
              "mu_z": 1.10, "beta_z": 1.00, "coastal": 1.10,
              "mu_s_pos": 1.30, "mu_s_neg": -1.30},
}


# --------------------------------------------------------------------------
# 窗口图标（纯 Python 生成 64×64 PNG：太阳 + 倾斜光伏板）
# --------------------------------------------------------------------------

def _make_icon_png():
    W = H = 64
    px = [[(0, 0, 0, 0)] * W for _ in range(H)]

    def in_quad(x, y, pts):
        sign = None
        for i in range(4):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % 4]
            cross = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
            if cross != 0:
                s = cross > 0
                if sign is None:
                    sign = s
                elif s != sign:
                    return False
        return True

    for y in range(H):
        for x in range(W):
            # 太阳
            if (x - 14) ** 2 + (y - 14) ** 2 <= 10 ** 2:
                px[y][x] = (255, 193, 7, 255)
            # 倾斜光伏板
            elif in_quad(x, y, [(26, 18), (50, 18), (62, 50), (38, 50)]):
                px[y][x] = (33, 150, 243, 255)
            # 板框
            elif in_quad(x, y, [(24, 15), (52, 15), (65, 50), (37, 50)]):
                if not in_quad(x, y, [(27, 19), (49, 19), (60, 49), (38, 49)]):
                    px[y][x] = (66, 66, 66, 255)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"".join(bytes(p) for p in row) for row in px)
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


ICON_PNG_B64 = base64.b64encode(_make_icon_png()).decode("ascii")


# --------------------------------------------------------------------------
# 可滚动左侧面板
# --------------------------------------------------------------------------

class ScrollableFrame(ttk.Frame):
    """带纵向滚动条的 Frame，参数多了也不会被窗口裁掉。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._win, width=e.width),
        )
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _unbind_wheel(self, _event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event):
        # 内部画布（如支架示意）自己处理滚轮缩放时，不滚动面板
        if isinstance(event.widget, tk.Canvas) and event.widget is not self.canvas:
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


# --------------------------------------------------------------------------
# 主程序
# --------------------------------------------------------------------------

class PvSupportApp:
    def __init__(self, root):
        self.root = root
        self.vars = {}

        root.title("光伏支架线模生成器 V1.2.4")
        root.geometry("1280x840")
        root.resizable(False, False)   # 界面固定尺寸，不做左右拖动
        try:
            root.option_add("*Font", ("Microsoft YaHei UI", 10))
            icon = tk.PhotoImage(data=ICON_PNG_B64)
            root.iconphoto(True, icon)
        except tk.TclError:
            pass
        ttk.Style().theme_use("clam")

        self._load_city_data()
        self._build_top_bar()
        self._build_main_area()
        self._build_status_bar()
        self._bind_calc_events()
        self.apply_params(DEFAULT_PARAMS)
        self.set_status("就绪 V1.2.4：支架示意滚轮缩放/右键平移；3D 转盘旋转，Z 轴保持竖直")

    # -------------------------------------------------------------- 顶部栏
    def _build_top_bar(self):
        bar = ttk.Frame(self.root, padding=(10, 6))
        bar.pack(fill="x")

        ttk.Label(bar, text="支架类型").pack(side="left")
        self.vars["support_type"] = tk.StringVar(value=SUPPORT_TYPES[0])
        type_cb = ttk.Combobox(
            bar, textvariable=self.vars["support_type"],
            values=SUPPORT_TYPES, state="readonly", width=10,
        )
        type_cb.pack(side="left", padx=(4, 16))
        type_cb.bind("<<ComboboxSelected>>", lambda _e: self.update_calc())

        ttk.Label(bar, text="项目名称").pack(side="left")
        self.vars["project_name"] = tk.StringVar(value="某光伏项目")
        ttk.Entry(bar, textvariable=self.vars["project_name"], width=18).pack(
            side="left", padx=(4, 16)
        )

        ttk.Button(bar, text="打开工程", command=self.open_project).pack(side="right")
        ttk.Button(bar, text="保存工程", command=self.save_project).pack(
            side="right", padx=(0, 6)
        )
        ttk.Label(bar, text="单位：mm / kN　荷载 kN/m²").pack(side="right", padx=12)

    # ------------------------------------------------------------ 主区域
    def _build_main_area(self):
        main = ttk.Frame(self.root, padding=(10, 0, 10, 4))
        main.pack(fill="both", expand=True)

        left = ScrollableFrame(main)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.configure(width=580)

        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True)

        self._build_module_group(left.inner)
        self._build_support_group(left.inner)
        self._build_section_group(left.inner)

        self._build_preview(right)
        self._build_load_group(right)

    # ---------------------------------------------------------- ① 组件参数
    def _build_module_group(self, parent):
        grp = ttk.LabelFrame(parent, text="① 组件参数", padding=(8, 6))
        grp.pack(fill="x", pady=(0, 8))

        ttk.Label(grp, text="组件库").grid(row=0, column=0, sticky="w", pady=2)
        self.vars["module_lib"] = tk.StringVar()
        lib_cb = ttk.Combobox(
            grp, textvariable=self.vars["module_lib"],
            values=list(COMPONENT_LIB), state="readonly", width=12,
        )
        lib_cb.grid(row=0, column=1, columnspan=5, sticky="w", pady=2, padx=4)
        lib_cb.bind("<<ComboboxSelected>>", self._on_lib_change)

        def pair(row, label1, key1, unit1, label2, key2, unit2):
            ttk.Label(grp, text=label1).grid(row=row, column=0, sticky="w", pady=2)
            self.vars[key1] = tk.StringVar()
            e1 = ttk.Entry(grp, textvariable=self.vars[key1], width=5)
            e1.grid(row=row, column=1, sticky="w", padx=(4, 2))
            if unit1:
                ttk.Label(grp, text=unit1).grid(row=row, column=2, sticky="w", padx=(0, 8))
            ttk.Label(grp, text=label2).grid(row=row, column=3, sticky="w", pady=2)
            self.vars[key2] = tk.StringVar()
            e2 = ttk.Entry(grp, textvariable=self.vars[key2], width=5)
            e2.grid(row=row, column=4, sticky="w", padx=(4, 2))
            if unit2:
                ttk.Label(grp, text=unit2).grid(row=row, column=5, sticky="w")
            return [e1, e2]

        self.calc_entries = []
        self.calc_entries += pair(1, "组件长", "module_L", "mm",
                                     "组件宽", "module_W", "mm")
        self.calc_entries += pair(2, "组件厚", "module_T", "mm",
                                     "单重", "module_weight", "kg")
        self.calc_entries += pair(3, "行数", "layout_rows", "",
                                     "列数", "layout_cols", "")
        self.calc_entries += pair(4, "组件功率", "module_power", "W",
                                     "组件间隙", "layout_gap", "mm")

        self.calc_label = ttk.Label(
            grp, foreground="#1565c0", font=("Microsoft YaHei UI", 9, "bold"),
            justify="left",
        )
        self.calc_label.grid(row=5, column=0, columnspan=6, sticky="w", pady=(4, 0))

    # -------------------------------------------------------- ② 支架形式
    def _build_support_group(self, parent):
        grp = ttk.LabelFrame(
            parent, text="② 支架形式（侧面示意 · 单位 mm · 滚轮缩放 / 右键平移）",
            padding=(8, 6),
        )
        grp.pack(fill="x", pady=(0, 8))

        self.profile = tk.Canvas(
            grp, bg="white", height=200, highlightthickness=1,
            highlightbackground="#bdbdbd",
        )
        self.profile.grid(row=0, column=0, columnspan=6, sticky="ew", pady=(0, 4))
        self.profile.bind("<Configure>", lambda _e: self.draw_profile())
        self.profile.bind("<MouseWheel>", self._profile_wheel)
        self.profile.bind("<Button-3>", self._profile_pan_start)
        self.profile.bind("<B3-Motion>", self._profile_pan_drag)
        self.profile_zoom = 1.0
        self.profile_pan_x = 0.0
        self.profile_pan_y = 0.0
        self._profile_drag = None

        zoom_bar = ttk.Frame(grp)
        zoom_bar.grid(row=1, column=0, columnspan=6, sticky="e", pady=(0, 4))
        ttk.Label(zoom_bar, text="缩放").pack(side="left", padx=(0, 4))
        ttk.Button(zoom_bar, text="缩小", width=5,
                   command=lambda: self._profile_zoom_by(1 / 1.25)).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="放大", width=5,
                   command=lambda: self._profile_zoom_by(1.25)).pack(side="left", padx=2)
        ttk.Button(zoom_bar, text="复位", width=5,
                   command=self._profile_zoom_reset).pack(side="left", padx=2)

        def pair(row, label1, key1, unit1, label2, key2, unit2):
            ttk.Label(grp, text=label1).grid(row=row, column=0, sticky="w", pady=2)
            self.vars[key1] = tk.StringVar()
            e1 = ttk.Entry(grp, textvariable=self.vars[key1], width=5)
            e1.grid(row=row, column=1, sticky="w", padx=(4, 2))
            if unit1:
                ttk.Label(grp, text=unit1).grid(row=row, column=2, sticky="w", padx=(0, 6))
            ttk.Label(grp, text=label2).grid(row=row, column=3, sticky="w", pady=2)
            self.vars[key2] = tk.StringVar()
            e2 = ttk.Entry(grp, textvariable=self.vars[key2], width=5)
            e2.grid(row=row, column=4, sticky="w", padx=(4, 2))
            if unit2:
                ttk.Label(grp, text=unit2).grid(row=row, column=5, sticky="w")
            return [e1, e2]

        self.calc_entries += pair(2, "最低点", "layout_ground_gap", "",
                                     "倾角", "layout_tilt", "°")
        self.calc_entries += pair(3, "前斜撑", "brace_front", "",
                                     "后斜撑", "brace_rear", "")
        self.calc_entries += pair(4, "檩条间距", "struct_purlin_interval", "",
                                     "端距", "purlin_end_offset", "")

        ttk.Label(grp, text="柱距").grid(row=5, column=0, sticky="w", pady=2)
        self.vars["struct_bay"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["struct_bay"], width=5)
        e.grid(row=5, column=1, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)

        ttk.Label(grp, text="跨数").grid(row=5, column=3, sticky="w", pady=2)
        self.vars["struct_bays"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["struct_bays"], width=5)
        e.grid(row=5, column=4, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)

        ttk.Label(grp, text="排数").grid(row=6, column=0, sticky="w", pady=2)
        self.vars["struct_array_rows"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["struct_array_rows"], width=5)
        e.grid(row=6, column=1, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)

    # ------------------------------------------------------ ③ 构件截面表
    def _build_section_group(self, parent):
        grp = ttk.LabelFrame(parent, text="③ 构件截面表", padding=(8, 4))
        grp.pack(fill="x")

        ttk.Label(grp, text="构件").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(grp, text="规格").grid(row=0, column=1, sticky="w", padx=(0, 4))
        ttk.Label(grp, text="型号").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Label(grp, text="材质等级").grid(row=0, column=3, sticky="w")
        grp.columnconfigure(2, weight=1)   # 型号列占满剩余宽度

        self.section_spec_cbs = {}
        self.section_model_cbs = {}
        for i, (role, spec_default, model_default, mat_default) in enumerate(MEMBER_ROLES, start=1):
            ttk.Label(grp, text=role).grid(row=i, column=0, sticky="w", pady=1)

            self.vars[f"sec_{role}_spec"] = tk.StringVar()
            spec_cb = ttk.Combobox(
                grp, textvariable=self.vars[f"sec_{role}_spec"],
                values=SPEC_TYPES, state="readonly", width=6,
            )
            spec_cb.grid(row=i, column=1, sticky="w", padx=(0, 4), pady=1)
            spec_cb.bind("<<ComboboxSelected>>", lambda _e, r=role: self._on_spec_change(r))
            self.section_spec_cbs[role] = spec_cb

            self.vars[f"sec_{role}_model"] = tk.StringVar()
            model_cb = ttk.Combobox(
                grp, textvariable=self.vars[f"sec_{role}_model"],
                values=SECTION_MODELS[spec_default], state="readonly", width=16,
            )
            model_cb.grid(row=i, column=2, sticky="ew", padx=(0, 6), pady=1)
            self.section_model_cbs[role] = model_cb

            self.vars[f"sec_{role}_mat"] = tk.StringVar()
            ttk.Combobox(
                grp, textvariable=self.vars[f"sec_{role}_mat"],
                values=MATERIAL_OPTIONS, state="readonly", width=6,
            ).grid(row=i, column=3, sticky="w", pady=1)

        ttk.Label(
            grp, foreground="#757575",
            text="型号库 M4 接入正式截面库，当前为占位选项",
        ).grid(row=len(MEMBER_ROLES) + 1, column=0, columnspan=4, sticky="w", pady=(4, 0))

    # -------------------------------------------------------- ④ 3D 预览
    def _build_preview(self, parent):
        frame = ttk.LabelFrame(
            parent, text="④ 3D 线框预览（中键旋转 · 右键平移 · 滚轮缩放 · Z轴保持竖直）",
            padding=(6, 4),
        )
        frame.pack(fill="both", expand=True, pady=(0, 8))

        self.preview = tk.Canvas(
            frame, bg="#f5f5f5", highlightthickness=1,
            highlightbackground="#bdbdbd",
        )
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda _e: self.draw_viewer())

        # 转盘式视图：绕模型中心旋转，Z 轴保持竖直
        self.view_yaw = 0.6
        self.view_pitch = 0.35
        self.view_zoom = 1.0
        self.view_pan_x = 0.0
        self.view_pan_y = 0.0
        self._drag = None
        self._drag_mode = None
        self.preview.bind("<Button-2>", lambda e: self._view_start(e, "orbit"))
        self.preview.bind("<B2-Motion>", lambda e: self._view_drag(e, "orbit"))
        self.preview.bind("<Button-3>", lambda e: self._view_start(e, "pan"))
        self.preview.bind("<B3-Motion>", lambda e: self._view_drag(e, "pan"))
        self.preview.bind("<MouseWheel>", self._view_wheel)

        legend = ttk.Frame(frame)
        legend.pack(fill="x", pady=(4, 0))
        for role, color in MEMBER_COLORS.items():
            box = tk.Label(legend, bg=color, width=2)
            box.pack(side="left", padx=(8, 2), pady=2)
            ttk.Label(legend, text=role).pack(side="left", padx=(0, 6))

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=(4, 0))
        specs = [
            ("刷新预览", "#2e7d32", self.on_refresh),
            ("生成 DXF", "#1565c0", self.on_export_dxf),
            ("生成 3D3S", "#c62828", self.on_export_3d3s),
            ("生成 SAP2000", "#0277bd", self.on_export_sap),
        ]
        for text, color, cmd in specs:
            tk.Button(
                btns, text=text, command=cmd, bg=color, fg="white",
                font=("Microsoft YaHei UI", 10, "bold"),
                relief="raised", bd=1, padx=12, pady=4, cursor="hand2",
            ).pack(side="left", padx=(0, 8))

    # -------------------------------------------------------- ⑤ 荷载参数
    def _build_load_group(self, parent):
        grp = ttk.LabelFrame(
            parent, text="⑤ 荷载参数（NB/T 10115-2018 简化 · 城市查表 GB50009-2012）",
            padding=(8, 6),
        )
        grp.pack(fill="x")

        def entry(row, col, label, key, default, unit=""):
            ttk.Label(grp, text=label).grid(row=row, column=col * 2, sticky="w", pady=2)
            self.vars[key] = tk.StringVar()
            e = ttk.Entry(grp, textvariable=self.vars[key], width=5)
            e.grid(row=row, column=col * 2 + 1, sticky="w", padx=(4, 8))
            if unit:
                ttk.Label(grp, text=unit).grid(row=row, column=col * 2 + 2, sticky="w", padx=(0, 8))
            return e

        # 左列：基本荷载（竖向）+ 地面粗糙度
        ttk.Label(
            grp, text="基本荷载", foreground="#616161",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))
        entry(1, 0, "恒载", "load_dead", 0.05, "kN/m²")
        entry(2, 0, "雪载", "load_snow", 0.20, "kN/m²")
        entry(3, 0, "基本风压", "load_wind_base", 0.35, "kN/m²")
        ttk.Label(grp, text="地面粗糙度").grid(row=4, column=0, sticky="w", pady=2)
        self.vars["load_roughness"] = tk.StringVar()
        ttk.Combobox(
            grp, textvariable=self.vars["load_roughness"],
            values=ROUGHNESS_OPTIONS, state="readonly", width=5,
        ).grid(row=4, column=1, sticky="w", padx=(4, 8))

        # 中列：风压系数（竖向，含阵风系数、沿海放大系数）
        ttk.Label(
            grp, text="风压系数", foreground="#616161",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=0, column=4, columnspan=3, sticky="w", pady=(0, 2))
        entry(1, 2, "高度系数", "load_mu_z", 1.10)
        entry(2, 2, "阵风系数", "load_beta_z", 1.00)
        entry(3, 2, "正压体型系数", "load_mu_s_pos", 1.30)
        entry(4, 2, "负压体型系数", "load_mu_s_neg", -1.30)
        entry(5, 2, "沿海放大", "load_coastal", 1.10)

        # 右列：城市查表（省/市一行）
        ttk.Label(
            grp, text="城市查表（50年重现期）", foreground="#616161",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=0, column=8, columnspan=4, sticky="w", pady=(0, 2))

        ttk.Label(grp, text="省").grid(row=1, column=8, sticky="w", pady=2)
        self.vars["city_prov"] = tk.StringVar()
        self.prov_cb = ttk.Combobox(
            grp, textvariable=self.vars["city_prov"],
            values=sorted(self.city_data.keys()), state="readonly", width=5,
        )
        self.prov_cb.grid(row=1, column=9, sticky="w", padx=(4, 6))
        self.prov_cb.bind("<<ComboboxSelected>>", self._on_province_change)

        ttk.Label(grp, text="市").grid(row=1, column=10, sticky="w", pady=2)
        self.vars["city_name"] = tk.StringVar()
        self.city_cb = ttk.Combobox(
            grp, textvariable=self.vars["city_name"], state="readonly", width=10,
        )
        self.city_cb.grid(row=1, column=11, sticky="w", padx=(4, 4))
        self.city_cb.bind("<<ComboboxSelected>>", self._on_city_change)

        self.city_result_label = ttk.Label(
            grp, foreground="#1565c0", font=("Microsoft YaHei UI", 9, "bold"),
        )
        self.city_result_label.grid(row=2, column=8, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Label(
            grp, foreground="#757575",
            text="沿海放大：沿海城市基本风压按规范放大 1.1 倍，可调；查表后可再手动改",
            wraplength=540,
        ).grid(row=6, column=0, columnspan=12, sticky="w", pady=(4, 0))

    def _build_status_bar(self):
        self.status = ttk.Label(
            self.root, relief="sunken", anchor="w", padding=(8, 3),
        )
        self.status.pack(fill="x", side="bottom")

    # ------------------------------------------------------------ 城市查表
    def _load_city_data(self):
        self.city_data = {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "荷载规范城市数据.json")
        try:
            with open(path, "r", encoding="utf-8") as fp:
                self.city_data = json.load(fp).get("data", {})
        except (OSError, json.JSONDecodeError):
            self.city_data = {}

    def _on_province_change(self, _event=None):
        prov = self.vars["city_prov"].get()
        cities = sorted(self.city_data.get(prov, {}).keys())
        self.city_cb.configure(values=cities)
        if cities:
            self.vars["city_name"].set(cities[0])
            self._on_city_change()
        else:
            self.vars["city_name"].set("")
            self.city_result_label.config(text="该省暂无城市数据")

    def _on_city_change(self, _event=None):
        prov = self.vars["city_prov"].get()
        city = self.vars["city_name"].get()
        rec = self.city_data.get(prov, {}).get(city)
        if not rec:
            return
        self.vars["load_wind_base"].set(str(rec["w50"]))
        self.vars["load_snow"].set(str(rec["s50"]))
        self.city_result_label.config(
            text=f"风压 {rec['w50']} · 雪压 {rec['s50']} kN/m²（GB50009-2012 附录E）"
        )

    # ------------------------------------------------------------ 联动逻辑
    def _on_lib_change(self, _event=None):
        lib = self.vars["module_lib"].get()
        if lib in COMPONENT_LIB and lib != "自定义":
            L, W, T, weight, power = COMPONENT_LIB[lib]
            self.vars["module_L"].set(str(L))
            self.vars["module_W"].set(str(W))
            self.vars["module_T"].set(str(T))
            self.vars["module_weight"].set(str(weight))
            self.vars["module_power"].set(str(power))
        self.update_calc()

    def _on_spec_change(self, role):
        spec = self.vars[f"sec_{role}_spec"].get()
        models = SECTION_MODELS.get(spec, SECTION_MODELS["自定义"])
        self.section_model_cbs[role].configure(values=models)
        self.vars[f"sec_{role}_model"].set(models[0])

    def _bind_calc_events(self):
        for e in self.calc_entries:
            e.bind("<KeyRelease>", lambda _ev: self.update_calc())
            e.bind("<FocusOut>", lambda _ev: self.update_calc())

    # ------------------------------------------------------------ 支架示意交互
    def _profile_wheel(self, event):
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self.profile_zoom = max(0.3, min(3.5, self.profile_zoom * factor))
        self.draw_profile()

    def _profile_zoom_by(self, factor):
        self.profile_zoom = max(0.3, min(3.5, self.profile_zoom * factor))
        self.draw_profile()

    def _profile_zoom_reset(self):
        self.profile_zoom = 1.0
        self.profile_pan_x = 0.0
        self.profile_pan_y = 0.0
        self.draw_profile()

    def _profile_pan_start(self, event):
        self._profile_drag = (event.x, event.y)

    def _profile_pan_drag(self, event):
        if self._profile_drag is None:
            return
        dx, dy = event.x - self._profile_drag[0], event.y - self._profile_drag[1]
        self._profile_drag = (event.x, event.y)
        self.profile_pan_x += dx
        self.profile_pan_y += dy
        self.draw_profile()

    # ------------------------------------------------------------ 3D 视图交互
    def _view_start(self, event, mode):
        self._drag = (event.x, event.y)
        self._drag_mode = mode

    def _view_drag(self, event, mode):
        if self._drag is None or self._drag_mode != mode:
            return
        dx, dy = event.x - self._drag[0], event.y - self._drag[1]
        self._drag = (event.x, event.y)
        if mode == "orbit":
            self.view_yaw += dx * 0.008
            # 俯仰角限制在小范围，保证 Z 轴基本竖直
            self.view_pitch = max(-0.65, min(0.65, self.view_pitch + dy * 0.008))
        else:
            self.view_pan_x += dx
            self.view_pan_y += dy
        self.draw_viewer()

    def _view_wheel(self, event):
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self.view_zoom = max(0.3, min(4.0, self.view_zoom * factor))
        self.draw_viewer()

    # ------------------------------------------------------------ 计算联动
    def update_calc(self):
        """实时估算：组件总宽/总长、阵列功率（仅①显示；支架几何只在图上表达）。"""
        try:
            rows = int(float(self.vars["layout_rows"].get()))
            cols = int(float(self.vars["layout_cols"].get()))
            gap = float(self.vars["layout_gap"].get())
            L = float(self.vars["module_L"].get())
            W = float(self.vars["module_W"].get())
            power = float(self.vars["module_power"].get())

            total_width = rows * L + (rows - 1) * gap
            total_length = cols * W + (cols - 1) * gap
            count = rows * cols
            power_kw = power * count / 1000
            self.calc_label.config(
                text=f"组件总宽 {total_width:.0f} mm　组件总长 {total_length:.0f} mm\n"
                     f"阵列功率 ≈ {power_kw:.2f} kW（{count} 块 × {power:.0f} W）"
            )
            self.draw_profile()
            self.draw_viewer()
        except (ValueError, tk.TclError):
            self.calc_label.config(text="组件总宽/总长：参数不完整")

    # ------------------------------------------------------------ 侧面示意
    def _profile_geometry(self):
        try:
            rows = int(float(self.vars["layout_rows"].get()))
            gap = float(self.vars["layout_gap"].get())
            L = float(self.vars["module_L"].get())
            tilt = float(self.vars["layout_tilt"].get())
            ground = float(self.vars["layout_ground_gap"].get())
        except (ValueError, tk.TclError):
            return None
        slope = rows * L + (rows - 1) * gap
        a = math.radians(tilt)
        span = slope * math.cos(a)
        rise = slope * math.sin(a)
        if span <= 0:
            return None
        return slope, span, rise, ground, a

    def draw_profile(self):
        """② 支架形式：侧面示意图，复位后严格居中显示。"""
        c = self.profile
        c.delete("all")
        cw = max(c.winfo_width(), 60)
        ch = max(c.winfo_height(), 60)

        geo = self._profile_geometry()
        if geo is None:
            c.create_text(
                cw / 2, ch / 2, fill="#757575",
                text="支架形式：参数不完整", font=("Microsoft YaHei UI", 10),
            )
            return
        slope, span, rise, ground, a = geo
        try:
            brace_front = float(self.vars["brace_front"].get())
            brace_rear = float(self.vars["brace_rear"].get())
            purlin_interval = float(self.vars["struct_purlin_interval"].get())
            end_offset = float(self.vars["purlin_end_offset"].get())
            rows = int(float(self.vars["layout_rows"].get()))
        except (ValueError, tk.TclError):
            brace_front, brace_rear, purlin_interval, end_offset, rows = 960, 1808, 1500, 150, 2

        maxh = ground + rise
        m = 30
        base_scale = min((cw - 2 * m) / span, (ch - 2 * m) / maxh)
        scale = base_scale * self.profile_zoom

        # 复位后：几何中心对准画布中心
        def P(x, y):
            return (
                cw / 2 + (x - span / 2) * scale + self.profile_pan_x,
                ch / 2 - (y - maxh / 2) * scale + self.profile_pan_y,
            )

        gx0, gy = P(0, 0)
        gx1, _ = P(span, 0)
        c.create_line(gx0, gy, gx1, gy, fill="#9e9e9e", width=1, dash=(4, 3))
        c.create_text((gx0 + gx1) / 2, gy + 10, text="地面", fill="#9e9e9e",
                      font=("Microsoft YaHei UI", 8))

        ax, ay = P(0, ground)
        bx, by = P(span, ground + rise)
        c.create_line(ax, ay, bx, by, fill=MEMBER_COLORS["斜梁"], width=3)

        c.create_line(*P(0, 0), ax, ay, fill=MEMBER_COLORS["立柱"], width=3)
        if self.vars["support_type"].get() == "单桩双立柱":
            c.create_line(*P(span, 0), bx, by, fill=MEMBER_COLORS["立柱"], width=3)

        if 0 < brace_front < slope:
            fx, fy = P(brace_front * math.cos(a), ground + brace_front * math.sin(a))
            c.create_line(*P(0, 0), fx, fy, fill=MEMBER_COLORS["斜撑"], width=2)
        if self.vars["support_type"].get() == "单桩双立柱" and 0 < brace_rear < slope:
            t_rear = slope - brace_rear
            rx, ry = P(t_rear * math.cos(a), ground + t_rear * math.sin(a))
            c.create_line(*P(span, 0), rx, ry, fill=MEMBER_COLORS["斜撑"], width=2)

        purlin_count = rows * 2
        nx = -math.sin(a)
        ny = math.cos(a)
        tick = max(8, scale * 90)
        for i in range(purlin_count):
            t = end_offset + i * purlin_interval
            if t > slope:
                break
            px, py = P(t * math.cos(a), ground + t * math.sin(a))
            c.create_line(
                px - nx * tick, py - ny * tick,
                px + nx * tick, py + ny * tick,
                fill=MEMBER_COLORS["檩条"], width=2,
            )

        # 倾角标注
        r = max(24, min(40, scale * 240))
        c.create_arc(ax - r, ay - r, ax + r, ay + r,
                     start=0, extent=-math.degrees(a), style="arc", outline="#757575")
        c.create_text(
            ax + r * 0.78, ay - r * 0.5, text=f"{math.degrees(a):.0f}°",
            fill="#424242", font=("Microsoft YaHei UI", 9, "bold"),
        )

        lx, ly = 12, ch - 16
        for role in ("斜梁", "立柱", "斜撑", "檩条"):
            c.create_rectangle(lx, ly, lx + 10, ly + 8, fill=MEMBER_COLORS[role], outline="")
            c.create_text(lx + 14, ly + 4, text=role, anchor="w", fill="#424242",
                          font=("Microsoft YaHei UI", 8))
            lx += 62

        if self.profile_zoom > 1.01 or self.profile_pan_x or self.profile_pan_y:
            c.create_text(
                cw / 2, 12, fill="#757575",
                text=f"缩放 {self.profile_zoom:.1f}× · 右键平移 · 复位恢复居中",
                font=("Microsoft YaHei UI", 8),
            )

    # ------------------------------------------------------------ 3D 预览
    def draw_viewer(self):
        """④ 3D 线框预览：转盘式旋转（绕模型中心，Z 轴保持竖直）。
        中键拖动旋转 / 右键平移 / 滚轮缩放，模型自动放大居中填满画布。"""
        c = self.preview
        c.delete("all")
        w = max(c.winfo_width(), 60)
        h = max(c.winfo_height(), 60)

        geo = self._profile_geometry()
        if geo is None:
            c.create_text(
                w / 2, h / 2, fill="#757575",
                text="3D 预览：参数不完整", font=("Microsoft YaHei UI", 10),
            )
            return
        slope, span, rise, ground, a = geo
        try:
            bay = float(self.vars["struct_bay"].get())
            brace_front = float(self.vars["brace_front"].get())
            brace_rear = float(self.vars["brace_rear"].get())
            purlin_interval = float(self.vars["struct_purlin_interval"].get())
            end_offset = float(self.vars["purlin_end_offset"].get())
            rows = int(float(self.vars["layout_rows"].get()))
        except (ValueError, tk.TclError):
            bay, brace_front, brace_rear, purlin_interval, end_offset, rows = 2000, 960, 1808, 1500, 150, 2

        depth = bay * 0.55
        maxh = ground + rise

        def beam_pt(t):
            return (t * math.cos(a), 0.0, ground + t * math.sin(a))

        lines = []
        double_col = self.vars["support_type"].get() == "单桩双立柱"
        for y in (-depth, depth):
            lines.append(((0, y, 0), (0, y, ground), MEMBER_COLORS["立柱"]))
            if double_col:
                lines.append(((span, y, 0), (span, y, ground + rise), MEMBER_COLORS["立柱"]))
            lines.append(((0, y, ground), (span, y, ground + rise), MEMBER_COLORS["斜梁"]))
            if 0 < brace_front < slope:
                p = beam_pt(brace_front)
                lines.append(((0, y, 0), (p[0], y, p[2]), MEMBER_COLORS["斜撑"]))
            if double_col and 0 < brace_rear < slope:
                p = beam_pt(slope - brace_rear)
                lines.append(((span, y, 0), (p[0], y, p[2]), MEMBER_COLORS["斜撑"]))

        purlin_count = rows * 2
        for i in range(purlin_count):
            t = end_offset + i * purlin_interval
            if t > slope:
                break
            p = beam_pt(t)
            lines.append(((p[0], -depth, p[2]), (p[0], depth, p[2]), MEMBER_COLORS["檩条"]))

        lines.append(((0, -depth, 0), (span, -depth, 0), "#9e9e9e"))
        lines.append(((span, -depth, 0), (span, depth, 0), "#9e9e9e"))
        lines.append(((span, depth, 0), (0, depth, 0), "#9e9e9e"))
        lines.append(((0, depth, 0), (0, -depth, 0), "#9e9e9e"))

        # 固定支点 = 模型中心；转盘式：绕竖直 Z 轴旋转 + 小俯仰视角
        cxw, cyw, czw = span / 2, 0.0, maxh / 2
        yaw = self.view_yaw
        p = self.view_pitch
        cp, sp = math.cos(p), math.sin(p)

        def transform(x, y, z):
            dx, dy = x - cxw, y - cyw
            x1 = dx * math.cos(yaw) - dy * math.sin(yaw)
            y1 = dx * math.sin(yaw) + dy * math.cos(yaw)
            z1 = z - czw
            return x1, y1, z1

        maxdim = max(span, depth * 2, maxh, 1.0)
        scale = min(w, h) / maxdim * 0.62 * self.view_zoom
        cx, cy = w / 2 + self.view_pan_x, h / 2 + self.view_pan_y

        def proj(x, y, z):
            x1, y1, z1 = transform(x, y, z)
            sx = cx + x1 * scale
            sy = cy - z1 * scale * cp + y1 * scale * sp
            return sx, sy

        for p1, p2, color in lines:
            c.create_line(*proj(*p1), *proj(*p2), fill=color, width=2)

        axis = [
            ((0, 0, 0), (maxdim * 0.35, 0, 0), "#e53935", "X"),
            ((0, 0, 0), (0, maxdim * 0.35, 0), "#43a047", "Y"),
            ((0, 0, 0), (0, 0, maxdim * 0.35), "#1e88e5", "Z"),
        ]
        for a0, b0, color, label in axis:
            c.create_line(*proj(*a0), *proj(*b0), fill=color, width=2)
            x, y = proj(*b0)
            c.create_text(x, y - 5, text=label, fill=color,
                          font=("Microsoft YaHei UI", 9, "bold"))

        c.create_text(
            cx, h - 10, fill="#757575",
            text="中键拖动旋转（Z轴竖直）· 右键平移 · 滚轮缩放",
            font=("Microsoft YaHei UI", 9),
        )

    # ------------------------------------------------------------ 参数收集
    def collect_params(self):
        """界面 → 参数字典（后端唯一数据契约）。校验失败抛 ValueError。"""
        def f(key):
            return float(self.vars[key].get())

        def i(key):
            return int(float(self.vars[key].get()))

        tilt = f("layout_tilt")
        if not (5 <= tilt <= 35):
            raise ValueError(f"安装倾角需在 5~35° 之间，当前 {tilt}°")

        params = {
            "project": {"name": self.vars["project_name"].get(), "unit": "mm/kN"},
            "support_type": self.vars["support_type"].get(),
            "module": {
                "lib": self.vars["module_lib"].get(),
                "L": f("module_L"), "W": f("module_W"), "T": f("module_T"),
                "weight": f("module_weight"), "power": f("module_power"),
            },
            "layout": {
                "rows": i("layout_rows"), "cols": i("layout_cols"),
                "tilt": tilt, "gap": f("layout_gap"),
                "ground_gap": f("layout_ground_gap"),
            },
            "structure": {
                "type": self.vars["support_type"].get(),
                "bay": f("struct_bay"), "bays": i("struct_bays"),
                "array_rows": i("struct_array_rows"),
                "purlin_interval": f("struct_purlin_interval"),
                "purlin_end_offset": f("purlin_end_offset"),
                "brace_front": f("brace_front"),
                "brace_rear": f("brace_rear"),
            },
            "sections": {
                role: {
                    "spec": self.vars[f"sec_{role}_spec"].get(),
                    "model": self.vars[f"sec_{role}_model"].get(),
                    "material": self.vars[f"sec_{role}_mat"].get(),
                }
                for role, _, _, _ in MEMBER_ROLES
            },
            "loads": {
                "dead": f("load_dead"),
                "wind_base": f("load_wind_base"),
                "snow": f("load_snow"),
                "roughness": self.vars["load_roughness"].get(),
                "mu_z": f("load_mu_z"),
                "beta_z": f("load_beta_z"),
                "coastal": f("load_coastal"),
                "mu_s_pos": f("load_mu_s_pos"),
                "mu_s_neg": f("load_mu_s_neg"),
                "city": {
                    "province": self.vars["city_prov"].get(),
                    "city": self.vars["city_name"].get(),
                },
            },
        }
        return params

    def apply_params(self, params):
        """参数字典 → 界面控件（启动默认 / 打开工程共用）。"""
        def setv(key, value):
            if value is None:
                return
            self.vars[key].set(str(value))

        setv("project_name", params.get("project", {}).get("name", ""))
        setv("support_type", params.get("support_type", SUPPORT_TYPES[0]))
        mod = params.get("module", {})
        setv("module_lib", mod.get("lib", "高科545W"))
        setv("module_L", mod.get("L", 2278))
        setv("module_W", mod.get("W", 1134))
        setv("module_T", mod.get("T", 35))
        setv("module_weight", mod.get("weight", 28.5))
        setv("module_power", mod.get("power", 545))
        lay = params.get("layout", {})
        setv("layout_rows", lay.get("rows", 2))
        setv("layout_cols", lay.get("cols", 15))
        setv("layout_tilt", lay.get("tilt", 20))
        setv("layout_gap", lay.get("gap", 20))
        setv("layout_ground_gap", lay.get("ground_gap", 1000))
        st = params.get("structure", {})
        setv("struct_bay", st.get("bay", 2000))
        setv("struct_bays", st.get("bays", 8))
        setv("struct_array_rows", st.get("array_rows", 1))
        setv("struct_purlin_interval", st.get("purlin_interval", 1500))
        setv("purlin_end_offset", st.get("purlin_end_offset", 150))
        setv("brace_front", st.get("brace_front", 960))
        setv("brace_rear", st.get("brace_rear", 1808))
        for role, _, _, _ in MEMBER_ROLES:
            sec = params.get("sections", {}).get(role, {})
            spec = sec.get("spec", "自定义")
            model = sec.get("model", "自定义")
            mat = sec.get("material", "Q235B")
            if spec not in SECTION_MODELS:
                spec = "自定义"
            models = SECTION_MODELS[spec]
            if model not in models:
                model = models[0]
            self.section_spec_cbs[role].configure(values=SPEC_TYPES)
            self.section_model_cbs[role].configure(values=models)
            setv(f"sec_{role}_spec", spec)
            setv(f"sec_{role}_model", model)
            setv(f"sec_{role}_mat", mat)
        ld = params.get("loads", {})
        setv("load_dead", ld.get("dead", 0.05))
        setv("load_wind_base", ld.get("wind_base", 0.35))
        setv("load_snow", ld.get("snow", 0.20))
        rough = ld.get("roughness", "B类")
        if rough and "类" not in rough and rough in "ABCD":
            rough += "类"
        setv("load_roughness", rough)
        setv("load_mu_z", ld.get("mu_z", 1.10))
        setv("load_beta_z", ld.get("beta_z", 1.00))
        setv("load_coastal", ld.get("coastal", 1.10))
        setv("load_mu_s_pos", ld.get("mu_s_pos", 1.30))
        setv("load_mu_s_neg", ld.get("mu_s_neg", -1.30))
        city = ld.get("city", {})
        if city.get("province") in self.city_data:
            setv("city_prov", city["province"])
            cities = sorted(self.city_data[city["province"]].keys())
            self.city_cb.configure(values=cities)
            if city.get("city") in cities:
                setv("city_name", city["city"])
                self._on_city_change()
        self.update_calc()

    # ------------------------------------------------------------ 按钮动作
    def on_refresh(self):
        try:
            params = self.collect_params()
        except ValueError as exc:
            messagebox.showwarning("参数有误", str(exc))
            return
        print(json.dumps(params, ensure_ascii=False, indent=2))
        self.draw_profile()
        self.draw_viewer()
        self.set_status("参数已收集 ✔ 几何引擎未接入（M2 里程碑），3D 预览为示意线框")

    def on_export_dxf(self):
        self.set_status("【生成 DXF】尚未接入（M3 里程碑：ezdxf 导出线模）")

    def on_export_3d3s(self):
        self.set_status("【生成 3D3S】尚未接入（M3 里程碑：DXF 导入 3D3S 验证）")

    def on_export_sap(self):
        self.set_status("【生成 SAP2000】尚未接入（M3 里程碑：.s2k 导出）")

    def save_project(self):
        try:
            params = self.collect_params()
        except ValueError as exc:
            messagebox.showwarning("参数有误", str(exc))
            return
        path = filedialog.asksaveasfilename(
            title="保存工程", defaultextension=".json",
            filetypes=[("工程文件", "*.json")], initialfile="光伏支架工程.json",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(params, fp, ensure_ascii=False, indent=2)
        self.set_status(f"工程已保存：{path}")

    def open_project(self):
        path = filedialog.askopenfilename(
            title="打开工程", filetypes=[("工程文件", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                params = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("打开失败", str(exc))
            return
        self.apply_params(params)
        self.set_status(f"已打开工程：{path}")

    def set_status(self, text):
        self.status.config(text=text)


def main():
    root = tk.Tk()
    PvSupportApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
