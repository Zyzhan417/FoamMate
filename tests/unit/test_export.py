"""公开导出树的契约：`make_export.sh` + `verify_export.py` 必须真的咬人。

## 为什么这一层不能只在「工作树里跑一遍」就完事

工作树里有 `references/repos/`（第三方副本）、`STATUS.md`、`specs/`、`dist/`、`.hermes/`——
它们不进公开仓库。所以「工作树里全绿」与「导出树里全绿」是两件事，本项目已经两次栽在
「仓库里能跑、解出来就崩」上（N7 第 14 条，`batch.py` 曾 import 只存在于仓库里的
`bench/judge.py`）。这一层验的是**要发布的那棵树**。

## 为什么每条门都要一条变异用例

绿只在「改坏就红」时才算证据（本项目对 `G-DOC-1`/`G-BENCH-1` 一直是这个口径）。
`test_export_tree_passes_all_six_gates` 证明六道门在同一棵树上全绿；
下面 8 条 `test_*_catches_*` 证明**每一类失效都能被对应门抓到**，且抓到时退出码是 80、
消息里点名了那个文件。只做前者，等于允许「六道门全被改哑」也能绿。

变异一律在 `tmp_path` 的**副本**上做，绝不改 `dist/export`（否则下一次跑测试会被自己的脏文件绊倒）。

## 为什么这里有一条递归守卫

`verify_export.py` 的 E4 会在导出树里跑 `pytest tests/unit`，而本文件就在 `tests/unit` 里，
它又会调 `make_export.sh` —— 不设标记就是无限递归。守卫的口径是：**已经在验这棵树了，
再验一次不增加信息**（`VERIFY_EXPORT_ACTIVE=1` 时本模块整体 skip，由 E4 那一次调用覆盖）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("VERIFY_EXPORT_ACTIVE") == "1",
    reason="正处于 verify_export.py 的 E4 内部：本文件已在导出树里跑过一遍，不重复",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKE_EXPORT = REPO_ROOT / "scripts" / "make_export.sh"
VERIFY_EXPORT = REPO_ROOT / "scripts" / "verify_export.py"
BASH = "/usr/bin/bash"

EX_VIOLATION = 80
EX_USAGE = 64


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


@pytest.fixture(scope="module")
def export_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """真跑一次 assemble 器（跳过 E4 的 pytest），得到一棵可复用的导出树。"""
    dest = tmp_path_factory.mktemp("export") / "tree"
    proc = _run([BASH, str(MAKE_EXPORT), "--dest", str(dest), "--skip-tests"])
    assert proc.returncode == 0, (
        f"make_export.sh 退 {proc.returncode}，期望 0\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert dest.is_dir(), f"没有产出导出树：{dest}"
    return dest


def _mutated_copy(export_tree: Path, tmp_path: Path) -> Path:
    """导出一份完整副本供变异用（不污染 module 级 fixture）。"""
    dst = tmp_path / "mut"
    shutil.copytree(export_tree, dst)
    return dst


def _verify(tree: Path, gates: str = "", skip_tests: bool = True) -> subprocess.CompletedProcess[str]:
    """跑校验器。`skip_tests=True` 时跳过 E4 的 pytest（变异用例只需要看某一门，用它提速）。

    正面用例（`test_export_tree_passes_all_six_gates`）**不跳过**：它的主张是「六道门都真的跑过」，
    跳过 E4 的 pytest 就只剩「语法能过」，而 N7 第 14 条的缺陷恰恰是语法能过、跑起来才崩。
    """
    cmd = [sys.executable, str(VERIFY_EXPORT), "--tree", str(tree)]
    if skip_tests:
        cmd.append("--skip-tests")
    if gates:
        cmd += ["--gates", gates]
    return _run(cmd, timeout=900)


# ---------------------------------------------------------------------------
# 用法契约
# ---------------------------------------------------------------------------
def test_make_export_without_args_exits_64():
    """不传 --dest 必须是用法错误：不给默认值，避免在仓库根静默产出导出树。"""
    proc = _run([BASH, str(MAKE_EXPORT)], timeout=120)
    assert proc.returncode == EX_USAGE, f"实得 {proc.returncode}；stderr={proc.stderr[:300]!r}"
    assert proc.stderr.strip(), "用法错误必须写 stderr"


def test_verify_export_without_args_exits_64():
    proc = _run([sys.executable, str(VERIFY_EXPORT)], timeout=120)
    assert proc.returncode == EX_USAGE, f"实得 {proc.returncode}；stderr={proc.stderr[:300]!r}"


def test_verify_export_rejects_missing_tree(tmp_path: Path):
    proc = _verify(tmp_path / "does-not-exist")
    assert proc.returncode == EX_USAGE, f"--tree 不存在时应退 64，实得 {proc.returncode}"


# ---------------------------------------------------------------------------
# 正面：整棵树六道门全过（含 E4 真跑 pytest）
# ---------------------------------------------------------------------------
def test_export_tree_passes_all_six_gates(export_tree: Path):
    proc = _verify(export_tree, skip_tests=False)
    assert proc.returncode == 0, (
        f"导出树有违规（退 {proc.returncode}）\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "RESULT: EXPORT OK" in proc.stdout
    for gate in ("[E1]", "[E2]", "[E3]", "[E4]", "[E5]", "[E6]"):
        assert gate in proc.stdout, f"输出里没有 {gate} 汇总行：六道门必须各自打印自己的样本数"


def test_export_tree_excludes_internal_material(export_tree: Path):
    """工作树里的内部材料一个都不能出现在导出树上。"""
    for rel in ("STATUS.md", "specs", "dist", ".hermes", "references/repos",
                "references/external/anthropic-agent-skills.md", "bench/runs", "runs"):
        assert not (export_tree / rel).exists(), f"{rel} 不该出现在导出树里"

    for rel in ("README.md", "LICENSE", "AGENTS.md", "VERSION", "requirements-dev.txt",
                "scripts/make_export.sh", "scripts/verify_export.py",
                "references/registry.csv", "references/external/INDEX.md",
                "bench/preregistration.md", "tests/unit", "tests/contract"):
        assert (export_tree / rel).exists(), f"导出树缺少 {rel}"

    tasks = sorted((export_tree / "bench" / "tasks").glob("T*.yaml"))
    assert len(tasks) == 12, f"bench/tasks 应带 12 个任务 yaml，实得 {len(tasks)}"


def test_export_tree_has_no_self_home_path(export_tree: Path):
    """E3 的正面：导出树里不该再有**本机**家目录前缀。

    只判本机前缀、不判「任何 /home/」：`references/02-architectures.md` 里有对 autofoam
    源码的逐字引用 `OPENFOAM_BASHRC = "/home/nvidia/..."`，那是作者机器、不是我们的，
    改掉它会违反 R1 的「引用不许改写」。判据口径由 E3 的实现决定，这条测试只跟它对齐。
    """
    proc = _run(["grep", "-rlF", _HOME, str(export_tree)], timeout=120)
    assert proc.returncode == 1, f"导出树里仍有本机家目录前缀 {_HOME}：{proc.stdout}"


# ---------------------------------------------------------------------------
# 反面：每一类失效都必须被抓到（变异自证）
# ---------------------------------------------------------------------------
def test_e1_catches_unknown_top_level_dir(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    (tree / "notes").mkdir()
    (tree / "notes" / "todo.md").write_text("草稿\n", encoding="utf-8")

    proc = _verify(tree, "E1")
    assert proc.returncode == EX_VIOLATION
    assert "notes" in proc.stderr


def test_e1_catches_status_md(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    (tree / "STATUS.md").write_text("# 接续点\n", encoding="utf-8")

    proc = _verify(tree, "E1")
    assert proc.returncode == EX_VIOLATION
    assert "STATUS.md" in proc.stderr


def test_e1_catches_missing_license(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    (tree / "LICENSE").unlink()

    proc = _verify(tree, "E1")
    assert proc.returncode == EX_VIOLATION
    assert "LICENSE" in proc.stderr


def test_e2_catches_missing_script_reference(export_tree: Path, tmp_path: Path):
    """文档引用导出树里不存在的脚本 —— 这正是「工作树里看着对、读者照着抄就死路」。"""
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + "\n见 `scripts/no_such_script.py:1`。\n", encoding="utf-8")

    proc = _verify(tree, "E2")
    assert proc.returncode == EX_VIOLATION
    assert "no_such_script.py" in proc.stderr


def test_e2_catches_line_out_of_range(export_tree: Path, tmp_path: Path):
    """行号越界：编辑/翻译上游文档后，下游 `path:line` 静默失效的形态。"""
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + "\n见 `bench/preregistration.md:999999`。\n", encoding="utf-8")

    proc = _verify(tree, "E2")
    assert proc.returncode == EX_VIOLATION
    assert "行号越界" in proc.stderr


def test_e2_catches_broken_markdown_link(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + "\n见 [示例](release/NO-SUCH-DOC.md)。\n", encoding="utf-8")

    proc = _verify(tree, "E2")
    assert proc.returncode == EX_VIOLATION
    assert "NO-SUCH-DOC.md" in proc.stderr


def test_e2_catches_external_ref_without_sha(export_tree: Path, tmp_path: Path):
    """第三方引用：仓库名不在 registry.csv（或没有 sha）→ 不可复现，等于无法追溯。"""
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + "\n见 `references/repos/never-registered/foo.C:12`。\n", encoding="utf-8")

    proc = _verify(tree, "E2")
    assert proc.returncode == EX_VIOLATION
    assert "never-registered" in proc.stderr


#: 变异用的「本机标识」在运行时拼出来，不在源码里写成字面量——否则本文件自己会被 E3 判红
#: （它就在导出树里）。这不是躲检查：判的是**导出树里有没有真的出现这个串**，拼出来的串
#: 只存在于 tmp_path 的副本里。
_HOME = "/home" + "/" + ("dr" + "zy")
_MAIL = "somebody" + "@" + "example.com"
#: 学号同理在运行时拼出来。**这条判据原先没有变异用例**——只测「合法输入能过」等于没测，
#: 所以它长期恒绿的原因（字面量恰好不构成词边界）一直没被发现。
_STUDENT_ID = "2302" + "38104"
#: 别人的家目录：E3 只记 note、不判违规（逐字引用第三方源码时会出现），所以另立一条用例守它。
_FOREIGN = "/home" + "/" + "nvidia"


def test_e3_catches_local_home_path(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + f"\n实测见 `{_HOME}/work/log.txt`。\n", encoding="utf-8")

    proc = _verify(tree, "E3")
    assert proc.returncode == EX_VIOLATION
    assert _HOME in proc.stderr, f"E3 必须点名命中的前缀：{proc.stderr[:400]}"


def test_e3_allows_foreign_home_as_note(export_tree: Path, tmp_path: Path):
    """别人的 `/home/<user>`（第三方源码逐字引用）不判违规，只在 note 里报出来。"""
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + f"\n第三方源码里写死 `{_FOREIGN}/miniconda3/etc/bashrc`。\n", encoding="utf-8")

    proc = _verify(tree, "E3")
    assert proc.returncode == 0, f"不该判违规：{proc.stderr[:400]}"
    assert "nvidia" in proc.stdout, "至少要打印出来让人看见（note），不能静默放过"


def test_e3_catches_email(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + f"\n联系 {_MAIL}。\n", encoding="utf-8")

    proc = _verify(tree, "E3")
    assert proc.returncode == EX_VIOLATION
    assert "邮箱" in proc.stderr


def test_e3_catches_student_id(export_tree: Path, tmp_path: Path):
    """学号出现在导出树里必须判违规（这条判据原先没有变异用例，恒绿是偶然）。"""
    tree = _mutated_copy(export_tree, tmp_path)
    readme = tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8")
                      + f"\n作者学号 {_STUDENT_ID}。\n", encoding="utf-8")

    proc = _verify(tree, "E3")
    assert proc.returncode == EX_VIOLATION, f"学号应被判违规：{proc.stdout[-400:]}"
    assert "学号" in proc.stderr
    assert _STUDENT_ID in proc.stderr, "必须点名命中的串，否则读者不知道删什么"


def test_e5_catches_third_party_source(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    (tree / "references" / "repos" / "some-repo").mkdir(parents=True)
    (tree / "references" / "repos" / "some-repo" / "foo.C").write_text("// vendor\n", encoding="utf-8")

    proc = _verify(tree, "E5")
    assert proc.returncode == EX_VIOLATION
    assert "references/repos" in proc.stderr


def test_e5_catches_external_article(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    (tree / "references" / "external" / "some-article.md").write_text("别人文章的正文\n", encoding="utf-8")

    proc = _verify(tree, "E5")
    assert proc.returncode == EX_VIOLATION
    assert "some-article.md" in proc.stderr


def test_e6_catches_oversized_file(export_tree: Path, tmp_path: Path):
    tree = _mutated_copy(export_tree, tmp_path)
    big = tree / "tests" / "big.bin"
    big.write_bytes(b"0" * 1_100_000)

    proc = _verify(tree, "E6")
    assert proc.returncode == EX_VIOLATION
    assert "1 MB" in proc.stderr or "big.bin" in proc.stderr
