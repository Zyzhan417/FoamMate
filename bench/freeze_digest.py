#!/usr/bin/env python3
"""bench/freeze_digest.py — 计算预注册里「被冻结章节」的指纹。

为什么不能直接给整个 preregistration.md 做 sha256：
  §10（每臂预测）与 §14（变异记录）在冻结之后**本来就该继续增长**——前者等 ours 实现后补填，
  后者每加一次变异就追加一行。整文件哈希会把"合法的追加"和"非法的改判据"一起判红，
  于是门禁变成噪音，人就开始 `--no-verify`。

所以要冻结的是**章节切片**：
  §1–§9   （标 1 测量路径 … 到 ## 10 之前）
  §13     （未定项；它的内容决定哪些列不得进结论）
  §冻结记录（含指纹本身，防止有人把旧指纹改成新指纹来自洽）

用法：
  python3 bench/freeze_digest.py            # 打印当前指纹
  python3 bench/freeze_digest.py --record   # 打印用于写入冻结记录的整行
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

PREREG = Path(__file__).resolve().parent / "preregistration.md"

# (起始标记, 结束标记)；结束标记为 None 表示到下一个 "## " 二级标题为止
SLICES = [
    (r"^## 1 测量路径", r"^## 10 每臂预测"),
    (r"^## 13 未定项", r"^## 14 变异记录"),
    (r"^## 冻结记录", r"^### 变更规则"),
]


def slice_text(text: str, start_pat: str, end_pat: str | None) -> str:
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(start_pat, ln):
            start = i
            break
    if start is None:
        raise SystemExit(f"找不到起始标记: {start_pat}")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(end_pat, lines[j]):
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def digest() -> tuple[str, list[tuple[str, int, int]]]:
    text = PREREG.read_text(encoding="utf-8")
    parts, meta = [], []
    for s, e in SLICES:
        body = slice_text(text, s, e)
        parts.append(body)
        meta.append((s.replace("^", "").replace("  ", " "), len(body.splitlines()), len(body.encode())))
    joined = "\n\x1e\n".join(parts)  # \x1e 作分隔，避免拼接歧义
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), meta


if __name__ == "__main__":
    d, meta = digest()
    for name, lines, nbytes in meta:
        print(f"  {name:<16} {lines:>4} 行  {nbytes:>6} 字节")
    if "--record" in sys.argv:
        print(f"冻结章节 sha：      {d}")
    else:
        print(d)
