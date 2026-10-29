"""模块 H（scripts/batch.py）的 L1 单元测试：只测展开与校验，**零 OpenFOAM 依赖**。

对应 STATUS.md N3 #32–#33（2026-10-29 用户裁定）与 AGENTS.md R7/R12。

## 这一层为什么必须存在（分工判据）

`batch.py` 的风险不在"会不会跑求解"（那由 contract 层覆盖），而在**展开**：
笛卡尔积是隐式的，3 维 × 4 值 = 64 例，跑到一半才发现就太晚了。所以展开规则、
上限、命名、覆盖顺序都必须能在没有 OpenFOAM 的机器上判。

## 判据来自哪里

- 展开上限 50：`batch.py` 的 `DEFAULT_MAX_CASES`，理由写在模块 docstring §二。
- id 只允许 `[a-z0-9_.-]`：它会被用作目录名（`runs/<批次>/<case_id>/`），
  含其它字符会让「日志在哪」不可判定。
- vary 覆盖 base.set：同 `{file, entry}` 时 vary 胜出（docstring §二 第 3 条）。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "batch.py"


def _load_batch():
    """直接导入 batch.py 的纯函数（不起子进程），这样展开规则能被逐条断言。

    **必须先把模块登记进 `sys.modules`**：batch.py 用了 `@dataclass`，而 dataclasses 在
    处理 `ClassVar`/`KW_ONLY` 时会查 `sys.modules[cls.__module__]`——不登记就是一个
    `AttributeError: 'NoneType' object has no attribute '__dict__'`，看起来完全不像导入问题。
    """
    name = "_batch_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


batch = _load_batch()


def write_cases(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def minimal_doc(**over) -> dict:
    doc = {
        "base": {
            "id": "cavity",
            "source": "incompressibleFluid/cavity",
            "spec": {"geometry": "二维方腔", "objective": "transient"},
            "set": [
                {"file": "constant/momentumTransport", "entry": "simulationType",
                 "new_value": "laminar"},
            ],
        }
    }
    doc.update(over)
    return doc


# ---------------------------------------------------------------------------
# 展开：笛卡尔积 / 命名 / 覆盖顺序
# ---------------------------------------------------------------------------


def test_cartesian_product(tmp_path: Path):
    """2 维 × 2 值 → 4 例，id 按声明顺序拼接。"""
    doc = minimal_doc(vary=[
        {"name": "cm", "file": "system/blockMeshDict", "entry": "convertToMeters",
         "values": ["0.1", "0.2"]},
        {"name": "nu", "file": "constant/physicalProperties", "entry": "nu",
         "values": ["1e-5", "2e-5"]},
    ])
    base, varies = batch.parse_cases(write_cases(tmp_path, doc))
    cases = batch.expand(base, varies, 50)

    assert [c.id for c in cases] == [
        "cavity_cm0.1_nu1e-5",
        "cavity_cm0.1_nu2e-5",
        "cavity_cm0.2_nu1e-5",
        "cavity_cm0.2_nu2e-5",
    ], "展开顺序必须固定为 vary 的声明顺序（否则两次运行的 case_id 集合相同但顺序不同）"


def test_no_vary_yields_single_case(tmp_path: Path):
    """没有 vary → 只有 base 一个 case（批跑 1 例也是合法输入）。"""
    base, varies = batch.parse_cases(write_cases(tmp_path, minimal_doc()))
    cases = batch.expand(base, varies, 50)
    assert len(cases) == 1 and cases[0].id == "cavity"


def test_vary_overrides_base_set(tmp_path: Path):
    """同一 {file, entry} 出现在 base.set 与 vary 里 → vary 胜出，且不重复出现。"""
    doc = minimal_doc(vary=[
        {"name": "nu", "file": "constant/physicalProperties", "entry": "nu",
         "values": ["7e-6"]},
    ])
    doc["base"]["set"].append(
        {"file": "constant/physicalProperties", "entry": "nu", "new_value": "1e-5"}
    )
    base, varies = batch.parse_cases(write_cases(tmp_path, doc))
    case = batch.expand(base, varies, 50)[0]

    entries = [(i["file"], i["entry"]) for i in case.set]
    assert entries.count(("constant/physicalProperties", "nu")) == 1, (
        f"同一 entry 只能出现一次，实得 {entries}"
    )
    nu = [i for i in case.set if i["entry"] == "nu"][0]
    assert nu["new_value"] == "7e-6", "vary 必须覆盖 base.set 的值"


def test_id_is_lowercase_and_dir_safe(tmp_path: Path):
    """参数值含中文/空格/斜杠时，id 必须仍能当目录名。"""
    doc = minimal_doc(vary=[
        {"name": "case", "file": "system/controlDict", "entry": "deltaT",
         "values": ["1e-3 s", "水/值"]},
    ])
    base, varies = batch.parse_cases(write_cases(tmp_path, doc))
    cases = batch.expand(base, varies, 50)
    for case in cases:
        assert batch.ID_RE.match(case.id), f"{case.id!r} 不是合法目录名"


# ---------------------------------------------------------------------------
# 上限与非法输入（都是 71：整批中止，不是 64 用法错误）
# ---------------------------------------------------------------------------


def test_expansion_over_cap_aborts(tmp_path: Path):
    """超上限 → Aborted（71），且在**跑任何 case 之前**就失败。"""
    doc = minimal_doc(vary=[
        {"name": "a", "file": "x", "entry": "y", "values": [str(i) for i in range(8)]},
        {"name": "b", "file": "x", "entry": "z", "values": [str(i) for i in range(8)]},
    ])
    base, varies = batch.parse_cases(write_cases(tmp_path, doc))
    with pytest.raises(batch.Aborted) as exc:
        batch.expand(base, varies, 50)
    assert "64 例" in str(exc.value) and "超过上限" in str(exc.value)


def test_max_cases_can_be_raised(tmp_path: Path):
    """--max-cases 显式放宽后同一份输入可以展开（上限是策略，不是常量）。"""
    doc = minimal_doc(vary=[
        {"name": "a", "file": "x", "entry": "y", "values": [str(i) for i in range(8)]},
        {"name": "b", "file": "x", "entry": "z", "values": [str(i) for i in range(8)]},
    ])
    base, varies = batch.parse_cases(write_cases(tmp_path, doc))
    assert len(batch.expand(base, varies, 64)) == 64


def test_duplicate_id_after_sanitize_is_rejected(tmp_path: Path):
    """两个不同的值 sanitize 后撞名 → 必须报错，不能静默覆盖目录。"""
    doc = minimal_doc(vary=[
        {"name": "nu", "file": "f", "entry": "nu", "values": ["1e-5", "1e_5"]},
    ])
    base, varies = batch.parse_cases(write_cases(tmp_path, doc))
    # "1e-5" 与 "1e_5" 都会变成 "1e-5"
    with pytest.raises(batch.Aborted) as exc:
        batch.expand(base, varies, 50)
    assert "重复 id" in str(exc.value)


@pytest.mark.parametrize(
    "doc, needle",
    [
        ({"base": {}}, "`id`"),
        ({"base": {"id": "a"}}, "`source`"),
        ({"base": {"id": "a", "source": "s"}}, "必须给 `spec`"),
        ({"base": {"id": "a", "source": "s", "spec": {}, "spec_file": "x.json"}}, "只能给一个"),
        ({"base": {"id": "a b", "source": "s", "spec": {}}}, "非法字符"),
        ({"base": {"id": "a", "source": "s", "spec": {},
                   "set": [{"file": "f", "entry": "e"}]}}, "`new_value`"),
        ({"base": {"id": "a", "source": "s", "spec": {},
                   "set": [{"file": "f", "entry": "e", "new_value": None}]}}, "不能是 null"),
        ({"base": {"id": "a", "source": "s", "spec": {}},
          "vary": [{"name": "n", "file": "f", "entry": "e", "values": []}]}, "非空数组"),
    ],
)
def test_invalid_cases_json_is_named(tmp_path: Path, doc: dict, needle: str):
    """每种结构错误都要指名道姓（只说「cases.json 非法」等于让人自己猜）。"""
    with pytest.raises(batch.Aborted) as exc:
        batch.parse_cases(write_cases(tmp_path, doc))
    assert needle in str(exc.value), f"错误信息里应出现 {needle!r}，实得 {str(exc.value)!r}"


def test_missing_file_aborts(tmp_path: Path):
    with pytest.raises(batch.Aborted) as exc:
        batch.parse_cases(tmp_path / "absent.json")
    assert "不存在" in str(exc.value)


# ---------------------------------------------------------------------------
# 门日志解析（unmeasured 的语义）
# ---------------------------------------------------------------------------


def test_missing_gate_log_is_unmeasured(tmp_path: Path):
    """日志不存在 → unmeasured，不许猜成 0 或 1。"""
    rc, g2b = batch.read_gate(tmp_path / "log.g3")
    assert rc == "unmeasured" and g2b is None


def test_gate_rc_parsed(tmp_path: Path):
    path = tmp_path / "log.g1"
    path.write_text("RC=1\n\nsomething failed\n", encoding="utf-8")
    assert batch.read_gate(path) == ("1", None)


def test_g2b_parsed_from_second_line(tmp_path: Path):
    path = tmp_path / "log.g2"
    path.write_text("RC=0\nG2B=hard:2\n", encoding="utf-8")
    assert batch.read_gate(path) == ("0", "hard:2")


def test_diagnostics_parsed():
    text = (
        "G2 RC=0  x\n"
        "OBJ=match  (需求 objective=steady，实际 ddtSchemes=steadyState)\n"
        "GEO=cells=400  需求 geometry=二维方腔\n"
        "RE=1e+05  (...)\n"
        "RES=coarse  (...)\n"
    )
    diag = batch.parse_diagnostics(text)
    assert set(diag) == {"OBJ", "GEO", "RE", "RES"}


# ---------------------------------------------------------------------------
# CLI 契约（子进程）：退出码
# ---------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(SCRIPT), *args], capture_output=True, text=True, timeout=120)


def test_usage_error_exits_64():
    """无参数 → 64（不是 2：2 在 verify_case.sh 里是 G2 门失败）。"""
    proc = _run()
    assert proc.returncode == 64, f"实得 {proc.returncode}"
    assert "用法" in proc.stderr or "usage" in proc.stderr.lower()


def test_unknown_flag_exits_64():
    assert _run("--nope").returncode == 64


def test_bad_jobs_exits_64():
    """--jobs 超上限 → 64 并说明理由（R7：本机内存有限）。"""
    proc = _run("--cases", "x.json", "--jobs", "8")
    assert proc.returncode == 64
    assert "jobs" in proc.stderr.lower()


def test_dry_run_creates_nothing(tmp_path: Path):
    """--dry-run 必须只打印、不建目录（否则「先看一眼」这个动作本身就有副作用）。"""
    path = write_cases(tmp_path, minimal_doc())
    dest = tmp_path / "runs"

    proc = _run("--cases", str(path), "--dest", str(dest), "--dry-run")

    assert proc.returncode == 0, proc.stderr
    assert "cavity" in proc.stdout
    assert not dest.exists(), "--dry-run 不应创建任何目录"


# ---------------------------------------------------------------------------
# 发布自包含性（2026-10-29 实测：batch 在发布包里起不来）
# ---------------------------------------------------------------------------


def test_emittable_is_a_subset_of_judge_states():
    """`batch.EMITTABLE ⊆ bench/judge.py 的 STATES`。

    既然 batch 不能从 judge 导入（judge 不随包发布），就必须由**仓库里的测试**来保证
    两者不漂移。谁把七态改个拼写而没同步 EMITTABLE，这条会红。
    """
    judge_path = PROJECT_ROOT / "bench" / "judge.py"
    assert judge_path.is_file(), "仓库里应有 bench/judge.py"
    spec = importlib.util.spec_from_file_location("_judge_for_test", judge_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_judge_for_test"] = module
    spec.loader.exec_module(module)

    extra = set(batch.EMITTABLE) - set(module.STATES)
    assert not extra, f"EMITTABLE 里有 judge 不认识的状态: {sorted(extra)}"


def test_batch_does_not_import_bench():
    """batch.py 的**可执行代码**里不得出现 `bench/`（它不随发布包发布）。

    只看代码不看注释：注释里可以（而且应该）解释"为什么不从 judge 导入"。
    """
    code_lines = [
        line for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    hits = [line for line in code_lines if "bench/" in line or "bench.judge" in line]
    assert not hits, (
        "batch.py 不能依赖 bench/（发布包不含它）：\n" + "\n".join(hits)
    )


def test_release_package_is_self_contained():
    """batch.py 在**只有发布包**的环境里必须能起来（2026-10-29 实测踩了两次）。

    两次都是"仓库里能跑、解出 tar.gz 就崩"：
      ① `from bench.judge import STATES` —— `bench/` 不进发布包；
      ② 结尾无条件调用 `check_contracts.py` —— 它是治理脚本，也不进发布包。

    判据：把发布包组装出来，在其中跑 `batch.py --dry-run`，必须退 0。
    这条测试比"读代码里有没有 bench/"更强：它真的组装并执行交付物。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        build = subprocess.run(
            ["bash", str(PROJECT_ROOT / "scripts" / "make_release.sh"),
             "--dest", tmp, "--no-tar"],
            capture_output=True, text=True, timeout=300,
        )
        assert build.returncode == 0, f"组装失败：{build.stdout}\n{build.stderr}"
        pkg = next(Path(tmp).glob("foam-mate-*"))
        cases = write_cases(Path(tmp), minimal_doc())

        env = dict(os.environ)
        env.pop("WM_PROJECT_DIR", None)          # dry-run 不该需要 OpenFOAM 环境
        proc = subprocess.run(
            [sys.executable, str(pkg / "scripts" / "batch.py"),
             "--cases", str(cases), "--dest", str(Path(tmp) / "runs"), "--dry-run"],
            capture_output=True, text=True, timeout=180, env=env,
        )

    assert proc.returncode == 0, (
        f"发布包里的 batch.py 起不来（退 {proc.returncode}）：\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "cavity" in proc.stdout


def test_wall_seconds_keeps_two_decimals():
    """F7 的确定性防线：耗时换算必须保留两位小数，不能取整。

    为什么放在**单元层**：端到端那条曾用 `sum(wall_time_s) > 0` 判，结果偶发变红
    （同一份代码，全量跑一次红、单独跑两次绿）——因为短跑的实际耗时取决于机器当时多快。
    **判据依赖机器速度，就不是判据。**

    为什么单独测纯函数：F7 的 bug 在**测量**那一步（`int(round(...))`），
    不在写出那一步。只测 `write_results` 的 passthrough 抓不到它
    （实测：把 int 加回去，passthrough 测试仍然绿）。
    """
    assert batch.wall_seconds(0.54) == 0.54, "0.54 秒必须原样保留"
    assert batch.wall_seconds(0.07) == 0.07, "0.07 秒必须原样保留（取整会变 0）"
    assert batch.wall_seconds(12.3456) == 12.35, "两位小数四舍五入"
    # 亚厘秒确实该是 0.00：这不是缺陷，是"这次跑得比时钟分辨率还快"
    assert batch.wall_seconds(0.004) == 0.0


def test_wall_time_written_as_is(tmp_path: Path):
    """`write_results` 不得改写 `wall_time_s`（测量值与落盘值必须是同一个数）。"""
    outcomes = [
        batch.Outcome(
            case_id="c1", status="pass",
            gates={g: "0" for g in ("g1", "g2", "g3", "g4", "g5")},
            g2b="none", wall_time_s=0.54, note="n", metrics={},
        ),
        batch.Outcome(
            case_id="c2", status="pass",
            gates={g: "0" for g in ("g1", "g2", "g3", "g4", "g5")},
            g2b="none", wall_time_s=0.07, note="n", metrics={},
        ),
    ]
    path = tmp_path / "results.csv"
    batch.write_results(path, outcomes, batch_id="t", mode="short")

    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert [r["wall_time_s"] for r in rows] == ["0.54", "0.07"], (
        "wall_time_s 必须是两位小数原文；取整会让 12 例短跑全写成 0，"
        "那样「结论可从 CSV 重算」（R7）就失去意义"
    )
