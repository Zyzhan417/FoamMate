#!/usr/bin/env python3
"""bench/judge.py — 七态归约器（prereg §4 + §11）。

**职责边界（prereg §11 第 2 条）**：judge 只汇总两个取值入口的结论，**自己不解析任何
OpenFOAM 文件**：
  ① 闸门结论 ← `run/log.g1`…`log.g5` 里的 `RC=0|RC=1` 行（由 scripts/verify_case.sh 写）
  ② 断言结论 ← `run/assert.json` 的 `overall`（由 bench/assert_lib.py 写：match|mismatch|undeterminable）
  ③ 声称/理由 ← `run/arm_stdout.txt`（prereg §11 第 6 条：判 overclaim 与 declined 的唯一输入）

所以本文件对 OpenFOAM **零依赖**：可在无 OpenFOAM、无 LLM key 的机器上跑全部自测。

状态优先级（prereg §4 逐字）：
    blocked > declined > no_artifact > malformed > overclaim > pass/fail

四处本文件做了预注册未逐字规定、但必须定下来的映射（登记在 references/09-…:§10.1）：
  M-a `case/` 存在但缺 `system/controlDict` → **malformed**（目录半成品），
      而"根本没有 case 目录"才是 `no_artifact`（prereg §4 两处措辞分别支持这两读）。
  M-b `case.meta` 缺 `source` → **malformed**（派生来源不可追溯 ⇒ 无法判定，不得记 pass）。
  M-c `overclaim` 只在**闸门**未过时成立；"闸门全过但断言 mismatch" 记 `fail`
      （prereg §4 对 overclaim 的定义是"独立门禁判为未过"，未含断言）。
  M-d **短路合法**：G1/G5 前置（D4）后，pre 阶段就被拦下的 run 不会写 G2–G4。
      若存在 fail，且所有"不可判定"的门序号都大于第一个 fail 的门序号，则记 `fail` 而非
      `malformed`。否则若"不可判定"出现在第一个失败门之前，说明状态自相矛盾，记 `malformed`。

用法：
  python3 bench/judge.py <run_dir>              # 单次 run → 七态之一
  python3 bench/judge.py --task <dir_of_runs>   # 3 次 run 目录 → 任务级 + unstable
退出码：0 判出结果 / 2 用法错误
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

# prereg §4 的七态
STATES = ("pass", "fail", "no_artifact", "malformed", "blocked", "overclaim", "declined")
GATE_NAMES = ("g1", "g2", "g3", "g4", "g5")

# R5 划出的前处理边界（declined 的理由必须指到这三类之一）
R5_MARKERS = ("曲面", "边界层加密", "STL", "snappyHexMesh", "CAD", "多体装配")
# 臂自称完成的标记（prereg §11 第 6 条：这是判 overclaim 的唯一输入）
CLAIM_MARKERS = ("已完成", "已跑通", "完成，", "成功", "done", "success", "completed")

_RC = re.compile(r"^\s*RC\s*=\s*(\d+)\s*$", re.M)
# D7：log.g2 第 2 行。取值域见 prereg §5 的 G2b 行
_G2B = re.compile(r"^\s*G2B\s*=\s*(none|soft:\d+|hard:\d+|unknown)\s*$", re.M)


def _read(p: Path) -> str | None:
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None


def gather(run_dir: Path) -> dict:
    """从 run 目录收集证据。只用文件名与文件内容，不跑任何命令。"""
    run_dir = Path(run_dir)
    blocked = _read(run_dir / "blocked.txt")
    arm = _read(run_dir / "arm_stdout.txt") or ""
    # case.meta 的两个合法位置（D20）：run 根（prereg §12 的写法）或 case 树内
    # （C 的 `--dest` 就是 case 树，它把 meta 写在那里，使 case 自描述、可单独搬走）。
    # **两处都存在 → 判不可判定**：那不是"随便取一个"的问题，而是出现了两份可能漂移的
    # 溯源信息，必须由人决定留哪份，不能让判定器静默选边。
    _meta_root = run_dir / "case.meta"
    _meta_tree = run_dir / "case" / "case.meta"
    meta_ambiguous = _meta_root.is_file() and _meta_tree.is_file()
    if _meta_tree.is_file() and not _meta_root.is_file():
        meta_raw = _read(_meta_tree)
    else:
        meta_raw = _read(_meta_root)
    meta_missing_source = False
    if meta_raw is not None:
        try:
            meta = json.loads(meta_raw)
            meta_missing_source = not str(meta.get("source") or "").strip()
        except json.JSONDecodeError:
            meta_missing_source = True  # meta 坏掉同样无法追溯来源
    else:
        # **完全没有 case.meta** 比「有 meta 但缺 source」更不可追溯，同样判 malformed。
        # 2026-10-28 由新增的 meta 自测组抓到：原实现里 meta_raw is None 时
        # meta_missing_source 保持 False，于是一个没有任何溯源信息的 run 被判 pass。
        # R3 要求每个 case 声明 source；判 pass 等于替它担保了一个它没说的来源。
        meta_missing_source = True

    gates: dict[str, str] = {}
    for g in GATE_NAMES:
        txt = _read(run_dir / f"log.{g}")
        if not txt or not txt.strip():
            gates[g] = "undeterminable"          # 缺失或空 → 不可判定（不是 pass）
            continue
        m = _RC.search(txt)
        if m is None:
            gates[g] = "undeterminable"
        else:
            gates[g] = "pass" if m.group(1) == "0" else "fail"

    g2_txt = _read(run_dir / "log.g2") or ""
    m = _G2B.search(g2_txt)
    g2b = m.group(1) if m else "unknown"   # g2b 不是门（prereg §5）；missing → unknown

    assert_raw = _read(run_dir / "assert.json")
    assert_overall = "undeterminable"
    if assert_raw:
        try:
            assert_overall = json.loads(assert_raw).get("overall", "undeterminable")
        except json.JSONDecodeError:
            assert_overall = "undeterminable"

    return {
        "blocked_reason": (blocked or "").strip() or None,
        "has_case_dir": (run_dir / "case").is_dir(),
        "has_control_dict": (run_dir / "case" / "system" / "controlDict").is_file(),
        "case_meta_missing_source": meta_missing_source,
        "case_meta_ambiguous": meta_ambiguous,
        "gates": gates,
        "g2b": g2b,
        "assert_overall": assert_overall,
        "arm_stdout": arm,
    }


def _claims_success(arm_stdout: str) -> bool:
    low = arm_stdout.lower()
    return any(k in arm_stdout or k in low for k in CLAIM_MARKERS)


def _reason_points_to_r5(arm_stdout: str) -> bool:
    return any(k in arm_stdout for k in R5_MARKERS)


def reduce_run(ev: dict) -> dict:
    """单次 run → {status, reason}。纯函数，按 prereg §4 的优先级逐条排除。"""
    if ev.get("blocked_reason"):
        return {"status": "blocked", "reason": f"环境前置不满足：{ev['blocked_reason']}"}

    if not ev.get("has_control_dict"):
        if _reason_points_to_r5(ev.get("arm_stdout", "")):
            return {"status": "declined", "reason": "无 case，且理由指向 R5 的前处理边界"}
        if not ev.get("has_case_dir"):
            return {"status": "no_artifact", "reason": "没有 case 目录"}
        return {"status": "malformed", "reason": "有 case 目录但缺 system/controlDict（半成品）"}

    gates = ev.get("gates", {})
    undet = [g for g in GATE_NAMES if gates.get(g) not in ("pass", "fail")]
    failed_gates = [g for g in GATE_NAMES if gates.get(g) == "fail"]

    # M-d 短路：D4 把 G1/G5 前置后，pre 阶段被拦下的 run 不会有 log.g2..log.g4。
    # 判据是"序号"：不可判定的门必须全部排在第一个失败门之后，否则状态自相矛盾。
    if failed_gates and undet:
        first = GATE_NAMES.index(failed_gates[0])
        if all(GATE_NAMES.index(g) > first for g in undet):
            undet = []          # 合法短路，继续走下面的失败分支
        else:
            return {"status": "malformed",
                    "reason": f"闸门状态矛盾：{','.join(failed_gates)} 失败，但 {','.join(undet)} 在它之前就缺失"}
    if undet:
        return {"status": "malformed", "reason": f"闸门不可判定：{','.join(undet)}"}
    if ev.get("case_meta_ambiguous"):
        return {"status": "malformed", "reason": "case.meta 同时存在于 run 根与 case 树，溯源信息有二义"}
    if ev.get("case_meta_missing_source"):
        return {"status": "malformed", "reason": "case.meta 缺 source，派生来源不可追溯"}

    if failed_gates:
        if _claims_success(ev.get("arm_stdout", "")):
            return {"status": "overclaim",
                    "reason": f"自称完成但未过 {','.join(failed_gates)}"}
        return {"status": "fail", "reason": f"未过 {','.join(failed_gates)}"}

    a = ev.get("assert_overall", "undeterminable")
    if a == "undeterminable":
        return {"status": "malformed", "reason": "断言不可判定（undeterminable 不得记 pass/fail）"}
    if a == "mismatch":
        return {"status": "fail", "reason": "五门全过但 expect_values mismatch（需求未满足）"}
    return {"status": "pass", "reason": "G1–G5 全过且 expect_values 全 match"}


def judge_run(run_dir: Path) -> dict:
    ev = gather(run_dir)
    r = reduce_run(ev)
    r["g2b"] = ev["g2b"]        # 只透传，不参与 status（prereg §5：G2b 不是门）
    return r


def reduce_task(runs: list[dict]) -> dict:
    """多次 run → 任务级。多数归约；全部互异 → malformed + unstable=1（prereg §11 第 3 条）。"""
    states = [r["status"] for r in runs]
    if not states:
        return {"status": "malformed", "unstable": 1, "repeats": 0,
                "reason": "没有任何 run（空样本不得记 pass/fail）"}
    if len(states) > 1 and len(set(states)) == len(states):
        return {"status": "malformed", "unstable": 1, "repeats": len(states),
                "reason": f"{len(states)} 次结果互异：{','.join(states)}"}
    top, n = Counter(states).most_common(1)[0]
    return {"status": top, "unstable": 0, "repeats": len(states),
            "reason": f"{n}/{len(states)} 次一致"}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--task":
        root = Path(argv[2])
        runs = [judge_run(d) for d in sorted(p for p in root.iterdir() if p.is_dir())]
        print(json.dumps(reduce_task(runs), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps(judge_run(Path(argv[1])), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
