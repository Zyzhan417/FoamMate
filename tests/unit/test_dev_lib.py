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
    assert set(meta) == {"system_source", "lib_name", "system_lib",
                         "created_at", "allowed_files", "manifest", "symlinks"}
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
