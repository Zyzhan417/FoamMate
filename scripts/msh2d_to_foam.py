#!/usr/bin/env python3
"""2D gmsh `.msh`（msh2 ascii）→ OpenFOAM 单层三棱柱 `polyMesh`。

===============================================================================
为什么需要这个工具（三条现成的路都不通，每条都实测过）
==============================================================================
需求形态：一个 **2D** 方腔，要**三角形**网格。

  * `blockMesh` 只能出结构化六面体。`$FOAM_TUTORIALS/fluid/prism` 名字里有 prism，
    但 `blocks` 段全是 `hex (…) (16 8 1)`——"prism" 只是 patch 名 `prismWall`。
  * `gmsh -3` 把 2D 三角面挤出的三棱柱**自动拆成四面体**：`Mesh.Algorithm3D`
    0/1/2/4/6/7/9/10、`Mesh.Optimize 0`、`Mesh.SaveAll`、显式 `Save` 全部给同样的
    2832 个 tet。而 OpenFOAM 的 2D 判据要求「empty 面数 == 2 × cells」且「所有边垂直
    或平行于非空方向」——单层四面体两条都不满足，实测 checkMesh 报
    `Failed 1 mesh checks`（1888 empty faces vs 2832 cells、1456 条斜边），
    求解在 t=0.04 s 就 `Floating point exception`（Co max 33、残差 1e+297）。
  * `gmshToFoam` 明确拒收纯 2D msh：
    `No cells read from file … Does your file specify any 3D elements`。
    本机也没有任何 stock utility 做 2D → 单层 3D（`polyDualMesh` / `refineMesh` /
    `subsetMesh` / `extrudeMesh` 都不解决拓扑问题）。

所以本工具只做**格式搬运**：拓扑（点、三角形）全部来自 gmsh 的 Delaunay 剖分，
本脚本**不造点、不挪点、不生成网格**，只按 polyMesh 的规则写出
`points / faces / owner / neighbour / boundary`，并沿 z 拉出 `--thickness` 一层：
每个三角形变成一个三棱柱（2 个三角形 empty 面 + 3 个四边形侧面）。

===============================================================================
自检（任一条不过：写盘前退出 14，绝不留下半个 polyMesh）
==============================================================================
  1. `$MeshFormat` 必须是 msh2 且 ascii（二进制 / msh4 直接拒，不猜）
  2. 所有点共面（2D 面网格）
  3. 每个三角形有向面积 > 0（逆时针）。顺时针源会让所有面法向朝内，静默出错
  4. 每条边的相邻 cell 数 ∈ {1, 2}；≥3 = 非流形
  5. 每条边界边必须能从 msh 的 `Physical Curve` 拿到 patch 名，拿不到就报错，不猜
  6. 三角形元素只能来自一个 physical surface（本工具只处理单区域）

写盘格式纪律（每条都是实测踩出来的红）：
  * internal faces 必须按 `(owner, neighbour)` 排序（"upper triangular order"），
    否则 checkMesh：`***Faces not in upper triangular order.` + `Failed 1 mesh checks`
  * front/back 面归**一个** empty patch（2D 判据数 `nFaces == 2*cells`）；
    侧面归各自 wall patch；front/back 的面片顺序决定法向朝外——
    z=0 用 `(a,c,b)`，z=t 用 `(a+N, b+N, c+N)`
  * 输出目录非空时**拒写**（混进旧网格 = 一个看起来建好、其实跑不对的算例）；
    确实要覆盖时显式给 `--force`

===============================================================================
用法
==============================================================================
    gmsh -2 system/triangle2d.geo -format msh2 -o system/triangle2d.msh
    rm -rf constant/polyMesh          # 不删旧网格 = 门禁在旧网格上全绿
    python3 scripts/msh2d_to_foam.py --msh system/triangle2d.msh \\
            --out constant/polyMesh --thickness 0.01
    checkMesh > log.checkMesh; grep -E "prisms|Mesh OK\\.|\\*\\*\\*" log.checkMesh

退出码：0 成功 / 14 输入或自检不合格（不是程序崩溃）/ 15 输出目录非空且未给
`--force` / 64 用法错误。14 与 64 分开是因为处置相反：14 改网格或几何，64 改调用。

零 OpenFOAM 依赖：本脚本不读 `$WM_PROJECT_DIR`、不调任何 OpenFOAM 命令，
所以它能在没有 OpenFOAM 的机器上被判（`tests/unit/test_msh2d_to_foam.py`）。
真正的网格合法性由 `checkMesh` 判（`tests/contract/test_msh2d_to_foam_mesh.py`）。
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

# ---------------------------------------------------------------------------
# 退出码（与 verify_case 的门码 0–5、其它模块的 10–33 都不撞号）
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_BAD_INPUT = 14   # msh 不合规 / 自检不过
EXIT_OUT_EXISTS = 15  # 输出目录非空且未给 --force
EXIT_USAGE = 64       # 用法错误

MSH_LINE = 1
MSH_TRI = 2


class _BadInput(Exception):
    """自检失败：消息直接给人看，处置是改网格或几何，不是改调用。"""


# ---------------------------------------------------------------------------
# msh2 解析
# ---------------------------------------------------------------------------


def _block(txt: list[str], name: str) -> list[str]:
    i = txt.index(name)
    return txt[i + 2 : i + 2 + int(txt[i + 1])]


def read_msh(path: pathlib.Path):
    """解析 msh2 ascii，返回 (points, tris, lines, dim_names, surf_tags_declared)。"""
    txt = path.read_text(encoding="utf-8", errors="replace").split("\n")

    if "$MeshFormat" not in txt:
        raise _BadInput("文件里没有 $MeshFormat：这不是 gmsh msh 文件")
    # $MeshFormat 是唯一没有「行数」的块：下一行直接是 `2.2 0 8`
    fmt = txt[txt.index("$MeshFormat") + 1].split()
    if len(fmt) < 2:
        raise _BadInput(f"$MeshFormat 行解析不出 (version, binary): {fmt!r}")
    version, binary = fmt[0], int(fmt[1])
    if not version.startswith("2."):
        raise _BadInput(
            f"$MeshFormat 版本是 {version}，本工具只认 msh2（gmsh 的 `-format msh2`）"
        )
    if binary:
        raise _BadInput(
            "$MeshFormat 是二进制格式（第 2 个字段 = 1），本工具只认 ascii；"
            "gmsh 加 `-format msh2` 并确认没有 `-bin`"
        )

    dim_names: dict[tuple[int, int], str] = {}
    if "$PhysicalNames" in txt:
        for line in _block(txt, "$PhysicalNames"):
            parts = line.split('"')
            if len(parts) < 2:
                continue
            dim, tag = (int(x) for x in parts[0].split())
            dim_names[(dim, tag)] = parts[1]

    points: dict[int, tuple[float, float, float]] = {}
    for line in _block(txt, "$Nodes"):
        f = line.split()
        if len(f) == 4:
            points[int(f[0])] = (float(f[1]), float(f[2]), float(f[3]))

    tris: list[tuple[tuple[int, int, int], int]] = []      # (顶点, physical surface tag)
    lines: list[tuple[int, int, int]] = []                 # (端点, physical curve tag)
    for line in _block(txt, "$Elements"):
        f = line.split()
        if not f:
            continue
        etype, ntags = int(f[1]), int(f[2])
        tags = [int(x) for x in f[3 : 3 + ntags]]
        conn = [int(x) for x in f[3 + ntags :]]
        if etype == MSH_TRI:
            tris.append(((conn[0], conn[1], conn[2]), tags[0] if tags else 0))
        elif etype == MSH_LINE:
            lines.append((conn[0], conn[1], tags[0] if tags else 0))
    return points, tris, lines, dim_names


# ---------------------------------------------------------------------------
# polyMesh 写出
# ---------------------------------------------------------------------------

HEADER = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    note        "nPoints:{npoints}  nCells:{ncells}  nFaces:{nfaces}  nInternalFaces:{ninternal}";
    location    "constant/polyMesh";
    object      {obj};
}}
"""

