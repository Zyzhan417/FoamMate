# 七、理论溯源：这些架构从哪来（问题③）

> 最高幻觉风险的一份：**arXiv id 与标题必须逐条调 API 核实，不许凭记忆写**。
> 顺序不能反：先列「待溯源的机制」（取自 05 §3 候选表），再去找理论。
> 先有理论再套机制 = 强行附会。

## 0 口径：L1 / L2 / L3（本段已冻结，后续不得放宽）

| 级 | 判据 | 允许的写法 |
|---|---|---|
| **L1 明示引用** | 该项目代码/论文里写出了理论名字或论文 id（有 `path:line` 或论文原句） | 「引用」 |
| **L2 同构** | 机制逐条对得上，但项目没有引用文本 | 只能写「与 X 同构」，**不得写「源于」** |
| **L3 形似** | 只有一个模糊相似点 | **不得写**，只能进 §3「已排除的形似配对」 |

用户问的「源于」一词，本文件统一降级为 L1/L2 两档，并给出各多少条（E0 计数）。
**任何一条 arXiv id 核实失败就删掉，不许降级保留。**

## 1 机制 → 理论映射表

### 1.0 本节的执行顺序与两条子档（不改 §0）

顺序（不许反）：① 先把 `references/05-cross-project-matrix.md:100-109` 的 C1–C8 八条候选**当作待溯源对象**；
② 再问每条机制「本领域谁在代码/文档里写出了理论名」；③ 最后才去核实候选 id 的标题。
本表的「本领域谁在用」列只填**代码里能读到的机制形态**，不填「它可能受了谁启发」。

§0 的 L1 在本文件里再分两个子档，**只细分、不放宽**（`§0 已冻结，本节不修改其判据`）：

- **L1-学术**：项目代码/论文/README 里写出了**理论名**（ReAct / RAG / Reflexion …）或论文 id。这是学术传承。
- **L1-工程**：项目代码里 `import` 了某个库、或直接调用某个现成工具（LangGraph、MetaGPT、FastMCP、`foamCloneCase`）。
  这是**工程选型**——它证明「这个库被用了」，**不证明**「某篇论文被引用了」。LangGraph 不等于 ReAct，
  FastMCP 不等于任何工具学习论文。
- **P-实践（无理论来源）**：机制**完全自己写**——既没有 `import` 任何第三方件，也没有写出任何理论名或论文 id。
  典型：自己写的正则、自己写的词袋打分函数、直接用 OS 退出码。**它不是 L1-工程**（没有库），也不是 L2
  （L2 要求「机制与某理论逐条对得上」），更不是 L3（L3 是「有相似点但不足以称为同构」）。

**为什么必须有 P 这一档（2026-10-28 编排方补，见 §6 口径变更）**：初版把 C2（手写词袋）/ C3（退出码 + 自写
`compute_reward`）/ C8（自写正则）都记成 `L1-工程`，**而它们一个库都没 import**。这不是分类瑕疵，它会把结论
算错：初版据此说「6 条是用了某个框架的库」，逐行核对只覆盖 3 条（C1/C6/C7）。P 档让「有多少条机制**根本
没有理论来源**」变成一个可数的量，而这正是本文件要回答的问题的另一半。

**级别取该机制在本领域可辩护的最高档，且一格的级别只说这一层。** 名字出现但机制对不上时，
级别记 L1-学术，同时在「本领域谁在用」列写明「名字与机制不同层」。

### 1.1 主表（14 行）

