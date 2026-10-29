"""可移植性契约：用户面脚本不得在代码里写死 OpenFOAM 安装前缀（P1 解耦）。

## 为什么这一层必须有

`scripts/find_template.sh` 原来把 `readonly BASH_RC="/opt/openfoam13/etc/bashrc"` 写死，
别人把 OpenFOAM 装在别的前缀上，脚本给出的「下一步」就是一条跑不通的命令——而错误
提示刚好在**环境本来就坏了**的时候出现，读者最容易照着抄。这类缺陷没有行为测试能抓到：
在开发机上写死的路径与推导出来的路径逐字相同。

## 判据（三条，都是可判定的）

1. `test_no_bare_prefix_outside_comments`：7 个用户面脚本逐行扫，含 `/opt/openfoam13`
   的行要么是注释行，要么是**按 `$WM_PROJECT_DIR` 推导、缺省回退**的那一行。
   「推导」的机械判据是该行同时出现 `WM_PROJECT_DIR`——只写死一个常量、不读环境变量的
   行过不去。`find_template.sh` 允许恰好 1 行，且必须落在 `resolve_bash_rc()` 的回退分支内；
   `fix_case.py` 允许恰好 1 行（`os.environ.get("WM_PROJECT_DIR", ...)` 的缺省值）；
   其余文件 0 行。
2. `test_bash_rc_from_wm_project_dir`：`$WM_PROJECT_DIR` 指向一份临时安装树时，
   提示语里必须出现**那棵树**的 bashrc 路径。
3. `test_bash_rc_fallback_when_unset`：`$WM_PROJECT_DIR` 缺失时仍要有可执行的回退提示
   （回退不是妥协：没有它，「没 source」会从一句提示变成一次崩溃，
   `tests/unit/test_exit_codes.py::test_find_template_env_missing_is_64_not_2` 也依赖它）。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
FIND_TEMPLATE = SCRIPTS / "find_template.sh"

PREFIX = "/opt/openfoam13"
BASH = "/usr/bin/bash"

#: 用户面脚本（进发布包的那 6 个 + P2 才出现的 preflight.sh）。不存在者跳过。
USER_FACING = [
    "parse_requirement.py",
    "find_template.sh",
    "new_case.sh",
    "run_case.sh",
    "verify_case.sh",
    "fix_case.py",
    "preflight.sh",
    "msh2d_to_foam.py",
]

#: 回退分支之外，允许「非注释且含前缀」的行数。
#: find_template.sh 的那一处在 resolve_bash_rc() 里单独判（上面已剥离），故这里是 0；
#: fix_case.py 只有 os.environ.get("WM_PROJECT_DIR", "/opt/openfoam13") 那一行。
#: 这两个数不是宽容度，是**上限**——新增的写死前缀会让它变大，必须显式改这一行。
ALLOWED_NON_COMMENT = {
    "find_template.sh": 0,  # 回退值已在 resolve_bash_rc() 内单独判定
    "fix_case.py": 1,  # os.environ.get("WM_PROJECT_DIR", "/opt/openfoam13")
}


def _lines_with_prefix(name: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """返回 (注释行, 非注释行)，元素是 (1-based 行号, 原文)。"""
    path = SCRIPTS / name
    comments: list[tuple[int, str]] = []
    code: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if PREFIX not in line:
            continue
        if line.lstrip().startswith("#"):
            comments.append((i, line))
        else:
            code.append((i, line))
    return comments, code


def _resolve_bash_rc_span(name: str) -> tuple[int, int]:
    """`resolve_bash_rc()` 定义体的行号区间（含函数名行与收尾的 `}`）。"""
    lines = (SCRIPTS / name).read_text(encoding="utf-8").splitlines()
    start = None
    for i, line in enumerate(lines, start=1):
        if re.match(r"^resolve_bash_rc\(\)\s*\{", line):
            start = i
            break
    assert start is not None, f"{name} 里找不到 resolve_bash_rc() 定义"
    for j in range(start + 1, len(lines) + 1):
        if lines[j - 1].rstrip() == "}":
            return start, j
    raise AssertionError(f"{name}:{start} 的 resolve_bash_rc() 没有收尾的 '}}'")


@pytest.mark.parametrize("name", USER_FACING)
def test_no_bare_prefix_outside_comments(name: str):
    """代码里不得出现裸的写死前缀；只允许注释行与按 WM_PROJECT_DIR 推导的回退行。"""
    path = SCRIPTS / name
    if not path.is_file():
        pytest.skip(f"{name} 尚不存在（P2 交付物）")

    _comments, code = _lines_with_prefix(name)

    # find_template.sh 的回退分支是**唯一**的结构性豁免：那一行按定义就是写死的缺省值，
    # 所以它不参与「必须读 WM_PROJECT_DIR」的判据，改由「必须在 resolve_bash_rc() 里」守。
    in_fallback: list[tuple[int, str]] = []
    if name == "find_template.sh":
        lo, hi = _resolve_bash_rc_span(name)
        in_fallback = [(n, l) for n, l in code if lo <= n <= hi]
        code = [(n, l) for n, l in code if not lo <= n <= hi]
        assert len(in_fallback) == 1, (
            f"find_template.sh 的回退分支应恰好有 1 处写死前缀（resolve_bash_rc 的 else），"
            f"实际 {len(in_fallback)}：" + ", ".join(f"{n}:{l.strip()}" for n, l in in_fallback)
        )
        # 回退行本身必须是 else 分支给出的缺省值，而不是被顺手写在 if 分支里。
        assert f"{PREFIX}/etc/bashrc" in in_fallback[0][1], in_fallback[0][1]

    # 1) 其余每一处非注释出现都必须同时读 WM_PROJECT_DIR——写死常量过不去这条。
    for lineno, line in code:
        assert "WM_PROJECT_DIR" in line, (
            f"{name}:{lineno} 含写死前缀且没有按 WM_PROJECT_DIR 推导：{line.strip()!r}"
        )

    # 2) 数量上限：只有「按 WM_PROJECT_DIR 推导、缺省回退」的那一行，别的脚本 0 行。
    expected = ALLOWED_NON_COMMENT.get(name, 0)
    assert len(code) == expected, (
        f"{name} 的非注释出现次数 {len(code)} != 期望 {expected}："
        + ", ".join(f"{n}:{l.strip()}" for n, l in code)
    )


def _run_find_template(env: dict[str, str]):
    return subprocess.run(
        [BASH, str(FIND_TEMPLATE), "--keyword", "cavity"],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def test_bash_rc_from_wm_project_dir(tmp_path: Path):
    """$WM_PROJECT_DIR 指向临时安装树时，提示语必须指向那棵树的 bashrc。"""
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "bashrc").write_text("", encoding="utf-8")
    want = f"{tmp_path}/etc/bashrc"

    proc = _run_find_template(
        {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "WM_PROJECT_DIR": str(tmp_path),
        }
    )

    assert proc.returncode == 64, (
        f"五个搜索根全空时应退 64（用法/前置不满足），实际 {proc.returncode}；"
        f"stderr={proc.stderr!r}"
    )
    assert want in proc.stderr, (
        f"stderr 里没有推导出的 bashrc 路径 {want!r}（说明还在用写死前缀）：{proc.stderr!r}"
    )
    assert "source" in proc.stderr, f"提示语必须给可执行的下一步：{proc.stderr!r}"


def test_bash_rc_fallback_when_unset(tmp_path: Path):
    """$WM_PROJECT_DIR 缺失时仍给回退提示，退 64 不崩溃（不是 2，也不是 127）。"""
    proc = _run_find_template(
        {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
        }
    )

    assert proc.returncode == 64, (
        f"缺 WM_PROJECT_DIR 时应退 64，实际 {proc.returncode}；stderr={proc.stderr!r}"
    )
    assert f"{PREFIX}/etc/bashrc" in proc.stderr, (
        f"缺 WM_PROJECT_DIR 时回退提示丢了：{proc.stderr!r}"
    )
    assert "source" in proc.stderr, f"提示语必须给可执行的下一步：{proc.stderr!r}"
