# -*- coding: utf-8 -*-
"""
光伏支架线模几何引擎（M2）

输入：界面收集的参数字典（与 pv_support_gui.py 的 collect_params 一致）
输出：节点/杆件线模（build_model）→ DXF 文件（write_dxf，纯手写标准 DXF，
      无第三方依赖，AutoCAD / 3D3S 均可导入）。

坐标系：X=顺坡方向（斜梁低端→高端），Y=阵列方向（沿檩条），Z=高度，单位 mm。
构件：立柱、斜梁、檩条（通长一根）、前/后斜撑；柱脚节点为支座点。
"""

import math


# DXF 图层：名称 -> AutoCAD 颜色号
LAYERS = {
    "L-COLUMN": 2,     # 立柱 黄
    "L-BEAM":   5,     # 斜梁 蓝
    "L-PURLIN": 3,     # 檩条 绿
    "L-BRACE":  6,     # 斜撑 粉/品红
    "L-SUPPORT": 1,    # 支座 红
}

MEMBER_LAYER = {
    "立柱": "L-COLUMN",
    "斜梁": "L-BEAM",
    "檩条": "L-PURLIN",
    "斜撑": "L-BRACE",
}


def default_params():
    """与界面默认值一致的参数字典（供命令行/测试使用）。"""
    return {
        "project": {"name": "某光伏项目", "unit": "mm/kN"},
        "support_type": "单立柱",
        "module": {"lib": "高科545W", "L": 2278, "W": 1134, "T": 35,
                   "weight": 28.5, "power": 545, "hole_pitch": 1400},
        "layout": {"rows": 2, "cols": 15, "tilt": 20, "gap": 20, "ground_gap": 1000},
        "structure": {"type": "单立柱", "bay": 2000, "frames": 9,
                      "purlin_end_offset": 150, "purlin_extension": 150,
                      "beam_center_offset": 150, "brace_ground": 300,
                      "brace_front_off": 350, "brace_rear_off": 350},
    }


def _f(params, key, default=0.0):
    try:
        return float(params[key])
    except (KeyError, TypeError, ValueError):
        return default


def _i(params, key, default=0):
    try:
        return int(float(params[key]))
    except (KeyError, TypeError, ValueError):
        return default


def purlin_positions(params):
    """檩条沿斜梁的位置（t，从斜梁低端量起）。
    每行组件两道檩条（距组件底边 0 与背板孔距处），行间加组件间隙。"""
    module = params.get("module", {})
    layout = params.get("layout", {})
    st = params.get("structure", {})
    rows = max(1, _i(layout, "rows", 2))
    L = _f(module, "L", 2278)
    gap = _f(layout, "gap", 20)
    pitch = _f(module, "hole_pitch", 1400)
    end_offset = _f(st, "purlin_end_offset", 150)
    pos = set()
    for i in range(rows):
        base = end_offset + i * (L + gap)
        pos.add(base)
        pos.add(base + pitch)
    return sorted(pos)


def beam_length(params):
    """斜梁长度 = 檩条总跨度 + 端距×2，取整到 10mm。"""
    st = params.get("structure", {})
    end_offset = _f(st, "purlin_end_offset", 150)
    pos = purlin_positions(params)
    if pos:
        slope = (pos[-1] - pos[0]) + 2 * end_offset
    else:
        slope = 2 * end_offset
    return max(1.0, round(slope / 10.0) * 10.0)


