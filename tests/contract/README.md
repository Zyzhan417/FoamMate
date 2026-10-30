# tests/contract —— L2 契约测试（真跑 OpenFOAM 命令）

跑法（必须用**显式**解释器，即装有 pytest 的那个；脚本自己先 source OpenFOAM）：
python3 -m pytest tests/contract -q            # 全量
python3 -m pytest tests/contract/test_fix_case.py -q
# PATH 上的 python3 指向谁不稳定，报 No module named pytest 就是选错了解释器

期望：全量 **`failed=0`**（没有 OpenFOAM 时相关用例 skip 而不是红）。本文不记项数——项数随新增
用例变化，判据只看 `failed=0`。case 一律 `cp -a` 从 `$FOAM_TUTORIALS` 派生到
`tmp_path`，**不写 `bench/`**（R12）。

## 公共夹具 —— 环境引导只写一处（`conftest.py`）

`foam_env` / `roots` / `cavity_src` 三个 session 夹具在 `tests/contract/conftest.py`：
source bashrc → 取回环境、五个根非空校验、"cavity 作派生源"都在那里。

**新增 L2 文件只要在测试函数上声明 `foam_env` 参数，就默认得到「没装 OpenFOAM 就 skip」。**
不要再自己写一份 `_foam_env`：曾经 6 个文件各有一份拷贝，校验的变量集合与夹具作用域都不一样
（改一处要记得改 6 处，漏一处不会红）。`foam_env` 返回的 dict 被多个模块共享，测试**不得**原地
修改；需要改先 `dict(foam_env)` 拷贝。

两个文件刻意不并入（语义相反，不是遗漏）：`test_preflight.py` 要构造「**没** source 的环境」
并断言脚本退 50（用 `assert` 不用 `skip`）；`test_batch_e2e.py` 从**空 dict** 现场 source，
用来证明 `batch.py` 不依赖继承来的环境。判据与变异自证仍留在各文件里。

## 变异口径（判据必须真的会红）
"绿"只在"改坏实现就会红"时才算证据：备份 → 改坏 → 红 → 还原 → 绿 → `diff -q`。
没做过变异自测的测试文件，其绿灯不作数。F 的三个（`scripts/fix_case.py`）：

| 变异 | 改法 | 必须变红 |
|---|---|---|
| F-M1 | 「定位不到→declined」改成「默认用 `system/controlDict`」 | `test_f3` |
| F-M2 | 删掉备份那一步（直接改字典） | `test_f4` |
| F-M3 | 删掉指纹比对 | `test_f7` |

J（`scripts/dev_lib.py` 的 L2，`test_dev_lib_build.py`，真 wmake + 真 `foamRun -libs`）：
判据是「`dlopen error` 计数 == 0」，**不是** `foamRun` 的退出码（T0 实测好坏库都退 0）。

| 变异 | 改法 | 必须变红 |
|---|---|---|
| J-M1 | `stage_verify` 的 `if dlopen:` 改成 `if rc != 0:`（判据从计数换成退出码） | `test_verify_rejects_undlopenable_so` |

`test_verify_rejects_undlopenable_so` 是 J-M1 的捕手：`.so` 换成非 ELF 垃圾字节并把 `build.json`
的 `so_sha256`/`so_size` 改成与之一致（sha 门为绿），`foamRun -help` 仍 rc=0、只留一行
`dlopen error : … file too short`。判 rc 时这条会退 0。

墙钟（2026-10-31，WSL2 / `wmake -j 2` 派生源 `pairPatchAgglomeration`，1 个 `.C`）：
`pytest tests/contract/test_dev_lib_build.py -q` → **7 passed in 12.49 s**（`/usr/bin/time` WALL 12.76 s）。
