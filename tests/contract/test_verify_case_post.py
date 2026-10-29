"""模块 E-full（`scripts/verify_case.sh --stage post`）的 L2 契约测试，9 项。

规格来源（逐字，勿改写）：
  - `references/09-architecture-and-test-plan.md:201-234`（E 两入口 / D7 日志格式 / D6 退出码 /
    G2 与 G2b 判据 / D18「G2 不得看 checkMesh 退出码」/ D19「soft 分支不可达」）
  - `bench/preregistration.md:81-98`（G1–G5 + G2b 判据原文）
  - `bench/judge.py:47-84`（judge 怎么读 `RC=` 与 `G2B=`——这是唯一接口，格式错了 run 全变 malformed）

契约摘要（本文件只测 `--stage post`）：
  CLI    `verify_case.sh --stage post --case <dir> [--log <dir>]`，`--log` 缺省 = `--case`
  职责   **只解析日志，不跑求解**；日志由模块 D（`scripts/run_case.sh`）产生
  门     G2 = `log.checkMesh` 含 `Mesh OK.`；G3 = `log.shortRun` 非空、无 `FOAM FATAL`、含 `End`；
         G4 = 末时刻目录存在 + 至少一个场文件 `foamDictionary … -entry internalField -value`
         非空 + 该目录所有文件 `grep -rilE 'nan|inf'` 为空
  诊断   G2b = 数 `log.checkMesh` 里以 `***` 开头的行 → none | soft:N | hard:N | unknown
         **不是门**，不进 RC、不进退出码、不参与 judge 的 status
  退出码 0 全过 / 2 G2 / 3 G3 / 4 G4（只报第一个失败的门），64 用法错误
  日志   三个 `log.gN` **无论哪个门不过都要写**（judge 需要全部三个才能归约）

三个已实测的坑（改实现前先读，别"修"回去）：
  坑 1  `checkMesh` 的**进程退出码恒为 0**，即使打印 `Failed 1 mesh checks.` 且不打印 `Mesh OK.`
        （`$FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:180` 的 `return nFailedChecks == 0`
        是函数对象 `execute()` 的返回值，可执行文件没把它变成 `exit()`）。所以 G2 只能 grep
        `Mesh OK.`——这条由 E-f1b 单独守。
  坑 2  `foamDictionary` 的字典文件是**位置参数**：`foamDictionary <case>/0.01/U -entry internalField -value`。
        写成 `-case <dir> -entry …` 只打印 Usage 且**退出码仍是 0**（静默失败）。
  坑 3  `g2b=soft:N` 在 v13 **观测不到**（208 个 tutorial 全扫，`Mesh OK.` 与 `***` 共存 0 例；
        那 4 项被源码刻意豁免的检查不打印 `***`）。E-f4b 因此用**合成日志**，docstring 已写明。

设计约定：
- 全部 case 在 `tmp_path` 下从 `$FOAM_TUTORIALS` 派生，**绝不写 `bench/`**（R12：`bench/runs/` 必须 0 文件）。
- 退化网格的造法只有一种（已实测）：把 `system/blockMeshDict` 里的 `(20 20 1)` 换成 `(2000 1 1)`
  → `***High aspect ratio cells found` + `Failed 1 mesh checks.`、无 `Mesh OK.`，而 `checkMesh` 退出码 0。
- 每个"反例"测试都尽量带一个**控制组**：同一条 case 在注入前必须通过，注入后才红——
  否则"红"可能来自别的腿（例如 G4 的读值与 nan 检查两条腿）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# 环境引导（bashrc → env）、cavity 派生源与五个根统一由 `tests/contract/conftest.py`
# 提供：本文件只声明 `foam_env` / `cavity_src` / `roots` 夹具，不再自己 source 一遍。

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "verify_case.sh"
RUN_CASE = PROJECT_ROOT / "scripts" / "run_case.sh"


# 退化网格：把 cavity 的 20x20x1 块压成 2000x1x1（aspect ratio 2000，实测 checkMesh 判 Failed 1）
DEGENERATE_FROM = "(20 20 1)"
DEGENERATE_TO = "(2000 1 1)"

# 让 foamRun 立刻 FATAL 的最小改法：把 p 的 solver 改成不存在的名字（实测 0.4 s 内 FATAL）
FVSOLUTION_SOLVER = "solver          GAMG;"
FVSOLUTION_BROKEN = "solver          noSuchSolver999;"

NAN_RE = re.compile(r"^\((-?[0-9][0-9eE+.\-]*) ", re.M)
STAR_RE = re.compile(r"^[ \t]*\*\*\*", re.M)


# ---------------------------------------------------------------- 基础设施


def _copy_cavity(tmp_path: Path, cavity_src: Path, name: str) -> Path:
    dest = tmp_path / name
    subprocess.run(["cp", "-a", f"{cavity_src}/.", str(dest)], check=True)
    return dest


def _block_mesh(case: Path, env: dict) -> int:
    p = subprocess.run(["blockMesh"], cwd=case, env=env, capture_output=True, text=True)
    (case / "log.blockMesh").write_text(p.stdout + p.stderr, encoding="utf-8")
    return p.returncode


def _check_mesh(case: Path, env: dict) -> int:
    """跑真 checkMesh，日志落到 <case>/log.checkMesh，**返回进程退出码**（坑 1 要观察它）。"""
    p = subprocess.run(["checkMesh"], cwd=case, env=env, capture_output=True, text=True)
    (case / "log.checkMesh").write_text(p.stdout + p.stderr, encoding="utf-8")
    return p.returncode


def make_mesh_case(
    tmp_path: Path, cavity_src: Path, env: dict, name: str = "case", *, degenerate: bool = False
) -> Path:
    """派生 cavity → 可选退化 → blockMesh + checkMesh（日志落 case 目录）。"""
    case = _copy_cavity(tmp_path, cavity_src, name)
    if degenerate:
        d = case / "system" / "blockMeshDict"
        text = d.read_text(encoding="utf-8")
        assert DEGENERATE_FROM in text, f"cavity 的 blockMeshDict 里找不到 {DEGENERATE_FROM}，造退化网格的前提不成立"
        d.write_text(text.replace(DEGENERATE_FROM, DEGENERATE_TO), encoding="utf-8")

    assert _block_mesh(case, env) == 0, f"blockMesh 失败，见 {case / 'log.blockMesh'}"
    _check_mesh(case, env)
    return case


def run_short(case: Path, env: dict, timeout: int = 120) -> subprocess.CompletedProcess:
    """调模块 D 跑短跑（它自己会重写 log.checkMesh 并产 log.shortRun + 末时刻目录）。"""
    return subprocess.run(
        ["bash", str(RUN_CASE), "--case", str(case), "--mode", "short", "--timeout", str(timeout)],
        env=env,
        capture_output=True,
        text=True,
    )


def run_post(case: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--stage", "post", "--case", str(case), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def log_lines(logdir: Path, gate: str) -> list[str]:
    log = logdir / f"log.{gate}"
    assert log.is_file(), f"{log} 不存在：缺失的 log 在 judge 眼里是 undeterminable，不是 pass"
    return log.read_text(encoding="utf-8").splitlines()


def rc_line(logdir: Path, gate: str) -> str:
    """读 log.<gate> 第 1 行 `RC=` 后面的值。"""
    first = log_lines(logdir, gate)[0]
    assert first.startswith("RC="), f"log.{gate} 第 1 行不是 RC=，实测 {first!r}（D7 格式）"
    return first[3:].strip()


def g2b_line(logdir: Path) -> str:
    """读 log.g2 第 2 行 `G2B=` 后面的值；格式必须与 bench/judge.py:49 的正则相容。"""
    lines = log_lines(logdir, "g2")
    assert len(lines) >= 2, f"log.g2 只有 1 行：第 2 行必须是 G2B=（judge 读不到就记 unknown）"
    assert lines[1].startswith("G2B="), f"log.g2 第 2 行不是 G2B=，实测 {lines[1]!r}"
    value = lines[1][4:].strip()
    assert re.fullmatch(r"none|soft:\d+|hard:\d+|unknown", value), (
        f"G2B 取值非法: {value!r}（judge.py:49 的正则只认 none|soft:N|hard:N|unknown）"
    )
    return value


def checkmesh_star_count(case_or_logdir: Path) -> int:
    """独立重算 `***` 行数（与脚本无关的第二实现，用来交叉验证 G2B 的 N）。"""
    text = (case_or_logdir / "log.checkMesh").read_text(encoding="utf-8", errors="replace")
    return len(STAR_RE.findall(text))


def last_time_dir(case: Path) -> Path:
    """末时刻目录：名字能解析成 float 的子目录里最大的那个（排除 0）。"""
    best: tuple[float, str] | None = None
    for p in case.iterdir():
        if not p.is_dir():
            continue
        try:
            v = float(p.name)
        except ValueError:
            continue
        if v == 0.0:
            continue
        if best is None or v > best[0]:
            best = (v, p.name)
    assert best is not None, f"{case} 下没有末时刻目录（0 以外的数字目录）"
    return case / best[1]


def fd_internal_field(env: dict, field: Path) -> str:
    """坑 2：字典文件是位置参数，不能用 -case。返回 internalField -value 的第一行。"""
    p = subprocess.run(
        ["foamDictionary", str(field), "-entry", "internalField", "-value"],
        env=env,
        capture_output=True,
        text=True,
    )
    line = (p.stdout.splitlines() or [""])[0]
    return line


# ---------------------------------------------------------------- E-f1 G2


def test_ef1_g2_pass_and_fail(tmp_path, cavity_src, foam_env):
    """E-f1：正常网格 → 退出 0、log.g2 RC=0；退化网格 → 退出 2、log.g2 RC=1。

    正常例走完 D 的 short 全流程（G3/G4 才可能过），否则 "G2 过" 会被 G3 缺失掩盖成 3。
    """
    good = make_mesh_case(tmp_path, cavity_src, foam_env, "good")
    assert "Mesh OK." in (good / "log.checkMesh").read_text(encoding="utf-8", errors="replace")

    short = run_short(good, foam_env)
    assert short.returncode == 0, f"D 的短跑没跑通，G3/G4 无法成立：{short.stdout}{short.stderr}"

    p = run_post(good, foam_env)
    assert p.returncode == 0, f"三门都应通过，实测 {p.returncode}\n{p.stdout}\n{p.stderr}"
    assert rc_line(good, "g2") == "0"

    bad = make_mesh_case(tmp_path, cavity_src, foam_env, "bad", degenerate=True)
    p2 = run_post(bad, foam_env)
    assert p2.returncode == 2, f"网格门不过必须退 2，实测 {p2.returncode}\n{p2.stdout}\n{p2.stderr}"
    assert rc_line(bad, "g2") == "1", "log.g2 必须 RC=1"
    assert "Mesh OK." in (bad / "log.g2").read_text(encoding="utf-8"), (
        "失败串必须点名缺的证据（Mesh OK.），否则人看不出为什么红"
    )


def test_ef1b_g2_ignores_checkmesh_exit_code(tmp_path, cavity_src, foam_env):
    """E-f1b（**E-full 最重要的一条**，D18）：G2 绝不能看 `checkMesh` 的退出码。

    两件事都要证：
      ① 同一条退化网格上，`checkMesh` 的**真实进程退出码是 0**（看退出码就会放行）；
      ② 手造一份只有 `Failed …` 行、没有 `Mesh OK.` 的 log.checkMesh → G2 必须 RC=1、退 2。
    把 G2 改成 `if checkMesh 退出码 == 0 then pass` 时，这一条会红（②会被放行成 RC=0）。
    """
    bad = make_mesh_case(tmp_path, cavity_src, foam_env, "bad", degenerate=True)
    real_rc = _check_mesh(bad, foam_env)
    real_log = (bad / "log.checkMesh").read_text(encoding="utf-8", errors="replace")

    assert real_rc == 0, (
        f"前提不成立：这条退化网格上 checkMesh 的退出码实测 {real_rc}，不是 0。"
        "D18 的证据链（退出码 0 但判 Failed）需要重测"
    )
    assert "Mesh OK." not in real_log, "前提不成立：退化网格不该打印 Mesh OK."
    assert "Failed 1 mesh checks." in real_log, f"前提不成立：真实日志里没有 Failed 1 mesh checks.\n{real_log[-800:]}"

    # 手造日志：只有失败串，没有 Mesh OK.。G2 只看内容，不看产生它的进程退出码。
    logdir = tmp_path / "handmade_log"
    logdir.mkdir()
    (logdir / "log.checkMesh").write_text(
        "***High aspect ratio cells found, Max aspect ratio: 2000, number of cells 2000\n"
        "Failed 1 mesh checks.\n",
        encoding="utf-8",
    )

    p = run_post(bad, foam_env, "--log", str(logdir))
    assert p.returncode == 2, (
        f"日志里没有 `Mesh OK.` 必须退 2；实测 {p.returncode}"
        f"（若退 0，说明 G2 在看 checkMesh 退出码——而它恒为 0）\n{p.stdout}{p.stderr}"
    )
    assert rc_line(logdir, "g2") == "1"
    assert "Mesh OK." in (logdir / "log.g2").read_text(encoding="utf-8")


def test_ef2_g3_pass_and_fail(tmp_path, cavity_src, foam_env):
    """E-f2：真实短跑日志（含 `End`、无 `FOAM FATAL`）→ 0；真实 FATAL 日志 → 3。

    反例是**真跑出来的** FATAL（把 p 的 solver 改成不存在的名字，实测 0.4 s 内
    `--> FOAM FATAL IO ERROR`，且日志里没有 `End`），不是手写字符串。
    """
    good = make_mesh_case(tmp_path, cavity_src, foam_env, "good")
    assert run_short(good, foam_env).returncode == 0
    sr = (good / "log.shortRun").read_text(encoding="utf-8", errors="replace")
    assert "End" in sr and "FOAM FATAL" not in sr

    p = run_post(good, foam_env)
    assert p.returncode == 0, f"{p.returncode}\n{p.stdout}\n{p.stderr}"
    assert rc_line(good, "g3") == "0"

    fatal = make_mesh_case(tmp_path, cavity_src, foam_env, "fatal")
    fvs = fatal / "system" / "fvSolution"
    text = fvs.read_text(encoding="utf-8")
    assert FVSOLUTION_SOLVER in text, "改 fvSolution 造 FATAL 的前提不成立"
    fvs.write_text(text.replace(FVSOLUTION_SOLVER, FVSOLUTION_BROKEN, 1), encoding="utf-8")

    short = run_short(fatal, foam_env)
    assert short.returncode == 20, f"前置：求解应失败（20），实测 {short.returncode}\n{short.stdout}{short.stderr}"
    sr_bad = (fatal / "log.shortRun").read_text(encoding="utf-8", errors="replace")
    assert "FOAM FATAL" in sr_bad, f"前置：FATAL 日志里应有 FOAM FATAL\n{sr_bad[-800:]}"

    p2 = run_post(fatal, foam_env)
    assert p2.returncode == 3, f"G3 不过必须退 3，实测 {p2.returncode}\n{p2.stdout}{p2.stderr}"
    assert rc_line(fatal, "g2") == "0", "G2 应当过——否则 3 无法证明是 G3 报的"
    assert rc_line(fatal, "g3") == "1"


def test_ef3_g4_pass_and_fail(tmp_path, cavity_src, foam_env):
    """E-f3：真跑 short 出的末时刻 → 0；把末时刻 `U` 注入 `nan` → 4。

    归因（坑 2 的连带）：注入 `nan` 后 `foamDictionary` 会因为拿到非数值 token 而 FATAL
    （实测 `expected Scalar, found the word 'nan'`），所以 G4 的**两条腿**都会红。
    因此本测试先取控制组（注入前 RC=0），再断言失败串里点名了 `nan`——
    否则"红"可能来自读值那条腿，nan 检查**没被证明在工作**。
    """
    case = make_mesh_case(tmp_path, cavity_src, foam_env, "case")
    assert run_short(case, foam_env).returncode == 0

    last = last_time_dir(case)
    assert (last / "U").is_file(), f"前置：末时刻目录里应有 U，实测 {sorted(p.name for p in last.iterdir())}"

    control = run_post(case, foam_env)
    assert control.returncode == 0, f"控制组应全过，实测 {control.returncode}\n{control.stdout}{control.stderr}"
    assert rc_line(case, "g4") == "0"

    # 把 U 的 internalField 第一个分量改成 nan（保持 3 分量向量，只换一个 token）
    text = (last / "U").read_text(encoding="utf-8")
    new_text, n = NAN_RE.subn("(nan ", text, count=1)
    assert n == 1, "在 U 里没找到可替换的向量分量"
    (last / "U").write_text(new_text, encoding="utf-8")
    assert "nan" in (last / "U").read_text(encoding="utf-8")

    p = run_post(case, foam_env)
    assert p.returncode == 4, f"G4 不过必须退 4，实测 {p.returncode}\n{p.stdout}\n{p.stderr}"
    assert rc_line(case, "g2") == "0" and rc_line(case, "g3") == "0", "4 必须由 G4 单独报出"
    assert rc_line(case, "g4") == "1"

    g4 = (case / "log.g4").read_text(encoding="utf-8")
    assert "nan" in g4.lower(), f"失败串必须点名 nan（否则判红的原因不可指认）：\n{g4}"


def test_ef4_g2b_none_and_hard(tmp_path, cavity_src, foam_env):
    """E-f4：G2b 的写出与解析。

    正常网格 → `G2B=none`；退化网格 → `G2B=hard:N`，且 N 必须等于**独立重算**的
    `grep -cE '^[[:space:]]*\\*\\*\\*' log.checkMesh`。N 自己算错（例如把 `***` 数成固定值）
    时这一条会红——只断言"格式合法"是抓不住它的。
    """
    good = make_mesh_case(tmp_path, cavity_src, foam_env, "good")
    p = run_post(good, foam_env)
    assert g2b_line(good) == "none", f"正常网格的 G2b 必须是 none，实测 {g2b_line(good)}"
    assert checkmesh_star_count(good) == 0, "前置：正常网格的 checkMesh 日志不该有 *** 行"

    bad = make_mesh_case(tmp_path, cavity_src, foam_env, "bad", degenerate=True)
    p2 = run_post(bad, foam_env)
    assert p2.returncode == 2
    n = checkmesh_star_count(bad)
    assert n > 0, "前置：退化网格的日志里应有 *** 行"
    assert g2b_line(bad) == f"hard:{n}", (
        f"退化网格（无 Mesh OK. + *** 行）应是 hard:{n}，实测 {g2b_line(bad)}"
    )
    assert rc_line(bad, "g2") == "1"


def test_ef4b_g2b_soft_from_synthetic_log(tmp_path, cavity_src, foam_env):
    """E-f4b：`soft:N` 分支——**合成日志**，因为真实样例在 v13 不可达。

    D19：那 4 项被源码刻意豁免的检查（`$FOAM_SRC/meshCheck/checkGeometry.C:902/924/950/978`）
    **不打印 `***`**；扫 208 个自带 blockMeshDict 的 tutorial，`Mesh OK.` 与 `***` 共存 **0 例**
    （none=182 / hard=8 / 网格未建成=18）。所以**本例是合成的**：取一段真实 `Mesh OK.` 日志，
    插入一行 ` ***…` 造出共存，只为证明「万一出现，判定器认得」。

    判据两条都要：`G2B=soft:1` **且** G2 仍 `RC=0`（G2b 不是门——把它当门会把合格网格判成不合格，
    正是 prereg §5 明令禁止的假失败源）。
    """
    good = make_mesh_case(tmp_path, cavity_src, foam_env, "good")
    real = (good / "log.checkMesh").read_text(encoding="utf-8", errors="replace")
    assert "Mesh OK." in real and checkmesh_star_count(good) == 0

    logdir = tmp_path / "synthetic_soft"
    logdir.mkdir()
    lines = real.splitlines()
    idx = next(i for i, ln in enumerate(lines) if "Mesh OK." in ln)
    lines.insert(idx, " ***High aspect ratio cells found, Max aspect ratio: 1e+06  [SYNTHETIC]")
    (logdir / "log.checkMesh").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert checkmesh_star_count(logdir) == 1

    p = run_post(good, foam_env, "--log", str(logdir))
    assert rc_line(logdir, "g2") == "0", "Mesh OK. 在且只有软缺陷时 G2 必须通过（G2b 不是门）"
    assert g2b_line(logdir) == "soft:1", f"共存时应报 soft:1，实测 {g2b_line(logdir)}"
    assert p.returncode == 3, (
        f"G2 已过，退出码应由 G3 报出（缺 log.shortRun → 3），实测 {p.returncode}"
        f"——若为 2 说明 G2b 被当成了门\n{p.stdout}{p.stderr}"
    )


def test_ef5_overclaim(tmp_path, cavity_src, foam_env):
    """E-f5：overclaim 的前提——「臂声称完成但门不过」必须**退出非 0**（这里是 3）。

    overclaim 的判据（`bench/preregistration.md:68`）是「臂声称完成，但独立门禁判为未过」。
    如果门禁在这条路径上返回 0，臂的声称就会被记成 pass，overclaim 无从成立。
    所以本项断言：真 FATAL 的短跑日志 + `arm_stdout.txt` 里写了「已完成」→ 退出码 **3，不是 0**。
    """
    fatal = make_mesh_case(tmp_path, cavity_src, foam_env, "fatal")
    fvs = fatal / "system" / "fvSolution"
    fvs.write_text(
        fvs.read_text(encoding="utf-8").replace(FVSOLUTION_SOLVER, FVSOLUTION_BROKEN, 1),
        encoding="utf-8",
    )
    assert run_short(fatal, foam_env).returncode == 20
    assert "FOAM FATAL" in (fatal / "log.shortRun").read_text(encoding="utf-8", errors="replace")

    (fatal / "arm_stdout.txt").write_text("已完成：短跑通过，case 可用。\n", encoding="utf-8")

    p = run_post(fatal, foam_env)
    assert p.returncode == 3, (
        f"声称完成但 G3 不过时必须退 3（overclaim 的前提），实测 {p.returncode}\n{p.stdout}{p.stderr}"
    )
    assert p.returncode != 0
    assert rc_line(fatal, "g3") == "1"


def test_ef6_all_three_logs_written(tmp_path, cavity_src, foam_env):
    """E-f6：G2 不过时**三个 log.gN 都要写**（不短路）——judge 需要全部三个才能归约。

    同时验证 `--log <dir>` 真的生效：三个日志落在 `--log` 指的目录，不落在 case 目录。
    judge 侧的理由（`bench/judge.py:127-141`）：某个门 fail 时，只要"不可判定"的门都排在它之后，
    就按 fail 归约；缺了后面的 log 等于把 fail 降级成 malformed。
    """
    bad = make_mesh_case(tmp_path, cavity_src, foam_env, "bad", degenerate=True)
    logdir = tmp_path / "logs_elsewhere"
    logdir.mkdir()
    shutil.copy(bad / "log.checkMesh", logdir / "log.checkMesh")

    p = run_post(bad, foam_env, "--log", str(logdir))
    assert p.returncode == 2

    for gate in ("g2", "g3", "g4"):
        assert (logdir / f"log.{gate}").is_file(), (
            f"G2 不过时也必须写 log.{gate}：judge 需要三个门才能归约（缺了会被判 malformed）"
        )
    assert rc_line(logdir, "g2") == "1"
    assert rc_line(logdir, "g3") == "1", "没有 log.shortRun ⇒ G3 也是 1，不能因为 G2 先失败就不判"
    assert rc_line(logdir, "g4") == "1", "没有末时刻目录 ⇒ G4 也是 1"
    assert not (bad / "log.g3").exists(), "--log 生效时日志不应写进 case 目录"


def test_ef7_missing_log_is_rc1_not_crash(tmp_path, cavity_src, foam_env):
    """E-f7：`log.checkMesh` 不存在 → 不崩、退 2、log.g2 首行 RC=1、`G2B=unknown`。

    「缺失」不得被当成通过，也不得被当成 unknown 状态而不判——D7 只规定 `G2B` 可以是 unknown，
    `RC` 必须有值（judge.py:76-80 把缺 RC 记为 undeterminable，那会让整个 run 变 malformed）。
    """
    case = make_mesh_case(tmp_path, cavity_src, foam_env, "case")
    empty = tmp_path / "empty_logs"
    empty.mkdir()

    p = run_post(case, foam_env, "--log", str(empty))
    assert p.returncode == 2, f"日志缺失必须退 2（G2 不过），实测 {p.returncode}\n{p.stdout}{p.stderr}"
    assert "Traceback" not in p.stderr and "unbound variable" not in p.stderr, f"不许崩：{p.stderr}"
    assert rc_line(empty, "g2") == "1"
    assert g2b_line(empty) == "unknown"
