# -*- coding: utf-8 -*-
"""
3D3S 文本模型导出器（M3，依据 123.3D3S 真实样例校准）

格式要点（与 3D3S 文本模型一致）：
    *VERSION 2024.0
    *UNIT    N, MM, J, C
    *MATERIAL 材料号, 名称, STEEL, 钢号, E, 泊松比, 线膨胀系数, 质量密度, fy, f, fu, 1
    *SECTION  类型号, 截面号, VALUE/DB, 名称, 类型名称, [SecData/标号]
    *NODE     节点号, X, Y, Z, 1
    *ELE_LINE 单元号, BEAM, 材料号, 截面类型, 截面号, 节点1, 节点2,
              K节点x, K节点y, K节点z, 2, 绕1轴转角, 4, 0,0,0,0,-1,0,0,单元号
    *CONSTRAINT 节点:节点, 111111, NEWFLAG, 6, 0x6, 6, 0x6
    *STLDCASE 工况号, 类型(D/W/L/S), 说明, 准永久系数, 1/0

截面类型号：3=普通槽钢, 5=普通角钢(等肢), 13=冷弯卷边槽钢,
            16=矩形空心型钢, 22=热轧无缝钢管与电焊钢管
"""

from pv_geometry import build_model, beam_length


# 规格 -> (3D3S 类型号, 类型名称, 行类型)
SPEC_TYPE_ID = {
    "C型钢":     (13, "冷弯卷边槽钢", "VALUE"),
    "角钢":      (5,  "普通角钢(等肢)", "DB"),
    "槽钢":      (3,  "普通槽钢", "DB"),
    "圆钢/圆管": (22, "热轧无缝钢管与电焊钢管", "VALUE"),
    "矩形钢管":  (16, "矩形空心型钢", "DB"),
    "方钢管":    (16, "矩形空心型钢", "DB"),      # 方形管暂归矩形空心型钢，待校准
    "U型钢":     (13, "冷弯卷边槽钢", "VALUE"),   # 待校准
    "Z型钢":     (13, "冷弯卷边槽钢", "VALUE"),   # 待校准
}


def _sec_name_3d3s(spec, model):
    """截面名称转 3D3S 格式。"""
    # 已符合 3D3S 库真实命名（方括号槽钢 / 矩xx / 方xx / φxx / Lxx）时直接使用
    if model.startswith("["):
        return model
    if model.startswith(("矩", "方", "φ", "L")) and "×" not in model:
        return model
    if spec == "槽钢":
        # 槽8 -> [8（3D3S 槽钢用方括号表示法）
        return "[" + model.replace("槽", "")
    if spec == "角钢":
        return model.replace("×", "x").replace("L", "L")
    if spec == "矩形钢管":
        # 矩形管100×50×3 -> 矩100x50x3
        return "矩" + model.replace("矩形管", "").replace("×", "x")
    if spec == "方钢管":
        # 方形空心型钢库名：方30x2.0 = 方[边长]x[壁厚]
        m = model.replace("方管", "").replace("×", "x")
        parts = m.split("x")
        if len(parts) == 3 and parts[0] == parts[1]:
            return "方%sx%s" % (parts[0], parts[2])
        return "方" + m
    if spec == "圆钢/圆管":
        m = model.replace("圆管", "").replace("圆钢φ", "φ").replace("φ", "φ").replace("×", "x")
        if model.startswith("圆管") and not m.startswith("φ"):
            m = "φ" + m
        return m
    return model.replace("×", "X")


def _sec_data_3d3s(spec, model):
    """VALUE 型截面的 SecData（圆管给出 D,0,t,0x7；其余按名称引用库）。"""
    if spec == "槽钢":
        return _sec_name_3d3s(spec, model)
    if spec == "圆钢/圆管":
        import re
        m = re.match(r"(?:圆管|圆钢φ|φ)([\d.]+)(?:[x×])([\d.]+)", model)
        if m:
            return "%s, 0, %s, 0, 0, 0, 0, 0, 0, 0" % (m.group(1), m.group(2))
        m2 = re.match(r"(?:圆钢φ|φ)([\d.]+)", model)
        if m2:
            return "%s, 0, 0, 0, 0, 0, 0, 0, 0, 0" % m2.group(1)
    return model


def _material_row(mid, mat_name, steel_grade, E, nu, alpha, rho_n, fy, f, fu):
    return "%d, %s, STEEL, %s, %g, %g, %g, %g, %d, %d, %d, 1" % (
        mid, mat_name, steel_grade, E, nu, alpha, rho_n, fy, f, fu)


MATERIAL_ROWS = {
    "Q235B": lambda i: _material_row(i, "Q235B", "Q235", 206000, 0.3, 1.2e-05, 7.69771e-05, 235, 215, 370),
    "Q355B": lambda i: _material_row(i, "Q355B", "Q355", 206000, 0.3, 1.2e-05, 7.69771e-05, 355, 305, 470),
    "Q460B": lambda i: _material_row(i, "Q460B", "Q460", 206000, 0.3, 1.2e-05, 7.69771e-05, 460, 410, 550),
}


