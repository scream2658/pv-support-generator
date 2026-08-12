# -*- coding: utf-8 -*-
"""
光伏支架线模生成器 V1.2.17 — 界面骨架（MVP M1，2026-08-12 第二十版）

运行方式：
    python pv_support_gui.py

V1.2.17 改动（立柱高度修正）：
    1. 新增【梁中心偏移】参数（默认150mm）：组件最低点至斜梁中心线的
       垂直距离（主要由檩条截面高度决定，M4 可从檩条截面自动带出）；
    2. 实际立柱高度 = 最低点高度 + 斜梁半长×sin(倾角) − 梁中心偏移；
       斜梁中心线整体下移偏移量，前/后斜撑长度按修正后的立柱高度计算；
    3. 斜梁长度不受影响（长细比影响仅几十毫米，忽略）。

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
SEISMIC_OPTIONS = ["6度(0.05g)", "7度(0.10g)", "7度(0.15g)", "8度(0.20g)", "8度(0.30g)", "9度(0.40g)"]
MANUAL_PROVINCE = "（手动输入）"

PROV_DISPLAY = {
    "北京": "北京市", "天津": "天津市", "上海": "上海市", "重庆": "重庆市",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "西藏": "西藏自治区",
    "宁夏": "宁夏回族自治区", "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区", "澳门": "澳门特别行政区", "台湾": "台湾省",
}

def prov_display(key):
    return PROV_DISPLAY.get(key, key + "省")

def prov_key(display):
    for k, v in PROV_DISPLAY.items():
        if v == display:
            return k
    return (display.replace("省", "").replace("壮族", "").replace("回族", "")
            .replace("维吾尔", "").replace("自治区", "").replace("特别行政区", ""))

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
    "斜撑": "#ec407a",
    "支座": "#e53935",
}

DEFAULT_PARAMS = {
    "project": {"name": "某光伏项目", "unit": "mm/kN"},
    "support_type": "单立柱",
    "module": {"lib": "高科545W", "L": 2278, "W": 1134, "T": 35,
               "weight": 28.5, "power": 545, "hole_pitch": 1400},
    "layout": {"rows": 2, "cols": 15, "tilt": 20, "gap": 20, "ground_gap": 1000},
    "structure": {"type": "单立柱", "bay": 2000, "frames": 8,
                  "purlin_end_offset": 150, "purlin_extension": 150,
                  "beam_center_offset": 150, "brace_ground": 300,
                  "brace_front_off": 350, "brace_rear_off": 350},
    "sections": {
        role: {"spec": spec, "model": model, "material": mat}
        for role, spec, model, mat in MEMBER_ROLES
    },
    "loads": {"dead": 0.05, "wind_base": 0.35, "snow": 0.20, "roughness": "B类",
              "site_class": "Ⅱ类",
              "mu_z": 1.10, "beta_z": 1.00, "coastal": 1.10, "coastal_enabled": False,
              "mu_s_pos": 1.30, "mu_s_neg": -1.30,
              "seismic": "7度(0.10g)",
              "city": {"province": "北京", "city": "北京", "district": ""}},
}


# --------------------------------------------------------------------------
# 窗口图标（纯 Python 生成 64×64 PNG：支架线框样式）
# --------------------------------------------------------------------------

def _make_icon_png():
    W = H = 64
    px = [[(0, 0, 0, 0)] * W for _ in range(H)]

    def dist_seg(px_, py_, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px_ - x1, py_ - y1)
        t = max(0.0, min(1.0, ((px_ - x1) * dx + (py_ - y1) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px_ - (x1 + t * dx), py_ - (y1 + t * dy))

    for y in range(H):
        for x in range(W):
            if (17 <= x <= 22 and 32 <= y <= 56) or (42 <= x <= 47 and 18 <= y <= 56):
                px[y][x] = (21, 101, 192, 255)          # 立柱（蓝）
            elif dist_seg(x, y, 17, 32, 47, 18) <= 3.2:
                px[y][x] = (21, 101, 192, 255)          # 斜梁（蓝）
            elif dist_seg(x, y, 22, 56, 29, 30) <= 2.0:
                px[y][x] = (198, 40, 40, 255)           # 斜撑（红）
            elif dist_seg(x, y, 22, 29, 26, 28) <= 1.6 or dist_seg(x, y, 38, 21, 42, 20) <= 1.6:
                px[y][x] = (67, 160, 71, 255)           # 檩条（绿）
            elif 10 <= x <= 54 and 56 <= y <= 57:
                px[y][x] = (158, 158, 158, 255)         # 地面（灰）

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

        root.title("光伏支架线模生成器 V1.2.17")
        root.geometry("1120x820")
        root.resizable(False, False)
        try:
            root.option_add("*Font", ("Microsoft YaHei UI", 10))
            icon = tk.PhotoImage(data=ICON_PNG_B64)
            root.iconphoto(True, icon)
        except tk.TclError:
            pass
        ttk.Style().theme_use("clam")

        self._load_city_data()
        self._load_seismic_data()
        self._build_top_bar()
        self._build_main_area()
        self._build_status_bar()
        self._bind_calc_events()
        self.apply_params(DEFAULT_PARAMS)
        self.set_status("就绪 V1.2.17：梁中心偏移150修正立柱高度；斜撑长度联动")

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
            e1 = ttk.Entry(grp, textvariable=self.vars[key1], width=5, justify="right")
            e1.grid(row=row, column=1, sticky="w", padx=(4, 2))
            if unit1:
                ttk.Label(grp, text=unit1).grid(row=row, column=2, sticky="w", padx=(0, 8))
            ttk.Label(grp, text=label2).grid(row=row, column=3, sticky="w", pady=2)
            self.vars[key2] = tk.StringVar()
            e2 = ttk.Entry(grp, textvariable=self.vars[key2], width=5, justify="right")
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
        self.calc_entries += pair(5, "背板孔距", "module_hole_pitch", "mm",
                                     " ", "", " ")

        self.calc_label = ttk.Label(
            grp, foreground="#1565c0", font=("Microsoft YaHei UI", 9, "bold"),
            justify="left",
        )
        self.calc_label.grid(row=6, column=0, columnspan=6, sticky="w", pady=(4, 0))

    # -------------------------------------------------------- ② 支架形式
    def _build_support_group(self, parent):
        grp = ttk.LabelFrame(
            parent, text="② 支架形式（侧面示意 · 滚轮缩放 / 右键平移）",
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

        def pair(row, label1, key1, unit1, label2, key2, unit2):
            ttk.Label(grp, text=label1).grid(row=row, column=0, sticky="w", pady=2)
            self.vars[key1] = tk.StringVar()
            e1 = ttk.Entry(grp, textvariable=self.vars[key1], width=5, justify="right")
            e1.grid(row=row, column=1, sticky="w", padx=(4, 2))
            if unit1:
                ttk.Label(grp, text=unit1).grid(row=row, column=2, sticky="w", padx=(0, 6))
            ttk.Label(grp, text=label2).grid(row=row, column=3, sticky="w", pady=2)
            self.vars[key2] = tk.StringVar()
            e2 = ttk.Entry(grp, textvariable=self.vars[key2], width=5, justify="right")
            e2.grid(row=row, column=4, sticky="w", padx=(4, 2))
            if unit2:
                ttk.Label(grp, text=unit2).grid(row=row, column=5, sticky="w")
            return [e1, e2]

        self.calc_entries += pair(2, "最低点", "layout_ground_gap", "mm",
                                     "倾角", "layout_tilt", "度")
        self.calc_entries += pair(3, "前斜撑距梁端", "brace_front_off", "mm",
                                     "后斜撑距梁端", "brace_rear_off", "mm")
        ttk.Label(grp, text="端距").grid(row=4, column=0, sticky="w", pady=2)
        self.vars["purlin_end_offset"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["purlin_end_offset"], width=5, justify="right")
        e.grid(row=4, column=1, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)
        ttk.Label(grp, text="mm").grid(row=4, column=2, sticky="w", padx=(0, 6))

        ttk.Label(grp, text="梁中心偏移").grid(row=4, column=3, sticky="w", pady=2)
        self.vars["beam_center_offset"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["beam_center_offset"], width=5, justify="right")
        e.grid(row=4, column=4, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)
        ttk.Label(grp, text="mm").grid(row=4, column=5, sticky="w")

        ttk.Label(grp, text="柱距").grid(row=5, column=0, sticky="w", pady=2)
        self.vars["struct_bay"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["struct_bay"], width=5, justify="right")
        e.grid(row=5, column=1, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)
        ttk.Label(grp, text="mm").grid(row=5, column=2, sticky="w", padx=(0, 6))

        ttk.Label(grp, text="榀数").grid(row=5, column=3, sticky="w", pady=2)
        self.vars["struct_frames"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["struct_frames"], width=5, justify="right")
        e.grid(row=5, column=4, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)
        ttk.Label(grp, text="榀").grid(row=5, column=5, sticky="w")

        self.frame_warn_label = ttk.Label(
            grp, foreground="#c62828", font=("Microsoft YaHei UI", 9, "bold"),
            wraplength=430, justify="left",
        )
        self.frame_warn_label.grid(row=6, column=0, columnspan=6, sticky="w", pady=(2, 0))

        ttk.Label(grp, text="斜撑离地").grid(row=7, column=0, sticky="w", pady=2)
        self.vars["brace_ground"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["brace_ground"], width=5, justify="right")
        e.grid(row=7, column=1, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)
        ttk.Label(grp, text="mm").grid(row=7, column=2, sticky="w", padx=(0, 6))

        ttk.Label(grp, text="檩条外伸").grid(row=7, column=3, sticky="w", pady=2)
        self.vars["purlin_extension"] = tk.StringVar()
        e = ttk.Entry(grp, textvariable=self.vars["purlin_extension"], width=5, justify="right")
        e.grid(row=7, column=4, sticky="w", padx=(4, 2))
        self.calc_entries.append(e)
        ttk.Label(grp, text="mm").grid(row=7, column=5, sticky="w")

        ttk.Label(grp, text="檩条悬挑").grid(row=8, column=0, sticky="w", pady=2)
        self.overhang_entry = ttk.Entry(grp, width=5, state="disabled", justify="right")
        self.overhang_entry.grid(row=8, column=1, sticky="w", padx=(4, 2))
        ttk.Label(grp, text="mm").grid(row=8, column=2, sticky="w", padx=(0, 6))

        self.overhang_warn_label = ttk.Label(
            grp, foreground="#c62828", font=("Microsoft YaHei UI", 9, "bold"),
            wraplength=430, justify="left",
        )
        self.overhang_warn_label.grid(row=9, column=0, columnspan=6, sticky="w", pady=(2, 0))

        ttk.Label(grp, text="斜梁长度").grid(row=10, column=0, sticky="w", pady=(2, 0))
        self.beam_len_entry = ttk.Entry(grp, width=5, state="disabled", justify="right")
        self.beam_len_entry.grid(row=10, column=1, sticky="w", padx=(4, 2))
        ttk.Label(grp, text="mm").grid(row=10, column=2, sticky="w", padx=(0, 6))

        ttk.Label(grp, text="檩条总长").grid(row=11, column=0, sticky="w", pady=(2, 0))
        self.purlin_len_entry = ttk.Entry(grp, width=5, state="disabled", justify="right")
        self.purlin_len_entry.grid(row=11, column=1, sticky="w", padx=(4, 2))
        ttk.Label(grp, text="mm").grid(row=11, column=2, sticky="w", padx=(0, 6))

        ttk.Label(grp, text="立柱高度").grid(row=12, column=0, sticky="w", pady=(2, 0))
        self.col_h_entry = ttk.Entry(grp, width=5, state="disabled", justify="right")
        self.col_h_entry.grid(row=12, column=1, sticky="w", padx=(4, 2))
        ttk.Label(grp, text="mm").grid(row=12, column=2, sticky="w", padx=(0, 6))

        ttk.Label(grp, text="前斜撑长").grid(row=13, column=0, sticky="w", pady=(2, 0))
        self.front_brace_len_entry = ttk.Entry(grp, width=5, state="disabled", justify="right")
        self.front_brace_len_entry.grid(row=13, column=1, sticky="w", padx=(4, 2))
        ttk.Label(grp, text="mm").grid(row=13, column=2, sticky="w", padx=(0, 6))
        ttk.Label(grp, text="后斜撑长").grid(row=13, column=3, sticky="w", pady=(2, 0))
        self.rear_brace_len_entry = ttk.Entry(grp, width=5, state="disabled", justify="right")
        self.rear_brace_len_entry.grid(row=13, column=4, sticky="w", padx=(4, 2))
        ttk.Label(grp, text="mm").grid(row=13, column=5, sticky="w")

        # 右列单位列弹性拉伸，保证单位标签不被右侧裁切
        grp.columnconfigure(5, weight=1)

    # ------------------------------------------------------ ③ 构件截面表
    def _build_section_group(self, parent):
        grp = ttk.LabelFrame(parent, text="③ 构件截面表", padding=(8, 4))
        grp.pack(fill="x")

        ttk.Label(grp, text="构件", anchor="center").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Label(grp, text="规格", anchor="center").grid(row=0, column=1, sticky="ew", padx=(0, 4))
        ttk.Label(grp, text="型号", anchor="center").grid(row=0, column=2, sticky="ew", padx=(0, 6))
        ttk.Label(grp, text="材质等级", anchor="center").grid(row=0, column=3, sticky="ew")
        grp.columnconfigure(2, weight=1)

        self.section_spec_cbs = {}
        self.section_model_cbs = {}
        for i, (role, spec_default, model_default, mat_default) in enumerate(MEMBER_ROLES, start=1):
            ttk.Label(grp, text=role).grid(row=i, column=0, sticky="w", pady=1)

            self.vars[f"sec_{role}_spec"] = tk.StringVar()
            spec_cb = ttk.Combobox(
                grp, textvariable=self.vars[f"sec_{role}_spec"],
                values=SPEC_TYPES, state="readonly", width=5,
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

        self.view_yaw = math.pi - 0.6
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
            box = tk.Label(legend, bg=color, width=1)
            box.pack(side="left", padx=(4, 1), pady=1)
            ttk.Label(legend, text=role, font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(0, 5))

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
            e = ttk.Entry(grp, textvariable=self.vars[key], width=5, justify="right")
            e.grid(row=row, column=col * 2 + 1, sticky="w", padx=(2, 6))
            if unit:
                ttk.Label(grp, text=unit).grid(row=row, column=col * 2 + 2, sticky="w", padx=(0, 6))
            return e

        # 上段：城市查表（省/市/区县/抗震设防 一行）
        ttk.Label(
            grp, text="城市查表（50年重现期）· 抗震设防", foreground="#616161",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=12, sticky="w", pady=(0, 2))

        self.vars["city_prov"] = tk.StringVar()
        self.prov_cb = ttk.Combobox(
            grp, textvariable=self.vars["city_prov"],
            values=[MANUAL_PROVINCE] + [prov_display(k) for k in sorted(self.city_data.keys())],
            state="readonly", width=5,
        )
        self.prov_cb.grid(row=1, column=0, sticky="w", padx=(0, 4))
        self.prov_cb.bind("<<ComboboxSelected>>", self._on_province_change)
        ttk.Label(grp, text="省").grid(row=1, column=1, sticky="w", pady=2, padx=(0, 8))

        self.vars["city_name"] = tk.StringVar()
        self.city_cb = ttk.Combobox(
            grp, textvariable=self.vars["city_name"], state="readonly", width=9,
        )
        self.city_cb.grid(row=1, column=2, sticky="w", padx=(0, 4))
        self.city_cb.bind("<<ComboboxSelected>>", self._on_city_change)
        ttk.Label(grp, text="市").grid(row=1, column=3, sticky="w", pady=2, padx=(0, 8))

        self.vars["city_district"] = tk.StringVar()
        self.district_cb = ttk.Combobox(
            grp, textvariable=self.vars["city_district"], state="disabled", width=10,
        )
        self.district_cb.grid(row=1, column=4, sticky="w", padx=(0, 4))
        self.district_cb.bind("<<ComboboxSelected>>", self._on_district_change)
        ttk.Label(grp, text="区县").grid(row=1, column=5, sticky="w", pady=2, padx=(0, 8))

        ttk.Label(grp, text="抗震设防").grid(row=1, column=6, sticky="w", pady=2)
        self.vars["seismic"] = tk.StringVar()
        ttk.Combobox(
            grp, textvariable=self.vars["seismic"],
            values=SEISMIC_OPTIONS, state="readonly", width=9,
        ).grid(row=1, column=7, sticky="w", padx=(2, 8))

        self.city_result_label = ttk.Label(
            grp, foreground="#1565c0", font=("Microsoft YaHei UI", 8, "bold"),
        )
        self.city_result_label.grid(row=10, column=0, columnspan=12, sticky="w", pady=(2, 0))

        # 下段：基本荷载 + 风压系数
        ttk.Label(
            grp, text="基本荷载", foreground="#616161",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 2))
        ttk.Label(
            grp, text="风压系数", foreground="#616161",
            font=("Microsoft YaHei UI", 9, "bold"),
        ).grid(row=3, column=4, columnspan=3, sticky="w", pady=(6, 2))

        entry(4, 0, "恒载", "load_dead", 0.05, "kN/m²")
        self.snow_entry = entry(5, 0, "雪载", "load_snow", 0.20, "kN/m²")
        self.wind_base_entry = entry(6, 0, "基本风压", "load_wind_base", 0.35, "kN/m²")

        ttk.Label(grp, text="地面粗糙度").grid(row=7, column=0, sticky="w", pady=2)
        self.vars["load_roughness"] = tk.StringVar()
        ttk.Combobox(
            grp, textvariable=self.vars["load_roughness"],
            values=ROUGHNESS_OPTIONS, state="readonly", width=5,
        ).grid(row=7, column=1, sticky="w", padx=(2, 6))

        ttk.Label(grp, text="场地类别").grid(row=8, column=0, sticky="w", pady=2)
        self.vars["site_class"] = tk.StringVar()
        ttk.Combobox(
            grp, textvariable=self.vars["site_class"],
            values=["Ⅰ类", "Ⅱ类", "Ⅲ类", "Ⅳ类"], state="readonly", width=5,
        ).grid(row=8, column=1, sticky="w", padx=(2, 6))

        entry(4, 2, "风压高度系数", "load_mu_z", 1.10)
        entry(5, 2, "阵风系数", "load_beta_z", 1.00)
        entry(6, 2, "正风压体型系数", "load_mu_s_pos", 1.30)
        entry(7, 2, "负风压体型系数", "load_mu_s_neg", -1.30)
        coast_frame = ttk.Frame(grp)
        coast_frame.grid(row=8, column=4, columnspan=3, sticky="w", pady=2)
        panel_bg = ttk.Style().lookup("TFrame", "background")
        self.vars["load_coastal_enabled"] = tk.BooleanVar(value=False)
        tk.Checkbutton(
            coast_frame, text="沿海城市风压放大系数", variable=self.vars["load_coastal_enabled"],
            command=self._toggle_coastal, bg=panel_bg, activebackground=panel_bg,
            relief="flat", bd=0, highlightthickness=0,
        ).pack(side="left")
        self.vars["load_coastal"] = tk.StringVar()
        self.coastal_entry = ttk.Entry(
            coast_frame, textvariable=self.vars["load_coastal"], width=5, justify="right",
        )
        self.coastal_entry.pack(side="left", padx=(4, 0))

        ttk.Label(
            grp, foreground="#757575",
            text="沿海风压放大按需勾选；选定城市后风压/雪载锁定；抗震烈度按省-市-区县自动匹配",
            wraplength=1000,
        ).grid(row=9, column=0, columnspan=12, sticky="w", pady=(4, 0))

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

    def _load_seismic_data(self):
        self.seismic_data = {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "抗震设防数据.json")
        try:
            with open(path, "r", encoding="utf-8") as fp:
                self.seismic_data = json.load(fp).get("data", {})
        except (OSError, json.JSONDecodeError):
            self.seismic_data = {}

    @staticmethod
    def _norm_prov(name):
        return (name.replace("省", "").replace("壮族", "").replace("回族", "")
                .replace("维吾尔", "").replace("自治区", "").replace("特别行政区", ""))

    def _set_load_locked(self, locked):
        state = "disabled" if locked else "normal"
        self.wind_base_entry.configure(state=state)
        self.snow_entry.configure(state=state)

    def _toggle_coastal(self):
        if not self.vars["load_coastal_enabled"].get():
            self.vars["load_coastal"].set("1.00")

    def _on_province_change(self, _event=None):
        prov_disp = self.vars["city_prov"].get()
        if prov_disp == MANUAL_PROVINCE:
            self.vars["city_name"].set("")
            self.city_cb.configure(values=[])
            self.city_result_label.config(text="手动输入模式（风压/雪载可编辑）")
            self._set_load_locked(False)
            self.district_cb.configure(values=[], state="disabled")
            self.vars["city_district"].set("")
            return
        prov = prov_key(prov_disp)
        cities = sorted(self.city_data.get(prov, {}).keys())
        self.city_cb.configure(values=cities)
        if cities:
            self.vars["city_name"].set(cities[0])
            self._on_city_change()
        else:
            self.vars["city_name"].set("")
            self.city_result_label.config(text="该省暂无城市数据")

    def _on_city_change(self, _event=None):
        prov = prov_key(self.vars["city_prov"].get())
        city = self.vars["city_name"].get()
        rec = self.city_data.get(prov, {}).get(city)
        if not rec:
            return
        self.vars["load_wind_base"].set(str(rec["w50"]))
        self.vars["load_snow"].set(str(rec["s50"]))
        self.city_result_label.config(
            text=f"风压 {rec['w50']} · 雪压 {rec['s50']} kN/m²（规范值，已锁定）"
        )
        self._set_load_locked(True)
        # 区县级抗震数据（若有）
        se_city = self.seismic_data.get(self._norm_prov(prov), {}).get(city, {})
        se_districts = se_city.get("districts", [])
        if se_districts:
            self.district_cb.configure(values=se_districts, state="readonly")
            self.vars["city_district"].set("")
            best = max(se_city.get("entries", []), key=lambda e: len(e.get("districts", [])))
            if best.get("intensity") in SEISMIC_OPTIONS:
                self.vars["seismic"].set(best["intensity"])
        else:
            self.district_cb.configure(values=[], state="disabled")
            self.vars["city_district"].set("")

    def _on_district_change(self, _event=None):
        prov = prov_key(self.vars["city_prov"].get())
        city = self.vars["city_name"].get()
        district = self.vars["city_district"].get()
        se_city = self.seismic_data.get(self._norm_prov(prov), {}).get(city, {})
        for e in se_city.get("entries", []):
            if district in e.get("districts", []):
                if e.get("intensity") in SEISMIC_OPTIONS:
                    self.vars["seismic"].set(e["intensity"])
                break

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
            e.bind("<FocusOut>", lambda ev: (self.update_calc(), ev.widget.selection_clear()))

    # ------------------------------------------------------------ 支架示意交互
    def _profile_wheel(self, event):
        factor = 1.12 if event.delta > 0 else 1 / 1.12
        self.profile_zoom = max(0.3, min(3.5, self.profile_zoom * factor))
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
                text=f"组件阵列宽 {total_width:.0f} mm　组件阵列长 {total_length:.0f} mm\n"
                     f"阵列功率 ≈ {power_kw:.2f} kW（{count} 块 × {power:.0f} W）"
            )
            frames = int(float(self.vars["struct_frames"].get()))
            bay = float(self.vars["struct_bay"].get())
            extension = float(self.vars["purlin_extension"].get())
            geo = self._profile_geometry()
            beam_len = geo[0] if geo else 0.0
            purlin_n = max(2, rows * 2)
            self.beam_len_entry.configure(state="normal")
            self.beam_len_entry.delete(0, "end")
            self.beam_len_entry.insert(0, f"{beam_len:.0f}")
            self.beam_len_entry.configure(state="disabled")
            purlin_total = total_length + 2 * extension
            overhang = (purlin_total - frames * bay) / 2
            self.overhang_entry.configure(state="normal")
            self.overhang_entry.delete(0, "end")
            self.overhang_entry.insert(0, f"{overhang:.0f}")
            self.overhang_entry.configure(state="disabled")
            self.purlin_len_entry.configure(state="normal")
            self.purlin_len_entry.delete(0, "end")
            self.purlin_len_entry.insert(0, f"{purlin_total:.0f}")
            self.purlin_len_entry.configure(state="disabled")
            # 立柱高度与前后斜撑长度（余弦定理）
            alpha = math.radians(tilt)
            beam_half = beam_len / 2
            brace_ground = float(self.vars["brace_ground"].get())
            front_off = float(self.vars["brace_front_off"].get())
            rear_off = float(self.vars["brace_rear_off"].get())
            beam_off = float(self.vars["beam_center_offset"].get())
            ground_beam = ground - beam_off
            if self.vars["support_type"].get() == "单立柱":
                col_front_h = col_rear_h = ground_beam + beam_half * math.sin(alpha)
                front_side = max(0.0, beam_half - front_off)
                rear_side = max(0.0, beam_half - rear_off)
            else:
                col_front_h = ground_beam
                col_rear_h = ground_beam + beam_len * math.sin(alpha)
                front_side = max(0.0, front_off)
                rear_side = max(0.0, rear_off)
            front_v = max(0.0, col_front_h - brace_ground)
            rear_v = max(0.0, col_rear_h - brace_ground)
            front_len = math.sqrt(max(0.0, front_v ** 2 + front_side ** 2
                                      - 2 * front_v * front_side * math.cos(math.radians(90 - tilt))))
            rear_len = math.sqrt(max(0.0, rear_v ** 2 + rear_side ** 2
                                     - 2 * rear_v * rear_side * math.cos(math.radians(90 + tilt))))
            for entry, val in ((self.col_h_entry, col_front_h),
                               (self.front_brace_len_entry, front_len),
                               (self.rear_brace_len_entry, rear_len)):
                entry.configure(state="normal")
                entry.delete(0, "end")
                entry.insert(0, f"{val:.0f}")
                entry.configure(state="disabled")
            if overhang < 0:
                self.overhang_warn_label.config(
                    text=f"⚠ 悬挑为负（{overhang:.0f} mm）：柱距×品数超出檩条总长，"
                         f"请减小柱距或品数"
                )
            elif overhang > 800:
                self.overhang_warn_label.config(
                    text=f"⚠ 檩条悬挑 {overhang:.0f} mm ＞ 800 mm：柱距或品数过少，"
                         f"请增大柱距或品数"
                )
            else:
                self.overhang_warn_label.config(text="")
            frames_len = frames * bay
            if frames_len > total_length:
                self.frame_warn_label.config(
                    text=f"⚠ 榀数×柱距 = {frames_len:.0f} mm ＞ 组件阵列总长 "
                         f"{total_length:.0f} mm，请减小榀数或柱距"
                )
            else:
                self.frame_warn_label.config(text="")
            self.draw_profile()
            self.draw_viewer()
        except (ValueError, tk.TclError):
            self.calc_label.config(text="组件总宽/总长：参数不完整")
            self.beam_len_entry.configure(state="normal")
            self.beam_len_entry.delete(0, "end")
            self.beam_len_entry.insert(0, "")
            self.beam_len_entry.configure(state="disabled")
            self.overhang_entry.configure(state="normal")
            self.overhang_entry.delete(0, "end")
            self.overhang_entry.insert(0, "")
            self.overhang_entry.configure(state="disabled")
            self.purlin_len_entry.configure(state="normal")
            self.purlin_len_entry.delete(0, "end")
            self.purlin_len_entry.insert(0, "")
            self.purlin_len_entry.configure(state="disabled")
            for entry in (self.col_h_entry, self.front_brace_len_entry, self.rear_brace_len_entry):
                entry.configure(state="normal")
                entry.delete(0, "end")
                entry.insert(0, "")
                entry.configure(state="disabled")
            self.overhang_warn_label.config(text="")
            self.frame_warn_label.config(text="")

    # ------------------------------------------------------------ 几何辅助
    def _profile_geometry(self):
        try:
            end_offset = float(self.vars["purlin_end_offset"].get())
            tilt = float(self.vars["layout_tilt"].get())
            ground = float(self.vars["layout_ground_gap"].get())
            beam_off = float(self.vars["beam_center_offset"].get())
        except (ValueError, tk.TclError):
            return None
        # 斜梁长度 = 檩条总跨度 + 端距×2（檩条位置由组件背板孔距推导），取整到10mm
        positions = self._purlin_positions()
        if positions:
            slope = (positions[-1] - positions[0]) + 2 * end_offset
        else:
            slope = 2 * end_offset
        slope = max(1.0, round(slope / 10.0) * 10.0)
        a = math.radians(tilt)
        span = slope * math.cos(a)
        rise = slope * math.sin(a)
        if span <= 0:
            return None
        # 斜梁中心线低于组件最低点（檩条+组件坐落在斜梁上）
        ground = ground - beam_off
        return slope, span, rise, ground, a

    def _purlin_positions(self):
        """檩条位置：按组件背板开孔排布。
        每行组件两道檩条（距组件底边 0 与 背板孔距处），行间加组件间隙。"""
        try:
            rows = int(float(self.vars["layout_rows"].get()))
            L = float(self.vars["module_L"].get())
            gap = float(self.vars["layout_gap"].get())
            pitch = float(self.vars["module_hole_pitch"].get())
            end_offset = float(self.vars["purlin_end_offset"].get())
        except (ValueError, tk.TclError):
            rows, L, gap, pitch, end_offset = 2, 2278, 20, 1400, 150
        pos = set()
        for i in range(max(1, rows)):
            base = end_offset + i * (L + gap)
            pos.add(base)
            pos.add(base + pitch)
        return sorted(pos)

    # ------------------------------------------------------------ 侧面示意
    def draw_profile(self):
        """② 支架形式：侧面示意图。单立柱立于斜梁中心正下方，双立柱在两端。"""
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
            brace_front_off = float(self.vars["brace_front_off"].get())
            brace_rear_off = float(self.vars["brace_rear_off"].get())
            brace_ground = float(self.vars["brace_ground"].get())
        except (ValueError, tk.TclError):
            brace_front_off, brace_rear_off, brace_ground = 350, 350, 300

        maxh = ground + rise
        m = 44
        base_scale = min((cw - 2 * m) / span, (ch - 2 * m) / maxh)
        scale = base_scale * self.profile_zoom

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

        double_col = self.vars["support_type"].get() == "单桩双立柱"
        if double_col:
            # 双立柱：前后两端
            c.create_line(*P(0, 0), ax, ay, fill=MEMBER_COLORS["立柱"], width=3)
            c.create_line(*P(span, 0), bx, by, fill=MEMBER_COLORS["立柱"], width=3)
            if 0 < brace_front_off < slope:
                fx, fy = P(brace_front_off * math.cos(a), ground + brace_front_off * math.sin(a))
                c.create_line(*P(0, brace_ground), fx, fy, fill=MEMBER_COLORS["斜撑"], width=2)
            if 0 < brace_rear_off < slope:
                t_rear = slope - brace_rear_off
                rx, ry = P(t_rear * math.cos(a), ground + t_rear * math.sin(a))
                c.create_line(*P(span, brace_ground), rx, ry, fill=MEMBER_COLORS["斜撑"], width=2)
        else:
            # 单立柱：立于斜梁中心正下方（支架左右平衡）
            mid_x = span / 2
            mid_z = ground + rise / 2
            c.create_line(*P(mid_x, 0), *P(mid_x, mid_z), fill=MEMBER_COLORS["立柱"], width=3)
            if 0 < brace_front_off < slope:
                bx2, by2 = P(brace_front_off * math.cos(a), ground + brace_front_off * math.sin(a))
                c.create_line(*P(mid_x, brace_ground), bx2, by2, fill=MEMBER_COLORS["斜撑"], width=2)
            if 0 < brace_rear_off < slope:
                t_r = slope - brace_rear_off
                rx2, ry2 = P(t_r * math.cos(a), ground + t_r * math.sin(a))
                c.create_line(*P(mid_x, brace_ground), rx2, ry2, fill=MEMBER_COLORS["斜撑"], width=2)

        for t in self._purlin_positions():
            px, py = P(t * math.cos(a), ground + t * math.sin(a))
            nx, ny = -math.sin(a), math.cos(a)
            tick = max(8, scale * 80)
            c.create_line(
                px - nx * tick, py - ny * tick,
                px + nx * tick, py + ny * tick,
                fill=MEMBER_COLORS["檩条"], width=2,
            )

        # 倾角：固定显示在画布右上角，不随缩放/平移移动
        c.create_text(
            cw - 34, 14, anchor="ne", text=f"倾角 {math.degrees(a):.0f}度",
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
                text=f"缩放 {self.profile_zoom:.1f}× · 右键平移",
                font=("Microsoft YaHei UI", 8),
            )

    # ------------------------------------------------------------ 3D 预览
    def draw_viewer(self):
        """④ 3D 线框预览：按品数生成多榀，转盘式旋转（Z 轴保持竖直）。"""
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
            frames = int(float(self.vars["struct_frames"].get()))
            brace_front_off = float(self.vars["brace_front_off"].get())
            brace_rear_off = float(self.vars["brace_rear_off"].get())
            brace_ground = float(self.vars["brace_ground"].get())
        except (ValueError, tk.TclError):
            bay, frames, brace_front_off, brace_rear_off, brace_ground = 2000, 3, 350, 350, 300

        frames = max(1, min(12, frames))
        maxh = ground + rise
        double_col = self.vars["support_type"].get() == "单桩双立柱"

        def beam_pt(t, y):
            return (t * math.cos(a), y, ground + t * math.sin(a))

        lines = []
        frame_ys = [(i - (frames - 1) / 2) * bay for i in range(frames)]
        for y in frame_ys:
            if double_col:
                lines.append(((0, y, 0), (0, y, ground), MEMBER_COLORS["立柱"]))
                lines.append(((span, y, 0), (span, y, ground + rise), MEMBER_COLORS["立柱"]))
                lines.append(((0, y, ground), (span, y, ground + rise), MEMBER_COLORS["斜梁"]))
                if 0 < brace_front_off < slope:
                    p = beam_pt(brace_front_off, y)
                    lines.append(((0, y, brace_ground), (p[0], y, p[2]), MEMBER_COLORS["斜撑"]))
                if 0 < brace_rear_off < slope:
                    p = beam_pt(slope - brace_rear_off, y)
                    lines.append(((span, y, brace_ground), (p[0], y, p[2]), MEMBER_COLORS["斜撑"]))
            else:
                # 单立柱：斜梁中心正下方
                mid_x = span / 2
                mid_z = ground + rise / 2
                lines.append(((mid_x, y, 0), (mid_x, y, mid_z), MEMBER_COLORS["立柱"]))
                lines.append(((0, y, ground), (span, y, ground + rise), MEMBER_COLORS["斜梁"]))
                if 0 < brace_front_off < slope:
                    p = beam_pt(brace_front_off, y)
                    lines.append(((mid_x, y, brace_ground), (p[0], y, p[2]), MEMBER_COLORS["斜撑"]))
                if 0 < brace_rear_off < slope:
                    p = beam_pt(slope - brace_rear_off, y)
                    lines.append(((mid_x, y, brace_ground), (p[0], y, p[2]), MEMBER_COLORS["斜撑"]))

        # 檩条：横跨所有品
        y0, y1 = frame_ys[0], frame_ys[-1]
        for t in self._purlin_positions():
            p = beam_pt(t, 0)
            lines.append(((p[0], y0, p[2]), (p[0], y1, p[2]), MEMBER_COLORS["檩条"]))

        # 地面框
        lines.append(((0, y0, 0), (span, y0, 0), "#9e9e9e", (4, 3)))
        lines.append(((span, y0, 0), (span, y1, 0), "#9e9e9e", (4, 3)))
        lines.append(((span, y1, 0), (0, y1, 0), "#9e9e9e", (4, 3)))
        lines.append(((0, y1, 0), (0, y0, 0), "#9e9e9e", (4, 3)))

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

        total_depth = max(abs(y0), abs(y1)) * 2
        maxdim = max(span, total_depth, maxh, 1.0)
        scale = min(w, h) / maxdim * 0.62 * self.view_zoom
        cx, cy = w / 2 + self.view_pan_x, h / 2 + self.view_pan_y

        def proj(x, y, z):
            x1, y1, z1 = transform(x, y, z)
            return cx + x1 * scale, cy - z1 * scale * cp + y1 * scale * sp

        for item in lines:
            if len(item) == 4:
                p1, p2, color, dash = item
                c.create_line(*proj(*p1), *proj(*p2), fill=color, width=1, dash=dash)
            else:
                p1, p2, color = item
                c.create_line(*proj(*p1), *proj(*p2), fill=color, width=2)

        # 左下角独立小坐标（与支架分离，随旋转联动）
        bx0, by0 = 26.0, h - 46.0
        o = transform(cxw, 0.0, czw)
        for vx, vy, vz, color, label in (
            (maxdim * 0.3, 0, 0, "#e53935", "X"),
            (0, maxdim * 0.3, 0, "#43a047", "Y"),
            (0, 0, maxdim * 0.3, "#1e88e5", "Z"),
        ):
            v = transform(cxw + vx, 0.0 + vy, czw + vz)
            dx = (v[0] - o[0]) * scale
            dy = -(v[2] - o[2]) * scale * cp + (v[1] - o[1]) * scale * sp
            ln = math.hypot(dx, dy) or 1.0
            ex, ey = dx / ln * 34, dy / ln * 34
            c.create_line(bx0, by0, bx0 + ex, by0 + ey, fill=color, width=2)
            lx, ly = bx0 + ex / 34 * 43, by0 + ey / 34 * 43
            c.create_text(lx, ly - 4, text=label, fill=color,
                          font=("Microsoft YaHei UI", 9, "bold"))

        c.create_text(
            cx, h - 10, fill="#757575",
            text=f"{frames} 榀 · 中键旋转（Z轴竖直）· 右键平移 · 滚轮缩放",
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
                "hole_pitch": f("module_hole_pitch"),
            },
            "layout": {
                "rows": i("layout_rows"), "cols": i("layout_cols"),
                "tilt": tilt, "gap": f("layout_gap"),
                "ground_gap": f("layout_ground_gap"),
            },
            "structure": {
                "type": self.vars["support_type"].get(),
                "bay": f("struct_bay"), "frames": i("struct_frames"),
                "purlin_end_offset": f("purlin_end_offset"),
                "purlin_extension": f("purlin_extension"),
                "beam_center_offset": f("beam_center_offset"),
                "brace_ground": f("brace_ground"),
                "brace_front_off": f("brace_front_off"),
                "brace_rear_off": f("brace_rear_off"),
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
                "site_class": self.vars["site_class"].get(),
                "mu_z": f("load_mu_z"),
                "beta_z": f("load_beta_z"),
                "coastal": f("load_coastal") if self.vars["load_coastal_enabled"].get() else 1.0,
                "coastal_enabled": self.vars["load_coastal_enabled"].get(),
                "mu_s_pos": f("load_mu_s_pos"),
                "mu_s_neg": f("load_mu_s_neg"),
                "seismic": self.vars["seismic"].get(),
                "city": {
                    "province": self.vars["city_prov"].get(),
                    "city": self.vars["city_name"].get(),
                    "district": self.vars["city_district"].get(),
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
        setv("module_hole_pitch", mod.get("hole_pitch", 1400))
        lay = params.get("layout", {})
        setv("layout_rows", lay.get("rows", 2))
        setv("layout_cols", lay.get("cols", 15))
        setv("layout_tilt", lay.get("tilt", 20))
        setv("layout_gap", lay.get("gap", 20))
        setv("layout_ground_gap", lay.get("ground_gap", 1000))
        st = params.get("structure", {})
        setv("struct_bay", st.get("bay", 2000))
        # 品数（兼容旧字段 array_rows）
        setv("struct_frames", st.get("frames", st.get("array_rows", 3)))
        setv("purlin_end_offset", st.get("purlin_end_offset", 150))
        setv("purlin_extension", st.get("purlin_extension", 150))
        setv("beam_center_offset", st.get("beam_center_offset", 150))
        setv("brace_ground", st.get("brace_ground", 300))
        setv("brace_front_off", st.get("brace_front_off", 350))
        setv("brace_rear_off", st.get("brace_rear_off", 350))
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
        setv("site_class", ld.get("site_class", "Ⅱ类"))
        setv("load_mu_z", ld.get("mu_z", 1.10))
        setv("load_beta_z", ld.get("beta_z", 1.00))
        coastal_enabled = ld.get("coastal_enabled", False)
        self.vars["load_coastal_enabled"].set(bool(coastal_enabled))
        self._toggle_coastal()
        setv("load_coastal", ld.get("coastal", 1.10))
        setv("load_mu_s_pos", ld.get("mu_s_pos", 1.30))
        setv("load_mu_s_neg", ld.get("mu_s_neg", -1.30))
        setv("seismic", ld.get("seismic", "7度(0.10g)"))
        city = ld.get("city", {})
        ckey = city.get("province", "")
        pkey = ckey if ckey in self.city_data else prov_key(ckey)
        if pkey in self.city_data:
            setv("city_prov", prov_display(pkey))
            cities = sorted(self.city_data[pkey].keys())
            self.city_cb.configure(values=cities)
            if city.get("city") in cities:
                setv("city_name", city["city"])
                self._on_city_change()
                if city.get("district") in list(self.district_cb.cget("values")):
                    setv("city_district", city["district"])
                    self._on_district_change()
        else:
            # 无城市记录 → 手动输入模式
            self.vars["city_prov"].set(MANUAL_PROVINCE)
            self.vars["city_name"].set("")
            self.city_cb.configure(values=[])
            self.district_cb.configure(values=[], state="disabled")
            self.vars["city_district"].set("")
            self._set_load_locked(False)
            self.city_result_label.config(text="手动输入模式（风压/雪载可编辑）")
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
