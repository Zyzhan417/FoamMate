"""bench/runners 的 L1 单元测试：任务解析 / 多例展开 / L2 归约 / CSV 行构造。

**零 OpenFOAM 依赖**（不 source bashrc、不跑 foamDictionary、不 checkMesh）：
本文件只读 `bench/tasks/*.yaml`、`bench/judge.py` 的常量表与 `bench/runners/` 的纯函数。

## 这一层守的是什么（分工判据）

`bench/runners/` 的风险不在「能不能跑求解」（那由批跑的 G1–G5 覆盖），而在三处**静默错误**：

1. **L2 归约把 `undeterminable` 折成 pass/fail**。`bench/preregistration.md:141`–`143`
   与 `:388` 把这条写成红线（judge 侧的同一红线由 `bench/selftest_judge.py` 的
   `mapping_checked` 守）。L2 是预注册没逐字规定、由计划 §2 新增的一层，
   因此**只有这里的测试能咬住它**。
2. **臂的自述里出现「已完成」类词**。`bench/judge.py:45` 的 `CLAIM_MARKERS` 一旦命中，
   任何门失败的 run 都会被判 `overclaim` 而不是 `fail`（判据语义整体变样）。
   所以摘要文本必须能在没有 OpenFOAM 的机器上被断言「不含任何 CLAIM_MARKERS」。
3. **T12 的理由不含 R5 关键词**。`bench/judge.py:43` + `:138`：没有 R5 关键词的
   「无 case」只会被判 `no_artifact`，负对照就失效了。

另外两条一致性断言（防止计划表与代码漂移）：
- 12 个任务的例数（T09=3 / T10=9 / T11=9 / 其余 1）来自计划 §5 的表，改计划必须改测试。
- 每条 `Edit` 都必须带 `R1: <path>:<line> "<逐字原文>"` 证据（`AGENTS.md` R1：
  没有 grep 证据的源码陈述 = 编造）。
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCH = PROJECT_ROOT / "bench"
RUNNERS = BENCH / "runners"


def _load(name: str, path: Path):
    """按路径加载模块，并**登记进 sys.modules**。

    `ours_scripted.py` 用了 `@dataclass(frozen=True)`，而 dataclasses 处理 frozen 字段时
    会查 `sys.modules[cls.__module__]`——不登记就是一个看起来完全不像导入问题的
    `AttributeError: 'NoneType' object has no attribute '__dict__'`
    （`tests/unit/test_batch.py` 已记录同一个坑）。
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"无法加载 {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ours():
    return _load("bench_runners_ours_scripted", RUNNERS / "ours_scripted.py")


@pytest.fixture(scope="module")
def runner(ours):
    return _load("bench_runners_run_bench", RUNNERS / "run_bench.py")


@pytest.fixture(scope="module")
def judge_mod():
    return _load("bench_judge_for_runner_tests", BENCH / "judge.py")


# ---------------------------------------------------------------- 1 任务解析


def test_load_task_t09_fields(ours):
    """T09 的四个字段必须逐字来自 yaml（prompt 里的 0.5/1/2 是需求原文）。"""
    task = ours.load_task("T09")
    assert task["id"] == "T09"
    assert task["ref"] == "incompressibleFluid/cavity"
    assert task["allowed_files"] == ["system/*", "0/U"]
    assert task["expect"] == "pass"
    assert "0.5/1/2" in task["prompt"]
    assert len(task["specs"]) == 1
    spec = task["specs"][0]
    assert spec["kind"] == "boundary"
    assert spec["patch"] == "movingWall"
    assert spec["comp"] == [2, 0, 0]


def test_load_task_multi_spec_task(ours):
    """T06 有三条断言（yaml note：三条必须一起判）——解析不能只取第一条。"""
    task = ours.load_task("T06")
    assert len(task["specs"]) == 3
    assert [s["kind"] for s in task["specs"]] == ["key_present", "key_present", "dict_value"]
    assert task["specs"][1]["expect_present"] is False


def test_load_task_t12_expect_refuse(ours):
    task = ours.load_task("T12")
    assert task["expect"] == "refuse"
    assert task["allowed_files"] == []
    assert task["specs"] == [{"kind": "behavior", "expect": "refuse"}]


@pytest.mark.parametrize("tid", ["T01", "T02", "T03", "T04", "T05",
                                 "T06", "T07", "T08", "T09", "T10", "T11", "T12"])
