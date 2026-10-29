#!/usr/bin/env python3
"""发布文档的契约检查：四条判据，一个退出码。

判据（任一不过 → 退 41，并逐条列出违规）：

  1. **引用存在性**：`release/*.md` 里出现的 `scripts/<名>.<扩展>` 与
     `release/<名>.md` 必须在**仓库根**（= `--dir` 的父目录）下真实存在。
     文档里写了不存在的脚本，等于给陌生用户指了一条死路。
  2. **退出码集合**：文档里所有 `退 <N>` / `退出码 <N>` 形态的数字必须落在
     `KNOWN_EXIT_CODES` 内。集合外的新数字一般意味着"文档承诺了一个不存在的码"。
  3. **frontmatter**：`SKILL.md`（文件名硬定）必须有 YAML frontmatter，含 `name` 与
     `description`，且 `len(description) <= 1024`（宿主加载 skill 的字段长度上限）。
  4. **自称**：`SKILL.md` 全文不得出现「智能体」，且**正文**（frontmatter 之后）必须出现
     `harness`。对外措辞是验收标准的一部分，不能靠人记住。

退出码：0 全过 / 41 文档契约违规 / 64 用法错误或前置不满足（未知参数、`--dir` 不存在）。

为什么 41 不用 40：40 已被内部契约检查占用（它判的是另一件事：判据文件自身的导入与结构），
两者处置不同——40 是我们的工具坏了，41 是文档与实现不一致，后者改文档就能好。
为什么 41 不用 1：1 在门禁里有业务含义（G1 结构门失败），混用会让调用方无法区分
「我文档写错了」与「这个 case 结构不对」，两者处置相反。

用法：
  python3 scripts/check_release_docs.py                 # 检查 ./release
  python3 scripts/check_release_docs.py --dir release    # 同上，显式
  python3 scripts/check_release_docs.py --dir /tmp/x/release

  `--dir` 的**父目录**被当作仓库根：判据 1 的 `scripts/xxx.sh` 就去 `<父目录>/scripts/xxx.sh`
  找。测试就是这么用的（把 release/ 与 scripts/ 复制到同一个临时目录下）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EX_OK = 0
EX_VIOLATION = 41  # 文档契约违规
EX_USAGE = 64      # 用法错误（不给 2：2 是 G2 网格门失败）

#: 文档可以提到的全部退出码。新增业务码时必须同时改这里，否则文档写不出新码——
#: 这是刻意的摩擦：先定契约，再改文档。
KNOWN_EXIT_CODES = frozenset({
    0, 1, 2, 3, 4, 5,          # 门结果（0 全过 / 1–5 第一个失败的门）
    10, 11, 12, 13,            # 需求缺项 / 检索无命中 / 派生源不合法 / 目标已存在
    14, 15,                    # 网格转换：输入或自检不合格 / 输出目录非空且未 --force
    20, 21, 22, 23,            # 求解失败 / 超时 / 环境缺失 / 无可用网格
    31, 32, 33,                # 到上限 / 指纹重复 / 写前校验或回读不符
    40, 41,                    # 内部契约检查 / 本文档契约检查（维护侧）
    50, 51,                    # 前置检查：环境不全 / 版本不符
    60,                        # 打包白名单违规（维护侧）
    70, 71,                    # 批量运行：有失败 / 整批中止
    64,                        # 用法错误（全部脚本统一）
})

SKILL_NAME = "SKILL.md"
DESCRIPTION_MAX = 1024

#: `scripts/<名>.<扩展>`。允许 `$HARNESS/scripts/x.sh` 这种前缀（只取 `scripts/` 之后那段）。
SCRIPT_REF = re.compile(r"scripts/([A-Za-z0-9_.\-]+\.(?:sh|py))")
#: `release/<名>.md`
RELEASE_REF = re.compile(r"release/([A-Za-z0-9_.\-]+\.md)")
#: 裸文件名形式的兄弟文档引用（`QUICKSTART.md`、`SCOPE.md`、`SKILL.md`）。
#: **这是发布包里的真实形态**：包内三份文档与 `scripts/` 同级，没有 `release/` 这一层，
#: 所以文档里必须写裸文件名。若只查 `release/<名>.md`，改了引用写法就等于让判据 1 空转
#: （实测：从 `release/X.md` 改成 `X.md` 后，检查器的引用计数从 32 掉到 26 而仍然全绿）。
SIBLING_REF = re.compile(r"(?<![A-Za-z0-9_.\-/])(SKILL\.md|QUICKSTART\.md|SCOPE\.md)(?![A-Za-z0-9_.\-])")
#: `退 41` / `退 \`41\`` / `退出码 41`（允许中间有空白，也允许数字被反引号包住）。
#: 文档里大量数字为了可读性加了反引号，漏掉这些等于让判据 2 形同虚设。
EXIT_MENTION = re.compile(r"(?:退出码|退)\s*`?\s*([0-9]+)")

FORBIDDEN_WORD = "智能体"
REQUIRED_WORD = "harness"


class _Parser(argparse.ArgumentParser):
    """argparse 默认的用法错误退 2，这里改成 64（全项目统一约定）。"""

    def error(self, message: str):  # noqa: D401 - argparse 挂钩
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: 用法错误: {message}\n")
        raise SystemExit(EX_USAGE)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(
        prog="check_release_docs.py",
        description="检查 release/*.md 的引用、退出码集合与 SKILL.md 的 frontmatter/自称。",
        add_help=True,
    )
    parser.add_argument(
        "--dir",
        default="release",
        help="要检查的文档目录（其父目录当作仓库根，缺省 release）",
    )
    return parser.parse_args(argv)


def split_frontmatter(text: str) -> tuple[list[str] | None, str]:
    """返回 (frontmatter 行列表, 正文)；没有 frontmatter 时返回 (None, 全文)。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return lines[1:i], "\n".join(lines[i + 1:])
    return None, text


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def frontmatter_fields(fm_lines: list[str]) -> dict[str, str]:
    """极简 YAML 顶层字段解析：`key: value`，支持 `|` / `>` 折叠块的缩进续行。"""
    fields: dict[str, str] = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        m = re.match(r"^([A-Za-z0-9_\-]+):[ \t]*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block: list[str] = []
            i += 1
            while i < len(fm_lines) and (fm_lines[i].startswith((" ", "\t")) or not fm_lines[i].strip()):
                block.append(fm_lines[i].strip())
                i += 1
            fields[key] = " ".join(part for part in block if part)
            continue
        fields[key] = _unquote(value)
        i += 1
    return fields


def check_references(doc_dir: Path, root: Path) -> tuple[int, list[str]]:
    """判据 1：文档提到的脚本/文档路径必须真实存在（相对仓库根）。"""
    violations: list[str] = []
    refs = 0
    for md in sorted(doc_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, subdir, what in (
                (SCRIPT_REF, "scripts", "脚本"),
                (RELEASE_REF, "release", "文档"),
            ):
                for m in pattern.finditer(line):
                    name = m.group(1)
                    refs += 1
                    target = root / subdir / name
                    if not target.is_file():
                        violations.append(
                            f"{md.name}:{lineno}: 引用了不存在的{what} `{subdir}/{name}`"
                            f"（按仓库根 {root} 找）"
                        )
            # 裸文件名的兄弟文档引用：必须在**本目录**里存在（发布包内三份文档同级）
            for m in SIBLING_REF.finditer(line):
                name = m.group(1)
                refs += 1
                if not (doc_dir / name).is_file():
                    violations.append(
                        f"{md.name}:{lineno}: 引用了不存在的兄弟文档 `{name}`"
                        f"（按文档目录 {doc_dir} 找）"
                    )
    return refs, violations


def check_exit_codes(doc_dir: Path) -> tuple[int, list[str]]:
    """判据 2：`退 N` / `退出码 N` 的数字必须在已知码集合内。"""
    violations: list[str] = []
    seen: set[int] = set()
    for md in sorted(doc_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in EXIT_MENTION.finditer(line):
                code = int(m.group(1))
                seen.add(code)
                if code not in KNOWN_EXIT_CODES:
                    violations.append(
                        f"{md.name}:{lineno}: 退出码 `{code}` 不在已知集合内"
                        f"（{m.group(0).strip()}）"
                    )
    return len(seen), violations


def check_frontmatter(skill: Path) -> tuple[bool, list[str]]:
    """判据 3：frontmatter 有 name 与 description，且 description 不超过 1024 字符。"""
    if not skill.is_file():
        return False, [f"缺少入口文档 `{skill.name}`（文件名硬定，必须存在）"]
    text = skill.read_text(encoding="utf-8", errors="replace")
    fm_lines, _ = split_frontmatter(text)
    if fm_lines is None:
        return False, [f"{skill.name}: 没有 YAML frontmatter（首行必须是 `---`，且要有闭合 `---`）"]

    fields = frontmatter_fields(fm_lines)
    violations: list[str] = []
    name = fields.get("name", "").strip()
    description = fields.get("description", "").strip()

    if not name:
        violations.append(f"{skill.name}: frontmatter 缺 `name` 或为空")
    if not description:
        violations.append(f"{skill.name}: frontmatter 缺 `description` 或为空")
    elif len(description) > DESCRIPTION_MAX:
        violations.append(
            f"{skill.name}: description 长度 {len(description)} > {DESCRIPTION_MAX}"
            f"（超出 {len(description) - DESCRIPTION_MAX} 字符）"
        )
    return not violations, violations


def check_self_naming(skill: Path) -> tuple[bool, list[str]]:
    """判据 4：SKILL.md 不得自称「智能体」，正文必须出现 harness。"""
    if not skill.is_file():
        return False, [f"缺少入口文档 `{skill.name}`（文件名硬定，必须存在）"]
    text = skill.read_text(encoding="utf-8", errors="replace")
    _, body = split_frontmatter(text)

    violations: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FORBIDDEN_WORD in line:
            violations.append(f"{skill.name}:{lineno}: 出现禁用自称「{FORBIDDEN_WORD}」")
    if REQUIRED_WORD not in body.lower():
        violations.append(
            f"{skill.name}: 正文里没有 `{REQUIRED_WORD}`（对外自称必须是 harness，不能省）"
        )
    return not violations, violations


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    doc_dir = Path(args.dir)
    if not doc_dir.is_dir():
        sys.stderr.write(f"check_release_docs.py: 用法错误: --dir 不是目录: {args.dir}\n")
        sys.stderr.write("用法: python3 scripts/check_release_docs.py [--dir release]\n")
        return EX_USAGE

    doc_dir = doc_dir.resolve()
    root = doc_dir.parent
    skill = doc_dir / SKILL_NAME

    all_violations: list[str] = []

    ref_count, ref_violations = check_references(doc_dir, root)
    all_violations.extend(ref_violations)
    print(f"[1/4] 引用存在性  {ref_count} 处引用，违规 {len(ref_violations)} 处", flush=True)

    code_count, code_violations = check_exit_codes(doc_dir)
    all_violations.extend(code_violations)
    print(f"[2/4] 退出码集合  {code_count} 种码，违规 {len(code_violations)} 处", flush=True)

    fm_ok, fm_violations = check_frontmatter(skill)
    all_violations.extend(fm_violations)
    print(f"[3/4] frontmatter   {'OK' if fm_ok else f'违规 {len(fm_violations)} 处'}", flush=True)

    name_ok, name_violations = check_self_naming(skill)
    all_violations.extend(name_violations)
    print(f"[4/4] 自称检查      {'OK' if name_ok else f'违规 {len(name_violations)} 处'}", flush=True)

    if all_violations:
        print("", file=sys.stderr)
        print(f"文档契约违规 {len(all_violations)} 处：", file=sys.stderr)
        for item in all_violations:
            print(f"  - {item}", file=sys.stderr)
        print("下一步：改文档（不是改检查器）；若检查器本身判错，请给出反例。", file=sys.stderr)
        return EX_VIOLATION

    print(f"文档契约 4/4 通过（{doc_dir}）")
    return EX_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
