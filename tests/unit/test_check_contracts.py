"""模块 G（`scripts/check_contracts.py`）的 L1 测试，共 6 项。

规格来源（唯一权威 = 编排方下发的 G 规格；与代码里的常量一一对应）：
  - `AGENTS.md` R12：`bench/results.csv` 列固定 15 列、结果状态七态
  - `AGENTS.md` R3 / `scripts/new_case.sh`：`case.meta` 六键
  - `references/09-architecture-and-test-plan.md` §G

===============================================================================
这个脚本是**脚本不是测试辅助**
===============================================================================
M2 的 `bench/batch.py` 与 M4b 的 adapter 将来要复用它，所以判据写在脚本里、测试只喂输入
看退出码。测试不做"脚本应该这样实现"的断言（那是实现细节），只钉三件可观察的事：
退出码（0 / 40 / 64）、stderr 是否点名了违规对象、合规输入是否真的放行。

七态**不在这里重写**：从 `bench/judge.py` 导入 `STATES`。测试若自己列一份，就会在
"改了一处忘改另一处"时静默通过——G3 就白测了。

本层**不需要 OpenFOAM**：G6 唯一的外部依赖是 `scripts/new_case.sh`（bash + cp + 标准库
json），伪 tutorial 树在 `tmp_path` 下现造。
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_contracts.py"

# 七态从 judge 导入（DRY：G4 与 judge 的判定必须同源）
sys.path.insert(0, str(REPO_ROOT / "bench"))
from judge import STATES  # noqa: E402  （必须在 sys.path 之后导入）

# ---------------------------------------------------------------------------
# 契约常量（逐字抄自规格，空格与大小写都是判据的一部分）
# ---------------------------------------------------------------------------

HEADER = (
    "task_id,arm,status,g1,g2,g3,g4,g5,g2b,repeats,unstable,"
    "tokens_total,wall_time_s,human_interventions,note"
)

META_KEYS = (
    "source",
    "derived_at",
    "spec",
    "changes",
    "allowed_files",
    "schema_version",
)

EXIT_OK = 0
EXIT_VIOLATION = 40


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _run(*args: str) -> subprocess.CompletedProcess:
    """跑被测脚本。用 `sys.executable`，不依赖 PATH 上的 python3。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _row(**overrides: str) -> list[str]:
    """一行合法的 results.csv 数据（15 列，顺序 = HEADER）。

    默认值全部取"合法"侧：任何一条违规都必须是调用方显式改出来的，
    不能因为默认值自己不合法而在别的用例里连带变红。
    """
    cells = {
        "task_id": "T01",
        "arm": "hermes",
        "status": "pass",
        "g1": "1",
        "g2": "1",
        "g3": "1",
        "g4": "1",
        "g5": "1",
        "g2b": "none",
        "repeats": "3",
        "unstable": "0",
        "tokens_total": "1234",
        "wall_time_s": "1.5",
        "human_interventions": "0",
        "note": "",
    }
    cells.update(overrides)
    return [cells[name] for name in HEADER.split(",")]


def _write_csv(path: Path, header: list[str] | str, rows: list[list[str]]) -> None:
    """按行写 CSV；`header` 传 str 时按逗号切（用于造坏表头）也是等价的。"""
    if isinstance(header, str):
        header = header.split(",")
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _meta(**overrides) -> dict:
    """一份合法的 case.meta（六键齐）。"""
    meta = {
        "source": "incompressibleFluid/cavity",
        "derived_at": "2026-10-28T21:30:00+08:00",
        "spec": {"geometry": "二维方腔", "properties": "水"},
        "changes": [],
        "allowed_files": ["system/*", "constant/*", "0/*"],
        "schema_version": 1,
    }
    meta.update(overrides)
    return meta


def _write_meta(path: Path, meta: dict) -> None:
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# G1 · 仓库真实 results.csv（只有表头、0 数据行）必须放行
# ---------------------------------------------------------------------------

def test_g1_real_results_csv_passes() -> None:
    real = REPO_ROOT / "bench" / "results.csv"
    assert real.is_file(), "仓库存放点缺失：bench/results.csv"

    proc = _run("--results", str(real))

    assert proc.returncode == EXIT_OK, (
        f"真实 bench/results.csv 被判违规：\n{proc.stderr}"
    )


# ---------------------------------------------------------------------------
# G2 · 表头违规必须逐条抓到（4 种坏法各造一份）
# ---------------------------------------------------------------------------

def test_g2_header_violations_caught(tmp_path: Path) -> None:
    cols = HEADER.split(",")

    swapped = list(cols)
    i, j = swapped.index("g1"), swapped.index("g2")
    swapped[i], swapped[j] = swapped[j], swapped[i]

    renamed = list(cols)
    renamed[0] = "Task_id"

    bad_headers = {
        "① 删掉最后一列 note": cols[:-1],
        "② 末尾多一列 extra": cols + ["extra"],
        "③ g1 与 g2 换序": swapped,
        "④ task_id 改成 Task_id": renamed,
    }

    for label, header in bad_headers.items():
        path = tmp_path / f"bad-{cols.index('note')}-{len(header)}-{header[0]}.csv"
        _write_csv(path, header, [_row()])
        proc = _run("--results", str(path))
        assert proc.returncode == EXIT_VIOLATION, (
            f"{label} 没有被抓到（退出码 {proc.returncode}）\nstderr={proc.stderr}"
        )

    # 反向对照：把 4 份坏表头改回正确表头，同一批断言下必须全部放行
    # （否则上面的 40 可能是"什么都判 40"）
    good = tmp_path / "good.csv"
    _write_csv(good, cols, [_row()])
    assert _run("--results", str(good)).returncode == EXIT_OK


