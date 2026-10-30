"""模块 J（`scripts/dev_lib.py`）的 L1 单元测试：**零 OpenFOAM**。

## 为什么这一层能零 OpenFOAM

`prepare` / `check` 只做文件与 JSON；`build` / `verify` 只**调用** `wmake` / `foamRun`，
而这两个命令从 `PATH` 取。所以 L1 用 PATH 前置的假桩替换它们，判的是
「我们怎么调用、怎么解析结果」，不是「OpenFOAM 会不会编译」——后者是 L2（契约层）的事。

## 为什么不能「skip 掉 build / verify」

判据里的每一条（rc 非 0、日志有 `error:`、`.so` 不在位、输出有 `dlopen error`）都是**分支**，
skip 掉等于这些分支没人测，`V3`/`V4` 就退化成「跑过了就算过」。

## 不碰真环境

每条用例都用 `env=` 把 `WM_PROJECT_DIR` / `FOAM_APP` / `FOAM_SRC` / `FOAM_LIBBIN` /
`WM_PROJECT_USER_DIR` / `FOAM_USER_LIBBIN` 全部指到 `tmp_path` 下的伪树。
真 `/opt/openfoam13` 与真 `~/OpenFOAM` 一次都不读、不写（R2）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "dev_lib.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dev"


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


# ---------------------------------------------------------------------------
# T2 · 骨架：用法错误 64、--help 0
# ---------------------------------------------------------------------------


def test_no_args_exits_64_with_stderr():
    """不给任何参数 = 用法错误，必须退 64（全仓统一），且不得往 stdout 写 JSON。

    64 而不是 argparse 默认的 2：2 在 `verify_case.sh` 里已经是 G2 门失败，
    两个语义不同的东西共用一个码会让调用方无法区分「我调错了」与「网格不过」。
    """
    p = subprocess.run([str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 64, p.stderr
    assert p.stderr.strip(), "用法错误必须写 stderr"
    assert p.stdout == "", "用法错误不得往 stdout 写 JSON"


def test_help_exits_0_and_lists_stages():
    p = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0
    for s in ("prepare", "check", "build", "verify"):
        assert s in p.stdout
