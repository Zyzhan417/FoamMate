# 五、横向矩阵与稳定架构候选

> 注意：`references/02-architectures.md` 已有 8 列汇总矩阵（第 1214–1223 行、2099–2108 行）。
> 本文件**不重做它**，只做三件事：① 补它没有的维度；② 把它变成「稳定性评级」；③ 给出反例。
> 任何与 02 文字高度重合的句子都必须删掉，只允许「引用 + 扩展」。

## 0 口径：K/E/V 三维修判定（本段已冻结，后续不得放宽）

三个维度各自独立打分，**禁止合成为一个总分**（合成会掩盖「广泛但无效」与「罕见但已被消融证明」两种相反情况）。

| 维 | 含义 | 记法 |
|---|---|---|
| **K** | 收敛度：在多少个**互不相关的独立实现**里出现同一机制 | 整数；同源代码计为 1 |
| **E** | 证据强度：是否有对照/消融/失败统计支持它起作用 | `有对照` / `仅实现` / `无` |
| **V** | 版本无关性：机制是否绑定某个 OpenFOAM 版本或某个模型 API | `无关` / `绑 <对象>` |

**同源判定（K 计数前必须先做）**：
- `references/repos/cfd-agent` 与 docs_only 的 ChatCFD 是同一份代码 → 计 1。
- Foam-Agent 与 AI-CFD-Scientist 同出 csml-rpi，后者基于前者 → 计 1。
- `2503.01273`（OptMetaOpenFOAM）与 MetaOpenFOAM 同仓 → 计 1。

**评级（三档，不用分数）**：
- **强** = K≥3 且 E=`有对照` 且 V=`无关`
- **中** = K≥2，或 E 弱，或 V 绑定（V 绑定一律最多「中」，且必须写出绑定对象）
- **弱** = K=1，或 E=`无`

本文件禁止出现「更优 / 更强 / 更好」这类比较词；只允许「强 / 中 / 弱」三档清单。
（用户 2026-10-28 决策：不出排名，只按理论分三档。）

## 1 主表（9 列）

> 表列前 7 项是 `references/02-architectures.md:1216-1222` 与 `references/02-architectures.md:2101-2108` 两张 8 列矩阵的**压缩重排**（展开论证见 02 各项目小节，本表不重做）。
> **增量只有第 8、9 两列**：「状态与记忆」「终止条件」是 02 没有系统化的两列，锚点全部自己回切。
> docs_only 两项（chatcfd、openfoamgpt）的**每一格都标「（文档级）」**——其实现细节无源码证据（`references/03-evidence-audit.md` §4 黑名单第 5 条）。

