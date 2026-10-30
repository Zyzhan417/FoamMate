#!/usr/bin/env python3
"""scripts/dev_lib.py —— 模块 J：OpenFOAM 二次开发（用户库）的确定性半边。

四个 stage，全部通过 --stage 选择（与 verify_case.sh 的 --stage 同风格，不另起子命令）：

  prepare  从 $WM_PROJECT_DIR 派生一个子库到 $WM_PROJECT_USER_DIR/src/<name>，
           改写 Make/files 的 LIB 行与 Make/options 里指向副本之外的相对 -I，写 dev.meta。
  check    先验 dev.meta 自身的封印（meta_self_sha256），再把当前树与 manifest 的 sha256
           清单比对：改动必须落在 allowed_files 内。
  build    在副本里 `wmake -j N libso`（选项必须在 target 之前），日志写 <dest>/log.wmake，
           判 rc、判日志里的 error: 计数、判 .so 是否落在 $FOAM_USER_LIBBIN。
  verify   证明 .so 能被 dlopen（**只判 `dlopen error` 计数，不判退出码**：坏库名实测也退 0）；
           并检查 $WM_PROJECT_DIR 未被改动（R2）。

退出码：0 全过 / 85 规格不合法 / 86 改动越界 / 87 构建失败或产物缺失 /
        88 加载证明失败 / 89 系统树被改动（R2） / 64 用法错误

环境：必须先 source OpenFOAM 的 bashrc。本脚本**不**自己去发现安装路径
      （写死前缀会被 tests/unit/test_portability.py 判红），环境为空一律 85 并提示。
"""

from __future__ import annotations

import argparse
import difflib
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
VERIFY_NAME = "verify.json"
WMAKE_LOG = "log.wmake"
#: `dev.meta` 里记录自身哈希的键（见 meta_self_sha 的注释）
META_SELF = "meta_self_sha256"
#: 由脚本自己产出的文件：不属于「改动」，不进 manifest 比对
GENERATED = frozenset({META_NAME, BUILD_NAME, VERIFY_NAME, WMAKE_LOG})

STAGES = ("prepare", "check", "build", "verify")