# 各构件类型的绕1轴转角（°），依据 123.3D3S 工作模型实测
# （斜梁/檩条=0，立柱/斜撑=90；若仍有偏差请反馈具体构件需转多少度）
ROLE_ANGLE = {
    "斜梁": 0,
    "檩条": 70,
    "斜撑": 90,
    "立柱": 180,
}


def write_3d3s_text(params, path):
    """生成 3D3S 文本模型文件。返回模型统计。"""
    model = build_model(params)
    nodes = model["nodes"]
    members = model["members"]

    out = []
    out.append(";----------------------------------------------------------------------------")
    out.append("*VERSION")
    out.append("2024.0")
    out.append("*UNIT")
    out.append("N, MM, J, C")

    # 材料
    mat_ids = {}
    out.append("*MATERIAL")
    for i, (kind, _a, _b) in enumerate(members, start=1):
        mat = params.get("sections", {}).get(kind, {}).get("material", "Q235B")
        if mat not in mat_ids:
            mat_ids[mat] = len(mat_ids) + 1
            row = MATERIAL_ROWS.get(mat)
            if row:
                out.append(row(mat_ids[mat]))
            else:
                out.append("%d, %s, STEEL, %s, 206000, 0.3, 1.2e-05, 7.69771e-05, 235, 215, 370, 1"
                           % (mat_ids[mat], mat, mat))
    out.append("*MATL-COLOR")
    for mid in mat_ids.values():
        out.append("%d, 128, 128, 128" % mid)

    # 截面
    sec_map = {}
    out.append("*SECTION")
    sec_no = {}
    for i, (kind, _a, _b) in enumerate(members, start=1):
        sec = params.get("sections", {}).get(kind, {})
        spec = sec.get("spec", "自定义")
        secname = sec.get("model", "自定义")
        key = (spec, secname)
        if key in sec_map:
            continue
        if spec not in SPEC_TYPE_ID:
            sec_map[key] = (0, 0, None)
            continue
        tid, tname, kind2 = SPEC_TYPE_ID[spec]
        sec_no[tid] = sec_no.get(tid, 0) + 1
        sid = sec_no[tid]
        sec_map[key] = (tid, sid, secname)
        name3 = _sec_name_3d3s(spec, secname)
        if kind2 == "DB":
            out.append("%d, %d, DB, %s, %s, %s," % (tid, sid, name3, tname, name3))
        else:
            out.append("%d, %d, VALUE, %s, %s, %s," % (tid, sid, name3, tname, _sec_data_3d3s(spec, secname)))
    out.append("*SECT-COLOR")
    for tid, sid in sorted(sec_no.items()):
        out.append("%d, %d, 128, 128, 128" % (tid, sid))

    # 节点
    out.append("*NODE")
    for idx in sorted(nodes):
        x, y, z = nodes[idx]
        out.append("%d, %.3f, %.3f, %.3f, 1" % (idx, x, y, z))

    # 单元（含绕1轴转角）
    xs = [nodes[k][0] for k in nodes]
    ys = [nodes[k][1] for k in nodes]
    zs = [nodes[k][2] for k in nodes]
    # K 节点：参考 123.3D3S 的做法，取模型外上方一点（与所有单元不共线）
    kx = (min(xs) + max(xs)) / 2
    ky = max(ys) + 3000
    kz = max(zs) - 1000
    out.append("*ELE_LINE")
    for i, (kind, i1, i2) in enumerate(members, start=1):
        sec = params.get("sections", {}).get(kind, {})
        spec = sec.get("spec", "自定义")
        secname = sec.get("model", "自定义")
        tid, sid, _ = sec_map.get((spec, secname), (0, 0, None))
        matid = mat_ids.get(sec.get("material", "Q235B"), 1)
        angle = ROLE_ANGLE.get(kind, 90)
        # 檩条按自身位置设置 K 节点（x 同檩条、z 上方），保证 4 根严格平行；
        # 其余构件沿用全局 K（已实测方位正确）
        if kind == "檩条":
            x1, y1, z1 = nodes[i1]
            mkx, mky, mkz = x1, y1, z1 + 1000
        else:
            mkx, mky, mkz = kx, ky, kz
        out.append("%d, BEAM, %d, %d, %d, %d, %d, %.3f, %.3f, %.3f, 2, %d, 4, 0, 0, 0, 0, -1, 0, 0, %d"
                   % (i, matid, tid, sid, i1, i2, mkx, mky, mkz, angle, i))

    # 支座（柱脚刚接）
    out.append("*CONSTRAINT")
    sup = ":".join(str(n) for n in sorted(model["supports"]))
    out.append("%s,111111,NEWFLAG,6, 0, 0, 0, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0" % sup)

    # 工况
    out.append("*STLDCASE")
    out.append("0, D, 恒载, 0.5, 1")
    out.append("1, W, 风荷载, 0.5, 0")
    out.append("2, S, 雪荷载, 0.5, 0")
    out.append("*END")

    with open(path, "w", encoding="gbk") as fh:
        fh.write("\n".join(out))
    return model["info"]


if __name__ == "__main__":
    import sys
    from pv_geometry import default_params
    out = sys.argv[1] if len(sys.argv) > 1 else "光伏支架_3D3S文本.3D3S"
    info = write_3d3s_text(default_params(), out)
    print("已生成:", out, "| 节点:", info["node_count"], "杆件:", info["member_count"])
