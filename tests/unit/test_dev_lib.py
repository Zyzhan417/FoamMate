"""模块 J（`scripts/dev_lib.py`）的 L1 单元测试：**零 OpenFOAM**。

## 为什么这一层能零 OpenFOAM

`prepare` / `check` 只做文件与 JSON；`build` / `verify` 只**调用** `wmake` / `foamRun`，
而这两个命令从 `PATH` 取。所以 L1 用 PATH 前置的假桩替换它们，判的是
「我们怎么调用、怎么解析结果」，不是「OpenFOAM 会不会编译」——后者是 L2（契约层）的事。

## 为什么不能「skip 掉 build / verify」

判据里的每一条（rc 非 0、日志有 `error:`、`.so` 不在位、输出有 `dlopen error`）都是**分支**，
skip 掉等于这些分支没人测，`V3`/`V4` 就退化成「跑过了就算过」。

## 不碰真环境

每条用例都用 `env=` 把 `WM_PROJECT_DIR` / `FOAM_APP` / `FOAM_SRC` / `FOAM_LIBBIN` /
`WM_PROJECT_USER_DIR` / `FOAM_USER_LIBBIN` 全部指到 `tmp_path` 下的伪树。
真 `/opt/openfoam13` 与真 `~/OpenFOAM` 一次都不读、不写（R2）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "dev_lib.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "dev"


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


# ---------------------------------------------------------------------------
# T2 · 骨架：用法错误 64、--help 0
# ---------------------------------------------------------------------------


def test_no_args_exits_64_with_stderr():
    """不给任何参数 = 用法错误，必须退 64（全仓统一），且不得往 stdout 写 JSON。

    64 而不是 argparse 默认的 2：2 在 `verify_case.sh` 里已经是 G2 门失败，
    两个语义不同的东西共用一个码会让调用方无法区分「我调错了」与「网格不过」。
    """
    p = subprocess.run([str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 64, p.stderr
    assert p.stderr.strip(), "用法错误必须写 stderr"
    assert p.stdout == "", "用法错误不得往 stdout 写 JSON"


def test_help_exits_0_and_lists_stages():
    p = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0
    for s in ("prepare", "check", "build", "verify"):
        assert s in p.stdout


# ---------------------------------------------------------------------------
# 夹具：伪系统树 + 伪用户目录
# ---------------------------------------------------------------------------


def _pseudo_tree(tmp_path: Path) -> dict[str, str]:
    """把 `fixtures/dev/sys` 复制成 `tmp_path/sys`，并返回**全程只指 tmp_path** 的 env。

    为什么要复制而不是直接用仓库里的夹具：`prepare` 会读源树、甚至（改写后）比较 sha256，
    让它读仓库里的活文件等于把「仓库内容」当被测输入的一部分；复制一份到 tmp_path 后，
    仓库夹具只作为模板，被测的永远是 tmp 里的那份。
    """
    sysdir = tmp_path / "sys"
    shutil.copytree(FIXTURES / "sys", sysdir)
    user = tmp_path / "user"
    (user / "platforms/x/lib").mkdir(parents=True)
    env = dict(os.environ)
    env.update({
        "WM_PROJECT_DIR": str(sysdir),
        "FOAM_APP": str(sysdir / "applications"),
        "FOAM_SRC": str(sysdir / "src"),
        "FOAM_LIBBIN": str(tmp_path / "syslib"),        # 冲突判据用；默认不存在
        "WM_PROJECT_USER_DIR": str(user),
        "FOAM_USER_LIBBIN": str(user / "platforms/x/lib"),
    })
    return env


def _prepare_args(env: dict[str, str], lib: str = "demoMod", extra: list[str] | None = None) -> list[str]:
    src = Path(env["FOAM_APP"]) / "modules/demo/lb"
    dest = Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod"
    args = ["--stage", "prepare", "--source", str(src), "--dest", str(dest), "--lib", lib]
    args += extra or []
    return args


def _prepared(tmp_path: Path, allowed: list[str] | None = None,
              lib: str = "demoMod") -> tuple[dict[str, str], Path]:
    """跑完 prepare 的现场：返回 (env, dest)。check/build/verify 的每条用例都从这里起步。"""
    env = _pseudo_tree(tmp_path)
    extra: list[str] = []
    for pat in allowed or []:
        extra += ["--allowed", pat]
    p = run(_prepare_args(env, lib=lib, extra=extra), env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    return env, Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod"


# ---------------------------------------------------------------------------
# T3 · prepare
# ---------------------------------------------------------------------------


def test_prepare_rewrites_lib_and_external_include(tmp_path):
    """准备阶段的四条硬事实：LIB 换用户库、外部相对 -I 变绝对、副本内相对原样、make 变量原样。"""
    env = _pseudo_tree(tmp_path)
    src = Path(env["FOAM_APP"]) / "modules/demo/lb"
    dest = Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod"

    p = run(_prepare_args(env, extra=["--allowed", "demoModel/demoModel.C"]), env=env)
    assert p.returncode == 0, p.stdout + p.stderr

    files = (dest / "Make/files").read_text()
    assert "LIB = $(FOAM_USER_LIBBIN)/libdemoMod" in files
    assert "$(FOAM_LIBBIN)/libdemo" not in files, "原 LIB 行必须被整行替换，不是追加"

    opts = (dest / "Make/options").read_text()
    # 外部相对 → 绝对（用 resolve 后的写法比较：/tmp 在部分平台上是符号链接）
    assert f"-I{(src.parent / 'phaseSystem/lnInclude').resolve()}" in opts
    assert "-Isub/lnInclude" in opts                             # 副本内相对 → 原样
    assert "-I$(LIB_SRC)/finiteVolume/lnInclude" in opts         # make 变量 → 原样
    assert "-I../phaseSystem/lnInclude" not in opts, "旧相对路径必须消失"
    assert opts.count("\\\n") == 4, "行尾续行符数量必须不变（EXE_INC 靠它连成一条）"

    meta = json.loads((dest / "dev.meta").read_text())
    # 8 键 = 计划 §8 的 7 键 + `meta_self_sha256`（封印）。
    # 第 8 个键是本轮**唯一的 prepare 增量**：`check` 要判「dev.meta 自身被改」，
    # 而 manifest 按定义不含 dev.meta（它写不进自己的哈希），不记封印就无法判定——
    # 详见 dev_lib.py 里 meta_self_sha 的注释。除这一键外 prepare 的行为与退出码未变。
    assert set(meta) == {"system_source", "lib_name", "system_lib", "created_at",
                         "allowed_files", "manifest", "symlinks", "meta_self_sha256"}
    sealed = {k: v for k, v in meta.items() if k != "meta_self_sha256"}
    assert meta["meta_self_sha256"] == hashlib.sha256(
        json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True).encode()).hexdigest()
    assert meta["system_lib"] == "$(FOAM_LIBBIN)/libdemo"
    assert meta["system_source"] == "applications/modules/demo/lb"
    assert meta["lib_name"] == "demoMod"
    assert meta["allowed_files"] == ["demoModel/demoModel.C"]
    assert re.search(r"[+-]\d{2}:\d{2}$", meta["created_at"]), meta["created_at"]
    # manifest 是**改写后**的真值，且不含 dev.meta 自己
    assert meta["manifest"]["Make/files"] == hashlib.sha256((dest / "Make/files").read_bytes()).hexdigest()
    assert meta["manifest"]["demoModel/demoModel.C"] == hashlib.sha256(b"// demo\n").hexdigest()
    assert "dev.meta" not in meta["manifest"]

    out = json.loads(p.stdout)
    assert out["ok"] is True and out["stage"] == "prepare"
    assert out["dest"] == str(dest) and out["lib"] == "demoMod"
    assert out["files"] == len(meta["manifest"])


def test_prepare_rejects_dest_outside_user_dir(tmp_path):
    env = _pseudo_tree(tmp_path)
    src = Path(env["FOAM_APP"]) / "modules/demo/lb"
    outside = tmp_path / "elsewhere/lb_mod"
    p = run(["--stage", "prepare", "--source", str(src), "--dest", str(outside), "--lib", "demoMod"], env=env)
    assert p.returncode == 85, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["ok"] is False
    assert "WM_PROJECT_USER_DIR" in payload["reason"], payload["reason"]
    assert not outside.exists(), "拒收时不得在 $WM_PROJECT_USER_DIR 之外建目录"


def test_prepare_rejects_source_outside_project_dir(tmp_path):
    env = _pseudo_tree(tmp_path)
    stray = tmp_path / "stray/lb"
    shutil.copytree(Path(env["FOAM_APP"]) / "modules/demo/lb", stray)
    dest = Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod"
    p = run(["--stage", "prepare", "--source", str(stray), "--dest", str(dest), "--lib", "demoMod"], env=env)
    assert p.returncode == 85, p.stdout + p.stderr
    assert "WM_PROJECT_DIR" in json.loads(p.stdout)["reason"]
    assert not dest.exists()


def test_prepare_rejects_lib_name_colliding_with_system_lib(tmp_path):
    env = _pseudo_tree(tmp_path)
    libbin = Path(env["FOAM_LIBBIN"])
    libbin.mkdir(parents=True)
    (libbin / "libdemoMod.so").touch()
    p = run(_prepare_args(env), env=env)
    assert p.returncode == 85, p.stdout + p.stderr
    assert "已存在" in json.loads(p.stdout)["reason"]
    assert not (Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod").exists()


def test_prepare_rejects_existing_dest(tmp_path):
    env = _pseudo_tree(tmp_path)
    dest = Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod"
    dest.mkdir(parents=True)
    (dest / "keep.txt").write_text("用户的东西\n")
    p = run(_prepare_args(env), env=env)
    assert p.returncode == 85, p.stdout + p.stderr
    assert "已存在" in json.loads(p.stdout)["reason"]
    assert (dest / "keep.txt").read_text() == "用户的东西\n", "已存在的 dest 不许被覆盖或删除"


def test_prepare_rejects_unresolved_include_and_leaves_no_partial_dest(tmp_path):
    """`-I` 解析不到 → 85，而且 dest 不许留半成品（否则下一次 prepare 会因 dest 已存在而永远 85）。"""
    env = _pseudo_tree(tmp_path)
    opts = Path(env["FOAM_APP"]) / "modules/demo/lb/Make/options"
    opts.write_text(opts.read_text().replace("LIB_LIBS", "    -I../nope/lnInclude \\\n\nLIB_LIBS"))

    p = run(_prepare_args(env), env=env)
    assert p.returncode == 85, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["unresolved"] == ["../nope/lnInclude"]
    assert not (Path(env["WM_PROJECT_USER_DIR"]) / "src/lb_mod").exists()


def test_prepare_requires_env(tmp_path):
    """环境为空 → 85 且 reason 让人知道该 source bashrc（不猜安装路径）。"""
    env = dict(os.environ)
    for k in ("WM_PROJECT_DIR", "FOAM_LIBBIN", "WM_PROJECT_USER_DIR", "FOAM_USER_LIBBIN"):
        env.pop(k, None)
    p = run(["--stage", "prepare", "--source", "x", "--dest", "y", "--lib", "z"], env=env)
    assert p.returncode == 85, p.stdout + p.stderr
    assert "bashrc" in json.loads(p.stdout)["reason"]


# ---------------------------------------------------------------------------
# T4 · check（V2 越界检查）
#
# 判据只有一条：`sha256(当前树)` 与 `dev.meta.manifest` 的差集必须被
# `allowed_files`（fnmatch，`*` 跨 `/`）全覆盖。所以这组用例是「改了什么 → 退什么码」的
# 一张真值表：声明内的改动必须绿，声明外的四种形态（改/增/删/改判据）必须 86。
# ---------------------------------------------------------------------------


def _check(env: dict[str, str], dest: Path) -> subprocess.CompletedProcess[str]:
    return run(["--stage", "check", "--dest", str(dest)], env=env)


def test_check_allows_declared_edit(tmp_path):
    env, dest = _prepared(tmp_path, allowed=["demoModel/demoModel.C"])
    target = dest / "demoModel/demoModel.C"
    target.write_text(target.read_text() + "// 声明过的文件，可以改\n")

    p = _check(env, dest)
    assert p.returncode == 0, p.stdout + p.stderr
    out = json.loads(p.stdout)
    assert out["ok"] is True and out["stage"] == "check"
    assert out["changed"] == {"modified": ["demoModel/demoModel.C"], "added": [], "deleted": []}
    assert (out["lines_added"], out["lines_removed"]) == (1, 0)


def test_check_rejects_undeclared_modification(tmp_path):
    """改了 allowed 之外的文件 → 86，**且 payload 点名那个文件**（不能只说「越界了」）。"""
    env, dest = _prepared(tmp_path, allowed=["demoModel/demoModel.C"])
    sneaky = dest / "sub/lnInclude/sub.H"
    sneaky.write_text(sneaky.read_text() + "// 没声明\n")

    p = _check(env, dest)
    assert p.returncode == 86, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["ok"] is False
    assert payload["violations"]["modified"] == ["sub/lnInclude/sub.H"]
    assert payload["violations"]["added"] == [] and payload["violations"]["deleted"] == []


def test_check_rejects_added_file(tmp_path):
    env, dest = _prepared(tmp_path, allowed=["demoModel/demoModel.C"])
    (dest / "demoModel/extra.C").write_text("// 新增但没声明\n")

    p = _check(env, dest)
    assert p.returncode == 86, p.stdout + p.stderr
    assert json.loads(p.stdout)["violations"]["added"] == ["demoModel/extra.C"]


def test_check_rejects_deleted_file(tmp_path):
    env, dest = _prepared(tmp_path, allowed=["demoModel/demoModel.C"])
    (dest / "sub/lnInclude/sub.H").unlink()

    p = _check(env, dest)
    assert p.returncode == 86, p.stdout + p.stderr
    assert json.loads(p.stdout)["violations"]["deleted"] == ["sub/lnInclude/sub.H"]


def test_check_accepts_declared_new_header(tmp_path):
    """`--allowed 'demoModel/*.H'` + 新增头文件 → 0：glob 是 fnmatch 语义，`*` 要跨 `/`。"""
    env, dest = _prepared(tmp_path, allowed=["demoModel/*.H"])
    (dest / "demoModel/newModel.H").write_text("// 新头文件，声明过\n")

    p = _check(env, dest)
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout)["changed"]["added"] == ["demoModel/newModel.H"]


def test_check_rejects_tampered_dev_meta(tmp_path):
    """改 `dev.meta` 的 allowed_files = 改判据 → 86（否则「加一个 glob」就绕过 V2）。

    写回时故意用**规范序列化**（indent=2 / sort_keys / 末尾换行，与 prepare 逐字一致），
    即最不显眼的改法；判据必须靠 `meta_self_sha256` 抓住它，不能靠「格式变了」抓。
    """
    env, dest = _prepared(tmp_path, allowed=["demoModel/demoModel.C"])
    meta = json.loads((dest / "dev.meta").read_text())
    meta["allowed_files"] = ["*"]                      # 把判据放宽到「什么都允许」
    (dest / "dev.meta").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n")

    p = _check(env, dest)
    assert p.returncode == 86, p.stdout + p.stderr
    reason = json.loads(p.stdout)["reason"]
    assert "dev.meta" in reason and "meta_self_sha256" in reason, reason


# ---------------------------------------------------------------------------
# T5 · build（V3）
#
# 全部用 PATH 前置的假 `wmake`（`fixtures/dev/bin/wmake`）：L1 判的是「我们怎么调用、
# 怎么解析结果」，不是「OpenFOAM 会不会编译」。四条用例各盯一个分支：成功落 build.json、
# rc≠0、rc==0 但 error: 计数/产物不对、超时。
# ---------------------------------------------------------------------------


def _fake_bin(env: dict[str, str], **vars_: str | None) -> dict[str, str]:
    """把 `fixtures/dev/bin` 前置到 PATH（`wmake`/`foamRun` 都从 PATH 取），再注入桩的环境变量。"""
    e = dict(env)
    e["PATH"] = str(FIXTURES / "bin") + os.pathsep + os.environ.get("PATH", "")
    e.update({k: v for k, v in vars_.items() if v is not None})
    return e


def _build(env: dict[str, str], dest: Path, extra: list[str] | None = None):
    return run(["--stage", "build", "--dest", str(dest), *(extra or [])], env=env)


def test_build_success_writes_build_json(tmp_path):
    """成功形态：`wmake -j 2 libso`（选项在 target 之前）、日志落盘、build.json 有 so_sha256。"""
    env, dest = _prepared(tmp_path)
    so = Path(env["FOAM_USER_LIBBIN"]) / "libdemoMod.so"
    calls = tmp_path / "wmake.calls"
    e = _fake_bin(env, FAKE_SO_OUT=str(so), FAKE_WMAKE_LOG=str(calls))

    p = _build(e, dest)
    assert p.returncode == 0, p.stdout + p.stderr

    # T0 实测：`wmake libso -j 4` 退 1（could not change to directory '-j'）
    assert calls.read_text().strip() == "-j 2 libso"

    log = (dest / "log.wmake").read_text()
    assert "making dependency list" in log

    bj = json.loads((dest / "build.json").read_text())
    assert set(bj) == {"lib_name", "so_path", "so_sha256", "so_size",
                       "wmake_cmd", "wmake_rc", "wall_seconds", "error_first"}
    assert bj["lib_name"] == "demoMod"
    assert bj["so_path"] == str(so)
    assert bj["so_sha256"] == hashlib.sha256(so.read_bytes()).hexdigest()
    assert bj["so_size"] == so.stat().st_size
    assert bj["wmake_cmd"] == ["wmake", "-j", "2", "libso"]
    assert bj["wmake_rc"] == 0 and bj["error_first"] is None
    assert bj["wall_seconds"] >= 0


def test_build_rejects_nonzero_rc_and_parses_error_line(tmp_path):
    env, dest = _prepared(tmp_path)
    e = _fake_bin(env, FAKE_WMAKE_RC="2", FAKE_ERR_FILE="demoModel/demoModel.C")

    p = _build(e, dest)
    assert p.returncode == 87, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["wmake_rc"] == 2
    assert payload["error_first"] == {
        "file": "demoModel/demoModel.C", "line": 12,
        "msg": "expected initializer before '}'"}
    assert not (dest / "build.json").exists(), "构建失败不写 build.json（否则 verify 会拿旧记录假绿）"
    assert "error:" in (dest / "log.wmake").read_text(), "失败日志必须落盘，否则无法事后诊断"


def test_build_rejects_so_outside_user_libbin(tmp_path):
    """wmake 退 0 但 `.so` 不在 `$FOAM_USER_LIBBIN` → 87（V3 的第三条判据）。"""
    env, dest = _prepared(tmp_path)
    elsewhere = tmp_path / "elsewhere" / "libdemoMod.so"
    elsewhere.parent.mkdir()
    e = _fake_bin(env, FAKE_SO_OUT=str(elsewhere))

    p = _build(e, dest)
    assert p.returncode == 87, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert "FOAM_USER_LIBBIN" in payload["reason"], payload["reason"]
    assert payload["wmake_rc"] == 0, "退 0 也必须判红：产物不在位就是没构建出可用库"
    assert not (dest / "build.json").exists()


def test_build_rejects_error_in_log_even_if_rc_zero(tmp_path):
    """退 0 但日志里有 `error:` → 87。**这条是 V3 里唯一「只看 rc 就会假绿」的分支**。"""
    env, dest = _prepared(tmp_path)
    so = Path(env["FOAM_USER_LIBBIN"]) / "libdemoMod.so"
    e = _fake_bin(env, FAKE_SO_OUT=str(so), FAKE_ERR_ALWAYS="1")

    p = _build(e, dest)
    assert p.returncode == 87, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["wmake_rc"] == 0, "前提：wmake 自己退 0"
    assert payload["error_count"] == 1
    assert payload["error_first"]["line"] == 12
    assert so.is_file(), "前提：产物在位——所以这条红只能来自 error: 计数"
    assert not (dest / "build.json").exists()


def test_build_reports_timeout(tmp_path):
    """假桩 sleep + `--timeout 0` → 87 且 `timed_out=true`（墙钟必须是 monotic 差值，不许负）。"""
    env, dest = _prepared(tmp_path)
    e = _fake_bin(env, FAKE_SO_OUT=str(Path(env["FOAM_USER_LIBBIN"]) / "libdemoMod.so"),
                  FAKE_WMAKE_SLEEP="10")

    p = _build(e, dest, ["--timeout", "0"])
    assert p.returncode == 87, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["timed_out"] is True
    assert payload["wall_seconds"] >= 0


# ---------------------------------------------------------------------------
# T6 · verify（V4）
#
# 假 `foamRun`（`fixtures/dev/bin/foamRun`）。这里最要紧的一条是
# `test_verify_ignores_nonzero_rc`：T0 实测**坏库名的退出码也是 0**，所以 rc 不是判据；
# 反过来「rc≠0 但 dlopen=0」必须照样判绿。它同时是防下一个人"顺手"加 rc 判据的守卫。
# ---------------------------------------------------------------------------


def _stamp_ahead(env: dict[str, str], ahead_s: float = 60.0) -> Path:
    """造 `build-stamp`：mtime = now + ahead_s。系统树里的文件都比它旧 → R2 判据应绿。"""
    stamp = Path(env["WM_PROJECT_DIR"]) / "build-stamp"
    stamp.write_text("")
    t = time.time() + ahead_s
    os.utime(stamp, (t, t))
    return stamp


def _built(tmp_path: Path, allowed: list[str] | None = None) -> tuple[dict[str, str], Path]:
    """prepare → build 全绿后的现场，供 verify 用。"""
    env, dest = _prepared(tmp_path, allowed=allowed)
    so = Path(env["FOAM_USER_LIBBIN"]) / "libdemoMod.so"
    e = _fake_bin(env, FAKE_SO_OUT=str(so))
    p = _build(e, dest)
    assert p.returncode == 0, p.stdout + p.stderr
    return e, dest


def _verify(env: dict[str, str], dest: Path, extra: list[str] | None = None):
    return run(["--stage", "verify", "--dest", str(dest), *(extra or [])], env=env)


def test_verify_passes_on_loadable_lib(tmp_path):
    env, dest = _built(tmp_path)
    _stamp_ahead(env)
    calls = tmp_path / "foamrun.calls"
    e = _fake_bin(env, FAKE_LOAD="ok", FAKE_FOAMRUN_LOG=str(calls))

    p = _verify(e, dest)
    assert p.returncode == 0, p.stdout + p.stderr

    # 命令形态照 T0 定稿：-libs 的值是 fileNameList，里面的库名必须带引号
    assert calls.read_text().strip() == '-libs ("libdemoMod.so") -help'

    vj = json.loads((dest / "verify.json").read_text())
    assert set(vj) == {"so_sha256_ok", "load_cmd", "load_rc", "dlopen_error",
                       "system_tree_newer", "case_libs_ok"}
    assert vj["load_cmd"] == ["foamRun", "-libs", '("libdemoMod.so")', "-help"]
    assert vj["so_sha256_ok"] is True
    assert vj["load_rc"] == 0 and vj["dlopen_error"] == 0
    assert vj["system_tree_newer"] == []
    assert vj["case_libs_ok"] is None, "没给 --case 时必须显式记 null（而不是悄悄 True）"


def test_verify_rejects_dlopen_error(tmp_path):
    """坏库形态：rc=0 但 `dlopen error` 计数 1 → 88（**rc 抓不到这一条**）。"""
    env, dest = _built(tmp_path)
    _stamp_ahead(env)
    e = _fake_bin(env, FAKE_LOAD="bad")

    p = _verify(e, dest)
    assert p.returncode == 88, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["load_rc"] == 0, "前提：真实现里坏库也退 0（T0 实测）"
    assert payload["dlopen_error"] == 1
    assert "dlopen error" in payload["reason"], payload["reason"]
    assert payload["load_output"], "失败时必须把输出带给调用方，否则无法诊断"
    assert not (dest / "verify.json").exists()


def test_verify_ignores_nonzero_rc(tmp_path):
    """`foamRun` 退 1 但输出里没有 `dlopen error` → **仍判 0**。

    这是 T0 实测的直接推论：错误形态（`-libs "libX.so"`）会让好库退 1，
    判 rc 就会把好库判红。这条用例的存在是为了让「顺手加一句 rc 判据」立刻变红。
    """
    env, dest = _built(tmp_path)
    _stamp_ahead(env)
    e = _fake_bin(env, FAKE_LOAD="ok", FAKE_FOAMRUN_RC="1")

    p = _verify(e, dest)
    assert p.returncode == 0, p.stdout + p.stderr
    vj = json.loads((dest / "verify.json").read_text())
    assert vj["load_rc"] == 1, "rc 照实记进 verify.json，但**不参与判定**"
    assert vj["dlopen_error"] == 0


def test_verify_rejects_changed_system_tree(tmp_path):
    """`$WM_PROJECT_DIR/{src,applications}` 下有比 build-stamp 新的文件 → 89（R2）。"""
    env, dest = _built(tmp_path)
    _stamp_ahead(env)
    evil = Path(env["WM_PROJECT_DIR"]) / "applications/modules/demo/lb/evil.C"
    evil.write_text("// 有人动了系统树\n")
    t = time.time() + 120
    os.utime(evil, (t, t))
    e = _fake_bin(env, FAKE_LOAD="ok")

    p = _verify(e, dest)
    assert p.returncode == 89, p.stdout + p.stderr
    payload = json.loads(p.stdout)
    assert payload["system_tree_newer"] == ["applications/modules/demo/lb/evil.C"]
    assert not (dest / "verify.json").exists()


def test_verify_case_must_declare_libs(tmp_path):
    """`--case`：controlDict 的 `libs` 里必须有 `lib<名>.so`；缺就 88 并说清怎么加。只读不改。"""
    env, dest = _built(tmp_path)
    _stamp_ahead(env)
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    control = case / "system/controlDict"
    control.write_text(
        "FoamFile { version 2.0; format ascii; }\n"
        "solver incompressibleFluid;\n"
        f'libs ("libdemoMod.so");\n')
    e = _fake_bin(env, FAKE_LOAD="ok")

    ok = _verify(e, dest, ["--case", str(case)])
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert json.loads((dest / "verify.json").read_text())["case_libs_ok"] is True

    # 缺 libs → 88，reason 里给现成可粘的一行
    control.write_text("FoamFile { version 2.0; format ascii; }\nsolver incompressibleFluid;\n")
    missing = _verify(e, dest, ["--case", str(case)])
    assert missing.returncode == 88, missing.stdout + missing.stderr
    reason = json.loads(missing.stdout)["reason"]
    assert 'libs ("libdemoMod.so")' in reason, reason
    assert control.read_text() == "FoamFile { version 2.0; format ascii; }\nsolver incompressibleFluid;\n", \
        "verify 只读 case，不许修改它"
