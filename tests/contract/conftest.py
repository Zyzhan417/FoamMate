"""L2 契约层的公共夹具：**唯一**的「怎么拿到 OpenFOAM 环境 / 怎么派生 cavity」出处。

## 为什么有这个文件

2026-10-29 实测：同一段「`bash -c 'set -a; source <bashrc>; env -0'` → 解析成 dict」
在 6 个文件里各有一份拷贝，而且已经漂移：

| 文件 | 夹具作用域 | 额外校验 |
|---|---|---|
| `test_end_to_end.py` | module | 无 |
| `test_find_template.py` | session | 五个根都是非空 |
| `test_fix_case.py` | session | 无 |
| `test_msh2d_to_foam_mesh.py` | 无夹具（fixture 里直接调用） | `checkMesh` 在 PATH 上 |
| `test_run_case.py` | session | 无 |
| `test_verify_case_post.py` | session | `$FOAM_TUTORIALS` + `$FOAM_SRC` |

后果不是「代码难看」，而是**改一处必须记得改 6 处，漏一处不会红**。换 bashrc 的定位方式
（例如按 `WM_PROJECT_DIR` 推导）、加一个必需的环境变量、统一 skip 的措辞——都属这一类。

夹具集中后，新增 L2 文件只要在测试函数上声明 `foam_env` 参数就**默认**得到
「没装 OpenFOAM 就 skip」，不需要记得抄 guard。

## 本文件只做环境准备，不做断言

断言、变异自证、以及「这条判据要观察什么」留在各自的测试文件里：把判据挪进 conftest
会让「某个文件的判据被悄悄放宽」这件事看不出来。

## 两个文件刻意不并入（各有自己的被测语义，不是遗漏）

- `test_preflight.py`：它要构造「**没** source 的环境」并断言 `preflight.sh` 退 50，
  用 `assert` 而不是 `skip`——与本文件的 skip 语义相反，合并会让它失去被测对象。
- `test_batch_e2e.py`：它从**空 dict** 现场 source，用来证明 `batch.py` 不依赖继承来的
  环境；并入本文件（从 `os.environ` 出发）会把这个证明悄悄抹掉。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

#: OpenFOAM v13 的 bashrc（R11：全项目只允许这一份 OpenFOAM）。
BASH_RC = "/opt/openfoam13/etc/bashrc"

#: 允许被搜索的五个根，顺序固定——与 `scripts/find_template.sh` 的 `ROOT_VARS` 一致。
ROOT_VARS = ("FOAM_TUTORIALS", "FOAM_SRC", "FOAM_APP", "FOAM_ETC", "FOAM_UTILITIES")

#: L2 的派生源。cavity 的 `constant/` 没有 polyMesh（实测），正好当「无网格初始状态」。
CAVITY_REL = Path("incompressibleFluid") / "cavity"


def _sourced_env() -> dict[str, str]:
    """source bashrc 后取回全部环境变量；环境不到位一律 `skip`（skip ≠ pass）。

    校验的是五个根的**全集**（原先各文件只校验自己用到的那几个）。这不改变本机的结论
    ——五个根由同一个 bashrc 一起设置，全有或全无——但让「环境半坏」不再是一种
    随文件而异的判定。
    """
    if not Path(BASH_RC).is_file():
        pytest.skip(f"缺少 {BASH_RC}：测试环境未安装 OpenFOAM v13")

    proc = subprocess.run(
        ["bash", "-c", f"set -a; source {BASH_RC} >/dev/null 2>&1; env -0"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.skip(f"source {BASH_RC} 失败: {proc.stderr.strip()[:200]}")

    env = dict(os.environ)
    for item in proc.stdout.split("\0"):
        if "=" in item:
            key, _, value = item.partition("=")
            env[key] = value

    missing = [name for name in ROOT_VARS if not env.get(name)]
    if missing:
        pytest.skip(f"source bashrc 后这些根仍为空: {missing}")
    return env


@pytest.fixture(scope="session")
def foam_env() -> dict[str, str]:
    """已 source bashrc 的环境（session 级：整个 L2 只 source 一次）。

    这个 dict 被多个测试模块**共享**：测试不许原地修改它。需要改（例如造一个缺变量的
    环境）请先 `dict(foam_env)` 拷贝一份，否则污染会跨文件传播，且失败现象与污染源无关。
    """
    return _sourced_env()


@pytest.fixture(scope="session")
def roots(foam_env: dict[str, str]) -> list[tuple[str, Path]]:
    """`[(变量名, 绝对路径), ...]`，按 `ROOT_VARS` 的固定顺序。"""
    return [(name, Path(foam_env[name])) for name in ROOT_VARS]


@pytest.fixture(scope="session")
def cavity_src(foam_env: dict[str, str]) -> Path:
    """`$FOAM_TUTORIALS/incompressibleFluid/cavity`；不存在就 skip（tutorial 生态变了）。"""
    src = Path(foam_env["FOAM_TUTORIALS"]) / CAVITY_REL
    if not (src / "system" / "controlDict").is_file():
        pytest.skip(f"tutorial 不存在: {src}")
    return src
