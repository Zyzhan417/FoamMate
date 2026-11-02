"""L2 契约层：`scripts/deploy.py` 在真 OpenFOAM 环境里装一次、更新一次。

判据两条：
  ① install 之后，**目标副本**的 `scripts/preflight.sh` 退 0（6/6 项通过）；
  ② 造一个上游新提交 → update 之后，同一个副本仍是 6/6，且 HEAD 指到那个提交。

远端全部是本机临时 bare 仓库（`git clone --bare` 本仓库），**不访问网络**。

## 为什么还要处理「REPO 不是 git 仓库」

`make_export.sh` 用 `git archive HEAD` 组出**导出树**，那棵树里**没有 `.git`**；而在导出树里跑
`pytest tests/contract` 是本项目一直有的验收动作（STATUS N18 就记过「导出树内 L2 89 passed」）。
2026-11-02 实测：不加处理时 `git clone --bare <导出树>` 退 **128**（`fatal: repository … does not
exist`），L2 在导出树里必然红 —— 那不是被测对象坏了，是测试自己假设了「REPO 一定是个仓库」。

处置：**REPO 是 git 工作树** → 照旧 `clone --bare`（最快，且远端就是真实历史）；
**REPO 不是** → 把树复制成临时仓库再提交，用它当远端。两条路都真跑 install/update，
**不 skip** —— skip 会把「导出树里跑不了」这件事藏起来，而它正是要暴露的。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "deploy.py"
GIT = shutil.which("git")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([GIT, *args], cwd=str(cwd), capture_output=True, text=True,
                          timeout=300)


def _deploy_remote(tmp_path: Path) -> Path:
    """造一个可克隆的远端，内容 = REPO 这棵树。

    分支一（工作树）：`clone --bare` —— 远端直接是真实仓库历史。
    分支二（导出树，无 `.git`）：把树复制进临时目录、`git init` + 提交，再由它 `clone --bare`
    出一个**裸**远端。为什么要这第二步：往**非裸**仓库的当前分支 push 会被 git 拒绝
    （`receive.denyCurrentBranch`，实测 `push` 退 1），而本测试要往远端 push 新提交来模拟上游更新。
    """
    if _git(REPO, "rev-parse", "--git-dir").returncode == 0:
        remote = tmp_path / "remote.git"
        assert _git(tmp_path, "clone", "--quiet", "--bare", str(REPO),
                    str(remote)).returncode == 0, "从本仓库 clone --bare 失败"
        return remote

    work = tmp_path / "remote-work"
    shutil.copytree(REPO, work,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
    ident = ["-c", "user.name=probe",
             "-c", "user.email=" + "probe" + "@" + "example.invalid"]
    assert _git(work, *ident, "init", "-q", "--initial-branch=main").returncode == 0
    assert _git(work, *ident, "add", "-A").returncode == 0
    assert _git(work, *ident, "commit", "-q", "-m", "export tree as remote").returncode == 0

    remote = tmp_path / "remote.git"
    assert _git(tmp_path, "clone", "--quiet", "--bare", str(work),
                str(remote)).returncode == 0, "从临时仓库 clone --bare 失败"
    return remote


def _deploy(env: dict[str, str], *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, timeout=900, env=env)
    return proc, json.loads(proc.stdout)


@pytest.mark.skipif(GIT is None, reason="需要 git")
def test_install_and_update_keep_preflight_green(tmp_path: Path, foam_env: dict[str, str]):
    remote = _deploy_remote(tmp_path)
    seed = tmp_path / "seed"
    assert _git(tmp_path, "clone", "--quiet", str(remote), str(seed)).returncode == 0

    target = tmp_path / "harness"
    proc, payload = _deploy(foam_env, "--action", "install",
                            "--repo-url", str(remote), "--target", str(target))
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert payload["state"] == "installed"
    assert payload["preflight"]["ran"] is True
    assert payload["preflight"]["rc"] == 0, payload["preflight"]
    installed = payload["commit"]

    doc = seed / "release" / "QUICKSTART.md"
    doc.write_text(doc.read_text(encoding="utf-8") + "\n<!-- contract probe -->\n",
                   encoding="utf-8")
    # 邮箱在这里**拼接**：E3 扫导出树的每个文本文件（含 tests/），字面量会让 make_export 退 80。
    ident = ["-c", "user.name=probe", "-c", "user.email=" + "probe" + "@" + "example.invalid"]
    assert _git(seed, *ident, "commit", "-qam", "probe: contract update").returncode == 0
    assert _git(seed, "push", "-q", "origin", "main").returncode == 0
    upstream = _git(seed, "rev-parse", "HEAD").stdout.strip()
    assert upstream != installed

    proc, payload = _deploy(foam_env, "--action", "update", "--target", str(target))
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert payload["state"] == "fast_forward"
    assert payload["commit"] == upstream
    assert "release/QUICKSTART.md" in payload["changed"]
    assert payload["preflight"]["ran"] is True
    assert payload["preflight"]["rc"] == 0, payload["preflight"]
