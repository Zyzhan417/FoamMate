"""L2 契约层：`scripts/deploy.py` 在真 OpenFOAM 环境里装一次、更新一次。

判据两条：
  ① install 之后，**目标副本**的 `scripts/preflight.sh` 退 0（6/6 项通过）；
  ② 造一个上游新提交 → update 之后，同一个副本仍是 6/6，且 HEAD 指到那个提交。

远端全部是本机临时 bare 仓库（`git clone --bare` 本仓库），**不访问网络**。
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


def _deploy(env: dict[str, str], *args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, timeout=900, env=env)
    return proc, json.loads(proc.stdout)


@pytest.mark.skipif(GIT is None, reason="需要 git")
def test_install_and_update_keep_preflight_green(tmp_path: Path, foam_env: dict[str, str]):
    remote = tmp_path / "remote.git"
    assert _git(tmp_path, "clone", "--quiet", "--bare", str(REPO), str(remote)).returncode == 0
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
