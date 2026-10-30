"""发布包内容契约：包内文件集合**逐字等于**白名单映射结果（spec AC6 / D5）。

## 为什么这层必须是「相等」而不是「包含」

包含式判据（`assert WANT <= GOT`）在第一次往 `release/` 多放一份草稿后就永久为真，
且没有人会注意。发布包里于是慢慢长出一个 `bench/`、一份 `AGENTS.md`，
而 `README.md` 里「对外交付物」的描述从那一刻开始撒谎——**没有任何东西会红**。
所以这里的期望集合是**硬编码**的：如果从 `make_release.sh` 里读白名单，
脚本漏掉一个文件时期望集合会跟着漏，判据就退化成「脚本等于脚本」。

## 为什么期望集合里 `release/*.md` 是平铺的

`release/SKILL.md|QUICKSTART.md|SCOPE.md` 里的引用全部是裸文件名与 `scripts/<名>`，
它们默认「三份 md 与 scripts/ 同级」。包里保留 `release/` 这一层就会让文档互相指向
不存在的路径——这不是洁癖，是包能不能用的分界。

## 变异口径（T3.7）

绿只在「改坏就红」时才算证据：`test_extra_file_in_release_exits_60` 往真实的
`release/` 里临时塞一个未收录文件，组装器必须退 60 并**点名**它；`finally` 里删掉，
不许把脏文件留在仓库里。
"""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKE_RELEASE = REPO_ROOT / "scripts" / "make_release.sh"

EX_OK = 0
EX_WHITELIST = 60
EX_USAGE = 64

#: 白名单的映射结果（包内相对路径），**硬编码**，不从脚本读。
PACKAGE_SCRIPTS = {
    "scripts/preflight.sh",
    "scripts/parse_requirement.py",
    "scripts/find_template.sh",
    "scripts/new_case.sh",
    "scripts/run_case.sh",
    "scripts/verify_case.sh",
    "scripts/fix_case.py",
    "scripts/batch.py",
    "scripts/msh2d_to_foam.py",
    "scripts/dev_lib.py",
}
PACKAGE_DOCS = {"SKILL.md", "QUICKSTART.md", "SCOPE.md"}

#: 禁用路径：前缀（整棵目录）与裸名（根目录文件）。
FORBIDDEN_PREFIX = (
    "bench/",
    "references/",
    "tests/",
    "specs/",
    "release/",
    ".git/",
    ".hermes/",
    "dist/",
    "__pycache__/",
)
FORBIDDEN_EXACT = {
    "AGENTS.md",
    "STATUS.md",
    "README.md",
    "scripts/check_contracts.py",
    "scripts/status_snapshot.py",
    "scripts/verify_references.sh",
    "scripts/check_release_docs.py",
    "scripts/make_release.sh",
}


def expected_files() -> set[str]:
    """白名单映射后的文件全集；LICENSE 只在仓库根真有它时才计入。"""
    files = {"VERSION", *PACKAGE_DOCS, *PACKAGE_SCRIPTS}
    if (REPO_ROOT / "LICENSE").is_file():
        files.add("LICENSE")
    return files


