"""preflight.sh 的 L2 契约测试（spec §6 AC5：能分辨「没 source」与「版本不对」）。

三条判据对应 plan.md §2 的三条测试：
  1. 已 source 的当前环境 → 退 0（缺 `foamRun` 时 skip：环境不到位，这条没有判定力）
  2. 完全干净的 env（PATH=/usr/bin:/bin）→ 退 **50**，且提示里给出可执行的 `source <bashrc>`
  3. 只把 `WM_PROJECT_VERSION` 覆盖成 12 → 退 **51**，且文案含「只支持 OpenFOAM v13」

为什么 2 和 3 必须分开测：两者都让 preflight 失败，但**处置方向相反**——
「没 source」只要跑一条命令，「版本不对」要换安装。若两种情况都退 50（或都退 51），
调用方就无法区分，用户会去重装/降级一个本来没问题的 OpenFOAM，这正是 spec §1 要解决的问题。

为什么要断言「最后一行是可执行的下一步」：错误码对终端里的陌生用户没有信息量，
`source /opt/openfoam13/etc/bashrc` 才能直接复制执行（plan §2 的硬要求）。

设计约定：
- 直接执行脚本（不经 `bash script`），顺带守住可执行位与 shebang；
- 运行模式是 `--check`：无参数按统一契约算用法错误（`tests/unit/test_exit_codes.py`），
  所以跑检查必须显式给 `--check`；
- 第 3 条不 skip：若当前进程没有 source 过 bashrc，本测试自己 source 一次再覆盖版本，
  否则这条会在未 source 的上下文里静默退化成第 2 条的重复。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "preflight.sh"

BASH_RC = "/opt/openfoam13/etc/bashrc"

EX_OK = 0
EX_ENV = 50
EX_VERSION = 51

#: 6 项检查的输出顺序（plan §2 的表）。顺序是契约的一部分：差的顺序会让
#: 「没 source」落到版本检查上，被误报成 51。
CHECK_ORDER = ["bashrc", "commands", "tutorials", "version", "python3", "scripts"]


# ---------------------------------------------------------------- 基础设施


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    assert SCRIPT.is_file(), f"脚本不存在: {SCRIPT}"
    return subprocess.run(
        [str(SCRIPT)],          # 无参数 = 跑检查（默认动作）
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )


def _sourced_env() -> dict[str, str]:
    """当前环境；若当前进程没 source 过 bashrc，则现场 source 一次再取回变量。"""
    env = dict(os.environ)
    if env.get("WM_PROJECT_DIR") and env.get("FOAM_TUTORIALS"):
        return env

    assert Path(BASH_RC).is_file(), f"缺少 {BASH_RC}：无法构造「已 source」的环境"
    proc = subprocess.run(
        ["bash", "-c", f"set -a; source {BASH_RC} >/dev/null 2>&1; env -0"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"source {BASH_RC} 失败: {proc.stderr.strip()[:200]}"
    for item in proc.stdout.split("\0"):
        if "=" in item:
            key, _, value = item.partition("=")
            env[key] = value
    return env


def _combined(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stdout + proc.stderr


# ---------------------------------------------------------------- 三条判据


def test_passes_in_current_env():
    """已 source 的环境 → 退 0，6 项全 OK、顺序正确、stderr 无 FAIL。"""
    if shutil.which("foamRun") is None:
        pytest.skip("当前环境没有 foamRun（bashrc 未 source）：这条判据在此环境下无意义")

    proc = _run(dict(os.environ))

    assert proc.returncode == EX_OK, (
        f"已 source 的环境应退 {EX_OK}，实得 {proc.returncode}。\n"
        f"stdout={proc.stdout.strip()[:500]!r}\nstderr={proc.stderr.strip()[:500]!r}"
    )

    ok_lines = [line for line in proc.stdout.splitlines() if line.startswith("OK ")]
    assert [line.split()[1] for line in ok_lines] == CHECK_ORDER, (
        f"6 项 OK 行的名字/顺序应与 plan §2 的表一致，实得 "
        f"{[line.split()[1] for line in ok_lines]}；原始 stdout={proc.stdout.strip()[:500]!r}"
    )
    assert "FAIL " not in proc.stderr, f"全过时不应有 FAIL 行：{proc.stderr.strip()[:300]!r}"


def test_fails_50_without_foam_env():
    """干净 env（无 FOAM_*）→ 退 50，且给出可执行的 `source <bashrc>` 下一步。"""
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
    proc = _run(env)

    assert proc.returncode == EX_ENV, (
        f"未 source 时应退 {EX_ENV}（环境不全），实得 {proc.returncode}。\n"
        f"stdout={proc.stdout.strip()[:500]!r}\nstderr={proc.stderr.strip()[:500]!r}"
    )

    combined = _combined(proc)
    assert "source" in combined, f"提示里必须出现可执行的 source 命令：{combined[:500]!r}"
    assert BASH_RC in combined, (
        f"汇总必须给出具体 bashrc 路径（{BASH_RC}），不能只说 source：{combined[:500]!r}"
    )

    last_line = proc.stderr.strip().splitlines()[-1]
    assert "source" in last_line and "下一步" in last_line, (
        f"最后一行必须是可执行的下一步（不是错误码），实得：{last_line!r}"
    )

    # 没 source 时不得报 51：版本无从判断，报 51 会把用户引向重装
    assert "只支持 OpenFOAM v13" not in combined, (
        "环境未加载时不应给出「版本不符」的结论（应为 50）："
        f"{combined[:500]!r}"
    )


def test_fails_51_on_version_mismatch():
    """只覆盖 WM_PROJECT_VERSION=12 → 退 51，文案说明本包只支持 v13。"""
    env = _sourced_env()
    env["WM_PROJECT_VERSION"] = "12"

    proc = _run(env)

    assert proc.returncode == EX_VERSION, (
        f"版本不符时应退 {EX_VERSION}，实得 {proc.returncode}。\n"
        f"stdout={proc.stdout.strip()[:500]!r}\nstderr={proc.stderr.strip()[:500]!r}"
    )
    assert "只支持 OpenFOAM v13" in _combined(proc), (
        f"51 的文案必须说明「本包只支持 OpenFOAM v13」，实得：{_combined(proc)[:500]!r}"
    )

    # 只有 version 一项失败：证明 50 与 51 没混在同一个桶里
    fail_lines = [line for line in proc.stderr.splitlines() if line.startswith("FAIL ")]
    assert [line.split()[1] for line in fail_lines] == ["version"], (
        f"版本不符时只应 version 失败，实得 FAIL 行：{fail_lines}"
    )


def test_unknown_argument_exits_64():
    """用法错误仍必须退 64 —— 与全项目口径一致。

    这条替代了「把 preflight.sh 塞进 tests/unit/test_exit_codes.py 的 SCRIPTS 列表」：
    那个列表用「完全不传参数」来触发用法错误，而本脚本的默认动作是**跑检查**
    （不传参数不是用法错误），所以它的用法错误入口是「未知参数」。
    口径没变（64 = EX_USAGE），只是触发方式不同。删掉这条 = 本脚本的用法错误没人守。
    """
    proc = subprocess.run(
        [str(SCRIPT), "--nope"], capture_output=True, text=True, timeout=60,
        env=_sourced_env(),
    )
    assert proc.returncode == 64, (
        f"未知参数应退 64，实得 {proc.returncode}；stderr={proc.stderr.strip()[:300]!r}"
    )
    assert proc.stderr.strip(), "用法错误必须写 stderr，不能污染 stdout"
    assert "用法" in proc.stderr or "usage" in proc.stderr.lower(), (
        f"用法错误的 stderr 里既无 '用法' 也无 'usage'：{proc.stderr.strip()[:200]!r}"
    )


def test_help_exits_0_and_prints_usage():
    """--help 退 0（区别于用法错误 64）：它是被明确请求的帮助，不是调用错。"""
    proc = subprocess.run(
        [str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60,
        env=_sourced_env(),
    )
    assert proc.returncode == 0, f"--help 应退 0，实得 {proc.returncode}"
    assert "用法" in proc.stdout or "usage" in proc.stdout.lower(), (
        f"--help 应把用法打到 stdout：{proc.stdout[:200]!r}"
    )


def test_no_arg_is_not_usage_error():
    """无参数必须**跑检查**（退 0/50/51），不得退 64。

    这条守的是「陌生用户直接敲 ./preflight.sh」这个最可能的第一次接触。
    若有人把它改回「无参数=64」，这条会红——而那正是 P5 陌生用户验收会踩的坑。
    """
    proc = subprocess.run(
        [str(SCRIPT)], capture_output=True, text=True, timeout=180, env=_sourced_env(),
    )
    assert proc.returncode in (0, 50, 51), (
        f"无参数应跑检查并退 0/50/51，实得 {proc.returncode}（64 = 被当成用法错误了）\n"
        f"stderr={proc.stderr.strip()[:300]!r}"
    )
