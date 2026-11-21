"""脚本清单的单一权威是 `WL_SRC`：本文件把各处副本的漂移变成红灯。

## 为什么必须有

用户面脚本清单在仓库里有多处副本（`references/13-maintenance.md` §6 M-1 标题即「七处平行登记」，
并写明「usage 文字、README 计数漏改不会被抓红」）。本文件封其中 6 处：

    scripts/make_release.sh              WL_SRC              ← 权威（发布白名单），不封
    scripts/preflight.sh                 USER_SCRIPTS        ← 装好之后自检，必须自带清单
    scripts/preflight.sh                 三句 usage 文字里的「N 个用户面脚本」
    tests/unit/test_portability.py       USER_FACING
    tests/contract/test_make_release.py  PACKAGE_SCRIPTS
    tests/unit/test_exit_codes.py        SCRIPTS（包含关系，豁免 preflight.sh）
    README.md                            两句「N 个用户面 CLI / 脚本」
    release/*.md                         样例输出里的「N 个用户面脚本」

仍无门的两处及理由见 M-1：`WL_DST`（与 `WL_SRC` 平行，由 `make_release.sh` 自己的组装检查守）
与 `check_release_docs.py` 的 `KNOWN_EXIT_CODES`（退出码集合，不是脚本清单）。

实测腐坏过：`README.md` 曾写「另含 8 个维护侧脚本」（实际 9 个）；
`release/QUICKSTART.md` 至今写着「8 个用户面脚本」（实际 9 个）——没有任何东西会红。

本文件不消灭副本（preflight 装到别处后必须自带清单，删不掉），只做一件事：
**以 `WL_SRC` 为权威逐份比对，不一致就红**。派生失败（正则没命中、块没闭合）同样红——
否则判据会退化成「空集等于空集」。

## 为什么用 ast 读 .py 里的清单

那两个清单在测试文件里。import 它们会执行被测模块（`test_make_release.py` 导入时就有路径断言），
`ast.literal_eval` 只读字面量、不执行任何代码，也不受 pytest 收集顺序影响。

## 为什么文字副本的「空命中」分两种口径

`README.md` / `release/*.md` 的计数可以整句删掉（改成指向权威、不写数字是好方向），
所以空命中视为通过（`min_hits=0`）。`preflight.sh` 的三句 usage 是**用户可见的帮助文本**，
删掉就是缺陷，所以要求至少命中 1 处（`min_hits=1`）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKE_RELEASE = REPO_ROOT / "scripts" / "make_release.sh"
PREFLIGHT = REPO_ROOT / "scripts" / "preflight.sh"
TEST_PORTABILITY = REPO_ROOT / "tests" / "unit" / "test_portability.py"
TEST_MAKE_RELEASE = REPO_ROOT / "tests" / "contract" / "test_make_release.py"
TEST_EXIT_CODES = REPO_ROOT / "tests" / "unit" / "test_exit_codes.py"
README = REPO_ROOT / "README.md"
RELEASE_DOCS = sorted((REPO_ROOT / "release").glob("*.md"))

#: preflight 的 usage 里「N 个用户面脚本」（实测 3 处：`preflight.sh:12/74/95`）。
USAGE_COUNT_PATTERN = r"(\d+)\s*个用户面脚本"
#: README / release 文档里「N 个用户面 CLI / 脚本」。
README_COUNT_PATTERN = r"(\d+)\s*个用户面"

#: `test_exit_codes.py` 的 `SCRIPTS` 有意豁免 preflight.sh：它的默认动作是「跑检查」并退 0，
#: 所以「不传参数 = 用法错误」对它不成立（同一说明见 `preflight.sh:74`）。
EXIT_CODE_EXEMPT = {"preflight.sh"}


# ---------------------------------------------------------------------------
# 判据（纯函数；真实副本与合成坏样本走同一条代码）
# ---------------------------------------------------------------------------
def bash_array(path: Path, name: str) -> list[str]:
    """读 bash 脚本里的 `[readonly ]NAME=( ... )` 块，返回去注释/空行/引号后的条目。

    没命中块、或块没有收尾的 `)` → 抛 AssertionError。判据不许在「解析失败」时返回空列表：
    空列表会让后面的集合比较变成「空 == 空」而恒绿。
    """
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^\s*(?:readonly\s+)?{re.escape(name)}=\(\s*$", text, re.MULTILINE)
    assert m, f"{path} 里找不到 {name}=( ... ) 块——派生失败，判据不能空转"

    out: list[str] = []
    for line in text[m.end():].splitlines():
        if line.strip() == ")":
            return out
        item = line.split("#", 1)[0].strip().strip('"').strip("'")
        if item:
            out.append(item)
    raise AssertionError(f"{path} 的 {name} 块没有收尾的 ')'")


def py_literal(path: Path, name: str) -> list[str] | set[str]:
    """用 ast 取 .py 里模块级赋值 `NAME = [...]` / `NAME = {...}` 的字面量（不执行文件）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path} 里找不到模块级赋值 {name} —— 派生失败")


