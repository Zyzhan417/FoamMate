#!/usr/bin/env python3
"""scripts/deploy.py —— 模块 K：把 FoamMate 部署到稳定路径，并在远端有新提交时一键更新。

三个动作（`--action` 选；不传 = 用法错误 64，与 batch.py / dev_lib.py 同一约定）：

  install  从 `--repo-url`（缺省 = 本仓库的 origin）克隆到 `--target`
           （缺省 = $FOAM_MATE_HOME，再缺省 ~/foam-mate），再跑该副本自己的
           `scripts/preflight.sh` 自检。目标已是同源部署 → 幂等退 0。
  update   在 `--target` 里 `git fetch` 远端；本地落后且可快进 → `git merge --ff-only`，
           然后重跑 preflight。本地有未提交改动 / 远端历史被重写 → 拒绝并说明原因。
  status   只读：报部署的 commit / VERSION / 分支 / 未提交改动；`--fetch` 时额外
           报远端关系（current / behind 之外的 ahead / diverged / unreachable）。

## 为什么部署「克隆」而不是「发布包」

发布包 `dist/foam-mate-<版本>/`（15 个文件）没有 git 元数据，回答不了
「装的是哪个提交」「远端有没有更新」——而这两问正是本模块存在的理由。
代价：目标目录里多出 tests/ bench/ references/（本仓库 .git 实测 2.2 MB），
三份入口文档在 `release/` 下而不是包根；install 的 NEXT 段会把这两条路径直接打出来。

**装的是提交，不是工作树**（与 `scripts/make_export.sh` 同一条原则）：install 从远端克隆，
你本地未提交的改动不会进部署，所以部署内容永远能指到一个 SHA。

## 退出码

0 成功（含 already_deployed / current / ahead 三个幂等态）/ 90 目标状态或前置不合法 /
91 本地已跟踪文件被改动，拒绝更新 / 92 远端不是快进（历史被重写或已分叉）/
93 远端不可达（clone/fetch 失败或超时）/ 94 部署后 preflight 未通过 / 64 用法错误。

90–94 是自留区间：全仓已用 0–5、10–15、20–23、31–33、40、50/51、60、64、70/71、80/81、85–89。
本脚本**不进发布包**（见 `scripts/make_release.sh` 的 `FORBIDDEN_EXACT`），
所以使用者的退出码总表里不会出现这些码。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

EX_OK = 0
EX_USAGE = 64
EX_TARGET = 90       # 目标状态或前置不合法（非空目录 / 无 origin / detached HEAD / 没有部署）
EX_DIRTY = 91        # 本地已跟踪文件有改动，拒绝更新
EX_DIVERGED = 92     # 远端不是本地 HEAD 的后代（历史被重写或分叉）
EX_REMOTE = 93       # 远端不可达（clone / fetch 失败或超时）
EX_VERIFY = 94       # 部署后 preflight 未通过

ACTIONS = ("install", "update", "status")
PREFLIGHT_REL = Path("scripts") / "preflight.sh"
DEFAULT_TARGET_NAME = "foam-mate"


class _Parser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64，并**先打用法块**再退。

    理由与 scripts/dev_lib.py 的同名类逐字相同：2 在 verify_case.sh 里是「G2 网格门失败」；
    只打 `prog: error:` 会让 tests/unit/test_exit_codes.py 的
    「用法错误要说明错在哪」那条判据失去可判定的对象（2026-10-31 实测）。
    """

    def error(self, message: str) -> None:  # pragma: no cover - argparse 内部
        self.print_usage(sys.stderr)
        self.exit(EX_USAGE, f"{self.prog}: error: {message}\n")


