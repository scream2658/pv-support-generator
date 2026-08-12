# -*- coding: utf-8 -*-
"""
SAP2000 .s2k 导出器（M3，参照本机 SAP2000 V26 真实样本格式）

生成内容：材料(Q235/Q355) / 截面(全力学属性自包含) / 节点 / 杆件 /
          截面赋值 / 支座(全固接) / 局部轴转角 / 荷载工况(DEAD/snow/wp/wz) /
          檩条分布荷载 / 荷载组合(光伏规范) / 构件分组。
单位：N, mm, C。
"""

import math

from pv_geometry import build_model, purlin_positions, beam_length
from pv_3d3s_text import ROLE_ANGLE
from pv_sections import MATERIALS, SECTIONS, get_props


SHAPE = {
    "C型钢": '"Cold Formed C"',
    "Z型钢": '"Cold Formed C"',
    "U型钢": '"Cold Formed C"',
    "槽钢": "Channel",
    "角钢": "Angle",
    "方钢管": "Tube",
    "矩形钢管": "Tube",
    "圆钢/圆管": "Pipe",
}

# 槽钢翼缘厚度（GB，近似，供 Channel 截面 tf 用）
CHANNEL_TF = {"槽8": 8.0, "槽10": 8.5, "槽12": 9.0, "槽14a": 9.5, "槽16a": 10.0,
              "槽18a": 10.5, "槽20a": 11.0}

# SAP2000 局部轴转角（与 3D3S 定版值相差 90°，仅檩条不同）
S2K_ANGLE = {"斜梁": 0, "檩条": 160, "斜撑": 90, "立柱": 180}

# SAP2000 分组名用 ASCII（避免中文组名警告/截断）
GROUP_ASCII = {"立柱": "COLUMN", "斜梁": "BEAM", "檩条": "PURLIN", "斜撑": "BRACE"}


def _dims(spec, model):
    for name, dims in SECTIONS.get(spec, []):
        if name == model:
            return dims
    return None


def _sec_row(name, mat, spec, model):
    p = get_props(spec, model)
    dims = _dims(spec, model)
    if spec == "C型钢":
        h = dims[0] if dims else 100
        b = dims[1] if dims else 50
        c = dims[2] if dims else 20
        t = dims[3] if dims else 2.0
        shape = '"Cold Formed C"'
        shape_fields = [("t3", h), ("t2", b), ("tw", t), ("Radius", 0), ("LipDepth", c)]
    elif spec in ("方钢管", "矩形钢管"):
        h, b, t = dims if dims else (100, 50, 3.0)
        shape = "Tube"
        shape_fields = [("t3", h), ("t2", b), ("tw", t)]
    elif spec == "圆钢/圆管":
        h = dims[0] if dims else 48
        b = h
        t = dims[1] if len(dims or ()) > 1 else h / 2
        shape = "Pipe" if len(dims or ()) > 1 else "Circle"
        shape_fields = [("t3", h), ("tw", t)]
    elif spec == "槽钢":
        h = dims[0] if dims else 80
        b = dims[1] if dims else 43
        t = dims[2] if dims else 5.0
        tf = CHANNEL_TF.get(model, t * 1.6)
        shape = "Channel"
        shape_fields = [("t3", h), ("t2", b), ("tf", tf), ("tw", t), ("FilletRadius", 0)]
    elif spec == "角钢":
        b = dims[0] if dims else 50
        t = dims[1] if dims else 5
        shape = "Angle"
        shape_fields = [("t3", b), ("t2", b), ("tf", t), ("tw", t), ("FilletRadius", 0)]
    elif dims:
        h = dims[0]
        b = dims[1] if len(dims) > 1 else h
        t = dims[2] if len(dims) > 2 else (dims[1] if len(dims) > 1 else 3)
        shape = SHAPE.get(spec, "C")
        shape_fields = [("t3", h), ("t2", b), ("tw", t)]
    else:
        h = b = t = 50.0
        shape = SHAPE.get(spec, "C")
        shape_fields = [("t3", h), ("t2", b), ("tw", t)]
    if p is None:
        p = {"A": 500.0, "I1": 1e6, "I2": 3e5, "W1": 2e4, "W2": 1e4, "J": 1e3}
    r33 = math.sqrt(p["I1"] / p["A"]) if p["A"] > 0 else 0
    r22 = math.sqrt(p["I2"] / p["A"]) if p["A"] > 0 else 0
    fields = [("SectionName", name), ("Material", mat), ("Shape", shape)]
    fields += shape_fields
    fields += [("Area", p["A"]), ("TorsConst", p["J"]), ("I33", p["I1"]), ("I22", p["I2"]),
               ("I23", 0), ("AS2", 0), ("AS3", 0),
               ("S33Top", p["W1"]), ("S33Bot", p["W1"]),
               ("S22Left", p["W2"]), ("S22Right", p["W2"]),
               ("Z33", 0), ("Z22", 0), ("R33", r33), ("R22", r22),
               ("CGOffset3", 0), ("CGOffset2", 0), ("EccV2", 0), ("EccV3", 0), ("Cw", 0),
               ("IncludeSCAn", "No"), ("ConcCol", "No"), ("ConcBeam", "No"), ("Color", "Default"),
               ("TotalWt", 0), ("TotalMass", 0), ("FromFile", "No"),
               ("AMod", 1), ("A2Mod", 1), ("A3Mod", 1), ("JMod", 1),
               ("I2Mod", 1), ("I3Mod", 1), ("MMod", 1), ("WMod", 1)]
    return "   " + "   ".join("%s=%s" % (k, v) for k, v in fields)