def wl_src_scripts() -> list[str]:
    """权威：`WL_SRC` 里属于 `scripts/` 的条目 → 文件名（排序）。"""
    return sorted(Path(e).name for e in bash_array(MAKE_RELEASE, "WL_SRC") if e.startswith("scripts/"))


def inventory_mismatches(authority: list[str], copy: list[str], label: str) -> list[str]:
    """权威与副本的差集（空 = 一致）。两个方向都报：漏一个与多一个都会让门空转或误伤。"""
    a, c = set(authority), set(copy)
    out: list[str] = []
    if a - c:
        out.append(f"{label}: 漏了 {sorted(a - c)}")
    if c - a:
        out.append(f"{label}: 多了 {sorted(c - a)}")
    return out


def count_claims_violations(text: str, pattern: str, want: int, label: str,
                            min_hits: int = 0) -> list[str]:
    """文字副本与权威数量不一致 → 违规（空 = 一致）。

    `min_hits` 是命中下限：`preflight.sh` 的 usage 文字删掉就是缺陷，传 1；
    README / release 文档允许改成不写数字，传 0（空命中 = 不再声明，不判红）。
    """
    got = [int(m) for m in re.findall(pattern, text)]
    if len(got) < min_hits:
        return [f"{label}: 只命中 {len(got)} 处，至少应有 {min_hits} 处（文字副本可能被删了）"]
    bad = [n for n in got if n != want]
    return [f"{label}: 声明了 {bad}，权威是 {want}（共 {len(got)} 处）"] if bad else []


# ---------------------------------------------------------------------------
# 前置：权威本身可用
# ---------------------------------------------------------------------------
def test_wl_src_is_a_real_nonempty_inventory():
    """`WL_SRC` 派生出的脚本集合非空，且每个都真在 `scripts/` 下。"""
    derived = wl_src_scripts()
    assert derived, "WL_SRC 里没有任何 scripts/ 条目——派生失败"
    missing = [n for n in derived if not (REPO_ROOT / "scripts" / n).is_file()]
    assert not missing, f"WL_SRC 点了名但仓库里没有的脚本: {missing}"


# ---------------------------------------------------------------------------
# 各处副本逐份比对
# ---------------------------------------------------------------------------
def test_preflight_user_scripts_is_wl_src_minus_preflight_itself():
    """`preflight.sh` 的 `USER_SCRIPTS` = `WL_SRC` 去掉 `preflight.sh` 自己。

    preflight 装到别处后没有 `make_release.sh` 可读，所以清单删不掉；
    这条把它变成「权威减一」的派生量：改了 WL_SRC 而忘了它会红。
    """
    authority = [n for n in wl_src_scripts() if n != "preflight.sh"]
    got = sorted(Path(e).name for e in bash_array(PREFLIGHT, "USER_SCRIPTS"))
    assert not inventory_mismatches(authority, got, "preflight.sh:USER_SCRIPTS")


def test_portability_user_facing_equals_wl_src():
    """`tests/unit/test_portability.py` 的 `USER_FACING` = `WL_SRC`（含 preflight 自己）。"""
    got = sorted(Path(e).name for e in py_literal(TEST_PORTABILITY, "USER_FACING"))
    assert not inventory_mismatches(wl_src_scripts(), got, "test_portability.py:USER_FACING")


def test_release_package_scripts_equal_wl_src():
    """`tests/contract/test_make_release.py` 的 `PACKAGE_SCRIPTS` = `WL_SRC`。"""
    got = sorted(Path(e).name for e in py_literal(TEST_MAKE_RELEASE, "PACKAGE_SCRIPTS"))
    assert not inventory_mismatches(wl_src_scripts(), got, "test_make_release.py:PACKAGE_SCRIPTS")


def test_exit_codes_covers_every_user_facing_script():
    """`test_exit_codes.py` 的 `SCRIPTS` ⊇ `WL_SRC`（唯一豁免 `preflight.sh`）。

    包含关系而非相等：`SCRIPTS` 里还有 `make_export.sh` / `verify_export.py` / `make_release.sh`
    这些维护侧脚本，它们同样必须「不传参数退 64」，所以是超集。
    这是 M-1 #3 的封法——实测 `fix_case.py` 不传参数退 64 却从未被这条契约测过。
    """
    declared = {Path(e).name for e in py_literal(TEST_EXIT_CODES, "SCRIPTS")}
    need = set(wl_src_scripts()) - EXIT_CODE_EXEMPT
    missing = sorted(need - declared)
    assert not missing, (
        f"test_exit_codes.py:SCRIPTS 漏了 {missing}——这些脚本的「用法错误恒退 64」契约没有测试"
        f"（豁免 {sorted(EXIT_CODE_EXEMPT)} 的理由见模块 docstring）"
    )


