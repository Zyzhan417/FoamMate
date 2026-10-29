"""模块 I（`scripts/msh2d_to_foam.py`）的 L1 单元测试：**零 OpenFOAM、零 gmsh 依赖**。

## 这一层为什么必须存在（分工判据）

转换器的风险不在"网格质量好不好"（那由 contract 层的 `checkMesh` 判），而在**格式与自检**：
面顺序、法向朝向、patch 归属、拒绝半成品。这几件事全都能在没装 OpenFOAM 的机器上判，
而且必须在这里判——因为它们的失败形态是**静默**的：

  * internal faces 没排序 → `checkMesh` 报 `***Faces not in upper triangular order.`
    只是 1 项，很容易被当成噪音放过；
  * 顺时针三角形 → 所有面法向朝内，`checkMesh` 通常仍然 `Mesh OK.`，
    错到求解器才以"莫名其妙发散"出现；
  * 输出目录混进旧网格 → 门禁在旧网格上全绿。

所以断言的对象是**文件内容的结构性质**（owner/neighbour 单调、每条面恰好一个 owner、
empty 面数 == 2×cells、拒绝时一个文件都没写），不是"跑起来没崩"。

## fixture 是自己拼的 msh2 文本

不依赖 gmsh 版本、不依赖磁盘上的任何 tutorial：把 msh2 ascii 的最小合法结构写成字符串，
测什么就造什么（含逆向 fixture：顺时针、非流形、缺 patch 名、不共面、msh4、二进制）。
真实 gmsh 的产物由 `tests/contract/test_msh2d_to_foam_mesh.py` 覆盖。
"""

from __future__ import annotations

import collections
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "msh2d_to_foam.py"

EXIT_OK = 0
EXIT_BAD_INPUT = 14
EXIT_OUT_EXISTS = 15
EXIT_USAGE = 64


# ---------------------------------------------------------------------------
# msh2 合成器
# ---------------------------------------------------------------------------


def make_msh(
    points: list[tuple[float, float, float]],
    tris: list[tuple[tuple[int, int, int], int]],
    boundaries: list[tuple[int, int, int]],
    curve_names: dict[int, str],
    surface_name: str = "internal",
    version: str = "2.2",
    binary: int = 0,
) -> str:
    """按 msh2 ascii 的字段顺序拼一份网格。

    points      1-indexed 的 (x,y,z)
    tris        [((n1,n2,n3), physical_surface_tag)]
    boundaries  [(n1, n2, physical_curve_tag)]
    curve_names {physical_curve_tag: patch 名}
    """
    surf_tags = sorted({t for (_, t) in tris})
    names = [(1, tag, name) for tag, name in sorted(curve_names.items())]
    names += [(2, tag, f"{surface_name}{tag}" if len(surf_tags) > 1 else surface_name)
              for tag in surf_tags]

    out = [f"$MeshFormat", f"{version} {binary} 8", "$EndMeshFormat",
           "$PhysicalNames", str(len(names))]
    out += [f'{dim} {tag} "{name}"' for (dim, tag, name) in names]
    out.append("$EndPhysicalNames")

    out += ["$Nodes", str(len(points))]
    out += [f"{i + 1} {x} {y} {z}" for i, (x, y, z) in enumerate(points)]
    out.append("$EndNodes")

    elements: list[str] = []
    for (n1, n2, tag) in boundaries:            # type 1 = 线
        elements.append(f"{len(elements) + 1} 1 2 {tag} {tag} {n1} {n2}")
    for ((n1, n2, n3), tag) in tris:            # type 2 = 三角形
        elements.append(f"{len(elements) + 1} 2 2 {tag} {tag} {n1} {n2} {n3}")

    out += ["$Elements", str(len(elements))] + elements + ["$EndElements", ""]
    return "\n".join(out)


def square_fixture() -> str:
    """单位正方形，两个三角形（逆时针），四条边界边各自一个物理曲线。"""
    return make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        tris=[((1, 2, 3), 5), ((1, 3, 4), 5)],
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 4, 3), (4, 1, 4)],
        curve_names={1: "bottomWall", 2: "rightWall", 3: "topWall", 4: "leftWall"},
    )


