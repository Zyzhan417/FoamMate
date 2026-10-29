"""模块 C（`scripts/new_case.sh`）的 L1 测试，共 7 项。

规格来源（逐字，勿改写）：
  - `references/09-architecture-and-test-plan.md:143-158`（C 的输入/输出/三条 source 校验/六键/失败语义）
  - `references/09-architecture-and-test-plan.md:350-356`（C1…C7 判据原文）
  - `references/09-architecture-and-test-plan.md:28`（D11：用 `cp -a`，不用 `foamCloneCase`）
  - `AGENTS.md` R3（case 必须从 tutorial 派生）、R5（前处理边界，本层不涉及）

C1…C7 的编号与规格表一一对应，测试名带 `cN_` 前缀，便于「14/7/…」这类计数被断言而不是被数出来。

本层**不需要 OpenFOAM**：所有 fixture 都是 `tmp_path` 下现造的伪 tutorial 树，
`FOAM_TUTORIALS` 通过 `env=` 指向它，脚本不 source bashrc、不跑任何 `foam*` 命令。
若哪天这里开始需要 OpenFOAM，说明 C 被做坏了（C 只做文件树复制 + 写 JSON）。

已知边界（不是通过，是覆盖缺口）：
  - 内容比较一律 `read_bytes()` 逐字节相等，**不比 mtime**——`cp -a` 会保留 mtime，
    但 mtime 相等不蕴含内容相等（同秒内改两次即失效），所以它不是判据。
  - C4 只测「同一 spec → 两个不同 dest」，**不测**「同一 dest 跑两次」：
    后者是 C6 的失败路径（退出 13），语义相反，混在一起会让两条判据互相掩盖。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "new_case.sh"

# 伪 tutorial：v13 主线最小 case 形状（system/controlDict 是 source 校验第 ③ 条的唯一依据）
BASE_FILES = {
    "system/controlDict": "FoamFile { version 2.0; }\nendTime 10;\n",
    "system/fvSchemes": "FoamFile { version 2.0; }\n",
    "system/fvSolution": "FoamFile { version 2.0; }\n",
    "constant/physicalProperties": "FoamFile { version 2.0; }\n",
    "0/U": "FoamFile { version 2.0; }\n",
    "0/p": "FoamFile { version 2.0; }\n",
}

# source 的相对路径（相对 $FOAM_TUTORIALS，不带前导 /）——就是 case.meta.source 的期望值
REL = "incompressibleFluid/cavity"

# 四元组：键名是 properties 不是 material（D9）。带中文，顺带钉住「UTF-8 不转义」。
SPEC = {
    "geometry": {"shape": "cavity", "dim": "2D", "size": "1 m x 1 m"},
    "properties": {"fluid": "water", "nu": "1e-06 m2/s", "turbulence": "laminar"},
    "boundary": {"movingWall": "1 m/s", "fixedWalls": "no-slip"},
    "objective": "稳态层流，检查涡心位置",
}

META_KEYS = {
    "source",
    "derived_at",
    "spec",
    "changes",
    "allowed_files",
    "schema_version",
}
DEFAULT_ALLOWED = ["system/*", "constant/*", "0/*"]


# ---------------------------------------------------------------------------
# 辅助：造伪 tutorial 树 / 写 spec / 跑脚本
# ---------------------------------------------------------------------------
def make_tutorials(root: Path, rel: str = REL, files: dict[str, str] | None = None) -> Path:
    """在 root/tutorials/<rel> 造一棵伪 tutorial 树，返回 tutorials 根（= $FOAM_TUTORIALS）。"""
    tutorials = root / "tutorials"
    case = tutorials / rel
    for relpath, text in (BASE_FILES if files is None else files).items():
        dst = case / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")
    return tutorials


def write_spec(path: Path, spec: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(SPEC if spec is None else spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def run_new_case(
    *,
    source: Path | str,
    dest: Path | str,
    spec: Path | str,
    tutorials: Path | str | None = None,
    extra_env: dict[str, str] | None = None,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess:
    """跑 `bash scripts/new_case.sh`。环境变量显式给出，不继承调用者的 $FOAM_TUTORIALS。"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("FOAM_")}
    if tutorials is not None:
        env["FOAM_TUTORIALS"] = str(tutorials)
    if extra_env:
        env.update(extra_env)
    cmd = [
        "bash",
        str(SCRIPT),
        "--source",
        str(source),
        "--dest",
        str(dest),
        "--spec",
        str(spec),
        *extra_args,
    ]
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=env)