| 机制（05 §3 的 C 编号 + 名称） | 理论或实践 | arXiv id | 核实后的标题（逐字） | 映射级别（L1-学术\|L1-工程\|P-实践\|L2） | 本领域谁在用（带锚点） | 本地锚点 |
|---|---|---|---|---|---|---|
| C1 tutorial 派生 | 实践：官方 tutorial 作唯一生成基底（复制后改，不凭空生成）；本项目侧用现成命令 `foamCloneCase`（OpenFOAM 自带），非自写；**领域侧 3 家均自写复制**（harnessfoam 用 `shutil`、nullflux 自写遍历、metaopenfoam 自写正则）——故本格 L1-工程 仅由**本项目侧**成立 | — | — | L1-工程（无论文）| harnessfoam 4 个官方 tutorial 做成回归注册表 `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:9`；nullflux 遍历本机 tutorials 打分 `references/repos/nullflux/server.js:1081`；metaopenfoam 检索单元=tutorial 内的输入文件块 `references/repos/metaopenfoam/src/Langchain_database_add_tutorial.py:22` | `references/05-cross-project-matrix.md:102`；本项目 `AGENTS.md:135`（R3）、`references/00-project-readme.md:79`（P2） |
| C2 grep／字面检索 | 实践：Unix grep + 手写词袋打分（无嵌入、无索引、无 top-k 之外的任何加权） | — | — | P-实践（无理论来源） | harnessfoam `score = tag_hits * 4 + min(text_hits, 12)` `references/repos/harnessfoam/harnessfoam/knowledge.py:103`，`k=4` `:156`；nullflux topK=12 `references/repos/nullflux/server.js:1081` | `references/05-cross-project-matrix.md:103`；本项目 `AGENTS.md:23`（R1）、`references/00-project-readme.md:105` |
| C2-补 检索层的自称 | RAG | 2005.11401 | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks | L1-学术（仅名字，无 id） | harnessfoam README 把 "Retrieval-Augmented Generation" 写成功能项 `references/repos/harnessfoam/README.md:96`；但同仓检索实现是词袋打分（见上格），无嵌入模型 → **名字与机制不同层** | `references/05-cross-project-matrix.md:128`（该架构已被否决） |
| C3 确定性门禁 | 实践：命令退出码 + 日志字面量作判据（判据不经模型） | — | — | P-实践（无理论来源） | harnessfoam 前四道纯函数 `references/repos/harnessfoam/harnessfoam/validation.py:125`、`references/repos/harnessfoam/harnessfoam/physics_validation.py:43`；autofoam 加权分 `references/repos/autofoam/openfoam_agent/scorer.py:97`；openfoam-mcp-server 退出码 `references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:83` | `references/05-cross-project-matrix.md:104`；本项目 `references/00-project-readme.md:176`（§6 G1–G4）、`AGENTS.md:147`（R4） |
| C3-反例 物理／视觉闸 | LLM-as-judge | 2306.05685 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena | L2 | harnessfoam 第五道闸 `passed = "yes" in response.content.lower() or "correct" in response.content.lower()` `references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100`（判据即「让模型当裁判」，无引用文本） | `references/05-cross-project-matrix.md:132` |
| C4 失败反馈环 | CRITIC（用外部工具的执行结果作批判信号，再据此改） | 2305.11738 | CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing | L2 | 实现数见 05 §3 的 K 列（该列会被并发维护，本文件不复写数字）；环的守卫 `references/repos/foam-agent/src/nodes/reviewer_node.py:23`；轮数计数 `references/repos/metaopenfoam/src/actions/ReviewerAction.py:456`；空转反例 `references/repos/autofoam/openfoam_agent/dict_fix.py:106` | `references/05-cross-project-matrix.md:105` |
| C4/C5 反思块的命名 | Reflexion | 2303.11366 | Reflexion: Language Agents with Verbal Reinforcement Learning | L1-学术（仅名字，无 id） | ChatCFD 论文 §2.4 把反思写成 `<reflexion>` 标签块并入反思历史（文档级，无代码可读）。**严格性提示**：ChatCFD 全文只有小写 XML 标签 `<reflexion>`，未出现理论名 "Reflexion"——本格按 §1.0「写出理论名」判 L1-学术属**边界成立**；若从严只认首字母大写的专名，§5 的「3 个名字」会降到 2（RAG 与 ReAct 不受影响） | `references/02-architectures.md:1868`、`:1954` |
| C5 反思记忆落盘复用 | Reflexion 的 verbal memory（跨试次留文本经验，不训练） | 2303.11366 | Reflexion: Language Agents with Verbal Reinforcement Learning | L2 | harnessfoam：`failure_ledger.jsonl` 写入 `references/repos/harnessfoam/harnessfoam/agents/graph.py:317`，汇总 `:327`；**但汇总只进 API 返回串、不回流 prompt**——全库消费点仅 `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:103` 与 `references/repos/harnessfoam/harnessfoam/api/server.py:541`（2026-10-28 实测）；真正的 prompt 注入路径是 `memory.py` 的 `prompt_context()`（`references/repos/harnessfoam/harnessfoam/memory.py:49`、`:54`，六个调用点），而它 `memory_enabled` **默认 False**（`references/repos/harnessfoam/README.md:65`）。**故本格 L2 的成立依赖「显式开记忆开关」这条非默认路径；账本路径本身不构成复用** | `references/05-cross-project-matrix.md:106` |
| C5-补 技能库入库门控 | Voyager（可增长的技能库；只有通过自验证的行为才入库、可被后续任务检索复用） | 2305.16291 | Voyager: An Open-Ended Embodied Agent with Large Language Models | L2 | nullflux：本轮没有 `*_verify` / `run_stage_done` 通过就拒绝 `skill_save` `references/repos/nullflux/server.js:3719`（差在：Voyager 存可执行代码，nullflux 存 skill 卡文本） | `references/05-cross-project-matrix.md:106` |
| C6 工具封装 | 实践：MCP / function calling 协议（schema 人工写死，无训练、无「何时调用」的学习）；用现成库 `FastMCP` | — | — | L1-工程（无论文）| harnessfoam `FastMCP("HarnessFOAM")` `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8`、`references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6`；nullflux 87 个 `function: { name: … }` `references/repos/nullflux/server.js:232`（TOOLS 数组 232–390 行实点 87 个，初版写 91 是错数）；deepflow `@tool` `references/repos/deepflow/deepflow_agent/openfoam_agent.py:24` | `references/05-cross-project-matrix.md:107`、`:131`（该形态不采用的理由） |
| C6-补 接口粒度即能力上限 | SWE-agent ACI | 2405.15793 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering | L2 | harnessfoam 8 tool 与 11 tool 两套粒度并存、README 只宣传一套（`references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8` vs `references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6`）；openfoam-mcp-server 主程序只注册 9 个、7 个只在测试程序 `references/repos/openfoam-mcp-server/src/main_test.cpp:52` | `references/01-landscape.md:126`（「工具粒度即能力上限」） |
| C7 阶段状态机 | 实践：LangGraph `StateGraph` / 显式 STEPS 表 / JSON 快照（无事务语义）；用现成库 `LangGraph` / `MetaGPT` | — | — | L1-工程（无论文）| harnessfoam `workflow = StateGraph(SimulationState)` `references/repos/harnessfoam/harnessfoam/agents/graph.py:454`、条件边 `:470`；foam-agent `from langgraph.graph import StateGraph` `references/repos/foam-agent/src/main.py:2`；cfd-agent 11 步 `STEPS` `references/repos/cfd-agent/src/workflow.py:43`；nullflux `state.json` 断点 `references/repos/nullflux/server.js:323`；metaopenfoam `from metagpt.roles.role import Role` `references/repos/metaopenfoam/src/roles/Architect.py:3` | `references/05-cross-project-matrix.md:108` |
| C8 版本断言 | 实践：preflight 版本正则 / 环境断言 | — | — | P-实践（无理论来源） | harnessfoam 正则查日志 `Version: <期望>` `references/repos/harnessfoam/harnessfoam/validation.py:134` + 常量 `references/repos/harnessfoam/harnessfoam/case_manifest.py:8`；foam-agent 仅显式 target 时校验 `WM_PROJECT_VERSION` `references/repos/foam-agent/src/utils.py:1176`，默认空串 `references/repos/foam-agent/src/config.py:46` | `references/05-cross-project-matrix.md:109`；本项目 `AGENTS.md:238`（R11） |
| 补·主循环（推理-动作-观察交错） | ReAct | 2210.03629 | ReAct: Synergizing Reasoning and Acting in Language Models | L1-学术（仅名字，无 id） | deepflow README 自述 "decision-making loop based on the ReAct framework" `references/repos/deepflow/README.md:31`；实现是 LangChain `create_openai_tools_agent` `references/repos/deepflow/deepflow_agent/openfoam_agent.py:375`（**用库≠引论文**） | `references/02-architectures.md:2105`（拓扑列写「单 ReAct（LangChain `AgentExecutor`）」；`:2104` 是 autofoam 行） |

