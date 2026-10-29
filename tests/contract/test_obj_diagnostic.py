"""契约：`verify_case.sh --stage post` 必须把 `objective` 与派生源的真实 ddtSchemes 对照出来。

## 这条测试守的是什么（一次真实事故）

2026-10-29 的陌生用户验收（P5）里，一个只读发布包文档的人被要求做「二维方腔、顶盖 1 m/s、水、
层流、**稳态**」。他照文档走完全程，五道门全绿——但派生源 `incompressibleFluid/cavity` 的
`ddtSchemes` 是 `Euler`、`endTime 10`、`deltaT 0.005`，`log.run` 是 2000 步瞬态跑到 t=10 s。

也就是说：**四元组里的 `objective` 被解析了、存进了 `case.meta`，然后没有任何东西用它**。
需求里最容易被误认为「已经满足」的那一维，恰好是唯一没人判的一维。这正是发布包自己
在 `SKILL.md §3 步骤 1` 警告的失败形状（「默认值会把『需求没被满足』变成『五道门全过』」）。

## 为什么是诊断而不是门

「objective 是否被满足」依赖物理判断（稳态该用哪个求解器、残差到什么程度算收敛），
脚本判不了。把它设成门的后果是**所有人学会忽略这道门**——与 `g2b` 是诊断不是门的理由完全同构
（`bench/preregistration.md` 的决策 #7）。

所以判据分两层：
- **必须有**：`OBJ=` 这一行出现，且 mismatch 时给出警告文本。
- **不许有**：退出码因 OBJ 而改变。OBJ 是诊断，不是第 6 道门。

第二层同样要测：如果有人「顺手」把 OBJ 接进退出码，`test_obj_does_not_change_exit_code`
必须变红。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_case.sh"

FVS_CHEMES_STEADY = """/*--------------------------------*- C++ -*----------------------------------*/
ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}
"""

FVS_CHEMES_TRANSIENT = """ddtSchemes
{
    default         Euler;
}
"""


def _make_case(tmp_path: Path, objective: str | None, ddt: str) -> Path:
    """造一个最小的 case 树：system/fvSchemes + case.meta + 一份能过 G2/G3/G4 的日志。"""
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "system" / "fvSchemes").write_text(
        FVS_CHEMES_STEADY if ddt == "steadyState" else FVS_CHEMES_TRANSIENT,
        encoding="utf-8",
    )
    spec = {
        "geometry": "二维方腔",
        "properties": "水",
        "boundary": "顶盖 1 m/s",
        "objective": objective,
        "complete": objective is not None,
        "missing": [] if objective else ["objective"],
    }
    (case / "case.meta").write_text(
        json.dumps(
            {
                "source": "incompressibleFluid/cavity",
                "derived_at": "2026-10-29T00:00:00+08:00",
                "spec": spec,
                "changes": [],
                "allowed_files": ["system/*", "constant/*", "0/*"],
                "schema_version": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # 一份「跑成功」的最小产物：checkMesh 有 Mesh OK.、shortRun 无 FATAL、末时刻有场文件
    (case / "log.checkMesh").write_text("Mesh OK.\n", encoding="utf-8")
    (case / "log.shortRun").write_text("Time = 0.01\nEnd\n", encoding="utf-8")
    (case / "10").mkdir()
    for f in ("U", "p"):
        (case / "10" / f).write_text("internalField nonuniform List<vector>\n", encoding="utf-8")
    return case


def _run(case: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--stage", "post", "--case", str(case)],
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_obj_mismatch_is_reported(tmp_path: Path) -> None:
    """需求要稳态、派生源是 Euler → 必须打出 OBJ=mismatch 与警告。"""
    case = _make_case(tmp_path, objective="steady", ddt="Euler")

    proc = _run(case)
    out = proc.stdout + proc.stderr

    assert "OBJ=mismatch" in out, (
        "需求 objective=steady 而 ddtSchemes=Euler 时必须报 OBJ=mismatch。"
        f"实际输出：\n{out}"
    )
    assert "steady" in out and "Euler" in out, (
        f"OBJ 行必须同时写出需求值与实际值，便于人对照：\n{out}"
    )
    assert "不代表这条需求被满足" in out, (
        f"mismatch 必须给出「门全绿 ≠ 需求被满足」的警告，否则读者仍会误判：\n{out}"
    )


def test_obj_match_is_reported(tmp_path: Path) -> None:
    """需求要稳态、派生源是 steadyState → OBJ=match，且不得给出误导性警告。"""
    case = _make_case(tmp_path, objective="steady", ddt="steadyState")

    out = "".join(_run(case).stdout)

    assert "OBJ=match" in out, f"steady + steadyState 应判 match：\n{out}"
    assert "不代表这条需求被满足" not in out, f"match 时不该出现警告：\n{out}"


def test_obj_transient_match(tmp_path: Path) -> None:
    """需求要瞬态、派生源是 Euler → 也算 match（瞬态就是它本来的样子）。"""
    case = _make_case(tmp_path, objective="transient", ddt="Euler")

    out = "".join(_run(case).stdout)

    assert "OBJ=match" in out, f"transient + Euler 应判 match：\n{out}"


def test_no_objective_means_no_obj_line(tmp_path: Path) -> None:
    """需求里没给 objective（None）→ 不打 OBJ 行。

    为什么要测「不打」：这一行一旦无条件出现，读者会以为它有意义，
    而实际上它只是一句「没需求可对照」。诊断行的可信度来自它只在有话可说时出现。
    """
    case = _make_case(tmp_path, objective=None, ddt="Euler")

    out = "".join(_run(case).stdout)

    assert "OBJ=" not in out, f"没有 objective 时不该打 OBJ 行：\n{out}"


def test_obj_does_not_change_exit_code(tmp_path: Path) -> None:
    """**OBJ 是诊断，不是门**：它的结论不得改变退出码。

    判据：同一份 case，把 fvSchemes 从 steadyState 改成 Euler（把 OBJ 从 match 变成 mismatch），
    退出码必须**完全相同**。若有人把 OBJ 接进退出码，这条会红——那违反
    「判不了的东西不许设成门」（g2b 同款理由）。
    """
    match_case = _make_case(tmp_path / "a", objective="steady", ddt="steadyState")
    mismatch_case = _make_case(tmp_path / "b", objective="steady", ddt="Euler")

    rc_match = _run(match_case).returncode
    rc_mismatch = _run(mismatch_case).returncode

    assert rc_match == rc_mismatch, (
        f"OBJ 结论不同而退出码不同（{rc_match} vs {rc_mismatch}）："
        "OBJ 被接进退出码了，它应该只是诊断。"
    )


# ---------------------------------------------------------------------------
# GEO / RE / RES：第二组诊断（2026-10-29 第二轮陌生用户验收后补）
# ---------------------------------------------------------------------------


def _add_geometry(case: Path, *, ctm: float, cells: int, nu: float, u_mag: float) -> None:
    """给已有 case 补上 blockMeshDict / physicalProperties / 0-U，让 Re 可算。"""
    (case / "system" / "blockMeshDict").write_text(
        f"convertToMeters {ctm};\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({cells} 1 1) simpleGrading (1 1 1)\n);\n",
        encoding="utf-8",
    )
    (case / "constant").mkdir(exist_ok=True)
    (case / "constant" / "physicalProperties").write_text(
        f"nu              {nu};\n", encoding="utf-8"
    )
    (case / "0").mkdir(exist_ok=True)
    (case / "0" / "U").write_text(
        "boundaryField\n{\n    movingWall\n    {\n"
        f"        type            fixedValue;\n        value           uniform ({u_mag} 0 0);\n"
        "    }\n}\n",
        encoding="utf-8",
    )


def test_geo_and_re_are_reported(tmp_path: Path) -> None:
    """正常算例：GEO= 报 cells，Re= 报无量纲数。"""
    case = _make_case(tmp_path, objective="steady", ddt="steadyState")
    _add_geometry(case, ctm=0.1, cells=400, nu=1e-6, u_mag=1.0)

    out = "".join(_run(case).stdout)

    assert "GEO=" in out and "cells=400" in out, f"必须报出网格量：\n{out}"
    assert "Re=" in out, f"必须报出 Re：\n{out}"
    # Re = U*L/nu = 1*0.1/1e-6 = 1e5
    assert "1e+05" in out or "100000" in out, f"Re 应为 1e5：\n{out}"


def test_coarse_resolution_is_flagged(tmp_path: Path) -> None:
    """400 cells 跑 Re=1e5 → RES=coarse，并说明门全绿不等于结果可信。"""
    case = _make_case(tmp_path, objective="steady", ddt="steadyState")
    _add_geometry(case, ctm=0.1, cells=400, nu=1e-6, u_mag=1.0)

    out = "".join(_run(case).stdout)

    assert "RES=coarse" in out, (
        f"400 cells + Re=1e5 必须被判 coarse（实测这是 Stokes 流量级的假解）：\n{out}"
    )
    assert "不代表结果可信" in out, f"coarse 必须给出提示，否则读者仍只看门：\n{out}"


def test_fine_grid_is_not_flagged_coarse(tmp_path: Path) -> None:
    """反过来：网格足够时不许误报 coarse（否则提示会被当噪音忽略）。"""
    case = _make_case(tmp_path, objective="transient", ddt="Euler")
    # Re = 1*0.1/1e-6 = 1e5，cells 给 1e6（远超 0.01*Re = 1e3）
    _add_geometry(case, ctm=0.1, cells=1000000, nu=1e-6, u_mag=1.0)

    out = "".join(_run(case).stdout)

    assert "RES=coarse" not in out, f"网格充足时不该报 coarse：\n{out}"


def test_re_unknown_when_inputs_missing(tmp_path: Path) -> None:
    """读不到 nu/速度 → RE=unknown，而不是编一个数出来（R6：数字必须实测）。"""
    case = _make_case(tmp_path, objective="steady", ddt="steadyState")

    out = "".join(_run(case).stdout)

    assert "RE=unknown" in out, f"缺输入时必须说 unknown，不许估：\n{out}"
    assert "Re=" not in out.replace("RE=unknown", ""), (
        f"unknown 时不得同时给出一个 Re 数值（那等于编造）：\n{out}"
    )


def test_geo_diagnostics_do_not_change_exit_code(tmp_path: Path) -> None:
    """GEO/RE/RES 同样是诊断：coarse 与不 coarse 的退出码必须相同。"""
    coarse = _make_case(tmp_path / "a", objective="steady", ddt="steadyState")
    _add_geometry(coarse, ctm=0.1, cells=400, nu=1e-6, u_mag=1.0)
    fine = _make_case(tmp_path / "b", objective="steady", ddt="steadyState")
    _add_geometry(fine, ctm=0.1, cells=1000000, nu=1e-6, u_mag=1.0)

    assert _run(coarse).returncode == _run(fine).returncode, (
        "RES=coarse 改变了退出码：它应该只是诊断，不是门。"
    )


# ---------------------------------------------------------------------------
# 第三轮陌生用户验收（2026-10-29）后补的三条：这些是**真坑**，不是措辞问题
# ---------------------------------------------------------------------------


def _write_owner(case: Path, n_cells: int, n_points: int = 8450, n_faces: int = 16512) -> None:
    """写一个带 FoamFile 头的 owner，note 行同时含 nPoints/nCells/nFaces。

    **这三个数字必须都写**：正是「nFaces 与 nCells 不同」才让「取最后一个纯数字行」这种
    兜底实现露馅（实测把 4096 报成 16512）。
    """
    (case / "constant" / "polyMesh").mkdir(parents=True, exist_ok=True)
    (case / "constant" / "polyMesh" / "owner").write_text(
        "FoamFile\n{\n    format      ascii;\n    class       labelList;\n"
        f'    note        "nPoints: {n_points} nCells: {n_cells} nFaces: {n_faces} '
        f'nInternalFaces: {n_faces // 2}";\n'
        '    location    "constant/polyMesh";\n    object      owner;\n}\n'
        f"\n{n_faces}\n(\n0\n0\n)\n",
        encoding="utf-8",
    )


def test_cells_read_from_owner_not_from_faces(tmp_path: Path) -> None:
    """磁盘网格量必须取自 note 的 `nCells:`，不能取成 list 长度（= nFaces）。

    实测事故：4096 个格子被报成 16512（那其实是 nFaces）。这类"静默取错数"比不报更糟——
    读者会拿它算 cellRe 并得出错误结论。
    """
    case = _make_case(tmp_path, objective="transient", ddt="Euler")
    _add_geometry(case, ctm=0.1, cells=4096, nu=1e-6, u_mag=1.0)
    _write_owner(case, n_cells=4096, n_points=8450, n_faces=16512)

    out = "".join(_run(case).stdout)

    assert "cells=4096" in out, f"必须报磁盘网格 4096：\n{out}"
    assert "16512" not in out.replace("cells=4096", ""), (
        f"不得出现 nFaces 的数字（说明取错了字段）：\n{out}"
    )


def test_stale_mesh_is_detected(tmp_path: Path) -> None:
    """blockMeshDict 改了但 constant/polyMesh 还是旧的 → RES=stale 并点名两个数。

    实测事故：陌生人想加密网格，改了 blockMeshDict 的 `(20 20 1)→(32 32 1)` 就重跑，
    但 run_case.sh 只在 `constant/polyMesh` **不存在**时才 blockMesh，所以求解用的仍是旧网格。
    若诊断只报 blockMeshDict 的数，他会看到 `cells=1024` 和一个假的 `ok` 去交差。
    """
    case = _make_case(tmp_path, objective="transient", ddt="Euler")
    _add_geometry(case, ctm=0.1, cells=1024, nu=1e-6, u_mag=1.0)   # 「以为」是 1024
    _write_owner(case, n_cells=400)                                # 磁盘上仍是 400

    out = "".join(_run(case).stdout)

    assert "RES=stale" in out, f"网格与 blockMeshDict 不一致时必须报 stale：\n{out}"
    assert "1024" in out and "400" in out, f"stale 必须把两个数都写出来：\n{out}"
    assert "constant/polyMesh" in out, f"提示应告诉人删哪里才能重建：\n{out}"


def test_res_threshold_is_cell_reynolds(tmp_path: Path) -> None:
    """RES 判据必须是 cellRe（= Re/sqrt(cells)），不是「cells 与 Re 的绝对比」。

    实测事故：旧判据 `cells < 0.01*Re` 对 **1024 cells + Re=1e5 判了 ok**，
    而那 1024 个格子的 cellRe≈3130、解仍在 3 倍漂移中。
    「明显荒谬时喊、稍好一点就转安慰性措辞」比不喊更坏——读者会把它当放行条。
    """
    case = _make_case(tmp_path, objective="transient", ddt="Euler")
    _add_geometry(case, ctm=0.1, cells=1024, nu=1e-6, u_mag=1.0)
    _write_owner(case, n_cells=1024)

    out = "".join(_run(case).stdout)

    assert "RES=coarse" in out, (
        f"1024 cells + Re=1e5（cellRe≈3130）必须判 coarse，不能判 ok：\n{out}"
    )
    assert "cellRe" in out, f"RES 行必须给出 cellRe 这个量，否则无法复核：\n{out}"


def test_res_ok_needs_cell_re_below_100(tmp_path: Path) -> None:
    """真正够的网格（cellRe<100）才判 ok：Re=1e5 需要 ≥1e6 cells。"""
    case = _make_case(tmp_path, objective="transient", ddt="Euler")
    _add_geometry(case, ctm=0.1, cells=1000000, nu=1e-6, u_mag=1.0)
    _write_owner(case, n_cells=1000000)

    out = "".join(_run(case).stdout)

    assert "RES=ok" in out, f"1e6 cells + Re=1e5（cellRe=100）应判 ok：\n{out}"


def test_stale_suppresses_other_res_conclusions(tmp_path: Path) -> None:
    """网格未重建时，不许再打 RES=ok/coarse（第四轮陌生用户验收实测的真坑）。

    实测：原实现先打 `RES=stale(要 16384，磁盘 400)`，紧接着打 `RES=ok(cells=400 → cellRe≈50)`。
    同一个 RES 前缀、相反的两个结论并列，后者还是按旧网格算的 —— 读者读到第二行就把 stale
    当成已被覆盖，于是拿 400 cells 的 Re=1e5 结果去交差。
    **一个诊断如果会被它自己的下一行否定，它就不算诊断。**
    """
    case = _make_case(tmp_path, objective="transient", ddt="Euler")
    _add_geometry(case, ctm=0.1, cells=16384, nu=1e-6, u_mag=1.0)   # blockMeshDict 想要 16384
    _write_owner(case, n_cells=400)                                 # 磁盘上只有 400

    out = "".join(_run(case).stdout)
    res_lines = [ln for ln in out.splitlines() if ln.startswith("RES=")]

    assert len(res_lines) == 1, (
        f"stale 时 RES 只该有一行（stale），实得 {len(res_lines)} 行：\n" + "\n".join(res_lines)
    )
    assert res_lines[0].startswith("RES=stale"), f"唯一那行必须是 stale：{res_lines[0]!r}"