TAIL = "\n// ************************************************************************* //\n"


def _head(cls: str, obj: str, counts: dict[str, int]) -> str:
    return HEADER.format(cls=cls, obj=obj, **counts)


def render(meta: dict, files: dict[str, str]) -> dict[str, str]:
    """把形状拼成「文件名 → 全文」，便于先在内存里组装、再一次性落盘。"""
    counts = {"npoints": meta["npoints"], "ncells": meta["ncells"],
              "nfaces": meta["nfaces"], "ninternal": meta["ninternal"]}

    out: dict[str, str] = {}

    out["points"] = _head("vectorField", "points", counts) + f"{meta['npoints']}\n(\n" + \
        "".join(f"({x!r} {y!r} {z!r})\n" for (x, y, z) in meta["pts"]) + ")" + TAIL

    out["faces"] = _head("faceList", "faces", counts) + f"{meta['nfaces']}\n(\n" + \
        "".join(f"{len(f)}({' '.join(str(i) for i in f)})\n" for f in files["faces"]) + \
        ")" + TAIL

    for name in ("owner", "neighbour"):
        values = files[name]
        out[name] = _head("labelList", name, counts) + f"{len(values)}\n(\n" + \
            "".join(f"{v}\n" for v in values) + ")" + TAIL

    body = f"{len(meta['patches'])}\n(\n"
    for pname, nf, start, ptype in meta["patches"]:
        body += f"    {pname}\n    {{\n        type            {ptype};\n"
        if ptype == "empty":
            body += "        inGroups        1(empty);\n"
        body += f"        nFaces          {nf};\n        startFace       {start};\n    }}\n"
    out["boundary"] = _head("polyBoundaryMesh", "boundary", counts) + body + ")" + TAIL

    return out