行数口径：`C1`–`C8` 每个编号至少一行（C2/C3/C4/C5/C6 各两行），另加一行「补·主循环」标出唯一一条
不属于 05 §3 八条候选、但本领域明示引用了理论名的机制；不标它会让 §5 的「学术名 3 条」无法复算。

**同一篇在两条机制上出现两次的说明**：`2303.11366`（Reflexion）出现两次——一次是 C4/C5 的**名字被写出**
（L1-学术），一次是 C5 的**记忆机制对得上但无引用文本**（L2）。这不是重复计数错误，这正好是本文件要区分的两件事：
ChatCFD 写了 `<reflexion>` 标签却没说它来自哪篇论文；harnessfoam 实现了「反思落盘」却没写出这个名字。

**口径修正（实测）**：骨架给的模板是 `http://export.arxiv.org/api/...`，**实测 `http` 端点返回 0 字节**（本文件首次
运行 11/11 全空），必须用 `https://`。arXiv 限速时连续请求会返回**空体（不是 404）**，需要 12–20 s 退避重试。

### 1.2 逐条核实：11 个候选 id 的命令与真实返回

```bash
# 每条单独一条命令（http 端点实测 0 字节，故全部 https；间隔 ≥12s，空体重试）
curl -s "https://export.arxiv.org/api/query?id_list=2210.03629" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2303.11366" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2303.17651" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2302.04761" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2005.11401" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2402.01030" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2405.15793" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2305.20050" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2306.05685" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2305.11738" | grep -o '<title>[^<]*</title>' | tail -1
curl -s "https://export.arxiv.org/api/query?id_list=2305.16291" | grep -o '<title>[^<]*</title>' | tail -1
```

实测返回（2026-10-28，逐字，`opensearch:totalResults` 均为 1）：

```
2210.03629 | ReAct: Synergizing Reasoning and Acting in Language Models
2303.11366 | Reflexion: Language Agents with Verbal Reinforcement Learning
2303.17651 | Self-Refine: Iterative Refinement with Self-Feedback
2302.04761 | Toolformer: Language Models Can Teach Themselves to Use Tools
2005.11401 | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
2402.01030 | Executable Code Actions Elicit Better LLM Agents
2405.15793 | SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering
2305.20050 | Let's Verify Step by Step
2306.05685 | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena
2305.11738 | CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing
2305.16291 | Voyager: An Open-Ended Embodied Agent with Large Language Models
```

