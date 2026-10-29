#!/usr/bin/env python3
"""模块 F：把 OpenFOAM 的失败日志定位到「改哪个文件的哪个 entry」；或按调用方给的
changes 备份 → 写回 → 回读。**本模块不重跑求解**（重跑是部件 D 的事）。

规格：`references/09-architecture-and-test-plan.md` §F 与 D22–D25；「entry 必须恰好命中 1 次」
出自 `references/06-agent-anatomy.md:150`；「定位不到不猜」出自 D23；「结构修复不硬塞进
{file,entry,new_value}」出自 D24；指纹口径出自 D25。

===============================================================================
两种互斥模式（同时给 → 64；都不给 → 64）
===============================================================================
  locate  --case <c> --error-log <file> --attempt N [--max-attempts M] [--allowed g1,g2] [--dry-run]
          读失败日志，按**只有 4 条**的规则表定位。**不写任何字典**。
          定位成功也只给 `{file, entry, new_value: null}` —— 因为
          「能确定改哪儿」不等于「知道该改成什么值」：后者依赖需求与物理判断，
          本模块做不到，猜一个默认值会把「需求没被满足」伪装成「门全过」。
          所以 locate 永远 `written=false`。

  apply   --case <c> --apply '<json>' --attempt N [...] [--dry-run]
          接受调用方给的 `[{"file":..,"entry":..,"new_value":..}]`，
          校验 → 备份 → 写回 → 回读。**不读 --error-log**。
          `--dry-run` 只算不写（照样做校验，所以会如实报 33）。

===============================================================================
三条硬要求（每条都对应一次实测踩坑）
===============================================================================
1. **备份优先**：写回前 `cp -a <case> <case 的父目录>/attempt_<n>/`。备份失败 → 不写，退 64。
   备份里是**改前**字节，所以随时能回到刚才的状态。
2. **写完必须回读**：`foamDictionary` 的字典文件是**位置参数**
   （`foamDictionary <file> -entry <e> -set <v>`）。给它 `-case` 而不给文件时它只打 Usage
   （实测还会 FOAM FATAL "Wrong number of arguments"，退 1），**字典一个字节都没变**——
   也就是说「命令跑过了」不等于「值改了」。所以写后一律
   `foamDictionary <file> -entry <e> -value` 回读，值不符 → 回滚该文件 → 退 33。
3. **entry 必须在 file 里恰好命中 1 次**：写前自己数行（0 次或 >=2 次 → 退 33，字典不变）。
   为什么不能信 `-set` 的退出码（实测，cavity 的 controlDict）:
       $ foamDictionary $T/system/controlDict -entry noSuchKey9 -set 1; echo rc=$?
       New entry noSuchKey9      1;
       rc=0                              ← 拼错的 entry 被**新增**进文件，仍退 0
   所以在 apply 里，一个 typo 会被静默写进字典、求解器随后照样 FATAL。数一遍是唯一防线。

===============================================================================
stdout：**一行** JSON（字段顺序固定）
===============================================================================
  {"changes":[{"file":"system/fvSolution","entry":"PIMPLE","new_value":null}],
   "written":false,"backup_dir":null,"declined":false,"reason":null,
   "fingerprint":"a1b2c3d4e5f60718"}

  `changes` = 本模块**决定要改**的东西：locate 模式是定位结果（new_value=null，
  不写盘）；apply 模式是校验通过的请求；**退出码非 0 的拒绝一律 `changes=[]`**
  （拒绝时没有任何东西被应用，列出来只会让调用方误以为改过了）。

退出码：0 正常（**含 declined**，看 JSON 的 declined 字段）/ 31 已达 max-attempts /
32 同一指纹重复（D25）/ 33 写前校验或回读不符 / 64 用法错误。

===============================================================================
指纹去重（D25）的一个必要补充
===============================================================================
  D25：指纹 = `sha256(FATAL 首行 + "\\n" + "file:entry")[:16]`，落盘
  `<run>/attempt_<n>/fingerprint.txt`，跨 attempt 靠扫 `attempt_*/fingerprint.txt`。
  但 locate 模式**不建 attempt 目录**（那里是备份区，locate 没备份可放），于是同一 FATAL
  在 locate 模式下永远无记录可查 —— F7 要求的「attempt 1 后 attempt 2 退 32」就不可能成立。
  所以本实现额外维护一行一条的 `<run>/fingerprints.txt` 台账（run 目录本身，不是备份区），
  去重时**两处都扫**（`attempt_*/fingerprint.txt` + 台账）：对 D25 的规定是超集，不冲突。
  declined 的结果**不记台账**：它没有 file:entry，记了会让「同一个定位不了的老错误」
  变成 32，掩盖真正的原因（D23 的正解是交人，不是静默终止）。
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
from pathlib import Path

# ---------------------------------------------------------------------------
# 契约常量
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_MAX_ATTEMPTS = 31     # 达到上限：交人（06:149-150「不允许再试一次」）
EXIT_DUP_FINGERPRINT = 32  # 同一指纹重复出现（D25）
EXIT_ENTRY_NOT_UNIQUE = 33 # 写前校验失败 / 回读不符
EXIT_USAGE = 64            # 与其它模块一致：用法错误不用 2（2 在 verify_case 里是 G2）

DEFAULT_MAX_ATTEMPTS = 3

#: 定位规则表 —— **只有这 4 条**（3 条正则 + 1 条兜底）。不许扩：
#: 新增正则等于新增一种「猜法」，而每种猜法都需要自己的实测样本与判据。
RE_KEYWORD_UNDEFINED = re.compile(
    r'keyword\s+(\w+)\s+is\s+undefined\s+in\s+dictionary\s+"([^"]+)"'
)
RE_PATCHFIELD_MISSING = re.compile(r"Cannot find patchField entry for (\w+)")
# OpenFOAM 两种写法都有，实测：
#   大写  Cannot find file "points" in directory "polyMesh" in times "0" down to constant
#   小写  cannot find file "<abs>/system/fvSolution"
# 大小写敏感会漏掉后者，退化成「不匹配任何规则」——结论仍是 declined（正确），
# 但 reason 里丢掉了文件路径，违反 D24「declined 必须带定位信息」。
RE_MISSING_FILE = re.compile(r'cannot find file "([^"]+)"', re.IGNORECASE)

#: FOAM 字典里一个 entry 的行的形态：可选缩进 + 关键字 + 空白/{/;/行尾
#: （`endTime 10;`、`PIMPLE\n{`、`movingWall {` 都算命中；注释行不算）
_ENTRY_LINE = r"^\s*{name}(?=[\s{{;]|$)"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


class UsageError(Exception):
    """用法错误（退 64）。故意与「判定失败」分家：那是本模块的结论，这是调用方调错了。"""


def fatal_first_line(text: str) -> str:
    """日志里的 FATAL 首行（D25 指纹的第一个成分）。

    优先取 `--> FOAM FATAL ...` 那行；没有就退到第一个含 FATAL 的行；再没有就取第一个
    非空行。都空 → 空串（指纹仍可算，只是信息量低，此时通常已经被 declined）。
    """
    lines = text.splitlines()
    for line in lines:
        if line.lstrip().startswith("-->") and "FATAL" in line:
            return line.strip()
    for line in lines:
        if "FATAL" in line:
            return line.strip()
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


#: 指纹取错误正文的前 N 个非空行（跳过 `-->` 与分隔线）。见 D25（2026-10-28 修订）。
FINGERPRINT_LINES = 5


def error_signature(text: str) -> str:
    """从日志里取「错误的稳定特征串」＝`-->` 之后的前 N 个非空行。

    **为什么不用 FATAL 首行**：D25 原写「FATAL 首行 + file:entry」，但 OpenFOAM 的
    FATAL 首行几乎恒为 `--> FOAM FATAL ERROR:` / `--> FOAM FATAL IO ERROR:`，
    而定位不到时 `file:entry` 为空 → 所有「不可定位」的错误塌缩成同一个指纹。
    实测 `solvers table is empty` 与 `cannot find file ".../system/fvSolution"`
    都给出 `b10e79556e8a0b5d`，于是去重守卫把「另一个错误」当成「同一个」拒绝重试——
    守卫的作用整个反过来。

    跳过 `-->` 行本身与纯分隔线（`/*----*`），因为它们是每份日志都有的样板。
    """
    lines: list[str] = []
    seen_marker = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("/*") or line.startswith("\\*") or line.startswith("/*-"):
            continue
        if line.startswith("-->"):
            seen_marker = True
            continue          # 样板行本身不进特征串
        if not seen_marker:
            continue          # 还没到 FATAL 标记，前面是求解读屏输出
        lines.append(" ".join(line.split()))   # 压掉连续空白，跨 shell 稳定
        if len(lines) >= FINGERPRINT_LINES:
            break
    if not lines:
        # 没有 FATAL 标记：退回用整段日志的前 N 行（不返回空串，否则所有无标记日志同指纹）
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if line:
                lines.append(line)
            if len(lines) >= FINGERPRINT_LINES:
                break
    return "\n".join(lines)


def fingerprint_of(first_line: str, changes: list[dict], text: str = "") -> str:
    """D25（修订）：`sha256(错误特征串 + "\n" + "file:entry")[:16]`。

    参数 `text` 是整份日志；给了就用 `error_signature(text)` 当特征串，
    没给则退回 `first_line`（兼容旧调用点，但那条路径会产生指纹塌缩——
    所以所有真实调用点都必须传 `text`）。
    """
    signature = error_signature(text) if text else first_line
    locator = f'{changes[0]["file"]}:{changes[0]["entry"]}' if changes else ""
    return hashlib.sha256(f"{signature}\n{locator}".encode("utf-8")).hexdigest()[:16]


def fingerprint_for_apply(changes: list[dict]) -> str:
    """apply 模式的指纹：`sha256("apply\\n" + json.dumps(changes, sort_keys=True))[:16]`。"""
    blob = json.dumps(changes, sort_keys=True)
    return hashlib.sha256(f"apply\n{blob}".encode("utf-8")).hexdigest()[:16]


def _rel_to_case(raw: str, case_dir: Path) -> str | None:
    """把 FATAL 里的字典路径转成相对 case 根的路径；不在 case 内 → None（不猜）。"""
    p = Path(raw)
    if not p.is_absolute():
        p = case_dir / raw
    try:
        return p.resolve().relative_to(case_dir.resolve()).as_posix()
    except ValueError:
        return None


def _count_entry(dict_file: Path, entry: str) -> int:
    """entry 在字典里直接命中的行数（注释行不算）。

    这是「恰好 1 次」这条硬要求的实现：`foamDictionary -set` 对 0 次会**新增**并退 0，
    对 >=2 次只改第一处，两种都不是我们想要的。
    """
    pattern = re.compile(_ENTRY_LINE.format(name=re.escape(entry)))
    count = 0
    text = dict_file.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("//", "/*", "#")):
            continue
        if pattern.match(line):
            count += 1
    return count


#: 量纲块：OpenFOAM 里既可能是前置的 `[0 0 1 0 0 0 0] 0.02`，也可能是后置的
#: `1e-05 [ m^2 / s]`（`foamDictionary -set` 写带量纲的值时后者的形态）。
_DIM_RE = re.compile(r"\[[^\]]*\]")


def _norm_scalar(text: str) -> str:
    """剥掉量纲块，只留数值部分。

    **为什么要把后置量纲也剥掉**（2026-10-29 集成实测的 bug）：原实现只处理前置量纲，
    于是用户按最自然的写法 `-set "1e-5 [m^2/s]"` 时，回读到的是 OpenFOAM 规范化后的
    `1e-05 [ m^2 / s]` —— 逐字比对必失败，`apply` 退 33 并回滚。

    代价说清楚：剥掉量纲后，**量纲本身不再参与比对**。这是刻意的——OpenFOAM 会把
    `m^2/s` 规范化成 SI 基量纲 `[0 2 -1 0 0 0 0]`，按文本比量纲只会产生假失败
    （本 bug 就是这么来的）。量纲写错的真实后果是求解器报量纲不一致，由 G3 抓，
    不需要在回读这一步用文本比对来兜。
    """
    s = _DIM_RE.sub(" ", text.strip())
    return s.strip()


def _values_equal(want: str, got: str) -> bool:
    """回读比对：逐字相同或数值相等（`0.02` vs `2e-02` 不该判失败）。"""
    want_n, got_n = _norm_scalar(want), _norm_scalar(got)
    if want_n == got_n:
        return True
    try:
        w, g = float(want_n), float(got_n)
    except ValueError:
        return False
    return abs(w - g) <= 1e-12 * max(1.0, abs(w))


def _foam_dictionary() -> str:
    exe = shutil.which("foamDictionary")
    if not exe:
        # 路径按安装位置推导，不写死前缀（P1 可移植性解耦）；缺省值 = 本机默认安装前缀。
        bash_rc = f"{os.environ.get('WM_PROJECT_DIR', '/opt/openfoam13')}/etc/bashrc"
        raise UsageError(f"PATH 里没有 foamDictionary：先 `source {bash_rc}` 再调本脚本")
    return exe


# ---------------------------------------------------------------------------
# 定位（locate）
# ---------------------------------------------------------------------------


def locate(text: str, case_dir: Path) -> tuple[bool, list[dict], str | None]:
    """按 4 条规则定位。返回 (declined, changes, reason)。

    只有规则 1（关键字 undefined）能产出 changes，且 `new_value` 恒为 None——
    「该设成什么值」不是本模块能决定的（D23）。规则 2/3 是结构修复（加 dict 块 / 缺整个文件），
    `{file, entry, new_value}` 表达不了，故 declined（D24）。其余一律 declined 且**不猜**。
    """
    m = RE_KEYWORD_UNDEFINED.search(text)
    if m:
        entry, raw_path = m.group(1), m.group(2)
        rel = _rel_to_case(raw_path, case_dir)
        if rel is None:
            return True, [], (
                f'定位规则 1 命中（entry={entry}），但字典 "{raw_path}" 不在 case 目录 '
                f"{case_dir} 内：跨 case 的修复不归本模块，不猜路径"
            )
        if not (case_dir / rel).is_file():
            return True, [], (
                f'定位规则 1 命中（entry={entry}），但字典 "{rel}" 在 case 内不存在：'
                "缺整个文件是结构修复，不是改一个 entry 能解决的"
            )
        return False, [{"file": rel, "entry": entry, "new_value": None}], None

    m = RE_PATCHFIELD_MISSING.search(text)
    if m:
        return True, [], (
            f"结构修复：缺 patchField 条目 {m.group(1)}，需要在 0/ 的边界字段里补一个 patch 的"
            "BC 块（D24：{file, entry, new_value} 表达不了「加一段 dict」）"
        )

    m = RE_MISSING_FILE.search(text)
    if m:
        return True, [], (
            f'结构修复：缺文件 "{m.group(1)}"，需要从 tutorial 派生/补齐整份字典'
            "（D24：不是改一个 entry 能解决的）"
        )

    return True, [], "日志不匹配 4 条定位规则中的任何一条：无法定位到 file+entry，不猜（D23）"


# ---------------------------------------------------------------------------
# 指纹台账（D25 的可落盘部分）
# ---------------------------------------------------------------------------


def _ledger_path(run_dir: Path) -> Path:
    return run_dir / "fingerprints.txt"


def seen_fingerprints(run_dir: Path) -> set[str]:
    """扫 `attempt_*/fingerprint.txt`（D25 原文）**以及**台账（locate 模式的落点）。"""
    seen: set[str] = set()
    if run_dir.is_dir():
        for sub in sorted(run_dir.glob("attempt_*")):
            fp_file = sub / "fingerprint.txt"
            if fp_file.is_file():
                value = fp_file.read_text(encoding="utf-8", errors="replace").strip()
                if value:
                    seen.add(value)
    ledger = _ledger_path(run_dir)
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
            value = line.strip()
            if value:
                seen.add(value)
    return seen


def record_fingerprint(run_dir: Path, fingerprint: str) -> None:
    """把指纹追加进台账（去重；失败不致命——台账只是加速器，指纹文件才是权威记录）。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = _ledger_path(run_dir)
    existing = set()
    if ledger.is_file():
        existing = {
            line.strip()
            for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        }
    if fingerprint in existing:
        return
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(fingerprint + "\n")


