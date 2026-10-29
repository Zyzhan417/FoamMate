#!/usr/bin/env python3
"""bench/runners/ours_scripted.py — 被测臂（A 形态）：12 个冻结任务的**确定性改动计划**。

本文件是「臂」，不是驱动器：它只回答两件事——
  ① 每个任务要改成什么（`PLANS`，每条改动带一条 R1 证据）；
  ② 怎么把一条改动施加到已派生的 case 树上（`apply`）。

派单、落盘、门禁、断言、归约全在 `bench/runners/run_bench.py`。

===============================================================================
一、为什么是「写死的计划」而不是 LLM（本轮范围，计划 §0 判断 Aa）
===============================================================================
计划 §0 明确：本轮测的是 **C→E 脚本链对 12 类任务的回归基线**，不是「自然语言 → 四元组」
那一环，也不是「agent 的能力」。所以臂里不调用任何模型，`tokens_total` 恒为 0。

===============================================================================
二、三种改动词汇（`Edit.kind`），以及为什么第三种必须存在
===============================================================================
  `set`           单 entry 标量/向量/字符串 → `foamDictionary -entry ... -set ...`，**回读校验**。
                  回读不是形式：`-set` 对**不存在的 entry 会新增并退 0**（run_case.sh 坑 1 实测），
                  拼错键名不会失败，只会悄悄多出一个键。
  `copy_file`     从 `$FOAM_TUTORIALS` 复制整个文件（T02 缺 `0/omega`）。
  `replace_text`  **文本块替换**：`entry` = 待替换原文（必须唯一），`new_value` = 替换后文本。
                  T06 把 `fvSolution` 的 `SIMPLE` 块换成 `PIMPLE` 块，`foamDictionary -entry`
                  表达不了「加/删一个块」——run_case.sh 的模块注释与计划 §11 第 2 条都点明了这一点。
                  出现 0 次或多于 1 次一律抛 `UnsupportedEdit`，绝不静默跳过。

**所有改动都在任务 yaml 的 `allowed_files` 内**（L1 测试用 fnmatch 逐条核对）。
唯一会碰 `constant/polyMesh/` 的操作是 `rebuild_mesh=True` 时的删除，它在派生树上通常
是空操作（5 个参考 tutorial 都没有 `polyMesh`），且 `run_bench.py` 会把理由写进
`case.meta.changes`（G5 的 `constant/polyMesh/` 豁免判据）。

===============================================================================
三、12 个任务的改动要点（每条改动后面的 `# R1:` 就是证据本身）
===============================================================================
| 任务 | 改动 | 结构改动 |
|---|---|---|
| T01 | `endTime 10 → 5` | 否 |
| T02 | `RAS.model kEpsilon → kOmegaSST` + 补 `0/omega`（pitzDaily 的 `0/` 没有 omega） | 是（补场） |
| T03 | `vertices` 的 x 由 1 → 2（2:1）+ 顶盖 2 m/s + 重建网格 | 是 |
| T04 | `RAS.model kOmegaSSTLM → kOmegaSST`（T3A 的 `0/` 已有 omega） | 否 |
| T05 | `writeInterval 100 → 50` | 否 |
| T06 | `SIMPLE` 块 → `PIMPLE` 块 + `ddtSchemes Euler` + 瞬态时步 | 是（换块） |
| T07 | 顶盖 `(1 0 0) → (0.5 0 0)` | 否 |
| T08 | `blocks (20 20 1) → (40 40 1)` + 重建网格 | 是 |
| T09 | 顶盖 0.5/1/2 三例 + 汇总表 | 否 |
| T10 | 顶盖速度 × nu = 9 例 | 否 |
| T11 | 顶盖速度 × deltaT = 9 例 + 汇总 CSV（**按 prompt 原文，不改 nu**） | 否 |
| T12 | 不派生 case，给拒绝理由（R5：曲面 / 边界层加密） | — |

**T11 为什么不改 nu**：`bench/tasks/T11.yaml` 的断言是 `nu=2e-05`，但它的 prompt 原文
（"9 例，汇总 max(U) 与迭代步数到 CSV。"）从未要求改 nu，`allowed_files` 也只有
`["system/*","0/U"]`。改 nu 必 G5 越界、不改必断言 mismatch——这是**冻结件内部矛盾**，
已登记在计划 §5 与预注册 §10。按 prompt 原文做事：只做速度扫描 + 汇总表，不为了
让 T11 pass 而越界。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parents[1]
TASKS_DIR = BENCH_DIR / "tasks"

TASK_IDS = tuple(f"T{i:02d}" for i in range(1, 13))

CAVITY = "incompressibleFluid/cavity"
PITZ = "incompressibleFluid/pitzDaily"
PITZ_STEADY = "incompressibleFluid/pitzDailySteady"
T3A = "incompressibleFluid/T3A"


class ApplyError(Exception):
    """改动施加失败（改不了 / 改了没生效）。**绝不静默跳过**。"""


class UnsupportedEdit(ApplyError):
    """改动词汇表达不了这条改动（未知 kind、锚点不唯一、tutorial 里没有该文件）。"""


@dataclass(frozen=True)
class Edit:
    kind: str          # "set" | "copy_file" | "replace_text"
    file: str          # 相对 case 根的路径，如 "system/controlDict"
    entry: str = ""    # set: 关键字名；replace_text: 待替换原文（必须唯一）
    new_value: str = ""  # set: 新值文本；replace_text: 替换后文本
    source: str = ""   # copy_file: $FOAM_TUTORIALS 下的相对路径
    evidence: str = ""  # 必须非空：'R1: $FOAM_TUTORIALS/<rel>:<line> "<逐字原文>"'


@dataclass(frozen=True)
class Example:
    case_id: str
    edits: tuple[Edit, ...]
    rebuild_mesh: bool = False   # True → 改完先删 constant/polyMesh，让 run_case.sh 重新 blockMesh


# =============================================================================
# 证据：一律写成 `$FOAM_TUTORIALS/<相对路径>:<行号> "<逐字原文>"`
#
# 为什么不写本机绝对路径：硬禁令「不得在代码里硬编码本机绝对路径（`/home/<user>/...`），
# 路径必须从 argument 或 $FOAM_TUTORIALS 来」。`$FOAM_TUTORIALS` 是可解析的符号根，
# `verify_evidence()` 会在干跑时把它展开并**逐条核对原文是真的在那一行**。
# =============================================================================

def _ev(rel: str, line: int, text: str) -> str:
    return f'R1: $FOAM_TUTORIALS/{rel}:{line} "{text}"'


EV_ENDTIME_10 = _ev(f"{CAVITY}/system/controlDict", 25, "endTime         10;")
EV_DELTAT_CAVITY = _ev(f"{CAVITY}/system/controlDict", 27, "deltaT          0.005;")
EV_WRITEINT_100 = _ev(f"{CAVITY}/system/controlDict", 31, "writeInterval   100;")
EV_CONVERT = _ev(f"{CAVITY}/system/blockMeshDict", 16, "convertToMeters 0.1;")
EV_VERTEX_ORIGIN = _ev(f"{CAVITY}/system/blockMeshDict", 20, "(0 0 0)")
EV_BLOCKS_20 = _ev(
    f"{CAVITY}/system/blockMeshDict", 32,
    "hex (0 1 2 3 4 5 6 7) (20 20 1) simpleGrading (1 1 1)",
)
EV_U_TOP_1 = _ev(f"{CAVITY}/0/U", 25, "value           uniform (1 0 0);")
EV_NU_1E5 = _ev(f"{CAVITY}/constant/physicalProperties", 19, "nu              1e-05 [m^2/s];")
EV_MODEL_KEPS = _ev(f"{PITZ}/constant/momentumTransport", 21, "model           kEpsilon;")
# pitzDaily 的 system/ 里**没有** blockMeshDict（实测 ls 只有 controlDict/functions/fvSchemes/fvSolution），
# 它的 Allrun 用共享字典建网格。run_case.sh 只在 system/blockMeshDict 存在时才会 blockMesh，
# 否则退 23「无可用网格」→ 一个网格都建不出来的 case 谈不上换模型。
EV_PITZ_BLOCKMESH = _ev(f"{PITZ}/Allrun", 7,
                        "runApplication blockMesh -dict $FOAM_TUTORIALS/resources/blockMesh/pitzDaily")
# kOmegaSST 需要 wallDist（pitzDaily 的 fvSchemes 里没有它 —— 它跑 kEpsilon，用不上）。
# 同几何的 pitzDailySteady 有这一段，照抄其内容（`foamDictionary -entry wallDist -set '{...}'`
# 能直接建出子字典，实测 rc=0；这是唯一一处「加块」用 set 而不是 replace_text 的地方）。
EV_WALLDIST = _ev(f"{PITZ_STEADY}/system/fvSchemes", 54, "wallDist") + " ; " + _ev(
    f"{PITZ_STEADY}/system/fvSchemes", 56, "method meshWave;")
# pitzDaily 的 divSchemes 里只有 k / epsilon / R / nuTilda 的对流格式，**没有 div(phi,omega)**
# —— 它跑 kEpsilon。换到 kOmegaSST 后求解器在第一步就要求它
# （实测 FATAL：`Cannot find scheme for div(phi,omega)`）。取值照抄同几何的 pitzDailySteady。
EV_DIV_OMEGA = _ev(f"{PITZ_STEADY}/system/fvSchemes", 33, "div(phi,omega)  bounded Gauss limitedLinear 1;")
EV_DIV_EPS_LINE = _ev(f"{PITZ}/system/fvSchemes", 33, "div(phi,epsilon)    Gauss upwind;")
# pitzDaily 的 fvSolution 里求解组只写了 U|k|epsilon（它跑 kEpsilon，`grep -n omega` 零命中）。
# 换到 kOmegaSST 后求解器要求 omegaFinal（实测 FATAL：`keyword omegaFinal is undefined …`），
# 所以两组 solver 的键都要带上 omega —— 这是「换模型」必须一起做的配置改动，不是放宽判据。
# 注意：源行本身带引号（`    "(U|k|epsilon)"`）。证据里只写引号**内**的文本，
# 否则格式变成 `""(U|k|epsilon)""`，校验正则会匹配到一段空引文而**静默通过**
# （2026-10-29 实测踩过：这就是「不可校验被当成校验通过」的典型形态）。
EV_SOLVER_GROUP = _ev(f"{PITZ}/system/fvSolution", 35, "(U|k|epsilon)")
EV_SOLVER_GROUP_FINAL = _ev(f"{PITZ}/system/fvSolution", 43, "(U|k|epsilon)Final")
EV_OMEGA_PITZ_STEADY = _ev(f"{PITZ_STEADY}/0/omega", 19, "internalField   uniform 440.15;")
EV_SIMPLE_BLOCK = _ev(f"{PITZ_STEADY}/system/fvSolution", 44, "SIMPLE")
EV_DDT_STEADY = _ev(f"{PITZ_STEADY}/system/fvSchemes", 19, "default         steadyState;")
EV_DDT_EULER = _ev(f"{PITZ}/system/fvSchemes", 19, "default         Euler;")
EV_PIMPLE_BLOCK = _ev(f"{PITZ}/system/fvSolution", 52, "nNonOrthogonalCorrectors 0;")
EV_PIMPLE_CORRECTORS = _ev(f"{PITZ}/system/fvSolution", 53, "nCorrectors         2;")
EV_PITZ_ENDTIME = _ev(f"{PITZ}/system/controlDict", 25, "endTime         0.3;")
EV_PITZ_DELTAT = _ev(f"{PITZ}/system/controlDict", 27, "deltaT          0.0001;")
EV_PITZ_ADJUST = _ev(f"{PITZ}/system/controlDict", 47, "adjustTimeStep  yes;")
EV_PITZ_MAXCO = _ev(f"{PITZ}/system/controlDict", 49, "maxCo           5;")
EV_MODEL_LM = _ev(f"{T3A}/constant/momentumTransport", 21, "model           kOmegaSSTLM;")
EV_T3A_OMEGA = _ev(f"{T3A}/0/omega", 19, "internalField   uniform 264.63;")
EV_CYL_ARC = _ev(
    "incompressibleFluid/cylinder/system/blockMeshDict", 121, "arc 3  7  $arcZ"
)

#: pitzDailySteady 里 SIMPLE 块的**逐字原文**（`sed -n '44,55p'` 实测，无行尾空格）
_SIMPLE_BLOCK = (
    "SIMPLE\n"
    "{\n"
    "    nNonOrthogonalCorrectors 0;\n"
    "    consistent      yes;\n"
    "\n"
    "    residualControl\n"
    "    {\n"
    "        p               1e-2;\n"
    "        U               1e-3;\n"
    '        "(k|epsilon|omega|f|v2)" 1e-3;\n'
    "    }\n"
    "}"
)
#: 换成 pitzDaily（同为 incompressibleFluid、瞬态 PIMPLE）的 PIMPLE 块原文
_PIMPLE_BLOCK = (
    "PIMPLE\n"
    "{\n"
    "    nNonOrthogonalCorrectors 0;\n"
    "    nCorrectors         2;\n"
    "}"
)

#: cavity 的 vertices：z 向两片，各 4 点，x 从 0..1（convertToMeters 0.1 → 真实 0.1 m）
_VERTICES_1 = (
    "    (0 0 0)\n"
    "    (1 0 0)\n"
    "    (1 1 0)\n"
    "    (0 1 0)\n"
    "    (0 0 0.1)\n"
    "    (1 0 0.1)\n"
    "    (1 1 0.1)\n"
    "    (0 1 0.1)"
)
#: 2:1 —— x 方向翻倍到 2（真实 0.2 m × 0.1 m × 0.01 m，比值 2.0 无量纲）
_VERTICES_2TO1 = (
    "    (0 0 0)\n"
    "    (2 0 0)\n"
    "    (2 1 0)\n"
    "    (0 1 0)\n"
    "    (0 0 0.1)\n"
    "    (2 0 0.1)\n"
    "    (2 1 0.1)\n"
    "    (0 1 0.1)"
)

_TOP_1 = "uniform (1 0 0)"
_BLOCKS_ANCHOR = "(0 1 2 3 4 5 6 7) (20 20 1)"


def _set(file: str, entry: str, new_value: str, evidence: str) -> Edit:
    return Edit(kind="set", file=file, entry=entry, new_value=new_value, evidence=evidence)


def _copy(file: str, source: str, evidence: str) -> Edit:
    return Edit(kind="copy_file", file=file, source=source, evidence=evidence)


def _replace(file: str, old: str, new: str, evidence: str) -> Edit:
    return Edit(kind="replace_text", file=file, entry=old, new_value=new, evidence=evidence)


def _top_speed_edits(speed: str) -> tuple[Edit, ...]:
    """顶盖速度改动。1 m/s 是 tutorial 基线，**不改就是对的**（零编辑，不是漏改）。"""
    if speed == "1":
        return ()
    return (_replace("0/U", _TOP_1, f"uniform ({speed} 0 0)", EV_U_TOP_1),)


# =============================================================================
# 12 个任务的改动计划
# =============================================================================

_PLANS: dict[str, tuple[Example, ...]] = {
    # ---- T01 建 D1：派生方腔 + endTime=5 -------------------------------------
    "T01": (
        Example(
            case_id="T01",
            edits=(
                _set("system/controlDict", "endTime", "5", EV_ENDTIME_10),
            ),
        ),
    ),
    # ---- T02 建 D2：pitzDaily kEpsilon → kOmegaSST（补 omega 场） -------------
    "T02": (
        Example(
            case_id="T02",
            edits=(
                _replace(
                    "constant/momentumTransport",
                    "model           kEpsilon;",
                    "model           kOmegaSST;",
                    EV_MODEL_KEPS,
                ),
                # pitzDaily 的 0/ 实测只有 U epsilon k nuTilda nut p（**没有 omega**），
                # kOmegaSST 必需 omega。pitzDailySteady 与它同几何、同 patch 名
                # （inlet/outlet/upperWall/lowerWall/frontAndBack，两边 0/U 实测一致），
                # 所以整文件照抄，不手写边界条件。
                _copy("0/omega", f"{PITZ_STEADY}/0/omega", EV_OMEGA_PITZ_STEADY),
                # 网格字典：照 pitzDaily 的 Allrun 用同一份共享字典（同几何、同 patch 名），
                # 落到 system/blockMeshDict 才符合 run_case.sh 的「有 blockMeshDict 才建网格」契约。
                _copy("system/blockMeshDict", "resources/blockMesh/pitzDaily", EV_PITZ_BLOCKMESH),
                # div(phi,omega) 只能是「在 divSchemes 里插一行」：`-set` 会把整个 divSchemes
                # 换掉（手抄 6 条格式 = 制造 typo 的机会）。以 div(phi,epsilon) 那行为唯一锚点插入。
                #
                # **顺序有讲究**：必须先 replace_text、后 set。foamDictionary -set 会把
                # **整个文件**重新序列化（空白全部规整化，实测 `div(phi,epsilon)    Gauss`
                # 变成 `div(phi,epsilon) Gauss`），之后任何按原文空白写的锚点都会失配。
                _replace(
                    "system/fvSchemes",
                    "    div(phi,epsilon)    Gauss upwind;",
                    "    div(phi,epsilon)    Gauss upwind;\n"
                    "    div(phi,omega)  bounded Gauss limitedLinear 1;",
                    f"{EV_DIV_EPS_LINE} ; {EV_DIV_OMEGA}",
                ),
                # 求解组补 omega（两组都要：普通组 + Final 组）
                _replace(
                    "system/fvSolution",
                    '"(U|k|epsilon)"',
                    '"(U|k|epsilon|omega)"',
                    EV_SOLVER_GROUP,
                ),
                _replace(
                    "system/fvSolution",
                    '"(U|k|epsilon)Final"',
                    '"(U|k|epsilon|omega)Final"',
                    EV_SOLVER_GROUP_FINAL,
                ),
                # 换到 kOmegaSST 后求解器在第一步就要求 fvSchemes 里有 wallDist
                # （实测 FATAL：`keyword wallDist is undefined in dictionary …/fvSchemes`）。
                _set("system/fvSchemes", "wallDist", "{ method meshWave; }", EV_WALLDIST),
            ),
        ),
    ),
    # ---- T03 建 D3：方腔 2:1 + 顶盖 2 m/s + 重建网格 -------------------------
    "T03": (
        Example(
            case_id="T03",
            edits=(
                _replace("system/blockMeshDict", _VERTICES_1, _VERTICES_2TO1, EV_VERTEX_ORIGIN),
                _replace("0/U", _TOP_1, "uniform (2 0 0)", EV_U_TOP_1),
            ),
            rebuild_mesh=True,
        ),
    ),
    # ---- T04 建 D4：T3A kOmegaSSTLM → kOmegaSST ------------------------------
    "T04": (
        Example(
            case_id="T04",
            edits=(
                _replace(
                    "constant/momentumTransport",
                    "model           kOmegaSSTLM;",
                    "model           kOmegaSST;",
                    EV_MODEL_LM,
                ),
                # 0/omega 已存在（`ls T3A/0` = ReThetat U gammaInt k nut omega p），
                # 所以这一条**不改任何东西**，只作为「不需要补场」的取证：
                # 证据在 EV_T3A_OMEGA；T04.yaml 的 note 也明说不能用「omega 是否存在」当判据。
            ),
        ),
    ),
    # ---- T05 改 D1：writeInterval 100 → 50 -----------------------------------
    "T05": (
        Example(
            case_id="T05",
            edits=(
                _set("system/controlDict", "writeInterval", "50", EV_WRITEINT_100),
            ),
        ),
    ),
    # ---- T06 改 D2：稳态 SIMPLE → 瞬态 PIMPLE ---------------------------------
    "T06": (
        Example(
            case_id="T06",
            edits=(
                # ① 换求解器字典。**整文件照抄同几何的瞬态教程 pitzDaily**，不是「只把 SIMPLE
                #    改名为 PIMPLE」：瞬态 PIMPLE 需要 `pFinal` 与 `(U|k|epsilon)Final` 两组
                #    solver，只换块名会让求解器在第一步行就 FATAL
                #    （`keyword UFinal is undefined in dictionary …/fvSolution/solvers`，
                #     2026-10-29 实测：那条路的 run 停在 G3）。结构改动，文本替换表达不了，
                #    所以用 copy_file —— 与 fvSolution 一起拷进来的只有 solver 配置，没有物理改动。
                _copy("system/fvSolution", f"{PITZ}/system/fvSolution",
                      f'{EV_SIMPLE_BLOCK} ; {EV_PIMPLE_BLOCK} ; {EV_PIMPLE_CORRECTORS}'),
                # ② 稳态 ddt → Euler（只换 PIMPLE 不换 ddt 是自相矛盾的设置，T06.yaml 三条一起判）
                _replace(
                    "system/fvSchemes",
                    "default         steadyState;",
                    "default         Euler;",
                    f"{EV_DDT_STEADY} → {EV_DDT_EULER}",
                ),
                # ③ 真瞬态需要能走的时间步：pitzDailySteady 的 deltaT=1 / endTime=2000 是稳态
                #    pseudo-time，直接配 Euler 会得到 Co 上万的离谱步长。照同几何的瞬态教程
                #    pitzDaily 取 deltaT=1e-4、endTime=0.3、adjustTimeStep+maxCo。
                _set("system/controlDict", "deltaT", "0.0001", EV_PITZ_DELTAT),
                _set("system/controlDict", "endTime", "0.3", EV_PITZ_ENDTIME),
                _set("system/controlDict", "adjustTimeStep", "yes", EV_PITZ_ADJUST),
                _set("system/controlDict", "maxCo", "5", EV_PITZ_MAXCO),
            ),
        ),
    ),
    # ---- T07 改 D3：顶盖 1 → 0.5 m/s ----------------------------------------
    "T07": (
        Example(
            case_id="T07",
            edits=(
                _replace("0/U", _TOP_1, "uniform (0.5 0 0)", EV_U_TOP_1),
            ),
        ),
    ),
    # ---- T08 改 D4：网格每方向翻倍 + 重建网格 --------------------------------
    "T08": (
        Example(
            case_id="T08",
            edits=(
                _replace(
                    "system/blockMeshDict",
                    _BLOCKS_ANCHOR,
                    "(0 1 2 3 4 5 6 7) (40 40 1)",
                    EV_BLOCKS_20,
                ),
            ),
            rebuild_mesh=True,
        ),
    ),
    # ---- T09 批 D1：顶盖 0.5/1/2 三例 ---------------------------------------
    "T09": tuple(
        Example(case_id=f"T09_u{u}", edits=_top_speed_edits(u))
        for u in ("0.5", "1", "2")
    ),
    # ---- T10 批 D2：顶盖速度 × nu = 9 例 ------------------------------------
    "T10": tuple(
        Example(
            case_id=f"T10_u{u}_nu{nu}",
            edits=(
                *_top_speed_edits(u),
                # nu 是**顶层标量带量纲**：foamDictionary -value 输出 `2e-05 [ m^2 / s]`，
                # 回读校验会先剥掉方括号块再比数值。
                *(() if nu == "1e-05" else (
                    _set("constant/physicalProperties", "nu", nu, EV_NU_1E5),
                )),
            ),
        )
        for u in ("0.5", "1", "2")
        for nu in ("1e-05", "2e-05", "5e-05")
    ),
    # ---- T11 批 D3：9 例 + 汇总 CSV（**不改 nu**，见模块 docstring 末段） -----
    "T11": tuple(
        Example(
            case_id=f"T11_u{u}_dt{dt}",
            edits=(
                *_top_speed_edits(u),
                *(() if dt == "0.005" else (
                    _set("system/controlDict", "deltaT", dt, EV_DELTAT_CAVITY),
                )),
            ),
        )
        for u in ("0.5", "1", "2")
        for dt in ("0.0025", "0.005", "0.01")
    ),
    # ---- T12 负对照：不派生、不写 case，给指向 R5 的理由 ---------------------
    "T12": (
        Example(case_id="T12", edits=()),
    ),
}

PLANS: dict[str, tuple[Example, ...]] = _PLANS

#: 多例任务里每一例**自己**取到的参数值（`case_id → {参数: 值}`）。
#:
#: 用途只有一个：把冻结的 `expect_values` 按 yaml 的 `expect_values_note`
#: （"断言逐例施加，此处列 2 m/s 那例" / "9 例逐个施加"）实例化到该例自己的取值上。
#: 单例任务不在此表内 ⇒ 断言**逐字**使用冻结值，没有任何替换。
EXAMPLE_VALUES: dict[str, dict[str, str]] = {}
for _u in ("0.5", "1", "2"):
    EXAMPLE_VALUES[f"T09_u{_u}"] = {"U": _u}
for _u in ("0.5", "1", "2"):
    for _nu in ("1e-05", "2e-05", "5e-05"):
        EXAMPLE_VALUES[f"T10_u{_u}_nu{_nu}"] = {"U": _u, "nu": _nu}
for _u in ("0.5", "1", "2"):
    for _dt in ("0.0025", "0.005", "0.01"):
        EXAMPLE_VALUES[f"T11_u{_u}_dt{_dt}"] = {"U": _u, "deltaT": _dt}
del _u, _nu, _dt

#: T12 的拒绝理由。必须含 `bench/judge.py:43` 的 R5_MARKERS 之一（曲面 / 边界层加密 /
#: STL / snappyHexMesh / CAD / 多体装配），否则 judge 判 `no_artifact` 而不是 `declined`。
REFUSAL_TEXT = (
    "拒绝执行：该需求要曲面几何（圆柱绕流）与边界层加密，超出 R5 允许的前处理边界"
    "（只允许 blockMesh 或导入外部网格）。按 R5 停下询问用户：不生成 STL、不调用 "
    "snappyHexMesh、不自造 CAD。未派生任何 case。"
)


#: 跑之前就已知、必须随结果一起落盘的「冻结件问题」注记（进 results.csv 的 note，不进结论句）。
#: T11 是预注册 §10 逐字登记的：断言 nu=2e-05，但 prompt 从未要求改 nu、allowed_files 也不含
#: constant/physicalProperties → 改则 G5 越界、不改则断言 mismatch，两条路都是 fail。
TASK_NOTES = {
    "T11": "已知冻结件矛盾：prompt 未要求改 nu、allowed_files 不含 constant/physicalProperties，"
           "故按原文只做速度扫描，断言 nu 必然 mismatch（不得为 pass 而越界改 nu）",
}


def arm_stdout_for(tid: str, *, mode: str, n_examples: int, case_id: str | None = None) -> str:
    """臂的自述文本（`arm_stdout.txt` 的内容）。

    **纯结构化摘要**（`task=T01 examples=1 mode=short`）：`bench/judge.py:45` 的
    `CLAIM_MARKERS`（"已完成"/"已跑通"/"完成，"/"成功"/"done"/"success"/"completed"）
    一旦命中，任何门失败的 run 都会被判 `overclaim` 而不是 `fail` —— 语义整体变样，
    而这件事**不会报错**。所以这里绝不写自然语言结论，只有 `key=value`。

    唯一例外是 T12：它的 `declined` 判定要靠理由文本指认 R5（`bench/judge.py:138`）。
    """
    if tid == "T12":
        return REFUSAL_TEXT + "\n"
    parts = [f"task={tid}"]
    if case_id:
        parts.append(f"example={case_id}")
    parts += [f"examples={n_examples}", f"mode={mode}"]
    return " ".join(parts) + "\n"


# =============================================================================
# 任务 yaml 解析（零第三方依赖：项目只允许标准库）
# =============================================================================

def _strip_comment(value: str) -> str:
    """去掉行尾 `  # 注释`，但**不动引号内**的 `#`（prompt 里可能有）。"""
    out = []
    quote: str | None = None
    prev = ""
    for ch in value:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
            prev = ch
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            prev = ch
            continue
        if ch == "#" and prev in (" ", "\t"):
            break
        out.append(ch)
        prev = ch
    return "".join(out).strip()


def _scalar(raw: str):
    v = _strip_comment(raw).strip()
    if not v:
        return ""
    if v.startswith("[") or v.startswith("{"):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    if v in ("true", "false"):
        return v == "true"
    return v


def load_task(tid: str) -> dict:
    """解析 `bench/tasks/<tid>.yaml` → {id, prompt, ref, allowed_files, expect, specs, note}。

    `specs` 是 `expect_values` 的逐行 JSON 解析结果，**可直接喂给
    `bench/assert_lib.evaluate(case, specs, arm_stdout)`**（它吃的是断言列表，
    不是需求四元组——两者结构无关，`references/09-architecture-and-test-plan.md:738` 记过这个混淆）。

    只支持这 12 个 yaml 实际用到的 YAML 子集：`key: value`、行内 JSON 列表/对象、
    块标量 `key: |`、以及 `key:` 下的 `- {...}` 列表。**不引入 PyYAML**。
    """
    if tid not in TASK_IDS:
        raise KeyError(f"未知任务 id: {tid!r}（合法值 {TASK_IDS}）")
    path = TASKS_DIR / f"{tid}.yaml"
    if not path.is_file():
        raise FileNotFoundError(path)

    lines = path.read_text(encoding="utf-8").splitlines()
    doc: dict = {}
    specs: list[dict] = []
    note_parts: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if raw.startswith("expect_values:"):
            i += 1
            while i < len(lines):
                cur = lines[i]
                if not cur.strip():
                    i += 1
                    continue
                if not cur.lstrip().startswith("- "):
                    break
                item = _strip_comment(cur.lstrip()[2:].strip())
                specs.append(json.loads(item))
                i += 1
            continue
        if raw.startswith("expect_values_note:"):
            i += 1
            while i < len(lines):
                cur = lines[i]
                if cur.strip() and not cur.startswith((" ", "\t")):
                    break
                if cur.strip():
                    note_parts.append(cur.strip())
                i += 1
            continue
        if ":" in raw and not raw.startswith((" ", "\t", "-")):
            key, _, rest = raw.partition(":")
            doc[key.strip()] = _scalar(rest)
            i += 1
            continue
        i += 1

    key_map = {"id": "id", "prompt": "prompt", "reference_tutorial": "ref",
               "allowed_files": "allowed_files", "expect": "expect"}
    task = {out: doc.get(src, "") for src, out in key_map.items()}
    task["id"] = task["id"] or tid
    if task["id"] != tid:
        raise ValueError(f"{path} 里的 id={task['id']!r} 与文件名 {tid} 不一致")
    task["allowed_files"] = list(task["allowed_files"] or [])
    task["specs"] = specs
    task["note"] = " ".join(note_parts).strip()
    return task


# =============================================================================
# 施加改动
# =============================================================================

_NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_DIMS = re.compile(r"\[[^\]]*\]")

#: 一条 evidence 里的单个子句：`R1: $FOAM_TUTORIALS/<rel>:<line> "<逐字原文>"`
#: 引文必须**非空**（`[^"]+`）：空引文会命中任何一行，等于没校验。
EVIDENCE_RE = re.compile(r'R1: \$FOAM_TUTORIALS/([^:\s]+):(\d+)\s+"([^"]+)"')


def _norm(text: str) -> str:
    """剥掉量纲块、压缩空白 —— 用来比较「同一个值的不同书写」（`(1 0 0)` / `( 1 0 0 )`）。"""
    return " ".join(_DIMS.sub(" ", text).split())


def _numbers(text: str) -> list[float]:
    return [float(x) for x in _NUM.findall(_DIMS.sub(" ", text))]


def values_equal(want: str, got: str) -> bool:
    """回读比较：先逐字（空白归一），失败再按数值序列比（带 1e-9 相对容差）。"""
    if _norm(want) == _norm(got):
        return True
    a, b = _numbers(want), _numbers(got)
    if not a or len(a) != len(b):
        return False
    return all(abs(x - y) <= 1e-9 * max(1.0, abs(x), abs(y)) for x, y in zip(a, b))


def _foam_dictionary() -> str:
    exe = shutil.which("foamDictionary")
    if exe is None:
        raise ApplyError(
            "PATH 里没有 foamDictionary：先 `source $WM_PROJECT_DIR/etc/bashrc`。"
            "（环境缺失是整批性问题，不该被当成某条改动失败）"
        )
    return exe


def _apply_set(case_dir: Path, ed: Edit) -> None:
    target = case_dir / ed.file
    if not target.is_file():
        raise UnsupportedEdit(f"case 里没有 {ed.file}（派生源可能不是预期的 tutorial）")
    exe = _foam_dictionary()
    # 坑 1（run_case.sh 头注释）：字典文件是**位置参数**，`-case` 只能跟在它后面。
    common = [ed.file, "-case", str(case_dir), "-entry", ed.entry]
    proc = subprocess.run([exe, *common, "-set", ed.new_value],
                          cwd=str(case_dir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise ApplyError(
            f"foamDictionary -set {ed.entry} 失败（rc={proc.returncode}）："
            f"{(proc.stderr or proc.stdout).strip()[:300]}"
        )
    back = subprocess.run([exe, *common, "-value"],
                          cwd=str(case_dir), capture_output=True, text=True)
    if back.returncode != 0:
        raise ApplyError(f"{ed.file}:{ed.entry} 回读失败（rc={back.returncode}）")
    got = back.stdout.strip()
    if not values_equal(ed.new_value, got):
        # `-set` 对不存在的 entry 会新增并退 0（坑 1）。所以「改了没生效」必须在这里拦下。
        raise ApplyError(
            f"{ed.file}:{ed.entry} 设置 {ed.new_value!r} 未生效（回读 {got!r}）"
            "——foamDictionary 静默失败"
        )


def _apply_copy(case_dir: Path, ed: Edit) -> None:
    root = os.environ.get("FOAM_TUTORIALS", "").strip()
    if not root:
        raise ApplyError("$FOAM_TUTORIALS 为空：先 `source $WM_PROJECT_DIR/etc/bashrc`")
    src = Path(root) / ed.source
    if not src.is_file():
        raise UnsupportedEdit(f"tutorial 里没有 {ed.source}（{src} 不存在）")
    dst = case_dir / ed.file
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if dst.read_bytes() != src.read_bytes():
        raise ApplyError(f"复制 {ed.source} → {ed.file} 后内容不一致")


def _apply_replace(case_dir: Path, ed: Edit) -> None:
    target = case_dir / ed.file
    if not target.is_file():
        raise UnsupportedEdit(f"case 里没有 {ed.file}")
    text = target.read_text(encoding="utf-8")
    hits = text.count(ed.entry)
    if hits == 0:
        raise UnsupportedEdit(
            f"{ed.file} 里找不到待替换原文（tutorial 可能变了）：{ed.entry!r}"
        )
    if hits > 1:
        # 锚点不唯一 = 替换对象二义。宁可失败，不要「替换了第一个」这种静默分叉。
        raise UnsupportedEdit(f"{ed.file} 里待替换原文出现 {hits} 次，锚点不唯一")
    if ed.new_value == ed.entry:
        raise ApplyError(f"{ed.file} 的替换前后相同（空操作不算改动）")
    expected = text.replace(ed.entry, ed.new_value, 1)
    target.write_text(expected, encoding="utf-8")
    back = target.read_text(encoding="utf-8")
    # 回读判据：**逐字节等于预期结果**。
    # 不要用「旧文本必须消失」当判据：`replace` 的常见形态就是「旧行 + 新行」（插入一行），
    # 那时新文本包含旧文本，这条判据会把正确的改动判成失败（2026-10-29 实测踩过：
    # T02 的 div(phi,omega) 插入被自己判红，后续 wallDist 一步没跑）。
    if back != expected:
        raise ApplyError(f"{ed.file} 替换后回读与预期不一致（写盘失败？）")


def _drop_polymesh(case_dir: Path) -> None:
    """删 `constant/polyMesh` 让 `run_case.sh` 重新 blockMesh。

    为什么必须删：`scripts/run_case.sh` 的步骤②只在 `constant/polyMesh` **不存在**时才
    blockMesh。改了 `blocks`/`vertices` 却不删旧网格，求解会继续用旧网格，而 G2 读的是
    上次的日志照样过 —— 项目 N7 第 17 条记录的真实假 pass 事故。
    """
    mesh = case_dir / "constant" / "polyMesh"
    if not mesh.exists():
        return                     # 派生的 tutorial 本来就没有 polyMesh：空操作是正常情况
    if not (case_dir / "system" / "blockMeshDict").is_file():
        raise UnsupportedEdit(
            "rebuild_mesh=True 但 case 里没有 system/blockMeshDict："
            "删了旧网格就再也建不出来了（R5：不能改用 snappyHexMesh 之类）"
        )
    shutil.rmtree(mesh)


def apply(case_dir: Path, ex: Example) -> None:
    """把 `ex.edits` 施加到**已派生**的 case 树上；做不到就抛 `UnsupportedEdit`。

    失败一律抛出，绝不静默跳过：跳过一条改动会让「改了没改」不可判定，
    而 G5 只能判「动了哪些文件」，判不出「该动没动」。
    """
    case_dir = Path(case_dir)
    # 先校验词表：未知 kind 是「表达能力不足」，与「树不对」是不同性质的失败，
    # 且不该被一个刚好缺 controlDict 的目录掩盖掉。
    for ed in ex.edits:
        if ed.kind not in ("set", "copy_file", "replace_text"):
            raise UnsupportedEdit(
                f"未知改动 kind={ed.kind!r}（只支持 set / copy_file / replace_text）"
            )
    if not (case_dir / "system" / "controlDict").is_file():
        raise ApplyError(f"不是 case 目录（缺 system/controlDict）: {case_dir}")
    for ed in ex.edits:
        if not ed.evidence.strip():
            raise ApplyError(f"{ex.case_id} 的 {ed.file} 改动缺 R1 证据（R1：无证据不许写改动）")
        if ed.kind == "set":
            _apply_set(case_dir, ed)
        elif ed.kind == "copy_file":
            _apply_copy(case_dir, ed)
        elif ed.kind == "replace_text":
            _apply_replace(case_dir, ed)
        else:
            raise UnsupportedEdit(f"未知改动 kind={ed.kind!r}（只支持 set / copy_file / replace_text）")
    if ex.rebuild_mesh:
        _drop_polymesh(case_dir)


# =============================================================================
# 证据自检（干跑时跑，把「r1 证据是真的」从口头承诺变成一次可复现的检查）
# =============================================================================

def verify_evidence(tutorials: str | Path | None = None) -> list[str]:
    """逐条核对证据：`<path>:<line>` 里那一行是否**逐字**等于引文。

    返回问题清单（空 = 全部核对通过）。tutorials 根不存在/为空 → 返回一条问题，
    **不返回空表**（不可校验 ≠ 没问题）。
    """
    root = Path(tutorials) if tutorials else Path(os.environ.get("FOAM_TUTORIALS", "") or "/nonexistent")
    problems: list[str] = []
    if not root.is_dir():
        return [f"无法校验证据：tutorials 根不存在（{root}）；先 source $WM_PROJECT_DIR/etc/bashrc"]

    for tid, examples in PLANS.items():
        for ex in examples:
            for ed in ex.edits:
                # 一条 evidence 可以由多个 `R1: …:N "原文"` 子句组成（用 " ; " 串起来），
                # 例如 T06 换块时要同时引「被换掉的块」与「照抄的块」两处原文。
                clauses = EVIDENCE_RE.findall(ed.evidence)
                if not clauses:
                    problems.append(f"{tid}: 证据格式不合规：{ed.evidence!r}")
                    continue
                for rel, lineno, want in clauses:
                    f = root / rel
                    if not f.is_file():
                        problems.append(f"{tid}: 证据指向的文件不存在：{rel}")
                        continue
                    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    lineno = int(lineno)
                    if lineno < 1 or lineno > len(lines):
                        problems.append(f"{tid}: {rel}:{lineno} 超出文件行数 {len(lines)}")
                        continue
                    actual = lines[lineno - 1].strip()
                    if not want.strip():
                        problems.append(f"{tid}: {rel}:{lineno} 的引文为空（空引文会命中任何一行）")
                        continue
                    if want.strip() == actual or want.strip() in actual:
                        continue
                    problems.append(
                        f"{tid}: {rel}:{lineno} 的原文是 {actual!r}，证据里写的是 {want!r}"
                    )
    return problems
