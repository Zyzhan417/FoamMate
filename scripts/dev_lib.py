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
# Make 改写（规则见 references/14-library-dev-flow.md §5）
# ---------------------------------------------------------------------------

#: `Make/files` 里的 LIB 行（只要第一条）
LIB_LINE = re.compile(r"^LIB\s*=.*$", re.M)
#: `Make/options` 里一条 `-I<路径>`，缩进与行尾续行符都要原样保留
INC_LINE = re.compile(r"^(?P<pre>\s*)-I(?P<inc>\S+)(?P<post>\s*(?:\\)?\s*)$", re.M)
#: 库名：字母开头、只含字母数字下划线（`lib` 前缀与 `.so` 由脚本加）
LIB_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def rewrite_lib_line(text: str, lib: str) -> tuple[str, str | None]:
    """把第一条 `LIB = …` 换成用户库；没有则插到文件首行。返回 (新文本, 原行)。"""
    new = f"LIB = $(FOAM_USER_LIBBIN)/lib{lib}"
    m = LIB_LINE.search(text)
    if m is None:
        return f"{new}\n\n{text}", None
    return text[: m.start()] + new + text[m.end():], m.group(0)


def rewrite_includes(text: str, src_root: Path) -> tuple[str, list[str]]:
    """外部相对 -I 改绝对；副本内相对、绝对路径、make 变量一律原样。返回 (新文本, 不可解析项)。"""
    root = src_root.resolve()
    unresolved: list[str] = []

    def repl(m: re.Match[str]) -> str:
        inc = m.group("inc")
        if "$" in inc:
            return m.group(0)
        p = Path(inc)
        if p.is_absolute():
            return m.group(0)
        target = (root / p).resolve()
        try:
            target.relative_to(root)
            return m.group(0)            # 仍在副本内
        except ValueError:
            pass
        if target.is_dir():
            return f"{m.group('pre')}-I{target}{m.group('post')}"
        unresolved.append(inc)
        return m.group(0)

    return INC_LINE.sub(repl, text), unresolved