# ---------------------------------------------------------------------------
# 写回（apply）
# ---------------------------------------------------------------------------


def parse_apply_payload(raw: str) -> list[dict]:
    """校验 `--apply` 的形状：必须是 [{file,entry,new_value}, ...] 且字段非空。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--apply 不是合法 JSON: {exc}") from exc

    if not isinstance(data, list) or not data:
        raise UsageError('--apply 必须是非空 JSON 数组，形如 [{"file":..,"entry":..,"new_value":..}]')

    changes: list[dict] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise UsageError(f"--apply[{i}] 必须是对象，实际 {type(item).__name__}")
        missing = [k for k in ("file", "entry", "new_value") if k not in item]
        if missing:
            raise UsageError(f"--apply[{i}] 缺字段 {missing}")
        file_rel, entry, value = item["file"], item["entry"], item["new_value"]
        if not isinstance(file_rel, str) or not file_rel.strip():
            raise UsageError(f"--apply[{i}].file 必须是非空字符串")
        if not isinstance(entry, str) or not entry.strip():
            raise UsageError(f"--apply[{i}].entry 必须是非空字符串")
        if value is None:
            raise UsageError(
                f"--apply[{i}].new_value 为 null：apply 模式要求调用方给出确定的值"
                "（locate 模式只报位置，不写盘）"
            )
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise UsageError(f"--apply[{i}].new_value 必须是标量（str/int/float）")
        changes.append({"file": file_rel.strip(), "entry": entry.strip(), "new_value": str(value)})
    return changes


def _safe_rel_path(case_dir: Path, file_rel: str) -> Path:
    """file 必须是 case 内的相对路径；绝对路径或越界（..）→ 64。"""
    p = Path(file_rel)
    if p.is_absolute():
        raise UsageError(f"--apply 的 file 必须是相对 case 根的路径，不接受绝对路径: {file_rel}")
    target = (case_dir / p).resolve()
    try:
        target.relative_to(case_dir.resolve())
    except ValueError as exc:
        raise UsageError(f"--apply 的 file 越出 case 目录: {file_rel}") from exc
    return target


def _allowed_globs(args_allowed: str | None, case_dir: Path) -> list[str]:
    """`--allowed` 优先；否则读 case.meta.allowed_files（case 内或 case 的父目录，两处都找）。

    空列表 = 不限制（不是「全禁」）：老 case 没有 case.meta 时把自己锁死只会让模块失效。
    """
    if args_allowed:
        return [g.strip() for g in args_allowed.split(",") if g.strip()]
    for meta in (case_dir / "case.meta", case_dir.parent / "case.meta"):
        if meta.is_file():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            globs = data.get("allowed_files") or []
            if isinstance(globs, list):
                return [str(g).strip() for g in globs if str(g).strip()]
    return []


def _is_allowed(rel: str, globs: list[str]) -> bool:
    if not globs:
        return True
    return any(fnmatch.fnmatch(rel, g) for g in globs)


def validate_changes(case_dir: Path, changes: list[dict]) -> list[str]:
    """写前校验：每个 file 存在、每个 entry 恰好命中 1 次。返回错误说明（空 = 通过）。

    **先全部校验，再动手写**：这样「拒绝」不会留下半改的字典（F5 的 sha256 不变）。
    """
    problems: list[str] = []
    for change in changes:
        rel, entry = change["file"], change["entry"]
        target = (case_dir / rel)
        if not target.is_file():
            problems.append(f"{rel} 不存在（不是 case 内的字典文件）")
            continue
        hits = _count_entry(target, entry)
        if hits != 1:
            problems.append(
                f"{rel} 里 entry `{entry}` 命中 {hits} 次（要求恰好 1 次）"
            )
    return problems


def _backup_case(case_dir: Path, attempt: int) -> Path:
    """`cp -a <case> <run>/attempt_<n>/`，返回备份目录。失败抛 UsageError（不写字典）。"""
    run_dir = case_dir.parent
    target = run_dir / f"attempt_{attempt}"
    if target.exists():
        raise UsageError(f"备份目标已存在，拒绝覆盖: {target}")
    run_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        ["cp", "-a", str(case_dir), str(target)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(target, ignore_errors=True)  # 半份备份比没有备份更糟（会被当成可用备份）
        raise UsageError(f"备份失败（未写任何字典）: cp -a 退 {proc.returncode}: {proc.stderr.strip()[:200]}")
    return target


def _set_entry(exe: str, dict_file: Path, entry: str, value: str) -> subprocess.CompletedProcess:
    """`foamDictionary <file> -entry <e> -set <v>` —— 字典文件是**位置参数**（见模块 docstring）。"""
    return subprocess.run(
        [exe, str(dict_file), "-entry", entry, "-set", value],
        capture_output=True,
        text=True,
    )


def _read_entry(exe: str, dict_file: Path, entry: str) -> str:
    """回读：`-value` 只打值；读不到（entry 不在）→ 空串，由调用方判为不符。"""
    proc = subprocess.run(
        [exe, str(dict_file), "-entry", entry, "-value"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _payload(
    changes: list[dict],
    written: bool = False,
    backup_dir: str | None = None,
    declined: bool = False,
    reason: str | None = None,
    fingerprint: str | None = None,
) -> dict:
    """stdout 的唯一形状（字段顺序固定，见模块 docstring）。"""
    return {
        "changes": changes,
        "written": written,
        "backup_dir": backup_dir,
        "declined": declined,
        "reason": reason,
        "fingerprint": fingerprint,
    }


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return code


class _UsageParser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64（与 parse_requirement.py 同一套）。"""

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _UsageParser(
        prog="fix_case.py",
        description=(
            "失败日志 → 定位 {file, entry}（locate）；或按 --apply 的 changes 备份后写回（apply）。"
            "本模块不重跑求解。stdout 一行 JSON。"
        ),
    )
    parser.add_argument("--case", required=True, help="case 目录（内含 system/controlDict）")
    parser.add_argument("--error-log", default=None, help="locate 模式：失败日志文件")
    parser.add_argument("--apply", default=None, help='apply 模式：JSON 数组字符串')
    parser.add_argument("--attempt", required=True, type=int, help="第几次尝试（1-based）")
    parser.add_argument(
        "--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS, help="尝试上限（默认 3）"
    )
    parser.add_argument(
        "--allowed",
        default=None,
        help="逗号分隔的 glob 白名单（缺省读 case.meta.allowed_files；空 = 不限制）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只算不写（照样校验）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        # ---- 模式互斥（两模式同时给 / 都不给 → 64）
        if (args.error_log is None) == (args.apply is None):
            raise UsageError("必须且只能给 --error-log（locate）或 --apply（apply）之一")

        case_dir = Path(args.case).resolve()
        if not case_dir.is_dir() or not (case_dir / "system" / "controlDict").is_file():
            raise UsageError(
                f"--case 不是 case 目录（需存在 <case>/system/controlDict）: {args.case}"
            )
        if args.attempt < 1:
            raise UsageError(f"--attempt 从 1 开始（收到 {args.attempt}）")
        if args.max_attempts < 1:
            raise UsageError(f"--max-attempts 至少为 1（收到 {args.max_attempts}）")
        if args.error_log is not None and not Path(args.error_log).is_file():
            raise UsageError(f"--error-log 不存在: {args.error_log}")

        allowed = _allowed_globs(args.allowed, case_dir)
        run_dir = case_dir.parent

        # ---- 轮数上限：到顶就交人，不许「再试一次」（06:149-150）
        if args.attempt > args.max_attempts:
            return _emit(
                _payload(
                    [],
                    reason=(
                        f"attempt {args.attempt} 已超过 max-attempts {args.max_attempts}："
                        "不再重试，交人处理"
                    ),
                ),
                EXIT_MAX_ATTEMPTS,
            )

        if args.error_log is not None:
            return _run_locate(args, case_dir, run_dir, allowed)
        return _run_apply(args, case_dir, run_dir, allowed)

    except UsageError as exc:
        print(f"fix_case.py: error: {exc}\n", file=sys.stderr)
        return EXIT_USAGE


def _run_locate(args, case_dir: Path, run_dir: Path, allowed: list[str]) -> int:
    """locate 模式：定位 → （可选）白名单 → 指纹去重。**不写任何字典**。"""
    text = Path(args.error_log).read_text(encoding="utf-8", errors="replace")
    first_line = fatal_first_line(text)
    declined, changes, reason = locate(text, case_dir)

    if not declined and changes and not _is_allowed(changes[0]["file"], allowed):
        blocked = changes[0]["file"]
        return _emit(
            _payload(
                [],
                declined=True,
                reason=(
                    f"定位到 {blocked}，但不在 allowed 白名单内（{','.join(allowed)}）："
                    "按 G5 不越界改文件"
                ),
                fingerprint=fingerprint_of(first_line, [], text),
            ),
            EXIT_OK,
        )

    fingerprint = fingerprint_of(first_line, changes, text)

    if not declined:
        if fingerprint in seen_fingerprints(run_dir):
            return _emit(
                _payload(
                    [],
                    reason="同一失败指纹已出现过（本 attempt 之前已有记录）：终止重试（D25）",
                    fingerprint=fingerprint,
                ),
                EXIT_DUP_FINGERPRINT,
            )
        if not args.dry_run:
            record_fingerprint(run_dir, fingerprint)

    return _emit(_payload(changes, declined=declined, reason=reason, fingerprint=fingerprint), EXIT_OK)


def _run_apply(args, case_dir: Path, run_dir: Path, allowed: list[str]) -> int:
    """apply 模式：校验 → 去重 → 备份 → 写回 → 回读（任一不符即回滚并退 33）。"""
    from_cli_changes = parse_apply_payload(args.apply)
    fingerprint = fingerprint_for_apply(from_cli_changes)

    # 白名单（G5）：越界就不动，declined 报原因
    outside = [c["file"] for c in from_cli_changes if not _is_allowed(c["file"], allowed)]
    if outside:
        return _emit(
            _payload(
                [],
                declined=True,
                reason=(
                    f"这些文件不在 allowed 白名单内（{','.join(allowed)}），按 G5 拒绝改动: "
                    + ", ".join(outside)
                ),
                fingerprint=fingerprint,
            ),
            EXIT_OK,
        )

    # 形状/路径（64）——绝对路径与 `..` 越界都算调用方调错
    targets: list[Path] = []
    for change in from_cli_changes:
        target = _safe_rel_path(case_dir, change["file"])
        if not target.is_file():
            raise UsageError(f"--apply 指向的字典不存在: {change['file']}")
        targets.append(target)

    if fingerprint in seen_fingerprints(run_dir):
        return _emit(
            _payload(
                [],
                reason="同一 apply 指纹已出现过（相同 changes 重复提交）：终止重试（D25）",
                fingerprint=fingerprint,
            ),
            EXIT_DUP_FINGERPRINT,
        )

    # 写前校验：所有 entry 都恰好命中 1 次（**先全查，再动手**）
    problems = validate_changes(case_dir, from_cli_changes)
    if problems:
        return _emit(
            _payload([], reason="写前校验未通过（字典未改动）: " + "; ".join(problems),
                     fingerprint=fingerprint),
            EXIT_ENTRY_NOT_UNIQUE,
        )

    if args.dry_run:
        return _emit(
            _payload(from_cli_changes, fingerprint=fingerprint),
            EXIT_OK,
        )

    exe = _foam_dictionary()
    backup_dir = _backup_case(case_dir, args.attempt)

    for change, target in zip(from_cli_changes, targets):
        proc = _set_entry(exe, target, change["entry"], change["new_value"])
        got = _read_entry(exe, target, change["entry"])
        if not _values_equal(change["new_value"], got):
            # 回读不符 → 用备份把这一份字典还原成改前字节，再报 33
            shutil.copy2(backup_dir / change["file"], target)
            return _emit(
                _payload(
                    [],
                    backup_dir=str(backup_dir),
                    reason=(
                        f"回读不符: {change['file']} 的 `{change['entry']}` 期望 "
                        f"{change['new_value']!r}、回读到 {got!r}"
                        f"（foamDictionary 退 {proc.returncode}，stderr={proc.stderr.strip()[:160]!r}）；"
                        f"已用 {backup_dir} 回滚该文件"
                    ),
                    fingerprint=fingerprint,
                ),
                EXIT_ENTRY_NOT_UNIQUE,
            )

    # 成功的唯一落盘记录：备份目录里的指纹 + 台账
    (backup_dir / "fingerprint.txt").write_text(fingerprint + "\n", encoding="utf-8")
    record_fingerprint(run_dir, fingerprint)

    return _emit(
        _payload(from_cli_changes, written=True, backup_dir=str(backup_dir), fingerprint=fingerprint),
        EXIT_OK,
    )


if __name__ == "__main__":
    sys.exit(main())
