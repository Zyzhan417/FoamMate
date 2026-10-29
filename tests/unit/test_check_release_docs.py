"""文档契约检查器的**变异自测**：证明它有牙。

一个检查器只有"在真文档上退 0"是不够的——那可能只是因为它什么都没查。所以这里每条判据都
配一个**必红变异**：把真实的 `release/` 复制到 `tmp_path`，往副本里注入一处违规，断言检查器
必须退 41 并**指名**抓到的那一处。

判据 1 的路径是相对**仓库根**的，所以副本目录结构被造成 `<tmp>/release` + `<tmp>/scripts`：
`--dir <tmp>/release` 时检查器把 `<tmp>` 当仓库根，`scripts/x.sh` 就去 `<tmp>/scripts/x.sh` 找。
这一点本身也要被证明——`test_release_docs_pass_on_copy` 先跑一遍未改动的副本，必须退 0。

四条必红变异（对应四条判据）：
  1. `scripts/nonexistent_probe.sh`（引用不存在）      → 41
  2. `退 99`（越界退出码）                            → 41
  3. description 撑到 1025 字符（超上限）              → 41
  4. 删掉 SKILL.md 正文里的 `harness`（错误自称）      → 41
另加两条用法错误（64）与一条 `release/*.md` 引用缺失，防判据 1 只查了脚本那一半。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "check_release_docs.py"
REAL_RELEASE = REPO_ROOT / "release"
REAL_SCRIPTS = REPO_ROOT / "scripts"

EX_OK = 0
EX_VIOLATION = 41
EX_USAGE = 64


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """<tmp>/release + <tmp>/scripts：让 --dir 的父目录成为"仓库根"。"""
    _copy_tree(REAL_RELEASE, tmp_path / "release")
    _copy_tree(REAL_SCRIPTS, tmp_path / "scripts")
    return tmp_path


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ---------------------------------------------------------------------------
# 0. 基线：未改动的副本必须过（否则后面的"注入后不过"什么也证明不了）
# ---------------------------------------------------------------------------


def test_checker_exits_zero_on_real_release() -> None:
    """直接在真仓库上跑：退 0，且四条判据都报通过。"""
    proc = run_checker()
    assert proc.returncode == EX_OK, proc.stderr
    assert "文档契约 4/4 通过" in proc.stdout


def test_release_docs_pass_on_copy(sandbox: Path) -> None:
    """同一份内容放在 <tmp>/release 下也必须过：证明"仓库根 = --dir 的父目录"这件事成立。"""
    proc = run_checker("--dir", str(sandbox / "release"))
    assert proc.returncode == EX_OK, proc.stderr
    assert "4/4 通过" in proc.stdout


# ---------------------------------------------------------------------------
# 1. 引用存在性
# ---------------------------------------------------------------------------


def test_nonexistent_script_reference_exits_41(sandbox: Path) -> None:
    """注入一个不存在的脚本名 → 41，且 stderr 指名道姓。"""
    append_line(sandbox / "release" / "QUICKSTART.md", "另外：`scripts/nonexistent_probe.sh` 不存在。")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "nonexistent_probe.sh" in proc.stderr
    assert "QUICKSTART.md" in proc.stderr


def test_nonexistent_release_doc_reference_exits_41(sandbox: Path) -> None:
    """判据 1 的另一半：引用了不存在的 `release/<名>.md` 也要红。"""
    append_line(sandbox / "release" / "SCOPE.md", "详见 `release/NOT-THERE.md`。")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "NOT-THERE.md" in proc.stderr


# ---------------------------------------------------------------------------
# 2. 退出码集合
# ---------------------------------------------------------------------------


def test_unknown_exit_code_exits_41(sandbox: Path) -> None:
    """注入 `退 99` → 41。99 不在任何模块的业务码区间里。"""
    append_line(sandbox / "release" / "SKILL.md", "网格不合格时它退 99，重试即可。")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "99" in proc.stderr
    assert "不在已知集合内" in proc.stderr


# ---------------------------------------------------------------------------
# 3. frontmatter
# ---------------------------------------------------------------------------


def test_description_over_1024_exits_41(sandbox: Path) -> None:
    """把 description 撑到 1025 字符 → 41（1024 是上限，等于上限应放过）。"""
    skill = sandbox / "release" / "SKILL.md"
    lines = skill.read_text(encoding="utf-8").splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("description:"))
    lines[idx] = "description: " + "x" * 1025
    skill.write_text("\n".join(lines) + "\n", encoding="utf-8")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "1025" in proc.stderr
    assert "1024" in proc.stderr


def test_description_exactly_1024_passes(sandbox: Path) -> None:
    """边界：正好 1024 必须放过（否则上限写错了）。"""
    skill = sandbox / "release" / "SKILL.md"
    lines = skill.read_text(encoding="utf-8").splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("description:"))
    lines[idx] = "description: " + "x" * 1024
    skill.write_text("\n".join(lines) + "\n", encoding="utf-8")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_OK, proc.stdout + proc.stderr


def test_missing_frontmatter_exits_41(sandbox: Path) -> None:
    """把 frontmatter 整段删掉 → 41（没有 name/description 的 skill 加载不了）。"""
    skill = sandbox / "release" / "SKILL.md"
    lines = skill.read_text(encoding="utf-8").splitlines()
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    skill.write_text("\n".join(lines[end + 1:]) + "\n", encoding="utf-8")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "frontmatter" in proc.stderr


# ---------------------------------------------------------------------------
# 4. 自称
# ---------------------------------------------------------------------------


def test_missing_harness_word_in_body_exits_41(sandbox: Path) -> None:
    """把正文里所有 harness（含 `$HARNESS` 这种大写形式）换掉 → 41。

    注意 frontmatter 里的 name 不算正文：只改正文也必须能红。
    """
    import re

    skill = sandbox / "release" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    lines = text.splitlines()
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    body = "\n".join(lines[end + 1:])
    assert "harness" in body.lower(), "真实 SKILL.md 正文里必须本来就有 harness"

    replaced = re.sub("harness", "toolkit", body, flags=re.IGNORECASE)
    assert "harness" not in replaced.lower(), "变异必须真的删干净（含大写形式）"
    skill.write_text("\n".join(lines[: end + 1]) + "\n" + replaced + "\n", encoding="utf-8")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "harness" in proc.stderr


def test_forbidden_self_reference_exits_41(sandbox: Path) -> None:
    """正文出现「智能体」→ 41（对外措辞是验收标准的一部分）。"""
    append_line(sandbox / "release" / "SKILL.md", "本智能体会自动完成全部流程。")

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, proc.stdout + proc.stderr
    assert "智能体" in proc.stderr


# ---------------------------------------------------------------------------
# 用法错误 → 64（不给 2：2 是 G2 网格门失败）
# ---------------------------------------------------------------------------


def test_unknown_argument_exits_64() -> None:
    proc = run_checker("--nope")
    assert proc.returncode == EX_USAGE
    assert "用法" in proc.stderr


def test_missing_dir_exits_64(tmp_path: Path) -> None:
    proc = run_checker("--dir", str(tmp_path / "no-such-dir"))
    assert proc.returncode == EX_USAGE
    assert "用法" in proc.stderr or "--dir" in proc.stderr


def test_missing_sibling_doc_is_caught(sandbox: Path):
    """M5：删掉副本里的 SCOPE.md → 必须退 41。

    这条守的是「裸文件名的兄弟文档引用」。为什么必须单独一条：
    文档最初写 `release/QUICKSTART.md`，但发布包里三份文档与 scripts/ 同级、没有 release/ 层，
    所以引用必须是裸文件名。改动后如果检查器只认 `release/<名>.md`，引用计数会从 32 掉到 26
    **而仍然全绿** —— 判据 1 就空转了。这条测试保证那种退化会被抓住。
    """
    (sandbox / "release" / "SCOPE.md").unlink()

    proc = run_checker("--dir", str(sandbox / "release"))

    assert proc.returncode == EX_VIOLATION, (
        f"缺少兄弟文档时应退 {EX_VIOLATION}，实得 {proc.returncode}；"
        f"stderr={proc.stderr[:600]!r}"
    )
    assert "SCOPE.md" in proc.stderr, (
        f"违规信息应点名 SCOPE.md：{proc.stderr[:600]!r}"
    )