| 项目 | 知识来源形态 | 工具接口形态 | 编排拓扑 | 反馈与自修正 | 成功判据 | 状态与记忆 | 终止条件 | 版本绑定 |
|---|---|---|---|---|---|---|---|---|
| foam-agent | 4 条 FAISS 索引 × 2 套版本语料，一 case 一块；raw 文件是 LFS 指针（133 字节），须用本机 tutorials 重建（据 02:1218，明细见 02:140、02:162、02:1240） | MCP 7 tool，粒度=流水线阶段；流水线内无 function calling（据 02:1218、02:83、02:122） | 单图 8 节点 + 1 条回边（LangGraph）（据 02:1218、02:54） | 有：进程重试 1 次 + LLM 修复环 + 错误指纹去重（据 02:1218、02:172） | 仅「无 `ERROR:` 正则命中且退出码 0」，无独立判据（据 02:1218） | 共享 `GraphState` TypedDict（`references/repos/foam-agent/src/utils.py:878`），30+ 字段、纯进程内不落盘；无跨任务记忆 | `max_loop=25`（`references/repos/foam-agent/src/config.py:11`）＋指纹重复即停（`references/repos/foam-agent/src/nodes/reviewer_node.py:23`）＋`recursion_limit=100`（`references/repos/foam-agent/src/config.py:19`）；落 `termination_reason="max_review_loop_reached"`（`references/repos/foam-agent/src/nodes/reviewer_node.py:79`） | v10 基镜（`references/repos/foam-agent/docker/Dockerfile:2`）＋esi-v2006 双 target；默认 `openfoam_target=""` 时不校验（`references/repos/foam-agent/src/config.py:46`） |
| metaopenfoam | FAISS 4 库，一文件块一 Document，k=2，语料=v10 tutorials（据 02:1219） | 无（纯 prompt，由 Action 代码执行）（据 02:1219） | 5 角色消息总线（MetaGPT `Environment`）（据 02:1219） | 有：3 个独立计数器，`max_loop=20`，无指纹（据 02:1219） | `Executability` 0/1/2/3，3 = `endTime` 目录存在（据 02:1220） | MetaGPT `Message` 池，靠 `cause_by` 路由；InputWriter 用「内容是数字的那条消息」切上下文（`references/repos/metaopenfoam/src/roles/InputWriter.py:27`）→ 状态是字符串消息而非结构化清单；无跨任务记忆 | `max_loop=20`（`references/repos/metaopenfoam/src/config_path.py:32`）＋三计数器 `Run_loop`/`Postprocess_loop`/`Postprocess_python_loop`（`references/repos/metaopenfoam/src/actions/ReviewerAction.py:456`）＋`while not env.is_idle`（`references/repos/metaopenfoam/src/OptMetaOpenfoam.py:73`） | openfoam10 语料（`references/repos/metaopenfoam/src/Tutorial_postprocess.py:1`） |
| openfoam-mcp-server | 硬编码 C++ 模板 + 概念图谱，无检索（据 02:1220） | MCP 12 tool（主程序实际注册 9）（据 02:1220） | 无 agent 循环；工具层，规划外包给客户端（据 02:1220） | 无（try/catch 打包返回）（据 02:1220） | `blockMesh` 与 solver 两个退出码；solver 由默认构造固定为 `simpleFoam`（据 02:1221；`references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:56`） | 进程内 `caseResults_` map（`references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:95`），重启即失；无跨任务记忆 | 无轮数概念可终止——一次工具调用内 `runCase` 顺序跑 `blockMesh` 再跑 solver 后返回（`references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:947` 默认参数构造、`:949` 取 `params.solver`） | 编译期绑 `/opt/openfoam12`（`references/repos/openfoam-mcp-server/CMakeLists.txt:12`） |
| nullflux | 本机 tutorials 实时关键词检索（topK=12）+ 15 条错误正则 + skills 卡（据 02:1221） | function calling 91 tool（含 5 个 `*_verify`）（据 02:1221） | 单 agent + 阶段状态机（`run_stage_*`）+ watchdog 熔断（据 02:1221） | 有：阶段返工 ≤3 / 工具熔断 5 次 / 6h 上限（据 02:1222） | 网格：`Mesh OK.` + 5 条阈值（硬）；求解：VLM 判残差 + 渲染图（失败闭合）（据 02:1222） | 阶段状态写 `runs/<runId>/state.json`，可断点续跑（`references/repos/nullflux/server.js:323` 的工具描述原文）；跨任务记忆=skills 卡，且只有本轮有 verifier 通过才允许落盘（`references/repos/nullflux/server.js:3719`）；项目记忆仅 README 宣称、实现在混淆 bundle 内（据 02:1240） | 阶段返工 ≤3 次后整体记 `run_stage_done({passed:false})` 并向用户报告（`references/repos/nullflux/server.js:4643`）＋`WATCHDOG` 单工具 5 次 / 6h（`references/repos/nullflux/server.js:3400`） | 推荐 v2306+（`references/repos/nullflux/docs/index.html:634`）；路径正则能匹配 `openfoam13`，故版本可探测（据 02:1235） |
| cfd-agent（与 ChatCFD 同源） | 460 例结构化 JSON，四级回退，`random.sample` 截断（据 02:1222） | 无（据 02:1222） | 单 agent 显式状态机（11 步）+ 可选 2 阶段 Pipeline（据 02:1222） | 有：按同一错误连续次数分档（2 反思 / 4 重写），max 30（据 02:1222） | 退出码 0 + `FOAM FATAL` 关键字；本地模式因输出重定向而失效（据 02:1223） | 可变 `CaseState` dataclass + `StateUpdate` dict；唯一「记忆」是连续同错计数，只比错误文本前 100 字符（`references/repos/cfd-agent/src/state.py:188`），无跨任务记忆 | `max_attempts=30`（`references/repos/cfd-agent/src/state.py:124`）＋`consecutive >= 4` 升级为重写（`references/repos/cfd-agent/src/workflow.py:118`） | v2406 且绑 `database_OFv24`（`references/repos/cfd-agent/ReadMe.md:78`） |
| ai-cfd-scientist（与 Foam-Agent 同源） | 文献 API（S2）+ 继承 Foam-Agent 的 FAISS/v10 语料 + `prompts/prompts.yaml`（据 02:1084） | 无 function calling；工具= `scripts/*.py`，按 AGENTS.md 次序调用（据 02:1223） | Stage 0–7 脚本流水线 + 内层 vendored Foam-Agent 环（据 02:1223） | 有：内层 10 轮 + 判读层 `RERUN` 时整 case 重来（据 02:1223） | 三层：求解 `error_logs` 空 / 网格扫 `***` 行 / 物理层 LLM 读图（据 02:34） | stage 之间不共享内存，只通过磁盘 JSON 交接（`lit.json`→…→`analysis.json`），每次交接可审计（据 02:1070） | 内层 `max_loops=10`（`references/repos/ai-cfd-scientist/scripts/foam_run.py:1261`）＋判读层三态出口（`references/repos/ai-cfd-scientist/scripts/interpret.py:58`） | OF 10（`references/repos/ai-cfd-scientist/README.md:282`），且同级硬依赖 Foam-Agent 目录 → 版本依赖嵌套 |
| harnessfoam | 词袋检索：7 条硬编码 + 20 文件名白名单 tutorial（块=文件，前 6000 字符，k=4）（据 02:2103） | 双 MCP（8 tool + 11 tool）+ REST 30 路由（据 02:2103） | LangGraph 9 节点，**4 条**条件边（02:2103 写 3 条，按 `grep -c` 修正，见 04 §1.2 #2） | 有：3 轮 + 整目录备份 + `failure_ledger.jsonl`（据 02:2103） | 退出码 + 日志 5 判据 + cavity 5 阈值；另加第五道视觉闸（子串匹配，见 §4） | `SimulationState` TypedDict（`references/repos/harnessfoam/harnessfoam/agents/graph.py:9`）＋`.harnessfoam/manifest.json`（`references/repos/harnessfoam/harnessfoam/case_manifest.py:22`）＋按 attempt 整目录备份＋失败账本（`references/repos/harnessfoam/harnessfoam/agents/graph.py:317`）＋可选 per-agent 记忆（`references/repos/harnessfoam/README.md:65`，默认关） | `max_errors=3`（`references/repos/harnessfoam/harnessfoam/agents/graph.py:68`）→ 轮数到顶标 `RETRY_EXHAUSTED`（`references/repos/harnessfoam/harnessfoam/agents/graph.py:312`） | 13（`references/repos/harnessfoam/harnessfoam/validation.py:134` 正则断言 + `references/repos/harnessfoam/harnessfoam/case_manifest.py:8` 常量） |
| autofoam | Chroma + `bge-small-en-v1.5`，按文件角色切 5 类块，`n_results=3` + 1276 行字典模板（据 02:2104） | 无（CLI + Python API + gradio）（据 02:2104） | 单 agent 8 段流水线（无框架）（据 02:2104） | 有：3 轮 + FATAL 单文件 `dict_fix` + 立即重跑（据 02:2104） | 加权分 ≥0.5（据 02:2104） | `CFDParams`（pydantic）+ `RunResult`，纯进程内；每轮独立目录可回看（`references/repos/autofoam/openfoam_agent/agent.py:94`），无跨任务记忆 | `max_retries=3`（`references/repos/autofoam/openfoam_agent/agent.py:68`）＋`score >= 0.5` 收（`references/repos/autofoam/openfoam_agent/agent.py:273`）；`RETRY_SCORE_THRESHOLD=0.7` 决定是否再试（`references/repos/autofoam/openfoam_agent/config.py:26`） | v2412（`references/repos/autofoam/README.md:152`）；`references/repos/autofoam/openfoam_agent/config.py:6` 写死作者机器的 conda bashrc 绝对路径 |
| deepflow | FAISS + `text-embedding-3-small`；requirements 缺 `faiss-cpu` → RAG 实际不成立（据 02:2104） | 11 个 `@tool`（实际可见 10）（据 02:2104） | 单 ReAct（LangChain `AgentExecutor`）（据 02:2105） | 无（规则全写在 prompt 里）（据 02:2105） | 无独立判据（LLM 读 `--- Exit Code: N ---`）（据 02:2105） | 只有 `chat_history` 最近 20 条（`references/repos/deepflow/deepflow_agent/openfoam_agent.py:396`），不落盘、无账本 | `AgentExecutor` 未传 `max_iterations`（`references/repos/deepflow/deepflow_agent/openfoam_agent.py:299`）→ 用框架默认，无上限记录 | v2412（`references/repos/deepflow/README.md:146`）；代码无版本常量，实际跑哪版不可控（据 02:1670） |
| hpc-skills | 272 篇 md + 手写路由表（无检索、无索引）（据 02:2105） | 无（4 个 argparse CLI + 模板文件）（据 02:2105） | 无 agent（宿主驱动，渐进加载）（据 02:2105） | 无（替代物是文本决策树，据 02:1761） | 无实现（只给判据清单：checkMesh 70°/85°、dry-start）（据 02:2105） | 仓库不定义状态、不定义角色、不定义轮数（据 02:1733） | 不定义——重试策略整块留给宿主（据 02:1763） | 未统一；唯一版本串在模板（`references/repos/hpc-skills/skills/hpc-openfoam/assets/templates/simplefoam-minimal/README.txt:1` = OpenFOAM-11） |
| chatcfd | （文档级）结构化 JSON db1–db4 + FAISS `all-mpnet-base-v2`，参考文件固定 2 个（据 02:2105） | （文档级）未公布，摘要自称 MCP-compatible（据 02:1872） | （文档级）多 agent 双模型（R1 推理 / V3 执行）（据 02:2106） | （文档级）有：≤30 轮，持久错误写 `<reflexion>` 块（据 02:2106） | （文档级）「无错文件 + 跑到收敛」；物理保真为人工三级评审（据 02:2106） | （文档级）`ContextRetriever` 把当前配置与修改轨迹编成 JSON + `<reflexion>` 反思历史（据 02:1868） | （文档级）`max_running_test_round=30`，论文称超 75%（约 22 轮）后基本修不好（据 02:1900） | （文档级）v2406 硬绑定（据 02:1923） |
| openfoamgpt | （文档级）单一 RAG，1536 维 `text-embedding-3-small`，语料=tutorial case 描述（据 02:2106） | （文档级）未公布（无 tool 名、无 MCP）（据 02:2014） | （文档级）planner-executor + 内层 agent（据 02:2107） | （文档级）有：错误数据追加到用户 query 后迭代（据 02:2107） | （文档级）论文未报告独立判据，只有循环退出条件（据 02:2045） | （文档级）无结构化状态，错误数据直接追加到 user query（据 02:2035） | （文档级）论文未给轮数上限，只报实测 1–10 轮（据 02:2107） | （文档级）v2406 + OpenAI API（4o / o1-preview）（据 02:2057） |