def build_model(params):
    """生成线模：节点字典、杆件列表、支座节点。
    返回 {"nodes": {idx:(x,y,z)}, "members": [(类型,i,j), ...],
          "supports": [idx,...], "info": {...}}"""
    module = params.get("module", {})
    layout = params.get("layout", {})
    st = params.get("structure", {})
    support_type = params.get("support_type", st.get("type", "单立柱"))

    rows = max(1, _i(layout, "rows", 2))
    cols = max(1, _i(layout, "cols", 15))
    L = _f(module, "L", 2278)
    W = _f(module, "W", 1134)
    gap = _f(layout, "gap", 20)
    tilt = _f(layout, "tilt", 20)
    ground_gap = _f(layout, "ground_gap", 1000)

    bay = _f(st, "bay", 2000)
    frames = max(1, min(40, _i(st, "frames", 9)))
    end_offset = _f(st, "purlin_end_offset", 150)
    extension = _f(st, "purlin_extension", 150)
    beam_off = _f(st, "beam_center_offset", 150)
    brace_ground = _f(st, "brace_ground", 300)
    front_off = _f(st, "brace_front_off", 350)
    rear_off = _f(st, "brace_rear_off", 350)

    slope = beam_length(params)
    a = math.radians(tilt)
    span = slope * math.cos(a)
    rise = slope * math.sin(a)
    ground_beam = ground_gap - beam_off          # 斜梁中心线（低于组件最低点）
    purlin_total = cols * W + (cols - 1) * gap + 2 * extension
    purlin_half = purlin_total / 2

    positions = purlin_positions(params)

    def beam_pt(t, y):
        return (t * math.cos(a), y, ground_beam + t * math.sin(a))

    node_keys = {}
    nodes = {}
    members = []

    def add_node(p):
        key = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
        if key not in node_keys:
            idx = len(nodes) + 1
            node_keys[key] = idx
            nodes[idx] = key
        return node_keys[key]

    def add_member(kind, p1, p2):
        members.append((kind, add_node(p1), add_node(p2)))

    frame_ys = [(i - (frames - 1) / 2) * bay for i in range(frames)]
    double_col = support_type == "单桩双立柱"

    for y in frame_ys:
        if double_col:
            # 前柱（低端）与后柱（高端）
            add_member("立柱", (0, y, 0), (0, y, ground_beam))
            add_member("立柱", (span, y, 0), (span, y, ground_beam + rise))
            add_member("斜梁", (0, y, ground_beam), (span, y, ground_beam + rise))
            if 0 < front_off < slope:
                add_member("斜撑", (0, y, brace_ground), beam_pt(front_off, y))
            if 0 < rear_off < slope:
                add_member("斜撑", (span, y, brace_ground), beam_pt(slope - rear_off, y))
        else:
            # 单立柱：斜梁中心正下方
            mid_x = span / 2
            mid_z = ground_beam + rise / 2
            add_member("立柱", (mid_x, y, 0), (mid_x, y, mid_z))
            add_member("斜梁", (0, y, ground_beam), (span, y, ground_beam + rise))
            if 0 < front_off < slope:
                add_member("斜撑", (mid_x, y, brace_ground), beam_pt(front_off, y))
            if 0 < rear_off < slope:
                add_member("斜撑", (mid_x, y, brace_ground), beam_pt(slope - rear_off, y))

    # 檩条：通长一根，横跨全阵列（含外伸），根数 = 行数×2
    for t in positions:
        p = beam_pt(t, 0)
        add_member("檩条", (p[0], -purlin_half, p[2]), (p[0], purlin_half, p[2]))

    # 支座点：所有柱脚
    supports = []
    for y in frame_ys:
        if double_col:
            supports.append(add_node((0, y, 0)))
            supports.append(add_node((span, y, 0)))
        else:
            supports.append(add_node((span / 2, y, 0)))

    info = {
        "support_type": support_type,
        "frames": frames,
        "bay": bay,
        "beam_len": slope,
        "purlin_total": purlin_total,
        "overhang": (purlin_total - (frames - 1) * bay) / 2,
        "member_count": len(members),
        "node_count": len(nodes),
    }
    return {"nodes": nodes, "members": members, "supports": supports, "info": info}


# --------------------------------------------------------------------------
# DXF 导出（优先 ezdxf 生成标准 DXF；无 ezdxf 时回退到完整手写格式）
# --------------------------------------------------------------------------

def write_dxf(params, path):
    model = build_model(params)
    try:
        import ezdxf
    except ImportError:
        _write_dxf_raw(model, path)
        return model
    doc = ezdxf.new("R2000")               # AC1015，AutoCAD 2000 及以上
    doc.units = ezdxf.units.MM
    doc.header["$PDMODE"] = 3              # 支座点显示为交叉点
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    nodes = model["nodes"]
    for kind, i, j in model["members"]:
        msp.add_line(nodes[i], nodes[j], dxfattribs={"layer": MEMBER_LAYER[kind]})
    for idx in model["supports"]:
        msp.add_point(nodes[idx], dxfattribs={"layer": "L-SUPPORT"})
    doc.saveas(path)
    return model


