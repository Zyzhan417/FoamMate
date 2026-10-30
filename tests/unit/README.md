# tests/unit — L1 单元层（零 OpenFOAM、零 LLM）

## 跑法（**必须用显式解释器**）

    <装有 pytest 的解释器> -m pytest tests/unit -q

**不要想当然地用 PATH 上的第一个 `python3`**：它指向谁可能**不稳定**——实测同一会话里
一次是系统 python（有 pytest 9.0.3），下一次变成某个 venv（无 pytest，报
`No module named pytest`）。选解释器：

    for py in $(which -a python3); do $py -c "import pytest" 2>&1 | head -1; done

## 期望 `failed=0`（<5 s）

**本文不记测试项数**：项数随新增用例变化，记在这里必然腐坏（曾经记过的数字已与实测不符）。
判据是命令输出里的 `failed=0`；要当前项数就自己跑 `--collect-only -q | tail -1`。

| 文件 | 被测对象 |
|---|---|
| `test_parse_requirement.py` | 模块 A：需求 → 四元组（`properties` 非 `material`；`objective` 限 steady/transient） |
| `test_new_case.py` | 模块 C：`cp -a` 派生 + `case.meta` 六键；退出码 12/13/64 |
| `test_verify_case_pre.py` | 模块 E-lite：G1 结构 + G5 范围；mtime 与 `base/` 两条路径 |
| `test_batch.py` | 模块 H：`cases.json` 的 base + vary 展开（上限 50）、id 命名、覆盖顺序；零求解 |
| `test_msh2d_to_foam.py` | 模块 I：面顺序 / 法向 / patch 归属 / 拒收半成品（零 gmsh，判的是格式与自检） |
| `test_dev_lib.py` | 模块 J：四个 stage 的判据（`prepare` 两处改写 + 4 条拒收 + V1 自检 / `check` 越界 / `build` 的 rc 与 `error:` 计数 / `verify` 的 `dlopen` 计数 + 系统树）——假 `wmake`、假 `foamRun` 桩，**零 OpenFOAM** |
| `test_check_contracts.py` | 模块 G：`results.csv` 15 列 + `case.meta` 六键；退出码 0/40/64 |
| `test_check_release_docs.py` | 文档契约检查器的变异自测：四条判据各配一个必红变异（退 41） |
| `test_export.py` | 导出树 E1–E6：六门在一棵树上全绿 + 每一类失效都有变异用例（退 80） |
| `test_portability.py` | 可移植性：正文不得写死 `/opt/openfoam13`，须按 `WM_PROJECT_DIR` 推导 + 回退 |
| `test_bench_runner.py` | bench runner 的三处静默错误：任务解析 / 多例展开 / L2 归约不得把 `undeterminable` 折成 pass |
| `test_script_entrypoints.py` | **跨模块**：`scripts/` 下每个带 shebang 的文件 — 存在、有可执行位、能直接启动（不看退出码） |
| `test_exit_codes.py` | **跨模块**：用法错误恒退 `64` 且写 stderr（不能用 `2`，`2` 是 G2 门失败） |

后两个文件是**横切契约**，按「类」遍历 `scripts/` 而不是列举文件名——新增脚本自动被覆盖。

## 为什么本层不需要 OpenFOAM

三个被测对象都不调 OpenFOAM 命令：A 只做正则+校验+JSON；C 只做 `cp -a` + 写 JSON
（测试用 `tmp_path` 造伪 tutorial 树并改 `FOAM_TUTORIALS`）；E-lite 的 G1/G5 是纯文件检查。
**C 之所以能在 L1**（不是 L2）就是这条：一条 `foamRun`/`checkMesh` 都不跑。

需要真跑 OpenFOAM 的模块 D 在 `tests/contract/`（L2）。

## 变异口径（每个模块至少一个，全部实测过红/绿）

- A-M1：校验器「缺键填空串」→ 13 failed（含 A2、A3）
- 入口-M1：`chmod -x scripts/parse_requirement.py` → 入口测试 2 条红
- 退出码-M1：把某个脚本的 `die 64` 改回 `die 2` → `test_exit_codes` 对应项红
- A-M2：去掉 `objective` 枚举校验 → A4 红
- C-M1：`dest` 已存在改成覆盖 → C6 红
- C-M2：删掉「在 `$FOAM_TUTORIALS` 下」前缀校验 → C7 红
- E-M1：mtime 分支恒判「无改动」→ E-p7 红
- E-M2：忽略 `base/` 强制走 mtime → E-p7b 红（+ 4 项连带红）

**只测「合法输入能过」等于没测**：每条判据都要有一个「注入后必须红」的变异体。