# ---------------------------------------------------------------------------
# 主流程：解析 → 自检 → 组装 → 落盘
# ---------------------------------------------------------------------------


def _cells_for_edges(cells):
    """无向边 → [(cell, (i, j)), …]。i→j 是该 cell 里的有向顺序。"""
    edges: dict[frozenset[int], list[tuple[int, tuple[int, int]]]] = collections.defaultdict(list)
    for ci, (a, b, c) in enumerate(cells):
        for (i, j) in ((a, b), (b, c), (c, a)):
            edges[frozenset((i, j))].append((ci, (i, j)))
    return edges


def convert(points, tris, lines, dim_names, thickness: float, front_and_back: str) -> dict:
    """核心转换（纯函数，不碰磁盘）。自检失败抛 _BadInput。"""
    if not tris:
        raise _BadInput(
            "msh 里没有二维三角形元素：需要用 `gmsh -2`（或 geo 里 `Mesh 2;`）"
            "产出的面网格，而不是 -3 的体网格"
        )

    surf_tags = sorted({tag for (_, tag) in tris if tag})
    if len(surf_tags) > 1:
        named = [dim_names.get((2, t), str(t)) for t in surf_tags]
        raise _BadInput(
            f"msh 里有 {len(surf_tags)} 个 physical surface（{named}）："
            "本工具只处理单区域 2D 网格，请逐个导出"
        )

    # ---- 自检 2：共面
    zs = [p[2] for p in points.values()]
    xs = [p[0] for p in points.values()]
    ys = [p[1] for p in points.values()]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1e-30)
    if max(zs) - min(zs) > 1e-9 * extent:
        raise _BadInput(
            f"点不共面（z 跨度 {max(zs) - min(zs):.6g}，面内尺度 {extent:.6g}）："
            "这是 3D 网格，本工具只把 2D 面网格拉成单层棱柱"
        )

    # ---- 自检 3：逆时针
    badly_oriented = 0
    for ((a, b, c), _) in tris:
        ax, ay, _ = points[a]; bx, by, _ = points[b]; cx, cy, _ = points[c]
        if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) <= 0:
            badly_oriented += 1
    if badly_oriented:
        raise _BadInput(
            f"{badly_oriented}/{len(tris)} 个三角形不是逆时针（有向面积 <= 0）："
            "顺时针源会让所有面法向朝内。检查 Curve Loop 的绕向"
            "（从 +z 看应为逆时针），不要靠改本脚本绕过"
        )

    ids = sorted(points)
    if ids != list(range(1, len(ids) + 1)):
        raise _BadInput(
            f"节点编号不连续（{ids[0]}…{ids[-1]}，共 {len(ids)} 个）："
            "msh 的 $Nodes 必须是 1..N 稠密编号"
        )

    # ---- 单元 = 三角形；第二层顶点 = 第一层 + N
    N = len(points)
    cells = [(a - 1, b - 1, c - 1) for ((a, b, c), _) in tris]
    edges = _cells_for_edges(cells)

    # ---- 自检 4：非流形
    over = [e for e, v in edges.items() if len(v) > 2]
    if over:
        raise _BadInput(f"{len(over)} 条边被 3 个以上 cell 共用（非流形），gmsh 输出不该有这种边")

    # ---- 自检 5：边界边必须有 patch 名
    edge_patch: dict[frozenset[int], str] = {}
    for (n1, n2, tag) in lines:
        name = dim_names.get((1, tag))
        if name is None:
            raise _BadInput(
                f"线元素 ({n1},{n2}) 的 physical tag {tag} 不在 $PhysicalNames 里："
                "边界边必须能定位到 patch，本工具不猜"
            )
        edge_patch[frozenset((n1 - 1, n2 - 1))] = name

    # ---- 面表：先 internal（必须按 (owner, neighbour) 排序），再各 patch
    internal: list[tuple[int, int, list[int]]] = []
    for e, lst in edges.items():
        if len(lst) != 2:
            continue
        (c1, _), (c2, _) = lst
        if c1 == c2:
            continue
        own, nei = (c1, c2) if c1 < c2 else (c2, c1)
        i, j = next(pair for (cc, pair) in lst if cc == own)
        internal.append((own, nei, [i, j, j + N, i + N]))
    internal.sort(key=lambda t: (t[0], t[1]))

    faces: list[list[int]] = [f for (_, _, f) in internal]
    owner: list[int] = [o for (o, _, _) in internal]
    neighbour: list[int] = [n for (_, n, _) in internal]
    n_internal = len(faces)

    patches: list[tuple[str, int, int, str]] = []

    fb_start = len(faces)
    for ci, (a, b, c) in enumerate(cells):          # z=0：法向 -z → 倒序
        faces.append([a, c, b]); owner.append(ci); neighbour.append(-1)
    for ci, (a, b, c) in enumerate(cells):          # z=t：法向 +z
        faces.append([a + N, b + N, c + N]); owner.append(ci); neighbour.append(-1)
    patches.append((front_and_back, 2 * len(cells), fb_start, "empty"))

    side_order: list[str] = []
    for (_, _, tag) in lines:
        name = dim_names[(1, tag)]
        if name not in side_order:
            side_order.append(name)

    side: dict[str, list[tuple[list[int], int]]] = {n: [] for n in side_order}
    for e, lst in edges.items():
        if len(lst) != 1:
            continue
        (ci, (i, j)) = lst[0]
        name = edge_patch.get(e)
        if name is None:
            raise _BadInput(f"边界边 ({i},{j}) 没有对应的物理曲线，无法定位 patch")
        side[name].append(([i, j, j + N, i + N], ci))

    for name in side_order:
        start = len(faces)
        for f, ci in side[name]:
            faces.append(f); owner.append(ci); neighbour.append(-1)
        patches.append((name, len(side[name]), start, "wall"))

    return {
        "npoints": 2 * N,
        "ncells": len(cells),
        "nfaces": len(faces),
        "ninternal": n_internal,
        "pts": [(points[i][0], points[i][1], 0.0) for i in range(1, N + 1)]
               + [(points[i][0], points[i][1], float(thickness)) for i in range(1, N + 1)],
        "patches": patches,
    }, {"faces": faces, "owner": owner, "neighbour": neighbour}