def version() -> str:
    return (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def package_root(dest: Path) -> Path:
    return dest / f"foam-mate-{version()}"


def relpaths(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def run_make_release(*args: str) -> subprocess.CompletedProcess[str]:
    assert MAKE_RELEASE.is_file(), f"组装器不存在: {MAKE_RELEASE}"
    return subprocess.run(
        [str(MAKE_RELEASE), *args],
        capture_output=True,
        text=True,
        timeout=300,
    )


def build(tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    proc = run_make_release("--dest", str(tmp_path), "--no-tar")
    assert proc.returncode == EX_OK, f"RC={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    root = package_root(tmp_path)
    assert root.is_dir(), f"没有生成包目录: {root}"
    return proc, root


# ---------------------------------------------------------------------------
# a) 基本可用
# ---------------------------------------------------------------------------


def test_no_tar_builds_package(tmp_path: Path) -> None:
    """`--dest <tmp> --no-tar` → RC=0，且 stdout 报出包路径与文件数。"""
    proc, root = build(tmp_path)

    assert str(root) in proc.stdout
    assert f"{len(expected_files())} 个" in proc.stdout
    assert not (tmp_path / f"foam-mate-{version()}.tar.gz").exists(), "--no-tar 不该打归档"


# ---------------------------------------------------------------------------
# b) 文件集合逐字相等（本条是整个 AC6 的核心）
# ---------------------------------------------------------------------------


def test_file_set_equals_whitelist(tmp_path: Path) -> None:
    """包内相对路径排序后必须与硬编码的期望集**完全相等**（多一个 / 少一个都红）。"""
    _, root = build(tmp_path)

    got = set(relpaths(root))
    want = expected_files()

    assert got - want == set(), f"包内多出白名单外的文件: {sorted(got - want)}"
    assert want - got == set(), f"包内缺少白名单要求的文件: {sorted(want - got)}"
    assert len(relpaths(root)) == len(want), f"文件数不符: 实际 {len(relpaths(root))} / 期望 {len(want)}"


def test_docs_are_flattened_not_under_release(tmp_path: Path) -> None:
    """三份入口文档必须平铺在包根：`SKILL.md` 存在，`release/SKILL.md` 不存在。"""
    _, root = build(tmp_path)

    for name in PACKAGE_DOCS:
        assert (root / name).is_file(), f"包根缺少 {name}（文档必须在包根平铺）"
        assert not (root / "release" / name).exists(), f"包里出现了 release/ 这一层: release/{name}"
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == version()


# ---------------------------------------------------------------------------
# c) 禁用路径一个都不能在包里
# ---------------------------------------------------------------------------


def test_no_forbidden_paths(tmp_path: Path) -> None:
    """遍历包内每个相对路径，断言不含任何禁用前缀 / 裸名 / 编译缓存。"""
    _, root = build(tmp_path)

    bad: list[str] = []
    for rel in relpaths(root):
        if any(rel.startswith(prefix) for prefix in FORBIDDEN_PREFIX):
            bad.append(rel)
        elif rel in FORBIDDEN_EXACT:
            bad.append(rel)
        elif rel.endswith(".pyc") or "/__pycache__/" in rel:
            bad.append(rel)

    assert bad == [], f"包内出现禁用路径: {bad}"


# ---------------------------------------------------------------------------
# d) tar：顶层唯一目录，内容与 b) 相同
# ---------------------------------------------------------------------------


def test_tar_top_level_is_single_package_dir(tmp_path: Path) -> None:
    """不打 `--no-tar`：归档解包后顶层**只有一个**目录，其内文件集合与白名单相同。"""
    proc = run_make_release("--dest", str(tmp_path))
    assert proc.returncode == EX_OK, proc.stdout + proc.stderr

    tarball = tmp_path / f"foam-mate-{version()}.tar.gz"
    assert tarball.is_file(), f"没有生成归档: {tarball}"

    with tarfile.open(tarball) as tf:
        names = tf.getnames()
        assert all(not n.startswith("/") for n in names), f"归档里有绝对路径: {names[:3]}"
        assert all(not n.startswith("./") for n in names), f"归档条目以 ./ 开头: {names[:3]}"
        tops = {n.split("/", 1)[0] for n in names}
        assert tops == {f"foam-mate-{version()}"}, f"归档顶层不唯一: {sorted(tops)}"
        tf.extractall(tmp_path / "unpacked", filter="data")

    unpacked = tmp_path / "unpacked"
    assert [p.name for p in unpacked.iterdir()] == [f"foam-mate-{version()}"]
    assert set(relpaths(package_root(unpacked))) == expected_files()


# ---------------------------------------------------------------------------
# e) 幂等：连续两次都 0，第二次集合不变
# ---------------------------------------------------------------------------


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    """先删后建：连跑两次都 RC=0，包内文件集合不变（不累积、不嵌套）。"""
    _, root_first = build(tmp_path)
    first = relpaths(root_first)

    _, root_second = build(tmp_path)
    second = relpaths(root_second)

    assert first == second, f"第二次组装改变了文件集合: {sorted(set(second) - set(first))} / {sorted(set(first) - set(second))}"
    assert not (root_second / f"foam-mate-{version()}").exists(), "包内出现了嵌套的同名目录（没先删后建）"


# ---------------------------------------------------------------------------
# f) 变异：白名单外偷放一个文件 → 必须 60（T3.7）
# ---------------------------------------------------------------------------


def test_extra_file_in_release_exits_60(tmp_path: Path) -> None:
    """往 `release/` 临时塞一个未收录文件 → 组装器必须退 60 并点名它。

    只复制白名单点名的文件的组装器，在复制阶段**看不见**多余文件——所以这条变异
    专门验证「源侧完整性检查」真的存在。没有它，往 release/ 里丢草稿会被静默忽略，
    而测试仍然全绿，等于这条判据什么都没守。
    """
    probe = REPO_ROOT / "release" / "_probe_extra.md"
    assert not probe.exists(), f"探测文件已存在，先清理: {probe}"
    probe.write_text("变异探测：这个文件不在白名单里，组装必须退 60。\n", encoding="utf-8")
    try:
        proc = run_make_release("--dest", str(tmp_path), "--no-tar")
    finally:
        probe.unlink(missing_ok=True)

    assert proc.returncode == EX_WHITELIST, (
        f"release/ 里多出未收录文件时应退 {EX_WHITELIST}，实得 {proc.returncode}；"
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "_probe_extra.md" in proc.stderr, f"报错没有点名那个文件: {proc.stderr!r}"
    assert not package_root(tmp_path).exists(), "失败的组装不该在 dest 留下半个包（它会看起来能发）"


def test_probe_file_is_cleaned_up() -> None:
    """变异测试的收尾判据：仓库里不许留下探测文件。"""
    assert not (REPO_ROOT / "release" / "_probe_extra.md").exists()


# ---------------------------------------------------------------------------
# 用法错误：无参数 / 未知参数 → 64（默认 dest 不能靠"忘了传参"生效）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["--nope"], ["--dest"]])
def test_usage_errors_exit_64(argv: list[str]) -> None:
    proc = run_make_release(*argv)

    assert proc.returncode == EX_USAGE, (
        f"{argv} 应退 {EX_USAGE}（用法错误），实得 {proc.returncode}；stderr={proc.stderr[:200]!r}"
    )
    assert "用法" in proc.stderr
    assert proc.stdout == "", f"用法错误不许污染 stdout: {proc.stdout!r}"