def test_specs_count_matches_yaml(ours, tid):
    """`specs` 的条数必须等于 yaml 里 `- {...}` 的行数（不许多、不许少）。"""
    yaml_path = BENCH / "tasks" / f"{tid}.yaml"
    text = yaml_path.read_text(encoding="utf-8")
    n_lines = len(re.findall(r"^\s*-\s*\{", text, re.M))
    assert len(ours.load_task(tid)["specs"]) == n_lines
    assert n_lines >= 1


def test_load_task_unknown_id_raises(ours):
    with pytest.raises(Exception):
        ours.load_task("T99")


# ---------------------------------------------------------------- 2 例展开计数


def test_task_ids_complete(ours):
    assert ours.TASK_IDS == tuple(f"T{i:02d}" for i in range(1, 13))


def test_plans_has_twelve_keys(ours):
    assert len(ours.PLANS) == 12
    assert set(ours.PLANS) == set(ours.TASK_IDS)


@pytest.mark.parametrize("tid,n", [
    ("T01", 1), ("T02", 1), ("T03", 1), ("T04", 1), ("T05", 1), ("T06", 1),
    ("T07", 1), ("T08", 1), ("T09", 3), ("T10", 9), ("T11", 9), ("T12", 1),
])
def test_example_counts(ours, tid, n):
    """例数逐字来自计划 §5（T09=3 / T10=9 / T11=9 / 其余 1）。"""
    assert len(ours.PLANS[tid]) == n


def test_case_ids_unique_and_prefixed(ours):
    seen: set[str] = set()
    for tid, examples in ours.PLANS.items():
        ids = [ex.case_id for ex in examples]
        assert len(ids) == len(set(ids)), f"{tid} 的 case_id 有重复"
        for cid in ids:
            assert cid.startswith(tid), f"{cid} 不以 {tid} 开头（case_id 必须可溯源到任务）"
            assert cid not in seen
            seen.add(cid)
    assert len(seen) == sum(len(v) for v in ours.PLANS.values())


def test_t09_and_t10_ids_follow_plan(ours):
    """计划 §6.2/§5 给的两个例子：T09_u0.5、T10_u0.5_nu1e-05。"""
    assert ours.PLANS["T09"][0].case_id == "T09_u0.5"
    assert [ex.case_id for ex in ours.PLANS["T09"]] == ["T09_u0.5", "T09_u1", "T09_u2"]
    t10_ids = [ex.case_id for ex in ours.PLANS["T10"]]
    assert "T10_u0.5_nu1e-05" in t10_ids
    assert len(t10_ids) == 9
    assert len(ours.PLANS["T11"]) == 9


def test_t09_u2_example_carries_u2_edit(ours):
    """T09 的 2 m/s 那例必须真的把顶盖改成 (2 0 0)——断言 comp=[2,0,0] 指着它。"""
    ex = {e.case_id: e for e in ours.PLANS["T09"]}["T09_u2"]
    assert any("(2 0 0)" in ed.new_value for ed in ex.edits)


def test_t12_does_not_derive_case(ours):
    """T12 是负对照：不派生、不改任何文件（否则 judge 判不出 declined）。"""
    ex = ours.PLANS["T12"][0]
    assert ex.edits == ()
    assert ex.rebuild_mesh is False


def test_rebuild_mesh_only_where_structural(ours):
    """结构性改动（改 vertices / blocks）必须置 rebuild_mesh=True，否则 G2 读旧网格
    —— 这是项目 N7 第 17 条记录的真实假 pass 事故。"""
    assert all(ex.rebuild_mesh for ex in ours.PLANS["T03"])
    assert all(ex.rebuild_mesh for ex in ours.PLANS["T08"])
    for tid in ("T01", "T05", "T07", "T09", "T10", "T11"):
        assert not any(ex.rebuild_mesh for ex in ours.PLANS[tid]), tid


# ---------------------------------------------------------------- 3 L2 归约


def test_reduce_examples_all_pass(runner):
    assert runner.reduce_examples(["pass", "pass", "pass"]) == "pass"


def test_reduce_examples_any_fail(runner):
    assert runner.reduce_examples(["pass", "fail", "pass"]) == "fail"
    assert runner.reduce_examples(["fail"]) == "fail"


def test_reduce_examples_undeterminable_is_malformed(runner):
    """红线（prereg §11 第 7 条）：undeterminable 只能映射 malformed。

    这两条断言就是变异自证的靶子——把它改成 → pass，这里必红。
    """
    assert runner.reduce_examples(["pass", "undeterminable"]) == "malformed"
    assert runner.reduce_examples(["undeterminable"]) == "malformed"
    assert runner.reduce_examples(["fail", "undeterminable"]) == "malformed"