def tree_files(root: Path) -> set[str]:
    """root 下所有**普通文件**的相对路径（posix 形式，已排序无关）。"""
    return {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def read_meta(dest: Path) -> dict:
    meta_path = dest / "case.meta"
    assert meta_path.is_file(), f"{meta_path} 不存在：没有 case.meta 的目录不算 case（成功语义）"
    return json.loads(meta_path.read_text(encoding="utf-8"))


def fail_msg(p: subprocess.CompletedProcess) -> str:
    return f"rc={p.returncode}\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"


# ---------------------------------------------------------------------------
# C1 派生完整性
# ---------------------------------------------------------------------------
def test_c1_derive_completeness(tmp_path):
    """dest 文件集合 == source 文件集合，白名单只允许 `case.meta` 多出来；逐文件比字节，不比 mtime。"""
    tutorials = make_tutorials(tmp_path)
    src = tutorials / REL
    dest = tmp_path / "cases" / "case1"

    p = run_new_case(source=src, dest=dest, spec=write_spec(tmp_path / "spec.json"), tutorials=tutorials)
    assert p.returncode == 0, fail_msg(p)

    src_files = tree_files(src)
    dst_files = tree_files(dest)
    # 白名单只有一个额外文件；多一个日志/软链/空目录以外的产物都会在这里红
    assert dst_files - src_files == {"case.meta"}, (
        f"dest 多出的文件不止 case.meta：{sorted(dst_files - src_files)}"
    )
    assert src_files - dst_files == set(), f"漏复制的文件：{sorted(src_files - dst_files)}"
    assert src_files, "fixture 是空的，这条测试就是空跑"

    for rel in sorted(src_files):
        assert (dest / rel).read_bytes() == (src / rel).read_bytes(), f"内容不一致：{rel}"


# ---------------------------------------------------------------------------
# C2 case.meta 六键齐全
# ---------------------------------------------------------------------------
def test_c2_case_meta_six_keys(tmp_path):
    """六键齐（不多不少）；source 是相对 $FOAM_TUTORIALS 的路径且真实存在；schema_version == 1。"""
    tutorials = make_tutorials(tmp_path)
    dest = tmp_path / "case2"

    p = run_new_case(
        source=tutorials / REL, dest=dest, spec=write_spec(tmp_path / "spec.json"), tutorials=tutorials
    )
    assert p.returncode == 0, fail_msg(p)

    meta = read_meta(dest)
    assert set(meta) == META_KEYS, f"键集合不对：多 {sorted(set(meta) - META_KEYS)}，缺 {sorted(META_KEYS - set(meta))}"

    assert meta["source"] == REL, f"source 应是相对 $FOAM_TUTORIALS 的路径，实测 {meta['source']!r}"
    assert not meta["source"].startswith("/"), "source 不许带前导 /"
    assert (tutorials / meta["source"]).is_dir(), "source 指向的 tutorial 必须真实存在（R3）"

    assert meta["schema_version"] == 1
    assert isinstance(meta["schema_version"], int) and not isinstance(meta["schema_version"], bool)
    assert meta["changes"] == [], "派生时改动清单必须是空数组"
    assert meta["allowed_files"] == DEFAULT_ALLOWED, f"白名单默认值不对：{meta['allowed_files']!r}"

    # derived_at：ISO8601 且带时区（否则跨机比较 derived_at 无意义）
    derived_at = meta["derived_at"]
    assert isinstance(derived_at, str) and derived_at, f"derived_at 不是非空字符串：{derived_at!r}"
    parsed = datetime.fromisoformat(derived_at)
    assert parsed.tzinfo is not None, f"derived_at 缺时区：{derived_at!r}"

    # UTF-8 不转义：中文必须原样落盘（ensure_ascii=False）
    raw = (dest / "case.meta").read_text(encoding="utf-8")
    assert "稳态层流" in raw, "case.meta 里的中文被转义成了 \\uXXXX"
    assert "\\u7a33" not in raw, "case.meta 里的中文被转义成了 \\uXXXX"


# ---------------------------------------------------------------------------
# C3 spec 原样写入
# ---------------------------------------------------------------------------
def test_c3_spec_written_verbatim(tmp_path):
    """`case.meta.spec` 与 `--spec` 传入的 JSON 逐键相等；不许多键、不许改值。"""
    tutorials = make_tutorials(tmp_path)
    dest = tmp_path / "case3"
    spec_path = write_spec(tmp_path / "spec.json")

    p = run_new_case(source=tutorials / REL, dest=dest, spec=spec_path, tutorials=tutorials)
    assert p.returncode == 0, fail_msg(p)

    given = json.loads(spec_path.read_text(encoding="utf-8"))
    assert set(given) == {"geometry", "properties", "boundary", "objective"}, "fixture 的四元组键名不对"

    meta_spec = read_meta(dest)["spec"]
    assert meta_spec == given, f"spec 未原样写入：\n写入 {meta_spec!r}\n传入 {given!r}"
    assert set(meta_spec) == set(given), f"spec 键集合被改动：{sorted(set(meta_spec) ^ set(given))}"
    assert "material" not in meta_spec, "键名是 properties 不是 material（D9）"
    for key in given:
        assert meta_spec[key] == given[key], f"键 {key} 的值被改：{meta_spec[key]!r} != {given[key]!r}"


# ---------------------------------------------------------------------------
# C4 幂等（两个不同 dest）
# ---------------------------------------------------------------------------
def test_c4_idempotent_two_dests(tmp_path):
    """同一 spec 生成到两个**不同** dest：两树逐文件字节相等；case.meta 除 derived_at 外相等。"""
    tutorials = make_tutorials(tmp_path)
    spec_path = write_spec(tmp_path / "spec.json")
    dest_a = tmp_path / "a" / "case"
    dest_b = tmp_path / "b" / "case"

    pa = run_new_case(source=tutorials / REL, dest=dest_a, spec=spec_path, tutorials=tutorials)
    assert pa.returncode == 0, fail_msg(pa)
    pb = run_new_case(source=tutorials / REL, dest=dest_b, spec=spec_path, tutorials=tutorials)
    assert pb.returncode == 0, fail_msg(pb)

    files_a = tree_files(dest_a)
    files_b = tree_files(dest_b)
    assert files_a == files_b, f"两次派生文件集合不同：{sorted(files_a ^ files_b)}"
    # case.meta 不参与逐字节比较：它含 `derived_at`，两次运行跨秒就必然不同。
    # 这里曾放手让循环比全部文件，于是测试**在负载下随机变红**（2026-10-28 全量跑时
    # 复现：`At index 79 diff: b'8' != b'9'`，正是时间戳的秒位）。
    # 正确做法：字节比较只管冷数据，meta 由下面的 dict 比较负责（已 pop derived_at）。
    for rel in sorted(files_a - {"case.meta"}):
        assert (dest_a / rel).read_bytes() == (dest_b / rel).read_bytes(), f"两次派生内容不同：{rel}"

    meta_a = read_meta(dest_a)
    meta_b = read_meta(dest_b)
    meta_a.pop("derived_at")  # derived_at 只允许这一个键不同
    meta_b.pop("derived_at")
    assert meta_a == meta_b, "除 derived_at 外的 case.meta 必须逐键相等"


# ---------------------------------------------------------------------------
# C5 不凭空写：源不存在 → 12 且 dest 不存在
# ---------------------------------------------------------------------------
def test_c5_missing_source_no_dir(tmp_path):
    """source 不存在 → 退出 12，且 dest **不存在**（不是空目录）。

    顺带覆盖三条 source 校验的第三条：目录存在但无 `system/controlDict` → 同一退出码 12，
    dest 同样不存在。两条合并在 C5 内，不新增第 8 条测试。
    """
    tutorials = make_tutorials(tmp_path)  # $FOAM_TUTORIALS 合法，失败只可能来自 source
    missing = tutorials / "incompressibleFluid" / "noSuchCase"
    assert not missing.exists(), "fixture 造错了：这个 source 不该存在"
    dest = tmp_path / "should_not_exist"

    p = run_new_case(source=missing, dest=dest, spec=write_spec(tmp_path / "spec.json"), tutorials=tutorials)
    assert p.returncode == 12, f"source 不存在应退 12：{fail_msg(p)}"
    assert not dest.exists(), f"失败路径不许留下目录（哪怕是空目录）：{dest} 存在"

    # 同一判据的另一半：有目录、有文件，但缺 system/controlDict
    bare = make_tutorials(
        tmp_path,
        rel="incompressibleFluid/noControlDict",
        files={"system/fvSchemes": "FoamFile { version 2.0; }\n", "0/p": "FoamFile { version 2.0; }\n"},
    )
    src = bare / "incompressibleFluid" / "noControlDict"
    assert src.is_dir() and not (src / "system" / "controlDict").exists()
    dest2 = tmp_path / "should_not_exist_2"
    p2 = run_new_case(source=src, dest=dest2, spec=tmp_path / "spec.json", tutorials=bare)
    assert p2.returncode == 12, f"无 system/controlDict 应退 12：{fail_msg(p2)}"
    assert not dest2.exists(), f"失败路径不许留下目录：{dest2} 存在"


# ---------------------------------------------------------------------------
# C6 dest 已存在 → 13，且不改动它
# ---------------------------------------------------------------------------
def test_c6_dest_exists_13(tmp_path):
    """预置 dest 目录（含哨兵文件）→ 退出 13；哨兵仍在且内容未变，目录内容不被改动。"""
    tutorials = make_tutorials(tmp_path)
    dest = tmp_path / "existing_case"
    dest.mkdir()
    sentinel = dest / "SENTINEL"
    sentinel.write_text("do not touch\n", encoding="utf-8")
    before = tree_files(dest)
    before_bytes = {rel: (dest / rel).read_bytes() for rel in before}

    p = run_new_case(source=tutorials / REL, dest=dest, spec=write_spec(tmp_path / "spec.json"), tutorials=tutorials)
    assert p.returncode == 13, f"dest 已存在应退 13（不覆盖）：{fail_msg(p)}"

    assert sentinel.is_file(), "哨兵文件被删了：脚本覆盖了已存在的 dest"
    assert sentinel.read_text(encoding="utf-8") == "do not touch\n", "哨兵文件内容被改了"
    assert tree_files(dest) == before, f"已存在的 dest 被写入了新文件：{sorted(tree_files(dest) - before)}"
    for rel, raw in before_bytes.items():
        assert (dest / rel).read_bytes() == raw, f"已存在的 dest 里 {rel} 被改动"


# ---------------------------------------------------------------------------
# C7 越界源 → 12
# ---------------------------------------------------------------------------
def test_c7_source_outside_tutorials_12(tmp_path):
    """源存在但不在 `$FOAM_TUTORIALS` 下（如落在 `$FOAM_SRC`）→ 退出 12。"""
    tutorials = make_tutorials(tmp_path)  # $FOAM_TUTORIALS 合法且非空
    foam_src = tmp_path / "src"
    outside = foam_src / "someCase"
    (outside / "system").mkdir(parents=True)
    (outside / "system" / "controlDict").write_text("FoamFile { version 2.0; }\n", encoding="utf-8")
    assert (outside / "system" / "controlDict").is_file()
    dest = tmp_path / "should_not_exist"

    p = run_new_case(
        source=outside,
        dest=dest,
        spec=write_spec(tmp_path / "spec.json"),
        tutorials=tutorials,
        extra_env={"FOAM_SRC": str(foam_src)},
    )
    assert p.returncode == 12, f"越界的 source 应退 12（R3：只许从 tutorial 派生）：{fail_msg(p)}"
    assert not dest.exists(), f"失败路径不许留下目录：{dest} 存在"
