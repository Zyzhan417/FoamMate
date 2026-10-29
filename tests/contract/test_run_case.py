"""模块 D（scripts/run_case.sh）的 L2 契约测试，7 项。

契约（references/09-architecture-and-test-plan.md §D）：
  CLI   run_case.sh --case <dir> --mode check|short|full [--timeout <秒>]
  步骤  ① 环境探测 → ② 网格准备（polyMesh 缺失时 blockMesh） → ③ checkMesh
        → ④ short/full 求解
  退出  0 正常 / 20 求解失败 / 21 超时 / 22 环境缺失 / 23 无可用网格 / 2 用法错误

测试对应关系：
  D1 test_d1_solver_failure_20              删 system/fvSolution → 20
  D2 test_d2_logs_by_mode                   check 只出 log.checkMesh；short 出 checkMesh+shortRun
  D3 test_d3_timeout_21                     --timeout 3 → 21，且不挂死（< 30 s）
  D4 test_d4_env_missing_22_not_127         空环境下 22 而非 127（坑 2）
  D5 test_d5_no_mesh_no_dict_23             无 polyMesh 且无 blockMeshDict → 23（不是 20）
  D6 test_d6_short_run_really_shortened     endTime 真被改成 deltaT*2，且日志最大时间不超它（坑 1）
  D7 test_d7_blockmesh_auto_prepared        无 polyMesh 的 cavity → 自动 blockMesh 后退出 0

设计约定：
- 全部 case 都在 `tmp_path` 下从 tutorial 复制，绝不写 bench/（AGENTS.md R12）。
- 所有数字都是**实测**：需要先用 foamDictionary 回读确认测试自己的 setup 生效（R12 的教训：
  `foamDictionary` 用法错时静默不改且退 0，测试 setup 自己也会踩坑）。
- D3 的慢化机制说明（重要，别"修"回去）：
  契约规定 short 模式把 endTime 改写成 `deltaT*2`，因此**改 endTime 不能让短跑变慢**——
  实测 cavity 2 步只要 0.1 s。所以 D3 用 `nOuterCorrectors 20000` 让每个时间步本身变慢
  （实测 2 步不设上限 27.1 s / 40000 次 PIMPLE 迭代，`timeout 3` 实测 3.0 s 被杀并退 124；
  即上限 3 s 对不设上限 27.1 s，约 9 倍余量，不受机器快慢影响）。
  仍然按契约把 endTime 设成 1e9，以保持与测试计划的字面一致。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

# 环境引导（bashrc → env）、cavity 派生源与五个根统一由 `tests/contract/conftest.py`
# 提供：本文件只声明 `foam_env` / `cavity_src` / `roots` 夹具，不再自己 source 一遍。

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "run_case.sh"


# 空环境跑脚本时用的 PATH（坑 2：真空下 foamRun 退 127，与"求解失败"同形）
EMPTY_ENV_PATH = "/usr/bin:/bin"

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)", re.MULTILINE)
STDERR_ENV_MISSING = "OpenFOAM 环境未加载"


# ---------------------------------------------------------------- 基础设施


def make_case(tmp_path: Path, cavity_src: Path, name: str = "case") -> Path:
    """cp -a cavity 到 tmp_path/<name>，返回该路径。

    cavity 的 constant/ 只有 momentumTransport + physicalProperties，**没有 polyMesh**
    （实测），所以这是"无网格"初始状态，正好用来测 D5/D7。
    """
    dest = tmp_path / name
    subprocess.run(["cp", "-a", f"{cavity_src}/.", str(dest)], check=True)
    return dest


def run_case(
    env: dict,
    case: Path,
    mode: str,
    timeout: int | None = None,
    *,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    args = ["bash", str(SCRIPT), "--case", str(case), "--mode", mode, *extra_args]
    if timeout is not None:
        args += ["--timeout", str(timeout)]
    return subprocess.run(args, capture_output=True, text=True, env=env)


def fd_value(env: dict, case: Path, entry: str) -> str:
    """回读 controlDict 顶层标量（必须带 -value，否则拿到的是带 `;` 的原文）。"""
    proc = subprocess.run(
        ["bash", "-c", f"foamDictionary system/controlDict -case . -entry {entry} -value"],
        cwd=case,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"回读 {entry} 失败: {proc.stderr[:300]}"
    return proc.stdout.strip()


def fd_set(env: dict, case: Path, entry: str, value: str) -> None:
    """设置并**回读校验**（坑 1：字典文件是位置参数，写错时退 0 但不改）。"""
    proc = subprocess.run(
        ["bash", "-c",
         f"foamDictionary system/controlDict -case . -entry {entry} -set {value}"],
        cwd=case,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"设置 {entry}={value} 失败: {proc.stderr[:300]}"
    got = fd_value(env, case, entry)
    assert float(got) == pytest.approx(float(value)), (
        f"测试 setup 自己没生效：{entry} 期望 {value}，回读 {got}"
    )


def log_text(case: Path, name: str) -> str:
    p = case / name
    assert p.is_file(), f"缺少日志 {name}（case 里有：{sorted(x.name for x in case.iterdir())}）"
    return p.read_text(errors="replace")


# ---------------------------------------------------------------- D1–D7


def test_d1_solver_failure_20(foam_env: dict, tmp_path: Path, cavity_src: Path) -> None:
    """求解失败必须退 20（不是 0、不是 1、不是 127）。"""
    case = make_case(tmp_path, cavity_src)
    (case / "system" / "fvSolution").unlink()

    proc = run_case(foam_env, case, "short", timeout=120)

    assert proc.returncode == 20, (
        f"期望 20（求解失败），实得 {proc.returncode}\n"
        f"stdout={proc.stdout[-800:]}\nstderr={proc.stderr[-800:]}"
    )


def test_d2_logs_by_mode(foam_env: dict, tmp_path: Path, cavity_src: Path) -> None:
    """check 模式只产 log.checkMesh；short 模式另产 log.shortRun。"""
    case = make_case(tmp_path, cavity_src)

    proc = run_case(foam_env, case, "check", timeout=120)
    assert proc.returncode == 0, f"check 模式失败 rc={proc.returncode}\n{proc.stderr[-800:]}"

    check_log = case / "log.checkMesh"
    assert check_log.is_file() and check_log.stat().st_size > 0, "check 模式未产出非空 log.checkMesh"
    assert not (case / "log.shortRun").exists(), "check 模式不许产出 log.shortRun"
    assert not (case / "log.run").exists(), "check 模式不许产出 log.run"

    proc = run_case(foam_env, case, "short", timeout=120)
    assert proc.returncode == 0, f"short 模式失败 rc={proc.returncode}\n{proc.stderr[-800:]}"

    for name in ("log.checkMesh", "log.shortRun"):
        p = case / name
        assert p.is_file() and p.stat().st_size > 0, f"short 模式缺少非空 {name}"
    assert not (case / "log.run").exists(), "short 模式不许产出 log.run"


def test_d3_timeout_21(foam_env: dict, tmp_path: Path, cavity_src: Path) -> None:
    """--timeout 3 必须映射成 21，且总耗时 < 30 s（不挂死）。"""
    case = make_case(tmp_path, cavity_src)

    # 契约里的 endTime=1e9（保留字面一致；它对短跑时长无影响，见模块 docstring）
    fd_set(foam_env, case, "endTime", "1e9")

    # 真正的慢化机制：两步 × 20000 个外迭代（实测不设上限 27.1 s，约为上限 3 s 的 9 倍）
    fv = case / "system" / "fvSolution"
    text = fv.read_text()
    assert "nCorrectors     2;" in text, "cavity 的 fvSolution 结构变了，请更新 D3 的慢化注入"
    fv.write_text(text.replace("nCorrectors     2;", "nOuterCorrectors 20000;\n    nCorrectors     2;", 1))
    assert "nOuterCorrectors 20000;" in fv.read_text(), "D3 慢化注入未生效"

    started = time.monotonic()
    proc = run_case(foam_env, case, "short", timeout=3)
    elapsed = time.monotonic() - started

    assert proc.returncode == 21, (
        f"期望 21（超时），实得 {proc.returncode}，耗时 {elapsed:.1f}s\n"
        f"stderr={proc.stderr[-800:]}"
    )
    assert elapsed < 30, f"超时路径耗时 {elapsed:.1f}s，说明没被 timeout 杀掉（挂死风险）"


def test_d4_env_missing_22_not_127(
    tmp_path: Path, cavity_src: Path, foam_env: dict
) -> None:
    """空环境下必须主动探测出 22，而不是让子进程 127 冒充求解失败（坑 2）。"""
    case = make_case(tmp_path, cavity_src)

    proc = subprocess.run(
        ["env", "-i", f"PATH={EMPTY_ENV_PATH}", "bash", str(SCRIPT),
         "--case", str(case), "--mode", "check"],
        capture_output=True,
        text=True,
        env={"PATH": EMPTY_ENV_PATH},
    )

    assert proc.returncode == 22, (
        f"期望 22（环境缺失），实得 {proc.returncode}\nstderr={proc.stderr[-800:]}"
    )
    assert proc.returncode != 127, "把 foamRun 的 127 当成了求解失败"
    assert STDERR_ENV_MISSING in proc.stderr, (
        f"stderr 缺少 '{STDERR_ENV_MISSING}'，实得：{proc.stderr[-400:]!r}"
    )
    # 环境缺失时不该留下任何 OpenFOAM 产物
    assert not (case / "log.checkMesh").exists(), "环境缺失时不应继续执行 checkMesh"


def test_d5_no_mesh_no_dict_23(foam_env: dict, tmp_path: Path, cavity_src: Path) -> None:
    """既无 polyMesh 又无 blockMeshDict → 23（不能落到 blockMesh 失败被当成 20）。"""
    case = make_case(tmp_path, cavity_src)
    if (case / "constant" / "polyMesh").exists():
        shutil.rmtree(case / "constant" / "polyMesh")
    (case / "system" / "blockMeshDict").unlink()
    assert not (case / "constant" / "polyMesh").exists()
    assert not (case / "system" / "blockMeshDict").exists()

    proc = run_case(foam_env, case, "check", timeout=120)

    assert proc.returncode == 23, (
        f"期望 23（无可用网格），实得 {proc.returncode}\nstderr={proc.stderr[-800:]}"
    )


def test_d6_short_run_really_shortened(
    foam_env: dict, tmp_path: Path, cavity_src: Path
) -> None:
    """短跑必须真的把 endTime 改成 deltaT*2 —— 专防坑 1 的静默失败。"""
    case = make_case(tmp_path, cavity_src)

    delta_t = float(fd_value(foam_env, case, "deltaT"))
    expected = delta_t * 2

    proc = run_case(foam_env, case, "short", timeout=120)
    assert proc.returncode == 0, f"short 失败 rc={proc.returncode}\n{proc.stderr[-800:]}"

    got = float(fd_value(foam_env, case, "endTime"))
    assert got == pytest.approx(expected, rel=1e-9), (
        f"endTime 未被改成 deltaT*2={expected:g}，回读 {got:g}（foamDictionary 静默失败？）"
    )

    times = [float(m) for m in TIME_RE.findall(log_text(case, "log.shortRun"))]
    assert times, "log.shortRun 里没有任何 'Time = ...' 行"
    assert max(times) <= expected + 1e-9 + 1e-6 * abs(expected), (
        f"短跑实际推进到 {max(times):g}，超过 endTime={expected:g}"
    )
    assert max(times) > 0, f"短跑没有推进时间（最大 Time = {max(times):g}）"


def test_d7_blockmesh_auto_prepared(
    foam_env: dict, tmp_path: Path, cavity_src: Path
) -> None:
    """无 polyMesh 的 cavity 副本，check 模式必须自动 blockMesh 后成功。"""
    case = make_case(tmp_path, cavity_src)
    assert not (case / "constant" / "polyMesh").exists(), "cavity 副本不该自带 polyMesh"

    proc = run_case(foam_env, case, "check", timeout=120)

    assert proc.returncode == 0, f"期望 0，实得 {proc.returncode}\nstderr={proc.stderr[-800:]}"
    mesh = case / "constant" / "polyMesh"
    assert mesh.is_dir(), "constant/polyMesh 未被生成"
    assert (mesh / "points").is_file(), "constant/polyMesh/points 缺失，网格不完整"
    assert (case / "log.blockMesh").is_file(), "未留下 log.blockMesh"
    assert "Mesh OK." in log_text(case, "log.checkMesh"), "checkMesh 未报 Mesh OK."