def _mat_rows():
    rows = []
    for mat in ("Q235", "Q355"):
        rows.append('   Material=%s   Type=Steel   Grade=%s   SymType=Isotropic   TempDepend=No'
                    % (mat, mat))
    return rows


def _mat_mech():
    rows = []
    for mat in ("Q235", "Q355"):
        rows.append('   Material=%s   UnitWeight=7.7E-05   UnitMass=7.85E-09   E1=206000   '
                    'G12=79230.76923076923   U12=0.3   A1=1.2E-05' % mat)
    return rows


def _mat_steel():
    return [
        '   Material=Q235   Fy=235   Fu=370   EffFy=260   EffFu=410   SSCurveOpt=Simple   '
        'SSHysType=Kinematic   SHard=0.015   SMax=0.11   SRup=0.17   FinalSlope=-0.1',
        '   Material=Q355   Fy=355   Fu=470   EffFy=390   EffFu=520   SSCurveOpt=Simple   '
        'SSHysType=Kinematic   SHard=0.015   SMax=0.11   SRup=0.17   FinalSlope=-0.1',
    ]


def _purlin_tributaries(params):
    pos = purlin_positions(params)
    trib = []
    for i in range(len(pos)):
        if len(pos) == 1:
            trib.append(1000.0)
        elif i == 0:
            trib.append(pos[1] - pos[0])
        elif i == len(pos) - 1:
            trib.append(pos[-1] - pos[-2])
        else:
            trib.append((pos[i + 1] - pos[i - 1]) / 2)
    return pos, trib


