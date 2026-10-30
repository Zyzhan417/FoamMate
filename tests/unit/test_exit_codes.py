"""调用契约：**所有**脚本的「用法错误」必须退同一个码 `64`。

## 为什么必须是 64，不能是 2

`2` 在 `verify_case.sh` 里已经有业务含义：**G2 网格门失败**（D6 的退出码 `0–5`）。
如果 `verify_case.sh` 的用法错误也退 2，调用方**无法区分**
「你把参数写错了」与「这个 case 的网格没过」——两种情况的处置完全相反
（前者改调用，后者修算例）。

所以 64（`sysexits.h` 的 `EX_USAGE`）是对的，因为它不落在任何模块的业务码区间内：

| 模块 | 业务码 | 与 64 冲突？ |
|---|---|---|
| A `parse_requirement.py` | `0` / `10` | 否 |
| B `find_template.sh` | `0` / `11` | 否 |
| C `new_case.sh` | `0` / `12` / `13` | 否 |
| D `run_case.sh` | `0` / `20` / `21` / `22` / `23` | 否 |
| E `verify_case.sh` | `0`–`5`（门结果） | 否 |

## 为什么这一层必须有

实测（2026-10-28）：五个脚本里 `verify_case.sh` 退 64，另外四个退 2。
每个模块内部都无歧义，但**跨模块不一致**——统一消费者（批跑 `batch.py`、M3 的 skill）
要判「是不是我调错了」就得先查表知道是哪个模块。有了这条测试，规则变成一条可判定的事实。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 每个脚本名 → 一次「必然属于用法错误」的调用方式。
#: 统一用「完全不传参数」：所有脚本都要求至少一个必填参数，故必然走到 usage 分支。
SCRIPTS = [
    "parse_requirement.py",
    "find_template.sh",
    "new_case.sh",
    "run_case.sh",
    "verify_case.sh",
    "make_release.sh",
    # batch.py 也在这个列表里：它没有默认动作，不传参数就是用法错误（64）。
    # 与 preflight.sh **相反**是有意的：preflight 的默认动作是"跑检查"（陌生人的第一条命令），
    # batch 的默认动作是"什么都不做"（误敲一次就 rm -rf 一个批次目录，代价不对称）。
    "batch.py",
    # 导出树组装器与校验器同理：不给 --dest / --tree 就没有默认动作。
    "make_export.sh",
    "verify_export.py",
    # 网格转换器同理：不给 --msh 就没有默认动作。
    "msh2d_to_foam.py",
    # 二次开发模块同理：不给 --stage 就没有默认动作。
    "dev_lib.py",
]

EX_USAGE = 64


@pytest.mark.parametrize("name", SCRIPTS)
def test_usage_error_exits_64(name: str):
    """不传任何参数 → 必须是 64，不能是 2，也不能是 0。"""
    path = REPO_ROOT / "scripts" / name
    assert path.is_file(), f"脚本不存在: {path}"

    proc = subprocess.run(
        [str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == EX_USAGE, (
        f"{name} 缺参数时应退 {EX_USAGE}（用法错误），实得 {proc.returncode}。"
        f"stderr={proc.stderr.strip()[:300]!r}\n"
        f"注意：退回 2 会和 verify_case.sh 的『G2 门失败』混淆。"
    )


#: 「用户看得懂错在哪」的两种合法形态（二选一即可）：
#: ① 打用法块（`usage` / `用法`）；② argparse 的 `prog: error: <缺哪个参数>`。
#: 实测 `scripts/dev_lib.py` 是②（`dev_lib.py: error: the following arguments are required: --stage`），
#: 它比用法块更直接——直接点名缺哪个选项。判据的实质是「stderr 里有可执行的下一步」，
#: 不是「必须打用法块」；把②判红会逼人往脚本里加一行没用的 usage dump。
USAGE_HINTS = ("usage", "用法", "error:")


@pytest.mark.parametrize("name", SCRIPTS)
def test_usage_error_writes_to_stderr(name: str):
    """用法错误必须写 stderr，不能污染 stdout，且要说明「错在哪」。

    为什么单独一条：模块间契约里 stdout 有语义（A 回显 JSON、B 输出命中行）。
    用法错误若写 stdout，会被下游当成正常输出解析——例如 B 的空命中判据是
    「stdout 恰好等于 FOUND=0」，混进一行 usage 就会让该判据假红。
    """
    path = REPO_ROOT / "scripts" / name
    proc = subprocess.run([str(path)], capture_output=True, text=True, timeout=60)

    assert proc.stderr.strip(), f"{name} 用法错误时 stderr 为空，用户看不到错在哪"
    assert any(hint in proc.stderr.lower() for hint in USAGE_HINTS), (
        f"{name} 用法错误的 stderr 里既无 'usage' / '用法' 也无 'error:'：{proc.stderr.strip()[:200]!r}"
    )


def test_find_template_env_missing_is_64_not_2():
    """B 在「五个搜索根全为空」时退 64。

    这条来自实测：不 source bashrc 时 `find_template.sh --keyword cavity` 原本退 2。
    2 与 verify_case.sh 的「G2 门失败」同号，所以统一进 64 桶。

    注意与 D 的区别（不要「统一」它们）：`run_case.sh` 的环境缺失是 **22**，
    因为 D 的契约额外登记了 22（「环境缺失」），而 B 没有这个码。两者**故意不同**——
    D 的 22 让调用方能说「环境没加载」而不必去读 stderr。
    """
    path = REPO_ROOT / "scripts" / "find_template.sh"
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}   # 无 FOAM_*，故意不 source
    proc = subprocess.run(
        [str(path), "--keyword", "cavity"], capture_output=True, text=True,
        timeout=60, env=env,
    )
    assert proc.returncode == 64, (
        f"搜索根全空时应退 64，实得 {proc.returncode}；stderr={proc.stderr.strip()[:200]!r}"
    )
    assert "source" in proc.stderr, "应提示用户先 source bashrc"
