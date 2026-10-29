"""E-lite（`scripts/verify_case.sh --stage pre`）的 L1 测试：G1 结构 + G5 范围，6 项。

规格来源（逐字，勿改写）：
  - `references/09-architecture-and-test-plan.md:145-183`（两入口 / log.gN 格式 / 退出码 D6）
  - `references/09-architecture-and-test-plan.md:302-341`（E-lite 6 项 E-p1…E-p6）
  - `bench/preregistration.md:85-90`（G1 / G2 / G3 / G4 / G5 / G2b 判据原文）
  - `references/00-project-readme.md:230`（既有退出码 0–4，第五码 5 = G5 是 D1 的后果）

「改动」怎么算（两种，脚本内固定顺序，见 docstring 末）：
  ① `<dir>/base` 存在 → `git diff --no-index --no-index --name-status -z -- base case`。
     用 git 自己的内容比较，不受 cp/touch 影响；仓库本身不是 git 仓库也能用（--no-index 正为此）。
  ② `<dir>/base` 不存在 → 取 mtime 晚于 `<dir>/case.meta` 的文件。
     弱：任何解包/cp 都会污染，所以只要 base/ 在就绝不走这条。
  本文件的 fixture 全部带 `base/`，因此 **mtime 分支未被这 6 项覆盖**（已知缺口，不是通过）。

fixture 布局（= `bench/preregistration.md:387` 的 run<k>/ 布局）：
    tests/unit/fixtures/<name>/
        case.meta        JSON：source / derived_at / spec / changes / allowed_files
        base/            基线 case 树（git diff 的左端）
        case/            被测 case 树（G1 判它，G5 与 base 比它）
脚本把 log.g1 / log.g5 写进 `<dir>`（即 fixtures/<name>/ 那一层），不写进 `case/`——
否则日志自己会成为「改动」而污染 G5。

测试只跑 `bash scripts/verify_case.sh`，**不跑任何 OpenFOAM 命令**（不 source bashrc、
不 blockMesh / checkMesh / foamRun）。若哪天这里开始需要 OpenFOAM，说明 E-lite 被做坏了。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_case.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

GATES_PRE = ("g1", "g5")
GATES_POST = ("g2", "g3", "g4")


def _prepare(fixture: str, tmp_path: Path) -> Path:
    """把 fixture 复制到 tmp（测试不得污染 fixtures/），并清掉可能残留的日志。"""
    dst = tmp_path / fixture
    shutil.copytree(FIXTURES / fixture, dst)
    for g in GATES_PRE + GATES_POST:
        (dst / f"log.{g}").unlink(missing_ok=True)
    return dst


def _run(run_dir: Path, *args: str) -> subprocess.CompletedProcess:
    cmd = ["bash", str(SCRIPT), "--stage", "pre", "--case", str(run_dir), *args]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)


def _rc_line(run_dir: Path, gate: str) -> str:
    """读 log.<gate> 第 1 行，返回 `RC=` 后面的值。文件缺失直接失败（缺失 ≠ 通过）。"""
    log = run_dir / f"log.{gate}"
    assert log.is_file(), f"{log} 不存在：缺失的 log 在 judge 眼里是 undeterminable，不是 pass"
    first = log.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("RC="), f"{log} 第 1 行不是 RC=，实测 {first!r}（D7 格式）"
    return first[3:].strip()


def _log_lines(run_dir: Path, gate: str) -> list[str]:
    return (run_dir / f"log.{gate}").read_text(encoding="utf-8").splitlines()


def _assert_log_shape(run_dir: Path, gate: str, rc: str) -> None:
    """D7：第 1 行 RC，第 2 行留给 G2B=（g1/g5 必须为空），第 3 行起才是自由文本。"""
    lines = _log_lines(run_dir, gate)
    assert lines[0] == f"RC={rc}", lines[:2]
    assert len(lines) >= 2, f"log.{gate} 只有 1 行，第 2 行（G2B 位）必须留空"
    assert lines[1].strip() == "", f"log.{gate} 第 2 行必须为空（G2B= 只属于 log.g2），实测 {lines[1]!r}"
    assert not any("G2B=" in ln for ln in lines), f"log.{gate} 不该出现 G2B=：那是 --stage post 的产物"


def test_ep1_g1_complete_exit_0_and_patch_set_checked(tmp_path):
    """E-p1：G1 完整 → 0；顺带验 P4a（0/U、0/p 的 patch 集合必须等于 polyMesh/boundary）。

    pre_ok 与 pre_boundary_violation 只差 0/U 里多一个 `inlet` patch：前者 0，后者必须 1。
    只判 `test -f` 三连的实现会在这里就红——这正是 P4a 想前移到 pre 的那类失败。
    """
    ok = _prepare("pre_ok", tmp_path)
    p = _run(ok)
    assert p.returncode == 0, p.stdout + p.stderr
    _assert_log_shape(ok, "g1", "0")
    _assert_log_shape(ok, "g5", "0")

    bad = _prepare("pre_boundary_violation", tmp_path)
    p2 = _run(bad)
    assert p2.returncode == 1, p2.stdout + p2.stderr
    assert _rc_line(bad, "g1") == "1"
    assert "inlet" in (bad / "log.g1").read_text(encoding="utf-8"), "失败串必须点名多出来的 patch"


def test_ep2_missing_fvSolution_exit_1(tmp_path):
    """E-p2：删掉 system/fvSolution → 1，且 log.g1=RC=1、**不产生** log.g2..log.g4（短路）。"""
    run_dir = _prepare("pre_no_fvSolution", tmp_path)
    p = _run(run_dir)
    assert p.returncode == 1, p.stdout + p.stderr
    _assert_log_shape(run_dir, "g1", "1")
    assert "fvSolution" in (run_dir / "log.g1").read_text(encoding="utf-8")
    for g in GATES_POST:
        assert not (run_dir / f"log.{g}").exists(), f"pre 阶段不许写 log.{g}（G2/G3/G4 是 post 的事）"


def test_ep3_change_inside_allowed_files_exit_0(tmp_path):
    """E-p3：只改 allowed_files 内 → 0。

    pre_ok 的 case/system/controlDict 真的改了（writeInterval 100 → 50），所以这项不是空跑：
    先断言 G5 确实看见了 1 个改动，再断言它是合规的。随后用 `--allowed system/controlDict`
    覆盖 case.meta 的 `system/*`，同一条改动仍应放行 —— 验命令行入口与元数据入口同语义。
    """
    run_dir = _prepare("pre_ok", tmp_path)
    p = _run(run_dir)
    assert p.returncode == 0, p.stdout + p.stderr
    g5 = (run_dir / "log.g5").read_text(encoding="utf-8")
    assert "改动 1 个文件" in g5, f"G5 没看见改动，这条测试就是空跑：\n{g5}"
    assert "system/controlDict" not in g5 or "VIOLATION" not in g5, g5

    p2 = _run(run_dir, "--allowed", "system/controlDict")
    assert p2.returncode == 0, p2.stdout + p2.stderr
    assert "命令行" in (run_dir / "log.g5").read_text(encoding="utf-8"), "--allowed 应覆盖 case.meta"


def test_ep4_polymesh_change_without_reason_exit_5(tmp_path):
    """E-p4：改 constant/polyMesh/blockMeshDict 且 case.meta 无理由 → 5。

    取 pre_boundary_excused（同一份改动、同一份 allowed_files：`system/*`+`0/*`，**不含**
    constant/polyMesh/）并清空 changes。于是 p4 与 p5 的唯一差别就是「理由有没有写」，
    门必须只由这一点翻转，而不是被别的差异带偏。
    """
    run_dir = _prepare("pre_boundary_excused", tmp_path)
    meta_path = run_dir / "case.meta"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["changes"], "fixture 预置理由被清掉了，这项测试的前提不成立"
    meta["changes"] = []
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    p = _run(run_dir)
    assert p.returncode == 5, f"期望 5（G5），实测 {p.returncode}\n{p.stdout}{p.stderr}"
    _assert_log_shape(run_dir, "g1", "0")   # G1 本身是过的，只红 G5
    _assert_log_shape(run_dir, "g5", "1")
    assert "constant/polyMesh/blockMeshDict" in (run_dir / "log.g5").read_text(encoding="utf-8")


def test_ep5_polymesh_change_with_reason_exit_0(tmp_path):
    """E-p5：同一处 constant/polyMesh/ 改动，case.meta.changes 写了理由 → 0（例外放行）。"""
    run_dir = _prepare("pre_boundary_excused", tmp_path)
    p = _run(run_dir)
    assert p.returncode == 0, p.stdout + p.stderr
    _assert_log_shape(run_dir, "g1", "0")
    _assert_log_shape(run_dir, "g5", "0")
    g5 = (run_dir / "log.g5").read_text(encoding="utf-8")
    assert "放行 constant/polyMesh/blockMeshDict" in g5, f"放行必须在日志里留名（否则等于没判）：\n{g5}"


def test_ep6_double_failure_reports_smallest_code_1(tmp_path):
    """E-p6：同时缺 fvSolution（G1）且越界（G5）→ **1**，不是 5。

    D6「只报第一个失败的门」：退出码按门号取最小。两个门都要判、都要写日志（judge 同时读
    g1 与 g5），只有退出码短路到 G1 —— 「日志齐全」与「只报第一个」不矛盾。
    """
    run_dir = _prepare("pre_both_fail", tmp_path)
    p = _run(run_dir)
    assert p.returncode == 1, f"双失败必须报 1（G1 优先），实测 {p.returncode}\n{p.stdout}{p.stderr}"
    assert _rc_line(run_dir, "g1") == "1"
    assert _rc_line(run_dir, "g5") == "1", "G5 也要如实写 1：judge 读两行 RC，不能因为短路就不判"
    assert "G1 RC=1" in p.stdout and "G5 RC=1" in p.stdout, p.stdout


# ---------------------------------------------------------------------------
# E-p7（验收时补，2026-10-28）：**mtime 分支**。
#
# 为什么必须有这一条：上面 5 个 fixture 全部带 `base/`，于是 G5 永远走 `git diff --no-index`
# 那条路，`mtime` 分支**一行测试都没有**——子代理 E 自己在报告里指出了这个缺口。
# 一条判据只要没被测试证明会红，就等于没有判据（本项目的硬要求）。
#
# 判据（两条同时成立才算通过）：
#   ① 没有 base/ 时脚本不崩，且能判出越界（exit 5）——证明 mtime 分支真的在工作；
#   ② 同一棵树、有 base/ 且内容相同 → exit 0——证明「有 base 就不走 mtime」这条优先级成立。
#   只证①，把 mtime 分支改成「恒判越界」也能过；只证②，mtime 分支死了也发现不了。
# ---------------------------------------------------------------------------
def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


_BASE_FILES = {
    "system/controlDict": "FoamFile { version 2.0; }\nendTime 1;\n",
    "system/fvSchemes": "FoamFile { version 2.0; }\n",
    "system/fvSolution": "FoamFile { version 2.0; }\n",
    "constant/momentumTransport": "FoamFile { version 2.0; }\n",
    "constant/polyMesh/boundary": "FoamFile { version 2.0; }\n2(movingWall fixedWall)\n",
    "0/U": "FoamFile { version 2.0; }\n",
    "0/p": "FoamFile { version 2.0; }\n",
}


def _make_meta(root: Path, *, allowed: list[str], changes: str = "") -> None:
    (root / "case.meta").write_text(
        json.dumps(
            {
                "source": "incompressibleFluid/cavity",
                "derived_at": "2026-10-28T00:00:00",
                "spec": {},
                "changes": changes,
                "allowed_files": allowed,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _run_pre(workdir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--stage", "pre", "--case", str(workdir)],
        capture_output=True,
        text=True,
    )


def test_ep7_mtime_branch_without_base(tmp_path):
    """无 base/ 时走 mtime：改了不许改的文件 → 必须 exit 5。"""
    workdir = tmp_path / "mtime_case"
    _write_tree(workdir / "case", _BASE_FILES)
    _make_meta(workdir, allowed=["system/*"])

    # 先跑一次，让日志生成（脚本会排除自己写的 run 产物）
    first = _run_pre(workdir)
    assert first.returncode == 0, f"初次应通过（只改了 system/ 内），实得 {first.returncode}"

    # 再改一个 allowed_files 之外的字典；touch 时间戳严格晚于 case.meta
    import os
    import time

    time.sleep(0.01)
    target = workdir / "case" / "constant" / "momentumTransport"
    target.write_text(target.read_text(encoding="utf-8") + "\n// touched\n", encoding="utf-8")
    os.utime(target, None)

    second = _run_pre(workdir)
    assert second.returncode == 5, (
        f"无 base/ 时靠 mtime 应判出越界（exit 5），实得 {second.returncode}；"
        f"stderr={second.stderr[:200]}"
    )


def test_ep7b_base_present_takes_precedence_over_mtime(tmp_path):
    """有 base/ 且内容相同 → exit 0，即使 case/ 里的 mtime 更新。

    这一条证明「只要 base 在就绝不走 mtime」——否则 cp/解包 会把合法 case 判成越界。
    """
    import os
    import time

    workdir = tmp_path / "base_case"
    _write_tree(workdir / "base", _BASE_FILES)
    _write_tree(workdir / "case", _BASE_FILES)
    _make_meta(workdir, allowed=["system/*"])

    time.sleep(0.01)
    for rel in _BASE_FILES:                      # 内容不变，只把 mtime 全部推新
        os.utime(workdir / "case" / rel, None)

    proc = _run_pre(workdir)
    assert proc.returncode == 0, (
        f"内容未变时不得因 mtime 判越界，实得 {proc.returncode}；stderr={proc.stderr[:200]}"
    )