def write_s2k(params, path):
    model = build_model(params)
    nodes = model["nodes"]
    members = model["members"]
    layout = params.get("layout", {})
    module = params.get("module", {})
    loads = params.get("loads", {})
    st = params.get("structure", {})

    out = []
    out.append('TABLE:  "PROGRAM CONTROL"')
    out.append('   ProgramName=SAP2000   Version=26.3.0   ProgLevel=Advanced   '
               'CurrUnits="N, mm, C"')
    out.append('')
    out.append('TABLE:  "ACTIVE DEGREES OF FREEDOM"')
    out.append('   UX=Yes   UY=Yes   UZ=Yes   RX=Yes   RY=Yes   RZ=Yes')
    out.append('')
    out.append('TABLE:  "ANALYSIS OPTIONS"')
    out.append('   Solver=Advanced   SolverProc=Auto   Force32Bit=No')
    out.append('')
    out.append('TABLE:  "COORDINATE SYSTEMS"')
    out.append('   Name=GLOBAL   Type=Cartesian   X=0   Y=0   Z=0   AboutZ=0   AboutY=0   AboutX=0')
    out.append('')

    # 材料
    out.append('TABLE:  "MATERIAL PROPERTIES 01 - GENERAL"')
    out += _mat_rows()
    out.append('')
    out.append('TABLE:  "MATERIAL PROPERTIES 02 - BASIC MECHANICAL PROPERTIES"')
    out += _mat_mech()
    out.append('')
    out.append('TABLE:  "MATERIAL PROPERTIES 03A - STEEL DATA"')
    out += _mat_steel()
    out.append('')

    # 截面（按构件角色+型号）
    sections = {}
    out.append('TABLE:  "FRAME SECTION PROPERTIES 01 - GENERAL"')
    for kind, _a, _b in members:
        sec = params.get("sections", {}).get(kind, {})
        spec = sec.get("spec", "自定义")
        model_name = sec.get("model", "自定义")
        mat = "Q355" if sec.get("material", "").startswith("Q355") else "Q235"
        name = "%s-%s" % (kind, model_name.replace("×", "x"))
        if name not in sections:
            sections[name] = (mat, spec, model_name)
            out.append(_sec_row(name, mat, spec, model_name))
    out.append('')

    # 节点
    out.append('TABLE:  "JOINT COORDINATES"')
    for idx in sorted(nodes):
        x, y, z = nodes[idx]
        out.append('   Joint=%d   CoordSys=GLOBAL   CoordType=Cartesian   XorR=%.3f   Y=%.3f   Z=%.3f   SpecialJt=Yes'
                   % (idx, x, y, z))
    out.append('')

    # 杆件
    out.append('TABLE:  "CONNECTIVITY - FRAME"')
    for i, (_k, i1, i2) in enumerate(members, start=1):
        out.append('   Frame=%d   JointI=%d   JointJ=%d   IsCurved=No' % (i, i1, i2))
    out.append('')
    out.append('TABLE:  "FRAME SECTION ASSIGNMENTS"')
    for i, (kind, _a, _b) in enumerate(members, start=1):
        sec = params.get("sections", {}).get(kind, {})
        name = "%s-%s" % (kind, sec.get("model", "自定义").replace("×", "x"))
        mat = sections[name][0]
        stype = SHAPE.get(sec.get("spec", ""), "Frame")
        out.append('   Frame=%d   SectionType=%s   AutoSelect=N.A.   AnalSect=%s   DesignSect=%s   MatProp=Default'
                   % (i, stype, name, name))
    out.append('')

    # 支座
    out.append('TABLE:  "JOINT RESTRAINT ASSIGNMENTS"')
    for idx in sorted(model["supports"]):
        out.append('   Joint=%d   U1=Yes   U2=Yes   U3=Yes   R1=Yes   R2=Yes   R3=Yes' % idx)
    out.append('')

    # 局部轴转角
    out.append('TABLE:  "FRAME LOCAL AXES ASSIGNMENTS 1 - TYPICAL"')
    for i, (kind, _a, _b) in enumerate(members, start=1):
        out.append('   Frame=%d   Angle=%d   AdvanceAxes=No' % (i, S2K_ANGLE.get(kind, 90)))
    out.append('')

    # 荷载工况
    out.append('TABLE:  "LOAD PATTERN DEFINITIONS"')
    out.append('   LoadPat=DEAD   DesignType=Dead   SelfWtMult=1   AutoLoad=None')
    out.append('   LoadPat=snow   DesignType=Snow   SelfWtMult=0   AutoLoad=None')
    out.append('   LoadPat=wp     DesignType=Wind   SelfWtMult=0   AutoLoad=None')
    out.append('   LoadPat=wz     DesignType=Wind   SelfWtMult=0   AutoLoad=None')
    out.append('')
    out.append('TABLE:  "LOAD CASE DEFINITIONS"')
    for case, dtype, dact in (
            ("DEAD", "Dead", "Non-Composite"),
            ("snow", "Dead", "Non-Composite"),
            ("wp", "Wind", "Short-Term Composite"),
            ("wz", "Wind", "Short-Term Composite")):
        out.append('   Case=%s   Type=LinStatic   InitialCond=Zero   DesTypeOpt="Prog Det"   '
                   'DesignType=%s   DesActOpt="Prog Det"   DesignAct=%s   AutoType=None   '
                   'RunCase=Yes   CaseStatus="Not Run"' % (case, dtype, dact))
    out.append('')
    out.append('TABLE:  "CASE - STATIC 1 - LOAD ASSIGNMENTS"')
    for case in ("DEAD", "snow", "wp", "wz"):
        out.append('   Case=%s   LoadType="Load pattern"   LoadName=%s   LoadSF=1' % (case, case))
    out.append('')

    # 檩条分布荷载（恒=组件+附件；雪=重力；风=局部2向）
    w_dead_area = (module.get("weight", 28.5) * 9.80665 / 1e3) / \
                  (module.get("L", 2278) * module.get("W", 1134) * 1e-6) + loads.get("dead", 0.05)
    snow = loads.get("snow", 0.20)
    w0 = loads.get("wind_base", 0.35)
    mu_z = loads.get("mu_z", 1.10)
    mu_p = abs(loads.get("mu_s_pos", 1.30))
    mu_n = abs(loads.get("mu_s_neg", 1.30))
    coastal = loads.get("coastal", 1.10)

    purlin_frames = [i for i, (kind, _a, _b) in enumerate(members, start=1) if kind == "檩条"]
    _, trib = _purlin_tributaries(params)
    alpha = math.radians(layout.get("tilt", 20))
    sa, ca = math.sin(alpha), math.cos(alpha)
    out.append('TABLE:  "FRAME LOADS - DISTRIBUTED"')
    for k, fid in enumerate(purlin_frames):
        t = trib[k % len(trib)]
        q_dead = w_dead_area * 1e-3 * t
        q_snow = snow * 1e-3 * t
        q_wp = w0 * mu_z * mu_p * coastal * 1e-3 * t
        q_wz = w0 * mu_z * mu_n * coastal * 1e-3 * t
        out.append('   Frame=%d   LoadPat=DEAD   CoordSys=GLOBAL   Type=Force   Dir=Gravity   '
                   'DistType=RelDist   RelDistA=0   RelDistB=1   FOverLA=%.4f   FOverLB=%.4f'
                   % (fid, q_dead, q_dead))
        out.append('   Frame=%d   LoadPat=snow   CoordSys=GLOBAL   Type=Force   Dir=Gravity   '
                   'DistType=RelDist   RelDistA=0   RelDistB=1   FOverLA=%.4f   FOverLB=%.4f'
                   % (fid, q_snow, q_snow))
        # 正风压 wz：垂直于斜梁面朝下（压向板面），方向 (sin a, 0, -cos a)
        out.append('   Frame=%d   LoadPat=wz   CoordSys=GLOBAL   Type=Force   Dir=X   '
                   'DistType=RelDist   RelDistA=0   RelDistB=1   FOverLA=%.4f   FOverLB=%.4f'
                   % (fid, q_wz * sa, q_wz * sa))
        out.append('   Frame=%d   LoadPat=wz   CoordSys=GLOBAL   Type=Force   Dir=Z   '
                   'DistType=RelDist   RelDistA=0   RelDistB=1   FOverLA=%.4f   FOverLB=%.4f'
                   % (fid, -q_wz * ca, -q_wz * ca))
        # 负风压 wp：垂直于斜梁面朝上（吸力），方向 (-sin a, 0, +cos a)
        out.append('   Frame=%d   LoadPat=wp   CoordSys=GLOBAL   Type=Force   Dir=X   '
                   'DistType=RelDist   RelDistA=0   RelDistB=1   FOverLA=%.4f   FOverLB=%.4f'
                   % (fid, -q_wp * sa, -q_wp * sa))
        out.append('   Frame=%d   LoadPat=wp   CoordSys=GLOBAL   Type=Force   Dir=Z   '
                   'DistType=RelDist   RelDistA=0   RelDistB=1   FOverLA=%.4f   FOverLB=%.4f'
                   % (fid, q_wp * ca, q_wp * ca))
    out.append('')

    # 荷载组合（光伏规范 NB/T 10115 常用组合）
    combos = [
        ("1.3D+1.5Wz+1.5*0.7Sn", [("DEAD", 1.3), ("wz", 1.5), ("snow", 1.05)]),
        ("1.3D+1.5Sn+1.5*0.7Wz", [("DEAD", 1.3), ("snow", 1.5), ("wz", 1.05)]),
        ("1.0D+1.0Wp+1.0*0.7Sn", [("DEAD", 1.0), ("wp", 1.0), ("snow", 0.7)]),
        ("1.0D+1.0Wz", [("DEAD", 1.0), ("wz", 1.0)]),
    ]
    out.append('TABLE:  "COMBINATION DEFINITIONS"')
    first = True
    for cname, items in combos:
        if first:
            out.append('   ComboName=%s   ComboType="Linear Add"   AutoDesign=No   CaseType="Linear Static"   CaseName=%s   ScaleFactor=%g   SteelDesign=None'
                       % (cname, items[0][0], items[0][1]))
            first = False
        else:
            out.append('   ComboName=%s   CaseType="Linear Static"   CaseName=%s   ScaleFactor=%g'
                       % (cname, items[0][0], items[0][1]))
        for cname2, (case, sf) in list(zip([cname] * len(items), items))[1:]:
            out.append('   ComboName=%s   CaseType="Linear Static"   CaseName=%s   ScaleFactor=%g'
                       % (cname2, case, sf))
    out.append('')

    # 分组
    out.append('TABLE:  "GROUPS 1 - DEFINITIONS"')
    kinds = []
    for kind, _a, _b in members:
        if kind not in kinds:
            kinds.append(kind)
    for kind in kinds:
        out.append('   GroupName=%s   Selection=No   SectionCut=No   Steel=No   Concrete=No   Aluminum=No   ColdFormed=No   Color=Yellow'
                   % GROUP_ASCII.get(kind, kind))
    out.append('')
    out.append('TABLE:  "GROUPS 2 - ASSIGNMENTS"')
    for i, (kind, _a, _b) in enumerate(members, start=1):
        out.append('   GroupName=%s   ObjectType=Frame   ObjectLabel=%d'
                   % (GROUP_ASCII.get(kind, kind), i))
    out.append('')

    with open(path, "w", encoding="gbk", errors="replace") as fh:
        fh.write("\n".join(out))
    return model["info"]


if __name__ == "__main__":
    import sys
    from pv_geometry import default_params
    out = sys.argv[1] if len(sys.argv) > 1 else "光伏支架_SAP2000.s2k"
    info = write_s2k(default_params(), out)
    print("已生成:", out, "| 节点:", info["node_count"], "杆件:", info["member_count"])