class _Parser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64（理由同其它模块：2 是 G2 门失败）。

    覆盖 `error()` 时必须**先打印用法块**再退：argparse 默认实现就是这么做的，
    只打 `prog: error: <msg>` 会让 `tests/unit/test_exit_codes.py` 的
    「用法错误要说明错在哪」那条判据失去可判定的对象（2026-10-31 实测）。
    """

    def error(self, message: str) -> None:      # pragma: no cover - argparse 内部
        self.print_usage(sys.stderr)
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


def meta_self_sha(meta: dict) -> str:
    """`dev.meta` 自身的封印：对其余键做**规范序列化**后取 sha256（不含封印本身）。

    为什么要这个：`manifest` 明确不含 `dev.meta`（它自己写不进去自己的哈希），
    于是「把 allowed_files 加一个 `*`」这种改法可以让 V2 恒绿——**改判据绕过判据**。
    封印把它变成一个可判定的差值；它防的是误改与随手绕过，不是有决心的本地伪造
    （算法是公开的，重算一遍封印就能过——本地工具能给的强度只到这里）。
    """
    body = {k: v for k, v in meta.items() if k != META_SELF}
    raw = json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True).encode()
    return sha256_bytes(raw)


def diff_manifest(base: dict[str, str], cur: dict[str, str]) -> dict[str, list[str]]:
    """清单差集。三个键恒存在（空也是 `[]`），调用方不必再判 None。"""
    return {
        "modified": sorted(k for k in base.keys() & cur.keys() if base[k] != cur[k]),
        "added": sorted(cur.keys() - base.keys()),
        "deleted": sorted(base.keys() - cur.keys()),
    }


def match_any(rel: str, patterns: list[str]) -> bool:
    """与 verify_case.sh 的 G5 同语义：fnmatch，`*` 跨 `/`（`fnmatch` 不把 `/` 当分隔符）。"""
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


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
# 四个 stage（prepare → check → build → verify 的顺序就是 S2/S4/S5/S6 的顺序）
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
    meta[META_SELF] = meta_self_sha(meta)     # 封印：只覆盖上面这 7 键
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



def _base_text(rel: str, meta: dict, project_dir: Path | None) -> str | None:
    """prepare 时该文件应有的文本，用来算 `lines_added`/`lines_removed`。

    两个被改写过的 Make 文件可以从源文件**逆推**（改写是纯函数，且 lib 名记在 meta 里），
    所以这里的基线与 prepare 当时逐字一致；源树不可读（没 source bashrc）时返回 None。
    """
    if project_dir is None:
        return None
    src_root = project_dir / (meta.get("system_source") or "")
    if not meta.get("system_source") or not (src_root / rel).is_file():
        return None
    text = (src_root / rel).read_text(errors="replace")
    if rel == "Make/files":
        return rewrite_lib_line(text, meta.get("lib_name") or "")[0]
    if rel == "Make/options":
        return rewrite_includes(text, src_root)[0]
    return text


def _line_delta(before: str | None, after: str | None) -> tuple[int, int]:
    """纯信息量（不参与判据）：按行 diff 数 `+`/`-`。基线不可得的一侧按空算。"""
    a = (before or "").splitlines()
    b = (after or "").splitlines()
    added = removed = 0
    for line in difflib.unified_diff(a, b, lineterm="", n=0):
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def stage_check(args: argparse.Namespace) -> int:
    """V2：当前树与 `dev.meta.manifest` 的差集必须被 `allowed_files` 全覆盖。

    顺序：先验封印（**判据自身**），再比树。反过来的话，改 `allowed_files` 就能让后面的
    比对恒绿——那是「改判据绕过判据」，与 `bench` 冻结清单同一个理由。
    """
    if not args.dest:
        _usage("--stage check 需要 --dest")

    dest = Path(args.dest).resolve()
    meta_path = dest / META_NAME
    if not meta_path.is_file():
        _fail(EX_SPEC, "缺 dev.meta：这个目录不是 prepare 的产物（先跑 --stage prepare）",
              dest=str(dest))
    meta = json.loads(meta_path.read_text(errors="replace"))

    sealed = meta.get(META_SELF)
    if not sealed:
        _fail(EX_SCOPE,
              "dev.meta 缺 meta_self_sha256：判据自身无法校验（旧版 prepare 写的或无此键），"
              "重跑 --stage prepare 让封印落到盘上",
              dest=str(dest))
    if meta_self_sha(meta) != sealed:
        _fail(EX_SCOPE,
              "dev.meta 自身被改过（meta_self_sha256 不符）：改 allowed_files 等于改判据，"
              "这条判据失效后 V2 恒绿，所以先判它",
              dest=str(dest))

    allowed = [p for p in (meta.get("allowed_files") or []) if p]
    base = {k: v for k, v in (meta.get("manifest") or {}).items() if k not in GENERATED}
    cur_files, _links = sha256_tree(dest)
    cur = {k: v for k, v in cur_files.items() if k not in GENERATED}

    changed = diff_manifest(base, cur)
    # 三个键恒存在（空也给 `[]`）：payload 的形状稳定，调用方不用判 None
    violations = {kind: [rel for rel in rels if not match_any(rel, allowed)]
                  for kind, rels in changed.items()}
    if any(violations.values()):
        offenders = sorted({rel for rels in violations.values() for rel in rels})
        _fail(EX_SCOPE,
              f"改动越界：{len(offenders)} 个文件不在 dev.meta.allowed_files 里"
              "（改之前先把它们写进 --allowed，否则 V2 挡不住任何东西）",
              violations=violations, allowed_files=allowed, dest=str(dest))

    project_dir = Path(_env("WM_PROJECT_DIR")).resolve() if _env("WM_PROJECT_DIR") else None
    lines_added = lines_removed = 0
    for kind, rels in changed.items():
        for rel in rels:
            before = _base_text(rel, meta, project_dir) if kind != "added" else None
            after = ((dest / rel).read_text(errors="replace")
                     if kind != "deleted" and (dest / rel).is_file() else None)
            a, r = _line_delta(before, after)
            lines_added += a
            lines_removed += r

    _emit({
        "ok": True,
        "stage": "check",
        "dest": str(dest),
        "lib": meta.get("lib_name"),
        "changed": changed,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "allowed_files": allowed,
    }, EX_OK)


# ---------------------------------------------------------------------------
# build（V3）：call wmake / parse log / check .so
# ---------------------------------------------------------------------------

#: gcc 的错误行形态：`file:12:5: error: msg` / `file:12: error: msg`（列号可选）
GCC_ERR = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*(?:fatal )?error:\s*(?P<msg>.+)$",
    re.M,
)


def first_error(log_text: str) -> dict | None:
    """日志里第一条 gcc 形态的错误（`wmake error: ...` 这种没有 `file:line:` 的不算）。"""
    m = GCC_ERR.search(log_text)
    if m is None:
        return None
    return {"file": m.group("file"), "line": int(m.group("line")), "msg": m.group("msg").strip()}


def error_lines(log_text: str) -> int:
    """`grep -c 'error:'` 的行数语义（不是出现次数：一行只算一次，与手工核对一致）。"""
    return sum(1 for line in log_text.splitlines() if "error:" in line)


def _as_text(value: str | bytes | None) -> str:
    """TimeoutExpired 里带出来的可能是 bytes 也可能是 None（text=True 时通常是部分文本）。"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def stage_build(args: argparse.Namespace) -> int:
    """V3：`wmake -j N libso` 必须退 0、日志 `error:` 计数为 0、`.so` 落在 `$FOAM_USER_LIBBIN`。

    判据顺序是有讲究的：rc 与 `error:` 计数**各自都不完备**（实测：`wmake libso -j 4` 退 1，
    反方向也有退 0 但带 error 的），两条一起才闭合；`.so` 在位是第三条，缺了它
    「上次的产物」会让这道门假绿。
    """
    if not args.dest:
        _usage("--stage build 需要 --dest")
    if args.timeout < 0:
        _usage("--timeout 不能为负")

    dest = Path(args.dest).resolve()
    meta_path = dest / META_NAME
    if not meta_path.is_file():
        _fail(EX_SPEC, "缺 dev.meta：这个目录不是 prepare 的产物（先跑 --stage prepare）",
              dest=str(dest))
    meta = json.loads(meta_path.read_text(errors="replace"))
    lib = meta.get("lib_name")
    if not lib:
        _fail(EX_SPEC, "dev.meta 里没有 lib_name", dest=str(dest))
    libbin = _require_env(("FOAM_USER_LIBBIN",))["FOAM_USER_LIBBIN"]

    # 选项必须在 target 之前：T0 实测 `wmake libso -j 4` 退 1（could not change to directory '-j'）
    cmd = ["wmake", "-j", str(args.jobs), "libso"]
    if shutil.which(cmd[0]) is None:
        _fail(EX_BUILD, "PATH 上没有 wmake：先 source $WM_PROJECT_DIR/etc/bashrc",
              cmd=cmd, timed_out=False, wall_seconds=0.0)

    t0 = time.monotonic()                 # 墙钟只许用 monotonic（time.time() 会写出负值）
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=str(dest), capture_output=True,
                              text=True, timeout=args.timeout)
        stdout, stderr, rc = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out, rc = True, None
        stdout, stderr = _as_text(exc.stdout), _as_text(exc.stderr)
    wall = round(time.monotonic() - t0, 3)

    log = stdout + stderr
    log_path = dest / WMAKE_LOG
    log_path.write_text(log)               # 失败也落盘：不落盘就无法事后定位
    errors = error_lines(log)
    err_first = first_error(log)
    common = {"wmake_cmd": cmd, "wmake_rc": rc, "wall_seconds": wall, "log": str(log_path)}

    if timed_out:
        _fail(EX_BUILD, f"wmake 超过 --timeout {args.timeout}s，已杀掉；改 --timeout 或查环境",
              timed_out=True, **common)
    if rc != 0:
        _fail(EX_BUILD, f"wmake 退出 {rc}", timed_out=False, error_count=errors,
              error_first=err_first, **common)
    if errors > 0:
        _fail(EX_BUILD,
              f"wmake 退 0 但日志里有 {errors} 行 error:（不信退出码，只信日志行）",
              timed_out=False, error_count=errors, error_first=err_first, **common)
    so = libbin / f"lib{lib}.so"
    if not so.is_file():
        _fail(EX_BUILD, "wmake 成功但 .so 不在 $FOAM_USER_LIBBIN",
              timed_out=False, error_count=errors, so_path=str(so), **common)

    build = {
        "lib_name": lib,
        "so_path": str(so),
        "so_sha256": sha256_bytes(so.read_bytes()),
        "so_size": so.stat().st_size,
        "wmake_cmd": cmd,
        "wmake_rc": rc,
        "wall_seconds": wall,
        "error_first": err_first,
    }
    (dest / BUILD_NAME).write_text(
        json.dumps(build, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    _emit({"ok": True, "stage": "build", "dest": str(dest), **build}, EX_OK)


# ---------------------------------------------------------------------------
# verify（V4）：dlopen 证明 + 系统树干净
# ---------------------------------------------------------------------------


def system_tree_newer(project_dir: Path) -> list[str]:
    """`$WM_PROJECT_DIR/{src,applications}` 下 mtime **严格晚于** `build-stamp` 的文件。

    这是 R2 的逆否：`/opt/openfoam13` 不是 git 仓库，编译时间戳是唯一现成基线。
    `build-stamp` 缺失时返回哨兵串（**不**返回空列表）：没有基线就不能说「没被改过」，
    返回 `[]` 会让 89 变成恒绿。
    """
    stamp = project_dir / "build-stamp"
    if not stamp.is_file():
        return ["<build-stamp 缺失>"]
    t = stamp.stat().st_mtime
    out: list[str] = []
    for sub in ("src", "applications"):
        base = project_dir / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            try:
                if p.is_file() and p.stat().st_mtime > t:
                    out.append(p.relative_to(project_dir).as_posix())
                    if len(out) >= 20:
                        return out
            except OSError:
                continue
    return out


#: controlDict 里的 `libs` 条目（先剥注释，再取到第一个 `;` 为止）
LIBS_ENTRY = re.compile(r"^\s*libs\s+(?P<val>.*?);", re.M | re.S)


def case_libs_problem(control_dict: Path, libfile: str) -> str | None:
    """`--case` 的可选断言：controlDict 的 `libs` 里要有 `lib<名>.so`。**只读**。返回问题描述。"""
    try:
        text = control_dict.read_text(errors="replace")
    except OSError as exc:
        return f"读不到 {control_dict}：{exc}"
    body = re.sub(r"/\*.*?\*/", "", re.sub(r"\/\/[^\n]*", "", text), flags=re.S)
    m = LIBS_ENTRY.search(body)
    hint = f'libs ("{libfile}");'
    if m is None:
        return (f"{control_dict} 里没有 libs 条目：在 FoamFile 块之后加一行 {hint} "
                f"（只读断言，本脚本不改 case）")
    if libfile not in m.group("val"):
        return f"{control_dict} 的 libs 里没有 {libfile}：把 {hint} 补进去（只读断言，本脚本不改 case）"
    return None


def stage_verify(args: argparse.Namespace) -> int:
    """V4：`.so` 与 build.json 一致、`dlopen error` 计数为 0、系统树没被改、（可选）case 声明了本库。

    **不判 `foamRun` 的退出码**：T0 实测好库名与坏库名都退 0，而写错的 `-libs` 形态会让
    好库退 1——判 rc 既有假绿也有假红。
    """
    if not args.dest:
        _usage("--stage verify 需要 --dest")

    dest = Path(args.dest).resolve()
    meta_path = dest / META_NAME
    if not meta_path.is_file():
        _fail(EX_SPEC, "缺 dev.meta：这个目录不是 prepare 的产物（先跑 --stage prepare）",
              dest=str(dest))
    meta = json.loads(meta_path.read_text(errors="replace"))
    lib = meta.get("lib_name")
    if not lib:
        _fail(EX_SPEC, "dev.meta 里没有 lib_name", dest=str(dest))

    build_path = dest / BUILD_NAME
    if not build_path.is_file():
        _fail(EX_BUILD, "缺 build.json：还没构建过（先跑 --stage build）", dest=str(dest))
    build = json.loads(build_path.read_text(errors="replace"))

    envs = _require_env(("FOAM_USER_LIBBIN", "WM_PROJECT_DIR"))
    libbin, project_dir = envs["FOAM_USER_LIBBIN"], envs["WM_PROJECT_DIR"]
    libfile = f"lib{lib}.so"
    so = libbin / libfile

    # 1) 产物与构建记录必须对得上（防「re-build 了别的库」这种假绿）
    so_sha = sha256_bytes(so.read_bytes()) if so.is_file() else None
    so_ok = so_sha is not None and so_sha == build.get("so_sha256")
    if not so_ok:
        _fail(EX_LOAD,
              "产物与 build.json 不符：.so 缺失或 sha256 变了（re-build 过？重跑 --stage build）",
              so_sha256_ok=False, so_path=str(so),
              so_sha256=so_sha, expect=build.get("so_sha256"))

    # 2) 加载证明：命令形态照 T0 定稿，判据只有 `dlopen error` 计数
    load_cmd = ["foamRun", "-libs", f'("{libfile}")', "-help"]
    if shutil.which(load_cmd[0]) is None:
        _fail(EX_LOAD, "PATH 上没有 foamRun：先 source $WM_PROJECT_DIR/etc/bashrc",
              load_cmd=load_cmd, so_sha256_ok=True)
    rc: int | None = None
    try:
        proc = subprocess.run(load_cmd, capture_output=True, text=True, timeout=args.timeout)
        merged, rc = (proc.stdout or "") + (proc.stderr or ""), proc.returncode
    except subprocess.TimeoutExpired as exc:
        merged = _as_text(exc.stdout) + _as_text(exc.stderr)
        _fail(EX_LOAD, f"foamRun -help 超过 --timeout {args.timeout}s", load_cmd=load_cmd,
              load_rc=None, dlopen_error=merged.count("dlopen error"))

    dlopen = merged.count("dlopen error")
    if dlopen:
        head = "\n".join(merged.splitlines()[:20])
        _fail(EX_LOAD,
              f"加载证明失败：输出里 dlopen error 出现 {dlopen} 次"
              "（`.so` 在 $FOAM_USER_LIBBIN 但不在 LD_LIBRARY_PATH 上，或库本身坏了）",
              load_cmd=load_cmd, load_rc=rc, dlopen_error=dlopen, load_output=head)

    # 3) R2：系统树没有被我们改动过
    newer = system_tree_newer(project_dir)
    if newer:
        _fail(EX_SYSTEM,
              f"$WM_PROJECT_DIR 下有 {len(newer)} 个文件比 build-stamp 新：系统树被改过（R2）",
              system_tree_newer=newer, project_dir=str(project_dir))

    # 4) 可选：case 侧声明了本库（只读断言，不改 case）
    case_libs_ok: bool | None = None
    if args.case:
        problem = case_libs_problem(Path(args.case).resolve() / "system" / "controlDict", libfile)
        if problem:
            _fail(EX_LOAD, problem, case_libs_ok=False, load_cmd=load_cmd)
        case_libs_ok = True

    verify = {
        "so_sha256_ok": so_ok,
        "load_cmd": load_cmd,
        "load_rc": rc,
        "dlopen_error": dlopen,
        "system_tree_newer": newer,
        "case_libs_ok": case_libs_ok,
    }
    (dest / VERIFY_NAME).write_text(
        json.dumps(verify, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    _emit({"ok": True, "stage": "verify", "dest": str(dest), "lib": lib,
           "so_path": str(so), **verify}, EX_OK)


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