def sha256_tree(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """普通文件 → sha256；符号链接 → 指向（不跟随，避免把系统头文件的哈希也算进来）。"""
    files: dict[str, str] = {}
    links: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            links[rel] = os.readlink(p)
        elif p.is_file():
            files[rel] = sha256_bytes(p.read_bytes())
    return files, links


# ---------------------------------------------------------------------------
# 小工具（prepare 用）
# ---------------------------------------------------------------------------


def _usage(message: str) -> None:
    """用法错误：只写 stderr，stdout 保持空（否则调用方会把错误当成 JSON 结果）。"""
    sys.stderr.write(f"dev_lib.py: error: {message}\n")
    sys.exit(EX_USAGE)


def _under(child: Path, parent: Path) -> bool:
    """child 是否在 parent 之下（含相等由调用方另判）。两边都已 resolve。"""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _now_iso() -> str:
    """带时区偏移的本地时间（`2026-10-31T00:05:00+08:00`）。

    不带偏移的时间戳在跨机器比较时无法排序，也无法区分「同一时刻的不同写法」。
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 四个 stage（T2 只放桩，T3 起逐段替换）
# ---------------------------------------------------------------------------


def stage_prepare(args: argparse.Namespace) -> int:
    """派生 + 改写 Make + V1 自检 + dev.meta。任何一处不合规都退 85 并说明人话原因。"""
    if not (args.source and args.dest and args.lib):
        _usage("--stage prepare 需要 --source、--dest、--lib 三个参数")

    envs = _require_env(("WM_PROJECT_DIR", "FOAM_LIBBIN",
                         "WM_PROJECT_USER_DIR", "FOAM_USER_LIBBIN"))
    project_dir = envs["WM_PROJECT_DIR"]
    user_dir = envs["WM_PROJECT_USER_DIR"]
    lib = args.lib

    # 判据 2：库名合法且不与系统库同名（R2 的逆否：不许覆盖系统产物）
    if LIB_NAME.fullmatch(lib) is None:
        _fail(EX_SPEC,
              "lib 名不合法：必须字母开头、只含字母/数字/下划线（不带 lib 前缀与 .so）",
              lib=lib)
    system_so = envs["FOAM_LIBBIN"] / f"lib{lib}.so"
    if system_so.exists():
        _fail(EX_SPEC,
              f"$FOAM_LIBBIN 下已存在 lib{lib}.so：新库名不得与系统库同名（R2）",
              conflicting=str(system_so))

    # 判据 3：source 必须来自系统树，且是个「带 Make/files 的子库」
    source = Path(args.source).resolve()
    if not (_under(source, project_dir / "src") or _under(source, project_dir / "applications")):
        _fail(EX_SPEC,
              "source 必须在 $WM_PROJECT_DIR 的 src/ 或 applications/ 之下（派生源只读自系统树，R2）",
              source=str(source), project_dir=str(project_dir))
    if not (source / "Make" / "files").is_file():
        _fail(EX_SPEC,
              "source 不是可编译子库：缺 Make/files（用 grep -rl '^LIB' <目录> --include=files 找带 Make/ 的目录）",
              source=str(source))

    # 判据 4：dest 必须在用户目录下，且不存在（不覆盖、不删除：破坏性操作交给用户）
    dest = Path(args.dest).resolve()
    if dest == user_dir or not _under(dest, user_dir):
        _fail(EX_SPEC,
              "dest 必须在 $WM_PROJECT_USER_DIR 之下（运行期零写入仓库树）",
              dest=str(dest), user_dir=str(user_dir))
    if dest.exists():
        _fail(EX_SPEC, "dest 已存在：不覆盖、不删除（破坏性操作交给用户）", dest=str(dest))

    # 判据 5：cp -a 语义（symlinks=True 才等价于 `cp -a`；默认会跟随链接、把系统头文件拷进来）
    shutil.copytree(source, dest, symlinks=True)

    # 判据 6：改写 Make/files 的 LIB 行 + Make/options 的外部相对 -I
    rewritten: list[str] = []
    files_path = dest / "Make" / "files"
    text = files_path.read_text()
    new_text, original_lib = rewrite_lib_line(text, lib)
    if new_text != text:
        files_path.write_text(new_text)
        rewritten.append("Make/files")

    options_path = dest / "Make" / "options"
    if options_path.is_file():
        otext = options_path.read_text()
        new_otext, unresolved = rewrite_includes(otext, source)
        if unresolved:
            shutil.rmtree(dest)          # 不留半成品：否则下一次 prepare 会因 dest 已存在而永远 85
            _fail(EX_SPEC,
                  "Make/options 里的 -I 指向副本之外、目标目录又不存在：不猜，已删掉 dest 副本",
                  unresolved=unresolved, source=str(source))
        if new_otext != otext:
            options_path.write_text(new_otext)
            rewritten.append("Make/options")

    # 判据 7：V1 自检 —— 除被改写的两份外，逐文件 sha256 必须与源相同
    src_files, src_links = sha256_tree(source)
    dst_files, dst_links = sha256_tree(dest)
    exempt = {"Make/files", "Make/options"}
    mismatched = sorted(rel for rel, h in src_files.items()
                        if rel not in exempt and dst_files.get(rel) != h)
    extra = sorted(set(dst_files) - set(src_files))
    if mismatched or extra or src_links != dst_links:
        shutil.rmtree(dest)
        _fail(EX_SPEC,
              "V1 派生不完整：副本与源的 sha256/链接不一致，已删掉 dest 副本",
              mismatched=mismatched, extra=extra,
              symlinks_ok=src_links == dst_links)

    # 判据 8：写 dev.meta（7 键；manifest 是**改写后**的真值，不含 dev.meta 自身）
    allowed = [item.strip()
               for raw in args.allowed
               for item in raw.split(",")
               if item.strip()]
    meta = {
        "system_source": source.relative_to(project_dir).as_posix(),
        "lib_name": lib,
        "system_lib": original_lib.split("=", 1)[1].strip() if original_lib else None,
        "created_at": _now_iso(),
        "allowed_files": allowed,
        "manifest": dst_files,
        "symlinks": dst_links,
    }
    (dest / META_NAME).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )

    # 判据 9：成功形态
    _emit({
        "ok": True,
        "stage": "prepare",
        "dest": str(dest),
        "source": str(source),
        "lib": lib,
        "files": len(dst_files),
        "rewritten": rewritten,
        "allowed_files": allowed,
    }, EX_OK)



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