11 个 id **全部核实成功，与骨架候选清单一致，无一条需要改写或删除**。其中 7 条进了 §1.1 主表
（2005.11401、2306.05685、2305.11738、2303.11366、2305.16291、2405.15793、2210.03629），
4 条经裁定为 L3 并写进 §3（2302.04761、2402.01030、2305.20050、2303.17651）。

数据来源：
```bash
# 主表行数（14）——注意不能用 '^| C'，会把 §2 的 '| CI/CD …' 也数进去
sed -n '/^## 1 /,/^## 2 /p' references/07-theory-provenance.md \
  | awk -F'|' '$2 ~ /^ *(C[0-9]|补)/' | wc -l
14
# 表内 path:line 逐条回切。**口径必须写死，否则数字对不上**（critic 实测：同一段文字按不同口径可数出 46/48/50/53）：
#   口径 A（本文采用）= 主表第 48–63 行内、形如 `references/...:N` 的**全路径去重**个数：
sed -n '48,63p' references/07-theory-provenance.md | grep -oE 'references/[^` )|]+:[0-9]+' | sort -u | wc -l   # → 48
#   口径 B（参考）= 同区间内所有 `:N`（含 `:N` 简写）去重个数 → 56。两者差 8 条简写，都成立。
#   全部 48 条已逐条 sed 回切：文件存在、行号不越界、行内容支持所引主张。