数据来源：前 7 列 `sed -n '1216,1222p;2101,2108p' references/02-architectures.md`；第 8、9 列逐条 `for a in "<path>:<N>" …; do p=${a%:*}; l=${a##*:}; sed -n "${l}p" "$p"; done`（本表用到的 40 余条 path:line 全部如此回切，回切清单见 §2 表下注）。

**两处 02 已被证伪、本表不沿用的说法**（详见 `references/04-harnessfoam-deepdive.md` §1.2）：
- 「harnessfoam 3 个条件边」→ 实为 4 条（`grep -c 'add_conditional_edges'` = 4，行 470/477/487/495）。
- 「`pyproject.toml:9 requires-python`」→ 在 `:8`（`:9` 是 `description`）。
另：本表**未**引用 02 那两处已被证伪的断言（「只有 `agents/` 调 LLM」、「只有 4 处起子进程」），涉及处一律改用 04 的实测结论。

## 2 补充表（体量 / 可重算性 / tier）

体量实测（10 个 full 仓全跑，命令与输出逐字复制）：

```
$ for d in foam-agent metaopenfoam openfoam-mcp-server nullflux cfd-agent ai-cfd-scientist harnessfoam autofoam deepflow hpc-skills; do du -sm references/repos/$d; done
2	references/repos/foam-agent
5	references/repos/metaopenfoam
5	references/repos/openfoam-mcp-server
43	references/repos/nullflux
66	references/repos/cfd-agent
8	references/repos/ai-cfd-scientist
13	references/repos/harnessfoam
28	references/repos/autofoam
14	references/repos/deepflow
4	references/repos/hpc-skills
```