def test_preflight_usage_text_states_the_real_count():
    """`preflight.sh` 三句「N 个用户面脚本」的 N = `USER_SCRIPTS` 条目数，且至少命中 1 处。"""
    want = len(bash_array(PREFLIGHT, "USER_SCRIPTS"))
    violations = count_claims_violations(
        PREFLIGHT.read_text(encoding="utf-8"), USAGE_COUNT_PATTERN, want,
        "preflight.sh 的 usage 文字", min_hits=1,
    )
    assert not violations, "; ".join(violations)


def test_readme_states_the_real_user_script_count():
    """`README.md` 里「N 个用户面 CLI / 脚本」的 N = `WL_SRC` 条目数。

    `min_hits=0`：README 允许改成不写数字（指向 `WL_SRC`），那时空命中不判红。
    """
    want = len(wl_src_scripts())
    violations = count_claims_violations(
        README.read_text(encoding="utf-8"), README_COUNT_PATTERN, want, "README.md", min_hits=0
    )
    assert not violations, "; ".join(violations)


@pytest.mark.parametrize("doc", RELEASE_DOCS, ids=lambda p: p.name)
def test_release_docs_state_the_real_user_script_count(doc: Path):
    """`release/*.md` 的样例输出里「N 个用户面脚本」的 N = `USER_SCRIPTS` 条目数。

    这份文档是用户照抄的对象：`QUICKSTART.md` 曾写「8 个」而实测 9 个，
    照抄的人会以为包里的文件少了。
    """
    want = len(bash_array(PREFLIGHT, "USER_SCRIPTS"))
    violations = count_claims_violations(
        doc.read_text(encoding="utf-8"), USAGE_COUNT_PATTERN, want, doc.name, min_hits=0
    )
    assert not violations, "; ".join(violations)


# ---------------------------------------------------------------------------
# 尺子有牙：合成/变异样本（只写 tmp_path，不改仓库文件）
# ---------------------------------------------------------------------------
def test_ruler_reports_a_dropped_entry(tmp_path: Path):
    """把真 `preflight.sh` 复制到 tmp、删掉其中任意一项 → 比对必须点名被删的那一项。

    「少一项没人会说、也没有东西会红」在清单上的对应物。
    被删的条目**从当前文件里取最后一项**，不写死某个脚本名：写死会让这条用例在
    「那个脚本真的被移出白名单」时假红（它自己的前置断言会失败），而那时清单本身是对的。
    """
    src = PREFLIGHT.read_text(encoding="utf-8")
    entries = bash_array(PREFLIGHT, "USER_SCRIPTS")
    assert entries, "preflight.sh 的 USER_SCRIPTS 是空的，本变异不成立"
    victim = entries[-1]
    assert f"\n    {victim}\n" in src, f"在 preflight.sh 里定位不到 {victim} 单行占位，本变异不成立"

    bad = tmp_path / "preflight.sh"
    bad.write_text(src.replace(f"\n    {victim}\n", "\n"), encoding="utf-8")

    got = sorted(Path(e).name for e in bash_array(bad, "USER_SCRIPTS"))
    msgs = inventory_mismatches(
        [n for n in wl_src_scripts() if n != "preflight.sh"], got, "preflight.sh:USER_SCRIPTS"
    )
    assert msgs and victim in msgs[0], f"删掉 {victim} 却没有点名它：{msgs}"


def test_ruler_flags_wrong_count_in_text():
    """文字副本的真假两侧都要成立：错数字被判出，对数字不被误伤。"""
    good = "# 6 scripts  同目录 9 个用户面脚本存在且可执行\n"
    bad = "# 6 scripts  同目录 10 个用户面脚本存在且可执行\n"
    assert count_claims_violations(good, USAGE_COUNT_PATTERN, 9, "x") == []
    assert count_claims_violations(bad, USAGE_COUNT_PATTERN, 9, "x")


def test_ruler_flags_missing_text_when_floor_is_one():
    """`min_hits=1` 时一处都没命中必须红；`min_hits=0` 时放行（两种口径不能混）。"""
    text = "# 6 scripts  同目录若干脚本存在且可执行\n"
    assert count_claims_violations(text, USAGE_COUNT_PATTERN, 9, "x", min_hits=0) == []
    assert count_claims_violations(text, USAGE_COUNT_PATTERN, 9, "x", min_hits=1)


def test_ruler_flags_missing_block_instead_of_returning_empty(tmp_path: Path):
    """解析失败必须抛错，不能返回空列表——否则集合比较会「空 == 空」而恒绿。"""
    broken = tmp_path / "broken.sh"
    broken.write_text("readonly OTHER=(a b)\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        bash_array(broken, "USER_SCRIPTS")