sed -n '453p' references/repos/harnessfoam/harnessfoam/agents/graph.py
sed -n '1176p' references/repos/foam-agent/src/utils.py
```

## 2 工程实践来源表（非论文）

这张表回答的是另一半问题：本项目的规则**不是从论文来的**，是从工程实践来的。凡「论文里有对应」的，
已经在 §1 记过；这里只记工程侧，且能指到具体规则号或 README 节号（不允许空证据）。

| 实践 | 对应本项目哪条规则（R1/R3/R4/G1–G5/P1–P3） | 证据 |
|---|---|---|
| grep 而非索引（文本检索直接查权威树） | R1 / P3 | `AGENTS.md:23`（R1，七条配方在 `:65` 起，输出纪律在 `:106`）；`references/00-project-readme.md:83`（P3「源码是唯一权威，用 grep 查」）、`references/00-project-readme.md:105`（「无索引、无缓存、无预处理」）；领域侧同形实现见 `references/05-cross-project-matrix.md:103` |
| tutorial 派生（复制可运行模板再改） | R3 / P2 / G1 | `AGENTS.md:135`（R3 判定：每个 `case.meta` 的 `source` 路径必须真实存在）；`references/00-project-readme.md:79`（P2）、`references/00-project-readme.md:128-137`（§5.1 七步链） |
| 确定性门禁（退出码语义，agent 无权跳过） | R4 / G1–G4 | `references/00-project-readme.md:176-183`（§6 门表 G1–G4 + G2b）；`references/00-project-readme.md:230`（退出码 `0/1/2/3/4`）；`AGENTS.md:147`（R4「agent 的自述不算证据」） |
| CI/CD 与 pre-commit 门禁 | R9–R13 的九道门（单入口） | `scripts/verify_references.sh:29`（G-R9-1）、`:109`（G-R12-1）、`:143`（G-R12-2）、`:206`（G-R13-1）。**如实记录：本项目没有 `.github/`、没有 `.pre-commit-config.yaml`**（`ls -a` 实测只有 `AGENTS.md/README.md/STATUS.md/bench/references/scripts`）——等价物是「单入口脚本 + 冻结清单」，不是托管式 CI |
| 编译器即验证器（编译不过=方案不成立） | R2（用户库二次开发） | `AGENTS.md:112`（R2：`cp` 到 `$WM_PROJECT_USER_DIR/src` → `wmake libso`，禁改系统树）；`references/00-project-readme.md:110`（动作层「开发：cp → wmake libso」）；第三方侧同形：`references/repos/openfoam-mcp-server/CMakeLists.txt:12`（`set(OPENFOAM_DIR "/opt/openfoam12")` 把版本写进**编译期路径**，换版本必须重编）；注意 `:37` 的 `FATAL_ERROR` 是「找不到 OpenFOAM 库」而非版本断言，两点不能混谈 |
| TDD 红绿循环 | 部分对应：**判据先行**，无红绿循环 | `bench/preregistration.md:5`（冻结三道门）+ `AGENTS.md:251`（R12：先写「怎样算通过」再动手）；`bench/selftest_expect.py`（尺子自证）。**如实记录：没有单元测试框架，也没有「先写失败测试→实现→变绿」的循环**，这是形态不同，不记作 TDD |
| contract test（对判据本身设合约） | R12 / G-R12-2 / G-BENCH-1 | `scripts/verify_references.sh:143-146`（`sha256sum -c` 逐文件校验，能指出是哪一个变了）；`bench/selftest_expect.py`（`checked=12 failed=0`）；机制见 `AGENTS.md:251`（「只钉任务不钉尺子，等于允许冻结后放松判据」） |
| Unix 小工具组合 | R1 配方 / 动作层原生命令 | `AGENTS.md:53`（七条 grep 配方：`grep -rl` → `grep -n` → `read_file`）、`:106`（截断纪律 `head -20`）；`references/00-project-readme.md:107-112`（动作层只用 `foamCloneCase` / `foamDictionary` / `foamRun` / `blockMesh`） |
| 结构化日志与账本 | R7 / R12 | `AGENTS.md:180`（R7：每例 `runs/<批次>/<case_id>/` 下 `log.checkMesh`、`log.shortRun`、`log.run` 三份日志 + `results.csv` 固定列）；`references/00-project-readme.md:242`；领域侧同形：`references/repos/harnessfoam/harnessfoam/agents/graph.py:317`（`failure_ledger.jsonl`） |
| 预注册（先冻结判据与作废条件，再跑） | R12 | `AGENTS.md:251`（六项冻结：主指标/次指标/结果状态/判定规则/作废条件/每臂预测）；`bench/preregistration.md:1-6`（已冻结 v1.0，分段冻结声明）。**来源是实验科学的注册制，不是本领域论文**——01 全池 25 篇里 `preregist` 零命中（`grep -ci preregist references/01-landscape.md` → 0），02 里唯一一处 `preregist` 指的是我们自己的 `bench/preregistration.md`（`references/02-architectures.md:1200`） |
| 单一权威树（禁止第二份版本） | R11 / R9 | `AGENTS.md:238`（R11：不装第二份 OpenFOAM）、`AGENTS.md:205`（R9：第三方代码只读、不作源码事实来源） |

数据来源：
```bash
# 本表数据行 11 行（12 行含表头）
sed -n '/^## 2 /,/^## 3 /p' references/07-theory-provenance.md | grep -c '^| '
12
sed -n '35p;106p;147p;159p;192p;217p;250p;263p' AGENTS.md
sed -n '176p;230p;242p' README.md
ls -a .github .pre-commit-config.yaml    # 均不存在：No such file or directory
```

## 3 已排除的形似配对（禁止后人再引用）

判据：只有「一个模糊相似点」的一律进这张表（§0 的 L3）。**以后若有人拿这些类比来论证「有理论基础」，
应当先查到这里。** 每条写明「谁像谁 / 为何只是形似 / 差在哪」。

| 谁像谁 | 为何只是形似 | 差在哪 |
|---|---|---|
| Agent 阶段状态机（C7）vs 经典 BPMN 工作流引擎 | 都有「命名阶段 + 转移条件」 | 无持久化事务语义、无补偿/回滚、无参与者与消息契约；nullflux 的 `state.json` 只是 JSON 快照（`references/repos/nullflux/server.js:323`），进程崩在阶段中途没有事务保证；BPMN 的 token/网关语义在本领域一处都不存在 |
| 失败反馈环（C4）vs PID 控制 | 都是「误差→修正→再测」的闭环 | 无 setpoint、无误差度量（残差不是 control error）、无增益/积分项、无稳定性判据；本领域的「收敛」是**轮数上限硬截断**或**同错指纹即停**，不是误差进带——metaopenfoam 无指纹守卫、直接烧到 `max_loop=20`（`references/05-cross-project-matrix.md:108`），foam-agent 则以错误指纹守卫把同一 FATAL 压到 2 轮（`references/repos/foam-agent/src/nodes/reviewer_node.py:23`）。**注意 05:108 已明确更正：把 foam-agent 说成「同一 FATAL 用到 25 轮」是错的** |
| 反思记忆（C5）vs 案例库推理 CBR | 都「把过去的问题与解法留下来下次用」 | CBR 是四步（检索-复用-修正-保留）。本领域**部分**具备复用步：harnessfoam `memory.py` 的 `prompt_context()` 确实产出注入下一轮 prompt 的记忆块（`references/repos/harnessfoam/harnessfoam/memory.py:49`、`:54`，调用点 `references/repos/harnessfoam/harnessfoam/agents/graph.py:79`/`:97`/`:130`/`:205`/`:306`/`:350`），nullflux 的 `learnedErrorPatterns` 也并回错误库（`references/repos/nullflux/server.js:537`）。**差在**：harnessfoam 该路径 `memory_enabled` 默认 False（`references/repos/harnessfoam/README.md:65`），且它的 `failure_ledger.jsonl` 汇总只进 API 返回串、**不回流 prompt**（`references/repos/harnessfoam/harnessfoam/api/mcp_server.py:103`、`references/repos/harnessfoam/harnessfoam/api/server.py:541`）；nullflux 存的是正则/卡片而非案例索引，无相似度检索。故差的是**「默认启用的检索-复用」这一整环**，不是「完全没有复用」 |
| 工具封装（C6）vs 微服务 | 都「把能力切成带名字的接口」 | 无独立部署、无版本契约、无网络边界；MCP tool 在同一进程内注册（`references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8` 的 `FastMCP` 单进程）。代价可观测：openfoam-mcp-server 把 solver 固定成 `simpleFoam`（`references/05-cross-project-matrix.md:131`），没有契约就没有人拦它 |
| 工具封装（C6）vs Toolformer（`2302.04761` = Toolformer: Language Models Can Teach Themselves to Use Tools） | 都「让模型用外部工具」 | Toolformer 的核心是**训练模型自己决定调哪个 API、何时调、传什么参**；本领域 12 个项目的 tool schema 全是人手写死的 JSON，没有任何训练，也没有「何时调用」的学习——只有 0 个样本支持这条类比 |
| 工具封装（C6）vs CodeAct（`2402.01030` = Executable Code Actions Elicit Better LLM Agents） | 都「agent 输出动作」 | CodeAct 的主张正是**反对**本领域的形态：它的摘要把「预定义格式的 JSON/text 动作」列为被约束的动作空间，改以可执行 Python 统一动作；本领域恰恰全是预定义 JSON tool（`references/repos/deepflow/deepflow_agent/openfoam_agent.py:24` 起 11 个 `@tool`）→ 这是**反向**，不是同构 |
| 确定性门禁（C3）vs process supervision（`2305.20050` = Let's Verify Step by Step） | 都「对过程/中间结果判好坏」 | 该论文是**逐步监督训练一个验证器**——摘要已取到并逐字核实：「process supervision, which provides feedback for each intermediate reasoning step」、「800,000 step-level human feedback labels used to train our best reward model」（`curl https://export.arxiv.org/api/query?id_list=2305.20050` 的 `<summary>`，2026-10-28）；本领域既无标注、无训练、也无奖励模型，判据是末态产物 + 日志字面量（`references/repos/harnessfoam/harnessfoam/validation.py:125`）。**缺的是整个训练环节，不是判据形态** |
| 失败反馈环（C4）vs Self-Refine（`2303.17651` = Self-Refine: Iterative Refinement with Self-Feedback） | 都「生成→反馈→再生成」 | Self-Refine 的反馈由**同一个模型自己给**；本领域 C4 的多数实例反馈信号是外部客观产物（solver 日志/退出码），但**不是全部**：nullflux 的阶段门 `*_verify` 含 VLM 视觉核验（`references/repos/nullflux/server.js:4643` 明确要求「以对应 `*_verify` 做视觉/数值核验」），harnessfoam 第五道闸也是模型裁决（`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100`，已按 LLM-as-judge 记在 §1，不重复挂论文）。**故排除理由是「主流形态不同」，不是「唯一例外」** |
| harnessfoam 的词袋打分 vs BM25 | 都「按词命中给文档打分取 top-k」 | 无 idf、无文档长度归一、无 BM25 式的 tf 饱和曲线；它的 `min(text_hits, 12)` 只是**硬截断**（`references/repos/harnessfoam/harnessfoam/knowledge.py:103` 的 `score = tag_hits * 4 + min(text_hits, 12)`），权重 4 与上限 12 均硬编码、k 固定 4。叫它 BM25 或「概率检索模型」都是错标（初版写「无 tf 饱和项」与自身证据矛盾，已改） |

