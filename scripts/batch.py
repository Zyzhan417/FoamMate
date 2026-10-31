#!/usr/bin/env python3
"""模块 H：批量运行（M2）—— 读一个参数矩阵，逐例 派生 / 改参数 / 跑 / 过门禁 / 记账。

规格来源：AGENTS.md R7（批量产物必须落盘）+ R12（results.csv 15 列 = 唯一列定义）
+ `references/00-project-readme.md:350`（M2 完成判据：3 例矩阵产出 results.csv 且数字可从
CSV 重算）+ STATUS.md N3 #32–#33（2026-10-29 用户裁定：v0.2 只做 M2、15 列、默认串行）。

===============================================================================
一、这个脚本**不做**什么（与 P1 的分工一致）
===============================================================================
  - 不猜参数位置。`{file, entry}` 必须由用户在 cases.json 里写全。内置一张
    「nu → constant/physicalProperties」的映射表看似贴心，实则是「凭记忆写字典」，
    换个 tutorial 就不成立（R1 的形态）。
  - 不做物理判断。参数取什么值、网格够不够，由用户定；batch 只负责如实记账。
  - 不改结构。参数只能落在 `{file, entry, new_value}` 这个形状里（同 fix_case.py 的 D24：
    「加 dict 块 / 缺整个文件」这类结构修复表达不了）。
    → **尺寸扫描请用 `system/blockMeshDict` 的 `convertToMeters`**（标量，等价于
      「单位几何 × 尺度」）；改 `vertices` 表是结构改动，当前词汇表达不了。

===============================================================================
二、cases.json 形状（base + vary 的笛卡尔积）
===============================================================================
{
  "base": {
    "id": "cavity",                                   // 必填，只允许 [A-Za-z0-9_.-]
    "source": "incompressibleFluid/cavity",           // 必填，$FOAM_TUTORIALS 下的相对路径
    "spec_file": "cavity.spec.json",                  // 与 spec 二选一；相对 cases.json 所在目录
    "spec": {"geometry": "...", "objective": "steady"},   // 内联四元组（二选一）
    "set": [{"file": "constant/momentumTransport",
             "entry": "simulationType", "new_value": "laminar"}],   // 可选，作用于每个 case
    "allowed": ["system/*", "constant/*", "0/*"]      // 可选，写进 case.meta.allowed_files
  },
  "vary": [                                            // 可选；缺省 = 只有 base 一个 case
    {"name": "cm", "file": "system/blockMeshDict",
     "entry": "convertToMeters", "values": ["0.1", "0.05"]},
    {"name": "nu", "file": "constant/physicalProperties",
     "entry": "nu", "values": ["1e-05", "1e-06"]}
  ]
}

展开规则（三条，都可判定）：
  1. `vary` 里每一项都是一维；结果 = 所有维度的**笛卡尔积**，顺序固定按声明顺序。
  2. case id = `base.id` + 每维 `_<name><value>`（value 小写、非 `[a-z0-9.-]` 换成 `-`）。
     例：`cavity_cm0.1_nu1e-05`。
  3. 同一 `{file, entry}` 在 base.set 与某个 vary 项里同时出现时，**vary 胜出**
     （vary 是按维覆盖，base.set 是公共基线）。

**展开上限 50 例**（`--max-cases` 可调）。超上限直接报错不跑——因为展开是隐式的，
3 维 × 4 值 = 64 例，跑到一半才发现就太晚了。`--dry-run` 会先把展开结果逐行打出来。

===============================================================================
三、每个 case 的目录布局（与 verify_case.sh / R7 一致）
===============================================================================
  runs/<批次>/<case_id>/
    case/            派生的 case 树（new_case.sh --dest）
    case.meta        **从 case/ 移到 run 根**——见下面这段为什么必须移
    base/            改参数**之前**的基线（G5 用它做 git diff；没有 base 时 G5 退化成
                     mtime 比较，那正是 P5 第一轮「85 项假红」的根源）
    spec.json        本例实际用的四元组（可溯源）
    log.g1..log.g5   五道门的日志（verify_case.sh 写）
    log.blockMesh / log.checkMesh / log.shortRun / log.run   求解日志（run_case.sh 写）
    metrics.json     额外指标（不进 CSV，见 §五）
    batch.log        本例所有阶段的命令与输出（排查用）

**为什么 case.meta 必须放到 run 根**：`verify_case.sh` 的 meta 查找顺序是
`<case>/case.meta` → `<log>/case.meta`，**都不会去 `<case>/case/case.meta` 找**；
而 `new_case.sh` 恰恰把它写在 case 树里。batch 派生完就把它移到 run 根，
于是 run 根是**唯一**合法位置（两个位置都有会被 judge 判 malformed，见决策 #17）。

===============================================================================
四、失败策略（四层，2026-10-29 用户裁定）
===============================================================================
  | 失败点                       | 处置                        | status      | g1..g5        |
  |------------------------------|-----------------------------|-------------|---------------|
  | 派生失败（new_case 12/13）   | 记录并继续                  | no_artifact | 全 unmeasured |
  | 参数应用失败（fix_case 31-33）| 记录并继续（不跑求解）      | malformed   | 全 unmeasured |
  | pre 门失败（verify 1/5）     | **跳过求解**省机时，继续     | fail        | g1/g5 实测；  |
  |                              |                             |             | g2/g3/g4 未测 |
  | 求解失败（20/21/23）         | 仍跑 post 门禁，如实记账     | fail        | 五门全实测    |
  | 环境缺失（run_case 22）      | **中止整批**，剩余标 blocked | blocked     | 全 unmeasured |

  最后一条的理由：22 = PATH 里没有 foamRun，是整批性的环境问题。继续跑只会得到
  一行又一行相同的 22，纯粹浪费。所以它是唯一会中止整批的情形。

===============================================================================
五、results.csv 的 15 列（R12 是唯一列定义；本脚本不自造列）
===============================================================================
  task_id=case_id / arm="ours" / status=七态 / g1..g5=0|1|unmeasured / g2b=日志原值
  / repeats=1 / unstable=0 / tokens_total=0 / wall_time_s=本脚本实测墙钟 / human_interventions=0
  / note=批次与原因摘要

  三处刻意的取值，理由必须一起读：
  - **repeats=1, unstable=0**：A 形态没有 LLM，是确定性的（同一输入同一输出）。
    R12 的「每任务跑 3 次取多数」是为模型非确定性准备的（prereg §11）。代价是：
    M2 的行与 bench 的行（repeats=3）在稳定性维度上不可比，note 里写明这一点。
  - **tokens_total=0**：A 形态不消耗 token，这是可测事实而不是待测项。
  - **human_interventions=0**：批跑全自动、无人介入，真的是 0 次。
    注意它与 check_contracts 的约定不冲突——那个约定是「**未测时**必须写 unmeasured，
    不许留空（空串会被读成 0 次）」；这里是测过且为 0。

  **额外指标（末时刻 |U|max、cells、Re、RES 判定）不进 CSV**，写到
  `runs/<批次>/<case_id>/metrics.json`。理由：15 列是封闭契约（顺序即判据），
  写进 note 就不可重算（R7 要求「结论能从 CSV 重算」，note 是自由文本）。

===============================================================================
六、退出码
===============================================================================
  0  整批跑完，且没有任何 case 失败（全 pass）
  70 整批跑完，但有 case 是 fail / malformed / no_artifact / blocked（结果仍可用，逐行看）
  71 整批中止：环境缺失（22）/ 展开超上限 / cases.json 非法
  64 用法错误（未知参数、缺 --cases、--jobs 非法…）

  为什么 70/71 不用 1/2：1–5 在 verify_case.sh 里是「第几个门失败」，batch 的总码若也用
  就会与「某一例的 G2 没过」混淆；70/71 落在所有既有业务码区间之外。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK = 0
EXIT_HAD_FAILURES = 70
EXIT_ABORTED = 71
EXIT_USAGE = 64

#: 展开上限的缺省值。3 维 × 4 值 = 64 例，跑到一半才发现代价太大。
DEFAULT_MAX_CASES = 50
#: 并发上限（R7：本机内存有限，历史 OOM 事故，N ≤ 2 起步）
MAX_JOBS = 2

COLUMNS = (
    "task_id", "arm", "status", "g1", "g2", "g3", "g4", "g5", "g2b",
    "repeats", "unstable", "tokens_total", "wall_time_s", "human_interventions", "note",
)
GATE_COLUMNS = ("g1", "g2", "g3", "g4", "g5")
ARM_NAME = "ours"
ID_RE = re.compile(r"^[a-z0-9_.-]+$")


class Usage(Exception):
    """用法错误 → 64。"""


class _Parser(argparse.ArgumentParser):
    """argparse 默认的用法错误退 2，这里统一改成 64。

    2 在 `verify_case.sh` 里是「G2 网格门失败」，混用会让调用方无法区分
    「我调错了」与「这个 case 网格没过」——两者处置完全相反。
    """

    def error(self, message: str):  # noqa: D401 - argparse 挂钩
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: 用法错误: {message}\n")
        raise SystemExit(EXIT_USAGE)


class Aborted(Exception):
    """整批中止 → 71。"""


# ---------------------------------------------------------------------------
# STATES 只能从 bench/judge.py 导入（DRY：重写一份必然分叉）
# ---------------------------------------------------------------------------

#: batch 能产出的状态 —— **是七态的子集，不是七态全集的副本**。
#:
#: 为什么不 `from bench.judge import STATES`（2026-10-29 实测的发布缺陷）：
#: `bench/` 是仓库级的跨项目基准框架，**不随发布包发布**；而 `batch.py` 在包里。
#: 于是「从 judge.py 导入」在仓库里能跑、解出 tar.gz 就崩：
#:     batch.py: 中止: 找不到 .../bench/judge.py：七态定义必须从 judge.py 导入
#: 发布物必须自包含，所以包内不能有这个依赖。
#:
#: **单一事实源仍然是 `bench/judge.py` 的 `STATES`**——`tests/unit/test_batch.py`
#: 断言 `EMITTABLE ⊆ judge.STATES`：谁改了七态的拼写而没同步这里，那条测试立刻红。
#: 这样"包自包含"与"不许重写常量"两件事同时成立，没有靠约定维持的灰色地带。
EMITTABLE = ("pass", "fail", "no_artifact", "malformed", "blocked")


# ---------------------------------------------------------------------------
# cases.json 的解析与展开
# ---------------------------------------------------------------------------

@dataclass
class Varied:
    name: str
    file: str
    entry: str
    values: list[str]


@dataclass
class Base:
    id: str
    source: str
    spec: dict | None = None
    spec_file: str | None = None
    set: list[dict] = field(default_factory=list)
    allowed: list[str] | None = None


@dataclass
class Case:
    id: str
    source: str
    spec: dict | None
    spec_file: str | None
    set: list[dict]
    allowed: list[str] | None


def sanitize(value: str) -> str:
    """把参数值变成目录名安全的一段：小写，非 `[a-z0-9.-]` 一律换成 `-`。"""
    out = re.sub(r"[^a-z0-9.-]", "-", str(value).strip().lower())
    out = re.sub(r"-+", "-", out).strip("-")
    return out or "x"


def _require(obj: dict, key: str, where: str):
    if key not in obj or obj[key] in (None, ""):
        raise Aborted(f"{where} 缺必填字段 `{key}`")
    return obj[key]


def parse_cases(path: Path) -> tuple[Base, list[Varied]]:
    """解析 cases.json。任何结构问题都抛 Aborted（71）并指名道姓。"""
    if not path.is_file():
        raise Aborted(f"cases.json 不存在: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Aborted(f"cases.json 不是合法 JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise Aborted("cases.json 顶层必须是对象")

    raw_base = doc.get("base")
    if not isinstance(raw_base, dict):
        raise Aborted("cases.json 缺 `base` 对象")

    base = Base(
        id=str(_require(raw_base, "id", "base")),
        source=str(_require(raw_base, "source", "base")),
        spec=raw_base.get("spec"),
        spec_file=raw_base.get("spec_file"),
        set=list(raw_base.get("set") or []),
        allowed=raw_base.get("allowed"),
    )

    if not ID_RE.match(base.id.lower()):
        raise Aborted(
            f"base.id={base.id!r} 含非法字符：只允许 [A-Za-z0-9_.-]（它会被用作目录名）"
        )
    if base.spec is None and not base.spec_file:
        raise Aborted("base 必须给 `spec`（内联四元组）或 `spec_file`（指向 JSON 文件）之一")
    if base.spec is not None and base.spec_file:
        raise Aborted("base 的 `spec` 与 `spec_file` 只能给一个（两个都给会让「以哪个为准」不可判定）")
    if base.allowed is not None and not isinstance(base.allowed, list):
        raise Aborted("base.allowed 必须是字符串数组")

    for i, item in enumerate(base.set):
        _check_set_item(item, f"base.set[{i}]")

    varies: list[Varied] = []
    raw_vary = doc.get("vary") or []
    if not isinstance(raw_vary, list):
        raise Aborted("`vary` 必须是数组")
    for i, item in enumerate(raw_vary):
        where = f"vary[{i}]"
        if not isinstance(item, dict):
            raise Aborted(f"{where} 必须是对象")
        name = str(_require(item, "name", where))
        if not ID_RE.match(sanitize(name)):
            raise Aborted(f"{where}.name={name!r} 无法用作 id 片段")
        values = _require(item, "values", where)
        if not isinstance(values, list) or not values:
            raise Aborted(f"{where}.values 必须是非空数组")
        varies.append(
            Varied(
                name=name,
                file=str(_require(item, "file", where)),
                entry=str(_require(item, "entry", where)),
                values=[str(v) for v in values],
            )
        )
    return base, varies


def _check_set_item(item: object, where: str) -> None:
    if not isinstance(item, dict):
        raise Aborted(f"{where} 必须是对象")
    for key in ("file", "entry", "new_value"):
        if key not in item:
            raise Aborted(f"{where} 缺 `{key}`（形状必须是 {{file, entry, new_value}}）")
    if item["new_value"] is None:
        raise Aborted(
            f"{where}.new_value 不能是 null：batch 负责「按给定值改」；"
            "「该改成什么」不是它能决定的（同 fix_case.py 的 D23）"
        )


def expand(base: Base, varies: list[Varied], max_cases: int) -> list[Case]:
    """笛卡尔积展开。`vary` 的每一项覆盖 base.set 里同 {file,entry} 的条目。"""
    if not varies:
        combos: list[tuple] = [()]
    else:
        combos = list(itertools.product(*[v.values for v in varies]))

    if len(combos) > max_cases:
        detail = " × ".join(f"{v.name}({len(v.values)})" for v in varies)
        raise Aborted(
            f"展开出 {len(combos)} 例，超过上限 {max_cases}（{detail}）。"
            f" 先用 --dry-run 看一遍，再用 --max-cases 显式放宽"
        )

    cases: list[Case] = []
    seen: dict[str, int] = {}
    for combo in combos:
        suffix = ""
        overrides: dict[tuple[str, str], dict] = {}
        for varied, value in zip(varies, combo):
            suffix += f"_{varied.name}{sanitize(value)}"
            overrides[(varied.file, varied.entry)] = {
                "file": varied.file,
                "entry": varied.entry,
                "new_value": value,
            }
        case_id = (base.id + suffix).lower()
        if case_id in seen:
            raise Aborted(
                f"展开后出现重复 id `{case_id}`（第 {seen[case_id] + 1} 个与本次撞名）："
                "请让 vary 的 values 在 sanitize 后互不相同"
            )
        seen[case_id] = len(cases)

        merged: list[dict] = []
        covered: set[tuple[str, str]] = set()
        for item in base.set:
            key = (item["file"], item["entry"])
            if key in overrides:
                merged.append(overrides[key])
                covered.add(key)
            else:
                merged.append(dict(item))
        for key, item in overrides.items():
            if key not in covered:
                merged.append(item)

        cases.append(
            Case(
                id=case_id,
                source=base.source,
                spec=base.spec,
                spec_file=base.spec_file,
                set=merged,
                allowed=base.allowed,
            )
        )
    return cases


# ---------------------------------------------------------------------------
# 子进程与日志
# ---------------------------------------------------------------------------

def run(cmd: list[str], log: list[str], *, timeout: int | None = None) -> int:
    """跑一个子命令，把命令与输出追加进 `log`（供写 batch.log），返回退出码。"""
    log.append(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.stdout.strip():
        log.append(proc.stdout.rstrip())
    if proc.stderr.strip():
        log.append(f"[stderr] {proc.stderr.rstrip()}")
    log.append(f"[rc={proc.returncode}]")
    return proc.returncode


def read_gate(path: Path) -> tuple[str, str | None]:
    """读 `log.gN` 的第 1 行 `RC=0|1`；`log.g2` 的第 2 行是 `G2B=…`。

    返回 (`0|1|unmeasured`, g2b)。文件不存在或格式不对 → unmeasured（不猜）。
    """
    if not path.is_file():
        return "unmeasured", None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "unmeasured", None
    rc = "unmeasured"
    if lines:
        m = re.match(r"^RC=([01])\s*$", lines[0].strip())
        if m:
            rc = m.group(1)
    g2b = None
    if path.name == "log.g2":
        for line in lines[1:]:
            m = re.match(r"^G2B=(\S+)\s*$", line.strip())
            if m:
                g2b = m.group(1)
                break
    return rc, g2b


def parse_diagnostics(text: str) -> dict[str, str]:
    """从 post 门禁的 stdout 里抠出诊断行（OBJ= / GEO= / RE= / RES=）。"""
    out: dict[str, str] = {}
    for line in text.splitlines():
        for key in ("OBJ", "GEO", "RE", "RES"):
            if line.startswith(f"{key}="):
                out[key] = line
    return out


# ---------------------------------------------------------------------------
# 单个 case 的执行
# ---------------------------------------------------------------------------

def wall_seconds(delta: float) -> float:
    """墙钟秒数 → 写进 CSV 的值。**保留两位小数是刻意的**。

    短跑常在 1 秒内结束。若这里取整（`int(round(...))`），12 例全写成 0，
    而 R7 要求「结论能从 CSV 重算」——0 秒的 0 不携带信息，那条要求就落空了
    （这是 v0.2 的 F7 缺陷）。

    抽成纯函数是为了能被**确定性**地测：把取整写回 `int()`，单元测试立刻红，
    不依赖机器当时多快。
    """
    return round(float(delta), 2)


@dataclass
class Outcome:
    case_id: str
    status: str
    gates: dict[str, str]
    g2b: str
    wall_time_s: float
    note: str
    metrics: dict
    aborted: str | None = None


class Runner:
    def __init__(self, *, scripts: Path, run_root: Path, mode: str, timeout: int,
                 spec_base: Path):
        self.scripts = scripts
        self.run_root = run_root
        self.mode = mode
        self.timeout = timeout
        #: spec_file 的相对路径按 **cases.json 所在目录** 解析（不是 cwd）——
        #: 否则「在哪个目录下调用 batch」会改变它引用哪个文件，那是不可判定。
        self.spec_base = spec_base

    # -- 各阶段 ------------------------------------------------------------

    def _derive(self, case: Case, run_dir: Path, log: list[str]) -> int:
        spec_path = run_dir / "spec.json"
        if case.spec is not None:
            spec_path.write_text(
                json.dumps(case.spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        else:
            src = Path(case.spec_file or "")
            if not src.is_absolute():
                src = (self.spec_base / src).resolve()
            if not src.is_file():
                raise Aborted(f"spec_file 不存在: {src}（相对路径按 cases.json 所在目录解析）")
            shutil.copyfile(src, spec_path)

        cmd = [
            str(self.scripts / "new_case.sh"),
            "--source", case.source,
            "--dest", str(run_dir / "case"),
            "--spec", str(spec_path),
        ]
        if case.allowed:
            cmd += ["--allowed", ",".join(case.allowed)]
        return run(cmd, log)

    def _apply(self, case: Case, run_dir: Path, log: list[str]) -> int:
        if not case.set:
            return 0
        payload = json.dumps(
            [{"file": i["file"], "entry": i["entry"], "new_value": i["new_value"]} for i in case.set],
            ensure_ascii=False,
        )
        cmd = [
            sys.executable, str(self.scripts / "fix_case.py"),
            # 注意：fix_case.py **没有** 位置参数的 "apply" 子命令——模式由给哪个 flag 决定
            # （--apply = 应用改动；--error-log = 定位）。多写一个 "apply" 会被 argparse
            # 当成 unrecognized arguments 并退 64（实测踩过）。
            "--case", str(run_dir / "case"),
            "--apply", payload,
            "--attempt", "1",
        ]
        return run(cmd, log)

    def _verify(self, stage: str, run_dir: Path, log: list[str]) -> tuple[int, str]:
        cmd = [
            str(self.scripts / "verify_case.sh"), "--stage", stage,
            "--case", str(run_dir), "--log", str(run_dir),
        ]
        # 不用 run() 是因为 post 的 stdout 里有诊断行，要拿回来解析
        log.append(f"$ {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        if proc.stdout.strip():
            log.append(proc.stdout.rstrip())
        if proc.stderr.strip():
            log.append(f"[stderr] {proc.stderr.rstrip()}")
        log.append(f"[rc={proc.returncode}]")
        return proc.returncode, proc.stdout

    # -- 主流程 ------------------------------------------------------------

    def one(self, case: Case) -> Outcome:
        run_dir = self.run_root / case.id
        if run_dir.exists():
            shutil.rmtree(run_dir)          # 同名批次重跑：日志是唯一证据，不能混着旧的
        run_dir.mkdir(parents=True)

        log: list[str] = [f"### batch case {case.id}", f"### source {case.source}"]
        gates = {g: "unmeasured" for g in GATE_COLUMNS}
        metrics: dict = {"case_id": case.id, "source": case.source}
        g2b = "unknown"
        wall = 0.0

        def finish(status: str, note: str, aborted: str | None = None) -> Outcome:
            (run_dir / "batch.log").write_text("\n".join(log) + "\n", encoding="utf-8")
            metrics["status"] = status
            metrics["gates"] = dict(gates)
            metrics["wall_time_s"] = wall
            (run_dir / "metrics.json").write_text(
                json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            return Outcome(case.id, status, dict(gates), g2b, wall, note, metrics, aborted)

        # ① 派生
        metrics["stage_rc"] = {}
        rc = self._derive(case, run_dir, log)
        metrics["stage_rc"]["derive"] = rc
        if rc != 0:
            return finish(
                "no_artifact",
                f"派生失败（new_case 退 {rc}）：没有 case 树，没有可判对象",
            )

        # ② case.meta 移到 run 根（唯一合法位置，见模块 docstring §三）
        inner_meta = run_dir / "case" / "case.meta"
        if inner_meta.is_file():
            inner_meta.replace(run_dir / "case.meta")
        metrics["case_meta_at"] = "run_root" if (run_dir / "case.meta").is_file() else "missing"

        # ③ 改参数（复用 fix_case.py apply，并把 attempt_1 复用成 G5 的 base/）
        apply_rc = self._apply(case, run_dir, log)
        metrics["stage_rc"]["apply"] = apply_rc
        if apply_rc != 0:
            return finish(
                "malformed",
                f"参数应用失败（fix_case 退 {apply_rc}）：字典没改成预期值，跑了也是假数据",
            )
        attempt = run_dir / "attempt_1"
        if attempt.is_dir():
            attempt.replace(run_dir / "base")

        # ④ pre 门禁
        pre_rc, _ = self._verify("pre", run_dir, log)
        metrics["stage_rc"]["pre"] = pre_rc
        g1, _ = read_gate(run_dir / "log.g1")
        g5, _ = read_gate(run_dir / "log.g5")
        gates["g1"], gates["g5"] = g1, g5
        if pre_rc != 0:
            return finish(
                "fail",
                f"pre 门禁退 {pre_rc}（G1/G5 不过）：跳过求解，g2/g3/g4 未测",
            )

        # ⑤ 求解
        # 墙钟必须用 monotonic：time.time() 会被步进校正回退，实测写出过 wall_time_s=-1.7
        # （CLOCK_REALTIME 在 WSL2 上会倒退）。P-01，2026-10-31 修。
        started = time.monotonic()
        run_cmd = [
            str(self.scripts / "run_case.sh"),
            "--case", str(run_dir / "case"),
            "--mode", self.mode,
            "--log", str(run_dir),
            "--timeout", str(self.timeout),
        ]
        run_rc = run(run_cmd, log, timeout=self.timeout + 60)
        wall = wall_seconds(time.monotonic() - started)
        metrics["stage_rc"]["run"] = run_rc

        if run_rc == 22:
            return finish(
                "blocked",
                "环境缺失（run_case 退 22：PATH 里没有 foamRun）→ 中止整批",
                aborted="22",
            )

        # ⑥ post 门禁（求解失败也要跑：g2 可能是好的，如实记账）
        post_rc, post_out = self._verify("post", run_dir, log)
        metrics["stage_rc"]["post"] = post_rc
        metrics["diagnostics"] = parse_diagnostics(post_out)
        for gate in ("g2", "g3", "g4"):
            value, _ = read_gate(run_dir / f"log.{gate}")
            gates[gate] = value
        _, g2b = read_gate(run_dir / "log.g2")
        g2b = g2b or "unknown"

        bad = [g for g in GATE_COLUMNS if gates[g] == "1"]
        unmeasured = [g for g in GATE_COLUMNS if gates[g] == "unmeasured"]
        if bad:
            reason = "门失败: " + ",".join(bad)
            if run_rc != 0:
                reason += f"（run_case 退 {run_rc}）"
            return finish("fail", reason)
        if unmeasured:
            # 门没测全就不许记 pass —— 这是 R12 对 undeterminable 的要求
            return finish(
                "malformed",
                "门未测全: " + ",".join(unmeasured) + f"（post 退 {post_rc}）",
            )
        return finish("pass", f"五门全过（run_case 退 {run_rc}）")


# ---------------------------------------------------------------------------
# 写 CSV
# ---------------------------------------------------------------------------

def write_results(path: Path, outcomes: list[Outcome], batch_id: str, mode: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for item in sorted(outcomes, key=lambda o: o.case_id):
            note = f"batch={batch_id}; mode={mode}; {item.note}"
            if item.status == "blocked":
                note += "; 整批因环境缺失中止"
            note += "; deterministic harness, single trial"
            writer.writerow(
                {
                    "task_id": item.case_id,
                    "arm": ARM_NAME,
                    "status": item.status,
                    **{g: item.gates[g] for g in GATE_COLUMNS},
                    "g2b": item.g2b,
                    "repeats": 1,
                    "unstable": 0,
                    "tokens_total": 0,
                    "wall_time_s": item.wall_time_s,
                    "human_interventions": 0,
                    "note": note,
                }
            )


def _self_check_csv(path: Path) -> bool:
    """包内自检：列数、状态集合、门取值域。**不依赖任何外部文件**。

    它不替代 `check_contracts.py`（那个还查 case.meta schema、违规定位等），
    只保证"batch 自己写出来的东西至少形状对"——发布包里没有别的检查器可用。
    """
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
    except OSError as exc:
        sys.stderr.write(f"batch: 无法读回自己写的 results.csv: {exc}\n")
        return False
    if not rows or tuple(rows[0]) != COLUMNS:
        sys.stderr.write(f"batch: 表头不对，实得 {rows[0] if rows else '(空文件)'}\n")
        return False
    for lineno, row in enumerate(rows[1:], start=2):
        if len(row) != len(COLUMNS):
            sys.stderr.write(f"batch: 第 {lineno} 行列数 {len(row)} != {len(COLUMNS)}\n")
            return False
        rec = dict(zip(COLUMNS, row))
        if rec["status"] not in EMITTABLE:
            sys.stderr.write(f"batch: 第 {lineno} 行 status={rec['status']!r} 不可产出\n")
            return False
        for gate in GATE_COLUMNS:
            if rec[gate] not in ("0", "1", "unmeasured"):
                sys.stderr.write(f"batch: 第 {lineno} 行 {gate}={rec[gate]!r} 非法\n")
                return False
    return True


def print_expansion(cases: list[Case], batch_id: str, root: Path) -> None:
    print(f"# 批次 {batch_id}：共 {len(cases)} 例（run 根 {root}）")
    print(f"{'case_id':<44}  {'source':<28}  set")
    for case in cases:
        params = ", ".join(f"{i['file']}:{i['entry']}={i['new_value']}" for i in case.set)
        print(f"{case.id:<44}  {case.source:<28}  {params or '(无)'}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = _Parser(
        prog="batch.py",
        description="批量运行：读参数矩阵，逐例派生/改参数/跑/过门禁/写 results.csv",
    )
    parser.add_argument("--cases", required=True, help="cases.json 路径")
    parser.add_argument("--dest", default=None, help="run 根目录，缺省 <仓库根>/runs")
    parser.add_argument("--batch", default=None, help="批次名，缺省 UTC 时间戳")
    parser.add_argument("--mode", default="full", choices=("check", "short", "full"))
    parser.add_argument("--timeout", type=int, default=1800, help="单例求解墙钟上限（秒）")
    parser.add_argument("--jobs", type=int, default=1, help=f"并发数，默认 1，上限 {MAX_JOBS}")
    parser.add_argument("--max-cases", type=int, default=DEFAULT_MAX_CASES,
                        help=f"展开上限，缺省 {DEFAULT_MAX_CASES}")
    parser.add_argument("--dry-run", action="store_true", help="只打印展开结果，不执行")
    args = parser.parse_args(argv)

    if args.jobs < 1 or args.jobs > MAX_JOBS:
        raise Usage(f"--jobs 必须 1..{MAX_JOBS}（R7：本机内存有限，历史 OOM 事故）")
    if args.timeout < 1:
        raise Usage("--timeout 必须是正整数秒")

    states = EMITTABLE
    cases_path = Path(args.cases)
    base, varies = parse_cases(cases_path)
    cases = expand(base, varies, args.max_cases)

    batch_id = args.batch or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    root = Path(args.dest) if args.dest else Path(__file__).resolve().parent.parent / "runs"
    run_root = root / batch_id

    if args.dry_run:
        print_expansion(cases, batch_id, run_root)
        print("\n# --dry-run：未执行任何命令，未创建任何目录")
        return EXIT_OK

    # 环境前置检查：不做的话，12 个 case 会得到 12 行相同的 22
    if shutil.which("foamRun") is None:
        raise Aborted(
            "PATH 里没有 foamRun：先 `source $WM_PROJECT_DIR/etc/bashrc` 再跑 batch。"
            "（这里主动探测，是为了避免每个 case 都退一次 22）"
        )

    scripts = Path(__file__).resolve().parent
    runner = Runner(
        scripts=scripts, run_root=run_root, mode=args.mode, timeout=args.timeout,
        spec_base=cases_path.resolve().parent,
    )

    outcomes: list[Outcome] = []
    aborted: str | None = None

    def handle(case: Case) -> Outcome:
        return runner.one(case)

    if args.jobs == 1:
        for case in cases:
            outcome = handle(case)
            outcomes.append(outcome)
            print(f"{outcome.status:<12} {outcome.case_id}  {outcome.note}", flush=True)
            if outcome.aborted:
                aborted = outcome.aborted
                break
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for outcome in pool.map(handle, cases):
                outcomes.append(outcome)
                print(f"{outcome.status:<12} {outcome.case_id}  {outcome.note}", flush=True)
                if outcome.aborted and aborted is None:
                    aborted = outcome.aborted
        # 并发下无法立刻停止：已提交的会跑完。把未跑到的补成 blocked，保持"每例一行"
        done = {o.case_id for o in outcomes}
        for case in cases:
            if case.id not in done:
                outcomes.append(
                    Outcome(
                        case.id, "blocked", {g: "unmeasured" for g in GATE_COLUMNS},
                        "unknown", 0, "整批中止，本例未执行", {}, aborted="22",
                    )
                )

    if aborted:
        done = {o.case_id for o in outcomes}
        for case in cases:
            if case.id not in done:
                outcomes.append(
                    Outcome(
                        case.id, "blocked", {g: "unmeasured" for g in GATE_COLUMNS},
                        "unknown", 0, "整批中止（环境缺失），本例未执行", {}, aborted=aborted,
                    )
                )

    illegal = sorted({o.status for o in outcomes} - set(states))
    if illegal:
        raise Aborted(f"内部错误：产生了未定义的状态 {illegal}（可产出集合 {states}）")

    results = run_root / "results.csv"
    write_results(results, outcomes, batch_id, args.mode)
    print(f"\n# results.csv → {results}（{len(outcomes)} 行）")

    # 自证契约，分两层（2026-10-29 实测：第二层在发布包里必然不存在）
    #   ① 包内自检：用本文件已有的 COLUMNS / EMITTABLE 校验，**不依赖任何外部文件**；
    #   ② 仓库内全量校验：`check_contracts.py` 存在时才调它（它是治理脚本，不进发布包）。
    # 只做 ② 会让发布包里的 batch 每次都报"契约不满足"——而真实原因是那个文件不存在。
    if not _self_check_csv(results):
        return EXIT_ABORTED
    checker = scripts / "check_contracts.py"
    if checker.is_file():
        check = subprocess.run(
            [sys.executable, str(checker), "--results", str(results)],
            capture_output=True, text=True,
        )
        if check.returncode != 0:
            sys.stderr.write("batch: 写出的 results.csv 不满足契约（这是 batch 的 bug）:\n")
            sys.stderr.write(check.stdout + check.stderr)
            return EXIT_ABORTED
    else:
        print("# 注意：本环境没有 check_contracts.py（发布包内不带它），只做了包内自检")

    if aborted:
        print(f"# 整批中止：{aborted}")
        return EXIT_ABORTED
    if any(o.status != "pass" for o in outcomes):
        print("# 有 case 未通过（逐行看 results.csv 的 status 与 note）")
        return EXIT_HAD_FAILURES
    print("# 全部 pass")
    return EXIT_OK


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Usage as exc:
        sys.stderr.write(f"batch.py: 用法错误: {exc}\n")
        sys.stderr.write("用法: batch.py --cases <cases.json> [--dest DIR] [--batch NAME] "
                         "[--mode full|short|check] [--jobs 1|2] [--dry-run]\n")
        sys.exit(EXIT_USAGE)
    except Aborted as exc:
        sys.stderr.write(f"batch.py: 中止: {exc}\n")
        sys.exit(EXIT_ABORTED)