| 项目 | `du -sm` 实测（MB） | 可重算性 | 判定 `status` 的那条路径（锚点） | tier |
|---|---|---|---|---|
| foam-agent | 2 | 全确定性 | `error_logs` 为空即 `success`（`references/repos/foam-agent/src/nodes/local_runner_node.py:24`），来源是 4 条正则/退出码 | B |
| metaopenfoam | 5 | 全确定性 | 目录名字符串比较后置 `Executability`（`references/repos/metaopenfoam/src/actions/RunnerAction.py:662`） | B |
| openfoam-mcp-server | 5 | 全确定性 | `status == "completed" && exitCode == 0`（`references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:83`） | B |
| nullflux | 43 | 需模型 | 网格层硬阈值（`references/repos/nullflux/server.js:2958`）后，最终由 VLM 判官给 `passed`（失败闭合） | B |
| cfd-agent | 66 | 全确定性（判据已退化） | `returncode == 0 and not has_fatal_error`（`references/repos/cfd-agent/src/steps/simulation.py:56`），而后者因重定向恒 False | B |
| ai-cfd-scientist | 8 | 需模型 | 物理层 LLM 三态出口（`references/repos/ai-cfd-scientist/scripts/interpret.py:58`）；网格层确定（`src/cfd_langgraph/foam_native/loop.py:77`，同源已并入 foam-agent） | B |
| harnessfoam | 13 | 部分 | 四道纯函数（`references/repos/harnessfoam/harnessfoam/validation.py:125` 等）＋第五道视觉子串判 PASSED 后可翻 `status`（`references/repos/harnessfoam/harnessfoam/agents/graph.py:370`） | A |
| autofoam | 28 | 全确定性 | 加权分（`references/repos/autofoam/openfoam_agent/scorer.py:97`）→ `score >= 0.5`（`references/repos/autofoam/openfoam_agent/agent.py:273`） | B |
| deepflow | 14 | 需模型 | LLM 读 `--- Exit Code: N ---` 自行判断（`references/repos/deepflow/deepflow_agent/openfoam_agent.py:225`） | B |
| hpc-skills | 4 | 无实现 | 无判定代码，只有判据清单（据 02:2105） | B |
| chatcfd | 未下载（registry 记声明值 562，超 R10 100 MB 线） | 【待定：2506.02019 未写「收敛」用什么判据】 | （文档级）据 02:1904 | B |
| openfoamgpt | 无官方仓（registry 记 0） | 需模型 | （文档级）Table 1 的 ✓ 由人看文件判，非 runner 判（据 02:2049） | C |

三档判据：`全确定性` = 判定 `status` 的整条路径不含任何模型调用；`部分` = 纯函数判据可被模型通道改写；`需模型` = 终判落在模型输出上。`hpc-skills` 落不进三档（它没有任何判定实现），单列为 `无实现`，不参与三档统计。**本表 tier 一律取 `references/registry.csv` 第 8 列，实测分布 A=1 / B=10 / C=1。**

数据来源：`for d in …; do du -sm references/repos/$d; done`（输出见上块）；`awk -F, 'NR>1{print $1, $8}' references/registry.csv`（tier 列）；`awk -F, 'NR>1{c[$8]++} END{for(k in c) print k, c[k]}' references/registry.csv`（分布）。**`bench/preregistration.md:267` 写 B=9 是旧值（冻结切片内，未改）；`references/01-landscape.md:69` 已于 2026-10-28 更正为 B=10。以 registry 的 B=10 为准（prereg 内部 `:443` 亦写 B=10）。**

## 3 稳定架构候选表（含反例）

K/E/V 口径见本文件 §0（已冻结，不放宽）。同源去重已执行：cfd-agent↔ChatCFD 计 1、Foam-Agent↔AI-CFD-Scientist 计 1、harnessfoam 两套 MCP 计 1。
12 个项目经同源去重后**独立实现上限 = 9**（10 个 full 仓 − Foam-Agent↔AI-CFD-Scientist 一次并计 = 9；cfd-agent↔ChatCFD 这一对里 ChatCFD 是 docs_only、不计入 full，故不再扣）。**初版写的「上限 10」与「若把 OptMetaOpenFOAM 另计，上限 11」都错**：前者把 2 个 docs_only 放进了「实现」分母，后者直接违反 §0 的同源规则（OptMetaOpenFOAM 与 MetaOpenFOAM 同仓，计 1）。本节最大 K=7（C3、C4 之前），均 ≤9。