数据来源：
```bash
# 9 条（10 行含表头）
sed -n '/^## 3 /,/^## 4 /p' references/07-theory-provenance.md | grep -c '^| '
10
sed -n '101p;103p' references/repos/harnessfoam/harnessfoam/knowledge.py
sed -n '65p' references/repos/harnessfoam/README.md
sed -n '1954p' references/02-architectures.md
```

## 4 计数（L1/L2/L3 与「论文 / 工程实践」各几条，附命令）

**口径**：只数 §1.1 主表的 14 行（一行一个机制、一行一个级别，不重复计）。§3 的 9 条是**被排除**的，
单独数，不进 §1 的分母。

```bash
$ sed -n '/^## 1 /,/^## 2 /p' references/07-theory-provenance.md | awk -F'|' '$2 ~ /^ *(C[0-9]|补)/' | wc -l
14
$ sed -n '/^## 1 /,/^## 2 /p' references/07-theory-provenance.md \
    | awk -F'|' '$2 ~ /^ *(C[0-9]|补)/ {gsub(/^ +| +$/,"",$6); n[$6]++} END{for(k in n) print n[k], k}' | sort -rn
5 L2
3 P-实践（无理论来源）
3 L1-工程（无论文）
3 L1-学术（仅名字，无 id）
$ sed -n '/^## 1 /,/^## 2 /p' references/07-theory-provenance.md \
    | awk -F'|' '$2 ~ /^ *(C[0-9]|补)/ {gsub(/^ +| +$/,"",$3); if ($3 ~ /^实践/) p++; else t++} END{print "工程实践="p, "论文="t}'
工程实践=6 论文=8
$ sed -n '/^## 3 /,/^## 4 /p' references/07-theory-provenance.md | awk -F'|' 'NF==5 && $2 ~ /vs/' | wc -l
9
```

（`sed -n '/^## N /,/^## N+1 /p'` 限定范围是必须的：不限定范围时 `$2 ~ /C[0-9]/` 会把 §3 里
「工具封装（C6）vs …」这类行也算进主表。**实测**：用 `/C[0-9]/` 得 **21 行 / 论文=15**，
用 `/C[0-9]|补/` 得 **22 行 / 论文=16** —— **差的是正则，不是「漂移」**（§3 恒为 9 行，两次测量稳定）。
这两个数只用来演示「不限定范围会数错」，**不能当基线引用**。

