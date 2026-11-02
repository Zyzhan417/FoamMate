"""模块 K（`scripts/deploy.py`）的 L1 单元测试：**零 OpenFOAM、零网络**。

## 这一层判什么

- 用法契约：不给 `--action` 必须退 64 且 stderr 打用法块（与 `batch.py` / `dev_lib.py` 同约定）。
  这条**刻意不写进 `tests/unit/test_exit_codes.py`** 的 `SCRIPTS` 表：那张表是七处平行清单之一，
  为本次增量改它要连带核对 `preflight.sh` 的 `USER_SCRIPTS`、`make_release.sh` 的 `WL_SRC` 等。
- `classify()`：把四个可观测量（本地 SHA / 远端 SHA / 脏文件表 / 两个祖先判定）归约成唯一动作。
  这是「什么情况该自动更新」的唯一判断处，所以必须能逐条断言。
- `status` / `install` / `update` 的**状态机与退出码**：用本机 git 建临时 bare 仓库当远端，
  全部离线。真 OpenFOAM 的那一半在 `tests/contract/test_deploy_e2e.py`（任务 5）。

## 为什么不用 mock 替身

git 的真实行为（`fetch` 写 `FETCH_HEAD`、`merge --ff-only` 在不快进时退 128、
`status --porcelain --untracked-files=no` 忽略 untracked）正是被测对象。
用 `unittest.mock` 替掉 `git` 只会测「我们以为 git 怎么表现」。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy.py"
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(GIT is None, reason="需要 git 才能测部署/更新")


def _load_deploy():
    """直接导入纯函数（不起子进程）。登记 sys.modules 的理由见 test_batch.py 的同名函数。"""
    name = "_deploy_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deploy = _load_deploy()


def _run(*args: str, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, timeout=180, env=env)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:                     # pragma: no cover - 便于报错
        raise AssertionError(f"stdout 不是 JSON: {proc.stdout!r} / stderr={proc.stderr!r}")
    return proc, payload


# ---------------------------------------------------------------------------
# 用法契约（与 batch.py / dev_lib.py 同一个 64）
# ---------------------------------------------------------------------------


def test_no_action_is_usage_error_64(tmp_path: Path) -> None:
    """不传 `--action` → 64，且 stderr 里有用法块（不是只打 `error:`）。"""
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                          timeout=60, cwd=str(tmp_path))
    assert proc.returncode == deploy.EX_USAGE, (
        f"缺 --action 时应退 64，实得 {proc.returncode}；stderr={proc.stderr[:300]!r}"
    )
    assert proc.stderr.strip(), "用法错误时 stderr 为空，用户看不到错在哪"
    assert any(hint in proc.stderr.lower() for hint in ("usage", "用法")), proc.stderr[:300]


def test_help_exits_zero(tmp_path: Path) -> None:
    """`--help` 必须退 0（`test_script_entrypoints.py` 只判「能起来」，这里判「能读」）。"""
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True,
                          text=True, timeout=60, cwd=str(tmp_path))
    assert proc.returncode == 0, proc.stderr[:300]
    for word in ("install", "update", "status", "90", "94"):
        assert word in proc.stdout, f"--help 里缺少 {word}"