def test_reduce_examples_empty_is_malformed(runner):
    """非退化守卫：空样本不得判 pass/fail（同 prereg §8.2 的 no_data 精神）。"""
    assert runner.reduce_examples([]) == "malformed"


def test_reduce_examples_unknown_state_fails_closed(runner):
    assert runner.reduce_examples(["pass", "wat"]) == "malformed"


def test_reduce_examples_precedence(runner):
    """七态优先级（prereg §4）：blocked > declined > no_artifact > malformed > overclaim > fail > pass。

    L2 是同一批例的合取，优先级必须与 judge 的 run 级一致，否则两层结论会互相矛盾。
    """
    assert runner.reduce_examples(["fail", "no_artifact"]) == "no_artifact"
    assert runner.reduce_examples(["fail", "blocked"]) == "blocked"
    assert runner.reduce_examples(["fail", "overclaim"]) == "overclaim"
    assert runner.reduce_examples(["pass", "declined"]) == "declined"


# ---------------------------------------------------------------- 4 CSV 行


def test_csv_row_has_exactly_15_columns(runner):
    row = runner.csv_row(
        task_id="T01", status="pass",
        gates={g: "0" for g in runner.GATES}, g2b="none",
        repeats=3, unstable=0, tokens_total=0, wall_time_s=1.25,
        human_interventions=0, note="mode=short",
    )
    assert isinstance(row, list)
    assert len(row) == 15
    assert tuple(runner.COLUMNS) == (
        "task_id", "arm", "status", "g1", "g2", "g3", "g4", "g5", "g2b",
        "repeats", "unstable", "tokens_total", "wall_time_s", "human_interventions", "note",
    )
    assert list(row) == [
        "T01", "ours_scripted", "pass", "0", "0", "0", "0", "0", "none",
        "3", "0", "0", "1.25", "0", "mode=short",
    ]


def test_csv_row_rejects_missing_gate(runner):
    with pytest.raises(Exception):
        runner.csv_row(
            task_id="T01", status="pass", gates={"g1": "0"}, g2b="none",
            repeats=1, unstable=0, tokens_total=0, wall_time_s=0.0,
            human_interventions=0, note="",
        )


# ---------------------------------------------------------------- 5 R1 证据


def _all_edits(ours):
    for tid, examples in ours.PLANS.items():
        for ex in examples:
            for ed in ex.edits:
                yield tid, ex, ed


def test_every_edit_has_evidence(ours):
    """R1：每条改动都要有 `R1: <path>:<line> "<逐字原文>"` 证据，一条都不许空。"""
    n = 0
    for tid, ex, ed in _all_edits(ours):
        assert ed.evidence.strip(), f"{tid}/{ex.case_id} 的 {ed.file} 缺 evidence"
        assert ed.evidence.startswith("R1: "), f"{tid}/{ex.case_id}: {ed.evidence!r} 不以 R1: 开头"
        assert re.search(r":\d+\s+\"", ed.evidence), f"{tid}/{ex.case_id} 的证据缺 :line \"原文\": {ed.evidence!r}"
        n += 1
    assert n >= 20, f"只有 {n} 条改动，与计划 §5 的改动量不符"


def test_evidence_quotes_are_non_empty(ours):
    """每段引文都非空，且能被校验器解析成「非空引文」子句。

    空引文会命中任何一行 —— 那是「不可校验被当成校验通过」的典型形态
    （实现里真的出现过：源行自带引号时被包成 `""(U|k|epsilon)""`，正则会匹配到空串，
    于是 `"" in 任意行` 恒真，校验静默通过）。
    """
    for tid, ex, ed in _all_edits(ours):
        clauses = ours.EVIDENCE_RE.findall(ed.evidence)
        assert clauses, f"{tid}/{ex.case_id}: 证据无法解析成 path:line 原文: {ed.evidence!r}"
        for rel, lineno, text in clauses:
            assert text.strip(), f"{tid}/{ex.case_id}: {rel}:{lineno} 的引文为空"
            assert int(lineno) >= 1


def test_every_task_has_at_least_one_evidence(ours):
    """12 个任务里 T12 是唯一允许「无编辑」的（它不派生 case，理由本身就是产物）。"""
    for tid in ours.TASK_IDS:
        edits = [ed for ex in ours.PLANS[tid] for ed in ex.edits]
        if tid == "T12":
            assert edits == []
        else:
            assert edits, f"{tid} 没有任何改动，却声称完成需求"


def test_evidence_paths_are_under_tutorials(ours):
    """证据路径一律从 `$FOAM_TUTORIALS` 起算——代码里不许出现本机绝对路径。"""
    for tid, ex, ed in _all_edits(ours):
        path = ed.evidence.split('"')[0]
        assert path.startswith("R1: $FOAM_TUTORIALS/"), (tid, ed.evidence)
        assert "/home/" not in ed.evidence and "/opt/" not in ed.evidence, (tid, ed.evidence)