| # | 架构 | K | E | V | 评级 | 支撑项目（带锚点） | 反例 |
|---|---|---|---|---|---|---|---|
| C1 | tutorial 派生（case 以 tutorial 为唯一生成基底，不从空目录起写） | 3 | 仅实现 | 无关 | 中 | harnessfoam：4 个官方 tutorial 做成回归注册表，逐个复制到隔离目录再跑同一套 v13 门禁（`references/repos/harnessfoam/harnessfoam/tutorial_regression.py:17`，01:147）／nullflux：`foam_clone_tutorial` + 遍历本机 tutorials 打分（`references/repos/nullflux/server.js:1081`）／metaopenfoam：检索单元=tutorial 内的一个输入文件块，直接作为生成基底（`references/repos/metaopenfoam/src/Langchain_database_add_tutorial.py:22`） | hpc-skills 的 `simplefoam-minimal` 也是「复制后改」形态，但它写明 OpenFOAM-11（`references/repos/hpc-skills/skills/hpc-openfoam/assets/templates/simplefoam-minimal/README.txt:1`），v13 已把 `transportProperties`/`turbulenceProperties` 换名 → 派生目标版本错，派生反而制造 FATAL（据 02:1806）。另 2 个 full 仓根本不派生：autofoam 走 gmsh 模板（01:150） |
| C2 | grep／文本检索（不建向量索引，直接在 tutorial 或结构化库上做字面检索） | 3 | 仅实现 | 无关 | 中 | harnessfoam：词袋打分 `tag_hits*4 + min(text_hits,12)`，k=4（`references/repos/harnessfoam/harnessfoam/knowledge.py:156`）／nullflux：本机 tutorials 关键词打分，topK=12（`references/repos/nullflux/server.js:1081`）／cfd-agent：明文 JSON 四级回退 + solver 路径子串匹配（`references/repos/cfd-agent/src/database.py:169`） | cfd-agent 在同一条检索路径上用 `random.sample` 截断到 3 条（`references/repos/cfd-agent/src/database.py:217`）→ 同一查询两次给不同参考，「可复算」被自己毁掉；且它绑 `database_OFv24`（`references/repos/cfd-agent/ReadMe.md:78`），说明「文本检索」不天然版本无关。另：hpc-skills 的检索是手写路由表、无 top-k 兜底，路由错即知识错（据 02:1752） |
| C3 | 确定性门禁（判据是纯函数或命令输出，**不经模型**） | 7 | 有对照 | 无关 | **强** | harnessfoam 前四道纯函数（`references/repos/harnessfoam/harnessfoam/validation.py:125`、`physics_validation.py:43`、`reference_benchmarks.py:5`）／nullflux（`references/repos/nullflux/server.js:2958`）／autofoam（`references/repos/autofoam/openfoam_agent/scorer.py:97`）／metaopenfoam（`references/repos/metaopenfoam/src/actions/RunnerAction.py:662`）／cfd-agent（`references/repos/cfd-agent/src/steps/simulation.py:56`）／openfoam-mcp-server（`references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:83`）／foam-agent＋ai-cfd-scientist 计 1（`references/repos/foam-agent/src/nodes/local_runner_node.py:24`、`references/repos/ai-cfd-scientist/src/cfd_langgraph/foam_native/loop.py:77`）。E 依据：**CFD Forge（2610.14104）的 36 状态回放**——同一模型在「不看 check 结果」时三次重复里放过了 13 个可检故障中的 12 个，由 checks 裁决时放过 0 个（01:159）。§0:111 明写 `有对照` 覆盖「同一篇工作内部的消融**或回放**」，故本条成立 | harnessfoam 第五道视觉闸：判据是 `"correct" in response.content.lower()`（`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100`），而 `"incorrect"` 含 `"correct"`，且提示词自身含 `correct`（`reviewer.py:92`）→ 在最该报警的回答形态下判 PASSED（据 04 §5.6）。**注意：这道闸不属本候选**——本候选的定义是「不经模型」，视觉闸经模型，它是**违反该定义**的实例，故放在反例列而非 V 列；它本身已单列为 §4 的「视觉物理门禁」。另 metaopenfoam 只比目录名字符串（`endTime 1;` 与目录 `1.0` 不等） |
| C4 | 失败反馈环（错误 → 定位/改文件 → 重跑，带轮数上限） | 6 | 有对照 | 无关 | 强 | foam-agent（`references/repos/foam-agent/src/nodes/reviewer_node.py:23`）／metaopenfoam（`references/repos/metaopenfoam/src/actions/ReviewerAction.py:456`）／nullflux（`references/repos/nullflux/server.js:4643`）／cfd-agent＋ChatCFD 计 1（`references/repos/cfd-agent/src/workflow.py:118`）／harnessfoam（`references/repos/harnessfoam/harnessfoam/agents/graph.py:68`）／autofoam（`references/repos/autofoam/openfoam_agent/dict_fix.py:106`）。**K=6 而非 7**：初版把 openfoamgpt 也计入了，但它是 docs_only（`registry.csv:13` `kind=paper`、`size_mb=0`、无官方仓），K 的定义是「独立**实现**」，论文不算实现——已剔除。E 依据：2609.03718 同篇内部开关修复轮的消融，无修复轮 71.8% → 有修复轮 96.4%（01:103、01:168） | autofoam 的 `dict_fix` 在认不出 FATAL 指名文件时直接 `return None`（`references/repos/autofoam/openfoam_agent/dict_fix.py:106`）→ 环在，但整条定向修复路径空转，只剩「整份重生成」。另 01:103 同一篇报 scripted reflection 增益为零（「adds nothing」原句在 01:19、01:139）：**环有效，环里的反思文本无效** |
| C5 | 结构化反思记忆（失败经验结构化落盘，跨轮/跨任务复用） | 2 | 仅实现 | 无关 | 中 | harnessfoam：`failure_ledger.jsonl` 记 attempt/prompt/error/suggestions（`references/repos/harnessfoam/harnessfoam/agents/graph.py:317`）＋可选 per-agent md 记忆（`references/repos/harnessfoam/harnessfoam/memory.py:56`）／nullflux：只有本轮 verifier 通过才允许 `skill_save`（`references/repos/nullflux/server.js:3719`）＋`learnedErrorPatterns` 并进错误库（`references/repos/nullflux/server.js:537`）。**K=2 而非 3**：初版把 cfd-agent↔ChatCFD 也计入，但 ChatCFD 无代码，而 cfd-agent 侧只有分档反思（`references/repos/cfd-agent/src/workflow.py:118`）、**未落盘也未跨轮复用**，不满足本候选的定义「落盘 + 跨轮/跨任务复用」——已剔除 | 2609.03718 的消融显示 scripted reflection「adds nothing」（原句在 01:19、01:139）；harnessfoam 的 per-agent 记忆默认关闭（`references/repos/harnessfoam/README.md:65`）→ 实现了但默认不生效，等于没进入主路径；且它的 `failure_ledger.jsonl` 写完只进 API 返回串（`api/mcp_server.py:103`、`api/server.py:541`），**不回流 prompt**。autofoam 把「反思」退化为把最后 40 行日志拼进下轮输入（据 02:1513），不落盘、不复用 |
| C6 | 工具封装（MCP / function calling） | 5 | 仅实现 | 无关 | 中 | foam-agent：MCP 7 tool（`references/repos/foam-agent/src/mcp/fastmcp_server.py:91`）／openfoam-mcp-server：12 tool、主程序 9（`references/repos/openfoam-mcp-server/src/tools/pipe_flow_tool.hpp:46`）／nullflux：91 tool（`references/repos/nullflux/server.js:232`）／deepflow：11 个 `@tool`（`references/repos/deepflow/deepflow_agent/openfoam_agent.py:24`）／harnessfoam：8+11 tool 同源计 1（`references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8`、`core/mcp_server.py:6`） | openfoam-mcp-server：主程序只注册 9 个、7 个只在测试程序（`references/repos/openfoam-mcp-server/src/main_test.cpp:52`），且 `pipe_flow` 返回的 `maxVelocity`/`pressureDrop` 是解析公式而非仿真产物（`pipe_flow.cpp:221`、`pipe_flow.cpp:224`）→ 封得越整齐，越难看出返回值与算例是否真跑无关。harnessfoam 两套粒度并存且 README 只宣传其中一套（K2），「谁是权威」未定 |
| C7 | 阶段状态机（流程切成**命名阶段**） | 5 | 仅实现 | 无关 | 中 | nullflux：`runs/<runId>/state.json` 断点续跑（`references/repos/nullflux/server.js:323`）＋`passed` 作阶段退出条件（`server.js:4643`）／cfd-agent：11 步 `STEPS` 表（`references/repos/cfd-agent/src/workflow.py:43`）／harnessfoam：9 节点 + 4 条条件边（`references/repos/harnessfoam/harnessfoam/agents/graph.py:470` 起）／foam-agent＋ai-cfd-scientist 计 1（8 节点 / Stage 0–7，02:1070）／autofoam：8 段流水线主体在 `run()` 内（`references/repos/autofoam/openfoam_agent/agent.py:65`）。**K 对定义敏感（编排方 2026-10-28 记）**：本候选初版的定义写成「命名阶段 **+ 阶段产物/状态落盘**」，若严格按含落盘读，只有 nullflux（`state.json`）、harnessfoam（`manifest.json`）、ai-cfd-scientist（stage 间磁盘 JSON）3 家满足 → K=3；按「命名阶段」读则 K=5。两读都落在「中」（K≥2 且 E=仅实现），**评级不随定义变**，故取较宽的 K=5 并在本格记明两种口径 | 五家里只有 nullflux 把 `passed` 写成阶段退出条件；其余四家的阶段只决定「下一个跑谁」，不判「这一段算不算过」。**编排方更正（2026-10-28）**：本行初版写「所以 foam-agent 仍能在同一 FATAL 上用到 `max_loop=25`」是**错的**——foam-agent 有错误指纹守卫，同一指纹重复即终止（`references/repos/foam-agent/src/nodes/reviewer_node.py:23` 原文 `repeated = bool(fingerprints and fingerprint == fingerprints[-1])`，02:175 明写「把『同一错误反复重试』从 25 轮压到 2 轮」）。正确的反例是 **metaopenfoam**：无指纹去重，同一错误会烧到 `max_loop=20`（02:439） |
| C8 | 版本断言（把 OpenFOAM 版本号当硬信号检查） | 2 | 仅实现 | 无关（期望值为字面 `"13"`，机制本身不绑版本） | 中 | harnessfoam：正则查日志 `Version: 13`，四个调用点（`references/repos/harnessfoam/harnessfoam/validation.py:134`，据 02:1376）／foam-agent：仅当显式指定 target 时校验 `WM_PROJECT_VERSION`（`references/repos/foam-agent/src/utils.py:1175` 起） | foam-agent 的版本门默认不生效（`references/repos/foam-agent/src/config.py:46` 的 `openfoam_target` 默认空串）；openfoam-mcp-server 只有编译期 `FATAL_ERROR`（`references/repos/openfoam-mcp-server/CMakeLists.txt:37`），运行期零版本检查；其余 8 个实现完全没有版本断言（`grep WM_PROJECT_VERSION` 在 metaopenfoam 为空，02:1421；deepflow 无版本常量，02:1670） |

