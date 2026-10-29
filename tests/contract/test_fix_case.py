"""模块 F（scripts/fix_case.py）的 L2 契约测试，7 项。

对应 references/09-architecture-and-test-plan.md §F 与 §F 测试表（F1–F7）：

  F1 定位（可定位类）    关键字 undefined 的真实 FATAL → changes[0]={system/fvSolution, PIMPLE}
                        declined=false、written=false、new_value=null
  F2 定位（结构类）      Cannot find patchField entry for movingWall → declined、changes=[]、
                        reason 提到 movingWall（D24：{file,entry,new_value} 表达不了结构修复）
  F3 定位（不可定位）    solvers table is empty → declined、changes=[]、reason 非空，
                        且**不含任何猜测的文件名**（D23：不许猜；这里只判 controlDict 不在 reason 里）
  F4 apply 标量 + 备份    controlDict.endTime → 0.02：written=true、回读 0.02、
                        attempt_1/system/controlDict == 改前快照
  F5 entry 必须唯一命中   指向不存在的 entry → 退 33、written=false、字典 sha256 前后相同
  F6 轮数上限            --attempt 4 --max-attempts 3 → 退 31、changes=[]、无 attempt_4/
  F7 指纹去重            同一 FATAL attempt 1 后 attempt 2 → 退 32、无 attempt_2/（D25）

设计约定：
- case 一律从 cavity 用 `cp -a` 派生到 tmp_path，绝不写 bench/（R12）。
- **不跑 blockMesh**：F 不重跑求解、不做网格判断，字典文本才是被测对象；少跑一条 OpenFOAM
  命令既快又不引入与判据无关的失败源。
- 断言只用「可判定」的事实：退出码、JSON 字段、目录是否存在、sha256、`foamDictionary -value`
  的回读值。不写「看起来对」。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 环境引导（bashrc → env）、cavity 派生源与五个根统一由 `tests/contract/conftest.py`
# 提供：本文件只声明 `foam_env` / `cavity_src` / `roots` 夹具，不再自己 source 一遍。

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "fix_case.py"

CAVITY_REL = "incompressibleFluid/cavity"


# ---------------------------------------------------------------- 基础设施


def make_case(tmp_path: Path, env: dict) -> Path:
    """把 cavity 整树 `cp -a` 到 <tmp>/run/case，返回 case 目录。

    放在 <tmp>/run/ 之下是刻意的：run/ 就是「case 的父目录」，备份与指纹都落在这里
    （<run>/attempt_<n>/），与真实流水线一致。
    """
    src = Path(env["FOAM_TUTORIALS"]) / CAVITY_REL
    assert src.is_dir(), f"cavity 教程不存在: {src}"
    case = tmp_path / "run" / "case"
    case.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, case, symlinks=True)
    return case


def run_fix(env: dict, *args: str) -> subprocess.CompletedProcess:
    """用解释器调脚本（行为测试；可执行位由 tests/unit/test_script_entrypoints.py 管）。"""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def out_json(proc: subprocess.CompletedProcess) -> dict:
    """stdout 必须正好一行 JSON —— 多行/空行/前后缀都算违约，直接炸。"""
    lines = proc.stdout.splitlines()
    assert len(lines) == 1, f"stdout 必须正好 1 行 JSON，实际 {len(lines)} 行: {proc.stdout!r}"
    return json.loads(lines[0])


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fatal(tmp_path: Path, body: str, name: str = "log.run") -> Path:
    log = tmp_path / name
    log.write_text(body, encoding="utf-8")
    return log


def dict_value(env: dict, file: Path, entry: str) -> str:
    """独立回读：直接问 foamDictionary，不信脚本自报。"""
    proc = subprocess.run(
        ["foamDictionary", str(file), "-entry", entry, "-value"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, f"foamDictionary -value 失败 rc={proc.returncode}: {proc.stderr[:300]!r}"
    return proc.stdout.strip()


KEYWORD_FATAL = """--> FOAM FATAL IO ERROR: 
keyword PIMPLE is undefined in dictionary "{case}/system/fvSolution"

file: {case}/system/fvSolution at line 17.
"""

PATCHFIELD_FATAL = """--> FOAM FATAL IO ERROR: 
Cannot find patchField entry for movingWall

