#!/usr/bin/env python3
"""模块 G：校验项目两份**固定契约** —— `bench/results.csv` 的表头与取值、`case.meta` 的 schema。

规格：编排方下发的 G 规格（唯一权威）+ `AGENTS.md` R12（results.csv 列固定、结果状态七态）
+ `AGENTS.md` R3（case.meta 六键）。本文档不重复规格，只写"为什么这么做"。

===============================================================================
这是**脚本**不是测试辅助
===============================================================================
M2 的 `bench/batch.py` 与 M4b 的 adapter 将来要复用它，所以：

  [1] 判据全部是纯函数：`check_results(path, states)` / `check_case_meta(path, tutorials)`
      → 返回**违规清单**（`list[str]`，空清单 = 合规）。不 print、不 sys.exit、不读环境变量。
  [2] CLI `main()` 只做三件事：解析参数、调 [1]、把清单翻译成退出码（0 / 40 / 64）。
  [3] 调用方（batch.py）可以 import [1] 拿到逐条违规，而不必去解析 stderr。

**七态不是本文件的常量**：从 `bench/judge.py` 导入 `STATES`。重写一份就必然分叉——
judge 改了七态而校验器还在用旧的，是静默通过，没有任何东西会红（这正是 R12 说的
"只有门时 agent 什么都不改也能 pass" 的同类错误）。导入失败 → 退 40 并说明，
**不自己编一份常量兜底**。

退出码（与 `parse_requirement.py` / `verify_case.sh` 统一口径）：
    0  = 合规
    40 = 契约违规（逐条打印违规行到 stderr）
    64 = 用法错误（含输入文件不存在/不是 UTF-8 —— 那是"我调错了"，不是"契约坏了"）
        argparse 默认是 2，但 2 在 `verify_case.sh` 里是「G2 网格门失败」，
        两者混用会让调用方无法区分「我传错了路径」与「这个 case 网格没过」。

===============================================================================
--results 的五条判据（顺序即报告顺序）
===============================================================================
  1. 表头**逐字**等于 15 列（顺序 / 大小写 / 空格全敏感）。不做 strip：表头里多一个空格
     会让 `csv.DictReader` 读出 ` task_id` 这种键，下游按名取值得 None，而它不会报错。
  2. 每行数据列数 == 15。列数不对时**不再**做字段检查——按名取值必然错位，
     多报 4 条无意义的字段违规只会淹没真正那条。
  3. `status` ∈ 七态。
  4. `g1..g5` ∈ `{0, 1, unmeasured}`（`unmeasured` 与七态里的 `no_artifact` 是两回事：
     前者是"这一门没测"，后者是"整个 run 没产物"）。
  5. `human_interventions` 非空。未测时必须写字面量 `unmeasured` —— 空串会被
     Excel/awk 读成 0，而"没测"与"零次干预"是相反的含义（R12 的主指标是人工干预次数）。

数据行的字段值做 `strip()` 后判定（容忍手写 CSV 的逗号后空格）；**表头不做**，理由见 1。

--case-meta 的八条判据：六键齐、`source` 非空 str、`derived_at` 可被
`datetime.fromisoformat()` 解析、`spec` 是 dict、`changes` 是 list、`allowed_files` 是非空
list 且元素全 str、`schema_version == 1` **且必须是 int**（`"1"` 算违规：JSON 里字符串
"1" 与数字 1 是不同的类型，允许它等于允许下游 `==` 比较静默通过而 `int()` 抛错）、
`source` 指向的目录存在（**仅当传了 `--tutorials`**）。

`source` 存在性只在给了 `--tutorials` 时校验：默认情况下本脚本不假设 `$FOAM_TUTORIALS`
指向哪里（R1 的搜索根只有那五个，不该由校验器替用户猜）。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 契约常量（逐字，勿改）
# ---------------------------------------------------------------------------

#: `bench/results.csv` 的 15 列，顺序即判据（R12 逐字）
RESULTS_COLUMNS = (
    "task_id",
    "arm",
    "status",
    "g1",
    "g2",
    "g3",
    "g4",
    "g5",
    "g2b",
    "repeats",
    "unstable",
    "tokens_total",
    "wall_time_s",
    "human_interventions",
    "note",
)

#: 五个闸门列（`g2b` 是辅助信号不是门，见 R12，所以不在此列）
GATE_COLUMNS = ("g1", "g2", "g3", "g4", "g5")

#: 闸门列的取值域：0/1 = 门判过/没过，unmeasured = 短路或未执行
GATE_VALUES = ("0", "1", "unmeasured")

#: `case.meta` 的六个键（R3 + new_case.sh 写出的形状）
CASE_META_KEYS = (
    "source",
    "derived_at",
    "spec",
    "changes",
    "allowed_files",
    "schema_version",
)

#: 唯一的 schema 版本。改这里等于改契约，必须同时改 new_case.sh 与所有 fixture。
SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_VIOLATION = 40
EXIT_USAGE = 64


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------

class ContractError(Exception):
    """契约层面的致命错误（不是"某一行违规"，而是"没法判"）。

    目前只有一个来源：`bench/judge.py` 的 `STATES` 导入失败。这种情况退 40 而不是 0：
    "判不了"绝不能记成"合规"——沿用 R12 对 `undeterminable` 的要求。
    """


class UsageError(Exception):
    """调用方用错了（路径不存在、不是 UTF-8 文本）→ 退出码 64。"""


# ---------------------------------------------------------------------------
# 七态：从 judge 导入，不重写
# ---------------------------------------------------------------------------

def load_states() -> tuple[str, ...]:
    """返回 `bench/judge.py` 的 `STATES`（结果状态七态的唯一权威）。

    `scripts/` 与 `bench/` 是兄弟目录，所以优先用 `parents[1]`（项目根）拼 `bench`；
    若脚本被搬到别处（或符号链接），再退回"从本文件向上找含 bench/judge.py 的目录"，
    避免因相对深度变化而静默导入失败。
    """
    here = Path(__file__).resolve()
    candidates = [here.parents[1] / "bench"] + [p / "bench" for p in here.parents]
    bench_dir = next(
        (c for c in candidates if (c / "judge.py").is_file()),
        None,
    )
    if bench_dir is None:
        raise ContractError(
            "找不到 bench/judge.py：七态常量 STATES 是结果的唯一权威，"
            "本脚本不允许自己再写一份。请在项目根下运行，或修好 bench/judge.py。"
        )

    if str(bench_dir) not in sys.path:
        sys.path.insert(0, str(bench_dir))
    try:
        from judge import STATES  # noqa: PLC0415  （延迟导入：只有 --results 才需要）
    except ImportError as exc:  # pragma: no cover - judge.py 已实测可导入
        raise ContractError(
            f"从 {bench_dir / 'judge.py'} 导入 STATES 失败：{exc}. "
            "不自己编一份常量兜底——那会让校验器与 judge 悄悄分叉。"
        ) from exc

    states = tuple(STATES)
    if not states:  # 空元组会让"任何 status 都违规"，错误形态太隐蔽，显式拦下
        raise ContractError(f"{bench_dir / 'judge.py'} 的 STATES 是空的，无法判定 status")
    return states


# ---------------------------------------------------------------------------
# 读文件（把"读不到"与"不合契约"分开）
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    """读 UTF-8 文本；读不到 → `UsageError`（64），不混进违规清单。"""
    if not path.exists():
        raise UsageError(f"输入文件不存在: {path}")
    if not path.is_file():
        raise UsageError(f"输入不是普通文件: {path}")
    try:
        # utf-8-sig：容忍 Windows 编辑器加的 BOM（BOM 不在列名里，不该算表头违规）
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise UsageError(f"读不了 {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise UsageError(f"{path} 不是 UTF-8 文本: {exc}") from exc


# ---------------------------------------------------------------------------
# [1a] results.csv 校验（纯函数）
# ---------------------------------------------------------------------------

def _header_problems(header: list[str]) -> list[str]:
    """把"表头不等于 15 列"拆成可操作的几条：缺哪列、多哪列、第几列错。"""
    problems: list[str] = []
    expected = list(RESULTS_COLUMNS)

    if len(header) != len(expected):
        problems.append(
            f"表头列数 {len(header)} != {len(expected)}"
            f"（期望：{','.join(expected)}；实际：{','.join(header)}）"
        )

    # 逐列比对，只报前几条，避免 15 列全错时刷屏
    mismatches = [
        f"第 {i + 1} 列：期望 {expected[i]!r}，实际 {header[i]!r}"
        for i in range(min(len(expected), len(header)))
        if expected[i] != header[i]
    ]
    problems.extend(mismatches[:5])
    if len(mismatches) > 5:
        problems.append(f"……另有 {len(mismatches) - 5} 列不符")

    missing = [name for name in expected if name not in header]
    extra = [name for name in header if name not in expected]
    if missing:
        problems.append(f"缺少列: {','.join(missing)}")
    if extra:
        problems.append(f"多余的列: {','.join(extra)}")

    return problems or ["表头不符（原因未定位，请人工比对）"]


def check_results(path: Path, states: tuple[str, ...]) -> list[str]:
    """校验 `bench/results.csv`，返回违规清单（空 = 合规）。纯函数：无 print / 无退出。"""
    text = _read_text(path)
    records = list(csv.reader(io.StringIO(text)))

    if not records:
        return ["文件为空：缺表头行"]

    problems: list[str] = []
    header = records[0]
    if tuple(header) != RESULTS_COLUMNS:
        problems.extend(_header_problems(header))

    for lineno, record in enumerate(records[1:], start=2):
        if not record:  # 末尾空行 / 纯空行：不是一行数据，不判
            continue
        if len(record) != len(RESULTS_COLUMNS):
            problems.append(
                f"第 {lineno} 行：列数 {len(record)} != {len(RESULTS_COLUMNS)}"
                f"（该行字段级检查已跳过：按名取值会错位）"
            )
            continue

        row = dict(zip(RESULTS_COLUMNS, (cell.strip() for cell in record)))

        if row["status"] not in states:
            problems.append(
                f"第 {lineno} 行：status={row['status']!r} 不在七态 {states}"
            )

        for column in GATE_COLUMNS:
            if row[column] not in GATE_VALUES:
                problems.append(
                    f"第 {lineno} 行：{column}={row[column]!r} 不在 {GATE_VALUES}"
                )

        if not row["human_interventions"]:
            problems.append(
                f"第 {lineno} 行：human_interventions 为空；"
                "未测时必须写字符串 unmeasured（空串会被读成 0 次干预）"
            )

    return problems


# ---------------------------------------------------------------------------
# [1b] case.meta 校验（纯函数）
# ---------------------------------------------------------------------------

def _is_int(value: object) -> bool:
    """真 int，排除 bool（`True == 1`，JSON 里 `true` 不该被当成 schema_version=1）。"""
    return isinstance(value, int) and not isinstance(value, bool)


def check_case_meta(path: Path, tutorials: Path | None = None) -> list[str]:
    """校验 `case.meta`，返回违规清单（空 = 合规）。纯函数：无 print / 无退出。

    `tutorials` 给定时才校验 `(tutorials / source).is_dir()`；给 None 跳过。
    """
    text = _read_text(path)
    try:
        meta = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"case.meta 不是合法 JSON: {exc}"]

    if not isinstance(meta, dict):
        return [f"case.meta 顶层必须是 JSON 对象，实际是 {type(meta).__name__}"]

    problems: list[str] = []

    # ① 六键齐（逐条点名缺的那个键：只报"缺键"看不出是哪一个）
    for key in CASE_META_KEYS:
        if key not in meta:
            problems.append(f"缺键: {key}")

    # ② source：非空 str
    source = meta.get("source")
    source_ok = isinstance(source, str) and bool(source.strip())
    if "source" in meta and not source_ok:
        problems.append(f"source 必须是非空字符串，实际是 {source!r}")

    # ③ derived_at：能被 datetime.fromisoformat() 解析
    if "derived_at" in meta:
        derived_at = meta["derived_at"]
        if not isinstance(derived_at, str):
            problems.append(f"derived_at 必须是字符串，实际是 {derived_at!r}")
        elif not derived_at.strip():
            problems.append("derived_at 为空字符串")
        else:
            try:
                datetime.fromisoformat(derived_at)
            except ValueError as exc:
                problems.append(
                    f"derived_at={derived_at!r} 不是合法 ISO8601（{exc}）"
                )

    # ④ spec：dict
    if "spec" in meta and not isinstance(meta["spec"], dict):
        problems.append(f"spec 必须是 JSON 对象(dict)，实际是 {type(meta['spec']).__name__}")

    # ⑤ changes：list
    if "changes" in meta and not isinstance(meta["changes"], list):
        problems.append(
            f"changes 必须是 JSON 数组(list)，实际是 {type(meta['changes']).__name__}"
        )

    # ⑥ allowed_files：非空 list，元素全 str
    if "allowed_files" in meta:
        allowed = meta["allowed_files"]
        if not isinstance(allowed, list):
            problems.append(
                f"allowed_files 必须是 JSON 数组(list)，实际是 {type(allowed).__name__}"
            )
        else:
            if not allowed:
                problems.append(
                    "allowed_files 不能为空列表：空白名单会让 G5 越界门失去判据"
                )
            bad = [item for item in allowed if not isinstance(item, str)]
            if bad:
                problems.append(f"allowed_files 的元素必须是字符串，违规元素: {bad!r}")

    # ⑦ schema_version：必须是 int 且 == 1（"1" 字符串算违规）
    if "schema_version" in meta:
        version = meta["schema_version"]
        if not _is_int(version):
            problems.append(
                f"schema_version 必须是整数 {SCHEMA_VERSION}，实际是 "
                f"{type(version).__name__} {version!r}"
            )
        elif version != SCHEMA_VERSION:
            problems.append(
                f"schema_version={version} != {SCHEMA_VERSION}（未知版本不可判）"
            )

    # ⑧ source 的存在性：只在给了 --tutorials 时校验
    if tutorials is not None and source_ok:
        resolved = Path(tutorials) / source
        if not resolved.is_dir():
            problems.append(
                f"source={source!r} 指向的目录不存在: {resolved}"
                f"（--tutorials={tutorials}；R3 要求派生来源可追溯）"
            )

    return problems


# ---------------------------------------------------------------------------
# [2] CLI
# ---------------------------------------------------------------------------

class _UsageParser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64（理由见模块 docstring 的退出码段）。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _UsageParser(
        description=(
            "校验固定契约：--results 查 bench/results.csv 的表头与取值；"
            "--case-meta 查 case.meta 的六键 schema。两者互斥。"
        ),
        epilog="退出码：0 合规 / 40 契约违规 / 64 用法错误",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--results", metavar="CSV", help="bench/results.csv 路径")
    mode.add_argument("--case-meta", metavar="JSON", help="case.meta 路径")
    parser.add_argument(
        "--tutorials",
        metavar="DIR",
        default=None,
        help="tutorial 根目录；只在 --case-meta 下用来校验 source 存在性（不给则跳过）",
    )
    args = parser.parse_args(argv)

    try:
        if args.results is not None:
            if args.tutorials is not None:
                parser.error("--tutorials 只能与 --case-meta 一起使用（--results 没有 source 概念）")
            states = load_states()
            problems = check_results(Path(args.results), states)
            subject = f"results.csv={args.results}"
        else:
            problems = check_case_meta(
                Path(args.case_meta),
                Path(args.tutorials) if args.tutorials is not None else None,
            )
            subject = f"case.meta={args.case_meta}"
    except UsageError as exc:
        print(f"check_contracts: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except ContractError as exc:
        print(f"check_contracts: 无法判定契约: {exc}", file=sys.stderr)
        return EXIT_VIOLATION

    if problems:
        print(f"[violation] {subject}：{len(problems)} 条违规", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return EXIT_VIOLATION

    print(f"[ok] {subject}：合规")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