**E 列的口径（必须与 01:136 并用，否则会读过头）**：本表 `有对照` 只指**同一篇工作内部**的消融或回放，不指跨项目在同一任务集上的对照——后者本领域没有，01:136 的原句是「这是证据缺口，不是反例」。
- C4 的 `有对照` = 2609.03718 在同一 harness 下开关修复轮的消融（71.8% → 96.4%，01:168）。
- C3 **改为 `有对照`（编排方 2026-10-28 更正，推翻初版）**。初版给了三条理由否掉它，逐条复核后**三条都不成立**：
  ① 「harnessfoam 第五道闸不是确定性的」——这是**实例完整性**论证，不是 §0 的 E 判据；E 问的是「有没有对照/回放支持该机制起作用」，不问「每个实例是否完整实现」；
  ② 「2610.14104 无代码」——**有无代码不是 §0 的 E 判据**；§0 只要求「同一篇工作内部的消融或回放」，01:159 的 36 状态回放满足这一条（同一篇内部，模型裁决 vs 规则裁决，13 个可检故障里模型放过 12、checks 放过 0）；
  ③ 「其余 5 个实现没在自己任务集上开关过门」——只对另外 5 家成立，**不能否掉 CFD Forge 那一次回放**。
  故 C3 的 E = `有对照`，V = `无关`（该机制按定义排除模型裁决，视觉闸是违反定义的实例，已放反例列），K=7 → **评级从「中」升为「强」**。
  这条更正把 §6 的「强 1」变成「强 2」，是本文件唯一一处**结论级**改动，留在本行以便复核。