file: {case}/0/U/boundaryField from line 20 to 35.
"""

EMPTY_SOLVERS_FATAL = """--> FOAM FATAL ERROR: 
solvers table is empty
"""


# ---------------------------------------------------------------- F1 定位


def test_f1_locate_keyword_undefined(tmp_path: Path, foam_env: dict):
    """可定位类：给出 file+entry，但**不给 new_value**（那是模型层的职责）。"""
    case = make_case(tmp_path, foam_env)
    log = write_fatal(tmp_path, KEYWORD_FATAL.format(case=case))

    proc = run_fix(foam_env, "--case", str(case), "--error-log", str(log), "--attempt", "1")

    assert proc.returncode == 0, f"定位成功应退 0，实际 {proc.returncode}: {proc.stderr[:400]!r}"
    payload = out_json(proc)
    assert payload["declined"] is False, f"这条 FATAL 能定位，不该 declined: {payload}"
    assert payload["changes"] == [
        {"file": "system/fvSolution", "entry": "PIMPLE", "new_value": None}
    ], payload["changes"]
    assert payload["written"] is False, "locate 模式不写盘"
    assert payload["backup_dir"] is None
    assert payload["reason"] is None
    assert re.fullmatch(r"[0-9a-f]{16}", payload["fingerprint"] or ""), payload["fingerprint"]


# ---------------------------------------------------------------- F2 结构类


def test_f2_locate_structural_declines(tmp_path: Path, foam_env: dict):
    """结构修复（缺 patchField 条目）→ declined，且 reason 必须指名 patch（D24）。"""
    case = make_case(tmp_path, foam_env)
    log = write_fatal(tmp_path, PATCHFIELD_FATAL.format(case=case))

    proc = run_fix(foam_env, "--case", str(case), "--error-log", str(log), "--attempt", "1")

    assert proc.returncode == 0, f"declined 属于正常结果（退 0），实际 {proc.returncode}"
    payload = out_json(proc)
    assert payload["declined"] is True
    assert payload["changes"] == []
    assert payload["written"] is False
    assert payload["backup_dir"] is None
    assert "movingWall" in (payload["reason"] or ""), payload["reason"]


# ---------------------------------------------------------------- F3 不猜


def test_f3_unlocatable_declines_not_guesses(tmp_path: Path, foam_env: dict):
    """定位不到 → declined，且 reason 里**不得出现猜测的文件名**（D23）。"""
    case = make_case(tmp_path, foam_env)
    log = write_fatal(tmp_path, EMPTY_SOLVERS_FATAL)

    proc = run_fix(foam_env, "--case", str(case), "--error-log", str(log), "--attempt", "1")

    assert proc.returncode == 0, f"declined 属于正常结果（退 0），实际 {proc.returncode}"
    payload = out_json(proc)
    assert payload["declined"] is True
    assert payload["changes"] == []
    assert payload["written"] is False
    assert payload["reason"], "declined 必须给非空 reason"
    # 关键：不许默认回退到 controlDict —— 那正是「猜」
    assert "controlDict" not in payload["reason"], (
        f"reason 里出现猜测的文件名 controlDict: {payload['reason']!r}"
    )
    assert "system/controlDict" not in json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------- F4 apply


def test_f4_apply_scalar_and_backup(tmp_path: Path, foam_env: dict):
    """apply 标量：written=true、回读 0.02、attempt_1 里是**改前**的字节。"""
    case = make_case(tmp_path, foam_env)
    control = case / "system" / "controlDict"
    before = control.read_bytes()
    assert dict_value(foam_env, control, "endTime") == "10", "cavity 的 endTime 应为 10（前置事实）"

    changes = [{"file": "system/controlDict", "entry": "endTime", "new_value": "0.02"}]
    proc = run_fix(
        foam_env,
        "--case", str(case),
        "--apply", json.dumps(changes),
        "--attempt", "1",
    )

    assert proc.returncode == 0, f"apply 应退 0，实际 {proc.returncode}: {proc.stderr[:400]!r}"
    payload = out_json(proc)
    assert payload["written"] is True, payload
    assert payload["declined"] is False
    assert payload["reason"] is None

    backup_dir = Path(payload["backup_dir"] or "")
    assert backup_dir.is_absolute(), f"backup_dir 必须是绝对路径: {payload['backup_dir']!r}"
    assert backup_dir == case.parent / "attempt_1", backup_dir

    # 回读：不信自报，直接问字典
    assert dict_value(foam_env, control, "endTime") == "0.02"
    # 备份是**改前**内容（逐字节）
    assert (backup_dir / "system" / "controlDict").read_bytes() == before
    # 且当前文件确实变了（否则「回读 0.02」可能是巧合）
    assert control.read_bytes() != before


# ---------------------------------------------------------------- F5 唯一命中


def test_f5_entry_must_hit_exactly_once(tmp_path: Path, foam_env: dict):
    """entry 不存在 → 退 33，字典**一个字节都不变**。

    为什么不能信 foamDictionary 的退出码（2026-10-28 实测，cavity 的 controlDict）:

        $ foamDictionary $T/system/controlDict -entry noSuchKey9 -set 1; echo "rc=$?"
        New entry noSuchKey9      1;

        rc=0
        $ grep -c noSuchKey9 $T/system/controlDict
        1
        $ sha256sum $T/system/controlDict   # 改前 b90f414c7b665ae8... → 改后 b3d9c2d7a623b29f...

    `-set` 对不存在的 entry **不是报错，而是新增一个 entry 并退 0**。所以「退 0」在这里
    根本不能当"改对了"的证据：一个拼错的 entry 会被静默写进去，求解器随后照样 FATAL。
    必须在写之前自己数一遍：恰好 1 次才写，0 次或 >=2 次一律 33。
    """
    case = make_case(tmp_path, foam_env)
    control = case / "system" / "controlDict"
    sha_before = sha256_of(control)

    changes = [{"file": "system/controlDict", "entry": "noSuchKey9", "new_value": "1"}]
    proc = run_fix(
        foam_env,
        "--case", str(case),
        "--apply", json.dumps(changes),
        "--attempt", "1",
    )

    assert proc.returncode == 33, f"entry 未命中必须退 33，实际 {proc.returncode}: {proc.stdout[:300]!r}"
    payload = out_json(proc)
    assert payload["written"] is False
    assert sha256_of(control) == sha_before, "拒绝时字典文件字节必须不变"
    assert "noSuchKey9" not in control.read_text(encoding="utf-8")
    # 校验先于备份：被拒绝的 apply 不该产生备份目录
    assert not (case.parent / "attempt_1").exists(), "退 33 时不应产生 attempt_1/"


# ---------------------------------------------------------------- F6 轮数上限


def test_f6_max_attempts_refuses(tmp_path: Path, foam_env: dict):
    """attempt > max-attempts → 退 31，且不许建 attempt_4/（06:149-150）。"""
    case = make_case(tmp_path, foam_env)
    log = write_fatal(tmp_path, KEYWORD_FATAL.format(case=case))

    proc = run_fix(
        foam_env,
        "--case", str(case),
        "--error-log", str(log),
        "--attempt", "4",
        "--max-attempts", "3",
    )

    assert proc.returncode == 31, f"超上限必须退 31，实际 {proc.returncode}: {proc.stdout[:300]!r}"
    payload = out_json(proc)
    assert payload["changes"] == []
    assert payload["written"] is False
    assert not (case.parent / "attempt_4").exists(), "退 31 时不许建 attempt_4/"


# ---------------------------------------------------------------- F7 指纹去重


def test_f7_fingerprint_dedup(tmp_path: Path, foam_env: dict):
    """同一 FATAL 第二次 → 退 32，且不建 attempt_2/（D25）。"""
    case = make_case(tmp_path, foam_env)
    log = write_fatal(tmp_path, KEYWORD_FATAL.format(case=case))

    first = run_fix(foam_env, "--case", str(case), "--error-log", str(log), "--attempt", "1")
    assert first.returncode == 0, f"第一次应正常定位，实际 {first.returncode}: {first.stderr[:300]!r}"
    fp_first = out_json(first)["fingerprint"]

    second = run_fix(foam_env, "--case", str(case), "--error-log", str(log), "--attempt", "2")

    assert second.returncode == 32, f"重复指纹必须退 32，实际 {second.returncode}: {second.stdout[:300]!r}"
    payload = out_json(second)
    assert payload["written"] is False
    assert payload["fingerprint"] == fp_first, "同一日志算出的指纹必须一致"
    assert not (case.parent / "attempt_2").exists(), "退 32 时不许建 attempt_2/"


# ---------------------------------------------------------------------------
# F8（验收时补，2026-10-28）：**不同错误必须给不同指纹**。
#
# 为什么必须有这一条：D25 定义指纹为 `sha256(FATAL 首行 + "\n" + "file:entry")`。
# 但 OpenFOAM 的 FATAL 首行几乎恒为 `--> FOAM FATAL ERROR:`（或 IO ERROR），
# 于是所有**定位不到**的错误（file:entry 为空）都会塌缩成同一个指纹。
# 实测：`solvers table is empty` 与 `cannot find file ".../system/fvSolution"`
# 给出同一个 `b10e79556e8a0b5d`。
#
# 后果是守卫的作用整个反过来：指纹去重本来是防「同一个错误烧 N 轮」
# （metaopenfoam 的 max_loop=20），塌缩后变成「第二个不同的错误被拒绝重试」。
#
# 判据必须证明两件事：①两个不同错误指纹不同；②同一个错误两次指纹相同
# （只证①，改成随机哈希也能过；只证②，恒定值也能过）。
# ---------------------------------------------------------------------------
def test_f8_distinct_errors_get_distinct_fingerprints(tmp_path, foam_env):
    """两个不同的、都定位不到的错误 → 指纹必须不同；同一错误重复 → 指纹必须相同。"""
    env = foam_env
    case = make_case(tmp_path, env)

    log_a = tmp_path / "a.log"
    log_a.write_text(
        "--> FOAM FATAL ERROR: \n"
        "solvers table is empty\n",
        encoding="utf-8",
    )
    log_b = tmp_path / "b.log"
    log_b.write_text(
        "--> FOAM FATAL ERROR: \n"
        f'cannot find file "{case}/system/fvSolution"\n',
        encoding="utf-8",
    )

    def run(log: Path, attempt: int) -> dict:
        proc = run_fix(env, "--case", str(case), "--error-log", str(log),
                       "--attempt", str(attempt), "--max-attempts", "9")
        assert proc.returncode == 0, f"应正常退 0（declined 是合法结论），实得 {proc.returncode}: {proc.stderr[:300]}"
        return json.loads(proc.stdout)

    a1 = run(log_a, 1)
    b1 = run(log_b, 2)

    assert a1["declined"] is True and b1["declined"] is True, "两条都应定位不到而 declined"
    assert a1["fingerprint"] != b1["fingerprint"], (
        f"两个不同的错误给了同一指纹 {a1['fingerprint']!r}。"
        f"指纹塌缩会让去重守卫把「另一个错误」当成「同一个错误」拒绝重试。"
    )

    # 反向：同一错误（词句相同、路径相同）重复出现 → 指纹必须一致，否则守卫形同虚设
    a_again = run(log_a, 3)
    assert a_again["fingerprint"] == a1["fingerprint"], (
        "同一错误两次的指纹必须相同，否则去重永远命中不了"
    )


# ---------------------------------------------------------------------------
# 回读比对的量纲归一（2026-10-29 由 batch 集成首次跑出来）
# ---------------------------------------------------------------------------

def _fix_case_module():
    """导入 fix_case.py 的纯函数。必须登记 sys.modules（同 test_batch 的理由）。"""
    import importlib.util
    name = "_fix_case_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_readback_accepts_openfoam_normalized_dimension():
    """用户写 `1e-5 [m^2/s]`、回读是 `1e-05 [ m^2 / s]` → 必须判相等。

    **这是实测抓到的真 bug**：原实现只剥「前置」量纲（`[0 0 1 0 0 0 0] 0.02`），
    而 `foamDictionary -set` 写带量纲的值时给的是**后置**形态。于是用户按最自然的写法
    就会得到 `回读不符 → 退 33 → 回滚`，且错误信息看起来像"值没改对"，实际是同一件事。
    """
    mod = _fix_case_module()
    assert mod._values_equal("1e-5 [m^2/s]", "1e-05 [ m^2 / s]")
    assert mod._values_equal("1e-06 [m^2/s]", "1e-06 [ m^2 / s]")
    assert mod._values_equal("[0 0 1 0 0 0 0] 0.02", "0.02")


def test_readback_still_catches_a_different_value():
    """归一不能把「值不同」也放过——那会把守卫变成摆设。"""
    mod = _fix_case_module()
    assert not mod._values_equal("1e-5", "2e-5")
    assert not mod._values_equal("laminar", "RAS")
    assert not mod._values_equal("(1 0 0)", "(0 0 1)")