def test_edit_files_stay_inside_allowed_files(ours):
    """逐条用 fnmatch 对 yaml 的 allowed_files 求交——G5 越界在 L1 就该被发现。"""
    import fnmatch

    for tid, ex, ed in _all_edits(ours):
        allowed = ours.load_task(tid)["allowed_files"]
        assert any(fnmatch.fnmatchcase(ed.file, g) for g in allowed), (
            f"{tid}/{ex.case_id}: {ed.file} 不在 allowed_files={allowed} 内（G5 会判越界）"
        )


def test_set_edits_have_entry_and_value(ours):
    for tid, ex, ed in _all_edits(ours):
        if ed.kind == "set":
            assert ed.entry, (tid, ed.file)
            assert ed.new_value != "", (tid, ed.file, ed.entry)
        elif ed.kind == "copy_file":
            # 源一律是 $FOAM_TUTORIALS 下的相对路径（可以是 incompressibleFluid/<case>/…，
            # 也可以是 resources/blockMesh/pitzDaily 这类共享字典）
            assert ed.source and not ed.source.startswith("/"), (tid, ed.source)
            assert ed.file in ("0/omega", "system/blockMeshDict", "system/fvSolution"), (tid, ed.file)
        elif ed.kind == "replace_text":
            assert ed.entry, (tid, ed.file)
            assert ed.new_value != "", (tid, ed.file)
        else:
            pytest.fail(f"{tid} 出现未实现的 kind={ed.kind!r}")


# ---------------------------------------------------------------- 6 臂输出语义


def test_apply_rejects_unknown_kind(ours, tmp_path):
    bad = ours.Edit(kind="chmod", file="system/controlDict", evidence='R1: $FOAM_TUTORIALS/x:1 "y"')
    with pytest.raises(ours.UnsupportedEdit):
        ours.apply(tmp_path, ours.Example(case_id="T99", edits=(bad,)))


@pytest.mark.parametrize("tid", ["T01", "T02", "T03", "T04", "T05",
                                 "T06", "T07", "T08", "T09", "T10", "T11", "T12"])
def test_arm_stdout_never_claims_success(ours, judge_mod, tid):
    """致命细节 1：非 T12 的 arm_stdout 绝不能含 CLAIM_MARKERS。

    一旦含了，任何门失败的 run 都会被 judge 判成 `overclaim` 而不是 `fail`
    （`bench/judge.py:45` + `:165`），整批语义静默变样。
    """
    text = ours.arm_stdout_for(tid, mode="short", n_examples=len(ours.PLANS[tid]))
    low = text.lower()
    hits = [k for k in judge_mod.CLAIM_MARKERS if k in text or k in low]
    assert hits == [], f"{tid} 的 arm_stdout 含 CLAIM_MARKERS {hits}: {text!r}"
    assert text.strip(), f"{tid} 的 arm_stdout 不能为空（空串会被读成没产物）"


def test_t12_arm_stdout_points_to_r5(ours, judge_mod):
    """致命细节 1 的唯一例外：T12 必须含 R5_MARKERS 才能判 declined。"""
    text = ours.arm_stdout_for("T12", mode="short", n_examples=1)
    hits = [k for k in judge_mod.R5_MARKERS if k in text]
    assert hits, f"T12 的拒绝理由没指认 R5 边界: {text!r}"
    low = text.lower()
    assert [k for k in judge_mod.CLAIM_MARKERS if k in text or k in low] == []


# ---------------------------------------------------------------- 7 证据自检工具


def test_verify_evidence_reports_missing_tutorials(ours, tmp_path):
    """没有 $FOAM_TUTORIALS 时不许假装「证据没问题」——必须报告不可校验。"""
    problems = ours.verify_evidence(tmp_path / "no-such-tutorials")
    assert problems, "tutorials 根不存在时必须给出问题清单，不能返回空表"
    assert all(isinstance(p, str) for p in problems)


def test_load_task_txt_has_no_yaml_dependency(ours):
    """不许引入 PyYAML（项目只允许标准库）：判据是**没有 yaml 的 import 语句**。

    注释里出现「PyYAML」四个字是允许的（那里正是解释为什么不引它）。
    """
    src = (RUNNERS / "ours_scripted.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(?:import\s+yaml|from\s+yaml)", src, re.M)
    assert not re.search(r"^\s*(?:import\s+(?:ruamel|tomlkit))", src, re.M)


