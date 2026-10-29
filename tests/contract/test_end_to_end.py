"""端到端：A → C → E(pre) → D → E(post) → assert → judge，必须归约出 `pass`。

## 为什么这个文件必须有

在此之前，6 个模块各自有测试、共 79 项全绿，但**没有任何一个测试同时调用两个模块**。
2026-10-28 手动串联时立刻暴露出三个孤立测试永远发现不了的问题：

1. `parse_requirement.py` 有 shebang 却没有可执行位（`./scripts/x.py` → 126）；
2. judge 从 `run/log.gN` 读，而 E 把日志写在 `--case`（= `run/case/`）里 → judge 判 `malformed`；
3. `case.meta` 的位置在 C（写进 case 树）与 judge（读 run 根）之间不一致。

**单模块测试绿不能推出系统可用**。这个文件的职责就是钉住「拼起来还能不能跑」。

## 布局以冻结的 preerg §12 为准（不是我们后来商量的）

`bench/preregistration.md:387`：

    bench/runs/<批次>/<task>/<arm>/run<k>/   log.g*, log.checkMesh, tokens.json,
                                             case.meta, arm_stdout.txt, case/

即 **run 目录同时容纳 `case/` 与全部日志和 meta**。本测试按这个布局摆目录，
因此它同时校验了「实现是否符合冻结件」，而不是只校验「我们自己内部自洽」。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

# 环境引导（bashrc → env）、cavity 派生源与五个根统一由 `tests/contract/conftest.py`
# 提供：本文件只声明 `foam_env` / `cavity_src` / `roots` 夹具，不再自己 source 一遍。

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
BENCH = REPO_ROOT / "bench"
CAVITY = "incompressibleFluid/cavity"


def _run(argv: list[str], env: dict, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)


def test_full_chain_reduces_to_pass(foam_env: dict, tmp_path: Path):
    """整条链跑通，且 judge 归约出 `pass`。

    断言分四段，每段单独报错——否则一个失败会掩盖后面所有失败，
    看起来「只错了一处」，实际是链断了。
    """
    run_dir = tmp_path / "run0"
    run_dir.mkdir()
    case_dir = run_dir / "case"
    spec_path = run_dir / "spec.json"

    # ---------- 1) A：需求 → spec.json ----------
    proc = _run(
        [sys.executable, str(SCRIPTS / "parse_requirement.py"),
         "--text", "一个二维方腔，顶盖 1 m/s，水，kOmegaSST，稳态",
         "--out", str(spec_path)],
        foam_env,
    )
    assert proc.returncode == 0, f"A 失败 rc={proc.returncode}: {proc.stderr[:300]}"
    assert spec_path.is_file(), "A 没有落盘 spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["complete"] is True, f"A 判需求不完整: {spec['missing']}"

    # ---------- 2) C：派生 case ----------
    proc = _run(
        ["bash", str(SCRIPTS / "new_case.sh"),
         "--source", CAVITY, "--dest", str(case_dir), "--spec", str(spec_path)],
        foam_env, cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, f"C 失败 rc={proc.returncode}: {proc.stderr[:300]}"

    # C 把 case.meta 写在 case 树内（`--dest` 就是 case 树）；prereg §12 则把它列在 run 根。
    # 两处都合法，**测试不替实现搬家**（第一版曾 `shutil.move` 过去，那等于测试自己
    # 补上了缺口，真实布局就没被验证）。D20 的规则：judge 与 E-pre 都认两处，
    # 两处同时存在才判二义。这里保持 C 的原样输出，让链自己去认。
    assert (case_dir / "case.meta").is_file(), "C 没有写 case.meta"

    # 基线快照（G5 需要 base/）
    shutil.copytree(case_dir, run_dir / "base")

    # ---------- 3) E(pre)：G1 + G5 ----------
    proc = _run(
        ["bash", str(SCRIPTS / "verify_case.sh"),
         "--stage", "pre", "--case", str(case_dir), "--log", str(run_dir)],
        foam_env,
    )
    assert proc.returncode == 0, (
        f"E-pre 失败 rc={proc.returncode}: {proc.stdout[:300]}{proc.stderr[:300]}"
    )
    for g in ("log.g1", "log.g5"):
        p = run_dir / g
        assert p.is_file(), (
            f"E-pre 没有把 {g} 写到 --log 目录（prereg §12 要求它在 run 根）。"
            f"实得文件: {sorted(x.name for x in run_dir.iterdir())}"
        )
        assert p.read_text(encoding="utf-8").startswith("RC="), f"{g} 首行不是 RC="

    # ---------- 4) D：短跑（--log 指向 run 根，与 E 的 --log 一致）----------
    proc = _run(
        ["bash", str(SCRIPTS / "run_case.sh"),
         "--case", str(case_dir), "--mode", "short", "--log", str(run_dir)],
        foam_env,
    )
    assert proc.returncode == 0, f"D 失败 rc={proc.returncode}: {proc.stdout[:400]}"
    for name in ("log.checkMesh", "log.shortRun"):
        p = run_dir / name
        assert p.is_file() and p.stat().st_size > 0, (
            f"D 没有把 {name} 写到 --log 目录。实得: {sorted(x.name for x in run_dir.iterdir())}"
        )

    # ---------- 5) E(post)：G2 + G3 + G4 + G2b ----------
    proc = _run(
        ["bash", str(SCRIPTS / "verify_case.sh"),
         "--stage", "post", "--case", str(case_dir), "--log", str(run_dir)],
        foam_env,
    )
    assert proc.returncode == 0, (
        f"E-post 失败 rc={proc.returncode}: {proc.stdout[:400]}{proc.stderr[:300]}"
    )
    for g in ("log.g2", "log.g3", "log.g4"):
        assert (run_dir / g).is_file(), f"E-post 没有写 {g} 到 run 根"

    # ---------- 6) 断言层：assert.json ----------
    #
    # **注意两种 spec 不是一回事，别混**（本测试第一版就混了，被 assert_lib 用
    # `TypeError: string indices must be integers` 当场抓住）：
    #   · A 的 `spec.json`     = 需求四元组（geometry/properties/boundary/objective）
    #   · assert_lib 的入参    = **断言列表**，每项带 `kind`（dict / dict_value /
    #                            key_present / boundary / mesh / behavior）
    # 后者对应任务 yaml 的 `expect_values`，与四元组无结构关系。这里就地构造一条
    # 最小断言（不读 `bench/tasks/`，避免与 R12「设计期禁跑」的边界搅在一起）：
    # `deltaT` 是 cavity 的固有值，且 `--mode short` 只改 `endTime`/`writeInterval`，
    # 不会动它 —— 所以这条断言在 short 之后仍然成立，测的是「断言层接得上」而非「改对了」。
    assertions = [
        {"kind": "dict", "file": "system/controlDict", "key": "deltaT", "expect": 0.005, "tol": 0}
    ]
    assertions_path = run_dir / "assertions.json"
    assertions_path.write_text(json.dumps(assertions, ensure_ascii=False), encoding="utf-8")

    proc = _run(
        [sys.executable, str(BENCH / "assert_lib.py"), str(case_dir), str(assertions_path)],
        foam_env,
    )
    assert proc.returncode == 0, f"assert_lib 失败: {proc.stderr[:400]}"
    verdict_raw = json.loads(proc.stdout)
    assert verdict_raw["overall"] == "match", (
        f"deltaT=0.005 的断言应 match，实得 {verdict_raw['overall']}：{verdict_raw['assertions']}"
    )
    (run_dir / "assert.json").write_text(proc.stdout, encoding="utf-8")

    # ---------- 7) judge：归约 ----------
    proc = _run([sys.executable, str(BENCH / "judge.py"), str(run_dir)], foam_env)
    assert proc.returncode == 0, f"judge 崩了: {proc.stderr[:300]}"
    verdict = json.loads(proc.stdout)

    # 五个门都 RC=0、断言 match、无 overclaim ⇒ 必须 pass。
    # 这里不写 `!= fail` 而是精确要求 pass：判据宽松时，一个把一切记成
    # malformed 的实现也能「不比 fail 更糟」，那不是判定器。
    assert verdict["status"] == "pass", (
        f"整条链跑完，judge 应判 pass，实得 {verdict['status']}（reason={verdict.get('reason')}）。"
        f"各门日志: "
        + ", ".join(f"{g}={ (run_dir / g).read_text(encoding='utf-8').splitlines()[0] if (run_dir / g).is_file() else 'MISSING'}"
                    for g in ("log.g1", "log.g2", "log.g3", "log.g4", "log.g5"))
    )
    assert verdict["g2b"] == "none", f"正常 cavity 网格的 g2b 应为 none，实得 {verdict['g2b']}"
