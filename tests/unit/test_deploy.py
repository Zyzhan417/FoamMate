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


#: 临时仓库的提交身份。**不写成邮箱字面量**：`scripts/verify_export.py` 的 E3 会扫导出树里
#: 每个文本文件（含 `tests/`），任何邮箱形状都会让 `make_export.sh` 退 80、连带 `test_export.py`
#: 的 module 级夹具报 17 个 error。这里按该文件自己写明的约定（`:114`–`:119`「拼接而非开豁免」）
#: 拼出运行期值——豁免清单会漂移，而拼接之后源码里不存在可匹配的字面量。
_TEST_EMAIL = "probe" + "@" + "example.invalid"


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "probe", "GIT_AUTHOR_EMAIL": _TEST_EMAIL,
        "GIT_COMMITTER_NAME": "probe", "GIT_COMMITTER_EMAIL": _TEST_EMAIL,
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
    }
    proc = subprocess.run([GIT, *args], cwd=str(cwd), capture_output=True, text=True,
                          timeout=120, env=env)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} 失败({proc.returncode}): {proc.stderr}")
    return proc


def _make_origin(tmp_path: Path, version: str = "0.3.0") -> tuple[Path, Path]:
    """造一个 bare 远端 + 它的 seed 工作副本（seed 用来造新提交）。"""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "--initial-branch=main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "--quiet", str(origin), str(seed))
    (seed / "VERSION").write_text(version + "\n", encoding="utf-8")
    (seed / "scripts").mkdir()
    preflight = seed / "scripts" / "preflight.sh"
    preflight.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    preflight.chmod(0o755)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "c1")
    _git(seed, "push", "-q", "origin", "main")
    return origin, seed


def _install(tmp_path: Path, origin: Path, name: str = "harness") -> Path:
    target = tmp_path / name
    proc, payload = _run("--action", "install", "--repo-url", str(origin),
                         "--target", str(target), "--no-preflight")
    assert proc.returncode == 0, proc.stderr
    assert payload["state"] == "installed"
    return target


# ---------------------------------------------------------------------------
# classify：自动更新的唯一判据
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("local", "upstream", "dirty", "local_is_ancestor", "upstream_is_ancestor", "expected"),
    [
        # 两个 SHA 相等：没有更新，工作树脏不脏都不改变这个事实
        ("a", "a", [], False, True, deploy.CURRENT),
        # 本地领先（部署目录里有人 commit 过）：不拒绝、也不动手
        ("a", "b", [], False, True, deploy.AHEAD),
        # 落后但本地有已跟踪改动：能快进也不做
        ("a", "b", ["M scripts/preflight.sh"], True, False, deploy.DIRTY),
        # 落后且干净、可快进：唯一会自动动手的分支
        ("a", "b", [], True, False, deploy.FAST_FORWARD),
        # 历史被重写 / 分叉：两个方向都不是祖先
        ("a", "b", [], False, False, deploy.DIVERGED),
    ],
)
def test_classify_table(local, upstream, dirty, local_is_ancestor, upstream_is_ancestor, expected):
    assert deploy.classify(local, upstream, dirty,
                           local_is_ancestor, upstream_is_ancestor) == expected


# ---------------------------------------------------------------------------
# status：只读
# ---------------------------------------------------------------------------


def test_status_reports_installed_commit_and_version(tmp_path: Path) -> None:
    origin, _seed = _make_origin(tmp_path, version="0.3.0")
    target = _install(tmp_path, origin)

    proc, payload = _run("--action", "status", "--target", str(target))

    assert proc.returncode == 0, proc.stderr
    assert payload["commit"] == _git(target, "rev-parse", "HEAD").stdout.strip()
    assert payload["version"] == "0.3.0"
    assert payload["branch"] == "main"
    assert payload["dirty_tracked"] == []
    assert payload["relation"] is None            # 没给 --fetch：一个字节都不访问网络


def test_status_without_deployment_is_90(tmp_path: Path) -> None:
    proc, payload = _run("--action", "status", "--target", str(tmp_path / "nope"))

    assert proc.returncode == deploy.EX_TARGET
    assert payload["ok"] is False
    assert "install" in payload["reason"]


# ---------------------------------------------------------------------------
# install：克隆式部署 + 幂等 + 拒绝破坏
# ---------------------------------------------------------------------------


def test_install_creates_deployment_at_head(tmp_path: Path) -> None:
    origin, seed = _make_origin(tmp_path)
    target = tmp_path / "harness"

    proc, payload = _run("--action", "install", "--repo-url", str(origin),
                         "--target", str(target), "--no-preflight")

    assert proc.returncode == 0, proc.stderr
    assert payload["state"] == "installed"
    assert payload["commit"] == _git(seed, "rev-parse", "HEAD").stdout.strip()
    assert payload["version"] == "0.3.0"
    assert (target / "scripts" / "preflight.sh").is_file()
    # 部署树里的 origin 必须是 --repo-url，否则 update 会去找一个不存在的远端
    assert _git(target, "remote", "get-url", "origin").stdout.strip() == str(origin)
    # --no-preflight 必须在 payload 里留痕：跳过 ≠ 通过
    assert payload["preflight"] == {"ok": None, "ran": False, "skipped": True,
                                    "rc": None}


def test_install_twice_is_idempotent(tmp_path: Path) -> None:
    origin, _seed = _make_origin(tmp_path)
    target = _install(tmp_path, origin)

    proc, payload = _run("--action", "install", "--repo-url", str(origin),
                         "--target", str(target), "--no-preflight")

    assert proc.returncode == 0
    assert payload["state"] == "already_deployed"
    assert payload["commit"] == _git(target, "rev-parse", "HEAD").stdout.strip()


def test_install_refuses_non_empty_non_deployment(tmp_path: Path) -> None:
    origin, _seed = _make_origin(tmp_path)
    target = tmp_path / "busy"
    target.mkdir()
    (target / "user-data.txt").write_text("mine\n", encoding="utf-8")

    proc, payload = _run("--action", "install", "--repo-url", str(origin),
                         "--target", str(target), "--no-preflight")

    assert proc.returncode == deploy.EX_TARGET
    assert payload["entries"] == ["user-data.txt"]
    assert (target / "user-data.txt").read_text(encoding="utf-8") == "mine\n"  # 一个字节没动


def test_install_refuses_target_inside_source_repo(tmp_path: Path) -> None:
    origin, _seed = _make_origin(tmp_path)

    proc, _payload = _run("--action", "install", "--repo-url", str(origin),
                          "--target", str(REPO / "deploy-probe"), "--no-preflight")

    assert proc.returncode == deploy.EX_TARGET
    assert not (REPO / "deploy-probe").exists()


def test_install_reports_unreachable_remote_as_93(tmp_path: Path) -> None:
    proc, payload = _run("--action", "install",
                         "--repo-url", str(tmp_path / "no-such-repo.git"),
                         "--target", str(tmp_path / "harness"), "--no-preflight")

    assert proc.returncode == deploy.EX_REMOTE
    assert payload["ok"] is False
    assert "clone" in payload["reason"]