四个计数（§1.1 主表，n=14）：

| 级别 | 条数 | 是哪几行 |
|---|---|---|
| **L1-学术**（写出理论名/论文 id） | **3** | C2-补 RAG、C4/C5 Reflexion、补·主循环 ReAct |
| **L1-工程**（import 库/调现成工具） | **3** | C1（`foamCloneCase`）、C6（`FastMCP`）、C7（`LangGraph` / `MetaGPT`） |
| **P-实践**（无库、无理论名，完全自写） | **3** | C2（手写 grep + 词袋打分）、C3（退出码 + 自写 `compute_reward`）、C8（自写版本正则） |
| **L2 同构**（机制对得上、无引用文本） | **5** | C3-反例 LLM-as-judge、C4 CRITIC、C5 Reflexion、C5-补 Voyager、C6-补 ACI |
| **L3 形似（已排除，见 §3）** | **9**（不计入 14） | 5 条对论文/算法（Toolformer、CodeAct、process supervision、Self-Refine、BM25）+ 4 条对工程范式（BPMN、PID、CBR、微服务） |

**这个 3 / 3 / 3 / 5 的分法本身就是问题③答案的主干**：14 条机制里，
**3 条只是「写出了理论名」（无一条写出 id）、3 条"用了个库"、3 条连库都没用（纯自制）、5 条只能算同构**。
即 **11/14 条机制没有任何可引用的学术出处**。（初版把后两类合并成「L1-工程 6 条」，逐行核对只覆盖 3 条 —— 见 §6。）

「论文 / 工程实践」两栏：**论文 8 行 / 工程实践 6 行**（合计 14）。

本节 §0 的 E0 计数因此是：**L1 = 6 条**（L1-学术 3 + L1-工程 3）、**P-实践 = 3 条**（独立于 L1/L2/L3），**L2 = 5 条**，**L3 = 9 条**（已排除）。

## 5 问题③的结论句

**问：本领域这些架构的设计，主要来自工程实践还是论文？**

**答（只给计数）**：14 条机制映射里，**论文侧 8 行（L1-学术 3 + L2 5）**，**工程实践侧 6 行（L1-工程 3 + P-实践 3）**。
但论文侧 8 行里有 **5 行只是 L2 同构**（机制对得上、项目里没有任何引用文本），真正「明示」的只有 **3 行**；
而这 3 行**全部只写出了名字、没有一条写出 arXiv id**：

- RAG —— harnessfoam README 的功能项名（`references/repos/harnessfoam/README.md:96`），而它的实现是词袋打分；
- Reflexion —— ChatCFD 论文的 `<reflexion>` 标签名（`references/02-architectures.md:1868`），无出处；
- ReAct —— deepflow README 的一句话（`references/repos/deepflow/README.md:31`），实现是 LangChain 的现成 agent 构造器。

**关键区分（这是回答用户问题的核心）**：§1.1 的 **明示级共 6 条（L1）+ 3 条纯自制（P）**，逐行拆开是 **3 + 3 + 3**：
- **3 条是「用了某个框架的库/现成工具」**——工程选型，不是学术传承（C1 的 `foamCloneCase`、C6 的 `FastMCP`、C7 的 `LangGraph` / `MetaGPT`）；
- **3 条连库都没用，完全自写**（C2 手写 grep + 词袋、C3 退出码 + 自写 `compute_reward`、C8 自写版本正则）——它们是纯工程实践，**没有任何可追溯的来源**；
- **3 条写出了理论名**，且只有名字级、无文献级。

**用 LangGraph 不等于引用 ReAct，用 FastMCP 不等于引用任何工具学习论文**：库只证明「这个轮子被装上了」，
不证明「某个学术结论被继承」。

因此：**本领域能立住的「来源」只有工程实践**——而这句话本身是**计数结论**，不是靠 §3 的排除项撑起来的：
- 可追溯的工程选型：**3 条**（L1-工程）；
- 无任何出处、纯自制：**3 条**（P-实践，这一档初版漏掉了，见 §6）；
- 学术侧：**3 个名字、0 个 id、5 条同构**。

（**口径修正**：初版此句写成「6 条 L1 + 9 条已排除的类比里 4 条对工程范式」——那是**拿 §3 里已判 L3、
且 §3 表头明写「禁止后人再引用」的条目去支撑结论**。被排除的东西不能反过来当证据，已删。）

最后一行：**本文件只建立「来源关系」，不建立「效果验证」——L1/L2 不说明该架构有效。**
C6 的 ACI（L2）与 C3 的 LLM-as-judge（L2）在本领域的实例恰好都是反例（`references/05-cross-project-matrix.md:131-132`），
这就是「有来源」与「有效」必须分开写的原因。


## 6 口径变更记录

