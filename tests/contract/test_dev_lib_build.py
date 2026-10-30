"""模块 J（`scripts/dev_lib.py`）的 L2 契约测试：**真 wmake + 真 `foamRun -libs`**。

L1（`tests/unit/test_dev_lib.py`）用假 `wmake` / 假 `foamRun` 桩判的是**脚本自己的判定逻辑**；
这里判的是**OpenFOAM 是否真的接受这份副本**，也就是 V3/V4 两道门的两条结论：

  * `wmake -j N libso` 在这个副本上真的退 0、日志 `error:` 计数 0、`.so` 真的落在 libbin；
  * `foamRun -libs '("lib<名>.so")' -help` 的输出里 `dlopen error` 计数 == 0（**不是看退出码**：
    T0 实测好库名与坏库名都退 0，见 `references/14-library-dev-flow.md` §4.4）；
  * 编译之后 `$WM_PROJECT_DIR/{src,applications}` 下没有比 `build-stamp` 新的文件（R2）；
  * 全程零写入**真实**的 `$FOAM_USER_LIBBIN` / `$WM_PROJECT_USER_DIR`。

## 隔离怎么做的（这条是最容易被写弱的）

`dev_lib.py` 的 `prepare` 要求 `dest` 在 `$WM_PROJECT_USER_DIR` 之下、`build` 把 `.so` 放到
`$FOAM_USER_LIBBIN`。所以用例必须在 `tmp_path` 下造一个**假的用户目录**，再把这两个变量覆盖掉：

```python
env["WM_PROJECT_USER_DIR"] = <tmp>/user
env["FOAM_USER_LIBBIN"]    = <tmp>/user/platforms/<WM_OPTIONS>/lib
env["LD_LIBRARY_PATH"]     = <tmp>/user/platforms/<WM_OPTIONS>/lib:<原值>
```

第三行不是多余的动作：`/opt/openfoam13/etc/bashrc` 在 **source 时**就把 `LD_LIBRARY_PATH`
定下来了（实测：source 前 `export FOAM_USER_LIBBIN=…` 会被 bashrc 覆盖回真实路径），
所以覆盖 `FOAM_USER_LIBBIN` 之后临时 libbin **不会**自动进 `LD_LIBRARY_PATH`。实测不加这一行，
`verify` 必退 88，逐字 `dlopen error : lib…so: cannot open shared object file`——
这正是 §4.4 的结论「`.so` 必须在 `LD_LIBRARY_PATH` 上」。

## 变异 1 的样本为什么不是计划里写的 `finiteVolume/lnInclude`

计划 T7.2 的原文是「把 `-I$(LIB_SRC)/finiteVolume/lnInclude` 改成 `-I$(LIB_SRC)/nope`，
`build` 必须退 87」。**2026-10-31 实测这条改法退 0**（rc=0，产出的 `.so` sha256 与未改前
逐字节相同 `da4a8031…`）：这个库只 `#include "meshTools.H"` / `polyPatch.H` /
`indirectPrimitivePatch.H`，`finiteVolume/lnInclude` 里的头一个都没被用到，而 gcc 对不存在的
`-I` 只发 warning。**一个不会让 build 变红的变异证明不了 V3 会红**，所以这里改落在真正被使用的那条上：

    副本 Make/options:3  `-I$(LIB_SRC)/meshTools/lnInclude`  →  `-I$(LIB_SRC)/nope`
    → 实测 `build` 退 87，`log.wmake` 里
      `pairPatchAgglomeration.C:27:10: error: … meshTools.H: No such file or directory`

形状与计划一致（坏一条 `-I`），只是选了一条**承重**的。

## 成本

派生源是 `$WM_PROJECT_DIR/src/fvAgglomerationMethods/pairPatchAgglomeration`（1 个 `.C`）：
T0 实测 `wmake -j 4 libso` 4 s，本文件实测墙钟见 `tests/contract/README.md`。不用
`populationBalance`（47 个 `.C`、61 s）当样本——契约层每次都要跑。

环境依赖：OpenFOAM v13（`foam_env` 夹具来自 `tests/contract/conftest.py`，缺环境 skip，
skip ≠ pass）。本文件**不**自己 source bashrc，也不另写一份 `_foam_env`。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "dev_lib.py"

#: 用**跑 pytest 的那个解释器**，不写死路径（PATH 上的 python3 指向谁不稳定）。
PY = sys.executable

#: 派生源（相对 `$WM_PROJECT_DIR`）：最小的带 `Make/files` 的子库 —— 1 个 `.C`、1 个 `LIB` 行。
SYSTEM_LIB_REL = Path("src") / "fvAgglomerationMethods" / "pairPatchAgglomeration"

#: `wmake -j N` 的 N：R7「本机内存有限，N ≤ 2 起步」。
JOBS = 2

BUILD_TIMEOUT = 900      # 实测 3 s；给足余量，超时是「机器坏了」而不是「库太大」
LOAD_TIMEOUT = 300       # `foamRun -help` 实测 < 1 s


# --------------------------------------------------------------------- 基础设施


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(path: Path) -> dict[str, str]:
    """`ls -A` 的可判定版本：条目名 → `"<dir>"` 或字节数（排序保证逐项可比）。

    为什么不用「文件数 == 0」：那样只能证明「现在没有文件」，证明不了「**开工前后是同一批文件**」。
    真用户库若本来就非空（本机实测是空的，但那不是判据），数数会把「少了一个旧文件」判绿。
    """
    if not path.is_dir():
        return {"<目录不存在>": ""}
    out: dict[str, str] = {}
    for entry in sorted(path.iterdir()):
        out[entry.name] = "<dir>" if entry.is_dir() else str(entry.stat().st_size)
    return out


def snapshot_diff(before: dict[str, str], after: dict[str, str]) -> str:
    keys = sorted(set(before) | set(after))
    lines = [f"  {k!r}: 开工前={before.get(k, '<缺>')!r} 开工后={after.get(k, '<缺>')!r}"
             for k in keys if before.get(k) != after.get(k)]
    return "\n".join(lines) if lines else "（无差异）"


@dataclass(frozen=True)
class Sandbox:
    """`tmp_path` 下的**假用户目录**：`WM_PROJECT_USER_DIR` + `FOAM_USER_LIBBIN` 都指到这里。"""

    root: Path
    user: Path
    libbin: Path
    env: dict[str, str]

    def dest(self, name: str) -> Path:
        return self.user / "src" / name


def explain(step: dict) -> str:
    """失败信息：命令 + rc + payload（含 `reason`）+ stderr 尾部。**不**只贴断言表达式。"""
    payload = json.dumps(step["payload"], ensure_ascii=False, sort_keys=True)
    return (f"cmd = {' '.join(step['cmd'])}\n"
            f"rc  = {step['rc']}\n"
            f"payload = {payload[:3000]}\n"
            f"stderr = {step['stderr'][:1500]}")


def run_stage(sandbox: Sandbox, stage: str, *args: object, timeout: int = BUILD_TIMEOUT) -> dict:
    """跑一个 stage，返回 `{rc, payload, cmd, stdout, stderr}`。**不在**这里断言（判据留在用例里）。"""
    cmd = [PY, str(SCRIPT), "--stage", stage, *(str(a) for a in args)]
    proc = subprocess.run(cmd, env=sandbox.env, capture_output=True, text=True, timeout=timeout)
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return {"rc": proc.returncode, "payload": payload, "cmd": cmd,
            "stdout": proc.stdout, "stderr": proc.stderr}


def prepare_copy(sandbox: Sandbox, name: str) -> tuple[Path, dict]:
    """派生一份副本。返回 `(dest, step)`；失败就是整个用例的错，不是被测判据。"""
    dest = sandbox.dest(name)
    step = run_stage(sandbox, "prepare",
                     "--source", Path(sandbox.env["WM_PROJECT_DIR"]) / SYSTEM_LIB_REL,
                     "--dest", dest, "--lib", name)
    assert step["rc"] == 0, "prepare 就失败了，后面的判据无从谈起：\n" + explain(step)
    return dest, step


# --------------------------------------------------------------------- 夹具


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory, foam_env: dict) -> Sandbox:
    """把两个「用户目录」变量都指向 `tmp_path` 下的临时树。

    `foam_env` 是 session 级共享 dict —— **必须拷贝**（conftest 的规矩），否则本文件把
    `FOAM_USER_LIBBIN` 改到临时目录这件事会污染同一次会话里的其它 L2 文件，
    且失败现象会指向那些文件。
    """
    for tool in ("wmake", "foamRun"):
        if shutil.which(tool, path=foam_env.get("PATH")) is None:
            pytest.skip(f"source 后 PATH 里没有 {tool}：这条契约无法判定")

    root = tmp_path_factory.mktemp("dev_lib")
    user = root / "user"
    libbin = user / "platforms" / foam_env.get("WM_OPTIONS", "unknown-platform") / "lib"
    libbin.mkdir(parents=True)

    env = dict(foam_env)
    env["WM_PROJECT_USER_DIR"] = str(user)
    env["FOAM_USER_LIBBIN"] = str(libbin)
    # bashrc 在 source 时就把 LD_LIBRARY_PATH 定死了，覆盖 FOAM_USER_LIBBIN 不会带着它走（见模块 docstring）。
    parts = [str(libbin)] + [p for p in env.get("LD_LIBRARY_PATH", "").split(":") if p]
    env["LD_LIBRARY_PATH"] = ":".join(parts)
    return Sandbox(root=root, user=user, libbin=libbin, env=env)


@pytest.fixture(scope="module")
def real_dirs_before(foam_env: dict) -> dict:
    """**任何编译发生之前**的真用户目录快照（`built` 依赖它，靠夹具依赖拿到时序保证）。"""
    libbin = Path(foam_env["FOAM_USER_LIBBIN"])
    user = Path(foam_env["WM_PROJECT_USER_DIR"])
    return {"libbin": libbin, "user": user,
            "libbin_snapshot": snapshot(libbin), "user_snapshot": snapshot(user)}


@pytest.fixture(scope="module")
def built(sandbox: Sandbox, real_dirs_before: dict) -> tuple[Path, dict]:
    """真链一次：prepare → check → build（真 wmake）→ verify（真 foamRun）。

    返回 `(dest, {stage: step})`，**不在这里断言** —— 「四步 rc 全 0」这条判据属于
    `test_real_build_and_load`，挪进夹具会让「哪一步红了」变成一个 fixture error。
    依赖 `real_dirs_before` 是为了保证快照取在任何写入之前。
    """
    dest, prep = prepare_copy(sandbox, "ppaReal")
    steps = {
        "prepare": prep,
        "check": run_stage(sandbox, "check", "--dest", dest),
        "build": run_stage(sandbox, "build", "--dest", dest, "--jobs", JOBS),
        "verify": run_stage(sandbox, "verify", "--dest", dest, timeout=LOAD_TIMEOUT),
    }
    return dest, steps


# --------------------------------------------------------------------- 契约


def test_real_build_and_load(foam_env: dict, sandbox: Sandbox, built: tuple[Path, dict]):
    """四步全 0；`.so` 真的落在临时 libbin；sha256 非空且与盘上一致；`dlopen error` = 0。"""
    dest, steps = built
    assert steps["prepare"]["rc"] == 0, "prepare 应当退 0：\n" + explain(steps["prepare"])
    assert steps["check"]["rc"] == 0, "check 应当干净（副本刚派生、还没改任何文件）：\n" + explain(steps["check"])
    assert steps["build"]["rc"] == 0, "build 应当退 0：\n" + explain(steps["build"])
    assert steps["verify"]["rc"] == 0, "verify 应当退 0：\n" + explain(steps["verify"])

    build, verify = steps["build"]["payload"], steps["verify"]["payload"]
    assert build["wmake_cmd"] == ["wmake", "-j", str(JOBS), "libso"], (
        "wmake 的选项必须在 target 之前（T0 实测 `wmake libso -j 4` 退 1）")
    assert build["wmake_rc"] == 0
    assert build["error_first"] is None, build["error_first"]

    so = sandbox.libbin / "libppaReal.so"
    assert so.is_file(), f"{so} 不存在：build 说成功但产物不在被覆盖的 FOAM_USER_LIBBIN 里"
    assert Path(build["so_path"]) == so
    assert build["so_sha256"], "build.json 的 so_sha256 不能为空（它是 verify 比对产物的唯一依据）"
    assert build["so_sha256"] == sha256_file(so), "build.json 的 so_sha256 与盘上的 .so 不一致"
    assert build["so_size"] == so.stat().st_size > 0

    assert verify["so_sha256_ok"] is True
    assert verify["dlopen_error"] == 0, (
        "加载证明失败：输出里出现 dlopen error（判据只看这个计数，不看 foamRun 的退出码）")
    assert verify["load_cmd"] == ["foamRun", "-libs", '("libppaReal.so")', "-help"], (
        "命令形态必须照抄 T0 定稿：`-libs` 后面是带引号的 `(\"…so\")`")
    assert verify["system_tree_newer"] == []

    # dev.meta 是 prepare 的产物，也是后面两条变异用例的输入 —— 顺手钉住它记的库名
    meta = json.loads((dest / "dev.meta").read_text(encoding="utf-8"))
    assert meta["lib_name"] == "ppaReal"
    assert meta["system_source"].endswith("pairPatchAgglomeration")


def test_system_tree_untouched(foam_env: dict, built: tuple[Path, dict]):
    """R2：真编译之后，系统树里比 `build-stamp` 新的文件数必须是 0（用 find 独立算一遍）。"""
    _, steps = built
    assert steps["build"]["rc"] == 0, "build 没成功，这条判定没有意义：\n" + explain(steps["build"])

    project = Path(foam_env["WM_PROJECT_DIR"])
    stamp = project / "build-stamp"
    if not stamp.is_file():
        pytest.skip(f"{stamp} 不存在：没有基线就不能说「没被改过」（返回空列表会把这道门变成恒绿）")

    proc = subprocess.run(
        ["find", str(project / "src"), str(project / "applications"),
         "-newer", str(stamp), "-type", "f"],
        capture_output=True, text=True, timeout=LOAD_TIMEOUT,
    )
    assert proc.returncode == 0, f"find 失败（rc={proc.returncode}）：{proc.stderr[:800]}"
    newer = [line for line in proc.stdout.splitlines() if line.strip()]
    assert newer == [], (
        f"编译之后 $WM_PROJECT_DIR 下有 {len(newer)} 个文件比 build-stamp 新（R2 被破）：\n"
        + "\n".join(newer[:20]))
    # 两条实现（find 与 dev_lib.py 的 system_tree_newer）必须对同一件事给出同一结论
    assert steps["verify"]["payload"]["system_tree_newer"] == []


def test_real_user_libbin_not_polluted(foam_env: dict, sandbox: Sandbox,
                                       real_dirs_before: dict, built: tuple[Path, dict]):
    """真用户库目录：开工前快照 vs 开工后快照**逐项相等**（不是「文件数为 0」）。"""
    _, steps = built
    assert steps["build"]["rc"] == 0, "build 没成功，这条判定没有意义：\n" + explain(steps["build"])

    real_libbin, real_user = real_dirs_before["libbin"], real_dirs_before["user"]
    # 先证明隔离是真的：临时 libbin 与真实 libbin 是两个目录，否则下面那条断言是空的
    assert sandbox.libbin.resolve() != real_libbin.resolve()
    assert sandbox.libbin.resolve().is_relative_to(sandbox.root.resolve())
    assert (sandbox.libbin / "libppaReal.so").is_file(), "临时 libbin 里没有产物：覆盖根本没生效"

    now_libbin, now_user = snapshot(real_libbin), snapshot(real_user)
    assert now_libbin == real_dirs_before["libbin_snapshot"], (
        f"真实 $FOAM_USER_LIBBIN（{real_libbin}）在编译前后不一致：\n"
        f"{snapshot_diff(real_dirs_before['libbin_snapshot'], now_libbin)}")
    assert now_user == real_dirs_before["user_snapshot"], (
        f"真实 $WM_PROJECT_USER_DIR（{real_user}）在编译前后不一致：\n"
        f"{snapshot_diff(real_dirs_before['user_snapshot'], now_user)}")


def test_build_fails_on_broken_include(foam_env: dict, sandbox: Sandbox):
    """变异自证 1：坏一条**承重**的 `-I` → `build` 必须退 87（证明 V3 不是恒绿）。

    样本为什么是 `meshTools/lnInclude` 而不是计划写的 `finiteVolume/lnInclude`，见模块 docstring
    （后者实测改坏之后 build 仍退 0 —— 那个头目录这份库根本没用到）。
    """
    dest, _prep = prepare_copy(sandbox, "ppaBrokenInclude")
    options = dest / "Make" / "options"
    text = options.read_text(encoding="utf-8")
    needle = "-I$(LIB_SRC)/meshTools/lnInclude"
    assert text.count(needle) == 1, f"副本的 Make/options 里应恰有 1 条 {needle}：\n{text}"
    options.write_text(text.replace(needle, "-I$(LIB_SRC)/nope"), encoding="utf-8")

    step = run_stage(sandbox, "build", "--dest", dest, "--jobs", JOBS)

    assert step["rc"] == 87, ("坏掉的 -I 必须让 build 退 87（`_E` 里 87 = 构建失败），"
                              "退 0 说明 V3 判据没在测任何东西：\n" + explain(step))
    payload = step["payload"]
    assert payload.get("ok") is False
    assert payload.get("wmake_rc") not in (0, None), f"wmake 应当非 0：{payload.get('wmake_rc')}"
    assert payload.get("error_count", 0) >= 1, "日志里没有 error: 行，那 rc 非 0 就无从解释"
    first = payload.get("error_first") or {}
    assert "No such file" in (first.get("msg") or ""), f"第一条错误不像缺头文件：{first}"
    assert not (sandbox.libbin / "libppaBrokenInclude.so").exists(), (
        "构建失败了却留下了 .so：产物检查形同虚设（旧产物会让下一次 verify 假绿）")


def test_verify_fails_when_so_renamed(foam_env: dict, sandbox: Sandbox):
    """变异自证 2：真编译成功后把 `.so` 改名 → `verify` 必须退 88。"""
    dest, _prep = prepare_copy(sandbox, "ppaRenamedSo")
    build = run_stage(sandbox, "build", "--dest", dest, "--jobs", JOBS)
    assert build["rc"] == 0, "前置的 build 没成功：\n" + explain(build)

    so = sandbox.libbin / "libppaRenamedSo.so"
    assert so.is_file(), "build 说成功但 .so 不在临时 libbin 里"
    moved = so.with_name(so.name + ".renamed")
    so.rename(moved)
    try:
        step = run_stage(sandbox, "verify", "--dest", dest, timeout=LOAD_TIMEOUT)
    finally:
        moved.rename(so)          # 复原：让这个目录继续是一个「能过 verify」的副本

    assert step["rc"] == 88, ("产物被挪走后 verify 必须退 88（`_E` 里 88 = 加载证明失败），"
                              "退 0 说明它没在核对产物：\n" + explain(step))
    assert step["payload"].get("so_sha256_ok") is False
    assert "产物与 build.json 不符" in (step["payload"].get("reason") or "")
    assert not (dest / "verify.json").exists(), (
        "失败的 verify 不该写出 verify.json：下游会把上一次的成功结果当成这一次的")


def test_verify_rejects_undlopenable_so(foam_env: dict, sandbox: Sandbox):
    """sha256 对得上、但 `.so` 打不开 → `verify` 必须退 88。

    这条是**「只看 `dlopen error` 计数」这条判据唯一的变异捕手**：把 `.so` 换成非 ELF 的垃圾字节，
    同时把 `build.json` 的 `so_sha256`/`so_size` 改成与它一致（于是 sha 那道门是绿的），
    实测 `foamRun -help` 仍然 **rc=0**，只在输出里留一行
    `dlopen error : …/lib….so: file too short`。判据一旦改成看 rc，这个用例立刻退 0；
    见 `tests/contract/README.md` 的 J-M1。
    """
    dest, _prep = prepare_copy(sandbox, "ppaBadSo")
    build = run_stage(sandbox, "build", "--dest", dest, "--jobs", JOBS)
    assert build["rc"] == 0, "前置的 build 没成功：\n" + explain(build)

    so = sandbox.libbin / "libppaBadSo.so"
    assert so.is_file(), "build 说成功但 .so 不在临时 libbin 里"
    garbage = b"not an elf\n"
    so.write_bytes(garbage)
    record = json.loads((dest / "build.json").read_text(encoding="utf-8"))
    record["so_sha256"] = hashlib.sha256(garbage).hexdigest()
    record["so_size"] = len(garbage)
    (dest / "build.json").write_text(json.dumps(record), encoding="utf-8")

    step = run_stage(sandbox, "verify", "--dest", dest, timeout=LOAD_TIMEOUT)

    assert step["rc"] == 88, (
        "sha 对得上但打不开的 .so 必须让 verify 退 88；退 0 说明加载判据没在测任何东西"
        "（`foamRun -help` 对坏库也退 0，判 rc 会假绿）：\n" + explain(step))
    assert step["payload"].get("dlopen_error", 0) >= 1, "输出里应当出现 dlopen error"
    assert "dlopen error" in (step["payload"].get("reason") or ""), step["payload"].get("reason")
    assert not (dest / "verify.json").exists()


def test_second_build_is_incremental(foam_env: dict, sandbox: Sandbox, built: tuple[Path, dict]):
    """同一副本第二次 `build` 也必须退 0（`wmake` 本就会增量，这条证明我们的封装不会因此出错）。

    **不断言墙钟**：耗时取决于机器与是否真的重链，断言它等于把测试绑在速度上。
    """
    dest, steps = built
    assert steps["build"]["rc"] == 0, "第一次 build 就没成功：\n" + explain(steps["build"])

    step = run_stage(sandbox, "build", "--dest", dest, "--jobs", JOBS)

    assert step["rc"] == 0, "第二次 build 应当仍然退 0：\n" + explain(step)
    payload = step["payload"]
    assert payload["wmake_rc"] == 0
    assert payload["error_first"] is None, payload["error_first"]
    assert payload["wmake_cmd"] == ["wmake", "-j", str(JOBS), "libso"]

    so = sandbox.libbin / "libppaReal.so"
    assert so.is_file(), "第二次 build 之后 .so 不见了"
    # build.json 必须跟着这一次的产物重写（verify 用它比对 sha256，写不进去就是假绿）
    written = json.loads((dest / "build.json").read_text(encoding="utf-8"))
    assert written["so_sha256"] == sha256_file(so) == payload["so_sha256"]
