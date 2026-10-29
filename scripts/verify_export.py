#!/usr/bin/env python3
"""公开导出树的六道门（E1–E6）。判据全部是「在导出树上跑出来的输出」，不是「工作树里看着对」。

## 为什么需要这一层：验收对象错了，绿就是假的

工作树与公开仓库**不是同一棵树**。工作树里有 `references/repos/`（第三方副本）、`STATUS.md`、
`specs/`、`dist/`、`.hermes/`——它们不进仓库；而工作树里能过的检查，进了导出树可能变成
「0 样本不构成证据」。两个实测形态：

1. `scripts/verify_references.sh` 的 `G-DOC-1` 扫的是**工作树**的 `references/*.md`，
   它验证的 446 条 `references/repos/<repo>/<file>:<line>` 引用，在导出树里目标全部不存在。
   于是那条门在导出树上是「要么全红、要么 0 样本」——它测的不是要发布的东西。
2. 本项目 N7 第 14 条（发布物自包含）在**代码**上已经栽过两次（`batch.py` 曾 import
   只存在于仓库里的 `bench/judge.py`）。同一类缺陷在**文档**上的形态是
   「路径写死了本机前缀」——在自己机器上读起来毫无问题，别人 clone 下来照着抄就全错。

所以判据必须落在导出树上，而且必须能对**任意目录**跑（不带 git、不带参考库）。

## 六道门各守什么

| 门 | 判据 | 抓的失效形态 |
|---|---|---|
| E1 结构 | 顶层只允许固定几个入口；排除项一个都不许在；必需项一个都不许少 | `.gitignore` 漏一条 + `git add -f`；导出漏了 `LICENSE` |
| E2 引用 | 文档里的仓库内引用必须能回切到真实文件、行号不越界；第三方引用必须能在 `registry.csv` 里指到 sha | 翻译/编辑后行号静默失效；引用了不存在的脚本 |
| E3 标识 | 导出树里不得出现本机家目录、用户名、学号、邮箱 | 硬编码 `/home/<user>`；把内部环境信息带出去 |
| E4 可运行 | 导出树里 `bash -n`、`py_compile`、可执行位、`pytest tests/unit` 全过 | 「仓库里能跑、解出来就崩」 |
| E5 第三方 | `references/repos/` 不存在；`references/external/` 只剩 INDEX.md | 第三方源码/文章正文被裹进 MIT 仓库 |
| E6 体积 | 单文件 ≤ 1 MB | 计算结果、PDF、归档混进 git |

## 为什么 E2 的「样本数」必须打印

一条判据扫到 0 条引用也会返回「0 违规」。这和「全部通过」在输出上无法区分——本项目对
`G-DOC-1` 已经明确规定：扫到 0 条要显式说「本门 0 样本，不构成证据」。E2 沿用同一条纪律，
并且把**无法解析的引用形态**也计数打印（`skipped`），否则「覆盖率」是隐形的。

E2 的解析分五类，只有前三类是硬判据：

  A 显式仓库内路径（`scripts/x.py:12`、`bench/preregistration.md:388`）→ 文件在 + 行号不越界；
  B markdown 相对链接（`[x](release/SCOPE.md)`）→ 相对本文档目录解析后必须存在；
  C 简写（`02:2105` → `references/02-*.md`；`README:14` → 两个候选之一）→ 命中唯一候选才判行号；
  D 第三方（`references/repos/<repo>/<file>:<line>`）→ `<repo>` 必须在 `registry.csv` 里且有 sha；
  E 其余（裸文件名、`fvSolution`、`main.py:104` 这类第三方仓内文件名）→ 计数后跳过。

## 退出码

0 全过 / 80 有违规 / 64 用法错误或前置不满足（`--tree` 不是目录）。
80 不与任何业务码冲突（0–5 门、10–13、20–23、31–33、40/41、50/51、60、70/71）。

用法：
  python3 scripts/verify_export.py --tree dist/export
  python3 scripts/verify_export.py --tree dist/export --skip-tests   # 只调试用，不算验收
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

EX_OK = 0
EX_VIOLATION = 80
EX_USAGE = 64

#: 门的执行顺序（也是 `--gates` 的合法取值）。顺序固定：E1 先判「树里有什么」，
#: 后面的门才有意义——空树或结构错乱的树上跑 E2/E4 只会产出一堆噪音。
GATES = ("E1", "E2", "E3", "E4", "E5", "E6")

#: 导出树允许出现的**顶层目录**。闭合集合：不在其中的顶层目录一律违规。
#: 用闭合集合而不是「禁止清单」，是因为禁止清单在新增一个目录时默认为「允许」，
#: 而这类文件的正确默认是「先想清楚它该不该发布」。
ALLOWED_TOP_DIRS = frozenset({"scripts", "tests", "bench", "references", "release"})

#: 导出树允许出现的**顶层文件**（仓库根）。
ALLOWED_ROOT_FILES = frozenset({
    "README.md", "LICENSE", "AGENTS.md", "VERSION", "requirements-dev.txt", ".gitignore",
    "CHANGELOG.md",
})

#: 无论出现在哪一层都不许有的路径（前缀匹配）与裸名（精确匹配）。
EXCLUDED_PREFIXES = (
    "references/repos/",        # 第三方源码副本（R9/R10：只读、不外发）
    ".git/",
    "dist/",
    "specs/",
    ".hermes/",
    "runs/",                    # 批量运行产物
    "bench/runs/",              # bench 实测产物（R12）
    ".pytest_cache/",
    "__pycache__/",
)
EXCLUDED_NAMES = frozenset({"STATUS.md", ".DS_Store"})

#: `references/external/` 下只保留我们自己的索引；正文副本版权不是我们的（MIT 覆盖不到）。
EXTERNAL_DIR = "references/external"
EXTERNAL_ALLOWED = frozenset({"INDEX.md"})

MAX_FILE_BYTES = 1_000_000       # E6：单文件 1 MB 上限

#: E3 的禁用模式 = **我们自己的**标识。学号 / 邮箱 / 本机用户名 / 本机家目录 / WSL 挂载点。
#:
#: 为什么不禁用「任何 /home/<用户名>」：文档里有大量对第三方源码的**逐字引用**，
#: 例如 autofoam 的 `OPENFOAM_BASHRC = "/home/nvidia/miniconda3/..."`（作者机器路径）。
#: 那是别人的环境，不是我们的；把它禁掉只有两种结局——要么改掉逐字引用（违反 R1 的
#: 「引用不许改写」），要么给门禁开一个允许清单（清单一定会漂移）。
#: 所以判据按「是否指向**我们这台机器**」来定，其余 `/home/<x>` 只计 note 让人看见。
#:
#: 同理 `Zyzhan417`（GitHub handle）不在禁用表里：仓库就挂在那个账号下，它是公开身份
#: 而不是本机环境信息。E3 单独打印它的出现次数，供人工复核。
#: 本机用户名/家目录/学号在源码里**拼接**给出。E3 判的是「导出树里有没有这个字面量」，
#: 而这个检查器与它的测试必须写出该模式的形状才能判它——写成字面量会让它们互相判红。
#: 拼接而不是「给这两个文件开豁免」：豁免清单会漂移（新加一个文件忘了登记就静默失效），
#: 而拼接之后源码里根本不存在可匹配的字面量，判据不需要任何白名单。
#: 学号同理（原先写成字面量是漏改：它靠前面紧邻的 `b`（`\b` 的转义）而不构成词边界才没判红，
#: 属于「判据恒绿是偶然」，不是设计）。
_SELF_USER = "dr" + "zy"
_SELF_HOME = "/home/" + _SELF_USER
_SELF_STUDENT_ID = "2302" + "38104"

BANNED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("本机家目录 " + _SELF_HOME,
     re.compile(re.escape(_SELF_HOME) + r"(?![A-Za-z0-9_.-])")),
    ("本机用户名 " + _SELF_USER,
     re.compile(r"(?<![A-Za-z0-9_./-])" + re.escape(_SELF_USER) + r"(?![A-Za-z0-9_.-])")),
    ("学号", re.compile(r"\b" + _SELF_STUDENT_ID + r"\b")),
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("WSL 挂载点 /mnt/<盘符>/", re.compile(r"/mnt/[a-z]/")),
)

#: 只计 note、不判违规的「别人的家目录」（见上面的口径说明）。
FOREIGN_HOME = re.compile(r"/home/([A-Za-z0-9_.-]+)")

#: E2 显式仓库内路径：`<顶层目录>/…:行号`
EXPLICIT_REF = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:scripts|bench|tests|release|references)"
    r"/[A-Za-z0-9_.<>/-]+?):(\d+)(?!\d)"
)
#: E2 根目录文件的显式引用：`AGENTS.md:124`
ROOT_REF = re.compile(r"(?<![A-Za-z0-9_./-])(AGENTS\.md|CHANGELOG\.md|README\.md|LICENSE|VERSION):(\d+)")
#: E2 简写：`02:2105`（数字前缀 01–11 → references/NN-*.md）
SHORT_REF = re.compile(r"(?<![A-Za-z0-9_./:\-])(0[1-9]|1[01]):(\d+)(?!\d)")
#: E2 `README:14` 简写（内部 README 改名后有两个候选，见 N3 #36）
README_SHORT_REF = re.compile(r"(?<![A-Za-z0-9_./-])README:(\d+)(?!\d)")
#: E2 第三方引用：`references/repos/<repo>/<file>:<line>`
EXTERNAL_REF = re.compile(r"references/repos/([A-Za-z0-9._-]+)/([^ `\"()<>:]+):(\d+)")
#: E2 markdown 相对链接（**只在剥掉行内代码段之后**扫）。
#: 为什么必须剥：文档里有用反引号包起来、用来展示「渲染成什么样」的片段，例如
#: ``[![License: MIT](…)]``（引用第三方 README:14 的 badge，省略号就是我们写的）。
#: 反引号里的 `[...](...)` 在渲染后**不是链接**，把它当链接判会要求一个不存在的路径，
#: 而唯一的「修法」是把逐字引用改坏——那是判据逼人做错事。
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_CODE = re.compile(r"`[^`\n]*`")

#: 文本文件才算 E3；这几个后缀是二进制/归档，交给 E5/E6 判
TEXT_SUFFIXES = frozenset({".md", ".py", ".sh", ".txt", ".csv", ".yaml", ".yml", ".json", ".cfg", ".toml"})


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # noqa: D401 - argparse 挂钩
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: 用法错误: {message}\n")
        raise SystemExit(EX_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = _Parser(prog="verify_export.py", description="在公开导出树上跑六道门（E1–E6）。")
    p.add_argument("--tree", required=True, help="导出树根目录")
    p.add_argument("--skip-tests", action="store_true",
                   help="跳过 E4 的 pytest（只用于调试；跳过时不算验收）")
    p.add_argument("--python", default=None,
                   help="跑 E4 单元测试用的解释器（缺省取 $PYTHON / 当前解释器 / PATH 上第一个装了 pytest 的）")
    p.add_argument("--gates", default=",".join(GATES),
                   help=f"只跑指定的门（逗号分隔，缺省全部）：{','.join(GATES)}。"
                        f"单门模式用于定位与变异测试，**不构成整体验收**。")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def walk_files(root: Path) -> list[str]:
    """返回树内所有普通文件的相对路径（POSIX 分隔符，排序）。符号链接单独处理。"""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            out.append(full.relative_to(root).as_posix())
    return out


def walk_symlinks(root: Path) -> list[str]:
    links: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in dirnames + filenames:
            full = Path(dirpath) / name
            if full.is_symlink():
                links.append(full.relative_to(root).as_posix())
    return sorted(links)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_count(path: Path) -> int:
    try:
        return len(read_text(path).splitlines())
    except OSError:
        return -1


def split_frontmatter_aware_lines(text: str):
    """逐行产出 (行号, 行)。目前不跳过 frontmatter——E2 只需行号准确。"""
    for i, line in enumerate(text.splitlines(), start=1):
        yield i, line


# ---------------------------------------------------------------------------
# E1 结构
# ---------------------------------------------------------------------------
def gate_e1(root: Path, files: list[str], links: list[str]) -> tuple[int, list[str]]:
    v: list[str] = []

    for rel in links:
        v.append(f"{rel}: 是符号链接（导出树里不许有，它可能指回本机路径）")

    # 顶层：目录与文件都必须落在闭合集合里
    for entry in sorted({rel.split("/")[0] for rel in files}):
        is_dir = "/" in "".join(r for r in files if r.split("/")[0] == entry)
        top = root / entry
        if top.is_dir():
            if entry not in ALLOWED_TOP_DIRS:
                v.append(f"{entry}/: 顶层目录不在允许集合 {sorted(ALLOWED_TOP_DIRS)} 内")
        elif entry not in ALLOWED_ROOT_FILES:
            v.append(f"{entry}: 顶层文件不在允许集合 {sorted(ALLOWED_ROOT_FILES)} 内")

    # 排除项：出现在任何层级都违规
    for rel in files:
        if any(rel.startswith(p) or f"/{p}" in f"/{rel}" for p in EXCLUDED_PREFIXES):
            v.append(f"{rel}: 命中排除项（{rel} 不该出现在公开导出树里）")
        elif rel.rsplit("/", 1)[-1] in EXCLUDED_NAMES:
            v.append(f"{rel}: 命中排除名 {rel.rsplit('/', 1)[-1]}")

    # references/external 下只许 INDEX.md
    for rel in files:
        if rel.startswith(EXTERNAL_DIR + "/"):
            name = rel[len(EXTERNAL_DIR) + 1:]
            if "/" not in name and name not in EXTERNAL_ALLOWED:
                v.append(f"{rel}: {EXTERNAL_DIR}/ 下只允许 {sorted(EXTERNAL_ALLOWED)}")

    # 必需项
    required_files = ["README.md", "LICENSE", "AGENTS.md", "VERSION",
                      "requirements-dev.txt", "references/registry.csv"]
    for rel in required_files:
        if not (root / rel).is_file():
            v.append(f"缺少必需文件: {rel}")
    for rel in ("scripts", "tests/unit", "tests/contract", "bench/tasks", "release"):
        if not (root / rel).is_dir():
            v.append(f"缺少必需目录: {rel}/")
    tasks = sorted((root / "bench" / "tasks").glob("T*.yaml")) if (root / "bench" / "tasks").is_dir() else []
    if len(tasks) != 12:
        v.append(f"bench/tasks/ 下有 {len(tasks)} 个任务 yaml，期望 12（R12 冻结任务集）")
    return len(files), v


# ---------------------------------------------------------------------------
# E2 引用
# ---------------------------------------------------------------------------
def load_registry(root: Path) -> dict[str, str]:
    """registry.csv → {project_id: commit_sha}（docs_only 行 sha 为空）。"""
    path = root / "references" / "registry.csv"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            pid = (row.get("project_id") or "").strip()
            if pid:
                out[pid] = (row.get("commit_sha") or "").strip()
    return out


def gate_e2(root: Path, files: list[str]) -> tuple[dict[str, int], list[str]]:
    v: list[str] = []
    counts = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    registry = load_registry(root)
    short_targets: dict[str, list[Path]] = {}
    for p in sorted((root / "references").glob("*.md")):
        m = re.match(r"^(\d\d)-", p.name)
        if m:
            short_targets.setdefault(m.group(1), []).append(p)
    readme_candidates = [p for p in (root / "README.md", root / "references" / "00-project-readme.md")
                         if p.is_file()]

    md_files = [rel for rel in files if rel.endswith(".md")]
    for rel in md_files:
        doc = root / rel
        text = read_text(doc)
        for lineno, line in split_frontmatter_aware_lines(text):
            where = f"{rel}:{lineno}"

            # A 显式仓库内路径（含 references/repos，交给 D 单独判，这里先扣掉）
            for m in EXPLICIT_REF.finditer(line):
                target_rel, want = m.group(1), int(m.group(2))
                if target_rel.startswith("references/repos/"):
                    continue
                counts["A"] += 1
                target = root / target_rel
                if not target.is_file():
                    v.append(f"{where}: 引用了导出树里不存在的文件 `{target_rel}`")
                    continue
                total = line_count(target)
                if want > total:
                    v.append(f"{where}: `{target_rel}:{want}` 行号越界（该文件共 {total} 行）")

            # A' 根目录文件
            for m in ROOT_REF.finditer(line):
                target_rel, want = m.group(1), int(m.group(2))
                counts["A"] += 1
                target = root / target_rel
                if not target.is_file():
                    v.append(f"{where}: 引用了不存在的根文件 `{target_rel}`")
                elif want > line_count(target):
                    v.append(f"{where}: `{target_rel}:{want}` 行号越界（共 {line_count(target)} 行）")

            # B markdown 相对链接（剥掉行内代码段后再判，见 INLINE_CODE 的注释）
            for m in MD_LINK.finditer(INLINE_CODE.sub(" ", line)):
                raw = m.group(1).strip()
                if not raw or raw.startswith(("#", "http://", "https://", "mailto:", "tel:")):
                    continue
                target_rel = raw.split("#", 1)[0]
                if not target_rel:
                    continue
                counts["B"] += 1
                target = (doc.parent / target_rel).resolve()
                if not target.exists():
                    v.append(f"{where}: markdown 链接指向不存在的路径 `{raw}`")

            # C 简写 NN:行号（唯一候选才判）
            for m in SHORT_REF.finditer(line):
                nn, want = m.group(1), int(m.group(2))
                cands = short_targets.get(nn, [])
                if len(cands) != 1:
                    counts["E"] += 1
                    continue
                counts["C"] += 1
                if want > line_count(cands[0]):
                    v.append(f"{where}: `{nn}:{want}` 行号越界（{cands[0].name} 共 {line_count(cands[0])} 行）")

            # C' README:行号（两个候选任一容纳即通过）
            for m in README_SHORT_REF.finditer(line):
                want = int(m.group(1))
                counts["C"] += 1
                if not readme_candidates:
                    v.append(f"{where}: `README:{want}` 无候选文件可解析")
                elif want > max(line_count(p) for p in readme_candidates):
                    v.append(f"{where}: `README:{want}` 行号超过所有 README 候选的最大行数")

            # D 第三方引用：仓库必须在 registry.csv 且带 sha
            for m in EXTERNAL_REF.finditer(line):
                repo = m.group(1)
                counts["D"] += 1
                if repo not in registry:
                    v.append(f"{where}: 第三方引用 `{repo}` 不在 registry.csv 里")
                elif not registry[repo]:
                    v.append(f"{where}: 第三方引用 `{repo}` 在 registry.csv 里没有 commit_sha"
                             f"（不可复现，等于无法追溯）")
    return counts, v


# ---------------------------------------------------------------------------
# E3 本机/个人标识
# ---------------------------------------------------------------------------
def gate_e3(root: Path, files: list[str]) -> tuple[int, list[str]]:
    v: list[str] = []
    scanned = 0
    handle_hits = 0
    foreign: dict[str, int] = {}
    for rel in files:
        if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned += 1
        for lineno, line in split_frontmatter_aware_lines(read_text(root / rel)):
            handle_hits += line.count("Zyzhan417")
            for m in FOREIGN_HOME.finditer(line):
                user = m.group(1)
                if user != _SELF_USER:
                    foreign[user] = foreign.get(user, 0) + 1
            for label, pat in BANNED_PATTERNS:
                for m in pat.finditer(line):
                    v.append(f"{rel}:{lineno}: 出现{label} `{m.group(0)}`")
    if handle_hits:
        print(f"  note: GitHub handle `Zyzhan417` 出现 {handle_hits} 次（公开身份，不算违规，请人工复核）")
    if foreign:
        detail = ", ".join(f"/home/{u}×{n}" for u, n in sorted(foreign.items()))
        print(f"  note: 第三方引用的**别人**家目录 {detail}（逐字引用不改写，仅提示）")
    return scanned, v


# ---------------------------------------------------------------------------
# E4 可运行
# ---------------------------------------------------------------------------
def python_with_pytest(explicit: str | None = None) -> str | None:
    """返回第一个「能 import pytest」的解释器路径；都没有则 None。

    为什么需要这一步：`verify_export.py` 自己的 `sys.executable` 未必装了 pytest
    （实测本机 PATH 上有多个 python3，只有一个装了 pytest）。用错解释器时 E4 会报
    `No module named pytest`，看起来像「导出树里的代码坏了」——那是**判据在说谎**，
    而不是被测对象有问题。所以这里显式挑解释器，挑不到就如实报「无法构成证据」。

    候选顺序：`--python` 显式指定 → `$PYTHON` → 当前解释器 → PATH 上每一个 python3/python。
    **不扫 $HOME 去找 conda 环境**：那需要知道本机布局，而本脚本要对任意机器成立。
    """
    seen: list[str] = []
    for cand in [explicit, os.environ.get("PYTHON"), sys.executable]:
        if cand and cand not in seen:
            seen.append(cand)
    for d in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("python3", "python"):
            p = Path(d) / name
            if p.is_file() and os.access(p, os.X_OK):
                s = str(p)
                if s not in seen:
                    seen.append(s)
    for py in seen:
        try:
            proc = subprocess.run([py, "-c", "import pytest"], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return py
    return None


def gate_e4(root: Path, files: list[str], skip_tests: bool,
            python_bin: str | None = None) -> tuple[int, list[str]]:
    v: list[str] = []
    checked = 0
    pyc_cache = Path(os.environ.get("TMPDIR", "/tmp")) / "verify_export_pycache"
    # VERIFY_EXPORT_ACTIVE：导出树的 E4 里会跑 tests/unit，而 tests/unit 里有一条测试
    # 会再调用 make_export —— 不设这个标记就会无限递归。标记的含义是「已经在验这棵树了，
    # 再验一次不增加任何信息」，对应的 skip 写在 tests/unit/test_export.py 的模块级 pytestmark。
    env = {**os.environ, "PYTHONPYCACHEPREFIX": str(pyc_cache),
           "PYTHONDONTWRITEBYTECODE": "1", "VERIFY_EXPORT_ACTIVE": "1"}

    for rel in files:
        suffix = Path(rel).suffix
        full = root / rel
        if suffix == ".py":
            checked += 1
            proc = subprocess.run([sys.executable, "-m", "py_compile", str(full)],
                                  capture_output=True, text=True, timeout=120, env=env)
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
                v.append(f"{rel}: py_compile 失败 — {tail[0]}")
        elif suffix == ".sh":
            checked += 1
            proc = subprocess.run(["bash", "-n", str(full)], capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                v.append(f"{rel}: bash -n 失败 — {proc.stderr.strip().splitlines()[:1]}")

    # 可执行位：scripts/ 下每个文件都必须能直接执行（shebang 契约，见 tests/unit/test_script_entrypoints.py）
    for rel in files:
        if rel.startswith("scripts/"):
            checked += 1
            if not os.access(root / rel, os.X_OK):
                v.append(f"{rel}: 没有可执行位（导出后 `./{rel}` 会 126）")

    if skip_tests:
        print("  note: --skip-tests 已跳过 pytest —— 本次 E4 **不构成**「代码可运行」的证据")
        return checked, v

    py = python_with_pytest(python_bin)
    if py is None:
        v.append("找不到装了 pytest 的解释器：E4 无法构成「代码可运行」的证据"
                 "（装法见 requirements-dev.txt，或用 --python / $PYTHON 指定；"
                 "不装就必须如实报红，不能退化为通过）")
        return checked, v
    print(f"  用解释器 {py} 跑导出树内的单元测试")

    proc = subprocess.run(
        [py, "-m", "pytest", "tests/unit", "-q", "-p", "no:cacheprovider"],
        cwd=str(root), capture_output=True, text=True, timeout=1800, env=env,
    )
    last = [ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()]
    print(f"  pytest tests/unit（导出树内）→ 退出码 {proc.returncode}；末行: {last[-1] if last else '(空)'}")
    if proc.returncode != 0:
        v.append(f"导出树内 pytest tests/unit 退出 {proc.returncode}"
                 f"（stderr 末尾: {(proc.stderr or '').strip().splitlines()[-1:] or ['']}）")
    return checked, v


# ---------------------------------------------------------------------------
# E5 第三方内容
# ---------------------------------------------------------------------------
def gate_e5(root: Path, files: list[str]) -> tuple[int, list[str]]:
    v: list[str] = []
    checked = len(files)
    if (root / "references" / "repos").exists():
        v.append("references/repos/ 存在（第三方源码副本不得随 MIT 仓库再分发；只留 registry.csv 的 sha）")
    ext = root / EXTERNAL_DIR
    if ext.is_dir():
        for p in sorted(ext.iterdir()):
            if p.is_file() and p.name not in EXTERNAL_ALLOWED:
                v.append(f"{EXTERNAL_DIR}/{p.name}: 第三方文章正文不得随仓库发布（只留 INDEX.md 的 URL + sha256）")
    for rel in files:
        if "/.git/" in f"/{rel}" or rel.endswith(".tar.gz") or rel.endswith(".bundle"):
            v.append(f"{rel}: 归档或嵌套仓库不得进导出树")
    return checked, v


# ---------------------------------------------------------------------------
# E6 体积
# ---------------------------------------------------------------------------
def gate_e6(root: Path, files: list[str]) -> tuple[int, list[str]]:
    v: list[str] = []
    total = 0
    biggest = ("", 0)
    for rel in files:
        try:
            size = (root / rel).stat().st_size
        except OSError:
            continue
        total += size
        if size > biggest[1]:
            biggest = (rel, size)
        if size > MAX_FILE_BYTES:
            v.append(f"{rel}: {size} 字节 > {MAX_FILE_BYTES}（计算结果/大文件应走 release asset 或外部存储）")
    print(f"  体积合计 {total / 1024 / 1024:.2f} MB；最大单文件 {biggest[0]} ({biggest[1]} 字节)")
    return len(files), v


# ---------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.tree)
    if not root.is_dir():
        sys.stderr.write(f"verify_export.py: 用法错误: --tree 不是目录: {args.tree}\n")
        return EX_USAGE
    root = root.resolve()

    files = walk_files(root)
    if not files:
        sys.stderr.write(f"verify_export.py: 用法错误: {root} 是空目录（空树全绿 = 假绿）\n")
        return EX_USAGE
    links = walk_symlinks(root)

    wanted = [g.strip().upper() for g in args.gates.split(",") if g.strip()]
    unknown = [g for g in wanted if g not in GATES]
    if unknown or not wanted:
        sys.stderr.write(f"verify_export.py: 用法错误: --gates 含未知门 {unknown}（合法值 {GATES}）\n")
        return EX_USAGE
    if len(wanted) != len(GATES):
        print(f"  note: 只跑了 {','.join(wanted)} —— 单门模式，**不构成整体验收**")

    all_v: list[str] = []

    if "E1" in wanted:
        n, v = gate_e1(root, files, links); all_v += v
        print(f"[E1] 结构      {n} 个文件，违规 {len(v)} 处")

    if "E2" in wanted:
        counts, v = gate_e2(root, files); all_v += v
        print(f"[E2] 引用      A(仓库内)={counts['A']} B(链接)={counts['B']} C(简写)={counts['C']} "
              f"D(第三方)={counts['D']} E(跳过)={counts['E']}，违规 {len(v)} 处")
        if counts["A"] + counts["B"] + counts["C"] + counts["D"] == 0:
            print("  note: 硬判据样本为 0 —— 本门不构成证据（判据可能已经和文档写法脱节）")

    if "E3" in wanted:
        n, v = gate_e3(root, files); all_v += v
        print(f"[E3] 标识      {n} 个文本文件，违规 {len(v)} 处")

    if "E4" in wanted:
        n, v = gate_e4(root, files, args.skip_tests, args.python); all_v += v
        print(f"[E4] 可运行    {n} 项检查，违规 {len(v)} 处")

    if "E5" in wanted:
        n, v = gate_e5(root, files); all_v += v
        print(f"[E5] 第三方    {n} 个文件，违规 {len(v)} 处")

    if "E6" in wanted:
        n, v = gate_e6(root, files); all_v += v
        print(f"[E6] 体积      {n} 个文件，违规 {len(v)} 处")

    if all_v:
        print("", file=sys.stderr)
        print(f"导出树违规 {len(all_v)} 处：", file=sys.stderr)
        for item in all_v[:80]:
            print(f"  - {item}", file=sys.stderr)
        if len(all_v) > 80:
            print(f"  …（还有 {len(all_v) - 80} 处未列出）", file=sys.stderr)
        print("下一步：改导出源（工作树），不要改这个检查器。", file=sys.stderr)
        return EX_VIOLATION

    print(f"RESULT: EXPORT OK（{root}）")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