def test_runner_hardcodes_no_local_paths(runner):
    """禁令：runner 里不得硬编码本机绝对路径（路径只能来自参数或 $FOAM_TUTORIALS）。"""
    for path in (RUNNERS / "ours_scripted.py", RUNNERS / "run_bench.py"):
        src = path.read_text(encoding="utf-8")
        # E3 的判据是「导出树里不存在本机用户名这个字面量」。这条测试要断言
        # 证据里没有它，但**不能把字面量写出来**——写了它自己就会被 E3 判红
        # （N7 第 20 条：扫描器会命中它自己）。拼接产生该模式，判据不需要白名单。
        assert ("/home/" + "dr" + "zy") not in src, path
        assert "/opt/openfoam13" not in src, path


def test_runner_does_not_import_batch(runner):
    """计划 §3.2 明确：可以参照 batch.py 的结构，但不得 import 它。"""
    for path in (RUNNERS / "ours_scripted.py", RUNNERS / "run_bench.py"):
        src = path.read_text(encoding="utf-8")
        assert "import batch" not in src and "from batch" not in src, path


def test_json_columns_snapshot(runner, tmp_path):
    """`csv_row` 的输出可直接写盘，且 15 列能被 csv.reader 逐字读回。"""
    import csv

    row = runner.csv_row(
        task_id="T12", status="declined", gates={g: "unmeasured" for g in runner.GATES},
        g2b="unknown", repeats=3, unstable=0, tokens_total=0, wall_time_s=0.5,
        human_interventions=0, note='declined（R5）; mode=short',
    )
    out = tmp_path / "one.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(runner.COLUMNS)
        w.writerow(row)
    rows = list(csv.reader(out.open(encoding="utf-8", newline="")))
    assert tuple(rows[0]) == runner.COLUMNS
    assert len(rows[1]) == 15
    assert dict(zip(rows[0], rows[1]))["status"] == "declined"
    assert json.dumps(row, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 回归：相对 --dest 必须被绝对化（2026-10-29 整批实测 bug）
# ---------------------------------------------------------------------------


def test_resolve_batch_root_makes_relative_dest_absolute(runner, tmp_path, monkeypatch):
    """`--dest bench/runs` 这种相对路径必须变成绝对路径。

    实测事故（2026-10-29 首次整批）：相对 `--dest` 让下游 `foamDictionary <相对路径>`
    在夹具自己的 cwd 下「文件不存在」→ `apply` 失败 → 跑的是**原始 tutorial**。
    G5 拿 base/（改前副本）做 diff，此时 base == case → RC=0 照样过，
    于是「五门全绿、需求没落地」，8/12 个任务假 fail。

    这条只测纯函数（N7 第 18 条：判据不许依赖机器速度；逻辑抽成纯函数比端到端稳）。
    """
    monkeypatch.chdir(tmp_path)
    got = runner.resolve_batch_root("bench/runs", "m4b")
    assert got.is_absolute(), f"相对 --dest 没被绝对化：{got}"
    assert got == (tmp_path / "bench" / "runs" / "m4b").resolve()
    # 已经是绝对路径时不得叠加 cwd
    abs_dest = tmp_path / "absdest"
    assert runner.resolve_batch_root(str(abs_dest), "m4b") == (abs_dest / "m4b").resolve()


def test_example_apply_error_is_surfaced_into_row_note(runner):
    """例级 `apply_error` 必须能上浮到行 note。

    实测事故的第二个成因：旧版只收集 `r["notes"]`（run 级），而单例任务的例级
    `apply_error` 从不出现 → CSV 里一行 fail 看不出「改动根本没落地」。
    这条断的是**可诊断性**，不是判据本身：没有它，下一次同类失败同样只剩一个 fail。
    """
    runs = [{
        "run_mode": "short", "notes": [],
        "examples": [
            {"case_id": "T01", "apply_error": "foamDictionary -set endTime 失败（rc=1）", "notes": []},
            {"case_id": "T02", "apply_error": None, "notes": ["派生后补 omega"]},
        ],
        "judge": {"reason": "x"}, "gates": {g: "0" for g in runner.GATES},
        "g2b": "none", "wall": 1.0, "run_dir": Path("/nonexistent"),
    }]
    parts = runner._example_note_parts(runs[0])
    joined = " | ".join(parts)
    assert "改动未落地[T01]" in joined, "例级 apply_error 没上浮"
    assert "foamDictionary" in joined
    assert "派生后补 omega" in joined, "例级 notes 没上浮"
    # 无 examples 的 run（T12）不得炸
    assert runner._example_note_parts({"notes": []}) == []