def _emit(payload: dict, code: int) -> None:
    """stdout 只有 JSON（机器可读），人看的下一步一律走 stderr（分工同 dev_lib.py）。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    sys.exit(code)


def _fail(code: int, reason: str, **extra) -> None:
    payload = {"ok": False, "reason": reason}
    payload.update(extra)
    _emit(payload, code)


def _next_steps(target: Path) -> None:
    print(f"DEPLOYED {target}", file=sys.stderr)
    print("NEXT:", file=sys.stderr)
    print(f"  export HARNESS={target}", file=sys.stderr)
    print('  bash "$HARNESS/scripts/preflight.sh"', file=sys.stderr)
    print(f"  read {target}/release/SKILL.md", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="deploy.py",
        description="FoamMate 部署与一键更新（git 克隆式部署；不进发布包）",
        epilog=("退出码：0 成功 / 90 目标或前置不合法 / 91 本地改动阻止更新 / "
                "92 非快进（历史被重写）/ 93 远端不可达 / 94 preflight 未过 / 64 用法"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--action", required=True, choices=ACTIONS,
                   help="install | update | status")
    p.add_argument("--target", help="部署目录（缺省 $FOAM_MATE_HOME，再缺省 ~/foam-mate）")
    p.add_argument("--repo-url", help="仓库地址（缺省 = 本仓库的 origin）")
    p.add_argument("--no-preflight", action="store_true",
                   help="跳过部署后的环境自检（仅测试/CI；跳过时不算「环境就绪」的证据）")
    p.add_argument("--fetch", action="store_true", help="status：同时 fetch 远端再报关系")
    p.add_argument("--timeout", type=int, default=600, help="单条 git/preflight 的墙钟上限（秒）")
    return p


# ---------------------------------------------------------------------------
# 纯函数与 git 助手（任务 2 起在这里追加）
# ---------------------------------------------------------------------------

CURRENT = "current"
AHEAD = "ahead"
DIRTY = "dirty"
FAST_FORWARD = "fast_forward"
DIVERGED = "diverged"


def classify(local: str, upstream: str, dirty: list[str],
             local_is_ancestor: bool, upstream_is_ancestor: bool) -> str:
    """把四个可观测量归约成一个动作；**除这里没有第二处做这个判断**。

    顺序即优先级，每一步对应一种不同的处置：

    1. 两个 SHA 相等    → current：没有更新；工作树脏不脏都不改变这个事实
    2. 远端是本地祖先    → ahead：部署目录里有未推送的提交（有人在这里 commit 过）
    3. 已跟踪文件有改动  → dirty：能快进也不做，否则用户改动会与合并结果纠缠
    4. 本地是远端祖先    → fast_forward：唯一会自动动手的分支
    5. 其余             → diverged：历史被重写或分叉；按项目规则不自动 reset
    """
    if local == upstream:
        return CURRENT
    if upstream_is_ancestor:
        return AHEAD
    if dirty:
        return DIRTY
    if local_is_ancestor:
        return FAST_FORWARD
    return DIVERGED


def _repo_root() -> Path:
    """本脚本所在仓库的根（deploy.py 在 scripts/ 下）；不写死任何绝对路径。"""
    return Path(__file__).resolve().parents[1]


def _target_path(raw: str | None) -> Path:
    if raw:
        return Path(raw).expanduser().resolve()
    env = os.environ.get("FOAM_MATE_HOME", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / DEFAULT_TARGET_NAME).resolve()


def _git(cwd: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout)


def _git_net(cwd: Path, *args: str, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """网络侧 git：超时也要变成可解释的 93，不能甩一段 traceback。"""
    try:
        return _git(cwd, *args, timeout=timeout)
    except subprocess.TimeoutExpired:
        _fail(EX_REMOTE, f"git {' '.join(args)} 超过 {timeout}s 未返回（网络不可达或卡在凭据提示）",
              cmd=["git", *args])


def _git_out(cwd: Path, *args: str) -> str | None:
    proc = _git(cwd, *args)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _require_git() -> None:
    if not shutil.which("git"):
        _fail(EX_TARGET, "PATH 上没有 git：本模块用 git 记录「装的是哪个提交」并判断远端更新")


def _origin_url(root: Path, override: str | None) -> str:
    if override:
        return override
    url = _git_out(root, "remote", "get-url", "origin")
    if not url:
        _fail(EX_TARGET,
              "无法确定仓库地址：当前仓库没有 origin。"
              "下载的 zip 没有提交坐标，不能部署；请 git clone 后用 --repo-url 指定地址",
              repo_root=str(root))
    return url


def _is_deployment(target: Path) -> bool:
    """target 本身（不是它的外层仓库）是一个 git 工作树 → 当作部署目录。

    `--show-toplevel` 会向上找到外层仓库，所以必须比对解析后的路径；
    否则 `~/foam-mate/sub` 这种子目录也会被当成部署。
    """
    if not target.is_dir():
        return False
    top = _git_out(target, "rev-parse", "--show-toplevel")
    return top is not None and Path(top).resolve() == target.resolve()


def _version(target: Path) -> str | None:
    f = target / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else None


def _head(target: Path) -> str | None:
    return _git_out(target, "rev-parse", "HEAD")


def _branch(target: Path) -> str | None:
    return _git_out(target, "symbolic-ref", "--short", "HEAD")


def _dirty_tracked(target: Path) -> list[str]:
    """**已跟踪**文件的改动。untracked 不算：算例/笔记放部署目录里是允许的，
    真会撞车时 `git merge` 自己会拒绝（`--ff-only` 也一样）。"""
    proc = _git(target, "status", "--porcelain", "--untracked-files=no")
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _ancestor(target: Path, a: str, b: str) -> bool:
    return _git(target, "merge-base", "--is-ancestor", a, b).returncode == 0


def _describe(target: Path) -> dict:
    return {
        "target": str(target),
        "commit": _head(target),
        "version": _version(target),
        "branch": _branch(target),
        "dirty_tracked": _dirty_tracked(target),
    }


# ---------------------------------------------------------------------------
# 动作
# ---------------------------------------------------------------------------


def action_install(args: argparse.Namespace) -> int:
    _fail(EX_USAGE, "install 尚未实现")


def action_update(args: argparse.Namespace) -> int:
    _fail(EX_USAGE, "update 尚未实现")


def action_status(args: argparse.Namespace) -> int:
    _require_git()
    target = _target_path(args.target)
    if not _is_deployment(target):
        _fail(EX_TARGET, "没有部署（或 --target 指错了）：先 --action install", target=str(target))

    info = _describe(target)
    upstream: str | None = None
    relation: str | None = None
    if args.fetch:
        branch = info["branch"]
        if not branch:
            _fail(EX_TARGET, "部署目录处于 detached HEAD；先 git -C <target> checkout main", **info)
        proc = _git_net(target, "fetch", "--quiet", "origin", branch, timeout=args.timeout)
        if proc.returncode != 0:
            relation = "unreachable"
        else:
            upstream = _git_out(target, "rev-parse", "FETCH_HEAD")
            relation = (classify(info["commit"], upstream, info["dirty_tracked"],
                                 _ancestor(target, info["commit"], upstream),
                                 _ancestor(target, upstream, info["commit"]))
                        if upstream else "unreachable")
    _emit({"ok": True, "action": "status", "upstream": upstream, "relation": relation, **info},
          EX_OK)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"install": action_install, "update": action_update, "status": action_status}
    return handlers[args.action](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
