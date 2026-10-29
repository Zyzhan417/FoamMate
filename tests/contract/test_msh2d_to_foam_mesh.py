"""模块 I（`scripts/msh2d_to_foam.py`）的 L2 契约测试：**真 gmsh + 真 checkMesh**。

L1（`tests/unit/test_msh2d_to_foam.py`）判的是文件结构；这里判的是**OpenFOAM 是否接受
这份网格**，也就是 2D 判据本身：

  * `faces on empty patches == 2 × cells`（`checkMesh` 的 1D/2D 判据）
  * `Mesh OK.`（无 `***` 失败）
  * 单元类型是 `prisms`（不是 tets——单层四面体不满足上面两条，实测会发散）
  * 5 个 patch 的 `nFaces` 与几何一致（20/20/20/20 + 1888 empty）

为什么必须真跑：这三条都是 OpenFOAM 内部的几何判据，L1 只能近似它的代数前提
（empty 面数 = 2×cells），不能替它判；而且转换器最容易犯的错
（internal faces 未按 upper-triangular 排序）只有 `checkMesh` 会直接点名。

环境依赖：gmsh（`gmsh --version`）+ OpenFOAM v13（`/opt/openfoam13/etc/bashrc`）。
缺任一项 skip 并说明原因——**不伪装成通过**（与其它 contract 用例一致）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

# 环境引导（bashrc → env）、cavity 派生源与五个根统一由 `tests/contract/conftest.py`
# 提供：本文件只声明 `foam_env` / `cavity_src` / `roots` 夹具，不再自己 source 一遍。

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "msh2d_to_foam.py"

#: 方腔 0.1 × 0.1 m，l = 0.1/20 —— 与 test00/cavity-02-tri 用同一份几何定义。
#: 只生成 2D 面网格（`Mesh 2;`），拉伸交给被测脚本。
GEO = """\
l = 0.1/20;
Point(1) = {0, 0, 0, l};
Point(2) = {0.1, 0, 0, l};
Point(3) = {0.1, 0.1, 0, l};
Point(4) = {0, 0.1, 0, l};
Line(1) = {1, 2};
Line(2) = {2, 3};
Line(3) = {3, 4};
Line(4) = {4, 1};
Curve Loop(1) = {1, 2, 3, 4};
Plane Surface(1) = {1};
Physical Curve("bottomWall") = {1};
Physical Curve("rightWall")  = {2};
Physical Curve("movingWall") = {3};
Physical Curve("leftWall")   = {4};
Physical Surface("internal") = {1};
Mesh.CharacteristicLengthMax = l;
Mesh.CharacteristicLengthMin = 0.7*l;
Mesh 2;
"""

CONTROL_DICT = """\
FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
solver incompressibleFluid;
startFrom startTime; startTime 0; stopAt endTime; endTime 0.01; deltaT 0.005;
writeControl timeStep; writeInterval 100;
"""

#: 合并版命名：三条壁面归一个 `fixedWalls` patch，于是派生源的 `0/` 边界字段
#: 可以原样复用（用于 test_solver_accepts_the_mesh）。也顺带证明转换器支持
#: 「多条物理曲线 → 一个 patch」。
GEO_FIXEDWALLS = GEO.replace(
    'Physical Curve("bottomWall") = {1};\n'
    'Physical Curve("rightWall")  = {2};\n'
    'Physical Curve("movingWall") = {3};\n'
    'Physical Curve("leftWall")   = {4};',
    'Physical Curve("fixedWalls") = {1, 2, 4};\n'
    'Physical Curve("movingWall") = {3};'
)


# ---------------------------------------------------------------- 基础设施


def _gmsh_available() -> bool:
    return shutil.which("gmsh") is not None


@pytest.fixture(scope="module")
def mesh_case(tmp_path_factory, foam_env: dict) -> tuple[dict, Path, subprocess.CompletedProcess]:
    """gmsh 出 2D msh → 被测脚本转 polyMesh → checkMesh。整个模块共用一次。"""
    if not _gmsh_available():
        pytest.skip("未安装 gmsh：这条契约无法判定")
    if not shutil.which("checkMesh", path=foam_env.get("PATH")):
        pytest.skip("source 后 PATH 里仍没有 checkMesh")

    case = tmp_path_factory.mktemp("msh2d") / "case"
    (case / "system").mkdir(parents=True)
    (case / "constant").mkdir()
    (case / "system" / "controlDict").write_text(CONTROL_DICT, encoding="utf-8")
    geo = case / "system" / "triangle2d.geo"
    geo.write_text(GEO, encoding="utf-8")

    msh = case / "system" / "triangle2d.msh"
    proc = subprocess.run(
        ["gmsh", "-2", str(geo), "-format", "msh2", "-o", str(msh)],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, f"gmsh 失败：{proc.stderr[:500]}"
    assert msh.is_file(), "gmsh 没有产出 msh"

    conv = subprocess.run(
        [str(SCRIPT), "--msh", str(msh), "--out", str(case / "constant" / "polyMesh"),
         "--thickness", "0.01"],
        capture_output=True, text=True, timeout=300,
    )
    return foam_env, case, conv


def checkmesh(env: dict, case: Path) -> tuple[subprocess.CompletedProcess, str]:
    proc = subprocess.run(
        ["checkMesh"], cwd=case, env=env, capture_output=True, text=True, timeout=600,
    )
    log = proc.stdout + proc.stderr
    (case / "log.checkMesh").write_text(log, encoding="utf-8")
    return proc, log


# ---------------------------------------------------------------- 契约


def test_convert_succeeds(mesh_case):
    _, _, conv = mesh_case
    assert conv.returncode == 0, f"转换失败（RC={conv.returncode}）：{conv.stderr[:500]}"
    assert "STATUS=ok" in conv.stdout


def test_converter_reports_gmsh_truth(mesh_case):
    """报告的数字必须与 gmsh 实际剖分一致（不是拍出来的 20×20）。"""
    _, _, conv = mesh_case
    kv = dict(line.split("=", 1) for line in conv.stdout.splitlines()
              if "=" in line and " " not in line.split("=")[0])
    cells = int(kv["CELLS"])
    assert cells > 0
    assert int(kv["INTERNAL_FACES"]) + int(kv["BOUNDARY_FACES"]) > 0
    # empty 面必须恰好是 2 × cells（这是 2D 判据的代数前提，checkMesh 会再判一次）
    fb = [line for line in conv.stdout.splitlines() if line.startswith("PATCH frontAndBack")]
    assert fb, conv.stdout
    assert 2 * cells == int(re.search(r"nFaces=(\d+)", fb[0]).group(1))


def test_checkmesh_accepts_the_mesh(mesh_case):
    env, case, conv = mesh_case
    assert conv.returncode == 0, conv.stderr
    proc, log = checkmesh(env, case)

    assert "Mesh OK." in log, (
        "checkMesh 没通过。失败行：\n"
        + "\n".join(line for line in log.splitlines() if "***" in line or "Failed" in line)
    )
    assert "***" not in log, "checkMesh 报了 *** 行：" + \
        "\n".join(line for line in log.splitlines() if "***" in line)
    assert not re.search(r"Failed [1-9]\d* mesh checks", log), log[-2000:]


def test_cells_are_prisms_not_tets(mesh_case):
    """单层四面体会同时违反 2D 判据并在 t≈0.04 s 发散——这条钉住单元类型。"""
    env, case, conv = mesh_case
    assert conv.returncode == 0, conv.stderr
    _, log = checkmesh(env, case)

    n_cells = int(re.search(r"^\s*cells:\s+(\d+)", log, re.M).group(1))
    n_prisms = int(re.search(r"^\s*prisms:\s+(\d+)", log, re.M).group(1))
    n_tets = int(re.search(r"^\s*tet wedges:\s+(\d+)", log, re.M).group(1))
    assert n_prisms == n_cells, f"cells={n_cells} prisms={n_prisms}：应全部是三棱柱"
    assert n_tets == 0, f"出现 {n_tets} 个四面体：单层四面体不满足 2D 判据"


def test_empty_patch_is_exactly_twice_the_cells(mesh_case):
    env, case, conv = mesh_case
    assert conv.returncode == 0, conv.stderr
    _, log = checkmesh(env, case)
    n_cells = int(re.search(r"^\s*cells:\s+(\d+)", log, re.M).group(1))

    boundary = (case / "constant" / "polyMesh" / "boundary").read_text(encoding="utf-8")
    m = re.search(r"frontAndBack\s*\n\s*\{[^}]*type\s+empty;[^}]*nFaces\s+(\d+);", boundary)
    assert m, boundary[:800]
    assert int(m.group(1)) == 2 * n_cells, boundary[:800]


def test_domain_geometry_is_preserved(mesh_case):
    """拉伸只加 z 厚度，不改面内几何：bounding box 必须是 (0 0 0)–(0.1 0.1 0.01)。"""
    env, case, conv = mesh_case
    assert conv.returncode == 0, conv.stderr
    _, log = checkmesh(env, case)
    m = re.search(r"Overall domain bounding box \(([^)]+)\) \(([^)]+)\)", log)
    assert m, log[:2000]
    lo = [float(v) for v in m.group(1).split()]
    hi = [float(v) for v in m.group(2).split()]
    assert lo == pytest.approx([0.0, 0.0, 0.0], abs=1e-12), lo
    assert hi == pytest.approx([0.1, 0.1, 0.01], abs=1e-9), hi


def test_patch_face_counts_match_the_geometry(mesh_case):
    """每条边 20 个边界面片（l = 0.1/20 → 每边 20 段）。"""
    env, case, conv = mesh_case
    assert conv.returncode == 0, conv.stderr
    _, log = checkmesh(env, case)
    boundary = (case / "constant" / "polyMesh" / "boundary").read_text(encoding="utf-8")
    for name in ("bottomWall", "rightWall", "movingWall", "leftWall"):
        m = re.search(rf"{name}\s*\n\s*\{{[^}}]*nFaces\s+(\d+);", boundary)
        assert m, f"boundary 里没有 {name}：{boundary[:600]}"
        assert int(m.group(1)) == 20, f"{name} 有 {m.group(1)} 个面，应为 20"


def test_refuses_to_overwrite_a_live_mesh(mesh_case):
    """已存在网格时必须拒写（15）——否则会得到新旧混合的 polyMesh。"""
    _, case, conv = mesh_case
    assert conv.returncode == 0, conv.stderr
    msh = case / "system" / "triangle2d.msh"
    proc = subprocess.run(
        [str(SCRIPT), "--msh", str(msh), "--out", str(case / "constant" / "polyMesh")],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 15, proc.stderr
    assert "非空" in proc.stderr


def test_solver_accepts_the_mesh(tmp_path, foam_env: dict, cavity_src: Path):
    """把导入的网格装进一个**可解**的 case，短跑 2 步：求解器读得进、不立即崩。

    为什么要真装一遍：`checkMesh` 通过不等于求解器能读。判据是「无 FOAM FATAL +
    RC=0 + 到达末时刻」。**不做**五门门禁（那是 run_case/verify_case 的职责）。

    这里用合并版 patch 命名（`fixedWalls` = 三条壁面），因此派生源 `0/` 的边界字段
    可以原样复用、无需改名——这同时证明了转换器支持「多条物理曲线 → 一个 patch」。
    四壁分开命名的路径由上面的 checkMesh 用例覆盖。
    """
    if not _gmsh_available():
        pytest.skip("未安装 gmsh：这条契约无法判定")
    if not shutil.which("checkMesh", path=foam_env.get("PATH")):
        pytest.skip("source 后 PATH 里仍没有 checkMesh")
    env = foam_env

    case = tmp_path / "run"
    shutil.copytree(cavity_src, case)
    shutil.rmtree(case / "constant" / "polyMesh", ignore_errors=True)
    (case / "system" / "blockMeshDict").unlink(missing_ok=True)

    # 只跑 2 步：foamRun 在 v13 不接受时间参数，时长由 controlDict.endTime 决定
    control = case / "system" / "controlDict"
    text = control.read_text(encoding="utf-8")
    new_text, n = re.subn(r"^endTime\s+\S+;", "endTime         0.01;", text, flags=re.M)
    assert n == 1, f"controlDict 里没有唯一的 endTime 行（替换了 {n} 处）"
    control.write_text(new_text, encoding="utf-8")

    geo = case / "system" / "triangle2d.geo"
    geo.write_text(GEO_FIXEDWALLS, encoding="utf-8")
    msh = case / "system" / "triangle2d.msh"
    proc = subprocess.run(["gmsh", "-2", str(geo), "-format", "msh2", "-o", str(msh)],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"gmsh 失败：{proc.stderr[:500]}"

    conv = subprocess.run(
        [str(SCRIPT), "--msh", str(msh), "--out", str(case / "constant" / "polyMesh")],
        capture_output=True, text=True, timeout=300,
    )
    assert conv.returncode == 0, f"转换失败：{conv.stderr[:500]}"

    run = subprocess.run(["foamRun"], cwd=case, env=env,
                         capture_output=True, text=True, timeout=600)
    log = run.stdout + run.stderr
    assert "FOAM FATAL" not in log, (
        "求解器拒绝了这份网格：\n"
        + "\n".join(line for line in log.splitlines() if "FOAM FATAL" in line or "patch" in line.lower())
        + "\n" + log[-1500:]
    )
    assert run.returncode == 0, f"foamRun RC={run.returncode}\n{log[-2000:]}"
    assert re.search(r"^Time = 0\.01s?$", log, re.M), log[-2000:]
