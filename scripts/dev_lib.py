#!/usr/bin/env python3
"""scripts/dev_lib.py —— 模块 J：OpenFOAM 二次开发（用户库）的确定性半边。

四个 stage，全部通过 --stage 选择（与 verify_case.sh 的 --stage 同风格，不另起子命令）：

  prepare  从 $WM_PROJECT_DIR 派生一个子库到 $WM_PROJECT_USER_DIR/src/<name>，
           改写 Make/files 的 LIB 行与 Make/options 里指向副本之外的相对 -I，写 dev.meta。
  check    把当前树与 dev.meta 里的 sha256 清单比对：改动必须落在 allowed_files 内。
  build    在副本里 wmake libso，日志写 <dest>/log.wmake，检查 .so 落在 $FOAM_USER_LIBBIN。
  verify   证明 .so 能被 dlopen（失败时日志里有 dlopen error）；并检查系统树未被改动。

退出码：0 全过 / 85 规格不合法 / 86 改动越界 / 87 构建失败或产物缺失 /
        88 加载证明失败 / 89 系统树被改动（R2） / 64 用法错误

环境：必须先 source OpenFOAM 的 bashrc。本脚本**不**自己去发现安装路径
      （写死前缀会被 tests/unit/test_portability.py 判红），环境为空一律 85 并提示。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EX_OK = 0
EX_SPEC = 85          # 规格不合法（source/dest/lib 名/Make 改写不可解析）
EX_SCOPE = 86         # 改动越界（allowed_files 之外的 modified/added/deleted）
EX_BUILD = 87         # wmake 失败 / .so 缺失 / 日志里有 error:
EX_LOAD = 88          # dlopen 证明失败
EX_SYSTEM = 89        # $WM_PROJECT_DIR 被改动（R2）
EX_USAGE = 64         # 用法错误（全仓统一，不用 2）

META_NAME = "dev.meta"
BUILD_NAME = "build.json"
WMAKE_LOG = "log.wmake"

STAGES = ("prepare", "check", "build", "verify")


class _Parser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64（理由同其它模块：2 是 G2 门失败）。"""

    def error(self, message: str) -> None:      # pragma: no cover - argparse 内部
        self.exit(EX_USAGE, f"{self.prog}: error: {message}\n")


def _emit(payload: dict, code: int) -> None:
    """成功/可解释的失败都往 stdout 打纯 JSON；人看的解释走 stderr。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    sys.exit(code)


def _fail(code: int, reason: str, **extra) -> None:
    payload = {"ok": False, "reason": reason}
    payload.update(extra)
    _emit(payload, code)


def _env(name: str) -> str:
    return os.environ.get(name, "")


def _require_env(keys: tuple[str, ...]) -> dict[str, Path]:
    missing = [k for k in keys if not _env(k)]
    if missing:
        _fail(EX_SPEC, "环境变量为空，先 source OpenFOAM 的 bashrc", missing=missing)
    return {k: Path(_env(k)).resolve() for k in keys}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="dev_lib.py",
        description="OpenFOAM 二次开发（用户库）：派生 / 越界检查 / 编译 / 加载证明",
        epilog="退出码：0 全过 / 85 规格 / 86 越界 / 87 构建 / 88 加载 / 89 系统树被改 / 64 用法",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--stage", required=True, choices=STAGES,
                   help="prepare | check | build | verify")
    p.add_argument("--source", help="prepare：系统子库目录（$WM_PROJECT_DIR 下）")
    p.add_argument("--dest", help="prepare/check/build/verify：用户副本目录（$WM_PROJECT_USER_DIR 下）")
    p.add_argument("--lib", help="prepare：新库名（不含 lib 前缀与 .so）")
    p.add_argument("--allowed", action="append", default=[],
                   help="prepare：允许后续改动的文件（glob，可重复或逗号分隔）")
    p.add_argument("--jobs", type=int, default=2, help="build：wmake -j 的并行度（默认 2）")
    p.add_argument("--timeout", type=int, default=1800, help="build：wmake 的墙钟上限（秒）")
    p.add_argument("--case", help="verify：可选，检查该 case 的 controlDict 是否 libs 了本库")
    return p


# ---------------------------------------------------------------------------
# 四个 stage（T2 只放桩，T3 起逐段替换）
# ---------------------------------------------------------------------------


def stage_prepare(args: argparse.Namespace) -> int:
    _fail(EX_SPEC, "未实现")


def stage_check(args: argparse.Namespace) -> int:
    _fail(EX_SPEC, "未实现")


def stage_build(args: argparse.Namespace) -> int:
    _fail(EX_SPEC, "未实现")


def stage_verify(args: argparse.Namespace) -> int:
    _fail(EX_SPEC, "未实现")


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "prepare": stage_prepare,
        "check": stage_check,
        "build": stage_build,
        "verify": stage_verify,
    }
    return handlers[args.stage](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