def write_polymesh(out_dir: pathlib.Path, rendered: dict[str, str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in rendered.items():
        (out_dir / name).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _UsageParser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64（2 在 verify_case 里是「G2 网格门失败」）。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    ap = _UsageParser(
        description="2D gmsh msh（msh2 ascii）→ OpenFOAM 单层三棱柱 polyMesh。"
                    "拓扑全部来自 gmsh，本工具只做格式搬运。",
    )
    ap.add_argument("--msh", required=True, type=pathlib.Path, help="gmsh -2 产出的 .msh（ascii msh2）")
    ap.add_argument("--out", default=pathlib.Path("constant/polyMesh"), type=pathlib.Path,
                    help="输出目录（缺省 constant/polyMesh）")
    ap.add_argument("--thickness", default=0.01, type=float,
                    help="沿 z 的厚度（2D 虚拟维度，对结果无影响；缺省 0.01）")
    ap.add_argument("--front-and-back", default="frontAndBack",
                    help="前后 empty patch 名（缺省 frontAndBack）")
    ap.add_argument("--force", action="store_true",
                    help="输出目录非空时也覆盖（会先删掉目录里的同名 polyMesh 文件）")
    args = ap.parse_args(argv)

    if args.thickness <= 0:
        print(f"--thickness 必须为正（实得 {args.thickness}）", file=sys.stderr)
        return EXIT_USAGE
    if not args.msh.is_file():
        print(f"--msh 不存在: {args.msh}", file=sys.stderr)
        return EXIT_USAGE

    meta = None
    files = None
    try:
        points, tris, lines, dim_names = read_msh(args.msh)
        meta, files = convert(points, tris, lines, dim_names,
                              args.thickness, args.front_and_back)
    except _BadInput as exc:
        print(f"[bad-input] {exc}", file=sys.stderr)
        print("未写任何文件（避免留下半个 polyMesh）。", file=sys.stderr)
        return EXIT_BAD_INPUT

    rendered = render(meta, files)

    if args.out.exists() and any(args.out.iterdir()) and not args.force:
        print(
            f"[out-exists] 输出目录非空: {args.out}\n"
            f"  混进旧网格 = 一个看着建好、其实跑在旧网格上的算例。\n"
            f"  要么 `rm -rf {args.out}`（推荐：换网格就该重建），要么显式加 --force。",
            file=sys.stderr,
        )
        return EXIT_OUT_EXISTS

    write_polymesh(args.out, rendered)

    print(f"MSH={args.msh.resolve()}")
    print(f"THICKNESS={args.thickness:g}")
    print(f"CELLS={meta['ncells']}")
    print(f"INTERNAL_FACES={meta['ninternal']}")
    print(f"BOUNDARY_FACES={meta['nfaces'] - meta['ninternal']}")
    for name, nf, start, ptype in meta["patches"]:
        print(f"PATCH {name} nFaces={nf} startFace={start} type={ptype}")
    print(f"POLYMESH={args.out.resolve()}")
    print("STATUS=ok")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