# ---------------------------------------------------------------------------
# G3 · status 取值域 = 七态
# ---------------------------------------------------------------------------

def test_g3_bad_status_caught(tmp_path: Path) -> None:
    # ① `passed` 不在七态里（这是最容易写错的一个：英文过去式很像状态名）
    bad = tmp_path / "bad-status.csv"
    _write_csv(bad, HEADER, [_row(status="passed")])
    proc = _run("--results", str(bad))
    assert proc.returncode == EXIT_VIOLATION, (
        f"status=passed 没被抓到（退出码 {proc.returncode}）"
    )
    assert "passed" in proc.stderr, f"stderr 没点名违规取值：\n{proc.stderr}"

    # ② 七态各写一行，全部合法 → 放行（分母 7 与 judge.STATES 同源，不手数）
    seven = tmp_path / "seven.csv"
    _write_csv(seven, HEADER, [_row(task_id=f"T{i:02d}", status=s) for i, s in enumerate(STATES)])
    proc = _run("--results", str(seven))
    assert proc.returncode == EXIT_OK, (
        f"七态全写一遍仍被拒：\n{proc.stderr}"
    )


# ---------------------------------------------------------------------------
# G4 · case.meta 六键：齐则放行，逐个缺键则逐次抓
# ---------------------------------------------------------------------------

def test_g4_case_meta_six_keys(tmp_path: Path) -> None:
    ok = tmp_path / "ok.json"
    _write_meta(ok, _meta())
    proc = _run("--case-meta", str(ok))
    assert proc.returncode == EXIT_OK, f"合法 case.meta 被拒：\n{proc.stderr}"

    for key in META_KEYS:
        meta = _meta()
        del meta[key]
        path = tmp_path / f"missing-{key}.json"
        _write_meta(path, meta)

        proc = _run("--case-meta", str(path))
        assert proc.returncode == EXIT_VIOLATION, (
            f"缺 {key} 没有被抓到（退出码 {proc.returncode}）"
        )
        assert key in proc.stderr, (
            f"缺 {key} 时 stderr 没有点名这个键：\n{proc.stderr}"
        )


# ---------------------------------------------------------------------------
# G5 · case.meta 类型：schema_version 必须是 int（不是 "1"）、列表不许空
# ---------------------------------------------------------------------------

def test_g5_case_meta_types(tmp_path: Path) -> None:
    cases = {
        'schema_version="1"（str 不是 int）': _meta(schema_version="1"),
        "allowed_files=[]（空列表）": _meta(allowed_files=[]),
        "spec=[]（不是 dict）": _meta(spec=[]),
        'derived_at="昨天"（不可解析）': _meta(derived_at="昨天"),
    }

    for label, meta in cases.items():
        path = tmp_path / f"bad-{abs(hash(label))}.json"
        _write_meta(path, meta)
        proc = _run("--case-meta", str(path))
        assert proc.returncode == EXIT_VIOLATION, (
            f"{label} 没有被抓到（退出码 {proc.returncode}）\nstderr={proc.stderr}"
        )


# ---------------------------------------------------------------------------
# G6 · 真实 new_case.sh 产出的 case.meta 必须放行（把 G 与 C 钉在一起）
# ---------------------------------------------------------------------------

def test_g6_real_new_case_output_passes(tmp_path: Path) -> None:
    # 伪 tutorial 树：new_case.sh 要求 source 在 $FOAM_TUTORIALS 下且含 system/controlDict
    tut = tmp_path / "tutorials"
    case_src = tut / "incompressibleFluid" / "cavity"
    (case_src / "system").mkdir(parents=True)
    (case_src / "system" / "controlDict").write_text(
        "FoamFile { version 2.0; }\n", encoding="utf-8"
    )
    (case_src / "0").mkdir()
    (case_src / "0" / "U").write_text("FoamFile { version 2.0; }\n", encoding="utf-8")

    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "geometry": "二维方腔",
                "properties": "水",
                "boundary": "顶盖 1 m/s",
                "objective": "steady",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    dest = tmp_path / "case"
    env = {
        **os.environ,
        "FOAM_TUTORIALS": str(tut),
        "PYTHON": sys.executable,  # new_case.sh 内部用 python3 写 meta，钉死解释器
    }
    subprocess.run(
        [
            "bash",
            "scripts/new_case.sh",
            "--source",
            "incompressibleFluid/cavity",
            "--dest",
            str(dest),
            "--spec",
            str(spec),
        ],
        check=True,
        env=env,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    meta_path = dest / "case.meta"
    assert meta_path.is_file(), f"new_case.sh 没有在 dest 里写 case.meta：{sorted(p.name for p in dest.iterdir())}"

    proc = _run("--case-meta", str(meta_path), "--tutorials", str(tut))
    assert proc.returncode == EXIT_OK, (
        f"new_case.sh 真实产出的 case.meta 被 G 判违规（G 与 C 的契约不一致）：\n"
        f"{proc.stderr}\nmeta={meta_path.read_text(encoding='utf-8')}"
    )

    # 反向对照：把 --tutorials 指到一棵不含该 source 的树 → 必须变 40。
    # 没有这条，`--tutorials` 可能被实现成"永远跳过"，G6 就只测了一半。
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    proc = _run("--case-meta", str(meta_path), "--tutorials", str(elsewhere))
    assert proc.returncode == EXIT_VIOLATION, (
        f"source 指向不存在的 tutorial 目录没有被抓到（退出码 {proc.returncode}）"
    )