def fan_fixture() -> str:
    """4 个三角形绕中心点成扇形，**单元顺序故意让邻居降序出现**。

    T0=(5,1,2) 的两条内部边按插入顺序是 (5,1)→邻 cell3、(2,5)→邻 cell1，
    即 (owner0, neighbour3) 先于 (owner0, neighbour1) 出现。不排序就会违反
    OpenFOAM 的 upper-triangular order。
    """
    return make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 0)],
        tris=[((5, 1, 2), 9), ((5, 2, 3), 9), ((5, 3, 4), 9), ((5, 4, 1), 9)],
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 4, 3), (4, 1, 4)],
        curve_names={1: "bottomWall", 2: "rightWall", 3: "topWall", 4: "leftWall"},
    )


# ---------------------------------------------------------------------------
# 跑一次 + 解析输出
# ---------------------------------------------------------------------------


def run(msh_text: str, tmp_path: Path, *extra: str, out_name: str = "polyMesh"):
    msh = tmp_path / "m.msh"
    msh.write_text(msh_text, encoding="utf-8")
    out = tmp_path / out_name
    cmd = [str(SCRIPT), "--msh", str(msh), "--out", str(out), *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return proc, out


def _foam_list(path: Path) -> tuple[int, list[str]]:
    """取 polyMesh 文件的「计数行 + 括号列表体」：跳过 FoamFile 头，返回 (n, 每行原文)。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines) and lines[i].strip() != "}":      # FoamFile 头结束
        i += 1
    i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    n = int(lines[i].strip())
    assert lines[i + 1].strip() == "(", f"{path.name}: 计数行之后应是 '('\n{lines[i:i+3]}"
    body: list[str] = []
    j = i + 2
    while lines[j].strip() != ")":
        body.append(lines[j].strip())
        j += 1
    return n, body


def parse_field(path: Path) -> list[int]:
    n, body = _foam_list(path)
    values = [int(x) for x in body]
    assert len(values) == n, f"{path.name} 声明 {n} 个，实际 {len(values)} 个"
    return values


def parse_faces(path: Path) -> list[list[int]]:
    n, body = _foam_list(path)
    faces = [[int(x) for x in m.group(2).split()]
             for m in (re.match(r"^(\d+)\(([\d ]+)\)$", line) for line in body) if m]
    assert len(faces) == n, f"面表声明 {n} 个，实际解析 {len(faces)} 个"
    return faces


def parse_points(path: Path) -> list[tuple[float, float, float]]:
    n, body = _foam_list(path)
    pts = [tuple(float(v) for v in m.group(1).split())
           for m in (re.match(r"^\(([-\d.eE+ ]+)\)$", line) for line in body) if m]
    assert len(pts) == n, f"点表声明 {n} 个，实际解析 {len(pts)} 个"
    return pts


def parse_boundary(path: Path) -> dict[str, tuple[int, int, str]]:
    """→ {patch 名: (nFaces, startFace, type)}。"""
    n, body = _foam_list(path)
    patches: dict[str, tuple[int, int, str]] = {}
    i = 0
    while i < len(body):
        name = body[i]
        assert body[i + 1] == "{", f"patch {name} 后面应是 '{{'\n{body[i:i+4]}"
        j = i + 2
        fields: dict[str, str] = {}
        while body[j] != "}":
            key, _, value = body[j].partition(" ")
            fields[key] = value.strip().rstrip(";").strip()
            j += 1
        patches[name] = (int(fields["nFaces"]), int(fields["startFace"]), fields["type"])
        i = j + 1
    assert len(patches) == n, f"boundary 声明 {n} 个 patch，解析出 {len(patches)} 个"
    return patches


def stdout_kv(proc) -> dict[str, str]:
    kv: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line and " " not in line.split("=")[0]:
            k, v = line.split("=", 1)
            kv[k] = v
    return kv


def internal_count(neighbour: list[int]) -> int:
    """internal faces 数 = neighbour 里非 -1 的条目数（边界面的 neighbour 恒为 -1）。

    注意：**不能**用 `len(neighbour)`。polyMesh 要求 neighbour 与 faces 等长，
    边界面填 -1，所以长度恒等于总面数。
    """
    return sum(1 for v in neighbour if v != -1)


# ---------------------------------------------------------------------------
# 1. 基本形状：面数、patch 归属、2D 判据的代数前提
# ---------------------------------------------------------------------------


def test_two_triangles_square_counts(tmp_path: Path):
    proc, out = run(square_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    kv = stdout_kv(proc)
    assert kv["CELLS"] == "2"
    assert kv["INTERNAL_FACES"] == "1"          # 两个三角形共用的对角边
    assert kv["BOUNDARY_FACES"] == "8"          # 2*2 前后 + 4 条边

    boundary = parse_boundary(out / "boundary")
    assert boundary["frontAndBack"][0] == 4, "empty 面数必须 = 2 × cells"
    assert boundary["frontAndBack"][2] == "empty"
    for name in ("bottomWall", "rightWall", "topWall", "leftWall"):
        assert boundary[name] == (1, boundary[name][1], "wall"), boundary[name]


def test_patch_names_come_from_physical_curves_in_declaration_order(tmp_path: Path):
    proc, out = run(square_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    order = list(parse_boundary(out / "boundary"))
    assert order == ["frontAndBack", "bottomWall", "rightWall", "topWall", "leftWall"], order


def test_points_are_doubled_with_requested_thickness(tmp_path: Path):
    proc, out = run(square_fixture(), tmp_path, "--thickness", "0.25")
    assert proc.returncode == EXIT_OK, proc.stderr
    pts = parse_points(out / "points")
    assert len(pts) == 8, f"4 个 2D 点应变成 8 个（两层），实得 {len(pts)}"
    assert {p[2] for p in pts} == {0.0, 0.25}


def test_every_cell_has_five_face_incidences(tmp_path: Path):
    """三棱柱：2 个三角形前后 + 3 个四边形侧面，每个 cell 恰好 5 个面。

    注意数的是 **incidence**（owner 出现 + neighbour 出现），不是 owner 计数：
    internal face 只记一次 owner，按 owner 数会得到 4，那是表示法而不是漏面。
    """
    proc, out = run(square_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    owner = parse_field(out / "owner")
    neighbour = parse_field(out / "neighbour")
    faces = parse_faces(out / "faces")

    incidence = collections.Counter(owner)
    incidence.update(v for v in neighbour if v != -1)
    assert set(incidence.values()) == {5}, incidence
    assert internal_count(neighbour) == 1, "两个三角形共用一条内部边"
    assert sum(1 for f in faces if len(f) == 3) == 4, "三角面应恰好 2×cells"
    assert sum(1 for f in faces if len(f) == 4) == 5, "四边形面应 = internal(1) + 侧壁(4)"


def test_face_indices_stay_in_range(tmp_path: Path):
    proc, out = run(square_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    npoints = len(parse_points(out / "points"))
    for f in parse_faces(out / "faces"):
        assert all(0 <= i < npoints for i in f), f"面 {f} 引用了不存在的点（npoints={npoints}）"


# ---------------------------------------------------------------------------
# 2. 排序与 owner/neighbour 一致性（checkMesh 真的会红的两处）
# ---------------------------------------------------------------------------


def test_internal_faces_are_in_upper_triangular_order(tmp_path: Path):
    """owner 非降；同一 owner 内 neighbour 升序。fixture 的邻居是降序出现的。"""
    proc, out = run(fan_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    owner = parse_field(out / "owner")
    neighbour = parse_field(out / "neighbour")

    nint = internal_count(neighbour)
    pairs = list(zip(owner[:nint], neighbour[:nint]))
    assert len(pairs) == 4, f"扇形 4 个三角形应有 4 条内部边，实得 {len(pairs)}"
    assert pairs == sorted(pairs), f"internal faces 未按 (owner, neighbour) 排序：{pairs}"
    assert (0, 1) in pairs and (0, 3) in pairs, pairs


def test_owner_less_than_neighbour_for_every_internal_face(tmp_path: Path):
    proc, out = run(fan_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    owner = parse_field(out / "owner")
    neighbour = parse_field(out / "neighbour")
    nint = internal_count(neighbour)
    for o, n in zip(owner[:nint], neighbour[:nint]):
        assert o < n, f"internal face 的 owner {o} 必须小于 neighbour {n}"


def test_neighbour_is_minus_one_on_boundary_faces(tmp_path: Path):
    proc, out = run(square_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    neighbour = parse_field(out / "neighbour")
    nfaces = len(parse_faces(out / "faces"))
    assert len(neighbour) == nfaces, "neighbour 必须与 faces 等长（边界面填 -1）"
    nint = internal_count(neighbour)
    assert set(neighbour[nint:]) == {-1}, neighbour[nint:]


def test_boundary_starts_are_contiguous_and_cover_all_faces(tmp_path: Path):
    proc, out = run(square_fixture(), tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    nfaces = len(parse_faces(out / "faces"))
    nint = internal_count(parse_field(out / "neighbour"))
    boundary = parse_boundary(out / "boundary")
    cursor = nint          # 边界面紧接在内部面之后
    for name, (nf, start, _) in boundary.items():
        assert start == cursor, f"{name} 的 startFace={start} 与上一段结束 {cursor} 不连续"
        cursor += nf
    assert cursor == nfaces, f"patch 覆盖到 {cursor}，实际有 {nfaces} 个面"


# ---------------------------------------------------------------------------
# 3. 自检：拒绝时不写任何文件（14）
# ---------------------------------------------------------------------------


def _assert_rejected(proc, out: Path, *, must_contain: str):
    assert proc.returncode == EXIT_BAD_INPUT, (
        f"应退 {EXIT_BAD_INPUT}（输入不合格），实得 {proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert must_contain in proc.stderr, proc.stderr
    assert not (out / "points").exists(), "自检失败时不得留下任何 polyMesh 文件"


def test_clockwise_triangle_is_rejected(tmp_path: Path):
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        tris=[((2, 1, 3), 5), ((1, 3, 4), 5)],     # 第一个三角形被转成顺时针
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 4, 3), (4, 1, 4)],
        curve_names={1: "b", 2: "r", 3: "t", 4: "l"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="逆时针")


def test_boundary_edge_without_physical_curve_is_rejected(tmp_path: Path):
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        tris=[((1, 2, 3), 5), ((1, 3, 4), 5)],
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 4, 3)],      # 少了 (4,1)
        curve_names={1: "b", 2: "r", 3: "t"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="没有对应的物理曲线")


def test_unknown_physical_tag_is_rejected(tmp_path: Path):
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0)],
        tris=[((1, 2, 3), 5)],
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 1, 99)],     # 99 未声明
        curve_names={1: "b", 2: "r"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="不在 $PhysicalNames")


def test_non_manifold_edge_is_rejected(tmp_path: Path):
    """三个三角形共用 (1,2)：平面几何里不可能，但解析层必须拦住而不是写出坏网格。

    三个三角形都要是逆时针，否则会被「朝向」那条自检先拦住（那样就测不到非流形）。
    """
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0), (0.5, 1, 0), (0.5, 2, 0), (0.5, -1, 0)],
        tris=[((1, 2, 3), 5), ((1, 2, 4), 5), ((2, 1, 5), 5)],
        boundaries=[(2, 3, 1), (3, 1, 2), (2, 4, 3), (4, 1, 4), (1, 5, 5), (5, 2, 6)],
        curve_names={1: "a", 2: "b", 3: "c", 4: "d", 5: "e", 6: "f"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="非流形")


def test_non_planar_points_are_rejected(tmp_path: Path):
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0.5), (0, 1, 0)],   # 一个点离开 z=0 面
        tris=[((1, 2, 3), 5), ((1, 3, 4), 5)],
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 4, 3), (4, 1, 4)],
        curve_names={1: "b", 2: "r", 3: "t", 4: "l"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="不共面")


def test_two_physical_surfaces_are_rejected(tmp_path: Path):
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
        tris=[((1, 2, 3), 5), ((1, 3, 4), 6)],       # 两个区域
        boundaries=[(1, 2, 1), (2, 3, 2), (3, 4, 3), (4, 1, 4)],
        curve_names={1: "b", 2: "r", 3: "t", 4: "l"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="单区域")


def test_msh4_is_rejected(tmp_path: Path):
    proc, out = run(square_fixture().replace("2.2 0 8", "4.1 0 8", 1), tmp_path)
    _assert_rejected(proc, out, must_contain="msh2")


def test_binary_msh_is_rejected(tmp_path: Path):
    proc, out = run(square_fixture().replace("2.2 0 8", "2.2 1 8", 1), tmp_path)
    _assert_rejected(proc, out, must_contain="ascii")


def test_volume_only_msh_is_rejected(tmp_path: Path):
    """只有线元素、没有三角形 = 用户拿 -3 的体网格或纯 1D 网格来跑。"""
    text = make_msh(
        points=[(0, 0, 0), (1, 0, 0)],
        tris=[],
        boundaries=[(1, 2, 1)],
        curve_names={1: "b"},
    )
    proc, out = run(text, tmp_path)
    _assert_rejected(proc, out, must_contain="没有二维三角形元素")


# ---------------------------------------------------------------------------
# 4. 输出目录守护（15）与 CLI 用法（64）
# ---------------------------------------------------------------------------


def test_non_empty_output_dir_is_refused(tmp_path: Path):
    out = tmp_path / "polyMesh"
    out.mkdir()
    (out / "points").write_text("SENTINEL\n", encoding="utf-8")

    msh = tmp_path / "m.msh"
    msh.write_text(square_fixture(), encoding="utf-8")
    proc = subprocess.run(
        [str(SCRIPT), "--msh", str(msh), "--out", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == EXIT_OUT_EXISTS, proc.stderr
    assert (out / "points").read_text(encoding="utf-8") == "SENTINEL\n", "拒写时不得改动已有文件"
    assert not (out / "faces").exists(), "拒写时不得写出新文件"


def test_force_overwrites_existing_output(tmp_path: Path):
    out = tmp_path / "polyMesh"
    out.mkdir()
    (out / "stale").write_text("x", encoding="utf-8")
    msh = tmp_path / "m.msh"
    msh.write_text(square_fixture(), encoding="utf-8")

    proc = subprocess.run(
        [str(SCRIPT), "--msh", str(msh), "--out", str(out), "--force"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (out / "owner").is_file()


def test_missing_required_arg_exits_64():
    proc = subprocess.run([str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert proc.stderr.strip(), "用法错误必须写 stderr"


def test_missing_msh_file_exits_64(tmp_path: Path):
    proc = subprocess.run(
        [str(SCRIPT), "--msh", str(tmp_path / "nope.msh"), "--out", str(tmp_path / "o")],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert "不存在" in proc.stderr


def test_nonpositive_thickness_exits_64(tmp_path: Path):
    msh = tmp_path / "m.msh"
    msh.write_text(square_fixture(), encoding="utf-8")
    proc = subprocess.run(
        [str(SCRIPT), "--msh", str(msh), "--out", str(tmp_path / "o"), "--thickness", "0"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert "thickness" in proc.stderr


# ---------------------------------------------------------------------------
# 5. 可移植性：本脚本必须零 OpenFOAM 依赖（能在没装的机器上判）
# ---------------------------------------------------------------------------


def test_script_does_not_require_openfoam(tmp_path: Path):
    """清掉所有 FOAM_* 与 WM_PROJECT_DIR 后必须照常工作。

    这条是「零 OpenFOAM 依赖」的判据：如果将来有人给它加一句
    `source $WM_PROJECT_DIR/etc/bashrc` 或读 `$FOAM_TUTORIALS`，这里会红。
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("FOAM") and k != "WM_PROJECT_DIR"}
    msh = tmp_path / "m.msh"
    msh.write_text(square_fixture(), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--msh", str(msh), "--out", str(tmp_path / "o")],
        capture_output=True, text=True, timeout=120, env=env,
    )
    assert proc.returncode == EXIT_OK, proc.stderr