def _write_dxf_raw(model, path):
    """完整手写 DXF（含 BLOCKS/OBJECTS/BLOCK_RECORD 等必需段），作为无 ezdxf 时的回退。"""
    nodes = model["nodes"]
    out = []
    out.append("0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n"
               "9\n$INSUNITS\n70\n4\n9\n$PDMODE\n70\n3\n0\nENDSEC\n")
    # CLASSES（空段）
    out.append("0\nSECTION\n2\nCLASSES\n0\nENDSEC\n")
    # TABLES
    out.append("0\nSECTION\n2\nTABLES\n")
    out.append("0\nTABLE\n2\nLTYPE\n70\n1\n"
               "0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid line\n72\n65\n73\n0\n40\n0.0\n"
               "0\nENDTAB\n")
    out.append("0\nTABLE\n2\nLAYER\n70\n%d\n" % len(LAYERS))
    for name, color in LAYERS.items():
        out.append("0\nLAYER\n2\n%s\n70\n0\n62\n%d\n6\nCONTINUOUS\n" % (name, color))
    out.append("0\nENDTAB\n")
    out.append("0\nTABLE\n2\nSTYLE\n70\n0\n0\nENDTAB\n")
    out.append("0\nTABLE\n2\nVIEW\n70\n0\n0\nENDTAB\n")
    out.append("0\nTABLE\n2\nUCS\n70\n0\n0\nENDTAB\n")
    out.append("0\nTABLE\n2\nAPPID\n70\n1\n"
               "0\nAPPID\n2\nACAD\n70\n0\n0\nENDTAB\n")
    out.append("0\nTABLE\n2\nDIMSTYLE\n70\n1\n"
               "0\nDIMSTYLE\n2\nSTANDARD\n70\n0\n0\nENDTAB\n")
    out.append("0\nTABLE\n2\nBLOCK_RECORD\n70\n1\n"
               "0\nBLOCK_RECORD\n2\n*Model_Space\n0\nENDTAB\n")
    out.append("0\nENDSEC\n")
    # BLOCKS
    out.append("0\nSECTION\n2\nBLOCKS\n"
               "0\nBLOCK\n8\n0\n2\n*Model_Space\n70\n0\n10\n0.0\n20\n0.0\n30\n0.0\n"
               "3\n*Model_Space\n1\n\n0\nENDBLK\n8\n0\n0\nENDSEC\n")
    # ENTITIES
    out.append("0\nSECTION\n2\nENTITIES\n")
    for kind, i, j in model["members"]:
        layer = MEMBER_LAYER[kind]
        x1, y1, z1 = nodes[i]
        x2, y2, z2 = nodes[j]
        out.append("0\nLINE\n8\n%s\n10\n%.3f\n20\n%.3f\n30\n%.3f\n"
                   "11\n%.3f\n21\n%.3f\n31\n%.3f\n" % (layer, x1, y1, z1, x2, y2, z2))
    for idx in model["supports"]:
        x, y, z = nodes[idx]
        out.append("0\nPOINT\n8\nL-SUPPORT\n10\n%.3f\n20\n%.3f\n30\n%.3f\n" % (x, y, z))
    out.append("0\nENDSEC\n")
    # OBJECTS
    out.append("0\nSECTION\n2\nOBJECTS\n"
               "0\nDICTIONARY\n5\nC\n330\n0\n100\nAcDbDictionary\n281\n1\n"
               "3\nACAD_GROUP\n350\nD\n0\nDICTIONARY\n5\nD\n330\nC\n100\nAcDbDictionary\n281\n1\n"
               "0\nENDSEC\n")
    out.append("0\nEOF\n")
    with open(path, "w", encoding="ascii", errors="replace") as fh:
        fh.write("".join(out))


if __name__ == "__main__":
    import json
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "光伏支架线模_测试.dxf"
    model = write_dxf(default_params(), out)
    info = model["info"]
    print("节点:", info["node_count"], "杆件:", info["member_count"],
          "| 类型:", info["support_type"], "榀数:", info["frames"],
          "梁长:", info["beam_len"], "檩条总长:", info["purlin_total"],
          "悬挑:", round(info["overhang"], 1))
    from collections import Counter
    print("构件统计:", dict(Counter(k for k, _, _ in model["members"])))
    print("已写出:", out)