| 日期 | 改了哪条 | 为什么 | 谁批的 |
|---|---|---|---|
| 2026-10-28 | §1.0 新增 **P-实践（无理论来源）** 一档；C2 / C3 / C8 由 `L1-工程` 改判 `P-实践` | §1.0 原定义 L1-工程 = 「`import` 库 / 调现成工具」，而这三条一个第三方件都没 import（C2 手写词袋、C3 退出码 + 自写 `compute_reward`、C8 自写正则）。硬套 L1-工程 会让 §5 的「6 条是用了库」变成不可核的数——逐行只覆盖 3 条。**加 P 档不放宽 §0**：它是「没有理论来源」这一类，与 L1/L2/L3 正交 | 编排方（07 的独立 critic G1 判 FAIL 后厘清） |
| 2026-10-28 | §5 结论删掉「9 条已排除的类比里 4 条对工程范式」这一论据 | 那 9 条在 §3 已被判 L3，且 §3 表头明写「禁止后人再引用」——**用被排除项支撑结论**。已改为纯 L1-工程 3 + P-实践 3 的计数 | 编排方（critic G5） |
| 2026-10-28 | 两条【待定】实测消除 | ① `failure_ledger` 汇总是否回流 prompt → **否**（消费点仅两个 API 返回串）；② 2305.20050 的 `<summary>` 已取到并逐字核实。前者同时暴露 C5 的 L2 只成立于「显式开记忆」的非默认路径 | 编排方（critic G7） |
| 2026-10-28 | §3 三条排除理由修正（PID / CBR / Self-Refine / BM25） | PID 条目引了 05:108 已撤回的「foam-agent 25 轮」；CBR 条目说「本领域缺复用步」被 nullflux `learnedErrorPatterns` 与 harnessfoam `prompt_context` 两条实测反例部分否掉；Self-Refine 条目说「唯一例外」被 nullflux 的 VLM `*_verify` 否掉；BM25 条目「无 tf 饱和项」与自身引用的 `min(text_hits,12)` 矛盾 | 编排方（critic G3） |

**这四条修正合起来说明一件事**：本文的结论方向（学术侧只有 3 个名字、0 个 id）从头就对；**错的是「有多少条算工程侧」这个分母**——初版把「用了库」与「纯自制」混成一档，多算了 3 条。

| 2026-10-28（二轮） | 表头「映射级别 L1\|L2」→ 四档；§4 输出块 `6 L1-工程` → `5 L2 / 3 P-实践 / 3 L1-工程 / 3 L1-学术`；「L1 = 9 条」→「L1 = 6 条 + P-实践 3 条」两处 | 新增 P 档后**表头与两处叙述没跟着改**，造成 §0 定义（L1 = 明示引用）与正文「L1=9」自相矛盾；§4 的 awk 输出块也是改表前的旧输出（**改表不改命令行输出**这一失效模式本轮再次出现） | 编排方（07 二轮 critic F1/F3） |
| 2026-10-28（二轮） | 6 处裸路径补全为 `references/repos/harnessfoam/...` | 原文写 `api/mcp_server.py:103`、`api/server.py:541`、`agents/graph.py:79`、`references/00-project-readme.md:65` 等，**从项目根解析会落到错误文件**（尤其 `references/00-project-readme.md:65` 会命中本项目 README 的表格分隔行）。违反 R9「引用第三方代码必须写 references/repos/<repo>/<file>:<line>」 | 编排方（07 二轮 critic R4） |
| 2026-10-28（二轮） | `graph.py:453` → `:454` | 引文 `workflow = StateGraph(SimulationState)` 实在 454 行，453 是 `def create_workflow() -> StateGraph:` | 编排方（critic R4-1） |
| 2026-10-28（二轮） | C1 格补「领域侧 3 家均自写复制」；C4/C5 格补 `<reflexion>` 严格性提示 | C1 的 L1-工程 只由**本项目侧**（`foamCloneCase` 是 OpenFOAM 自带命令）成立，领域侧 3 家全部自写；C4/C5 判 L1-学术 依赖小写 XML 标签而非理论专名，属边界成立、须让读者知道 | 编排方（critic 本轮新增两条） |

---

## 7 与 04_RAG_HMS 的关系（本项目自己的前一次实验）

> 本节原先写在 `AGENTS.md` 的「附 · 与 04_RAG_HMS 的关系」，2026-10-29 迁出：它是**溯源**，
> 不是 agent 要执行的条款（两条方法论已分别落在 R4 与 R12 上，见下）。

04 是「agent 检索层」实验，已于 2026-10-26 收尾并结论为「无增量价值」。
本项目**不复用其代码**，只继承两条方法论：

1. **测量前先定判定器**：先写「怎样算通过」，再动手。→ 落点：R12（预注册六项）。
2. **自报不可采信**：agent 声称完成 ≠ 完成，必须有命令输出或独立复核。→ 落点：R4（门禁）、R6（数字实测）。

04 的完整证据在 `../04_RAG_HMS/reports/`，项目[在线仓库](https://github.com/Zyzhan417/openfoam-kb)，
需要引用时直接读，不要转述。
