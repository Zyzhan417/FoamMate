# 四、harnessfoam 深度解剖（唯一 v13 原生参照物，tier A）

> 为什么是它：`references/repos/harnessfoam/README.md:100` 声明运行时契约要求 solver 日志确认
> OpenFOAM Version 13；`references/repos/harnessfoam/harnessfoam/case_manifest.py:8`
> `EXPECTED_OPENFOAM_VERSION = "13"`。它是参考库里唯一声明 v13 的项目（tier A），
> 也是 `references/02-architectures.md` §0 表里唯一「判据全确定性」的项目。

## 0 口径

1. **只读代码，未执行任何脚本**（R12 设计期禁跑：不许跑 `blockMesh` / `foamRun` / 本仓任何入口）。
2. 所有结论必须给 `references/repos/harnessfoam/...:行号`；行号必须真实（G-DOC-1 会查）。
3. 判据统计必须来自 `grep -c` 或 `sed -n` 的真实输出，不许凭 02 的描述转抄——02 是二手（E4）。
4. 本文件只回答「它怎么做」，不回答「它做得好不好」（后者需实跑，本阶段禁止）。
5. 不得修改 `references/repos/harnessfoam/` 下任何文件（G-R9-1 用 `git status --porcelain` 判）。

## 1 定位与规模（含实测命令输出）

### 1.1 规模实测（worker 自己重跑，非转抄 02）

```
$ find references/repos/harnessfoam -name '*.py' -not -path '*__pycache__*' | wc -l
79
$ find references/repos/harnessfoam -name '*.py' -print0 | xargs -0 cat | wc -l
5631
$ find references/repos/harnessfoam -type f -not -path '*/.git/*' | wc -l
266
$ find references/repos/harnessfoam/tests -name '*.py' | wc -l
34
$ find references/repos/harnessfoam -name '*.py' -not -path '*tests*' -not -path '*__pycache__*' | wc -l
45
$ find references/repos/harnessfoam -name '*.md' -not -path './.git/*' | wc -l
2
$ find references/repos/harnessfoam/assets/openfoam_tutorials -type f | wc -l
156
$ ls -1 references/repos/harnessfoam
Allrun
HarnessFOAM.egg-info
README.md
assets
harnessfoam
pyproject.toml
run_demo.py
tests
```

三个数与编排方实测的核对：**全仓 py=79 ✓、全仓行数 5631 ✓、tests py=34 ✓**。第三个「包内 44」我首次跑出 **45**，差额已定位到行、不是矛盾：

| 口径 | 命令 | 实测 | 与编排方「44」的差 |
|---|---|---|---|
| `harnessfoam/` 包内（排除 tests） | `find harnessfoam -name '*.py' \| wc -l` | 44 | 一致 |
| 全仓（排除 tests/） | `find . -name '*.py' -not -path './tests/*'` | 45 | +1 = 根目录 `run_demo.py` |
| tests/ | `find tests -name '*.py'` | 34 | 一致 |
| 合计校验 | 44 + 1 + 34 | 79 | 与全仓 79 相等 |

即「79 = 包内 44 + 根 1 + 测 34」；编排方的 44 是**包内**口径，`run_demo.py`（116 行）在根、既不属于包也不属于 tests。

规模分层（`wc -l` 实测，均有 `total` 行）：

| 目录 | 行数 | 命令 |
|---|---|---|
| `harnessfoam/agents/*.py` | 1537 | `wc -l harnessfoam/agents/*.py \| tail -1` |
| `harnessfoam/api/*.py` | 1259 | `wc -l harnessfoam/api/*.py \| tail -1` |
| `harnessfoam/core/*.py` | 522 | `wc -l harnessfoam/core/*.py \| tail -1` |
| `tests/unit/*.py` | 532 | `find tests/unit -name '*.py' -print0 \| xargs -0 cat \| wc -l` |
| `tests/cases/*.py` | 127 | 同上，路径换 `tests/cases` |
| 全仓 | 5631 | `find ... -print0 \| xargs -0 cat \| wc -l` |

数据来源：`find`/`wc -l`/`ls -1`，命令与输出见上两段。

### 1.2 02 主张验证矩阵（二手 → 一手，本文件主项）

下表把 `references/02-architectures.md:1266-1447` 的可验证主张逐条抽出，回切源码判定。**判定列每行只出现一个判定词。**

