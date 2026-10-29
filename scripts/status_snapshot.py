#!/usr/bin/env python3
"""scripts/status_snapshot.py — 生成 / 校验 STATUS.md 的「机器段」。

设计原则（为什么不是让 agent 手写状态文档）：
  手写的数字会腐坏，而且腐坏了没有任何东西会红。这里把**能量到的部分**全部机器生成，
  agent 只维护「NARRATIVE」段的判断性内容。这样"更新状态"= 跑一条命令（零判断），
  而"状态是否过期"可被门禁判定（G-R13-1）。

用法：
  python3 scripts/status_snapshot.py            # 打印机器段
  python3 scripts/status_snapshot.py --write    # 原地更新 STATUS.md 的机器段（保留 NARRATIVE）
  python3 scripts/status_snapshot.py --check    # 校验机器段是否与当前事实一致（门禁用）
退出码：0 一致 / 1 不一致或文件缺失 / 2 用法错误
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "STATUS.md"
BEGIN = "<!-- BEGIN MACHINE（本段由 scripts/status_snapshot.py 生成，勿手改） -->"
END = "<!-- END MACHINE -->"

# 参与快照的文档（事实来源；改动它们就应重跑 --write）
DOCS = ["AGENTS.md", "README.md", "bench/preregistration.md",
        "references/01-landscape.md", "references/02-architectures.md",
        "references/search-protocol.md", "bench/assert_lib.py",
        "bench/selftest_expect.py", "bench/freeze_digest.py",
        "scripts/verify_references.sh"]


def sh(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def line_bytes(p: Path) -> tuple[int, int]:
    if not p.is_file():
        return 0, 0
    b = p.read_bytes()
    return b.count(b"\n") + (0 if b.endswith(b"\n") or not b else 1), len(b)


def registry_stats() -> dict:
    f = ROOT / "references" / "registry.csv"
    if not f.is_file():
        return {"rows": 0, "full": 0, "docs_only": 0, "A": 0, "B": 0, "C": 0,
                "full_mb": 0, "sha256": "(缺)"}
    rows = list(csv.DictReader(open(f, encoding="utf-8")))
    return {
        "rows": len(rows),
        "full": sum(1 for r in rows if r["mode"] == "full"),
        "docs_only": sum(1 for r in rows if r["mode"] == "docs_only"),
        **{t: sum(1 for r in rows if r["tier"] == t) for t in "ABC"},
        "full_mb": sum(int(r["size_mb"]) for r in rows if r["mode"] == "full"),
        "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
    }


def tasks_stats() -> dict:
    d = ROOT / "bench" / "tasks"
    ys = sorted(d.glob("T*.yaml")) if d.is_dir() else []
    man = d / "FROZEN.sha256"
    ok = 0
    if man.is_file():
        _, out = sh(["sha256sum", "-c", str(man.relative_to(ROOT))], ROOT)
        ok = out.count(": OK")
    # 只数非注释行：清单头部有说明性注释，把注释算成"被校验的文件"会让 15/20 这种数字误导人
    ml = 0
    if man.is_file():
        ml = sum(1 for ln in man.read_text().splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#"))
    return {"n": len(ys), "manifest_lines": ml, "manifest_ok": ok}


def prereg_stats() -> dict:
    f = ROOT / "bench" / "preregistration.md"
    if not f.is_file():
        return {"state": "缺失", "digest_doc": "", "digest_now": ""}
    t = f.read_text(encoding="utf-8")
    m = re.search(r"^# .*预注册.*?(已冻结|草稿).*", t, re.M)
    doc = re.search(r"冻结章节 sha：\s+([0-9a-f]{64})", t)
    rc, out = sh([sys.executable, "bench/freeze_digest.py"])
    now = out.strip().splitlines()[-1] if rc == 0 and out.strip() else ""
    return {"state": "已冻结" if (m and "已冻结" in m.group(1)) else "未冻结",
            "digest_doc": doc.group(1) if doc else "",
            "digest_now": now}


def runs_stats() -> dict:
    r = ROOT / "bench" / "runs"
    files = [p for p in r.rglob("*") if p.is_file()] if r.is_dir() else []
    res = ROOT / "bench" / "results.csv"
    rows = 0
    if res.is_file():
        rows = max(0, len(res.read_text(encoding="utf-8").strip().splitlines()) - 1)
    return {"run_files": len(files), "result_rows": rows}


def compose() -> str:
    reg = registry_stats()
    tk = tasks_stats()
    pr = prereg_stats()
    rn = runs_stats()
    repos = ROOT / "references" / "repos"
    nrepos = len([d for d in repos.iterdir() if d.is_dir()]) if repos.is_dir() else 0

    dig_ok = "一致" if pr["digest_doc"] and pr["digest_doc"] == pr["digest_now"] else "不一致（或未冻结）"

    lines = [BEGIN,
             f"生成于：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {time.tzname[0]}",
             "",
             "## A 冻结状态",
             "",
             f"- 预注册：**{pr['state']}**；冻结章节指纹 {dig_ok}",
             f"  - 文档记录 `{(pr['digest_doc'] or '无')[:16]}…` / 现值 `{(pr['digest_now'] or '无')[:16]}…`",
             f"- 冻结清单：{tk['manifest_lines']} 个文件，`sha256sum -c` 通过 **{tk['manifest_ok']}/{tk['manifest_lines']}**",
             f"- 任务集：**{tk['n']}** 个 yaml",
             "",
             "## B 参考库",
             "",
             f"- `registry.csv`：{reg['rows']} 行 = {reg['full']} full + {reg['docs_only']} docs_only；"
             f"tier A={reg['A']} / B={reg['B']} / C={reg['C']}",
             f"- 已下载仓库 {nrepos} 个，实测合计 **{reg['full_mb']} MB**（单项目上限 100 MB，R10）",
             f"- registry sha256：`{reg['sha256'][:16]}…`",
             "",
             "## C 设计期禁跑状态（R12）",
             "",
             f"- `bench/runs/` 文件数：**{rn['run_files']}**（设计期必须 0）",
             f"- `bench/results.csv` 数据行：**{rn['result_rows']}**",
             "",
             "## D 文档规模",
             "",
             "| 文件 | 行 | 字节 |",
             "|---|---|---|",
             ]
    for rel in DOCS:
        n, b = line_bytes(ROOT / rel)
        if n or b:
            lines.append(f"| `{rel}` | {n} | {b} |")
    ag = ROOT / "AGENTS.md"
    ag_chars = len(ag.read_text(encoding="utf-8")) if ag.is_file() else 0
    pct = ag_chars / 20000 * 100
    # 关键：上限是 20000 **字符**，不是字节。CJK 一个字符 3 字节，按字节算会虚报约 3 倍
    # （第一版就是这么错的：17936 字节被读成 89.7%，实际 10226 字符 = 51.1%）。
    flag = ("⚠ 超过 20000 字符上限，会被 head+tail 截断（中间段落静默丢失）" if pct > 100
            else "⚠ 已超 90%，下一次扩充前先压缩叙述段" if pct > 90 else "OK")
    lines += ["",
              f"**AGENTS.md 注入上限占用：{ag_chars} 字符 / 20000 = {pct:.1f}% —— {flag}**",
              "（按字符计，不是字节：CJK 一字符 3 字节，按字节算会把占用虚报约 3 倍。）",
              END]
    return "\n".join(lines)


def read_status() -> str:
    return STATUS.read_text(encoding="utf-8") if STATUS.is_file() else ""


def write_section(block: str) -> None:
    cur = read_status()
    if BEGIN in cur and END in cur:
        pre = cur.split(BEGIN)[0]
        post = cur.split(END, 1)[1]
        new = pre + block + post
    else:
        new = ("# 项目状态\n\n"
               "> 本文件是给**新会话**（上下文清空 / 压缩之后）用的接续点。\n"
               "> 机器段由 `python3 scripts/status_snapshot.py --write` 生成；\n"
               "> 判断段（§NARRATIVE）由 agent 维护。校验：`bash scripts/verify_references.sh --frozen`。\n\n"
               + block + "\n\n"
               "<!-- BEGIN NARRATIVE（agent 维护：阶段 / 决策 / 下一步 / 已知缺口） -->\n"
               "（待填）\n"
               "<!-- END NARRATIVE -->\n")
    STATUS.write_text(new, encoding="utf-8")


def check() -> int:
    if not STATUS.is_file():
        print("STATUS.md 不存在")
        return 1
    cur = read_status()
    if BEGIN not in cur or END not in cur:
        print("STATUS.md 缺少机器段标记")
        return 1
    old = cur.split(BEGIN)[1].split(END)[0]
    new = compose().split(BEGIN)[1].split(END)[0]
    # 生成时间一定不同，比较时剔除
    strip = lambda s: "\n".join(ln for ln in s.splitlines() if not ln.startswith("生成于："))
    if strip(old).strip() == strip(new).strip():
        print("STATUS.md 机器段与当前事实一致")
        return 0
    # 逐行 diff，指出到底哪一行过期
    ol, nl = strip(old).strip().splitlines(), strip(new).strip().splitlines()
    diffs = [f"  现状: {a}\n  应为: {b}" for a, b in zip(ol, nl) if a != b]
    print(f"STATUS.md 机器段已过期（{len(diffs)} 行不一致）：")
    for d in diffs[:8]:
        print(d)
    print("修复：python3 scripts/status_snapshot.py --write")
    return 1


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_section(compose())
        print(f"已更新 {STATUS}")
        raise SystemExit(0)
    if "--check" in sys.argv:
        raise SystemExit(check())
    print(compose())
