"""模块 B（scripts/find_template.sh）的 L2 契约测试，5 项。

对应 references/09-architecture-and-test-plan.md 的 B 表：
  B1 确定性       同一查询两次输出 diff 为空
  B2 搜索根合规   每条命中的绝对路径以五个根之一开头；不得出现 ~/OpenFOAM
  B3 已知答案集   20 条手写 (查询, 期望相对路径子串)，每条至少命中 1 条
  B4 空结果不编造 查 kOmegaSSTFoo → FOUND=0 且退出 11，无任何回退
  B5 命中有效性   path 存在、行号不越界、该行非空（空行也算错）

设计约定：
- 五个搜索根从 /opt/openfoam13/etc/bashrc 现场取，不硬编码 /opt 下的子路径
  （只硬编码 bashrc 这一个入口），避免测试自己变成"记忆里的路径"。
- 不使用 fuzzy 断言：每条判据都是可判定的布尔条件，失败信息里带原始行。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# 环境引导（bashrc → env）、cavity 派生源与五个根统一由 `tests/contract/conftest.py`
# 提供：本文件只声明 `foam_env` / `cavity_src` / `roots` 夹具，不再自己 source 一遍。

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "find_template.sh"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
KNOWN_QUERIES = FIXTURES / "known_queries.tsv"


ABSENT_KEYWORD = "kOmegaSSTFoo"


# ---------------------------------------------------------------- 基础设施


def run_find(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def parse_hits(stdout: str) -> tuple[list[tuple[str, int]], int]:
    """把 stdout 拆成 ([(相对路径, 行号)], FOUND 值)。

    契约（末两行）：
        FOUND=<命中总数>   —— 不受 --limit 影响
        SHOWN=<输出行数>   —— 受 --limit 影响
    其余每行必须是 "相对路径:行号"。这里对格式本身也做硬校验——格式错了要立刻炸。

    为什么 FOUND 不能等于输出行数：规格原文是「n = 命中文件数」。
    若 `--limit 3` 时报 FOUND=3，下游会把「被截断」误读成「库里只有 3 个候选」。
    """
    lines = stdout.splitlines()
    assert lines, "stdout 为空：至少也要有 FOUND=0 一行"

    if len(lines) == 1:                       # 空命中：只有 FOUND=0，无 SHOWN
        assert lines[0] == "FOUND=0", f"空命中应只输出 FOUND=0: {lines!r}"
        return [], 0

    assert lines[-2].startswith("FOUND="), f"倒数第二行不是 FOUND=<n>: {lines[-2]!r}"
    assert lines[-1].startswith("SHOWN="), f"最后一行不是 SHOWN=<n>: {lines[-1]!r}"
    found = int(lines[-2][len("FOUND="):])
    shown = int(lines[-1][len("SHOWN="):])

    hits: list[tuple[str, int]] = []
    for line in lines[:-2]:
        assert ":" in line, f"命中行缺少冒号: {line!r}"
        rel, _, lineno = line.rpartition(":")
        assert rel, f"命中行相对路径为空: {line!r}"
        assert lineno.isdigit(), f"命中行行号不是整数: {line!r}"
        hits.append((rel, int(lineno)))

    assert shown == len(hits), f"SHOWN={shown} 与实际命中行数 {len(hits)} 不一致"
    assert found >= shown, f"FOUND={found} 不得小于 SHOWN={shown}（总数不可能少于输出行数）"
    return hits, found


def resolve_root(rel: str, roots: list[tuple[str, Path]]) -> Path:
    """把相对路径解析回它所在的根：按固定顺序取第一个真实存在的。"""
    for _, root in roots:
        if (root / rel).exists():
            return root
    pytest.fail(f"相对路径在五个根下都不存在: {rel}")


# ---------------------------------------------------------------- B1 确定性


def test_b1_determinism(foam_env: dict):
    """同一查询连续两次输出逐字相同；且同一相对路径不得重复出现（一行只用第一个命中）。"""
    first = run_find(foam_env, "--keyword", "cavity")
    second = run_find(foam_env, "--keyword", "cavity")

    assert first.returncode == 0, f"cavity 应命中，实际 rc={first.returncode}, stderr={first.stderr!r}"
    assert first.stdout == second.stdout, (
        "同一输入两次输出不一致（非确定性）\n"
        f"第一次:\n{first.stdout}\n第二次:\n{second.stdout}"
    )

    hits, _ = parse_hits(first.stdout)
    rels = [rel for rel, _ in hits]
    assert len(rels) == len(set(rels)), f"同一相对路径出现多次: {sorted({r for r in rels if rels.count(r) > 1})}"
    # 排序口径：按相对路径非降序（第二键是行号，只用于消除并列）
    assert rels == sorted(rels), "输出未按相对路径排序"


# ---------------------------------------------------------------- B2 搜索根合规


def test_b2_search_roots_compliant(foam_env: dict, roots: list[tuple[str, Path]]):
    """每条命中的绝对路径必须落在五个根之一以内；不得出现 $HOME/OpenFOAM。"""
    home_openfoam = Path(foam_env.get("HOME", "~")).expanduser() / "OpenFOAM"
    home_copy_prefix = str(home_openfoam) + "/"

    checked = 0
    for keyword in ("kOmegaSST", "checkMesh"):
        proc = run_find(foam_env, "--keyword", keyword)
        assert proc.returncode == 0, f"{keyword} 应命中，rc={proc.returncode}"
        hits, _ = parse_hits(proc.stdout)
        assert hits, f"{keyword} 命中为空"
        for rel, _ in hits:
            root = resolve_root(rel, roots=roots)
            abs_path = str(root / rel)
            allowed = [str(path) for _, path in roots]
            assert any(
                abs_path == a or abs_path.startswith(a.rstrip("/") + "/") for a in allowed
            ), f"命中不在五个根之内: {abs_path}"
            assert not abs_path.startswith(home_copy_prefix), (
                f"命中落进 $HOME/OpenFOAM 副本（R1/R9 禁止）: {abs_path}"
            )
            checked += 1
    assert checked > 0


# ---------------------------------------------------------------- B3 已知答案集


def test_b3_known_answer_set(foam_env: dict):
    """读 20 条手写 (查询, 期望子串)，每条至少命中 1 条期望子串。"""
    assert KNOWN_QUERIES.is_file(), f"缺少答案集文件: {KNOWN_QUERIES}"

    rows: list[tuple[str, str]] = []
    for raw in KNOWN_QUERIES.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = raw.split("\t")
        assert len(parts) == 2, f"答案集行格式错误（需 keyword\\texpected）: {raw!r}"
        keyword, expected = parts[0].strip(), parts[1].strip()
        assert keyword and expected, f"答案集行有空字段: {raw!r}"
        rows.append((keyword, expected))

    assert len(rows) == 20, f"答案集必须正好 20 条，实际 {len(rows)} 条"

    failures: list[str] = []
    for keyword, expected in rows:
        proc = run_find(foam_env, "--keyword", keyword)
        if proc.returncode != 0:
            failures.append(f"[{keyword}] 期望命中 {expected!r}，实际 rc={proc.returncode}（空结果）")
            continue
        hits, found = parse_hits(proc.stdout)
        if found == 0:
            failures.append(f"[{keyword}] FOUND=0，期望命中 {expected!r}")
            continue
        rels = [rel for rel, _ in hits]
        if not any(expected in rel for rel in rels):
            failures.append(
                f"[{keyword}] 无任何命中路径包含 {expected!r}；实际前 3 条: {rels[:3]}"
            )

    assert not failures, "B3 已知答案集未通过:\n" + "\n".join(failures)


# ---------------------------------------------------------------- B4 空结果不编造


def test_b4_empty_result_not_fabricated(foam_env: dict):
    """不存在的词：只输出 FOUND=0，退出 11，不得回退到任何默认值/记忆/别的目录。"""
    proc = run_find(foam_env, "--keyword", ABSENT_KEYWORD)

    assert proc.returncode == 11, (
        f"空命中必须退出 11，实际 {proc.returncode}；stdout={proc.stdout!r}"
    )
    assert proc.stdout.strip() == "FOUND=0", (
        f"空命中时 stdout 必须只有 FOUND=0（不得给候选/默认值），实际 {proc.stdout!r}"
    )
    assert proc.stdout.splitlines() == ["FOUND=0"]

    # 反向对照：同一进程环境下，真词必须命中 —— 否则"空结果"可能只是根全空或脚本坏了
    control = run_find(foam_env, "--keyword", "kOmegaSST")
    assert control.returncode == 0, "对照组 kOmegaSST 未命中，说明环境/脚本有问题，B4 结论不可信"
    assert parse_hits(control.stdout)[1] > 0


# ---------------------------------------------------------------- B5 命中有效性


def test_b5_hits_are_valid(foam_env: dict, roots: list[tuple[str, Path]]):
    """全部命中：文件存在、行号不越界、该行非空（空行算错）、且该行确实含查询词。"""
    problems: list[str] = []
    total = 0

    for keyword in ("cavity", "kOmegaSST"):
        proc = run_find(foam_env, "--keyword", keyword)
        assert proc.returncode == 0, f"{keyword} 应命中，rc={proc.returncode}"
        hits, found = parse_hits(proc.stdout)
        assert found > 0

        for rel, lineno in hits:
            total += 1
            paths = [root / rel for _, root in roots]
            existing = [p for p in paths if p.is_file()]
            if not existing:
                problems.append(f"[{keyword}] 文件不存在: {rel}")
                continue
            target = existing[0]
            text = target.read_text(encoding="utf-8", errors="replace").splitlines()
            if lineno < 1 or lineno > len(text):
                problems.append(
                    f"[{keyword}] 行号越界: {rel}:{lineno}（文件共 {len(text)} 行）"
                )
                continue
            line = text[lineno - 1]
            if line.strip() == "":
                # 本项目在"锚点指向空行"上栽过三次：门禁只查越界、不查空行
                problems.append(f"[{keyword}] 命中行是空行: {rel}:{lineno}")
                continue
            if keyword not in line:
                problems.append(
                    f"[{keyword}] 该行不含查询词: {rel}:{lineno} -> {line!r}"
                )

    assert total > 0, "B5 没有检查到任何命中，判据未被执行"
    assert not problems, "B5 命中有效性未通过:\n" + "\n".join(problems[:20])


def test_b6_found_is_total_not_truncated(foam_env):
    """B6（新增）：`--limit` 只截断输出行数，不改 FOUND 的语义。

    这是 2026-10-28 验收时发现的一个实现与规格不符：规格写「n = 命中文件数」，
    首版实现成了「输出行数」，于是 `--limit 3` 时报 FOUND=3 而实际有 28 个候选。
    下游（C 模块选派生源）会因此误判「库里只有 3 个候选」。

    判据必须同时证明两件事：①FOUND 与不带 limit 时一致；②SHOWN 真的被截断。
    只证①不证②，把 --limit 改成空操作也能过——那是单向测试。
    """
    full = run_find(foam_env, "--keyword", "cavity")
    hits_full, found_full = parse_hits(full.stdout)
    assert found_full == len(hits_full) and found_full > 3, "前置：cavity 的命中数应 > 3"

    limited = run_find(foam_env, "--keyword", "cavity", "--limit", "3")
    hits_lim, found_lim = parse_hits(limited.stdout)

    assert len(hits_lim) == 3, f"--limit 3 应只输出 3 行，实得 {len(hits_lim)}"
    assert found_lim == found_full, (
        f"--limit 不得改变 FOUND：全量 {found_full} vs 截断 {found_lim}")
    assert hits_lim == hits_full[:3], "截断必须是排序后的前 3 条，不能重新抽样"
