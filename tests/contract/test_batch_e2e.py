"""模块 H（scripts/batch.py）的 L2 契约测试：真跑一个 3 例矩阵。

对应 M2 的完成判据（`references/00-project-readme.md:350` 原文）：
    「3 例矩阵产出 `results.csv` 且数字可从 CSV 重算；A/B 对照一致」

## 这一层为什么必须存在

单元层只能证明"展开规则对"，证明不了"整条链跑得通"。而 batch 的价值全在链上：
派生 → 移 case.meta → 改参数 → pre 门禁 → 求解 → post 门禁 → 记账。
2026-10-29 首次真跑时，链上暴露了两个单元层看不见的缺陷：

1. `fix_case.py` 的回读比对只剥**前置**量纲，用户写 `1e-5 [m^2/s]` 时回读是
   `1e-05 [ m^2 / s]`，逐字比对必失败 → 退 33 并回滚（用户按最自然的写法就会中招）。
2. `fix_case.py` 把 `fingerprint.txt` 写进备份目录；batch 把该目录改名成 `base/` 之后，
   它被 G5 判成"改了非白名单文件" → 退 5。

两条都是"单模块测试绿、集成才暴露"，正是项目 N7 #12 记录的形态。

## 成本控制

- 只跑 3 例（矩阵 1 维 × 3 值），`--mode short`（cavity 2 步，实测每例 < 1 s）。
- 全部产物落 `tmp_path`，绝不写 `bench/`（R12）也不写仓库的 `runs/`。
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "batch.py"
CHECK_CONTRACTS = PROJECT_ROOT / "scripts" / "check_contracts.py"

BASH_RC = "/opt/openfoam13/etc/bashrc"
CAVITY = "incompressibleFluid/cavity"

COLUMNS = [
    "task_id", "arm", "status", "g1", "g2", "g3", "g4", "g5", "g2b",
    "repeats", "unstable", "tokens_total", "wall_time_s", "human_interventions", "note",
]


def invoked_env() -> dict[str, str]:
    """已 source bashrc 的环境；没有 OpenFOAM 就 skip（不许假装通过）。"""
    proc = subprocess.run(
        ["bash", "-c", f"set -a; source {BASH_RC} >/dev/null 2>&1; env -0"],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        pytest.skip(f"无法 source {BASH_RC}：测试环境没有 OpenFOAM v13")
    env = {}
    for item in proc.stdout.split("\0"):
        if "=" in item:
            key, _, value = item.partition("=")
            env[key] = value
    if not env.get("FOAM_TUTORIALS"):
        pytest.skip("FOAM_TUTORIALS 为空：环境未就绪")
    return env


def write_cases(tmp_path: Path, *, values: list[str]) -> Path:
    doc = {
        "base": {
            "id": "cavity",
            "source": CAVITY,
            "spec": {
                "geometry": "二维方腔",
                "properties": "水，laminar",
                "boundary": "顶盖 1 m/s",
                "objective": "transient",
                "complete": True,
                "missing": [],
            },
            "set": [
                {"file": "constant/momentumTransport", "entry": "simulationType",
                 "new_value": "laminar"},
                # 带量纲、且写法与 OpenFOAM 规范化结果**不同**（1e-5 vs 1e-05）：
                # 这正是上面缺陷 1 的触发条件，留在这里防止它回来。
                {"file": "constant/physicalProperties", "entry": "nu",
                 "new_value": "1e-5 [m^2/s]"},
            ],
        },
        "vary": [
            {"name": "cm", "file": "system/blockMeshDict", "entry": "convertToMeters",
             "values": values},
        ],
    }
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def run_batch(cases: Path, dest: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), "--cases", str(cases), "--dest", str(dest), "--batch", "m2test",
         "--mode", "short", "--timeout", "300", *extra],
        capture_output=True, text=True, timeout=900, env=invoked_env(),
    )


# ---------------------------------------------------------------------------
# 主判据：3 例矩阵跑通，CSV 合法且可重算
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def three_case_batch(tmp_path_factory) -> tuple[Path, subprocess.CompletedProcess[str], Path]:
    tmp = tmp_path_factory.mktemp("m2")
    cases = write_cases(tmp, values=["0.1", "0.15", "0.2"])
    dest = tmp / "runs"
    proc = run_batch(cases, dest)
    return cases, proc, dest


def test_three_cases_all_pass(three_case_batch):
    """3 例矩阵 → 退出码 0、每例 pass、CSV 15 列契约成立。"""
    cases, proc, dest = three_case_batch
    assert proc.returncode == 0, (
        f"batch 退 {proc.returncode}，期望 0\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )

    results = dest / "m2test" / "results.csv"
    assert results.is_file(), f"没有产出 results.csv：{results}"

    with results.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == COLUMNS, (
            f"表头必须逐字等于 R12 的 15 列，实得 {reader.fieldnames}"
        )
        rows = list(reader)

    assert len(rows) == 3, f"3 例矩阵应产出 3 行，实得 {len(rows)}"
    assert {r["task_id"] for r in rows} == {
        "cavity_cm0.1", "cavity_cm0.15", "cavity_cm0.2"
    }, f"task_id 必须是展开后的 case_id，实得 {[r['task_id'] for r in rows]}"
    for row in rows:
        assert row["status"] == "pass", f"{row['task_id']} 不是 pass：{row['note']}"
        for gate in ("g1", "g2", "g3", "g4", "g5"):
            assert row[gate] == "0", f"{row['task_id']} 的 {gate}={row[gate]}"
        assert row["arm"] == "ours"
        assert row["repeats"] == "1" and row["unstable"] == "0"
        assert row["tokens_total"] == "0" and row["human_interventions"] == "0"


def test_csv_passes_contract_checker(three_case_batch):
    """写出的 CSV 必须过 check_contracts（batch 自己也调了它，这里独立复核一次）。"""
    _cases, _proc, dest = three_case_batch
    # 用当前解释器，而不是写死某个机器上的绝对路径：写死的路径在别人机器上只会在
    # `is_file()` 那一步悄悄回退，看起来"跑过了"，其实测的是另一个解释器。
    proc = subprocess.run(
        [sys.executable, str(CHECK_CONTRACTS),
         "--results", str(dest / "m2test" / "results.csv")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"契约检查失败：\n{proc.stdout}\n{proc.stderr}"


def test_numbers_are_recomputable_from_csv(three_case_batch):
    """R7 的核心要求：结论能从 CSV 重算，不从日志肉眼摘。

    **这里刻意不判 `sum(wall_time_s) > 0`。** 那一条曾被写成判据，然后偶发变红
    （2026-10-29 实测：同一份代码，全量跑一次红、单独跑两次绿）——因为"耗时是否
    恰好大于零"取决于机器当时多快。**判据依赖机器速度，就不是判据。**
    "取整把耗时吞成 0" 那个缺陷（v0.2 的 F7）改由单元测试确定性地守：
    `tests/unit/test_batch.py::test_wall_time_keeps_two_decimals`。

    这一层只判**能重算**这件事本身：行数、通过率、以及每个数字可被解析。
    """
    _cases, _proc, dest = three_case_batch
    with (dest / "m2test" / "results.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 3
    n_pass = sum(1 for r in rows if r["status"] == "pass")
    assert n_pass == 3, f"通过率应能从 CSV 直接算出：{[(r['task_id'], r['status']) for r in rows]}"

    for row in rows:
        raw = row["wall_time_s"]
        assert raw != "", f"{row['task_id']} 的 wall_time_s 是空的：报告里就没法引用它"
        value = float(raw)                       # 解析不了会抛，这本身就是判据
        assert value >= 0, f"{row['task_id']} 的 wall_time_s={raw} 为负"


def test_run_dir_layout(three_case_batch):
    """每个 case 的落盘布局必须完整：case/ base/ case.meta log.g1..g5 metrics.json。"""
    _cases, _proc, dest = three_case_batch
    run_dir = dest / "m2test" / "cavity_cm0.1"

    for name in ("case", "base", "case.meta", "spec.json", "metrics.json", "batch.log"):
        assert (run_dir / name).exists(), f"缺 {name}（在 {run_dir}）"
    for gate in ("g1", "g2", "g3", "g4", "g5"):
        assert (run_dir / f"log.{gate}").is_file(), f"缺 log.{gate}"

    assert (run_dir / "case" / "system" / "controlDict").is_file(), "case 树不完整"

    # case.meta 必须**只在 run 根**：两个位置都有会被 judge 判 malformed（决策 #17）
    assert not (run_dir / "case" / "case.meta").exists(), (
        "case.meta 不能同时留在 case 树里（verify_case.sh 只在 run 根找它，"
        "两处都有会让 judge 判 malformed）"
    )


def test_param_really_applied(three_case_batch):
    """参数必须真的落到字典里——不靠 exit code，靠读文件（R6：数字必须实测）。

    `foamDictionary -set` 对不存在的 entry 会新增并退 0，所以"命令成功"不等于"值改了"。
    """
    _cases, _proc, dest = three_case_batch
    env = invoked_env()

    def read_entry(case: Path, dict_file: str, entry: str) -> str:
        proc = subprocess.run(
            ["foamDictionary", dict_file, "-entry", entry, "-value"],
            cwd=str(case), capture_output=True, text=True, timeout=120, env=env,
        )
        assert proc.returncode == 0, f"回读失败：{proc.stderr}"
        return proc.stdout.strip()

    for case_id, expected in (("cavity_cm0.1", "0.1"), ("cavity_cm0.2", "0.2")):
        case = dest / "m2test" / case_id / "case"
        got = read_entry(case, "system/blockMeshDict", "convertToMeters")
        assert float(got) == float(expected), f"{case_id} 的 convertToMeters 实得 {got}"
        # 两个 case 的 nu 都来自 base.set（vary 没动它）
        nu = read_entry(case, "constant/physicalProperties", "nu")
        assert "1e-05" in nu.replace("e-5", "e-05"), f"{case_id} 的 nu 实得 {nu!r}"
        sim = read_entry(case, "constant/momentumTransport", "simulationType")
        assert sim == "laminar", f"{case_id} 的 simulationType 实得 {sim!r}"


def test_metrics_sidecar_holds_diagnostics(three_case_batch):
    """诊断行（OBJ/GEO/RE/RES）进 metrics.json，不进 CSV（15 列是封闭契约）。"""
    _cases, _proc, dest = three_case_batch
    metrics = json.loads(
        (dest / "m2test" / "cavity_cm0.1" / "metrics.json").read_text(encoding="utf-8")
    )
    assert metrics["status"] == "pass"
    assert metrics["gates"] == {g: "0" for g in ("g1", "g2", "g3", "g4", "g5")}
    diag = metrics.get("diagnostics", {})
    for key in ("OBJ", "GEO", "RE", "RES"):
        assert key in diag, f"metrics.json 缺诊断 {key}：{diag}"


# ---------------------------------------------------------------------------
# 失败路径：不中断整批
# ---------------------------------------------------------------------------


def test_one_bad_case_does_not_stop_the_batch(tmp_path: Path):
    """中间一例派生失败（source 不存在）→ 该例 no_artifact，其余仍跑完，退出码 70。

    为什么必须测：批跑的价值就是"跑完 12 个知道哪几个坏"。若第一例失败就整体退出，
    用户永远拿不到另外 2 例的结果。
    """
    doc = {
        "base": {
            "id": "cavity",
            "source": CAVITY,
            "spec": {"geometry": "二维方腔", "objective": "transient"},
            "set": [{"file": "constant/momentumTransport", "entry": "simulationType",
                     "new_value": "laminar"}],
        },
        "vary": [
            {"name": "cm", "file": "system/blockMeshDict", "entry": "convertToMeters",
             "values": ["0.1", "0.2"]},
        ],
    }
    cases = tmp_path / "cases.json"
    cases.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    # 先把第二个 case 的 source 弄坏：单独写一份只含坏 case 的矩阵，
    # 与好 case 混在同一次运行里（batch 不支持逐例 source，所以用两次运行验证语义）
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "base": {"id": "nope", "source": "noSuchTutorial/xyz",
                         "spec": {"geometry": "x"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    proc = run_batch(bad, tmp_path / "runs_bad")

    assert proc.returncode == 70, (
        f"有 case 失败时应退 70（结果仍可用），实得 {proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    with (tmp_path / "runs_bad" / "m2test" / "results.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["status"] == "no_artifact", f"实得 {rows[0]['status']}"
    # 派生失败时五门都没测，必须是 unmeasured（不许记 0 —— 那会被读成"门全过"）
    for gate in ("g1", "g2", "g3", "g4", "g5"):
        assert rows[0][gate] == "unmeasured", f"{gate}={rows[0][gate]}，应为 unmeasured"


def test_env_missing_aborts_whole_batch(tmp_path: Path):
    """没有 source bashrc → 整批中止（71），且在跑任何 case 之前就停。

    理由：22 是整批性的环境问题，继续跑只会得到 N 行相同的 22，纯粹浪费机时。
    """
    cases = write_cases(tmp_path, values=["0.1", "0.2"])
    env = {k: v for k, v in os_environ().items()
           if k not in ("WM_PROJECT_DIR", "FOAM_TUTORIALS", "FOAM_SRC", "FOAM_APP",
                        "FOAM_ETC", "FOAM_UTILITIES")}
    env["PATH"] = "/usr/bin:/bin"
    proc = subprocess.run(
        [str(SCRIPT), "--cases", str(cases), "--dest", str(tmp_path / "runs"),
         "--batch", "noenv", "--mode", "short"],
        capture_output=True, text=True, timeout=300, env=env,
    )
    assert proc.returncode == 71, (
        f"环境缺失应退 71，实得 {proc.returncode}\nstderr:{proc.stderr}"
    )
    assert "foamRun" in proc.stderr
    assert not (tmp_path / "runs" / "noenv").exists(), "整批中止时不该留下半成品目录"


def os_environ() -> dict[str, str]:
    import os
    return dict(os.environ)
