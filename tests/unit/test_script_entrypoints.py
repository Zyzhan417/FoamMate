"""入口契约：`scripts/` 下每个带 shebang 的脚本都必须能**被直接执行**。

## 为什么这一层必须有

这是实测抓到的真实缺陷（2026-10-28）：`scripts/parse_requirement.py` 有 shebang
`#!/usr/bin/env python3`，但**没有可执行位**。它的 16 项单元测试全绿，全部通过
（测试里用 `sys.executable` 调用解释器），所以没有一条测试发现
`./scripts/parse_requirement.py` 会 `Permission denied`（退出码 126）。

问题不在某一条测试写错了，而在**测试只验证了「行为」，没验证「调用方式」**。
只要有人（或另一个模块、或文档里的命令行）按 README 那样直接执行，就会失败。

## 判据为什么是「按类」而不是「按文件」

只给 `parse_requirement.py` 补一个 `+x` 是修一个点；同一个缺口会在下一个新脚本上重现
（实测 `status_snapshot.py` 当时也缺）。所以判据遍历整个 `scripts/`：
**凡是第一行是 shebang 的文件，就必须可执行**。新增脚本自动被这条覆盖，不需要记得加测试。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _shebang_files() -> list[Path]:
    """scripts/ 下第一行以 `#!` 开头的普通文件（跳过 __pycache__ 等目录）。"""
    out: list[Path] = []
    for p in sorted(SCRIPTS.iterdir()):
        if not p.is_file():
            continue
        try:
            with p.open("rb") as fh:
                first = fh.readline(200)
        except OSError:                      # 读不了的文件不归这条测试管
            continue
        if first.startswith(b"#!"):
            out.append(p)
    return out


def test_scripts_dir_has_shebang_files():
    """前置：真的扫到了脚本，否则下面两条会「因为没有文件」而空跑成绿。"""
    files = _shebang_files()
    assert len(files) >= 6, f"只扫到 {len(files)} 个带 shebang 的脚本，预期 >=6：{[p.name for p in files]}"


@pytest.mark.parametrize("path", _shebang_files(), ids=lambda p: p.name)
def test_shebang_script_is_executable(path: Path):
    """带 shebang 的脚本必须有可执行位。

    没有可执行位时 `./scripts/x.py` 退 126（Permission denied），而用 `bash x.sh`
    或 `python3 x.py` 调用却能过——这正是缺陷能躲过 44 项测试的原因。
    """
    mode = path.stat().st_mode
    assert os.access(path, os.X_OK), (
        f"{path.name} 有 shebang 但不可执行（mode={oct(mode & 0o777)}）；"
        f"直接执行会 Permission denied（126）。修法：chmod +x {path.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("path", _shebang_files(), ids=lambda p: p.name)
def test_shebang_script_starts_directly(path: Path):
    """直接执行（不经解释器）必须真能启动，而不是只在 chmod 层面「看起来可执行」。

    为什么单独一条：`chmod +x` 能过上面那条，但如果 shebang 的解释器不存在
    （例如 `#!/usr/bin/env python3` 而 PATH 里没有 python3），直接执行仍失败，
    且报错形态与「脚本本身有 bug」难以区分。

    **判据只看「能不能起来」，不看退出码是多少。** 这么定是因为一开始我把判据写成
    「`--help` 必须退 0 或 2」，结果 `verify_references.sh` 红了一次——它没实现
    `--help`，直接把九道门跑了一遍（未 source bashrc 时 G-BENCH-1 退化，退 1）。
    那**不是缺陷**：本测试的职责是可执行性，不是「每个脚本都必须实现 `--help`」。
    把职责写进判据里会让测试去要求一件与它无关的事。

    所以判据是：退出码不得是 126（无权限）或 127（解释器/命令不存在），
    且 stderr 里不得出现 Permission denied / bad interpreter 这类「起不来」的证据。
    """
    proc = subprocess.run(
        [str(path), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )

    assert proc.returncode not in (126, 127), (
        f"直接执行 {path.name} 退出 {proc.returncode}（126=无权限 / 127=找不到解释器）。"
        f"stderr={proc.stderr.strip()[:300]!r}"
    )

    broken = ("Permission denied", "bad interpreter", "No such file or directory")
    hit = [t for t in broken if t in proc.stderr]
    assert not hit, (
        f"{path.name} 起不来（stderr 含 {hit}）：{proc.stderr.strip()[:300]!r}"
    )