| # | 02 逐字主张（位置） | 源码锚点 | 判定 | 依据 |
|---|---|---|---|---|
| 1 | 「LangGraph 编排的 9 节点多 agent 框架」（02:1269） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:456-464` | 证实 | 9 条 `add_node` 连续：architect/meshing/input_writer/runner/preflight/reviewer/physics_autopilot/visualizer/end |
| 2 | 「9 节点、单主干 + 3 个条件边，不存在并行分支」（02:1297） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:470` `:477` `:487` `:495` | 证伪 | `grep -c 'add_conditional_edges'` = **4**：preflight、runner、reviewer、visualizer 各一条 |
| 3 | 「`:466 workflow.set_entry_point("architect")`，`:500 return workflow.compile()`」（02:1299） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:466` | 证实 | 三处行号全对，`:500` 即 `return workflow.compile()` |
| 4 | api 一套「8 个 tool」（02:1309-1310） | `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:10` | 证实 | `grep -c '@mcp.tool()'` = 8，工具名与行号见 §7 |
| 5 | core 一套「11 个 tool（`grep -c "@app.tool()"` = 11）」（02:1312） | `references/repos/harnessfoam/harnessfoam/core/mcp_server.py:10` | 证实 | `grep -c '@app.tool()'` = 11 |
| 6 | 「`mcp = FastMCP("HarnessFOAM")`」（02:1309） | `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8` | 证实 | 逐字一致 |
| 7 | 「`app = FastMCP("HarnessFOAM-MCP")`」（02:1312） | `references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6` | 证实 | 逐字一致 |
| 8 | `validate_runtime` 「五条判据」（02:1355） | `references/repos/harnessfoam/harnessfoam/validation.py:125-138` | 证实 | 只有 5 个 `errors.append` 分支：128/130/132/134/136 |
| 9 | 「preflight 的 patch 集合交叉检查（`validation.py:41`-59`）」（02:1434） | `references/repos/harnessfoam/harnessfoam/validation.py:41-59` | 证实 | 函数 12-75；patch 段确在 41-59，且是**集合相等**（`patches != field_patches`） |
| 10 | 「`validate_physics`（`physics_validation.py:43`）」（02:1367） | `references/repos/harnessfoam/harnessfoam/physics_validation.py:43` | 证实 | 43 是 `def validate_physics`，函数体到 71 |
| 11 | 「启用时 5 条硬阈值（`:11-15`）」（02:1368） | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:10` | 证实 | 5 个键在 11-15 行，名字与 02 所写逐字一致 |
| 12 | 「没有数值时间目录时直接放行：`:45-46 return True, {"status": "SKIPPED"…`」（02:1367） | `references/repos/harnessfoam/harnessfoam/physics_validation.py:45-46` | 部分证实 | 两句字面属实，但 `_latest_time`（`:31-40`）用 `float(child.name)` 收集子目录，`0/` 也是数字目录 → **主流水线里该分支不可达**；实际行为是拿初场 `0/U` 判并返回 `CHECKED`（见 §5.3「无数字时间目录」行下的证明） |
| 13 | 「`graph.py:68 state['max_errors'] = 3`」（02:1303） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:68` | 证实 | 逐字一致，且仅 `if 'max_errors' not in state` 时才写 |
| 14 | 「reviewer 每次 `:302 state['errors'] += 1`」（02:1303） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:302` | 证实 | 逐字一致；另 `:390` physics_autopilot 也 `+= 1`（02 未提，见 §9） |
| 15 | 「`pyproject.toml` 声明 `faiss-cpu>=1.7.4`，但 `grep -rn "faiss" harnessfoam/` 无命中——死依赖」（02:1319） | `references/repos/harnessfoam/pyproject.toml:19` | 证实 | `grep -rn faiss harnessfoam/` = **0**；全仓 3 命中全是打包元数据（pyproject:19、egg-info/PKG-INFO:14、egg-info/requires.txt:5），无一处 import |
| 16 | README「solver logs must confirm OpenFOAM Version 13 before the run is accepted」（02:1372） | `references/repos/harnessfoam/README.md:100` | 证实 | 逐字一致（含反引号包裹的 `.harnessfoam/manifest.json`） |
| 17 | 「`parse_openfoam_version` 除测试外全仓无调用」（02:1380） | `references/repos/harnessfoam/harnessfoam/case_manifest.py:45` | 证实 | `grep -rn parse_openfoam_version` 仅 3 命中：定义 + 测试 import + 断言 |
| 18 | 「`pyproject.toml:9 requires-python = ">=3.10"`」（02:1409） | `references/repos/harnessfoam/pyproject.toml:8` | 证伪 | 第 9 行是 `description = …`；`requires-python` 在 **:8**。值 `">=3.10"` 本身对 |
| 19 | 「`agents`→1537、`api`→1259、`core`→522」（02:1271） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:1` | 证实 | 三条 `wc -l ... \| tail -1` 逐字复跑，三数全中 |
| 20 | 「79 个 py / 5631 行」（02:1271） | `references/repos/harnessfoam/harnessfoam/cli.py:1` | 证实 | §1.1 复跑一致 |
| 21 | 「**只有 `agents/` 调 LLM**」（02:1293） | `references/repos/harnessfoam/harnessfoam/api/server.py:614` | 证伪 | `api/server.py:569` import `build_llm`、`:614` 直接调；02 自己 §2 表里 api 行也写「碰 LLM 是」——同一节自相矛盾 |
| 22 | 「只有 `agents/runner.py`、`benchmark.py`、`tutorial_regression.py`、`core/hpc.py` 起子进程」（02:1293） | `references/repos/harnessfoam/harnessfoam/agents/visualizer.py:114` | 证伪 | `grep -rlnE 'subprocess\.(run\|Popen)' harnessfoam/` 共 **11 个文件**：visualizer、runner、knowledge、github_feedback、utils/installer、optimization、assistant_tools、api/routes（**5 处**：:62/:155/:181/:189/:458）、api/server（2 处）、benchmark、tutorial_regression；而 02 点名的 `core/hpc.py` 里 `grep -c subprocess` = **0**（只用 asyncssh） |
| 23 | 「`cli.py:58`（`def main():`，子命令 run/serve/mcp/benchmark 见 :63-77）」（02:1271） | `references/repos/harnessfoam/harnessfoam/cli.py:58` | 证实 | 58 = `def main():`；63 run / 68 serve / 73 mcp / 75 benchmark |
| 24 | 「`api/server.py:74`（`app = FastAPI(title="HarnessFOAM API"…`）、`api/mcp_server.py:8`」（02:1271） | `references/repos/harnessfoam/harnessfoam/api/server.py:74` | 证实 | 74 逐字一致；`:219` 是 `@app.websocket("/api/stream")`，与 02:1277 一致 |
| 25 | 「`api/routes.py` 有 30+ 路由」（02:1315） | `references/repos/harnessfoam/harnessfoam/api/routes.py:433` | 部分证实 | `grep -cE '^@router\.(get\|post\|put\|delete\|patch)'` = **30**（15 get + 15 post），是「恰好 30」不是「30 多」 |
| 26 | 「7 条硬编码 `KnowledgeChunk`（`knowledge.py:17`-25`）」（02:1321） | `references/repos/harnessfoam/harnessfoam/knowledge.py:17-25` | 证实 | `CORPUS` 元组 17-25，7 个条目在 18-24；`boundary-consistency` 确在 :20 |
| 27 | 「`find assets/openfoam_tutorials -type f \| wc -l` → 156，占全仓 266 个文件的 59%」（02:1322） | `references/repos/harnessfoam/harnessfoam/knowledge.py:38` | 证实 | 复跑 156 与 266，156/266 = 58.6% |
| 28 | 切块参数串「`:75` >80 KB 跳过、`:82` 前 6000 字符、`:84` 标签取前 15000、`:103 score`、`:97 k=4`、`:118-124` 5 facet、`:136` 0.72、`:147-152` 4 路、`:156 max_chars=2500`」（02:1325、:1428） | `references/repos/harnessfoam/harnessfoam/knowledge.py:156` | 证实 | 9 个行号与数值全部逐字命中，无一处偏移 |
| 29 | 「`graph.py:139` backup_dir…逐文件 `shutil.copy2`（`:146`）」（02:1338） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:139` | 证实 | 139 是 backup_dir 拼接 `attempt_{errors}`；146 是 `shutil.copy2` |
| 30 | 「`graph.py:317`-325，字段 `attempt/prompt/error/suggestions`，追加写 `.harnessfoam/failure_ledger.jsonl`」（02:1339） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:317` | 证实 | 317 路径、319 `'a'` 追加、320-325 四个键；`error` 截 4000 字符、`retry_history` 里截 2000（两处不同） |
| 31 | 「轮数到顶标 `RETRY_EXHAUSTED`（`graph.py:312`）」（02:1340） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:312` | 证实 | 三元表达式，条件 `errors < max_errors` 时给 `RETRY_PENDING` |
| 32 | 「`runner.py:143 process.wait(timeout=300)` → `:145 return process.returncode, stdout_str, ""`」（02:1349） | `references/repos/harnessfoam/harnessfoam/agents/runner.py:143` | 证实 | 两行逐字一致；`:110` 的 `wsl bash -lc` 命令、`:70` 的 `set -e`、`:75` foamrc 循环也全对 |
| 33 | 「HPC 分支把日志换成常量 `graph.py:230 stdout_str = "HPC Run Complete"`」（02:1401） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:230` | 证实 | 逐字一致 |
| 34 | 「我们的 G3（`references/repos/harnessfoam/README.md:182`）」（02:1384） | `references/repos/harnessfoam/README.md:182` | 证伪 | harnessfoam README 共 334 行，**:182 是空行**；G3 那一行在**本项目** `references/00-project-readme.md:182`（`\| **G3 短跑** \| …`）。02 把仓库前缀加错了 |
| 35 | 「9 节点图 + 6 个 LLM 角色」（02:1428） | `references/repos/harnessfoam/harnessfoam/agents/runner.py:34` | 部分证实 | 本地主干确为 6 个调 LLM 的节点；但 runner 在 HPC 分支调 `generate_hpc_script`（`:204`）也走 LLM → 最多 7 个，且 `optimizer.py:54` 是第 8 条 LLM 路径（不在图里） |
| 36 | 「**无 LICENSE 文件**（`ls harnessfoam/LICENSE*` → No such file），但 README:14 badge 写 MIT」（02:1414） | `references/repos/harnessfoam/README.md:14` | 证实 | `ls LICENSE*` 报 No such file；README:14 是 `[![License: MIT](…)]`；`Dockerfile*` 同样不存在 |
| 37 | 「全仓没有一处匹配 `Mesh OK.`——`grep -rn "Mesh OK" --include=*.py harnessfoam/` 返回 0 条」（02:1402） | `references/repos/harnessfoam/harnessfoam/validation.py:128` | 证实 | `grep -rn 'Mesh OK' --include='*.py' .` = 0 |
| 38 | 「`should_review :417-431`，读 `parse_physics_diagnostics` 的 7 个布尔」（02:1334） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:417-431` | 证实 | or 链 6 项 + `courant_explosion` 共 7 个键；`:435 route_after_physics_autopilot` 紧随其后（但未被使用，见 §9） |
| 39 | 「Autopilot 改完回 preflight（`graph.py:497`）」（02:1334） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:497` | 证实 | `workflow.add_edge("physics_autopilot", "preflight")` 逐字一致 |
| 40 | 「把一句自然语言需求编译成整套 OpenFOAM-13 字典**并跑到出结果**」（02:1269） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:271` | 无法验证 | 「跑到出结果」要实跑；R12 设计期禁跑，代码只能证明 graph 具备调用 Allrun 的能力 |

**判定统计（40 条）：证实 31 / 部分证实 3 / 证伪 5 / 无法验证 1。**

统计口径（**用第 4 列的精确取值数，不用 `grep -c`**：`grep -c '证实'` 会把「部分证实」一并计入，
且摘要行本身也含该词，得 36/5/6/2 是四个都会虚高的数）。可复现的命令：

```bash
python3 - <<'PY'
import re
rows=[l for l in open('references/04-harnessfoam-deepdive.md',encoding='utf-8').read().split('\n')[75:116] if l.startswith('|')]
cnt={}
for l in rows:
    cells=[c.strip() for c in re.sub(r'\\\|','<P>',l).split('|')[1:-1]]
    if len(cells)>=5 and cells[3] in ('证实','部分证实','证伪','无法验证'):
        cnt[cells[3]]=cnt.get(cells[3],0)+1
print(cnt, sum(cnt.values()))
PY
```
实测输出：`{'证实': 31, '证伪': 5, '部分证实': 3, '无法验证': 1} 40`

数据来源：逐条 `read_file` + `grep -rn` / `grep -c` / `sed -n` / `wc -l`，每条锚点在「源码锚点」列。

## 2 目录与模块职责表

表列：`路径 / 行数 / 职责 / 是否图节点 / 关键锚点`。「是否图节点」一栏：`是` = `add_node` 注册的 9 个之一；`宿主` = 节点函数定义在 `graph.py`、本文件只提供被调用的函数；`否` = 完全不在图上。

### 2.1 `harnessfoam/agents/` 全 11 个 py（`__init__.py` 1 + `graph.py` 1 + `llm_config.py` 1 + 8 个 agent 文件 = 11；表列 10 行，`__init__.py` 只含一行 docstring `"""Agents for HarnessFOAM."""`（30 字节）故不单列）

| 路径 | 行数 | 职责 | 是否图节点 | 关键锚点 |
|---|---|---|---|---|
| `agents/graph.py` | 500 | `SimulationState` 定义、9 个节点函数、4 条条件边、`create_workflow` | 宿主（9 个节点全在此） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:9` |
| `agents/architect.py` | 48 | LLM 出「要写哪些文件」的 plan（Pydantic 结构化） | 否（`architect_node` 调 `plan_simulation`） | `references/repos/harnessfoam/harnessfoam/agents/architect.py:43` |
| `agents/meshing.py` | 97 | 判定 blockMesh 还是 gmsh，gmsh 时返回 `mesh.py` 源码字符串 | 否 | `references/repos/harnessfoam/harnessfoam/agents/meshing.py:43` |
| `agents/input_writer.py` | 140 | 按 plan + review_suggestions 逐文件生成字典内容（返回 dict，不写盘） | 否 | `references/repos/harnessfoam/harnessfoam/agents/input_writer.py:19` |
| `agents/reviewer.py` | 109 | 先跑 `deterministic_suggestions` 再做 LLM 复核；另含 VLM 视觉复核 | 否 | `references/repos/harnessfoam/harnessfoam/agents/reviewer.py:25` |
| `agents/runner.py` | 145 | 生成 Allrun / Slurm 脚本并起子进程跑仿真，逐行收 stdout | 否 | `references/repos/harnessfoam/harnessfoam/agents/runner.py:101` |
| `agents/visualizer.py` | 123 | 生成 PyVista 脚本并本地执行出 `visualization.png` | 否 | `references/repos/harnessfoam/harnessfoam/agents/visualizer.py:93` |
| `agents/physics_autopilot.py` | 139 | 数值发散时按日志打桩改 controlDict/fvSolution（LLM 出补丁） | 否 | `references/repos/harnessfoam/harnessfoam/agents/physics_autopilot.py:43` |
| `agents/optimizer.py` | 89 | 自然语言 → 参数扫描计划 → 调 `run_parameter_sweep`；**不在图上**，见 §9 | 否 | `references/repos/harnessfoam/harnessfoam/agents/optimizer.py:54` |
| `agents/llm_config.py` | 146 | `build_llm`（provider 路由）+ `create_structured_chain`（含 DeepSeek 容错 parser） | 否 | `references/repos/harnessfoam/harnessfoam/agents/llm_config.py:5` |

**02 称「9 节点」但 agents/ 有 8 个 agent 文件（外加 graph.py 与 llm_config.py）——哪些 agent 文件没成为图节点**：`optimizer.py`（有 LLM、有完整业务路径，但 `grep -rn optimizer harnessfoam/` 只命中 `api/mcp_server.py:29` 与 `api/routes.py:433`，没有 `add_node` 引用）与 `llm_config.py`（纯工具，本不该是节点）。`graph.py` 本身不是节点，它是节点的**宿主**：9 个 `def *_node` 全定义在 `graph.py`，`architect.py`/`meshing.py`/… 只提供被节点调用的普通函数。

### 2.2 `harnessfoam/core/` 全 5 个 py（02 只按目录给了 522 行，未展开）

| 路径 | 行数 | 职责 | 是否图节点 | 关键锚点 |
|---|---|---|---|---|
| `core/database.py` | 107 | SQLite 单表 `runs`（case_id / case_dir / prompt / status / state_json），供 MCP 第二套与 API 回读 | 否 | `references/repos/harnessfoam/harnessfoam/core/database.py:19` |
| `core/hpc.py` | 182 | asyncssh 提交 Slurm：打包上传、`sbatch`、`tail -f` 流日志、下载结果 | 否（`runner_node` 的 HPC 分支调） | `references/repos/harnessfoam/harnessfoam/core/hpc.py:12` |
| `core/job_manager.py` | 42 | 内存态 job 队列（`asyncio.Queue`）与 task 表，模块级单例 `job_manager` | 否 | `references/repos/harnessfoam/harnessfoam/core/job_manager.py:42` |
| `core/schemas.py` | 36 | Pydantic 契约：`HPCConfig`/`SimulationRequest`/`SimulationResponse`/`RunStatus`/`UpdateRequest`/`FileContent` | 否 | `references/repos/harnessfoam/harnessfoam/core/schemas.py:4` |
| `core/mcp_server.py` | 155 | 第二套 FastMCP（11 tool），`import` 时即 `init_db()` | 否 | `references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6` |

core 的对外依赖面（`grep -rn 'from harnessfoam.core'`）：`graph.py:199-200`（hpc + schemas）、`main.py:1`（mcp_server）、`api/server.py:96`（job_manager）、`core/mcp_server.py:2`（database）、`core/hpc.py:8`（schemas）。`job_manager` 的队列 API（`get_queue`/`publish`/`subscribe`/`start_job`/`stop_job`/`finish_job`）**没有任何调用点**，`api/server.py` 只直接读写 `.tasks` 这个 dict（`:103`、`:112`、`:141`、`:161-162`）。

### 2.3 顶层 8 个最关键模块

| 路径 | 行数 | 职责 | 是否图节点 | 关键锚点 |
|---|---|---|---|---|
| `validation.py` | 138 | 纯函数门禁：`validate_case_files`（preflight）+ `validate_runtime`（日志）+ 两个日志解析器 | 否（被 preflight / runner 节点调） | `references/repos/harnessfoam/harnessfoam/validation.py:12` |
| `physics_validation.py` | 71 | 读末时刻 `U`/`p` 做 NaN/Inf/量级检查 | 否 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:43` |
| `reference_benchmarks.py` | 21 | cavity 专用 5 条硬阈值 + 开关 | 否 | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:5` |
| `case_manifest.py` | 48 | 版本常量 + 写/读 `.harnessfoam/manifest.json` + 解析日志版本 | 否 | `references/repos/harnessfoam/harnessfoam/case_manifest.py:8` |
| `failure_ledger.py` | 24 | **只读**汇总 `.harnessfoam/failure_ledger.jsonl` | 否 | `references/repos/harnessfoam/harnessfoam/failure_ledger.py:7` |
| `knowledge.py` | 160 | 7 条硬编码知识 + vendored 教程词袋检索（5 facet、去冗余、角色路由） | 否 | `references/repos/harnessfoam/harnessfoam/knowledge.py:17` |
| `memory.py` | 118 | 可选 per-agent markdown 记忆，按「词数」压缩 | 否 | `references/repos/harnessfoam/harnessfoam/memory.py:56` |
| `main.py` | 8 | 入口：直接 `app.run(transport="stdio")` 起**第二套** MCP | 否 | `references/repos/harnessfoam/harnessfoam/main.py:1` |

数据来源：`find ... -name '*.py' | while read f; do wc -l "$f"; done`、`grep -n '^def |^class '`、`grep -rn 'from harnessfoam.core'`。

## 3 执行主干时序（文本流程图）

```
                        ┌─────────────────────────────────────────────┐
                        │ entry_point = "architect"    graph.py:466   │
                        └───────────────────┬─────────────────────────┘
                                            ▼
   architect (456)  ──add_edge 467──▶ meshing (457) ──468──▶ input_writer (458)
        │ 出 plan/file_plan            │ 需要 gmsh 时写 mesh.py           │ 写字典 + 备份
        ▼                              ▼                                ▼
   ──469──▶ preflight (460)  validate_case_files + write_manifest
                                            │
                       route_after_preflight  graph.py:447
                    ┌───────────────────────┴───────────────────────┐
              status==FAILED                                    else
                    ▼                                                ▼
              reviewer (461)                                   runner (459)
                                                                     │
                                              should_review  graph.py:417
                    ┌──────────────┬───────────────┬──────────────┬──┘
              physics_autopilot   review        visualize        fail
                    │              ▼               ▼               ▼
                    │        reviewer (461)   visualizer (463)   end (464)
                    │              │               │
                    │   route_after_review    route_after_visualizer
                    │        graph.py:440        graph.py:450
                    │     ┌────┴────┐         ┌────┴────┐
                    │  meshing  input_writer  reviewer  end
                    ▼
         add_edge 497（静态边，无路由函数）
                    └──────────▶ preflight (460)  ← 回到门禁，不重跑网格

   end (464) ──add_edge 498──▶ END
```

路由函数与行号的完整清单（这是 02 说「3 个条件边」而实际是 4 个的地方）：

| 条件边起点 | 路由函数 | 函数定义行 | `add_conditional_edges` 行 | 目标映射（逐字） |
|---|---|---|---|---|
| `preflight` | `route_after_preflight` | `:447` | `:470-475` | `{"review": reviewer, "physics_autopilot": physics_autopilot, "run": runner}` |
| `runner` | `should_review` | `:417` | `:477-486` | `{"review", "physics_autopilot", "visualize", "fail"}` |
| `reviewer` | `route_after_review` | `:440` | `:487-494` | `{"meshing", "input_writer"}` |
| `visualizer` | `route_after_visualizer` | `:450` | `:495-496` | `{"review", "physics_autopilot", "end"}` |

两处「定义了但接不上」的接线事实（不评价，只记录）：
1. `route_after_physics_autopilot`（`:435-437`，永远 `return "preflight"`）从未被任何 `add_conditional_edges` 引用；`physics_autopilot` 用的是静态边 `:497`。
2. `preflight` 的映射里声明了 `"physics_autopilot"` 目标（`:474`），但 `route_after_preflight`（`:448`）只可能返回 `"review"` 或 `"run"`，该键不可达。

计数器的两处消费者（事实）：`max_errors` 由 `reviewer_node`（`:302` 自增）与 `physics_autopilot_node`（`:390` 自增）共用一个 `errors` 字段；`should_review`（`:418`）用 `errors < max_errors` 判是否还允许重试，`route_after_visualizer`（`:451`）用同一个条件判是否回 reviewer。即「reviewer 轮次」与「autopilot 轮次」不分开计数，两类失败共享 3 次预算。

数据来源：`read_file harnessfoam/agents/graph.py`（全 500 行）+ `grep -n 'add_conditional_edges|add_edge|set_entry_point|add_node'`。

## 4 契约层：清单 / 版本断言 / 三态

### 4.1 版本常量

`references/repos/harnessfoam/harnessfoam/case_manifest.py:8` 逐字：

```
EXPECTED_OPENFOAM_VERSION = "13"
```

全仓对该常量的引用只有 1 处（`grep -rn EXPECTED_OPENFOAM_VERSION`，共 2 命中 = 定义 + 使用）：

| 行 | 逐字 |
|---|---|
| `:8` | `EXPECTED_OPENFOAM_VERSION = "13"` |
| `:22` | `"openfoam_version": EXPECTED_OPENFOAM_VERSION,` |

也就是说：**常量只喂 manifest，不喂门禁**。真正的门禁调用 `validate_runtime(..., expected_version="13")` 在 `graph.py:271`、`benchmark.py:38`、`tutorial_regression.py:39`、`optimization.py:77` 四处**各自写死字符串 `"13"`**，没有一个 import 这个常量。改版本要改 5 个地方（1 定义 + 4 调用点）。

### 4.2 manifest 结构

`write_manifest`（`:19-31`）写出 5 个键，落盘 `.harnessfoam/manifest.json`：

| 键 | 值来源 | 锚点 |
|---|---|---|
| `openfoam_version` | 常量 `"13"` | `references/repos/harnessfoam/harnessfoam/case_manifest.py:22` |
| `solver` | 从 `system/controlDict` 正则抽 `application` | `references/repos/harnessfoam/harnessfoam/case_manifest.py:11` |
| `runtime` | 调用方传参，`preflight_node` 传 `"WSL"` 或 `"Native"` | `references/repos/harnessfoam/harnessfoam/agents/graph.py:166` |
| `tutorial_source` | 三元表达式两支都返回 `"OpenFOAM-13"` | `references/repos/harnessfoam/harnessfoam/case_manifest.py:25` |
| `source` | 调用方传参，默认 `"HarnessFOAM"`，benchmark 传 `"cavity-smoke-benchmark"` | `references/repos/harnessfoam/harnessfoam/benchmark.py:21` |

两处只有形式没有内容的地方：`:25` 的三元表达式 `"OpenFOAM-13" if (…).exists() else "OpenFOAM-13"` 两支同值；`write_manifest` 在 `preflight_ok` 为真时才被调（`graph.py:165-166`），所以 manifest 的**存在本身**就是 preflight 通过的产物。

读侧：`read_manifest`（`:34-42`）在生产代码里**无调用点**，只有 `references/repos/harnessfoam/tests/unit/test_provenance_postprocess.py:13` 用。`parse_openfoam_version`（`:45-47`）同样只在测试里出现。即 manifest 是**只写不读**的痕迹文件。

### 4.3 三态实现

代码里有两种「三态」，都不是 pass/fail 的二值：

**(1) 物理闸的三态**——`(bool, metrics, errors)` 里 `metrics["status"]` 取 `SKIPPED` / `CHECKED`，第三个状态由 `errors` 非空隐含：

| 状态 | 出现位置 | 逐字 | bool 通道 |
|---|---|---|---|
| `SKIPPED`（无数字时间目录） | `references/repos/harnessfoam/harnessfoam/physics_validation.py:46` | `return True, {"status": "SKIPPED", "reason": "No written numeric time directory"}, []` | **True** |
| `SKIPPED`（末时刻无 U 也无 p） | `references/repos/harnessfoam/harnessfoam/physics_validation.py:70` | `return True, {"status": "SKIPPED", "reason": "No U or p field in final time"}, []` | **True** |
| `CHECKED` | `references/repos/harnessfoam/harnessfoam/physics_validation.py:47` | `metrics: Dict[str, object] = {"status": "CHECKED", "time": time_dir.name}` | True / False 由 `errors` 决定（`:71`） |

关键事实：`SKIPPED` 与「检查通过」在**返回值**上是同一个 `True`，三态只存在于 `metrics` 字典里，而调用方 `graph.py:281` 只看 `physics_ok` 这个 bool。三态不进门禁判定。

**(2) 参考闸的三态**——`PASSED` / `FAILED` / `SKIPPED` 写进 `result["status"]`：

| 状态 | 锚点 | 条件 |
|---|---|---|
| `SKIPPED` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:9` | benchmark 参数不是 `cavity`，且 prompt 不含 `cavity` / `lid driven` / `lid-driven` |
| `PASSED` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:20` | `score == 1.0`（5 条全过） |
| `FAILED` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:20` | 任一条不过 |

同 (1)：`SKIPPED` 返回 `True`（`:9`）。

数据来源：`read_file case_manifest.py`（48 行全读）+ `read_file physics_validation.py` + `grep -rn EXPECTED_OPENFOAM_VERSION`。

## 5 门禁实现：逐条判据原文 + 可重算性判定

本节是全文件最重的部分。判据原文一律**逐字**抄自源码，不做等价改写。

### 5.1 preflight（`validate_case_files`，14 条判据 + 2 条死/空判据）

| 检查名 | 源码锚点 | 判据原文（逐字） | 触发条件 | 返回什么 | 可重算? |
|---|---|---|---|---|---|
| 必需文件清单 | `references/repos/harnessfoam/harnessfoam/validation.py:15` | `required = ["system/controlDict", "system/fvSchemes", "system/fvSolution", "system/blockMeshDict", "0/U", "0/p"]` | plan 里没有该路径**且**磁盘上不存在 | `Missing required OpenFOAM file: {path}` | 是 |
| 物性字典二选一 | `references/repos/harnessfoam/harnessfoam/validation.py:19-20` | `if not (os.path.isfile(.../constant/physicalProperties) or os.path.isfile(.../constant/transportProperties)):` → `Missing required OpenFOAM file: constant/physicalProperties (or legacy constant/transportProperties)` | 两个文件都不存在 | 同上错误串 | 是 |
| plan 是否落盘 | `references/repos/harnessfoam/harnessfoam/validation.py:21-25` | `if not os.path.isfile(full_path):` → `Planned file was not written: {path}` | plan 里有、磁盘上没有 | 错误串 | 是 |
| 占位内容 | `references/repos/harnessfoam/harnessfoam/validation.py:27-28` | `if "Mock OpenFOAM content" in content:` → `Placeholder content is not allowed: {path}` | 命中该魔法串 | 错误串 | 是 |
| FoamFile 头 | `references/repos/harnessfoam/harnessfoam/validation.py:29-30` | `if "FoamFile" not in content:` → `Missing FoamFile header: {path}` | 全文无 `FoamFile` 子串 | 错误串 | 是 |
| application 存在 | `references/repos/harnessfoam/harnessfoam/validation.py:35-39` | `match = re.search(r"\bapplication\s+([A-Za-z0-9_]+)\s*;", _read(control))` → 不中则 `system/controlDict has no application entry` | controlDict 存在但无 `application <名>;` | 错误串 + `solver=""` | 是 |
| boundary 段可解析 | `references/repos/harnessfoam/harnessfoam/validation.py:45-49` | `boundary_match = re.search(r"\bboundary\s*\((.*)\)\s*;", block, re.S)` → 不中则 `system/blockMeshDict has no parseable boundary section` | blockMeshDict 存在但 boundary 段抽不出 | 错误串 | 是 |
| patch 集合相等 | `references/repos/harnessfoam/harnessfoam/validation.py:58-59` | `if boundary_match and patches and patches != field_patches:` → `Patch mismatch for 0/{field}: mesh={sorted(patches)}, field={sorted(field_patches)}` | 仅 `0/U` 与 `0/p` 两个场；两集合**不等**（多一个少一个都报） | 错误串 | 是 |
| solver 复查（**死判据**） | `references/repos/harnessfoam/harnessfoam/validation.py:61-62` | `if solver and not re.search(r"\bapplication\s+" + re.escape(solver) + r"\s*;", _read(control)):` → `Unable to confirm solver application` | `solver` 就来自同一文件的同一正则（`:35`），故非空时必然命中 → **永不触发** | — | 是（可算出恒不触发） |
| solver 必需文件 | `references/repos/harnessfoam/harnessfoam/validation.py:63-74` | `solver_requirements = {"simpleFoam": ["constant/turbulenceProperties"], "pimpleFoam": [...], "interFoam": ["0/alpha.water", "constant/g"], ...}` → `{solver} requires {required_path}` | 只对表里 7 个 solver 生效；v13 的 `foamRun -solver <module>` 名（如 `incompressibleFluid`）不在表里 → 不触发 | 错误串 | 是 |
| 空 plan 跳过 | `references/repos/harnessfoam/harnessfoam/validation.py:14` | `paths = [f"{item['folder']}/{item['file']}" for item in plan]` | `plan=[]` 时 `paths=[]`，只剩磁盘检查 + controlDict 检查 | — | 是 |
| U/p 缺失时静默 | `references/repos/harnessfoam/harnessfoam/validation.py:53-54` | `if not os.path.isfile(field_path): continue` | `0/U` 不存在时**跳过** patch 比对（但 :15 已单独报缺失） | — | 是 |
| 返回契约 | `references/repos/harnessfoam/harnessfoam/validation.py:75` | `return not errors, errors` | — | `(bool, List[str])`，**无 metrics 通道** | 是 |

### 5.2 runtime（`validate_runtime`，5 条判据）

| 检查名 | 源码锚点 | 判据原文（逐字） | 触发条件 | 返回什么 | 可重算? |
|---|---|---|---|---|---|
| FATAL 关键字 | `references/repos/harnessfoam/harnessfoam/validation.py:128` | `if re.search(r"FOAM FATAL\|FOAM FATAL IO ERROR\|FOAM aborting", log or "", re.I):` | 合并 stdout 命中任一（大小写不敏感） | `OpenFOAM fatal error reported in solver log` | 是 |
| 完成标记 | `references/repos/harnessfoam/harnessfoam/validation.py:130` | `if not metrics["has_end_marker"]:` | 正则 `:91`：`bool(re.search(r"(?:\nEnd\s*$\|Simulation complete!\s*$)", log or "", re.M))` 未命中 | `Solver log has no completion marker` | 是 |
| 时间步非零 | `references/repos/harnessfoam/harnessfoam/validation.py:132` | `if metrics["time_steps"] == 0:` | `:82` 的 `findall(r"\bTime\s*=\s*([0-9.eE+-]+)")` 长度为 0 | `Solver log contains no time steps` | 是 |
| 版本断言 | `references/repos/harnessfoam/harnessfoam/validation.py:134` | `if expected_version and not re.search(r"\bVersion:\s*" + re.escape(expected_version) + r"\b", log or ""):` | `expected_version` 非空（默认 `""` = 关闭）且日志无 `Version: 13` | `OpenFOAM runtime version {expected_version} was not confirmed in solver log` | 是 |
| Courant 上限 | `references/repos/harnessfoam/harnessfoam/validation.py:136` | `if metrics["max_courant"] is not None and metrics["max_courant"] > max_courant:` | 有 Courant 行且末值 > 1.0（默认 `max_courant: float = 1.0`，`:125`） | `Maximum Courant number is too high: …` | 是 |
| 返回契约 | `references/repos/harnessfoam/harnessfoam/validation.py:138` | `return not errors, metrics, errors` | — | `(bool, metrics dict 8 键, List[str])` | 是 |

版本断言的**已知边界**（02:1400 已指出，我复核成立）：`\b13\b` 对 `Version: 13.1` 成立、对 `Version:  130` 不成立。另有一条实现细节 02 未写：`max_courant` 的取值来自 `parse_runtime_metrics` 的 `max((pair[1] …))`，是**全程最大值**，不是末步值。

### 5.3 物理闸（`validate_physics`，5 条判据 + 2 个 SKIPPED 出口）

| 检查名 | 源码锚点 | 判据原文（逐字） | 触发条件 | 返回什么 | 可重算? |
|---|---|---|---|---|---|
| 无数字时间目录 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:45-46` | `if not time_dir or time_dir == Path(case_dir):` → `return True, {"status": "SKIPPED", "reason": "No written numeric time directory"}, []` | 目录下没有任何「名字可 `float()`」的子目录 | SKIPPED + True | 是（但见下） |
| U 的 NaN/Inf | `references/repos/harnessfoam/harnessfoam/physics_validation.py:56-57` | `if not all(math.isfinite(value) for value in magnitudes):` | 向量模长任一非有限 | `Velocity field contains NaN or Inf` | 是 |
| U 量级上限 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:58-59` | `if any(value > 1e4 for value in magnitudes):` | 任一 `\|U\| > 1e4` | `Velocity magnitude exceeds conservative sanity limit 1e4` | 是 |
| cavity 初速下限 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:60-61` | `if "cavity" in (prompt or "").lower() and solver == "icoFoam" and magnitudes and max(magnitudes) < 0.5:` | prompt 含 `cavity` **且** solver 恰为 `icoFoam` **且** `max\|U\| < 0.5` | `Cavity velocity field never reaches 0.5 m/s despite a 1 m/s moving lid` | 是 |
| p 的 NaN/Inf | `references/repos/harnessfoam/harnessfoam/physics_validation.py:67-68` | `if not all(math.isfinite(value) for value in values):` | 标量场任一非有限 | `Pressure field contains NaN or Inf` | 是 |
| 末时刻无场 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:69-70` | `if not u_path.is_file() and not p_path.is_file():` → `return True, {"status": "SKIPPED", "reason": "No U or p field in final time"}, []` | 末时刻目录里既无 `U` 也无 `p` | SKIPPED + True | 是 |
| 返回契约 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:71` | `return not errors, metrics, errors` | — | `(bool, metrics, errors)` | 是 |

**「无数字时间目录」这条出口在主流水线里不可达，可静态证明**：`_latest_time`（`:31-40`）遍历 case 根的子目录并 `float(child.name)`；`0/` 的 `float("0")` 成功，于是 `max(...)` 至少是 `0.0`，返回值是 `0/` 这个目录、**不等于** `Path(case_dir)`，条件 `time_dir == Path(case_dir)` 不成立。而 `0/U`、`0/p` 是 preflight 的必需文件（`validation.py:15`），所以走到物理闸时 `0/` 必然存在。实际后果：solver 一步都没写场时，物理闸**读的是初场**并按 `CHECKED` 判定；`max|U|` 取初值（cavity 的 lid 是 1 m/s），`< 0.5` 不成立、NaN 也没有 → 通过。

### 5.4 参考闸（`evaluate_reference_case`，开关 + 5 条阈值）

| 检查名 | 源码锚点 | 判据原文（逐字） | 触发条件 | 返回什么 | 可重算? |
|---|---|---|---|---|---|
| 是否启用 | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:8-9` | `if benchmark != "cavity" and "cavity" not in text and "lid driven" not in text and "lid-driven" not in text:` → `return True, {"status": "SKIPPED", "benchmark": "none"}, []` | prompt 措辞里没有 3 个关键词之一 | SKIPPED + True | 是 |
| `openfoam13_final_time` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:11` | `"openfoam13_final_time": float(runtime.get("last_time") or 0) >= 0.5,` | `last_time < 0.5` | 进 `errors` 名字列表 | 是 |
| `courant_below_0.2` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:12` | `"courant_below_0.2": (runtime.get("max_courant") is None or float(runtime["max_courant"]) <= 0.2),` | none 时**视为通过**；有值且 > 0.2 则失败 | 同上 | 是 |
| `continuity_below_1e-6` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:13` | `"continuity_below_1e-6": (runtime.get("max_abs_continuity_error") is None or float(runtime["max_abs_continuity_error"]) <= 1e-6),` | none 时视为通过 | 同上 | 是 |
| `finite_velocity` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:14` | `"finite_velocity": physics.get("status") in ("CHECKED", "SKIPPED") and physics.get("U_max") is not None,` | 状态不在两值内**或** `U_max` 为 None | 同上 | 是 |
| `moving_lid_velocity_reached` | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:15` | `"moving_lid_velocity_reached": (physics.get("U_max") is not None and 0.5 <= float(physics["U_max"]) <= 2.0),` | `U_max` 不在 [0.5, 2.0] | 同上 | 是 |
| 打分与开关 | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:17-20` | `passed = sum(bool(value) for value in checks.values())` / `score = passed / len(checks)` / `"status": "PASSED" if score == 1.0 else "FAILED"` | 全过才 PASSED（无部分分通道） | `(score==1.0, result, errors)` | 是 |
| 两个 `None` 即通过 | 同上 `:12` `:13` | 见原文 | 日志里**没有** Courant 行/continuity 行时 → `None` → 该项自动为 True | — | 是（可算出：solver 不打印该行则该条恒过） |

### 5.5 门禁在节点里的合成方式（谁决定最终 status）

| 环节 | 源码锚点 | 事实 |
|---|---|---|
| 退出码 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:253` | `if returncode != 0:` → `status='FAILED'`，`execution_error = stdout_str[-2000:]` |
| 三道闸只在 returncode==0 分支 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:257` | `else:` 之后才跑 runtime/physics/reference |
| solver 名推断 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:259-267` | 默认 `"icoFoam"`；从 `system/controlDict` 抽 `application\s+(\w+);`，读不到就沿用默认 |
| 三闸合成 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:281-286` | physics/benchmark 的 errors **只追加到 metric_errors**；最终 `SUCCESS if not metric_errors else FAILED`——即三闸里任一错都落到同一个 `metric_errors` 列表，不区分来源 |
| 例外 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:285-289` | `runtime_ok` 为假时单独把 `execution_error` 写成 runtime 的错；physics/benchmark 的错只留在这个局部 `metric_errors` 列表里（三份 metrics 字典进了 `state['logs']`，但错误串列表本身没落 state） |

一条事实：`references/repos/harnessfoam/harnessfoam/agents/graph.py:370-372` 让**视觉模型**能翻最终状态——`if visual_review.get('visual_review_status') == 'FAILED': state['status'] = 'FAILED'`。这是全仓唯一由模型输出直接改写 `status` 的路径；其余 `status` 改写点（`:168` preflight 判失败、`:254` 退出码、`:286` 三闸合成、`:288`、`:291` 异常、`:401`/`:403` autopilot 结果）都只依赖命令输出或纯函数返回值。此条对「判据全确定性」的口径构成限定，可重算性一栏只能是「需模型看」。

### 5.6 视觉闸：判据是「LLM 回答里有没有子串」（编排方复核补入）

上面那条「模型能翻状态」的路径**几乎不会触发**，原因是它的判据写法：

`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100` 逐字：

```
passed = "yes" in response.content.lower() or "correct" in response.content.lower()
```

`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:101` 逐字：

```
return {"visual_inspection_passed": passed, "visual_review_status": "PASSED" if passed else "FAILED", "vlm_feedback": response.content}
```

| 事实 | 依据 |
|---|---|
| 判据是**子串包含**，不是结构化判定 | `reviewer.py:100` 无 JSON schema、无 structured output（`:97` 注释自认「We skip structured output here for broader VLM compatibility」） |
| `"correct"` 是 `"incorrect"` 的子串 → 模型回答「it is **incorrect**」也判 **PASSED** | Python `in` 语义；`"incorrect".find("correct") == 2` |
| 提示词本身含 `correct`（`reviewer.py:92`：`Does it look physically correct?`），模型复述该词的概率高 → 该闸**趋近恒 PASSED** | `reviewer.py:92` 逐字 |
| 只有回答里**既无** `yes` 又**无** `correct`（如 `No.` / `The flow is wrong.`）时才 FAILED | 同一行逻辑 |
| 调用是**无条件**的（只要 `status=='SUCCESS'` 且渲染出图），没有开关 / 没有 `enable_visual` 参数 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:360-368` |
| 无视觉模型时返回 `SKIPPED`（不翻状态、也不报假通过） | `references/repos/harnessfoam/harnessfoam/agents/reviewer.py:104-108`（`except` 分支） |

**本节的两条机制事实**：

1. 四道闸（preflight / runtime / physics / reference）的输入是文件与日志文本，函数体内无 LLM 调用，
   故判定可被脚本复算；第五道（视觉）的输入是 LLM 自由文本，判据是对该文本做子串匹配
   （`reviewer.py:100`）。按本项目 `03-evidence-audit.md` §0.1 的证据分级，前四道对应 E0/E1，
   第五道对应「需模型看」——模型每次回答不同，子串匹配结果随回答变化。
2. `"correct"` 是 `"incorrect"` 的子串，这是 Python `in` 的语义事实。因此当判据写成
   `"yes" in s or "correct" in s` 时，含 `incorrect` 的回答也会命中。这道闸的可重算性等级上限
   是「需模型看」，不随措辞改进而变。

数据来源：`sed -n '79,109p' references/repos/harnessfoam/harnessfoam/agents/reviewer.py`（全文读完）、
`grep -n 'visual_review\|analyze_visual' harnessfoam/agents/graph.py`（无开关，调用点 :364）、
`sed -n '355,380p' harnessfoam/agents/graph.py`。

数据来源：`read_file validation.py`（138 行全读）、`read_file physics_validation.py`、`read_file reference_benchmarks.py`、`read_file agents/graph.py`（全 500 行）、`grep -rn 'Mesh OK' --include=*.py .`（0 命中）。

## 6 失败账本与记忆

### 6.1 failure_ledger：读与写分在两个地方

| 侧 | 位置 | 形态 | 逐字/事实 |
|---|---|---|---|
| 读 | `references/repos/harnessfoam/harnessfoam/failure_ledger.py:7` | 独立模块，24 行，**只有这一个函数** | docstring `:1` 逐字：`"""Read-only summaries of bounded retry trajectories."""` |
| 写 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:316-325` | 内联在 `reviewer_node` 函数体内，`import json` 也在函数体内（`:316`） | 见下 |

写侧逐字（`graph.py:316-325`）：

```
    import json
    ledger_path = os.path.join(state['case_dir'], '.harnessfoam', 'failure_ledger.jsonl')
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    with open(ledger_path, 'a', encoding='utf-8', newline='') as ledger:
        ledger.write(json.dumps({
            'attempt': state['errors'],
            'prompt': state.get('prompt', ''),
            'error': error_logs[-4000:],
            'suggestions': review_results['suggestions'],
        }, ensure_ascii=False) + '\n')
```

读侧数据契约（`failure_ledger.py:7-24`）：入参 `case_dir`，路径固定 `<case_dir>/.harnessfoam/failure_ledger.jsonl`（`:8`）；返回 5 个键 `available` / `attempts` / `suggestions`（各条 `len(suggestions)` 求和，`:20`）/ `latest_error`（最后一条 `error` 的末 500 字符，`:21`）/ `file`；文件不存在或 JSON 解析失败时返回 `available: False`（`:10`、`:23`），**不抛异常**。

读写之间的耦合点（事实，不做评价）：

1. **schema 只在写侧定义**。读侧全程 `item.get(...)`（`:20`、`:21`），没有任何字段名校验；写侧把键名改成 `err` 后，读侧不会报错，只会让 `latest_error` 恒为 `""`。
2. **`import json` 在函数体内**。`graph.py` 顶部（`:1-6`）只 import 了 `typing` / `os` / `langgraph` / `time` / `logging`，`json` 每轮 reviewer 执行时重新 import（Python 有模块缓存，故是风格问题不是性能问题）。
3. **`attempt` 来自 `state['errors']`**，而 `errors` 在 `:302` 先自增，所以第一条记录是 `attempt=1`。
4. **无上限、无轮转**：追加模式，每条都重写整个 `prompt`，`max_errors=3` 时同一 prompt 最多落 3 份。
5. **读侧的唯一生产调用点在写完的下一行**（`graph.py:327`，`state['logs']['failure_ledger_summary'] = summarize_failure_ledger(...)`），再往上是 `api/mcp_server.py:103` 把它拼进 MCP 返回串。没有别的消费者。
6. 该模块的 docstring 自称 read-only、写入端留在 graph 里，两件事是**同一个设计动作的两半**：一个刻意保持无副作用的纯读取器 + 一个「写入必须知道 prompt 和 suggestions、只在这一个节点里可得」的内联写。判断它是有意还是疏漏，超出本文件口径（§0 第 4 条），此处只记录形态。

### 6.2 memory.py：可选、默认关

| 函数 | 锚点 | 落盘路径 / 数据格式 |
|---|---|---|
| `memory_path` | `references/repos/harnessfoam/harnessfoam/memory.py:27` | `<case_dir>/.harnessfoam/memory/<agent>.md`；agent 名做 `re.sub(r"[^a-z0-9_-]+", "_", agent.lower())` 清洗（`:28`） |
| `record_event` | `references/repos/harnessfoam/harnessfoam/memory.py:56` | append 一段 `\n## {outcome.upper()}\n- details: {…}\n`（`:64`），`details` 取末 2500 字符；随后整篇 `_compress` 重写 |
| `record_self_improvement` | `references/repos/harnessfoam/harnessfoam/memory.py:70` | 只是一层封装：`record_event(outcome="recovered", details=f"Observed error: {error[-1000:]}\nRecommended fix: {fix[-1000:]}")`（`:74-75`） |
| `prompt_context` | `references/repos/harnessfoam/harnessfoam/memory.py:48` | 关闭或无记忆时返回 `""`（`:51-52`）；有内容时返回 `"\n\nAgent memory for {agent} (use as lessons, verify against current files):\n{text}\n"`（`:54`） |
| `_compress` | `references/repos/harnessfoam/harnessfoam/memory.py:31` | 词数超限时保留前 2 行 + 一句 `> [Auto-Compressed] Old records folded, keeping only recent experience.` + 末 `max(8, limit//80)` 行，再按词截断（`:36-37`） |

两处实测细节：

- **「token 预算」实为空白分词计数**：`_token_count`（`:24-25`）是 `max(1, len(re.findall(r"\S+", text)))`，即按空白切的词数，不是任何 tokenizer 的 token 数。默认预算 `DEFAULT_TOKEN_LIMITS`（`:9-13`）为 architect 2000 / meshing 2000 / input_writer 4000 / preflight 2500 / runner 2500 / reviewer 3500 / visualizer 2500 / assistant 4000，用户值被钳在 `[256, 20000]`（`:19`）。
- **只有 reviewer 会在失败时写记忆**：`record_self_improvement` 的唯一调用点是 `graph.py:329`，且外面套 `if state.get('memory_enabled')`。其余 agent 只写 `started`/`success`/`failed` 事件（`record_event` 的调用点：`graph.py:47`、`:412`）。
- `end_node`（`:407-415`）在收尾时对 6 个 agent 名批量补写 `outcome`，但列表里**不含** `reviewer` 与 `physics_autopilot`、`end`（`:411` 逐字：`for agent in ('architect', 'meshing', 'input_writer', 'preflight', 'runner', 'visualizer'):`）。

数据来源：`read_file failure_ledger.py`（24 行全读）、`read_file memory.py`（118 行全读）、`grep -n 'record_self_improvement|record_event' harnessfoam/agents/graph.py`。

## 7 工具接口清单

### 7.1 第一套：`api/mcp_server.py`（`mcp = FastMCP("HarnessFOAM")`，8 tool）

| # | tool 名 | 行号 | 参数（逐字签名） | 是否返回门禁结论 |
|---|---|---|---|---|
| 1 | `get_knowledge_status` | `:11` | 无 | 否（返回教程语料统计） |
| 2 | `run_parameter_optimization` | `:18` | `base_case: str, output_root: str, parameters: list, objective: str = "last_time", direction: str = "max"` | 是（每个 case 过 `validate_runtime`，`optimization.py:77-78` 给 PASSED/FAILED） |
| 3 | `run_agentic_optimization` | `:26` | `base_case: str, output_root: str, user_objective: str` | 是（同上，转 `optimizer.run_agentic_optimization`） |
| 4 | `run_cavity_benchmark` | `:34` | `output_dir: str = "tmp_mcp_cavity"` | 是（`benchmark.py:38-39` → PASSED/FAILED + metrics + errors） |
| 5 | `run_cavity_repair_benchmark` | `:41` | `output_dir: str = "tmp_mcp_cavity_repair", execute: bool = False` | 是（`cavity_repair` 调 `validate_case_files`） |
| 6 | `search_repository` | `:48` | `query: str` | 否 |
| 7 | `read_repository_file` | `:55` | `path: str` | 否（异常转 `{"error": …}`） |
| 8 | `run_cfd_simulation` | `:65` | `prompt: str, output_dir: str = "demo_run_mcp"` | 是（返回 `status` + `preflight_ok` + 三个 metrics + ledger summary，`:96-107`） |

### 7.2 第二套：`core/mcp_server.py`（`app = FastMCP("HarnessFOAM-MCP")`，11 tool）

| # | tool 名 | 行号 | 参数（逐字签名） | 是否返回门禁结论 |
|---|---|---|---|---|
| 1 | `create_case` | `:11` | `user_prompt: str` | 否（只建目录 + 落 DB，`status: "CREATED"`） |
| 2 | `plan_simulation_structure` | `:24` | `case_id: str, user_prompt: str` | 否（`case_id` 未使用；`plan_simulation(user_prompt)` 不传 `llm_kwargs`） |
| 3 | `generate_file_content` | `:30` | `case_id: str, file: str, folder: str, user_prompt: str` | 否（只产内容，不写盘、不校验） |
| 4 | `generate_mesh` | `:40` | `case_id: str, mesh_config: dict, user_prompt: str` | 否（`mesh_config` 未使用） |
| 5 | `generate_hpc_script_tool` | `:53` | `case_id: str, hpc_config: dict, user_prompt: str` | 否（`hpc_config` 未使用） |
| 6 | `run_simulation` | `:59` | `case_id: str, environment: str` | 表面是、实为**否**：`:76-77` 跑完图并 `update_run_state` 写库，但 `:80` 返回的是 `:66` 取出的**旧 `job` 快照**（`job["status"]`、`job["logs"]`），调用方拿到的是入图前的状态；非 local/native/wsl/auto 时显式 `UNSUPPORTED`（`:69-71`） |
| 7 | `check_job_status` | `:83` | `job_id: str` | 是（回读 DB 里的 status，`:89`） |
| 8 | `get_simulation_logs` | `:92` | `case_id: str, job_id: str` | 否（`job_id` 未使用，只回 `logs`） |
| 9 | `review_and_suggest_fix` | `:98` | `case_id: str, logs: dict` | 否（模型建议，不判） |
| 10 | `apply_fix` | `:105` | `case_id: str, modifications: list` | 否（返回 `REQUIRES_WORKFLOW_RETRY`，`:145`，明确「改完请重跑再判」） |
| 11 | `generate_visualization` | `:148` | `case_id: str, quantity: str, user_prompt: str` | 否（`quantity` 未使用） |

两套的差异（可核事实）：A 有 3 个 tool 直接返回门禁结论、B 有 2 个；A 里最粗的 `run_cfd_simulation` 一个 tool 跑完整图（`await workflow.ainvoke`，`:83`），B 里最细的 `generate_file_content` 只产一个文件的内容。入口分裂的实证：`harnessfoam mcp` 起的是 A（`cli.py:84-86` → `from harnessfoam.api.mcp_server import start_mcp`），而 `python -m harnessfoam.main` 起的是 B（`main.py:1-2`）；B 的 `import` 期副作用是 `init_db()`（`core/mcp_server.py:7`），会在**当前工作目录**建 `.harnessfoam/harnessfoam.db`（`core/database.py:11` 的默认路径是相对路径）。

`apply_fix` 是唯一带路径逃逸检查的写接口：`os.path.commonpath([case_dir, target]) != case_dir` 即拒（`core/mcp_server.py:127-131`）。

数据来源：`read_file api/mcp_server.py`（113 行全读）、`read_file core/mcp_server.py`（155 行全读）、`grep -c '@mcp.tool()'`（8）、`grep -c '@app.tool()'`（11）。

## 8 版本耦合点（哪些是 v13 假设）

下面这条命令给出本节依据（**注意必须加 `-E`**：`|` 需要扩展正则才当分隔符；不加 `-E` 时该式按字面匹配，返回 0 条——这是本条命令第一版写错的地方）：

```
grep -rnE 'openfoam13|OpenFOAM-13|OpenFOAM 13|Version 13|"13"|/opt/openfoam' --include='*.py' harnessfoam/ | grep -v __pycache__ | wc -l
31
```

表内 18 行为上述 31 行的去重节选（同一文件同一语义的多条合并），**不覆盖全部**。另两条口径供对照：
`grep -rnE 'openfoam13|OpenFOAM-13|OpenFOAM 13' --include='*.py' . | grep -v __pycache__ | wc -l` → **27**；
加 `/opt/openfoam\*` 通配 → **28**。

| 位置 | 逐字 | 形态 | 判定 |
|---|---|---|---|
| `references/repos/harnessfoam/harnessfoam/case_manifest.py:8` | `EXPECTED_OPENFOAM_VERSION = "13"` | 常量 | 硬假设，且**未被门禁复用** |
| `references/repos/harnessfoam/harnessfoam/agents/graph.py:271` | `validate_runtime(stdout_str, expected_version="13")` | 字面量 | 硬假设（可改成参数，未改） |
| `references/repos/harnessfoam/harnessfoam/benchmark.py:38` | `validate_runtime(log, expected_version="13")` | 字面量 | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:39` | `validate_runtime(log, expected_version="13", max_courant=courant_limit)` | 字面量 | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/optimization.py:77` | `validate_runtime(log, expected_version="13") if result else …` | 字面量 | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/validation.py:125` | `expected_version: str = ""` | 默认参数 | **可配置**（默认关闭断言，谁不传谁不查） |
| `references/repos/harnessfoam/harnessfoam/agents/runner.py:75` | `for foamrc in /opt/openfoam13/etc/bashrc /opt/openfoam*/etc/bashrc; do` | 路径 + 通配回退 | 半可配置（优先 13，回退到任意 `/opt/openfoam*`） |
| `references/repos/harnessfoam/harnessfoam/benchmark.py:24` | `. /opt/openfoam13/etc/bashrc` | 硬路径，无回退 | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:29` | `source = f"/opt/openfoam13/tutorials/{relative}"` | 硬路径 | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:32` | `source /opt/openfoam13/etc/bashrc` | 硬路径 | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/api/routes.py:458` | `. /opt/openfoam13/etc/bashrc >/dev/null 2>&1 && command -v blockMesh` | 硬路径（探活） | 硬假设 |
| `references/repos/harnessfoam/harnessfoam/api/server.py:275-278` | `if [ -f /opt/openfoam13/etc/bashrc ]` … `for foamrc in /opt/openfoam*/etc/bashrc` | 路径 + 通配回退 | 半可配置 |
| `references/repos/harnessfoam/harnessfoam/knowledge.py:46` | 探测 `$FOAM_TUTORIALS` → `/opt/openfoam13/tutorials` → `/usr/share/openfoam/tutorials` | 三级探测 | 半可配置（顺序写死） |
| `references/repos/harnessfoam/harnessfoam/knowledge.py:29` | `"version": "OpenFOAM-13"` | 统计标签 | 字面标签，不参与判定 |
| `references/repos/harnessfoam/harnessfoam/case_manifest.py:25` | `"tutorial_source": "OpenFOAM-13" if … else "OpenFOAM-13"` | 三元两支同值 | 硬假设（形式上有分支） |
| `references/repos/harnessfoam/harnessfoam/agents/architect.py:31` | `For OpenFOAM 13 incompressible cases use physicalProperties (legacy releases may use transportProperties)` | prompt 文本 | 硬假设，但**写进了 LLM 提示词**——这是它让 LLM 知道 v13 的唯一通道 |
| `references/repos/harnessfoam/harnessfoam/cases/cavity.py:44` | `# OpenFOAM 13 uses physicalProperties for icoFoam transport data.` | 注释 | 说明性，无运行时作用 |
| `references/repos/harnessfoam/README.md:13` | `[![OpenFOAM](…badge/OpenFOAM-Compatible-darkgreen)]` | badge | 无版本号（与实现不一致处，见下） |

一条横跨全表的耦合事实：**版本进 case 有两条路，一条是字典（`physicalProperties` vs `transportProperties`，`validation.py:19-20` 两者都接受），一条是提示词（`architect.py:31`）。两条都不是从 `EXPECTED_OPENFOAM_VERSION` 派生的**——把常量改成 `"14"` 不会改变生成的字典语法，也不会改变提示词里的 `OpenFOAM 13`。

另一条：`tutorial_regression.py:38` 的 Courant 上限按教程名硬编码 `10.0 / 1.2 / 1.0`（`courant_limit = 10.0 if name == "pitzDaily" else (1.2 if name == "damBreak" else 1.0)`），与 `validate_runtime` 的默认 1.0 并存，两个默认值来源不同。

数据来源（**命令与数字一一对应，重跑可复现**）：
- 全仓版本字串出现行数（`*.py`，排除 `__pycache__`）：
  `grep -rnE 'openfoam13|OpenFOAM-13|OpenFOAM 13' --include='*.py' . | grep -v __pycache__ | wc -l` → **27**
  （加 `/opt/openfoam*` 通配变体 `grep -rnE 'openfoam13|OpenFOAM-13|OpenFOAM 13|/opt/openfoam\*' … | wc -l` → **28**）
- 上表 18 行为上述 27/28 行的去重节选（同一文件同一语义的多条合并），**不覆盖全部**；
  另单独核：`grep -rn 'requires-python' pyproject.toml` → `:8 requires-python = ">=3.10"`。

## 9 可迁移件三档 + 它没做的事

### 9.1 三档

| 档 | 条目 | 锚点 | 为什么属这一档 |
|---|---|---|---|
| 可直接搬 | `validate_runtime` 的五条判据（吃字符串、返 `(bool, metrics, errors)`） | `references/repos/harnessfoam/harnessfoam/validation.py:125-138` | 入参只有 log 文本，无路径、无 LLM、无子进程；改个正则就能当 G3 |
| 可直接搬 | patch 集合**相等**比对（不是子集） | `references/repos/harnessfoam/harnessfoam/validation.py:41-59` | 纯正则 + set，两集合不等就报并打印两侧排序结果 |
| 可直接搬 | 「完成标记 + 时间步非零」两条 | `references/repos/harnessfoam/harnessfoam/validation.py:91` `/132` | 补的是「退出 0 但一步没写」这个空洞，正则即判据 |
| 可直接搬 | `(bool, metrics, errors)` 三返回值契约 | `references/repos/harnessfoam/harnessfoam/validation.py:75` | 让判据与「报告」同源，调用方不必二次解析日志 |
| 可直接搬 | JSONL 失败账本的四字段 schema | `references/repos/harnessfoam/harnessfoam/agents/graph.py:320-325` | `attempt/prompt/error/suggestions` 四键够复现，且追加写、一条一行 |
| 可直接搬 | 纯读取器与写入点分离的边界 | `references/repos/harnessfoam/harnessfoam/failure_ledger.py:7` | 读侧不抛异常、返回 `available` 标志，可安全嵌进报告生成 |
| 需改 | `solver_requirements` 表（7 个 v10 可执行名） | `references/repos/harnessfoam/harnessfoam/validation.py:63-74` | 表里是 `simpleFoam/interFoam/buoyantSimpleFoam…`；v13 主线用 `foamRun -solver incompressibleFluid` 这类 module 名，键得重写，且表里没有 module 名 |
| 需改 | 版本断言正则 | `references/repos/harnessfoam/harnessfoam/validation.py:134` | `\b13\b` 的匹配集合包含 `Version: 13.1`（`\b` 在 `3` 与 `.` 之间成立）；只匹配 `13` 单值的形态是 `\bVersion:\s*13\s*$`——原式与该形态的差异在匹配集合，不在实现质量 |
| 需改 | `Allrun` 生成模板（blockMesh → checkMesh → 裸 solver 名） | `references/repos/harnessfoam/harnessfoam/agents/runner.py:69-98` | 直接执行 `{solver_name}`；v13 主线是 `foamRun`，多区域要 `foamMultiRun` |
| 需改 | 全部 WSL 调用面 | `references/repos/harnessfoam/harnessfoam/agents/runner.py:110` | `["wsl","bash","-lc",…]`；`benchmark.py:32-33` 与 `tutorial_regression.py:25-26` 在无 `wsl` 时直接 `UNSUPPORTED`，纯 Linux 上整条回归链失效 |
| 需改 | 备份与账本落在 case 目录内 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:139` | `.harnessfoam/` 在 case 里，会污染「case 有几个文件」这类统计，也让 case 不可只读共享 |
| 需改 | cavity 参考阈值 | `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:11-15` | 值是 cavity 专用常数（`>=0.5`、`<=0.2`、`<=1e-6`、`[0.5,2.0]`），换 case 必须重定标 |
| 需改 | 物理闸的「末时刻」选择 | `references/repos/harnessfoam/harnessfoam/physics_validation.py:31-40` | 靠目录名 `float()`，`0/` 也算，导致「一步没写」时判初场 |
| 不可搬 | 9 节点 LangGraph + 6 个 LLM 角色 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:456-464` | 每节点一次带 RAG 上下文的 LLM 调用；判据在命令输出里，多角色只加失败面 |
| 不可搬 | 双 MCP server（8 + 11 tool） | `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8` | 没有第二个消费者；且两套粒度带来「谁是权威」问题（`cli.py:84` 起 A、`main.py:1` 起 B） |
| 不可搬 | `cases/cavity.py` 自带 case 生成器 | `references/repos/harnessfoam/harnessfoam/cases/cavity.py:5` | 把整套字典写成 Python 字符串，与 R3「必须从 tutorial 派生」相反 |
| 不可搬 | `optimizer.py` 的 agentic sweep | `references/repos/harnessfoam/harnessfoam/agents/optimizer.py:54` | 依赖 LLM 结构化输出 + WSL 子进程 + 一个已存在的 base_case，三者都不是我们 M1 的约束 |
| 不可搬 | Web 一键装 OpenFOAM | `references/repos/harnessfoam/harnessfoam/utils/installer.py:42` | 该行代码为 `subprocess.run(["sudo", "apt-get", "install", "-y", "openfoam"], check=True)`（列表参数形式，非字面串）；`:45` 为 `subprocess.run(["docker", "pull", "openfoam/openfoam10-paraview510"], check=True)`；`:41` 另有 `apt-get update`。脚本内直接装第二份 OpenFOAM / 拉 openfoam10 镜像，与 R11 冲突 |
| 不可搬 | 视觉模型翻状态 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:370-372` | 模型输出进 pass/fail 通道，与「没有独立判据就写没有」冲突 |

### 9.2 它没做的事（从代码里看得出的缺失，逐条给锚点）

1. **两条最重要的判据没有任何测试**。`grep -rln 'validate_case_files' tests/` = 0 个文件，`grep -rln 'validate_runtime' tests/` = 0 个文件（34 个测试 py 里一个都没有）。对照：路由有 `tests/unit/test_graph_routing.py`（66 行，断言 `should_review` 的 4 个分支）、物理闸有 `tests/unit/test_physics_validation.py`（13 行）、参考闸有 `tests/unit/test_reference_benchmarks.py`（20 行）。即：**判据里最大的一块（14 条 preflight + 5 条 runtime）零覆盖**，而它恰恰是全仓判据的主体。
2. **`validation.py:61-62` 的 solver 复查是死判据**。`solver` 从 `:35` 的同一个正则取，取到才非空；拿它再回同一个文件匹配 `\bapplication\s+{solver}\s*;` 必然命中。这条 `Unable to confirm solver application` 在数学上不可能出现（除非文件在两次 `_read` 之间被改）。它给人「复查过 solver」的印象，实际没查第二件事（比如 solver 名是否属于 v13 的 module 名单）。
3. **gmsh 路径与 preflight 的必需文件表直接冲突**。`:15` 无条件要求 `system/blockMeshDict`；`:45-49` 还要求它能解析出 `boundary (...)` 段。而 `runner.py:81-85` 在有 `mesh.py` 时走 `gmshToFoam mesh.msh`，根本不用 blockMeshDict。结果是「提示词说要 gmsh 网格」的 case 会在 preflight 因为缺 blockMeshDict 被判失败，代码里没有分支区分这两条路。【待定：plan 是否仍会列出 `system/blockMeshDict`——plan 内容由 LLM 在运行时产出，静态读代码无法确定；若列出了而模型又没写该文件，`:24` 会额外报「Planned file was not written」，失败原因会是双份】
4. **HPC 分支缺 `import asyncio`**。`graph.py:225` 与 `:228` 用 `asyncio.run_coroutine_threadsafe` / `asyncio.run`，但模块顶部 `:1-6` 没有 `import asyncio`（`grep -n 'import asyncio' graph.py` 无命中）。该分支一旦走到就 `NameError`，被 `:290` 的 `except Exception` 吞成 `status='FAILED'` + `execution_error='name 'asyncio' is not defined'`。这条分支还有 `:230` 把日志换成常量的既有事实，两者叠加 → HPC 通道既跑不通、也无法用日志判定。
5. **「一步没写」的 case 会被物理闸判成 `CHECKED`**（§5.3 已证明）：`0/` 是数字目录，`_latest_time` 取到它，于是读初场；cavity 初场 `max|U|=1.0` 既非 NaN 也不 `<0.5`，两条阈值都过。真正想要的 `SKIPPED`（`:46`）永不触发。缺的是「末时刻必须 > 0」这条判据。
6. **provenance 只写不读**。`write_manifest` 在 `preflight_ok` 时写（`graph.py:166`），但 `read_manifest`（`case_manifest.py:34`）与 `parse_openfoam_version`（`:45`）在生产代码零调用，只有测试用。于是 `.harnessfoam/manifest.json` 里那个 `"openfoam_version": "13"` 永远等于常量，不会被任何代码拿去和实际日志比对——02:1380 的结论成立，此处补上「为什么」：读函数根本没接上。
7. **两处死路由**。`route_after_physics_autopilot`（`:435-437`）从未被 `add_conditional_edges` 引用；`preflight` 的条件边映射里声明了 `"physics_autopilot"` 目标（`:474`）但 `route_after_preflight`（`:448`）只会返回 `review`/`run`。读图的人会以为「preflight 失败可以进 autopilot」，实际不行。
8. **`optimizer.py` 完全在图外，且没有自己的门禁**。它在 `api/mcp_server.py:29` 与 `api/routes.py:433` 被直接调用。**两个口径要分清**：`grep -rn optimizer harnessfoam/` = **2 条**（就是上面这两处 import）；`grep -rn optimizer --include='*.py' .` = **5 条** = 上述 2 条 + `tests/test_optimizer.py` 的 3 条（`:3`/`:11`/`:12`）。注意 `agents/optimizer.py` 自身在这个 grep 下是 **0 条**（该文件正文里没有 `optimizer` 这个字符串），所以「5 条含自身定义」的说法是错的。**两个口径下都没有一条来自 `graph.py`**——这才是「它在图外」的判据。它的「优化」判定复用 `validate_runtime`（经 `optimization.py:77`），但**`agentic` 这一层（自然语言 → 参数表）没有任何确定性校验**：`generate_sweep_plan`（`optimizer.py:38`）让 LLM 直接给 `path/key/values`，`_inject`（`optimization.py:25-38`）只检查路径逃逸与「正则命中 1 次」，不检查被改的键是否真的影响该 solver。另外这条路径拿不到 `llm_kwargs` 参数传递（`api/mcp_server.py:30` 不传、`api/routes.py:434` 不传），所以外部无法为优化选模型。
9. **判据里没有 `Mesh OK.`**：`grep -rn 'Mesh OK' --include='*.py' .` = 0。checkMesh 的质量判定完全退回 `set -e`（`runner.py:70`）→ 退出码。02:1402 已写，我复核成立；补一条：`knowledge.py:22` 的知识条目里反而写了 `Run checkMesh after mesh generation`，即**知识层知道要检查、判据层没有实现**。
10. **失败账本只记 reviewer 轮，不记 autopilot 轮**。写入点唯一（`:316-325`，在 `reviewer_node` 内）；`physics_autopilot_node` 也自增 `errors`（`:390`）但**不落账本**，所以「第几轮发生了什么」在发散路径上是缺的——账本的 `attempt` 字段与真实尝试次数在发散路径上会出现跳号。
11. **视觉闸的判据是子串匹配，`"correct" ∈ "incorrect"`**（见 §5.6）。这使得「视觉物理复核」这一层在最该报警的回答形态（`it is incorrect`）下判 `PASSED`。它是全仓第五道闸，也是唯一一道输入含 LLM 自由文本的闸；前四道（preflight / runtime / physics / reference）都是纯函数。
12. **判据的测试覆盖是倒挂的**：路由（`should_review` 的 4 个分支）有 66 行单测、物理闸有 13 行、参考闸有 20 行，而**主体判据零覆盖**——`grep -rln 'validate_case_files' tests/` = 0、`grep -rln 'validate_runtime' tests/` = 0（34 个测试 py 里一个都没有）。即「最多判据的那一块」与「最少测试的那一块」是同一块。

数据来源：`grep -rln 'validate_case_files' tests/`（0）、`grep -rln 'validate_runtime' tests/`（0）、`grep -rn 'import asyncio' harnessfoam/agents/graph.py`（无命中）、`grep -rn 'subprocess\.\(run\|Popen\)'`、`grep -rn 'optimizer' --include=*.py .`（5 条）、`read_file` 各文件全文。
