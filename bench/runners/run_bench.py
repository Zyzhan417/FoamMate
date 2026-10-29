#!/usr/bin/env python3
"""bench/runners/run_bench.py — 基准跑的**驱动器**：12 任务 × repeats + 多例展开 + 三层归约 + CSV。

用法：
  python3 bench/runners/run_bench.py --tasks T01,T02 --repeats 3 --dest bench/runs --mode short
  python3 bench/runners/run_bench.py --tasks T01 --repeats 1 --dest /tmp/x --mode short
  python3 bench/runners/run_bench.py --dry-run          # 只打印展开表 + 校验 R1 证据，不建目录

===============================================================================
一、三层归约（计划 §2；L2 是本轮新增的解释，预注册没逐字规定）
===============================================================================
  L1 例级   一个 case 的 log.g1..g5 + assert.json + arm_stdout.txt → 七态
            **由 `bench/judge.py:reduce_run()` 判**，本文件不重写判据。
  L2 任务一次执行级  T09 的 3 例 / T10、T11 的 9 例 / 其余 1 例
            `reduce_examples(states)`：全 pass→pass；含 fail→fail；
            任一 undeterminable→**malformed**；空→malformed；其余按七态优先级取最重者。
  L3 任务级   repeats 次 L2 → `judge.reduce_task()`：≥2 次同态→该态；三次互异→malformed+unstable=1

**L2 的两层保险**：多例任务的 run 根同时写一份「合取」版的 `log.g*` 与 `assert.json`
（任何一例 RC=1 → run 根 RC=1；任何一门缺失 → run 根不写该门），于是
`judge.judge_run(run根)` 应当与 `reduce_examples()` 给出同一个答案。两者不一致时本文件
把它记成 `malformed` 并写进 note —— **判不了不许假装判过**（prereg §11 第 7 条）。

===============================================================================
二、run 目录契约（prereg §12 + 计划 §6.2）
===============================================================================
  bench/runs/<批次>/<task_id>/ours_scripted/run<k>/
    case/            new_case.sh --dest 派生 + apply() 改过的树
    case.meta        **只在 run 根**：new_case.sh 写在 case 树里，这里 shutil.move 出来。
                     两处都有 → judge 判 malformed（judge.py:67）
    base/            改参数**之前**的 cp -a 副本（G5 的 diff 基线）
    spec.json        本任务的四元组（多例时附 _bench.examples 清单）
    log.g1..log.g5   verify_case.sh 写（pre 写 g1/g5，post 写 g2/g3/g4）
    log.checkMesh / log.shortRun
    assert.json      **必须由本文件写**（= assert_lib.evaluate 的完整返回）。
                     缺了它 judge 判 malformed —— 这个失败模式挡住的就是「忘记断言」。
    arm_stdout.txt   T12 的拒绝理由；其余任务只有 key=value 摘要（不得含 CLAIM_MARKERS）
    tokens.json      {"total": 0, "note": "llm-free scripted arm"}
    wall_time.json   {"seconds": <float>}

  多例任务（T09/T10/T11）另有两处：
    run<k>/examples/<case_id>/   每一例一个可被 judge 独立判定的 run 目录（同样的契约）
    run<k>/summary.csv           T09「汇总表」/ T11「汇总 CSV」的产物（需求要求的，不是判据）

===============================================================================
三、三个致命细节（踩中任何一个都会让整批结果**静默**错误）
===============================================================================
  ① `arm_stdout.txt` 绝不写自然语言结论。judge.py:45 的 CLAIM_MARKERS 一旦命中，
     任何门失败的 run 都变 `overclaim` 而不是 `fail`。本文件在写盘前
     `_check_stdout()` 硬拦（非 T12 含标记 → 直接抛错）。T12 反过来必须含 R5_MARKERS。
  ② G5 靠 `base/` 做 diff。`base/` 必须在 `apply()` **之前**复制；改了 blocks/vertices
     的任务必须 `rebuild_mesh=True`（删 constant/polyMesh），否则 run_case.sh 会用旧网格，
     G2 读上一次的日志照样过 —— 项目 N7 第 17 条的真实事故。
  ③ **T11 不改 nu**：prompt 没要求、allowed_files 也不含 constant/physicalProperties。
     改 nu 是越界 + 作弊。它因此必然断言 mismatch → fail，这是冻结件内部矛盾（已登记）。

===============================================================================
四、退出码（沿用 scripts/batch.py 的口径，避开 verify_case 的 1..5）
===============================================================================
  0 全部 pass（T12 的 declined 视为正确） / 70 有任务非 pass / 71 整批中止（环境缺失）
  / 64 用法错误
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parents[1]
RUNNERS_DIR = Path(__file__).resolve().parent
for _p in (str(RUNNERS_DIR), str(BENCH_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import assert_lib            # noqa: E402  （judge 的唯一取值入口）
import judge as judge_mod    # noqa: E402  （七态归约的唯一实现）
import ours_scripted as arm  # noqa: E402  （被测臂）

ARM = "ours_scripted"

#: R12 / 计划 §6.3 的 15 列，顺序即契约
COLUMNS = (
    "task_id", "arm", "status", "g1", "g2", "g3", "g4", "g5", "g2b",
    "repeats", "unstable", "tokens_total", "wall_time_s", "human_interventions", "note",
)
GATES = ("g1", "g2", "g3", "g4", "g5")

EXIT_OK = 0
EXIT_HAD_FAILURES = 70
EXIT_ABORTED = 71
EXIT_USAGE = 64

#: R7：本机内存有限（历史 OOM 事故），并发上限 2
MAX_JOBS = 2


class Usage(Exception):
    """用法错误 → 64。"""


class _Parser(argparse.ArgumentParser):
    """argparse 默认退 2，但 2 在 verify_case.sh 里是「G2 网格门失败」，必须错开。"""

    def error(self, message: str):  # noqa: D401 - argparse 挂钩
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: 用法错误: {message}\n")
        raise SystemExit(EXIT_USAGE)


class Aborted(Exception):
    """整批中止 → 71。"""


# =============================================================================
# L2 归约（纯函数：单测直接喂状态串）
# =============================================================================

#: 七态优先级（prereg §4 逐字）：blocked > declined > no_artifact > malformed > overclaim > fail > pass
_EXAMPLE_PRIORITY = (
    "blocked", "declined", "no_artifact", "malformed", "overclaim", "fail", "pass",
)
#: `undeterminable` 是断言/门的三态用词，不是七态之一；它只能映射到 malformed
_UNDETERMINABLE = ("undeterminable",)


def reduce_examples(states: list[str]) -> str:
    """L2：一次任务执行内多个例 → 一个七态。

    判据（计划 §2 的表）：
      全 pass → pass；含 fail → fail；任一 undeterminable → **malformed**；空 → malformed。

    "undeterminable 绝不能映射成 pass 或 fail"（prereg §11 第 7 条）在这里是
    **一条独立的归一化步骤**，不是优先级列表的副作用——优先级列表被谁调换顺序都不会
    把 undeterminable 变成 pass，而这一行会。变异自证就打在它上面。
    """
    if not states:
        return "malformed"                      # 非退化守卫：空样本不判 pass/fail
    normalised = ["malformed" if s in _UNDETERMINABLE else s for s in states]
    for state in normalised:
        if state not in _EXAMPLE_PRIORITY:
            return "malformed"                  # 未知状态 fail-closed
    for state in _EXAMPLE_PRIORITY:             # 取最重者的优先级
        if state in normalised:
            return state
    return "malformed"


# =============================================================================
# CSV 行（15 列，顺序即契约）
# =============================================================================

def csv_row(*, task_id: str, status: str, gates: dict, g2b: str, repeats: int,
            unstable: int, tokens_total: int, wall_time_s: float,
            human_interventions: int | str, note: str, arm_name: str = ARM) -> list[str]:
    """构造一行 `results.csv`。恰好 15 列，顺序 = `COLUMNS`。

    缺门直接抛错：`g1..g5` 少一个就意味着「这一门没测」，而空串会被 CSV 读成别的东西
    （`check_contracts.py` 的判据 4 要求取值域 `{0,1,unmeasured}`）。
    """
    missing = [g for g in GATES if g not in gates]
    if missing:
        raise ValueError(f"csv_row: 缺门 {missing}（五门必须齐全，未测写 unmeasured）")
    row = [
        str(task_id), str(arm_name), str(status),
        *(str(gates[g]) for g in GATES),
        str(g2b), str(repeats), str(unstable), str(tokens_total),
        str(wall_time_s), str(human_interventions), str(note),
    ]
    if len(row) != len(COLUMNS):
        raise AssertionError(f"csv_row 产出 {len(row)} 列，契约是 {len(COLUMNS)} 列")
    return row


# =============================================================================
# 四元组与断言实例化
# =============================================================================

def build_spec(task: dict, ex: arm.Example) -> dict:
    """本例的四元组（geometry / properties / boundary / objective）+ `_bench` 溯源块。"""
    values = arm.EXAMPLE_VALUES.get(ex.case_id, {})
    u = values.get("U")
    nu = values.get("nu", "1e-05")
    dt = values.get("deltaT", "0.005")
    return {
        "geometry": f"从 $FOAM_TUTORIALS/{task['ref']} 派生（几何按需求调整）",
        "properties": f"nu={nu} [m^2/s]",
        "boundary": (
            f"顶盖 movingWall = ({u} 0 0) m/s；其余 wall noSlip、frontAndBack empty"
            if u else "沿用 tutorial 的边界条件（未改速度）"
        ),
        "objective": "transient",
        "_bench": {
            "task_id": task["id"],
            "case_id": ex.case_id,
            "arm": ARM,
            "prompt": task["prompt"],
            "deltaT": dt,
            "rebuild_mesh": ex.rebuild_mesh,
            "edits": [
                {"kind": ed.kind, "file": ed.file, "entry": ed.entry,
                 "new_value": ed.new_value, "source": ed.source, "evidence": ed.evidence}
                for ed in ex.edits
            ],
        },
    }


def instantiate_specs(specs: list[dict], case_id: str) -> tuple[list[dict], dict]:
    """把冻结的 `expect_values` 实例化到**该例自己**的取值上。

    为什么需要：T09/T10 的 yaml 只列了一条断言（"此处列 2 m/s 那例" / "9 例逐个施加"），
    而任务实际跑 3 / 9 例。把那条断言**逐字**施加到每一例，会让 0.5 m/s 那例必然 mismatch
    （它的 comp 是 [0.5,0,0]），于是「三例全对才算 match」永远不可能成立。

    本函数只替换**该例确实变化了的那个参数**（`ours_scripted.EXAMPLE_VALUES` 登记的
    U / nu / deltaT），因此它只会让判据**更贴住需求**（每例对自己的取值负责），
    不会放宽：某例漏改时，它的断言仍然 mismatch。单例任务不在表内 ⇒ **逐字使用冻结值**。
    """
    values = arm.EXAMPLE_VALUES.get(case_id) or {}
    out: list[dict] = []
    subs: dict[str, str] = {}
    for spec in specs:
        item = json.loads(json.dumps(spec))     # 深拷贝：绝不改冻结件的内存副本
        key = str(item.get("key") or "")
        if values and key in values and item.get("kind") in ("dict", "dict_value"):
            if item.get("kind") == "dict":
                try:
                    item["expect"] = float(values[key])
                except (TypeError, ValueError):
                    pass
            else:
                item["expect"] = values[key]
            subs[key] = values[key]
        comp = item.get("comp")
        if values.get("U") and item.get("kind") == "boundary" and isinstance(comp, list) and len(comp) == 3:
            item["comp"] = [float(values["U"]), comp[1], comp[2]]
            subs["U"] = values["U"]
        out.append(item)
    return out, subs


# =============================================================================
# 小工具
# =============================================================================

def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


_RC_RE = re.compile(r"^\s*RC\s*=\s*(\d+)\s*$", re.M)


def gate_rc(path: Path) -> str | None:
    """读 `log.gN` 的 `RC=0|1`。文件不存在/格式不符 → None（**不可判定，不是 pass**）。"""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _RC_RE.search(text)
    return m.group(1) if m else None


def _check_stdout(text: str, tid: str) -> None:
    """致命细节 1：臂的自述不许含 CLAIM_MARKERS（T12 必须含 R5_MARKERS）。

    这条检查本身不进任何日志输出（那会污染证据），只决定「写不写盘」：
    宁可整批中止，也不要写出一批语义被静默改写的 run。
    """
    low = text.lower()
    claims = [k for k in judge_mod.CLAIM_MARKERS if k in text or k in low]
    if tid == "T12":
        if not any(k in text for k in judge_mod.R5_MARKERS):
            raise RuntimeError("T12 的拒绝理由没有指认 R5 边界（曲面/边界层加密/STL…），judge 会判 no_artifact")
        if claims:
            raise RuntimeError(f"T12 的拒绝理由含 CLAIM_MARKERS {claims}：会把 declined 顶成 overclaim")
        return
    if claims:
        raise RuntimeError(
            f"{tid} 的 arm_stdout 含 CLAIM_MARKERS {claims}："
            "任何门失败都会被判 overclaim 而不是 fail（judge.py:45）"
        )


def _count_iterations(log_path: Path) -> str:
    """`log.shortRun` 里的 `Time = ` 行数（= 求解器实际走的步数）。读不到就写 undeterminable。"""
    if not log_path.is_file():
        return "undeterminable"
    n = 0
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^\s*Time = ", line):
            n += 1
    return str(n)


def _max_u(case_dir: Path) -> str:
    """末时刻 U 的 |U|max。读不到就写 undeterminable（**不许估**，R6）。"""
    times: list[tuple[float, Path]] = []
    if not case_dir.is_dir():
        return "undeterminable"
    for p in case_dir.iterdir():
        if p.is_dir() and re.fullmatch(r"[0-9]+(\.[0-9]+)?", p.name):
            times.append((float(p.name), p))
    later = [t for t in times if t[0] > 0]
    if not later:
        return "undeterminable"
    field = sorted(later)[-1][1] / "U"
    if not field.is_file():
        return "undeterminable"
    text = field.read_text(encoding="utf-8", errors="replace")
    vecs: list[list[float]] = []
    m = re.search(r"internalField\s+uniform\s+\(([^)]*)\)", text)
    if m:
        try:
            vecs = [[float(x) for x in m.group(1).split()]]
        except ValueError:
            return "undeterminable"
    else:
        m2 = re.search(r"internalField\s+nonuniform[^;]*?\n\((.*?)\)\s*;", text, re.S)
        if not m2:
            return "undeterminable"
        for chunk in re.findall(r"\(([^()]*)\)", m2.group(1)):
            try:
                vecs.append([float(x) for x in chunk.split()])
            except ValueError:
                return "undeterminable"
    if not vecs:
        return "undeterminable"
    return f"{max(math.sqrt(sum(c * c for c in v)) for v in vecs):.6g}"


# =============================================================================
# 驱动器
# =============================================================================

class Runner:
    def __init__(self, *, scripts: Path, mode: str, timeout: int):
        self.scripts = scripts
        self.mode = mode
        self.timeout = timeout
        self.aborted: str | None = None

    # -- 子进程 ------------------------------------------------------------

    def _sh(self, cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd, cwd=str(cwd) if cwd else None,
                capture_output=True, text=True, timeout=self.timeout + 120,
            )
        except subprocess.TimeoutExpired:
            # 21 在 run_case.sh 里是「超时」；这里用同一个码，别引入新的语义
            return subprocess.CompletedProcess(cmd, 21, "", f"timeout after {self.timeout + 120}s")

    def _foam_value(self, case_dir: Path, rel: str, entry: str) -> str | None:
        """读一个顶层关键字（加 `-value`；不加会带 key 名）。失败 → None。"""
        exe = shutil.which("foamDictionary")
        if exe is None:
            return None
        p = self._sh([exe, rel, "-case", str(case_dir), "-entry", entry, "-value"])
        if p.returncode != 0:
            return None
        return p.stdout.strip() or None

    def _verify(self, stage: str, run_dir: Path, allowed: list[str]) -> subprocess.CompletedProcess:
        cmd = [str(self.scripts / "verify_case.sh"), "--stage", stage,
               "--case", str(run_dir), "--log", str(run_dir)]
        # allowed_files 展开成 --allowed 的多值（verify_case.sh 的 glob 用 fnmatch，`*` 跨 `/`）
        for g in allowed:
            cmd += ["--allowed", g]
        return self._sh(cmd)

    # -- 单例 --------------------------------------------------------------

    def _derive(self, task: dict, ex_dir: Path) -> int:
        """new_case.sh 派生。spec.json 必须先落盘（它同时被写进 case.meta）。"""
        cmd = [str(self.scripts / "new_case.sh"),
               "--source", task["ref"],
               "--dest", str(ex_dir / "case"),
               "--spec", str(ex_dir / "spec.json")]
        if task["allowed_files"]:
            # new_case.sh 的 --allowed 是**逗号分隔单值**（重复给会被后者覆盖），必须 join
            cmd += ["--allowed", ",".join(task["allowed_files"])]
        return self._sh(cmd).returncode

    def _record_changes(self, meta_path: Path, ex: arm.Example) -> None:
        """把改动清单写进 case.meta（R3），顺带给 G5 的 polyMesh 豁免提供理由文本。"""
        if not meta_path.is_file():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        changes = [
            {"file": ed.file, "kind": ed.kind, "entry": ed.entry,
             "new_value": ed.new_value, "evidence": ed.evidence}
            for ed in ex.edits
        ]
        if ex.rebuild_mesh:
            changes.append({
                "file": "constant/polyMesh", "kind": "delete", "entry": "", "new_value": "",
                "evidence": "改了 blocks/vertices 必须删旧网格重建（不改网格 → G2 读上一次日志 → 假 pass，N7 第 17 条）",
            })
        meta["changes"] = changes
        _write_json(meta_path, meta)

    def _run_example(self, tid: str, task: dict, ex: arm.Example,
                     ex_dir: Path, n_examples: int) -> dict:
        started = time.time()
        ex_dir.mkdir(parents=True, exist_ok=True)
        text = arm.arm_stdout_for(tid, mode=self.mode, n_examples=n_examples, case_id=ex.case_id)
        _check_stdout(text, tid)
        (ex_dir / "arm_stdout.txt").write_text(text, encoding="utf-8")
        _write_json(ex_dir / "spec.json", build_spec(task, ex))

        info: dict = {"case_id": ex.case_id, "dir": ex_dir, "stage_rc": {},
                      "apply_error": None, "notes": []}

        def finish() -> dict:
            info["wall"] = round(time.time() - started, 2)
            _write_json(ex_dir / "wall_time.json", {"seconds": info["wall"]})
            return info

        # ① 派生
        rc = self._derive(task, ex_dir)
        info["stage_rc"]["derive"] = rc
        if rc != 0:
            info["notes"].append(f"派生失败（new_case 退 {rc}）：没有 case 树，无可判对象")
            _write_json(ex_dir / "assert.json", {
                "overall": "undeterminable", "assertions": [],
                "_bench": {"task_id": tid, "case_id": ex.case_id, "arm": ARM,
                           "derive_rc": rc},
            })
            return finish()

        # ② case.meta 移到 run / 例根：new_case.sh 写在 case 树里，两处都在会被判 malformed
        inner = ex_dir / "case" / "case.meta"
        if inner.is_file():
            inner.replace(ex_dir / "case.meta")

        # ③ base/ = **改动之前**的副本（G5 的 diff 基线）
        base = ex_dir / "base"
        if base.exists():
            shutil.rmtree(base)
        shutil.copytree(ex_dir / "case", base)

        # ④ 施加改动（失败不静默：记下来继续跑，让门与断言去判它到底做没做到）
        try:
            arm.apply(ex_dir / "case", ex)
        except arm.ApplyError as exc:
            info["apply_error"] = str(exc)
            info["notes"].append(f"改动施加失败：{exc}")
        self._record_changes(ex_dir / "case.meta", ex)

        # ⑤ pre 门（G1 结构 + G5 范围）
        pre = self._verify("pre", ex_dir, task["allowed_files"])
        info["stage_rc"]["pre"] = pre.returncode

        # ⑥ 求解（pre 不过也照跑：五个门都测出来，judge 才能判 fail 而不是 malformed。
        #    judge 的 M-d 短路只覆盖「G1 失败 + 后续门缺失」这一种合法组合）
        #
        # **求解前先快照 controlDict**：run_case.sh 的 short 模式会把 endTime 改成
        # `deltaT*2`、writeInterval 改成 2 并**落盘**（它就是靠改字典来缩短机时的）。
        # 不撤销这两处改动，T01 的 `endTime=5`、T05 的 `writeInterval=50` 断言读到的
        # 永远是测量工具写进去的值 → 每个任务都假 mismatch。这不是放宽判据：
        # 恢复的是**臂交付的**那一份，断言照样咬在需求上。
        control = ex_dir / "case" / "system" / "controlDict"
        control_bytes = control.read_bytes() if control.is_file() else None
        # run_case.sh 的 short 模式只改 endTime / writeInterval（按**步**计数），却没动
        # `writeControl`。控制字典若写的是 `adjustableRunTime`（pitzDaily 就是），
        # writeInterval=2 的意思变成「每 2 秒仿真时间写一次」，而 endTime 已被压到 2*deltaT
        # → 一次都不写 → G4「末时刻目录不存在」假红（2026-10-29 实测 T02）。
        # 这是**测量工具**的前置：把写盘节奏临时改成按步，跑完与 endTime 一起还原。
        harness_adjust: list[str] = []
        if self.mode != "check" and control.is_file():
            got = self._foam_value(control.parent.parent, "system/controlDict", "writeControl")
            if got and got != "timeStep":
                exe = str(shutil.which("foamDictionary") or "foamDictionary")
                base = [exe, "system/controlDict", "-case", str(ex_dir / "case")]
                setc = self._sh([*base, "-entry", "writeControl", "-set", "timeStep"])
                # 换成按步写盘后 `writeInterval` 必须是整数步数（pitzDaily 里是 0.01 秒）：
                # 否则 Time::readDict 直接 FATAL `writeInterval < 1 for writeControl timeStep`，
                # 而 blockMesh 在 run_case 的 short 模式改写之前就要读这份字典（实测踩过）。
                seti = self._sh([*base, "-entry", "writeInterval", "-set", "2"])
                if setc.returncode == 0 and seti.returncode == 0:
                    harness_adjust.append(
                        f"writeControl {got} → timeStep + writeInterval → 2（short 模式按步写盘）")
        run = self._sh([str(self.scripts / "run_case.sh"),
                        "--case", str(ex_dir / "case"), "--mode", self.mode,
                        "--log", str(ex_dir), "--timeout", str(self.timeout)])
        info["stage_rc"]["run"] = run.returncode
        if run.returncode == 22:
            (ex_dir / "blocked.txt").write_text(
                "run_case 退 22：PATH 里没有 foamRun（环境前置不满足）\n", encoding="utf-8")
            self.aborted = "22"
            info["notes"].append("环境缺失（22）→ 整批中止")

        # ⑦ post 门（G2 网格 + G3 短跑 + G4 产物）
        post = self._verify("post", ex_dir, task["allowed_files"])
        info["stage_rc"]["post"] = post.returncode

        # ⑧ 撤销 short 模式对 controlDict 的临时改动（见步骤⑥的快照说明）
        restored = False
        if control_bytes is not None and control.is_file() and control.read_bytes() != control_bytes:
            control.write_bytes(control_bytes)
            restored = True

        # ⑨ 断言（judge 的唯一取值入口；**必须写 assert.json**）
        specs, subs = instantiate_specs(task["specs"], ex.case_id)
        result = assert_lib.evaluate(ex_dir / "case", specs, text)
        result["_bench"] = {
            "task_id": tid, "case_id": ex.case_id, "arm": ARM, "mode": self.mode,
            "specs_verbatim": not bool(subs), "substitutions": subs,
            "gates_rc": {g: gate_rc(ex_dir / f"log.{g}") for g in GATES},
            "apply_error": info["apply_error"],
            "control_dict_restored": restored,
            "harness_adjust": harness_adjust,
        }
        _write_json(ex_dir / "assert.json", result)
        return finish()

    # -- T12 负对照 --------------------------------------------------------

    def _refuse(self, tid: str, task: dict, run_dir: Path, info: dict) -> None:
        """负对照：**不派生 case**，只写拒绝理由。

        不写 `blocked.txt`（写了 judge 判 `blocked`，优先级还在 `declined` 之前）；
        不写 `log.g*`（没有 case 就没有门可判）；不建 `case/` 目录。
        """
        text = arm.arm_stdout_for(tid, mode=self.mode, n_examples=1)
        _check_stdout(text, tid)
        (run_dir / "arm_stdout.txt").write_text(text, encoding="utf-8")
        _write_json(run_dir / "spec.json", build_spec(task, arm.PLANS[tid][0]))
        result = assert_lib.evaluate(run_dir / "case", task["specs"], text)
        result["_bench"] = {"task_id": tid, "case_id": tid, "arm": ARM,
                            "mode": self.mode, "refused": True}
        _write_json(run_dir / "assert.json", result)
        info["notes"].append("负对照：未派生 case，只写拒绝理由")

    # -- 多例合取 ----------------------------------------------------------

    def _aggregate(self, run_dir: Path, example_dirs: list[Path],
                   main_dir: Path, tid: str, n: int, task: dict) -> None:
        """多例 → run 根：五门合取 + 断言合取 + 主例的 case/base 副本。

        合取规则与 `reduce_examples` 逐条对应：
          任一门有任何一例缺失 → **run 根不写这一门**（judge 读成 undeterminable → malformed）；
          否则任一门 RC=1 → RC=1；否则 RC=0。
        """
        for g in GATES:
            rcs = [gate_rc(d / f"log.{g}") for d in example_dirs]
            if any(rc is None for rc in rcs):
                continue                     # 不可判定：留白比编一个 RC 诚实
            rc = "1" if "1" in rcs else "0"
            lines = [f"RC={rc}"]
            if g == "g2":
                lines.append(f"G2B={self._aggregate_g2b(example_dirs)}")
            bad = [d.name for d, r in zip(example_dirs, rcs) if r == "1"]
            if bad:
                lines.append(f"FAIL 例: {', '.join(bad)}")
            lines.append(f"# 合取自 {n} 例（{tid}）")
            (run_dir / f"log.{g}").write_text("\n".join(lines) + "\n", encoding="utf-8")

        overs: dict[str, str] = {}
        for d in example_dirs:
            raw = d / "assert.json"
            if not raw.is_file():
                overs[d.name] = "undeterminable"
                continue
            try:
                overs[d.name] = json.loads(raw.read_text(encoding="utf-8")).get("overall", "undeterminable")
            except json.JSONDecodeError:
                overs[d.name] = "undeterminable"
        vals = list(overs.values())
        if "mismatch" in vals:
            overall = "mismatch"
        elif any(v != "match" for v in vals):
            overall = "undeterminable"
        else:
            overall = "match"
        _write_json(run_dir / "assert.json", {
            "overall": overall, "assertions": [], "examples": overs,
            "_bench": {"task_id": tid, "arm": ARM, "mode": self.mode,
                       "aggregation": "conjunction of examples（任一例 mismatch/不可判定 → 全任务不 match）"},
        })

        # 主例 = 第一例：judge 在 run 根需要一份可判定的 case + 溯源
        for sub in ("case", "base"):
            dst = run_dir / sub
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(main_dir / sub, dst)
        for name in ("case.meta", "log.checkMesh", "log.shortRun", "spec.json"):
            src = main_dir / name
            if src.is_file():
                shutil.copy2(src, run_dir / name)
        spec_path = run_dir / "spec.json"
        if spec_path.is_file():
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                spec.setdefault("_bench", {})["main_example"] = main_dir.name
                spec["_bench"]["examples"] = [d.name for d in example_dirs]
                _write_json(spec_path, spec)
            except json.JSONDecodeError:
                pass

    @staticmethod
    def _aggregate_g2b(example_dirs: list[Path]) -> str:
        """g2b 不是门（prereg §5），只做诊断：取最重的一档并累加计数。"""
        found: list[str] = []
        for d in example_dirs:
            text = (d / "log.g2").read_text(encoding="utf-8", errors="replace") if (d / "log.g2").is_file() else ""
            m = re.search(r"^\s*G2B\s*=\s*(none|soft:\d+|hard:\d+|unknown)\s*$", text, re.M)
            found.append(m.group(1) if m else "unknown")
        if not found or "unknown" in found:
            return "unknown"
        hard = sum(int(v.split(":")[1]) for v in found if v.startswith("hard"))
        soft = sum(int(v.split(":")[1]) for v in found if v.startswith("soft"))
        if hard:
            return f"hard:{hard}"
        if soft:
            return f"soft:{soft}"
        return "none"

    # -- 一次执行 ----------------------------------------------------------

    def run_once(self, tid: str, task: dict, run_dir: Path) -> dict:
        started = time.time()
        if run_dir.exists():
            shutil.rmtree(run_dir)          # 同名批次重跑：旧日志是唯一证据，绝不混用
        run_dir.mkdir(parents=True)

        examples = arm.PLANS[tid]
        n = len(examples)
        info: dict = {"task_id": tid, "run_dir": run_dir, "n_examples": n,
                      "examples": [], "notes": [], "aborted": None}

        if task["expect"] == "refuse":
            self._refuse(tid, task, run_dir, info)
        else:
            root = run_dir if n == 1 else run_dir / "examples"
            main_dir: Path | None = None
            for ex in examples:
                ex_dir = root if n == 1 else root / ex.case_id
                if main_dir is None:
                    main_dir = ex_dir
                info["examples"].append(self._run_example(tid, task, ex, ex_dir, n))
            if n > 1:
                assert main_dir is not None
                self._aggregate(run_dir, [e["dir"] for e in info["examples"]], main_dir, tid, n, task)
                self._write_summary(run_dir, tid, info["examples"])

        # run 根公共记录（单例时与例目录同一处，重复写幂等）
        text = arm.arm_stdout_for(tid, mode=self.mode, n_examples=n)
        _check_stdout(text, tid)
        (run_dir / "arm_stdout.txt").write_text(text, encoding="utf-8")
        _write_json(run_dir / "tokens.json", {"total": 0, "note": "llm-free scripted arm"})
        info["wall"] = round(time.time() - started, 2)
        _write_json(run_dir / "wall_time.json", {"seconds": info["wall"]})

        # L1（judge）→ L2（reduce_examples）
        ev = judge_mod.gather(run_dir)
        judged = judge_mod.reduce_run(ev)
        info["judge"] = judged
        info["g2b"] = ev["g2b"]
        info["gates"] = {g: gate_rc(run_dir / f"log.{g}") for g in GATES}
        if task["expect"] == "refuse":
            info["l2_states"] = [judged["status"]]
        else:
            info["l2_states"] = [judge_mod.judge_run(e["dir"])["status"] for e in info["examples"]] \
                if n > 1 else [judged["status"]]
        info["l2"] = reduce_examples(info["l2_states"])
        if info["l2"] != judged["status"]:
            # 两层给出不同答案 → 判据自相矛盾，fail-closed 记 malformed（不许挑好看的）
            info["notes"].append(
                f"L2({info['l2']}) 与 run 级 judge({judged['status']}) 不一致 → 记 malformed"
            )
            info["l2"] = "malformed"
        info["aborted"] = self.aborted
        return info

    # -- 汇总表（T09 的「汇总表」/ T11 的「汇总 CSV」）----------------------

    def _write_summary(self, run_dir: Path, tid: str, ex_infos: list[dict]) -> None:
        """需求原文要求「出汇总表」/「汇总 max(U) 与迭代步数到 CSV」。

        它不是判据（judge 不查，见计划 §10.1），但**落盘了**才谈得上「做过」。
        读不到的数字一律写 `undeterminable`，不估（R6）。
        """
        if tid not in ("T09", "T11"):
            return
        path = run_dir / "summary.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["case_id", "U_m_per_s", "deltaT", "iterations", "maxU_m_per_s", "note"])
            for e in ex_infos:
                vals = arm.EXAMPLE_VALUES.get(e["case_id"], {})
                w.writerow([
                    e["case_id"], vals.get("U", ""), vals.get("deltaT", ""),
                    _count_iterations(e["dir"] / "log.shortRun"),
                    _max_u(e["dir"] / "case"),
                    f"mode={self.mode}",
                ])


# =============================================================================
# 任务级（L3）与 CSV
# =============================================================================

def task_row(tid: str, task: dict, runs: list[dict]) -> dict:
    """repeats 次执行 → 任务级一行。L3 用 `judge.reduce_task()`（不改写它的判据）。"""
    states = [r["l2"] for r in runs]
    l3 = judge_mod.reduce_task([{"status": s} for s in states])

    gates: dict[str, str] = {}
    for g in GATES:
        vals = [r["gates"].get(g) for r in runs]
        if any(v == "1" for v in vals):
            gates[g] = "1"
        elif vals and all(v == "0" for v in vals):
            gates[g] = "0"
        else:
            gates[g] = "unmeasured"

    g2bs = [r["g2b"] for r in runs if r["g2b"] and r["g2b"] != "unknown"]
    g2b = max(set(g2bs), key=g2bs.count) if g2bs else "unknown"
    wall = round(sum(r["wall"] for r in runs), 2)

    note_parts = [f"mode={runs[0]['run_mode']}" if runs and runs[0].get("run_mode") else "",
                  f"examples={len(arm.PLANS[tid])}",
                  f"L2={'/'.join(states) or 'none'}",
                  l3["reason"]]
    fails = [g for g, v in gates.items() if v == "1"]
    if fails:
        note_parts.append("门失败: " + ",".join(fails))
        # 把第一个失败门在日志里的原话摘一行进 note：结论要能指到具体门与具体日志行（R4/R6）
        detail = _gate_detail(runs[0]["run_dir"], fails[0])
        if detail:
            note_parts.append(f"{fails[0]}: {detail}")
    reasons = sorted({r["judge"]["reason"] for r in runs})
    if l3["status"] != "pass":
        note_parts.append("judge: " + " | ".join(reasons))
    if tid in arm.TASK_NOTES:
        note_parts.append(arm.TASK_NOTES[tid])
    for r in runs:
        for nt in r["notes"]:
            note_parts.append(nt)
        note_parts.extend(_example_note_parts(r))
    # 去重但保序：run 级 notes 会按 3 次重复各来一条（T12 的「负对照…」曾出现 3 次），
    # CSV 的 note 列是自由文本、不进结论，但一份要交付的表里同一句话写三遍会被当成噪声。
    note = "; ".join(dict.fromkeys(p for p in note_parts if p))

    return {
        "task_id": tid,
        "status": l3["status"],
        "gates": gates,
        "g2b": g2b,
        "repeats": l3["repeats"],
        "unstable": l3["unstable"],
        "wall_time_s": wall,
        "note": note,
    }


def resolve_batch_root(dest: str | Path, batch_id: str) -> Path:
    """批次根目录 = **绝对化**的 dest / batch_id。

    为什么必须 absolute：下游 `foamDictionary <相对路径>` 在夹具自己的 cwd 下解析，
    相对 `--dest` 会让它「文件不存在」→ `apply` 失败 → 跑的是**原始 tutorial**。
    而 G5 拿 base/（改前副本）做 diff，此时 base == case 无改动 → G5 照样 RC=0，
    于是「门全过、需求没落地」只能由断言层抓住。
    实测代价：一次 `--dest bench/runs` 的整批跑让 8/12 个任务假 fail，而旧版 note 里
    看不到任何原因（例级 apply_error 没上浮）。
    """
    return (Path(dest).expanduser().resolve()) / batch_id


def _example_note_parts(run_info: dict) -> list[str]:
    """例级 notes / apply_error 上浮到行 note。

    为什么必须上浮：单例任务的 `run_info["notes"]` 是 run 级空表，而「改动施加失败」记在
    例级。不上浮的话，一行 `fail` 的 CSV 看不出它跑的是**原始 tutorial**——实测：`--dest`
    用相对路径时 8/12 个任务假 fail，报告里唯一的线索就是 note 这一列。
    """
    parts: list[str] = []
    for ex in run_info.get("examples", []) or []:
        if ex.get("apply_error"):
            parts.append(f"改动未落地[{ex.get('case_id')}]：{str(ex['apply_error'])[:120]}")
        for nt in ex.get("notes", []) or []:
            parts.append(str(nt))
    return parts


def _gate_detail(run_dir: Path, gate: str, limit: int = 160) -> str:
    """`log.gN` 里第一行「人看的失败串」（跳过 `RC=` 与 `G2B=`）。"""
    path = Path(run_dir) / f"log.{gate}"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("RC=") or s.startswith("G2B="):
            continue
        return s[:limit]
    return ""


def _print_expansion(tasks: list[str]) -> None:
    print(f"# 展开表（{len(tasks)} 个任务）")
    total = 0
    for tid in tasks:
        task = arm.load_task(tid)
        examples = arm.PLANS[tid]
        total += len(examples)
        print(f"\n{tid}  例数={len(examples)}  ref={task['ref']}  expect={task['expect']}")
        print(f"      prompt: {task['prompt']}")
        for ex in examples:
            tag = " [rebuild_mesh]" if ex.rebuild_mesh else ""
            edits = ", ".join(
                f"{ed.kind}:{ed.file}"
                + (f":{ed.entry}={ed.new_value}" if ed.entry and ed.kind != "replace_text"
                   else (f"<块替换 {len(ed.entry)}B→{len(ed.new_value)}B>" if ed.kind == "replace_text" else ""))
                for ed in ex.edits
            ) or "(不改任何文件)"
            print(f"  - {ex.case_id}{tag}: {edits}")
    print(f"\n# 合计 {total} 例（T12 不派生 case，只写拒绝理由）")


def _check_evidence_or_warn() -> bool:
    problems = arm.verify_evidence()
    if problems:
        print(f"# R1 证据校验：{len(problems)} 项不通过", file=sys.stderr)
        for p in problems:
            print(f"#   {p}", file=sys.stderr)
        return False
    print("# R1 证据校验：全部逐字命中（$FOAM_TUTORIALS 下 path:line == 引文）")
    return True


def main(argv: list[str]) -> int:
    parser = _Parser(prog="run_bench.py",
                     description="基准跑驱动器：12 任务 × repeats + 多例展开 + 三层归约 + results.csv")
    parser.add_argument("--tasks", default=",".join(arm.TASK_IDS),
                        help="逗号分隔的任务 id，缺省全部 12 个")
    parser.add_argument("--repeats", type=int, default=3, help="每任务跑几次（prereg §8.1：3）")
    parser.add_argument("--dest", default=str(BENCH_DIR / "runs"), help="批次根目录")
    parser.add_argument("--batch", default=None, help="批次名，缺省 UTC 时间戳")
    parser.add_argument("--mode", default="short", choices=("check", "short", "full"))
    parser.add_argument("--timeout", type=int, default=600, help="单个 OpenFOAM 子进程墙钟上限（秒）")
    parser.add_argument("--jobs", type=int, default=1, help=f"并发任务数，默认 1，上限 {MAX_JOBS}")
    parser.add_argument("--dry-run", action="store_true", help="只打印展开表并校验证据，不建任何目录")
    args = parser.parse_args(argv)

    wanted = [t.strip() for t in args.tasks.split(",") if t.strip()]
    unknown = [t for t in wanted if t not in arm.TASK_IDS]
    if unknown:
        raise Usage(f"--tasks 里有未知 id {unknown}（合法值 {arm.TASK_IDS}）")
    if args.repeats < 1:
        raise Usage("--repeats 必须是正整数（prereg §8.1 固定 3）")
    if args.jobs < 1 or args.jobs > MAX_JOBS:
        raise Usage(f"--jobs 必须 1..{MAX_JOBS}（R7：本机内存有限，历史 OOM 事故）")
    if args.timeout < 1:
        raise Usage("--timeout 必须是正整数秒")

    if args.dry_run:
        _print_expansion(wanted)
        ok = _check_evidence_or_warn()
        print("\n# --dry-run：未执行任何命令，未创建任何目录")
        return EXIT_OK if ok else EXIT_HAD_FAILURES

    if not os.environ.get("FOAM_TUTORIALS", "").strip():
        raise Aborted("$FOAM_TUTORIALS 为空：先 `source $WM_PROJECT_DIR/etc/bashrc` 再跑")
    if shutil.which("foamRun") is None:
        # 主动探测：不探测的话会得到 12 行相同的 blocked（run_case 退 22）
        raise Aborted("PATH 里没有 foamRun：OpenFOAM 环境未加载")

    batch_id = args.batch or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    batch_root = resolve_batch_root(args.dest, batch_id)
    batch_root.mkdir(parents=True, exist_ok=True)
    scripts = BENCH_DIR.parent / "scripts"
    runner = Runner(scripts=scripts, mode=args.mode, timeout=args.timeout)

    def run_task(tid: str) -> dict:
        task = arm.load_task(tid)
        task_root = batch_root / tid / ARM
        task_root.mkdir(parents=True, exist_ok=True)
        runs: list[dict] = []
        for k in range(1, args.repeats + 1):
            if runner.aborted:
                break
            info = runner.run_once(tid, task, task_root / f"run{k}")
            info["run_mode"] = args.mode
            runs.append(info)
            print(f"{info['l2']:<12} {tid} run{k}  {info['judge']['reason']}", flush=True)
            if info["aborted"]:
                break
        if not runs:
            return {"task_id": tid, "status": "blocked",
                    "gates": {g: "unmeasured" for g in GATES}, "g2b": "unknown",
                    "repeats": 0, "unstable": 0, "wall_time_s": 0.0,
                    "note": "整批中止（环境缺失），本例未执行"}
        return task_row(tid, task, runs)

    print(f"# 批次 {batch_id} → {batch_root}（mode={args.mode}, repeats={args.repeats}, "
          f"jobs={args.jobs}, 任务 {len(wanted)} 个）", flush=True)

    rows: list[dict] = []
    if args.jobs == 1:
        for tid in wanted:
            rows.append(run_task(tid))
            if runner.aborted:
                break
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows.extend(pool.map(run_task, wanted))

    done = {r["task_id"] for r in rows}
    for tid in wanted:                       # 中止时补齐，保证「每任务一行」
        if tid not in done:
            rows.append({"task_id": tid, "status": "blocked",
                         "gates": {g: "unmeasured" for g in GATES}, "g2b": "unknown",
                         "repeats": 0, "unstable": 0, "wall_time_s": 0.0,
                         "note": "整批中止（环境缺失），本例未执行"})
    order = {tid: i for i, tid in enumerate(arm.TASK_IDS)}
    rows.sort(key=lambda r: order.get(r["task_id"], 99))

    results = batch_root / "results.csv"
    with results.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for row in rows:
            w.writerow(csv_row(
                task_id=row["task_id"], status=row["status"], gates=row["gates"],
                g2b=row["g2b"], repeats=row["repeats"], unstable=row["unstable"],
                tokens_total=0, wall_time_s=row["wall_time_s"],
                human_interventions=0, note=row["note"],
            ))

    print(f"\n# results.csv → {results}（{len(rows)} 行）")
    for row in rows:
        print(f"{row['status']:<12} {row['task_id']}  wall={row['wall_time_s']}s  {row['note'][:110]}")
    dist: dict[str, int] = {}
    for row in rows:
        dist[row["status"]] = dist.get(row["status"], 0) + 1
    print("# 状态分布: " + ", ".join(f"{k}={v}" for k, v in sorted(dist.items())))
    if len(dist) < 3:
        # prereg §12 / G-R12-1：只出现两种状态 → §9 判作废（如实报告，不为了凑数做错任务）
        print(f"# 注意：status 只有 {len(dist)} 种取值 —— prereg §12 要求 ≥3 种，"
              "否则本轮按 §9 作废（这是合法结果，不许为了凑第三种而故意做错任务）")

    if runner.aborted:
        print(f"# 整批中止：{runner.aborted}")
        return EXIT_ABORTED
    bad = [r for r in rows if r["status"] not in ("pass", "declined")]
    return EXIT_OK if not bad else EXIT_HAD_FAILURES


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except Usage as exc:
        sys.stderr.write(f"run_bench.py: 用法错误: {exc}\n")
        raise SystemExit(EXIT_USAGE)
    except Aborted as exc:
        sys.stderr.write(f"run_bench.py: 中止: {exc}\n")
        raise SystemExit(EXIT_ABORTED)