**没有反例的候选**：本节 8 条**都找到了反例**，故不适用「无反例，但只有 K 个实现、无对照实验支撑」这一写法。C8 最接近该边界（K=2，两个实现里一个默认关闭），已在反例列写明。

数据来源：`grep -c '^| C' references/05-cross-project-matrix.md`（→ 8）；各格 path:line 与 01/02/04 的行号引用均按 §1 表下的 `for a in …; do sed -n` 方式逐条回切。

## 4 已被证否或成本过高的架构

| 架构 | 代价（可量化） | 证据锚点 | 结论（本阶段不采用的理由） |
|---|---|---|---|
| RAG 层（向量索引 + 嵌入模型） | chatcfd 随仓知识库 **562 MB**（超 R10 100 MB 线 5.6×，故 docs_only）；cfd-agent **66 MB** 且库与版本一对一；foam-agent 索引是 LFS 指针（raw 文件 133 字节、声明 `size 64026283`），开箱不可检索须用本机 OF 重建；deepflow 的 `requirements.txt` 缺 `faiss-cpu` → RAG 静默降级 | `references/repos/cfd-agent/ReadMe.md:78`（换版本即与 `database_OFv24/*.json` 不匹配）；`references/repos/deepflow/deepflow_agent/openfoam_agent.py:334`（异常被吞、退化成仅文件工具）；02:1301（LFS 指针）；04 实测各 7/7、省 5.2% token、+98 MB，01:136 记为证据缺口 | 不采用。三件事同时成立：① 同任务集内无「检索层 vs tutorial 上 grep」的对照（01:136）；② 索引体积与版本绑定同时踩 R10 与 R11；③ 我们已选定 grep 路线（AGENTS.md R1），再引入向量库会让证据悄悄指向非权威树 |
| 微调（把「自然语言→字典」当监督学习） | 数据量 **28716 对（含 CoT）vs 252 条**，差两个数量级；autofoam 推理侧另需 ≥24 GB VRAM + 私有 HF 权重；两篇都未给数据集链接，无法判断是否泄漏目标 benchmark | 01:37（2504.09602 的 28716 对）／01:31（2608.00003 的 252 条）／01:118（「数据自造、不可比」）／01:192（「微调值不值得」在本领域目前无法回答）／`references/repos/autofoam/README.md:154`（≥24 GB VRAM） | 不采用。数据不可比、不可复现；模型固化后与 OF 版本脱钩，换版本需重训——与 R11「单一版本」和 R12「结果要能重算」同时冲突 |
| 全面多 agent 拆分（每个动作一个角色） | 2609.03718 在**同等信息与修复预算**下：单 agent 96.4%、多 agent 88.2%；角色数上升时 token 与延迟线性增长；harnessfoam 6–7 个 LLM 角色 × 最多 3 轮、每轮带 RAG 上下文（单次 2500 字符上限） | 01:18／01:34／01:108（多 agent 反而低 8.2 个百分点，且「拆开审并不自动带来正确性」）；`references/repos/harnessfoam/harnessfoam/knowledge.py:156`（`max_chars=2500`）；02:1428（token 成本是主开销） | 不采用。角色边界靠 prompt 维持、没有硬接口；失败模式会从「一个环里可见」变成「分摊到多个角色不可见」。保留的是角色分工中的**判据层**（见 §3 C3），不是角色数量 |
| 全面 MCP 封装（把每个 OpenFOAM 动作都做成 tool） | openfoam-mcp-server：主程序只注册 9 个 tool，测试程序注册 12 个（其中 7 个只在测试里），合计 16 个不同的 tool 名；solver 由默认构造固定成 `simpleFoam`（v13 无此可执行 → 恒 127 退出）；编译期绑 `/opt/openfoam12`，换版本要重编。harnessfoam：两套粒度（8 tool=一条流水线 vs 11 tool=一个节点）并存，README 只宣传一套 | `references/repos/openfoam-mcp-server/src/main_test.cpp:52`（`registerMeshQualityTool` 只在 test 里）；`references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:56`（`solver("simpleFoam")`）；`references/repos/openfoam-mcp-server/CMakeLists.txt:12`；01:128（「工具粒度即能力上限」）；K2（两套 MCP 同源，K 只计 1） | 不采用。MCP 是给外部编排器的协议面，我们没有第二个消费者；把动作封成 tool 会把「版本」和「跑完算不算成功」两个问题推到接口之外，openfoam-mcp-server 的默认 solver bug 就是这条路的现成代价 |
| 视觉物理门禁（让模型看图判物理是否像话） | 判据不可复算：`"correct" in response.content.lower()` —— `"incorrect"` 命中 `"correct"`；且提示词自身含 `correct`（`Does it look physically correct?`）→ 该闸趋近恒 PASSED。ai-cfd-scientist 的同类判据是 LLM 三态标签、无阈值留在代码里，其 14/16 只在论文口径成立 | `references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100`（判据）、`reviewer.py:92`（提示词）、`references/repos/harnessfoam/harnessfoam/agents/graph.py:370`（该模型输出能翻 `status`）；04 §5.6；01:160（视觉门禁 14/16 检出）；`references/repos/ai-cfd-scientist/scripts/interpret.py:58` | 不采用其**实现**。违反 R6（数字必须实测）与 R12（判据须可重算）：同一张图两次判读可不同。「物理是否像话」这一层次值得保留，但必须先约束成结构化枚举 + 显式阈值，且仍记为「需模型看」，不得写成 E0/E1 |

数据来源：表内 path:line 逐条 `sed -n` 回切；01/02/04 行号见各格括注；`du -sm` 与 registry 的 562 MB 见 §2。

## 5 退化说明

`bench/preregistration.md:275-284` 是**冻结前写死**的退化条款，不是事后口径：
- `:275` 起：若 A 档实际可跑臂 < 2，跨臂主标不成立，框架退化为「我们自研 agent 的回归基线」，其余只做定性对照；
- `:279` 起：该条件**已于 2026-10-27 静态触发**（未跑任何项目即已确定，A=1）；
- `:282`：其余 B/C 档只做定性对照表，不出任何跨臂可比数字。

实测分布（`awk -F, 'NR>1{c[$8]++} END{for(k in c) print k, c[k]}' references/registry.csv`）：**A=1 / B=10 / C=1**。唯一 A 档是 harnessfoam（`references/repos/harnessfoam/harnessfoam/case_manifest.py:8` 的 `EXPECTED_OPENFOAM_VERSION = "13"`），且它自己的第五道闸还带模型（§3 C3 反例）。也就是说：**本文件的三档评级没有任何实测绩效作为分母。**

因此本文件的三条自我约束：
1. §3 的评级只表达「收敛度 × 证据强度 × 版本无关性」三重属性，**不是实测绩效**；K 是「有多少个独立实现这么做」，不是「有多少个验证过它有效」。
2. 全文不产生任何跨臂可比数字；§2 的体量、§3 的 K 都是可直接复算的计数，不是效果量。
3. 三档清单只按 §0 的阈值机械落档，不排座次、不做名次。

## 6 问题②的结论句（强 / 中 / 弱三档）

强（K≥3 且 E=有对照 且 V=无关）：**确定性门禁**（K=7）、**失败反馈环**（K=6）
中（K≥2，或 E 弱，或 V 绑定）：tutorial 派生（3）、grep/文本检索（3）、结构化反思记忆（2）、工具封装（MCP / function calling）（5）、阶段状态机（5，含落盘读法为 3）、版本断言（2）
弱（K=1 或 E=无）：本领域无一条落在弱档（8 条候选的 K 全部 ≥2，最小 K=2 为版本断言与结构化反思记忆）

计数：**强 2 / 中 6 / 弱 0**，合计 8

```
$ grep -c '^| ' references/05-cross-project-matrix.md
45
$ grep -c '^| C' references/05-cross-project-matrix.md
8
```

`45` 数的是**全文所有表格行**（`^| ` 不计以 `|---` 开头的分隔行；含 §0 口径表 4 行、§1 主表 13 行、§2 补充表 13 行、§3 候选表 9 行、§4 表 6 行），不是候选数；候选数由 `^| C` 得到 `8`，与「合计 8」一致。

本结论只表达机制层面的「收敛度 × 证据强度 × 版本无关性」，不表达任何实践绩效，也不构成任何意义上的座次。
