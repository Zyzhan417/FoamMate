# 二、逐项目架构分析（12 个 distinct 项目）

> 分析对象：`references/repos/` 下 10 个已下载仓库 + 2 个仅文档级项目
> （`chatcfd` 实测 562 MB 超 R10 体积线未下载；`openfoamgpt` 无官方仓库）。
> 方法：11 段静态模板（输入形态 / 分层 / 拓扑 / 工具 / 知识来源 / 自修正 / **成功判据** /
> 部署依赖 / 优缺点 / 可迁移点），全部为静态阅读，**未运行任何被测代码**（R12 设计期禁跑）。
> 引用格式：`references/repos/<repo>/<file>:<line>`。R9：这些是「别人怎么实现」的证据，
> **不是** OpenFOAM 源码事实——凡涉及 v13 行为仍只走 R1 的五个搜索根。
>
> 本文件由两批并行子代理产出（part1：项目 1–5；part2：项目 6–11），由编排方合并、
> 统一引用格式并逐条回切校验行号；项目 12 由编排方在合并后追加（见该节开头的说明）。
> 校验记录见文末。

---

## 0 速读：12 个项目的成功判据横向对比

**这一节是全文件的核心**，因为「它怎么知道跑成功了」最容易被论文与 README 跳过，
而它决定了下游一切数字能不能信。

| 项目 | 成功判据类型 | 强度 | 一句话机制 |
|---|---|---|---|
| foam-agent | 正则「无 ERROR」+ 退出码 | 弱 | 无独立判据；提前结束会被报成 success |
| metaopenfoam | 终态目录存在（`Executability=3`） | 中 | 唯一检查终态的，但纯字符串比对、无 checkMesh |
| openfoam-mcp-server | 两个退出码 | 弱 | solver 被硬编码为 `simpleFoam`（v13 无此可执行） |
| nullflux | `Mesh OK.` + 5 阈值 + 层覆盖率 / 求解层靠 VLM 判残差 | 中（分层） | 网格层最硬；不查 `endTime` |
| cfd-agent | 名义「退出码 + FATAL」 | 弱 | 输出重定向进日志，FATAL 检查空转 |
| harnessfoam | 退出码 + 5 条日志判据 + cavity 5 阈值 | 强 | 判据条数最硬（含版本/时间步/Courant） |
| autofoam | 加权分 ≥ 0.5 | 中偏弱 | 「未收敛但残差低」可凑过线 |
| deepflow | 无独立判据 | 最弱 | 发散但退出码 0 会被报成成功 |
| hpc-skills | 只有判据清单，无实现 | — | 纯文本 skill，不执行 |
| chatcfd | 「无错文件 + 跑到收敛」 | 中 | 物理保真靠人工三级评审 |
| openfoamgpt | 论文未报告 | — | — |
| ai-cfd-scientist | 求解层 `error_logs` 空 / 网格层扫 `***` 行 / 物理层 LLM 看图 | 强（三层） | 只有网格层确定性；物理层是模型意见 |

**由这张表直接得到的三条判断**：

1. 12 个项目里只有 **harnessfoam / nullflux / autofoam / ai-cfd-scientist** 有多条判据；
   其余要么只有退出码，要么实现与声明不符（cfd-agent 的 FATAL 检查空转而实际只剩退出码）。
   这解释了为什么主流项目的报告里会出现「成功」与残差不符的情况——它们的判据抓不住。
   **但「多条」不等于「确定性」**：nullflux 的物理层靠 VLM、autofoam 是加权分 0.5、
   ai-cfd-scientist 的物理层靠 LLM 读图——真正全确定性的只有 harnessfoam 一家。
   我们的 G1–G4 全部是确定性判据（退出码 / 正文字符串 / 文件存在 / 数值有限），这是硬差别。
2. **没有任何一个项目同时具备 G2（网格）与版本断言。** harnessfoam 有版本断言但全仓
   `grep "Mesh OK"` 为 0；nullflux 有 `Mesh OK.` 但无版本断言。我们的 G1–G4 里恰好两者都有，
   这是我们相对它们的结构性优势，应当保留而不是「向主流看齐」砍掉。

---

## 1. foam-agent（csml-rpi/Foam-Agent，tier B）

### 0 一句话定位与规模

一句话：LangGraph 把"自然语言需求"或"已有 case"编排成 8 个节点（规划→建网格→写字典→跑 Allrun→看错→改→再跑），配 4 个 FAISS 检索库做参考 case 召回。

实测规模（命令均在 `references/repos/foam-agent` 下执行）：

- `find . -type f -name '*.py' | wc -l` → `54`
- `find . -name '*.py' -not -path './.git/*' -exec wc -l {} + | tail -1` → `12365 total`
- 单文件最大三处：`src/utils.py` 1482 行、`src/mcp/fastmcp_server.py` 762 行、`src/services/input_writer.py` 739 行
- 入口三处：`foambench_main.py`（CLI，第 7 行 `def parse_args():`）、``references/repos/foam-agent/src/main.py:38``（`def create_foam_agent_graph() -> StateGraph:`）、`src/mcp/start_mcp.py`（MCP 服务）

### 1 输入形态

三种入口，都由 `foambench_main.py` 的 argparse 收：

- `--prompt_path`：一个纯文本需求文件，README 示例即 `user_requirement.txt`
- `--case_path`：已有 case 目录或 ZIP（可加 `--case_subdir` 指定归档里的子 case）
- `--custom_mesh_path` / `--openfoam_target`：网格文件与目标版本标签

命令行参数定义在 ``references/repos/foam-agent/foambench_main.py:12`-47`（`--openfoam_target`、`--output`、`--prompt_path`、`--case_path`、`--case_subdir`）；路由进图的第一跳由 `references/repos/foam-agent/src/router_func.py:8` 决定：

- `references/repos/foam-agent/src/router_func.py:8` 原文：`    if state.get("workflow_mode") == "imported_case":`

### 2 分层与模块边界

```
src/main.py            LangGraph 装配、状态初始化、退出码
src/router_func.py     7 个条件路由函数（入口/planner/meshing/input_writer/runner/reviewer/case_import）
src/nodes/*.py         8 个节点，全是薄壳：取 state 字段 → 调 services → 回填 state
src/services/*.py      业务层：plan(674) / input_writer(739) / mesh(665) / run_local(173)
                       / run_hpc(406) / review(175) / case_import(419) / visualization(318)
src/mcp/*.py           FastMCP 服务，把同一批 services 暴露成 7 个 tool
src/translation/       esi_translator.py（402 行，v10↔ESI 语义翻译的兜底）
database/<target>/     foundation-v10 / esi-v2006，各含 raw/ 与 faiss/
docker/                Dockerfile（基镜 openfoam10）、两套 entrypoint
```

层次职责可以按"碰什么"切成三条：

- **只碰文件系统**：`src/services/input_writer.py`（落盘字典，见 `:231` 与 `:503` 的 `save_file(...)`）、`src/services/case_import.py`（复制 `original/`→`work/`）
- **只碰 LLM**：``references/repos/foam-agent/src/services/plan.py:215``（`return llm_client.invoke(user_prompt, sys_prompt, pydantic_obj=SimilarCaseAdviceModel)`）、`src/services/review.py`
- **只碰仿真进程**：``references/repos/foam-agent/src/services/run_local.py:69``（`command_result = run_command(`）→ ``references/repos/foam-agent/src/utils.py:1140``（`def run_command(`，内部 `subprocess.Popen`）

节点层刻意不写业务，所以每个节点都能单独替换；代价是 `GraphState` 字段膨胀到 30+ 个（见下一节）。

### 3 agent 拓扑

**单图、多角色、一条回边**。``references/repos/foam-agent/src/main.py:45`-52` 注册 8 个节点：

```
planner → (meshing) → input_writer → local_runner|hpc_runner → [reviewer → input_writer]* → visualization → END
```

角色清单与它读写的 state 字段：

| 角色（节点） | 职责 | 主要产出字段 |
|---|---|---|
| planner | 需求→case 名/domain/category/solver + 文件清单 | `subtasks`、`dir_structure`、`case_info` |
| meshing | gmsh/custom mesh 前处理 + checkMesh | `mesh_info`、`mesh_commands` |
| input_writer | 逐文件生成/改写字典 + 生成 Allrun | `foamfiles`、`allrun_reference` |
| local/hpc runner | 跑 Allrun 或提交 Slurm | `error_logs`、`workflow_status` |
| reviewer | 读 error_logs → 分析 → 出 rewrite_plan | `review_analysis`、`rewrite_plan`、`loop_count` |
| visualization | PyVista 截图 | `requires_visualization` |

传输格式是**一个共享 TypedDict**，不是消息传递：`references/repos/foam-agent/src/utils.py:878` 原文：`class GraphState(TypedDict):`

orchestrator 就是 LangGraph 的条件边表本身，``references/repos/foam-agent/src/main.py:55`-62` 用 `workflow.add_conditional_edges(...)` 把 7 个路由函数挂到节点上；回边在 `references/repos/foam-agent/src/router_func.py:221` 原文：`    return "input_writer"`（`route_after_reviewer` 的兜底返回）。

### 4 工具接口

**流水线内部没有任何 function calling**：每个 LLM 调用都是"system prompt + user prompt → 要求返回文本或 pydantic 对象"，模型不能自己决定调什么。真正暴露给外部 agent 的工具在 MCP 层，共 7 个：

| tool 名 | 定义处 |
|---|---|
| `plan` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:91``（`@mcp.tool(name="plan")`） |
| `input_writer` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:162`` |
| `run` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:313`` |
| `review` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:393`` |
| `apply_fixes` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:479`` |
| `run_case` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:621`` |
| `visualization` | ``references/repos/foam-agent/src/mcp/fastmcp_server.py:685`` |

- `references/repos/foam-agent/src/mcp/fastmcp_server.py:91` 原文：`@mcp.tool(name="plan")`

这 7 个 tool 的参数都是 pydantic model（如 `PlanRequest`/`PlanResponse`，`:77-88`），返回结构化字段；`run_case` 是唯一接收"已有 case"的入口，其余 6 个是流水线单步的裸封装。也就是说：**工具接口的粒度是"流水线阶段"，不是"OpenFOAM 动作"**——模型拿不到 `blockMesh` 这种原子工具。

### 5 知识来源

四套 FAISS 索引 × 两套目标语料 × 三种嵌入模型（`database/<target>/faiss/<model>/<index>/`，目录名即组合）：

- 索引名：`openfoam_tutorials_structure`、`openfoam_tutorials_details`、`openfoam_allrun_scripts`、`openfoam_command_help`
- 语料生成：`database/script/tutorial_parser.py` 扫一遍 OpenFOAM 安装的 tutorials，`init_database.py` 驱动；`references/repos/foam-agent/init_database.py:40` 原文：`        '--openfoam_path',`
- 嵌入模型默认值：`references/repos/foam-agent/src/config.py:50` 原文：`    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"`

**分块策略：没有分块器，一个 case 一个文档**。`references/repos/foam-agent/database/script/faiss_tutorials_details.py:66` 原文：`    pattern = re.compile(r"<case_begin>(.*?)</case_end>", re.DOTALL)`
即每个 `<case_begin>…</case_end>` 段落 = 1 个 `Document`，`page_content` 只放 `<index>` + `<directory_structure>`，全部字典正文塞进 `metadata['tutorials']`（`:92-103`）。检索命中后才把整段正文取出来——这是"两段式：先用目录树召回，再用同一 case 取正文"（``references/repos/foam-agent/src/services/plan.py:271`` 的 `_retrieve_matching_details`）。

实测检索参数（全部是硬编码常量）：

- 全局召回条数：`references/repos/foam-agent/src/config.py:12` 原文：`    searchdocs: int = 10 # max(10, searchdocs)`
- structure 召回：`recall_k = max(10, int(searchdocs))`（``references/repos/foam-agent/src/services/plan.py:231``）
- details 召回下限：`references/repos/foam-agent/src/services/plan.py:158` 原文：`_DETAIL_RECALL_FLOOR = 50`
- details 倍数：`references/repos/foam-agent/src/services/plan.py:159` 原文：`_DETAIL_RECALL_MULTIPLIER = 5`
- 硬过滤：`case_domain` 必须相等，然后按 solver 命中重排（``references/repos/foam-agent/src/services/plan.py:249`-262`，注释原文 `# Hard constraint: domain must match; solver match is a ranking preference.`）
- command help 召回：`topk=searchdocs`（``references/repos/foam-agent/src/services/input_writer.py:453``）

**关键实测：仓库里的语料是 git-lfs 指针，不是数据**。

- `ls -la database/foundation-v10/raw/openfoam_tutorials_details.txt` → `133` 字节
- `head -c 300` 该文件输出开头为 `version https://git-lfs.github.com/spec/v1`，其内 `size 64026283`
- 六个 raw 文件实测：details `64026283` B、allrun `239540` B、command_help `201519` B、structure `170177` B、commands `2769` B、case_stats `1989` B；`faiss/*/index.faiss` 也为 131 字节级指针

后果：**这份检出无法直接检索**，必须先 `init_database.py --openfoam_path <某份 OF 安装>` 用本机 tutorials 重建语料与索引。重建出来的语料版本 = 你手上那份 OF，与 README 宣称的 v10 无关。

### 6 错误处理与自修正

有，且是双层的：

1. **进程级重试**：`run_allrun_and_collect_errors(..., max_retries: int = 1)`，`references/repos/foam-agent/src/services/run_local.py:13` 原文：`    max_retries: int = 1,`
2. **LLM 级修复环**：reviewer → input_writer → runner，轮数上限 `max_loop`。`references/repos/foam-agent/src/config.py:11` 原文：`    max_loop: int = 25`
3. **无进展即停**：把"错误文本 + 过滤后的 case 文件 + 用户需求"算成指纹，与上轮相同就终止。`references/repos/foam-agent/src/nodes/reviewer_node.py:23` 原文：`    repeated = bool(fingerprints and fingerprint == fingerprints[-1])`
4. **图级上限**：`recursion_limit: int = 100`（``references/repos/foam-agent/src/config.py:19``）

触发条件是"有 error_logs 且指纹变化且 loop_count < 25"。修不好时落 `termination_reason="max_review_loop_reached"`（``references/repos/foam-agent/src/nodes/reviewer_node.py:79``）。指纹守卫是本项目最值得抄的一段：它把"同一错误反复重试"从 25 轮压到 2 轮。

### 7 它怎么知道跑成功了（门禁问题）

**判据：`error_logs` 为空 ⇒ 成功。没有第二条独立判据。**

`references/repos/foam-agent/src/nodes/local_runner_node.py:24` 原文：`        state["workflow_status"] = "success"`（紧接在 `:22` 的 `else:` 之后，即 `if error_logs:` 为假时）

`error_logs` 只有四个来源，全部在 `src/services/run_local.py` 里生成：

- 缺 `Allrun` 文件：`:49-55`（"Allrun script not found at …"）
- 超时：`:81-89`（"Allrun exceeded the {timeout} second execution timeout."）
- 非零退出码：`:90-98`（"Allrun exited with non-zero return code {returncode}."）
- 日志正则命中：`:100` `error_logs.extend(check_foam_errors(case_dir))`，其实现只有一条正则

`references/repos/foam-agent/src/utils.py:1299` 原文：`_EXPLICIT_FOAM_ERROR_RE = re.compile(r"ERROR:(.*)", re.DOTALL)`

该函数的 docstring 直接写明了它**故意不做完成度判断**：

- `references/repos/foam-agent/src/utils.py:1303` 原文：`    """Collect explicit OpenFOAM errors without imposing completion heuristics."""`

逐条对照我方 G1–G4：

| 我方门禁 | foam-agent 对应 | 结论 |
|---|---|---|
| G1 结构完整 | 无（`subtasks` 生成即认为结构对） | 缺 |
| G2 `checkMesh` 含 `Mesh OK.` | 全库 `grep -rn "Mesh OK" src/` 为空；checkMesh 只在 gmsh 分支用两个字符串 | 缺（见下） |
| G3 短跑无 `FOAM FATAL` | 不查 `FOAM FATAL` 字样，只查 `ERROR:` + 退出码 | 弱等价 |
| G4 产物可读 | 不检查时间目录/场文件 | 缺 |

checkMesh 的唯一用法（仅 gmsh 自定义网格路径）是字符串匹配，不是 `Mesh OK.`：

- `references/repos/foam-agent/src/services/mesh.py:394` 原文：`        if "Failed" in checkmesh_output and "mesh checks" in checkmesh_output:`

**结论（明确写清）**：foam-agent 的成功判据是"进程没说错"，**没有独立判据**。具体失效面是：

1. 求解器提前收敛、或跑到一半 `stopAt writeNow` 退出但返回 0 ⇒ 被判 success；
2. 日志里没有 `ERROR:` 字样（如 `FOAM FATAL ERROR :` 带空格变体、或残差发散但未触发异常）⇒ 被判 success；
3. `check_foam_errors` 用 `re.DOTALL` 从第一个 `ERROR:` 截到文件尾，命中后塞给 Reviewer 的上下文可能上万字符；
4. 唯一能识破"没跑完"的信号本可以来自时间目录是否等于 `endTime`，但本项目从未检查 `controlDict` 的 `endTime`（全库无 `endTime` 相关校验代码）。

对外的状态有三个：`success` / `failed` / `partial_success`（后者专用于"仿真成功但可视化失败"，``references/repos/foam-agent/src/main.py:35`` 把它也算非零退出）。

### 8 部署依赖

- **OpenFOAM 版本**：容器基镜 `references/repos/foam-agent/docker/Dockerfile:2` 原文：`FROM openfoam/openfoam10-paraview510:latest AS builder`
- 同口径的 README：`references/repos/foam-agent/README.md:35` 原文：`The container comes with OpenFOAM v10, Conda, and all dependencies pre-installed.`
- **运行期硬检查**：进程启动前必须能拿到 `WM_PROJECT_DIR`，否则直接抛错——``references/repos/foam-agent/src/utils.py:1153`-1158`（"WM_PROJECT_DIR is not set. Please source OpenFOAM environment before running Foam-Agent"）
- **版本门只在显式指定 target 时才校验**：`foundation-v10` 要求 `WM_PROJECT_VERSION == "10"`，`esi-v2006` 要求 `v2006|2006`（``references/repos/foam-agent/src/utils.py:1175`-1185`）；`openfoam_target` 默认空串（``references/repos/foam-agent/src/config.py:46``），因此**默认路径不做版本校验，v13 上照样会跑**
- **Python**：3.12.9（``references/repos/foam-agent/environment.yml:238`` 的 `python=3.12.9`）
- **关键三方包**（`environment.yml` 实测条目）：`langgraph=0.2.71`、`langchain=0.3.18`、`faiss-cpu==1.10.0`、`fastmcp==2.13.0.1`、`pytorch=2.5.1` + `pytorch-cuda=12.4`、`pyvista=0.44.2`、`openai==1.61.1`、`anthropic==0.45.2`、`transformers==4.51.3`
- **API key**：需要。provider 六选一（`openai / openai-codex / anthropic / bedrock / ollama / deepseek`，``references/repos/foam-agent/src/config.py:34``），默认 `openai-codex` 走 OAuth 缓存
- **GPU**：非必须。GPU 只在 `environment.yml` 的 cuda 依赖里体现；嵌入默认用 HF 的 0.6B 模型，CPU 可跑
- **容器**：README 主推 docker 镜像 `leoyue123/foamagent`，但有非容器路径（直接 `python foambench_main.py`）

### 9 理论上优点 / 缺点

优点：

- 机制：把流水线切成 8 个 LangGraph 节点 + 7 个纯函数路由（`src/router_func.py`），每个节点只读写自己那几个 state 字段 → 收益：失败能归因到具体一跳，单跳可离线单测（`tests/` 下有 `test_lid_driven_cavity_services.py` 等按节点分文件）
- 机制：错误指纹 = （错误文本 + 过滤后 case 文件 + 用户需求）三元组，重复即终止（``references/repos/foam-agent/src/nodes/reviewer_node.py:21`-32`）→ 收益：把"同一错误烧满 25 轮"压成 2 轮，省掉最贵的一类无效 token
- 机制：检索先用 `case_domain` 做硬过滤再按 solver 重排（``references/repos/foam-agent/src/services/plan.py:249`-262`）→ 收益：召回集里不会出现跨物理域的教程（可压/不可压混召回是最常见的坏参考源）
- 机制：`input_writer_generation_mode="sequential_dependency"`（``references/repos/foam-agent/src/config.py:23``），后生成的文件能读到先生成的内容 → 收益：跨字典一致性（如 `0/p` 的 dimensions 与 `transportProperties` 的 nu 量纲）在生成阶段就对齐，少一轮修复

缺点：

- 机制：成功 = "没有 `ERROR:` 且退出码 0"，不查 `endTime` 目录、不查 `Mesh OK.`、不查物理量 → 代价：提前结束/发散但正常退出会被记 success，且该误报在 FoamBench 式汇总里与真成功不可区分（这正是"100% success rate"这类数字最脆弱的地方）
- 机制：语料以 git-lfs 指针入库（raw 文件 128–133 字节），必须用本机 OF 安装重建 → 代价：开箱不可检索；重建后的语料版本由操作者的 OF 决定，README 的 v10 语义与实际检索内容脱钩
- 机制：`run_local` 每次调用只重试 1 次（`max_retries=1`），而 LLM 修复环有 25 轮 → 代价：把"偶发进程失败"和"字典错误"混在同一预算里，25 轮里的绝大多数花在后者，前者只值 1 次
- 机制：模型在流水线内部没有工具，只能整段吐文件文本（`FoamPydantic`/`FoamfilePydantic`，``references/repos/foam-agent/src/utils.py:118`-124`）→ 代价：无法"只改一行"，每次修复都是整文件重写，diff 噪音大

### 10 对本项目的可迁移点

- **可迁移**：错误指纹去重终止（``references/repos/foam-agent/src/nodes/reviewer_node.py:21`-32`）。我们的 G1–G3 修复循环目前没有"无进展"守卫，最坏情况是同一 FATAL 反复重试到轮数上限。机制上用"错误首行 + 被改文件列表"做指纹即可，不需要向量。
- **可迁移**：reviewer 只产出 `rewrite_plan.target_files`，input_writer 只改这些文件（`src/services/review.py` + `input_writer` 的 `rewrite` 模式）→ 收益：修复面可审计，"改了哪几个字典"是显式数据而不是聊天记录。
- **不可迁移**：整 case 块的 FAISS 检索。它要求离线建库、且库绑死一个 OF 版本；我们已选定 grep 路线（AGENTS.md R1），再引入一份向量库会带来第二个语料版本，正好踩 R1 的"证据指向非权威树"。
- **门禁对比结论**：它的门禁**比我们软**，软在最后一步——我们有 G2（`checkMesh` 含 `Mesh OK.`）与 G3（无 `FOAM FATAL`）两条独立断言；它把 G3 降级成"退出码 + `ERROR:` 正则"，并且完全没有 G2。唯一比我们硬的地方是它有 25 轮 LLM 修复 + 指纹守卫，而我们的 G1–G3 目前是"两轮修不好就停"（AGENTS.md R8.4）——这一点上它更像"多试"，我们更像"早停"，两者可组合。

---

## 2. metaopenfoam（Terry-cyx/MetaOpenFOAM，tier B）

### 0 一句话定位与规模

一句话：基于 MetaGPT 的五角色消息总线（TaskDivide→Architect→InputWriter→Runner→Reviewer），把一句需求变成 OpenFOAM case 并跑到 `endTime`，另带一条 active_subspaces 参数优化支线。

实测规模（`references/repos/metaopenfoam`）：

- `find . -type f -name '*.py' | wc -l` → `60`（含 `active_subspaces/` 这个内嵌第三方库与 `__pycache__`）
- `find . -name '*.py' -not -path './.git/*' -exec wc -l {} + | tail -1` → `15132 total`
- 其中 `src/` 自身 `7435` 行（`find src -name '*.py' -exec wc -l {} + | tail -1`）
- 单文件最大：`src/actions/ReviewerAction.py` 1788 行、`src/actions/InputWriterAction.py` 1109 行、`src/actions/RunnerAction.py` 967 行、`src/actions/TaskDivideAction.py` 831 行
- 入口：``references/repos/metaopenfoam/src/OptMetaOpenfoam.py:19``（`async def main():`），由 `Makefile` 的 `run` 目标串起"配置→建库→跑"

注意：README 首屏已声明项目废弃并迁往 sim-cli。

- `references/repos/metaopenfoam/README.md:1` 原文：`# ⚠️ MetaOpenFOAM 已停止维护 / This project is deprecated`

### 1 输入形态

**一份 YAML**，路径由环境变量 `CONFIG_FILE_PATH` 传入（`Makefile` 里 `export CONFIG_FILE_PATH`）：

```
usr_requirment: "do an incompressible lid driven cavity flow ..."
max_loop: 20
temperature: 0.01
batchsize: 10
searchdocs: 2
run_times: 10
MetaGPT_PATH: "MetaGPT/"
OPENAI_API_KEY / OPENAI_PROXY / OPENAI_BASE_URL / model
```

字段读取在 `references/repos/metaopenfoam/src/config_path.py:31` 原文：`usr_requirment = config.get('usr_requirment', '')`

用户需求最终以一条 MetaGPT 消息投递：

- `references/repos/metaopenfoam/src/OptMetaOpenfoam.py:72` 原文：`    env.publish_message(Message(content=config_path.usr_requirment, send_to=TaskDivide))`

模型名有硬性前缀检查，不匹配直接 `sys.exit()`：``references/repos/metaopenfoam/src/config_path.py:45`-54`（`deepseek` 或 `gpt` 开头，否则 "the chat model is not identified"）。示例输入见 `inputs/Cavity.yaml`（`usr_requirment` 在第 1 行）。

### 2 分层与模块边界

```
src/OptMetaOpenfoam.py    装配 Environment + 5 个 Role，投递首条消息，跑 while 循环
src/roles/*.py            5 个 Role：只声明 set_actions() 与 _watch()（每个 46–56 行）
src/actions/*.py          Action：真正干活——拼 prompt、调 LLM、落盘、起进程
src/qa_module.py          FAISS 加载 + RetrievalQA 封装 + token 记账（491 行）
src/Tutorial_postprocess.py  tutorials → txt 语料（274 行）
src/Langchain_database_add_*.py  4 个建库脚本（各 56–59 行）
src/config_path.py        读 YAML、设环境变量、拼 sys.path（100 行）
src/Statistics.py         Executability/loop/token 统计
active_subspaces/         内嵌第三方优化库（含自己的 tests/ 与 tutorials/）
database/                 FAISS 索引落点（仓内只有 .gitkeep）
inputs/*.yaml             22 个任务输入（find inputs -name '*.yaml' | wc -l → 见下）
run/                      运行期 case 目录
```

- `find inputs -name '*.yaml' | wc -l` → `22`

三条边界的落点很清楚：

- **碰文件系统**：`src/actions/InputWriterAction.py`（拼路径写字典，`:339` 的 `file_path = f"{config_path.Case_PATH}/{folder_name}/{file_name}"`）
- **碰 LLM**：`src/qa_module.py`（`RetrievalQA` + `ChatOpenAI`/`ChatDeepSeek`，`:406-420`）
- **跑仿真**：``references/repos/metaopenfoam/src/actions/RunnerAction.py:534``（`def run_command(self, script_path, out_file, err_file, working_dir):`，内部 `subprocess.Popen(['bash', script_path], ...)`）

`roles/` 极薄是 MetaGPT 的强约束：角色只能声明"我订阅哪些 Action"，逻辑全在 Action 里——好处是消息路由可枚举，代价是 1788 行的 ReviewerAction 变成单体。

### 3 agent 拓扑

**五角色 + 消息总线（MetaGPT Environment）**，不是 planner-executor 二跳：

| 角色 | 类/文件 | 订阅（`_watch`） | 产出 |
|---|---|---|---|
| TaskDivide | ``references/repos/metaopenfoam/src/roles/TaskDivide.py:12`` | `UserRequirement` | 拆 4 类任务文本 |
| Architect | ``references/repos/metaopenfoam/src/roles/Architect.py:11`` | `TaskDivideAction` | 若干 subtask 消息 |
| InputWriter | ``references/repos/metaopenfoam/src/roles/InputWriter.py:13`` | `ArchitectAction, ReviewerAction` | 触发写文件 |
| Runner | ``references/repos/metaopenfoam/src/roles/Runner.py:10`` | `InputWriterAction` | 跑 Allrun，回状态 |
| Reviewer | ``references/repos/metaopenfoam/src/roles/Reviewer.py:11`` | `RunnerAction` | 出修复任务 |

传输格式是 MetaGPT 的 `Message`，**内容一律是字符串**，靠 `cause_by=Action 类` 做路由键：

- `references/repos/metaopenfoam/src/roles/Architect.py:40` 原文：`           self.rc.env.publish_message(Message(content=i, cause_by=ArchitectAction)) `
- `references/repos/metaopenfoam/src/roles/Runner.py:18` 原文：`        self._watch({InputWriterAction})`

orchestrator 就是 MetaGPT 的 `Environment.run()` 轮询 + 每个 Role 的 `_act()`：

- `references/repos/metaopenfoam/src/OptMetaOpenfoam.py:73` 原文：`    while not env.is_idle and not config_path.should_stop: `

具体到"怎么知道该写哪些文件"，InputWriter 用的是**消息计数**而不是结构化清单：``references/repos/metaopenfoam/src/roles/InputWriter.py:27`-31` 先取 1 条消息读 `number_subtasks`，再按这个数字切片取上下文（`context = self.get_memories(k=1+int(number_subtasks.content)+1)`）。这是全项目最脆的一处耦合：subtask 数量变成一个内容为数字的字符串消息，顺序或格式一变，切片就错位。

### 4 工具接口

**没有工具接口**。模型不产出 tool_call，只产出文本；"执行"由 Action 代码在拿到文本后自己做（写文件、起 bash）。因此它的"工具集"其实是 prompt 模板集：

- 写字典：`src/actions/InputWriterAction.py`（1109 行，含各类文件的 prompt）
- 跑与判：`src/actions/RunnerAction.py`（967 行）
- 审与修：`src/actions/ReviewerAction.py`（1788 行，含 3、4、5 三档 Executability 的分支 prompt）

唯一接近"工具"的东西是它给模型的**命令白名单**（Allrun 里允许出现的命令族），在 `RunnerAction.py` 的注释里可见：

- `references/repos/metaopenfoam/src/actions/RunnerAction.py:57` 原文：`        #     runlists = ['isTest', 'getNumberOfProcessors','getApplication','runApplication','runParallel','compileApplication','cloneCase','cloneMesh']`

### 5 知识来源

纯 RAG（FAISS）+ 硬编码教程文本，**无微调**。四个库：`openfoam_tutorials`、教程名库、`allrun` 库、`ori` 库（``references/repos/metaopenfoam/src/qa_module.py:403`-484` 四段 `setup_qa_*`，每段各 `FAISS.load_local(...)`）。

语料来源与切分：

- `references/repos/metaopenfoam/src/Tutorial_postprocess.py:1` 原文：`# this function is to convert tutorials of openfoam10 to txt file which could be used as a database of metaOpenfoam`
- 分块：**没有 splitter，一个"输入文件块"一个 Document**。`references/repos/metaopenfoam/src/Langchain_database_add_tutorial.py:22` 原文：`pattern = re.compile(r"```input_file_begin:(.*?)input_file_end.```", re.DOTALL)`
- 语料生成的硬阈值：单文件超过 1000 行直接丢弃，``references/repos/metaopenfoam/src/Tutorial_postprocess.py:35`` 原文：`                        if len(lines) > 1000:`
- 嵌入：`HuggingFaceEmbeddings()` **无参数**，模型名未在本机代码中声明（``references/repos/metaopenfoam/src/Langchain_database_add_tutorial.py:46``、``references/repos/metaopenfoam/src/qa_module.py:406``）
- 检索条数：`k = config_path.searchdocs`，默认 2

- `references/repos/metaopenfoam/src/config_path.py:35` 原文：`searchdocs = config.get('searchdocs', 2)`
- `references/repos/metaopenfoam/src/qa_module.py:414` 原文：`    retriever = vectordb.as_retriever(search_type="similarity", search_kwargs={"k": config_path.searchdocs})`

检索模式是 `chain_type="stuff"`（``references/repos/metaopenfoam/src/qa_module.py:418``），即把 k 条整块文本直接塞进上下文——单块可能是一整个 `blockMeshDict`，k=2 时上下文里通常是两个完整字典。

### 6 错误处理与自修正

有，三层计数器：

1. **Run 层**：`global_statistics.Run_loop` 递增（``references/repos/metaopenfoam/src/actions/ReviewerAction.py:456``），上限来自 YAML 的 `max_loop`（默认 20，``references/repos/metaopenfoam/src/config_path.py:32``）
2. **后处理层**：`Postprocess_loop`、`Postprocess_python_loop` 各自独立计数（``references/repos/metaopenfoam/src/actions/ReviewerAction.py:590``、`:613`），即"仿真跑通但画图脚本报错"有自己的预算
3. **Executability 状态机**：跑不动时按"哪个命令失败"写 `*.err` 文件（``references/repos/metaopenfoam/src/actions/RunnerAction.py:137``）并回灌给 Reviewer

- `references/repos/metaopenfoam/src/actions/ReviewerAction.py:456` 原文：`                global_statistics.Run_loop = global_statistics.Run_loop + 1`

触发条件 = "`check_foam_errors` 返回非空" 或 "Executability 未达 3"。没有指纹去重，所以同一错误会一直烧到 `max_loop`——这是与 foam-agent 最大的工程差距。

### 7 它怎么知道跑成功了（门禁问题）

**判据是一条四级阶梯 `Executability ∈ {0,1,2,3}`，最高档是"存在以 `endTime` 命名的目录"。这是五个项目里唯一显式检查"到没到终态"的。**

先看错误检测（决定 0/1）：

- `references/repos/metaopenfoam/src/actions/RunnerAction.py:564` 原文：`                if 'error' in line.lower() and 'foam' in line.lower():`
  即：任何 `log*` 文件里出现同时含 `error` 与 `foam` 的行（大小写不敏感）就算错，前后各取 30/60 行塞进 `error_content`（`:570-574`）。这比 `ERROR:` 正则宽，能抓到 `FOAM FATAL IO ERROR:` 与 `FOAM FATAL ERROR :` 两种变体。

再看终态判定（决定 3）：

- `references/repos/metaopenfoam/src/actions/RunnerAction.py:652` 原文：`                if line.strip().startswith('endTime')`
- `references/repos/metaopenfoam/src/actions/RunnerAction.py:653` 原文：`                    endtime_value = line.split('endTime', 1)[1].strip().strip(';').replace(" ", "")`
- `references/repos/metaopenfoam/src/actions/RunnerAction.py:662` 原文：`            if os.path.isdir(folder_path) and folder_name == endtime_value:`
- `references/repos/metaopenfoam/src/actions/RunnerAction.py:663` 原文：`                global_statistics.Executability = 3`

中间档（决定 2）是"存在任意非 0 的纯数字目录"：

- `references/repos/metaopenfoam/src/actions/RunnerAction.py:694` 原文：`                if re.search(r'\b(?!0\b)\d+\b', folder_name):`
- `references/repos/metaopenfoam/src/actions/RunnerAction.py:695` 原文：`                    global_statistics.Executability = 2`

`6` 档是另一条支线（"该 case 已经跑过"）：``references/repos/metaopenfoam/src/actions/InputWriterAction.py:264`-265`（`if global_statistics.Executability == 0: global_statistics.Executability = 6`）。

**门禁强弱逐个说清**：

- 比 foam-agent 硬：它检查"终态时间目录**存在**"，能识破"跑到一半退出但返回 0"；foam-agent 完全不能。
- 仍不硬的地方（三条，都是机制性的）：
  1. 只比目录名**字符串**：`endTime 1;` 与目录 `1.0` 不相等 → 真跑完也可能判成 2（`endTime` 解析是纯文本切分，`:653`）；
  2. 只证明"写了终态目录"，不证明收敛、不证明物理合理——发散也能写出 `endTime` 目录；
  3. 完全没有 `checkMesh`：`grep -rn "checkMesh" src/` 返回空，网格质量只能靠求解器报错间接暴露。
- 与我方 G1–G4 的映射：G3（无 FATAL）≈ 它有且更宽；G2（`Mesh OK.`）**完全没有**；"产物存在"≈ 它的 3 档。也就是说它在 G3 上比我们硬，在 G2 上是零。

### 8 部署依赖

- **OpenFOAM 版本**：README 要求 OpenFOAM-10 已 source（"OpenFOAM‑10 installed and sourced"），语料亦取自 openfoam10 tutorials（``references/repos/metaopenfoam/src/Tutorial_postprocess.py:1``）。代码里不存在版本探测——`grep -rn "WM_PROJECT_VERSION" src/` 为空
- **Python**：``references/repos/metaopenfoam/environment.yml:6`` 的 `python=3.11.4`；另有 `requirements.txt` 五个 Python-only 依赖（`langchain==0.3.23`、`langchain_community==0.3.21`、`langchain_huggingface`、`langchain_deepseek==0.1.3`、`vtk>=9.0`）
- **外部源码依赖（硬）**：MetaGPT 不在仓库里，必须自己 clone 并把路径写进 YAML 的 `MetaGPT_PATH`（``references/repos/metaopenfoam/src/config_path.py:37`-38`、`:58` 的 `sys.path.append(MetaGPT_PATH)`）；`active_subspaces/` 是 vendored 的本地包
- **API key**：必需。`OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY` 由 YAML 读入并写进 `os.environ`（``references/repos/metaopenfoam/src/config_path.py:45`-51`）；还默认塞了一个 `OPENAI_PROXY`
- **Docker**：不依赖
- **GPU**：不需要（没有 torch 依赖，嵌入走 `HuggingFaceEmbeddings()` 的 CPU 路径）

### 9 理论上优点 / 缺点

优点：

- 机制：用 `Executability` 四级整数表示"跑到哪一步"，而不是布尔成功/失败（``references/repos/metaopenfoam/src/actions/RunnerAction.py:640`-707`）→ 收益：修复 prompt 能按档位分流（3/4/5 三档各有分支，``references/repos/metaopenfoam/src/actions/ReviewerAction.py:584`-587` 的注释即此设计），失败原因不必再从日志重建
- 机制：把"仿真/后处理/画图脚本"三条链路各自计数（`Run_loop` / `Postprocess_loop` / `Postprocess_python_loop`）→ 收益：画图脚本报错不会消耗仿真的修复预算
- 机制：教程文本在入库前就按 `<input_file_begin>` 切块，且 >1000 行文件直接丢弃（``references/repos/metaopenfoam/src/Tutorial_postprocess.py:35``）→ 收益：检索结果的单块体积可控，不会把一篇巨型字典整段塞进上下文
- 机制：角色极薄、消息路由靠 `_watch({ActionClass})` 声明式表达（`roles/*.py` 每个 46–56 行）→ 收益：新增一个角色不需要改调度代码

缺点：

- 机制：无错误指纹、无"无进展"判定，修复只受 `max_loop`（默认 20）约束（``references/repos/metaopenfoam/src/config_path.py:32``）→ 代价：同一 FATAL 会烧满 20 轮，token 成本随失败模式线性叠加
- 机制：subtask 数量通过"内容为数字的 Message"传递，InputWriter 用 `get_memories(k=1+int(number_subtasks.content)+1)` 切片（``references/repos/metaopenfoam/src/roles/InputWriter.py:27`-31`）→ 代价：消息顺序或计数格式一变就取错上下文，且这种错不会抛异常，只会生成错文件
- 机制：`endTime` 用文本切分 + 目录名字符串相等来判终态（``references/repos/metaopenfoam/src/actions/RunnerAction.py:652`-663`）→ 代价：`1` vs `1.0`、`endTime` 写成表达式（如 `$stopTime`）时判据失效，真成功被记成 2
- 机制：完全没有 checkMesh，网格质量只能等求解器报错（`grep -rn "checkMesh" src/` 空）→ 代价：坏网格的失败被归因到字典/数值格式，修复方向从一开始就错

### 10 对本项目的可迁移点

- **可迁移**：`Executability` 式多档状态，而不是二值 `pass/fail`。我们 `bench/results.csv` 已有 `status` 列（R12 要求三态），可再细化成"结构通过/网格通过/短跑通过/产物可读"四档位整数，好处是失败归因不用回头读日志。
- **可迁移**：`endTime` 目录存在性检查（``references/repos/metaopenfoam/src/actions/RunnerAction.py:662``）。这正是我方 G4"产物可读"最便宜的实现：从 `controlDict` 取 `endTime`，比对时间目录名。注意要按浮点比较而不是字符串比较，否则会复刻它的 bug。
- **不可迁移**：MetaGPT 的字符串消息总线。把结构化数据（subtask 列表）序列化成 `Message(content=str(len(subtasks)))` 再靠下标切片还原，等于自己实现一个易碎的 RPC；我们已有 `case.meta` 与 CSV 落盘，没必要引入第二套消息层。
- **门禁对比结论**：它的门禁在"是否跑完"这一维**比我们硬**（我们 G4 目前只要求"产物可读"，没有硬断言"终态目录存在"），在"网格质量"这一维**比我们软到零**（无 checkMesh）。硬的那一步正是我们该补的：把 `endTime` 目录存在性变成 G4 的显式断言。

---

## 3. openfoam-mcp-server（webworn/openfoam-mcp-server，tier B）

### 0 一句话定位与规模

一句话：一个 C++20 写的原生 MCP server（JSON-RPC 2.0 over stdio），把 OpenFOAM 封装成 12 个"领域分析工具"（管道流、外流、传热、多相、网格质量、STL、RDE 爆震、湍流），并内置一套苏格拉底式提问的"CFD 教学"状态机。

实测规模（`references/repos/openfoam-mcp-server`）：

- `find . -type f -name '*.py' | wc -l` → `20`（全是外围脚本：可视化、ParaView 服务、示例）
- `find . -name '*.cpp' -o -name '*.hpp' -o -name '*.h' | grep -v '\.git' | xargs wc -l | tail -1` → `23996 total`
- 其中 `src/tools/` 一个目录就占 `13317` 行（`find src/tools -maxdepth 1 -type f -name '*.cpp' -o -name '*.hpp' | xargs wc -l | tail -1`）
- 单文件最大：`src/tools/context_engine.cpp` 1329 行、`src/tools/rde_wave_analyzer.cpp` 923 行、`src/tools/rde_3d_geometry.cpp` 667 行
- 入口：``references/repos/openfoam-mcp-server/src/main.cpp:21``（`int main(int argc, char* argv[]) {`）

### 1 输入形态

**MCP 协议报文**，没有自然语言入口（除了一个 `start_cfd_assistance` 工具收 `user_input` 字符串）。客户端（Claude Code / Cursor）通过 stdin 发 JSON-RPC，参数是一个按工具 schema 校验的 JSON object。

工具注册在 ``references/repos/openfoam-mcp-server/src/main.cpp:52`-59`，服务启动即阻塞在 stdin：

- `references/repos/openfoam-mcp-server/src/main.cpp:53` 原文：`        registerPipeFlowTool(server);`
- `references/repos/openfoam-mcp-server/src/main.cpp:73` 原文：`        server.start();`

典型调用形如 `run_pipe_flow({"diameter":..., "length":..., "velocity":..., "viscosity":...})`，参数校验在分析器里手工做（``references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:120`-126` 的 `throw std::invalid_argument("Diameter too large (>10 m), please verify input")`）。

### 2 分层与模块边界

```
src/main.cpp            装配：注册 5 个注册函数 → server.start()
src/mcp/                JSON-RPC 2.0 编解码 + McpServer 生命周期（server.cpp / json_rpc.cpp）
src/openfoam/           领域分析器与 case 模板：pipe_flow / external_flow / heat_transfer
                        / multiphase_flow / mesh_quality / stl_analyzer / snappy_templates
                        / case_manager（建 case、跑 case、抽结果）
src/tools/              工具外壳（12 个）：schema + execute 转发到分析器；context_engine 是教学状态机
src/utils/              terminal_manager（popen 执行 + 输出解析）、logging
results/                落盘的 case（cavity / car_aerodynamics）
examples/, docs/        C++ 示例与 OpenFOAM 知识文档
```

三层边界很硬：

- **碰文件系统**：`src/openfoam/case_manager.cpp`（写 `system/blockMeshDict` 等，`:420` 起）
- **碰进程**：``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:109`-141`（`fork` + `execl("/bin/sh", "sh", "-c", command...)`）、``references/repos/openfoam-mcp-server/src/utils/terminal_manager.cpp:135``（`popen`）
- **碰 LLM**：**没有**。全仓无 LLM 客户端，`src/mcp/` 只做协议，语义理解完全外包给调用方

这一层划分是本项目最值得看的地方：它把"CFD 知识"写成 C++ 模板与判定阈值，而不是 prompt。

### 3 agent 拓扑

**没有 agent 循环**。它是工具层：拓扑上的"agent"是外部客户端（Claude Code），本进程只提供 12 个原子能力。

进程内部有两个状态机，都不是 agent：

1. `CFDAssistant`：用户建模 + 苏格拉底提问（`src/tools/cfd_assistant_tool.cpp` + `context_engine.cpp` 的 `UserConceptModel`/`conceptModels_`）
2. `Pipeline`（Python 侧不存在；C++ 侧无）；case 生命周期由 `CaseManager` 的 `caseResults_` map 管（`case_manager.hpp`）

对话式入口的"传输格式"仍是 MCP 工具返回：`ToolResult` 里打包文本 + 结构化 JSON（``references/repos/openfoam-mcp-server/src/tools/cfd_assistant_registration.cpp:102`-127` 的 `start_cfd_assistance`）。

### 4 工具接口

**MCP tool（JSON schema）**，名字与定义处（`getName()` 全是 `static std::string`）：

| tool 名 | 定义处 |
|---|---|
| `run_pipe_flow` | ``references/repos/openfoam-mcp-server/src/tools/pipe_flow_tool.hpp:46`` |
| `analyze_external_flow` | ``references/repos/openfoam-mcp-server/src/tools/external_flow_tool.hpp:48`` |
| `analyze_heat_transfer` | ``references/repos/openfoam-mcp-server/src/tools/heat_transfer_tool.hpp:33`` |
| `analyze_multiphase_flow` | ``references/repos/openfoam-mcp-server/src/tools/multiphase_flow_tool.hpp:58`` |
| `assess_mesh_quality` | ``references/repos/openfoam-mcp-server/src/tools/mesh_quality_tool.hpp:44`` |
| `analyze_stl_geometry` | ``references/repos/openfoam-mcp-server/src/tools/stl_analyzer_tool.hpp:44`` |
| `analyze_turbulent_flow` | ``references/repos/openfoam-mcp-server/src/tools/turbulent_flow_tool.hpp:210`` |
| `analyze_rde_waves_2d` | ``references/repos/openfoam-mcp-server/src/tools/rde_wave_tool.hpp:44`` |
| `analyze_rde_waves_3d` | ``references/repos/openfoam-mcp-server/src/tools/rde_3d_wave_tool.hpp:44`` |
| `generate_rde_3d_geometry` | ``references/repos/openfoam-mcp-server/src/tools/rde_3d_geometry_tool.hpp:44`` |
| `calculate_rde_3d_performance` | ``references/repos/openfoam-mcp-server/src/tools/rde_3d_performance_tool.hpp:45`` |
| `start_cfd_assistance` / `continue_cfd_conversation` / `execute_openfoam_operation` / `analyze_cfd_results` / `get_cfd_learning_guidance` | ``references/repos/openfoam-mcp-server/src/tools/cfd_assistant_registration.cpp:102`/128/160/178/196` |

- `references/repos/openfoam-mcp-server/src/tools/pipe_flow_tool.hpp:46` 原文：`    static std::string getName() { return "run_pipe_flow"; }`

**实测与 README 不符（重要）**：`src/main.cpp` 只调用 5 个注册函数（pipe/external/heat/multiphase/assistant），即 4 + 5 = **9 个工具**；`assess_mesh_quality`、`analyze_stl_geometry`、4 个 RDE 工具、`analyze_turbulent_flow` 共 7 个只在测试程序里注册：

- `references/repos/openfoam-mcp-server/src/main_test.cpp:52` 原文：`            registerMeshQualityTool(server);`
- `grep -n "registerMeshQualityTool" src/main.cpp` → 空

所以 README 的 "12 registered tools" 指的是**全仓工具总数**（其中 7 个只在 `openfoam-mcp-server-test` 里可用），不是主程序暴露的数量。主程序实际暴露 9 个 —— 包括网格质量工具在主程序里**不可达**。

### 5 知识来源

**纯硬编码**：C++ 常量表 + 模板字符串，无检索、无微调、无外部语料。

- 概念图谱：``references/repos/openfoam-mcp-server/src/tools/context_engine.hpp:236``（`class CFDKnowledgeGraph`）持 `std::map<std::string, CFDConcept> concepts_` 与 `conceptDependencies_`，概念在 ``references/repos/openfoam-mcp-server/src/tools/context_engine.cpp:274`` 起逐条硬编码（`reynolds.name = "Reynolds Number";`）
- case 模板：`src/openfoam/*.cpp` 里逐行 `file << "..."` 拼字典（``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:420`-436` 的 blockMeshDict）
- 错误知识：5 Whys 方法写死在 `context_engine` 的字符串里

- `references/repos/openfoam-mcp-server/src/tools/context_engine.cpp:274` 原文：`    reynolds.name = "Reynolds Number";`

代价很直接：这些阈值与模板是**写死在二进制里**的，OpenFOAM 换一个版本（v12→v13）不改代码就带不过去。

### 6 错误处理与自修正

**无自修正**。所有 tool 的错误路径都是 `try/catch` → 打包成 `ToolResult.addErrorContent(...)` 返回给调用方：

- `references/repos/openfoam-mcp-server/src/tools/pipe_flow_tool.cpp:212` 原文：`void registerPipeFlowTool(McpServer& server) {`（其 lambda 内 `return tool->execute(arguments);`，无重试、无回读）
- 分析器层：``references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:188`` 的 `catch (const std::exception& e)` 只做 `results.success = false; results.errorMessage = e.what();`

修正责任完全在外部 agent——这符合 MCP 的分工，但意味着它自身没有任何"改一轮再跑"的能力。

### 7 它怎么知道跑成功了（门禁问题）

**判据：`blockMesh` 退出码 0，且求解器命令退出码 0。求解器命令来自一个默认构造的参数对象，永远是 `simpleFoam`。**

``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:919`-972` 是完整的 `runCase`：

- `references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:938` 原文：`    int meshResult = executeCommand("blockMesh", casePath.string(), "blockMesh.log");`
- `references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:947` 原文：`    CaseParameters params;`
- `references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:949` 原文：`    int solverResult = executeCommand(params.solver, casePath.string(), "solver.log");`

`params` 是默认构造，`params.solver` 取的是头文件里的默认值：

- `references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:56` 原文：`          solver("simpleFoam"),`

而分析器明明为自己算过正确的 solver 字符串，却没有传下去：

- `references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:134` 原文：`        params.solver = "foamRun -solver incompressibleFluid";`

``references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:170`` 拿到 `params` 后只把 `caseName` 等写进 case，`:175` 直接调 `caseManager_->runCase(caseId)` —— 没有把 `params` 交给 `CaseManager`。因此每个 case 实际执行的求解器都是 `simpleFoam`，与它自己生成的字典（`foamRun` 语法）不匹配。

成功判定只有一个布尔表达式：

- `references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:83` 原文：`    bool isSuccess() const { return status == "completed" && exitCode == 0; }`

**更关键的一层：即使"跑成功"，返回的物理量也不是从仿真结果里读的。** `processResults` 用的是解析公式：

- `references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:185` 原文：`            results.frictionFactor = calculateLaminarFrictionFactor(results.reynoldsNumber);`
- `references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:221` 原文：`        results.maxVelocity = 1.224 * input.velocity;`
- `references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:224` 原文：`    results.pressureDrop = calculateTheoreticalPressureDrop(input);`

日志解析只做一件事——抠 `ExecutionTime`：

- `references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:1009` 原文：`        if (line.find("ExecutionTime") != std::string::npos) {`

`extractResults` 另外只把新出现的时间目录名收集成字符串（``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:991`-996`），**不读任何场数据**。

**结论（三句话）**：

1. 成功判据 = 两个子进程退出码，无日志关键字、无 `Mesh OK.`、无物理量范围检查；
2. 该判据在退出码层面被"默认 solver"这个 bug 短路：`simpleFoam` 在 v13 不存在（`ls /opt/openfoam13/applications/legacy/incompressible` 只有 `adjointShapeOptimisationFoam icoFoam porousSimpleFoam shallowWaterFoam`），`sh -c simpleFoam` 必然 127 退出，于是 **`runCase` 在本机 v13 上恒失败**——不是"误报成功"，而是"永远跑不成功"；
3. 反过来说，一旦 `simpleFoam` 存在（例如某些装了旧版二进制的机器），返回值里的 `frictionFactor`/`pressureDrop`/`maxVelocity` **本来就不是仿真产物**，而是 `PipeFlowInput` 的解析解，模型据此得出的"结论"与算例是否真跑无关。

（注：上面第 2 条关于 v13 的事实来自本机 `ls`，属 OpenFOAM 源码事实，与第三方代码引用分列；`grep -rn "simpleFoam" /opt/openfoam13/applications` 未检出同名应用。）

### 8 部署依赖

- **OpenFOAM 版本**：README badge 与安装命令都是 12 —— ``references/repos/openfoam-mcp-server/README.md:5`` 原文：`[![OpenFOAM](https://img.shields.io/badge/OpenFOAM-12-blue)](https://openfoam.org/)`；``references/repos/openfoam-mcp-server/README.md:257`` 原文：`sudo apt-get install openfoam12`
- **编译期硬依赖**：CMake 直接找 OF 库，找不到就 `FATAL_ERROR` —— ``references/repos/openfoam-mcp-server/CMakeLists.txt:12`` 原文：`set(OPENFOAM_DIR "/opt/openfoam12" CACHE PATH "OpenFOAM installation directory")`；``references/repos/openfoam-mcp-server/CMakeLists.txt:37`` 原文：`    message(FATAL_ERROR "❌ OpenFOAM library not found at ${OPENFOAM_LIB_DIR}")`
- **链接的具体库**：`libOpenFOAM`、`libfiniteVolume`、`libmeshTools`、`Pstream`(dummy)（``references/repos/openfoam-mcp-server/CMakeLists.txt:20`-25`）
- **语言/构建**：C++20（README badge `C++-20`），`cmake` + `make`
- **第三方包**：`nlohmann-json3-dev`、`libboost-system-dev`、`libboost-thread-dev`、`sqlite3`/`libsqlite3-dev`（README 依赖段）
- **Docker**：`Dockerfile:2` 是 `FROM ubuntu:22.04`，内部 `apt-get install -y openfoam12`（`Dockerfile:29`），并设死 `WM_PROJECT_DIR=/opt/openfoam12`（`Dockerfile:35`）
- **API key / GPU**：都不需要
- **本机可行性**：`/opt/openfoam13/platforms/linux64GccDPInt32Opt/lib/libOpenFOAM.so` 与 `lib/dummy/libPstream.so` 均存在，`-DOPENFOAM_DIR=/opt/openfoam13` 可绕过路径问题；**能否通过 v13 头文件编译未验证**（本阶段禁止编译/运行被测代码）

### 9 理论上优点 / 缺点

优点：

- 机制：把领域知识写成 C++ 常量与阈值（`context_engine.cpp` 的概念表、`pipe_flow.cpp` 的 `isLaminar()` 分流），而不是 prompt → 收益：判定完全确定，不受模型随机性影响，也不会出现"模型忘了某条规则"
- 机制：`fork`+`execl` 执行，stdout/stderr 由子进程 `dup2` 直接重定向到 `blockMesh.log`/`solver.log`（``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:120`-127`）→ 收益：输出不经过父进程内存，长日志不会撑爆内存
- 机制：MCP 工具粒度是"CFD 分析任务"（`run_pipe_flow`、`assess_mesh_quality`）而不是"shell 命令" → 收益：调用方不需要知道 OpenFOAM 字典细节，参数是物理量（直径/长度/流速/粘度）

缺点：

- 机制：`runCase` 用默认构造的 `CaseParameters` 取 solver（``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:947`-949` + ``references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:56``）→ 代价：每个分析器辛苦算出的 solver 与参数被丢弃，全部 case 都跑 `simpleFoam`；在无该二进制的 OF 版本上恒失败，且错误信息是 `blockMesh failed` 或空日志，归因方向被带偏
- 机制：结果物理量由解析公式计算并与仿真结果混在同一 `PipeFlowResults` 结构里返回（``references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:213`-227`）→ 代价：调用方无法区分"算出来的"和"跑出来的"，模型的后续推理建立在理论值上
- 机制：12 个工具里 7 个只在 `main_test.cpp` 注册（``references/repos/openfoam-mcp-server/src/main.cpp:52`-59` vs ``references/repos/openfoam-mcp-server/src/main_test.cpp:52`-94`）→ 代价：README 的"12 registered tools / 75% Functional"与主程序能力不符，网格质量这个最该用的工具在主程序里不可达
- 机制：知识以硬编码字符串与阈值存在于二进制（`context_engine.cpp`）→ 代价：换 OF 版本必须改代码重编译，无法像语料那样"重建一次索引"

### 10 对本项目的可迁移点

- **可迁移**：把门禁写成"两条独立断言"的形式——`blockMesh` 单独判、solver 单独判（``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:938`-949`）。我们 `verify_case.sh` 现在是 G1/G2/G3 顺序执行、遇错即停，可以改成"两条都跑完再报"，缺点定位更快（是网格挂了还是求解挂了）。
- **可迁移**：子进程输出用 `dup2` 直接落盘而不是 `communicate()` 收进内存（``references/repos/openfoam-mcp-server/src/openfoam/case_manager.cpp:120`-127`）。长求解的残差日志可能几十 MB，这一点对 WSL 小内存机器直接相关。
- **不可迁移**：解析公式与仿真结果同结构返回（``references/repos/openfoam-mcp-server/src/openfoam/pipe_flow.cpp:185`-227`）。这与我们 R4"agent 自述不算证据"直接冲突——我们的产物必须能指回 `runs/<case_id>/log.*`，不能让"理论值"混进 `results.csv`。
- **门禁对比结论**：它的门禁**比我们软**，软在没有任何日志层断言（我们 G2 要 `Mesh OK.`、G3 要无 `FOAM FATAL`）；它唯一的硬信号是退出码，而这个信号被默认 solver 短路。可借鉴的只有"网格/求解分两条断言"这个**结构**，判据内容要换成我们的 G2/G3。

---

## 4. nullflux（LZF1111/nullflux，tier B）

### 0 一句话定位与规模

一句话：闭源"sealed"发行的本地 Web 应用 **CFDriver**——浏览器里的多轮对话 + 91 个工具，直接在你的 Linux 工作站上读论文、写字典、跑 OpenFOAM/MFIX/LBM、调 ParaView 出图。

实测规模（`references/repos/nullflux`）：

- `find . -type f -name '*.py' | wc -l` → `0`（公开树里没有任何 Python 源文件）
- `wc -l server.js` → `8496`（`534267` 字节，可读源码，但缺一个模块）
- 三个 tar.gz 内容完全相同：`md5sum *.tar.gz` 三行都是 `0522f308fb0a1148e2dc4b8210d318ab`，各 `2036372` 字节
- 压缩包内 `tar tzvf` 实测：`server.bundle.mjs` `4259215` 字节、`public/app.js` `203349` 字节、`public/vendor/three/three.module.js` `1272972` 字节，共 23 个条目
- 入口：仓内**没有** `start.sh`（`ls references/repos/nullflux` 只有 `README.md`、`server.js`、三个 `*-sealed.tar.gz`、`docs/`），真正跑的是 sealed bundle，不是仓里的 `server.js`

### 1 输入形态

浏览器 UI（`public/index.html` 55425 字节）+ WebSocket 长连接 + REST。

- 用户在设置页填：LLM Provider + API Key、ParaView 路径、OpenFOAM 根目录（压缩包内 README 第 31 行 `- LLM Provider + API Key`）
- 对话输入是自然语言；也可上传 PDF/论文、STL、网格文件
- 入口在 `server.js` 的 express 路由（`grep -c "app.post" server.js` → `37`），工具调用参数是 JSON

OpenFOAM 根目录可自动探测，扫这三个目录：

- `references/repos/nullflux/server.js:101` 原文：`    const candDirs = ['/usr/lib/openfoam', '/opt/openfoam', '/opt/OpenFOAM', '/opt'];`
- `references/repos/nullflux/server.js:102` 原文：`    const FOAM_RE = /^(?:openfoam|OpenFOAM[-_]?)[\w.-]*$/i;`

这条正则可以匹配 `openfoam13`，且 ESI 的嵌套目录（`openfoam2312/`）也单独处理（`:114-118`）——**它不为某个版本硬编码路径**，这是它能跨版本的前提。

### 2 分层与模块边界

```
server.js               可读主程序：工具 schema 表、执行器、UI 后端、状态机
                        —— 但它 import 的 ./skills.js 不在仓内（见下）
*.tar.gz → sealed/      真正发行的运行体：server.bundle.mjs（4.26 MB，混淆）
                        + doc_reader.py / nb_kernel_host.py（明文 Python 辅助）
                        + public/（前端 + three.js）
docs/                   宣传页 index.html、demo.mp4、截图（无技术文档）
```

**关键事实：仓里的 `server.js` 不能独立运行。**

- `references/repos/nullflux/server.js:12` 原文：`import * as SkillLib from './skills.js';`
- `ls skills.js` → `ls: cannot access 'skills.js': No such file or directory`

而 `server.bundle.mjs` 是标准 `javascript-obfuscator` 产物（首行即 `const _0x92b1a7=_0x2d19;` 字符串数组 + 解码函数），在 bundle 里 `grep -ci openfoam` 只有 `2` 处命中——**字符串被编码，静态阅读拿不到工具实现**。

所以三个边界里有两个只能看到"接口"，看不到"实现"：

- **碰文件系统**：可读（`server.js` 的工具层）
- **碰 LLM**：可读（prompt 与工具 schema 在 `server.js`）
- **跑仿真**：部分可读（`runOpenFoam`/`_foamExecCapture` 在 `server.js`），真实行为在 bundle 内，**未确定**

### 3 agent 拓扑

**单 agent + 阶段状态机**（不是多角色）：

- 一个对话 agent，工具集按域切分：`web / doc / sim / foam / mfix / lbm / opt`（``references/repos/nullflux/server.js:396`-402`）
- 阶段状态机：`run_stage_start` / `run_stage_done`，把状态写 `runs/<runId>/state.json`，可断点续跑（schema 注释原文见 ``references/repos/nullflux/server.js:323``）
- 计划对账：`run_stage_done` 的返回里会带"本任务还没建计划"或"还剩几项待办"（``references/repos/nullflux/server.js:3880``），即**用 todo 列表交叉检查阶段是否被跳过**
- 熔断器 `WATCHDOG`：单工具连续失败 5 次或总时长超 6 小时即 `[WATCHDOG_HALT]`

- `references/repos/nullflux/server.js:3400` 原文：`const WATCHDOG = { maxFailPerTool: 5, maxRunMs: 6 * 3600 * 1000 };`

传输格式：工具调用是 OpenAI 风格 `{type:'function', function:{name, parameters}}`，工具返回是**字符串**（``references/repos/nullflux/server.js:3894`` 返回的是 `[foam_solve_verify] passed=… reasons:… JSON:…` 这种人类与模型都能读的文本）。

### 4 工具接口

**function calling**，工具表集中在 ``references/repos/nullflux/server.js:232`` 的 `const TOOLS = [` 数组里。工具名实测去重计数：

- `grep -o "name: '[a-z_0-9]*'" server.js | sort -u | wc -l` → `91`

按域分组（``references/repos/nullflux/server.js:396`-402` 的 `sim/foam/mfix/lbm/opt/...` 白名单）：`foam` 组 28 个，加上 `sim` 组的 `sim_open_paraview`，共 29 个：

`foam_find_tutorial`、`foam_find_source`、`foam_clone_tutorial`、`foam_inspect_case`、`foam_run_solver_async`、`foam_solver_status`、`foam_solver_stop`、`foam_stl_inspect`、`foam_mesh_plan`、`foam_compute_first_layer`、`foam_mesh_box_stl`、`foam_stl_generate`、`foam_env_check`、`foam_residual_series`、`foam_compare_render`、`foam_mesh_verify`、`foam_mesh_stl_check`、`foam_stl_render`、`foam_patch_diff`、`foam_geom_verify`、`foam_solve_verify`、`foam_post_verify`、`paper_param_verify`、`vision_analyze`、`sim_render`、`read_document`、`paper_extract`、`foam_dry_compile`、`sim_open_paraview`。

- `references/repos/nullflux/server.js:407` 原文：`const NEEDS_APPROVAL = new Set(['run_command', 'sim_run_openfoam', 'foam_run_solver_async', 'foam_mesh_plan', 'foam_mesh_box_stl', 'foam_stl_generate', 'mfix_run_solver_async', 'lbm_run_async', 'opt_study_create', 'opt_apply_params']);`

这 10 个工具执行前要用户点确认——**审批粒度是"会改文件系统或起长进程"的动作**，只读工具（`read_file`/`foam_inspect_case`）不拦。

另一条值得注意的接口设计：**每个 CFD 域都配一个 `*_verify`**（`foam_geom_verify`/`foam_mesh_verify`/`foam_solve_verify`/`foam_post_verify`/`paper_param_verify`）。验证不是内部函数，而是**模型必须显式调用的工具**——这是它门禁能被审计的根本原因（下一节）。

### 5 知识来源

**没有向量索引**（`grep -ci faiss server.js` → `0`），知识来自四处：

1. **教程实时检索**：不用预建索引，直接遍历本机 OF 安装的 `tutorials/`，按关键词打分。`references/repos/nullflux/server.js:1081` 原文：`async function foamFindTutorial(query, topK = 12) {`
   打分规则（`:1090-1098`）：每个 token 命中 +10、目录段完全相等再 +5，`topK=12`，`maxDepth: 8`，且只有含 `system/controlDict` 的目录才算 case。**版本无关**，因为索引就是你的安装目录。
2. **错误模式库**：15 条正则 → 类别/成因/下一步，`references/repos/nullflux/server.js:469` 原文：`const ERROR_PATTERNS = [`
   还有一条"学习"通道：`learn_error_pattern` 把新错误登记进 `skills.js` 的 `learnedErrorPatterns()`（``references/repos/nullflux/server.js:537``）
3. **技能卡（skills）**：`skills/<domain>/<slug>.skill.json`，由 `skill_save` 在"已被 verifier 盖章"后写入（``references/repos/nullflux/server.js:3719``），实现跨任务经验复用
4. **项目记忆**：README 宣称按工作目录维护长期记忆库（`README.md` 第 3 节），**实现未检出**（在 bundle 内）

- `references/repos/nullflux/server.js:537` 原文：`  const allPatterns = ERROR_PATTERNS.concat(SkillLib.learnedErrorPatterns());`

### 6 错误处理与自修正

有，四层，全部是显式阈值：

1. **阶段级返工**：`foam_mesh_verify` 失败后最多 3 次，再失败启动"自动降档" `coarsen → minimal → box_stl`
   - `references/repos/nullflux/server.js:4637` 原文：`最多 3 次失败后启动**自动降档**`
2. **阶段级阻断**：`passed=true` 才能 `run_stage_done({passed:true})`；`passed=false` 必须回去修
   - `references/repos/nullflux/server.js:4643` 原文：`passed=true 才能 run_stage_done({passed:true, memo:"为什么这么做+下一步"})；passed=false 进入返工，最多 3 次后整体记 run_stage_done({passed:false, memo:...}) 并向用户报告。`
3. **工具级熔断**：单工具连续失败 5 次 → `[WATCHDOG_HALT]`（``references/repos/nullflux/server.js:3412``）
4. **错误分类**：任何非零退出/`FOAM FATAL`/异常，下一步"必须先调 `diagnose_error`"（``references/repos/nullflux/server.js:371`` 的描述原文），由 15 条正则给出成因

注意第 4 条是**写在工具描述里的软约束**（"必须先调"），不是执行器强制的——模型可以不调，代码不拦。

### 7 它怎么知道跑成功了（门禁问题）

**两套判据，网格是硬的（确定性阈值），求解是软的（VLM 判官）。这是五个项目里门禁最接近我方 G1–G4 的一个。**

**（1）网格：硬判据，且解析 `Mesh OK.`**

`foam_mesh_verify` 先跑 `checkMesh -allTopology -allGeometry`：

- `references/repos/nullflux/server.js:3029` 原文：`  const checkOut = await runOpenFoam({ casePath: abs, command: 'checkMesh -allTopology -allGeometry' }, ws);`

解析器直接找 `Mesh OK.` 与 `Failed N mesh checks`：

- `references/repos/nullflux/server.js:2927` 原文：`  const m1 = /Mesh OK\./.exec(txt); if (m1) out.meshOk = true;`

判定是"标志位 + 阈值 + 零容忍"的合取：

- `references/repos/nullflux/server.js:2958` 原文：`  const pass = metrics.meshOk === true && metrics.nNegativeVolumeCells === 0 && metrics.nOpenCells === 0 && issues.length === 0;`

阈值逐条（``references/repos/nullflux/server.js:2952`-2956`）：负体积 > 0、open cell > 0、`maxNonOrtho > 70`、`maxSkew > 4`、`maxAspectRatio > 1000`，以及 snappy 边界层覆盖率 `< 80%`（``references/repos/nullflux/server.js:3078`` 的 `coverage_pct < 80`）。每条阈值都自带修复建议（同一行里 `suggestions.push(...)`），所以失败能直接变成下一步动作。

**（2）求解：软判据，VLM 读残差 + 渲染图**

- `references/repos/nullflux/server.js:3890` 原文：`    case 'foam_solve_verify': {`
- `references/repos/nullflux/server.js:3892` 原文：`      try { resTxt = foamResidualSeries(args.run_id, 30, null); } catch (e) { resTxt = '[residual: ' + e.message + ']'; }`

即：取最近 30 个残差点 + 终态渲染图，连同"判断是否收敛/发散/物理合理"的 prompt 一起丢给 VLM，要求只回 JSON `{passed, score, reasons, suggestions}`。**这个判官是失败闭合的**：

- `references/repos/nullflux/server.js:3419` 原文：`  if (!imagePaths || !imagePaths.length) return { passed: false, score: 0, reasons: ['无渲染图可供验证'], suggestions: ['先渲染后再校验'] };`

无图 → `passed:false`；VLM 输出非 JSON → `passed:false`（`:3423`）；JSON 解析失败 → `passed:false`（`:3425`）。**它不会因为"验证器自己坏了"而放行**——这一点比 foam-agent 的"没报错就算成功"硬得多。

**（3）没有的东西**：不检查 `endTime` 目录是否存在。`endTime` 只在两处出现，都是进度/ETA 用：

- `references/repos/nullflux/server.js:1373` 原文：`    const m = txt.match(`

（用于算 `percent`/`etaSec`，见 `:1407`）。所以"跑到一半退出但没报错"这一类，只能靠 VLM 看残差曲线发现——**软在哪一步：解算终止性**。

**（4）与 G1–G4 对照**：

| 我方门禁 | nullflux | 强弱 |
|---|---|---|
| G1 结构 | `foam_inspect_case` 提供事实，无硬断言 | 大致相当 |
| G2 `Mesh OK.` | **硬判据 + 5 条阈值 + 覆盖率** | **比我们硬** |
| G3 无 `FOAM FATAL` | 有 `diagnose_error` 分类，但门禁不是它 | 相当 |
| G4 产物可读 | 不查终态目录；靠 VLM 看残差 | 比我们软 |

### 8 部署依赖

- **运行时**：Node.js ≥ 18（README:9 badge `node-%3E%3D18`，README:140 表格 `18.x / 20.x LTS`）
  — 原稿此处曾声称「启动脚本设 `--max-old-space-size=4096`（指向仓内 start.sh 第 12 行）」，
  经核**该文件在仓内不存在、该参数 grep 不到**，已删除（详见文末校验记录）

- **OpenFOAM 版本**：压缩包内 README 第 26 行原文 `- OpenFOAM v2206+  （Beta CFD 模式；可选）`；宣传页口径 ``references/repos/nullflux/docs/index.html:634`` 原文：`开源 CFD 软件需提前安装（OpenFOAM 推荐 v2306 以上，其他按需）。`
- **Python**：3.9+ 可选（只在 `doc_reader.py` / notebook 内核用到，压缩包内 README 第 24 行）
- **ParaView**：5.x 可选（`pvpython` 离屏渲染）
- **第三方包**：不需要 `npm install`（压缩包内 README 第 8 行原文 `# 仅需 Node.js >= 18 (sealed 版不需要 npm install，所有依赖已内联)`）
- **API key**：必需（设置页填，支持 DeepSeek/硅基流动/火山/阿里百炼/本地 vLLM/Ollama）
- **Docker / GPU**：都不需要
- **可修改性**：**不可改**。bundle 混淆 + README 明写"源码已混淆封装，外部不可读取"（压缩包内 README 第 3 行）——适配只能通过 prompt、环境变量、`etc/bashrc` 这类外部手段

### 9 理论上优点 / 缺点

优点：

- 机制：把验证做成**模型必须显式调用的工具**（`foam_mesh_verify` 等 5 个），而不是隐藏在流水线里的断言 → 收益：每次通过都有独立的工具调用记录，门禁可审计、可回放；模型也无法"绕过"它不知道存在的检查
- 机制：`checkMesh` 输出解析成结构化指标后再与硬阈值合取（``references/repos/nullflux/server.js:2958``），且每个不达标项自带 `suggestions` → 收益：失败直接转成下一步动作，不需要再问一次模型"哪里不对"
- 机制：验证器失败闭合（无图/非 JSON/解析失败一律 `passed:false`，``references/repos/nullflux/server.js:3419`-3425`）→ 收益：验证链自身故障会让任务停下，而不是静默放行
- 机制：教程检索直接遍历本机 `tutorials/`（``references/repos/nullflux/server.js:1081``），不预建索引 → 收益：换 OpenFOAM 版本不需要重建任何库，索引即安装目录；代价是每次检索都要 walk 一遍文件树（`maxDepth: 8`）

缺点：

- 机制：求解收敛由 VLM 判（残差 30 点 + 渲染图），判据是自然语言 prompt → 代价：同一份残差在不同温度/不同模型下可能给出不同 `passed`，跨次不可复现；且要额外一次多模态调用（token 成本）
- 机制：不检查 `endTime` 目录，`endTime` 只用于算 ETA（``references/repos/nullflux/server.js:1373``）→ 代价："提前结束且无报错"必须靠 VLM 从残差曲线看出来，没有确定性兜底
- 机制：发行体是混淆 bundle，仓里的 `server.js` 又缺 `skills.js`（``references/repos/nullflux/server.js:12``）→ 代价：无法静态审阅真实工具实现、无法打补丁、无法定位"某个工具为什么这样返回"；出了问题只能看日志
- 机制：工具集 91 个、按域白名单 + 10 个审批项（``references/repos/nullflux/server.js:407``）→ 代价：单轮上下文里工具 schema 的固定开销大，模型选错工具的搜索空间也大；审批项是"起进程/改文件"的黑白名单，粒度不随风险大小细分

### 10 对本项目的可迁移点

- **可迁移（最重要）**：把 G1–G4 做成**模型可显式调用的 verify 工具**，而不是 agent 循环里的隐藏断言。理由：我们现在的"能跑"是 agent 自述 + 事后 `verify_case.sh`，两者之间有一段没人负责的地带；改成"模型必须调 `verify_case` 并拿到 `passed=true` 才能宣布完成"，就把 R4 的"自述不算证据"变成了协议约束。
- **可迁移**：`checkMesh` 解析成结构化指标 + 硬阈值合取（``references/repos/nullflux/server.js:2949`-2958`）。我们的 G2 只要求 `Mesh OK.`，而 `Mesh OK.` 允许 `maxSkew` 很大；把 `maxNonOrtho/maxSkew/aspectRatio/负体积/openCell` 四条阈值加上，才拦得住"能跑但算不准"。
- **可迁移**：验证器失败闭合（`:3419`）。我们的判定脚本在"拿不到日志/解析失败"时的默认行为要显式写成 `fail`，不能是 `skip` 或 `pass`。
- **不可迁移**：VLM 判收敛替代确定性判据。它需要多模态模型 + 渲染链路，而且引入不可复现性；我们 R12 要求结论能从 `bench/results.csv` 重算，VLM 的 `score` 不满足这个条件。可替代方案是"残差单调性 + 终态目录存在 + 无 FATAL"三条确定性断言。
- **门禁对比结论**：**网格层比我们硬**（我们是 `Mesh OK.` 单标志，它是标志 + 5 阈值 + 层覆盖率），**解算终止性比我们软**（不查 `endTime`）。它是五个项目里唯一值得在门禁设计上正面借鉴的对象。

---

## 5. cfd-agent（woog97/cfd-agent，tier B）

### 0 一句话定位与规模

一句话：ChatCFD 的工程化重写版——把"论文/一句话 + 网格文件 → OpenFOAM case"做成**显式状态机**（11 个步骤函数 + 路由表），配一个 460 例的结构化参考库和一个四级升级的纠错环。仓库里没有 ChatCFD 这个名字，但 README 首行即 ChatCFD（对应论文 2506.02019）。

实测规模（`references/repos/cfd-agent`）：

- `find . -type f -name '*.py' | wc -l` → `46`
- `find . -name '*.py' -not -path './.git/*' -exec wc -l {} + | tail -1` → `13584 total`
- 其中测试占大头：`src/tests/test_steps.py` 1400 行、`test_e2e_workflow.py` 566 行
- 生产代码最大：`src/agents/meshing/steps.py` 699 行、`src/run_manager.py` 479 行、`src/agents/meshing/agent.py` 422 行
- 入口：``references/repos/cfd-agent/src/main.py:76``（`def run_case(`），CLI 在 ``references/repos/cfd-agent/src/main.py:172`-219`

### 1 输入形态

命令行四件套（``references/repos/cfd-agent/src/main.py:172`-219`）：

```
--description "一句话需求"   或   --case_file paper.pdf|txt
--solver      simpleFoam 等（required）
--grid        mesh.msh / .foam（required）
--turbulence  kOmegaSST 等（可选）
--name / --output / --max-attempts（默认 30）
```

即：**必须自带网格**，程序不做几何建模（几何建模在另一条 `agents/meshing` 支线里）。入口也是函数级 API：

- `references/repos/cfd-agent/src/main.py:76` 原文：`def run_case(`

### 2 分层与模块边界

```
src/main.py             装配：config → llm → database → Dependencies → run_workflow
src/workflow.py         显式状态机：11 个 StepFunction + 12 个 router + WorkflowRunner
src/state.py            CaseState（可变 dataclass）+ CaseBuilder，含 error_history/attempt_count
src/steps/              步骤实现：generation(文件清单/生成/落盘) / simulation(跑) / correction(分析/修/反思)
                        / mesh(转网格/提边界) / tools(子进程封装) / prompts(模板)
src/database.py         参考库：加载 14 MB JSON、建 solver 索引、四级回退检索
src/llm.py              双模型客户端（instruct / reasoning）+ token 记账
src/agents/             meshing / solving 两个"子 agent" + orchestrator Pipeline（CAD→mesh→solve）
database_OFv24/         5 个 JSON（processed_merged_OF_cases.json 14.5 MB）
inputs/                 case 输入样例；run_chatcfd/ 启动脚本；test_env/
```

- **碰文件系统**：`src/steps/generation.py`（写字典）、`src/steps/mesh.py`（`gmshToFoam`/`fluent3DMeshToFoam` 封装）
- **碰 LLM**：`src/llm.py`（唯一出口，所有 prompt 都从这里过）
- **跑仿真**：``references/repos/cfd-agent/src/steps/tools.py:98``（`def run_solver_local(`）+ ``references/repos/cfd-agent/src/steps/tools.py:141``（`def run_solver_docker(`）

这一层划分的落点：主链的仿真执行集中在 `src/steps/tools.py`（`grep -c "subprocess" src/steps/tools.py` → `9`）；另一处执行点是 `src/agents/meshing/steps.py`（`grep -rln "subprocess" src/` 命中它），即网格生成支线自己起进程，两条链路不复用执行器。

### 3 agent 拓扑

**两层**：

1. **主链是单 agent 状态机**：``references/repos/cfd-agent/src/workflow.py:43`-55` 的 `STEPS` 表把 11 个步骤注册成 `NextStep → StepFunction`，路由表 `ROUTERS`（`:158-170`）一对一绑定。步骤之间不互相调用，只返回 `StateUpdate` 字典。
2. **可选 Pipeline**：``references/repos/cfd-agent/src/agents/orchestrator.py:69`` 的 `class Pipeline:` 把 `MeshingAgent → SolvingAgent` 串成阶段流水线（`StageStatus` 五态，`:34-40`）。

模型角色不是"agent"，而是**两个不同温度/不同用途的模型端点**：

- `instruct`（`ask_instruct`，``references/repos/cfd-agent/src/llm.py:156``）：定位出错文件、判断是否需要新文件
- `reasoning`（`ask_reasoning`，``references/repos/cfd-agent/src/llm.py:203``）：生成字典内容、反思失败原因

- `references/repos/cfd-agent/src/config.py:56` 原文：`    instruct_model: str`
- `references/repos/cfd-agent/src/config.py:57` 原文：`    reasoning_model: str`

传输格式 = `StateUpdate`（普通 dict）+ `CaseState` dataclass。比 foam-agent 的 `GraphState` 轻，但没有版本化/不可变保护——`CaseState` 是可变 dataclass，步骤函数有原地改字段的自由。

### 4 工具接口

**没有工具接口**。`grep -n "tools\|tool_choice\|function_call" src/llm.py` 只命中 `functools` 相关，客户端只发 messages、只收 content。

模型的"能力"完全由步骤函数在 prompt 里描述，输出被解析成文本再落盘（`src/steps/common.py` 的 `clean_llm_file_response`）。因此它无法让模型"先看一眼 checkMesh 再说"——检查时机由硬编码的状态机决定。

### 5 知识来源

**结构化 JSON 参考库 + 四级回退检索**，不是向量检索。

- 库文件：`database_OFv24/processed_merged_OF_cases.json`（`14469187` 字节）；实测条目数 `python3 -c "import json;print(len(json.load(open(...))))"` → `460`
- 每条记录字段：`solver`、`turbulence_type`、`turbulence_model`、`other_physical_model`、`configuration_files`（全文字典）、`required_field`、`boundary_type` 等（``references/repos/cfd-agent/src/database.py:102`-112`）
- 检索逻辑（``references/repos/cfd-agent/src/database.py:130`-221`）：四级回退 —— ① solver + 湍流模型 + 其他物理模型集合相等 → ② solver + 湍流模型 → ③ 仅 solver → ④ 同 domain（压缩/不可压等）
- 每级都靠 **solver 名在路径里做子串匹配**（`:169` 的 `if solver not in path: continue`），不是字段比较——路径改名即失效
- 条数与长度双限：`max_results: int = 3`、`max_content_length: int = 10000`（``references/repos/cfd-agent/src/database.py:136``）

**关键机制缺陷（可复现性问题）**：超过 3 条时用随机抽样截断。

- `references/repos/cfd-agent/src/database.py:217` 原文：`            keys = random.sample(list(results.keys()), max_results)`

意味着同一个 `(target_file, solver, turbulence)` 查询，两次运行可能给出不同参考字典——**case 生成不可复现**。

另：`faiss-cpu==1.7.4` 与 `sentence-transformers==4.0.1` 写在 `requirements.txt` 里，`sentence_transformer_path` 默认 `all-mpnet-base-v2`（``references/repos/cfd-agent/src/config.py:208``）、`pdf_chunk_distance` 默认 `1.5`（``references/repos/cfd-agent/src/config.py:207``），但 `grep -rn "faiss" src/` 命中 `0` 次，这两个配置项在代码里**未检出使用点**——即本版代码路径上没有向量检索，PDF 处理走的是纯文本抽取。

### 6 错误处理与自修正

有，且是**按"同一错误的连续次数"分档升级**的，这是它最有设计感的一段：

- `references/repos/cfd-agent/src/workflow.py:116` 原文：`    consecutive = state.consecutive_same_errors()`
- `references/repos/cfd-agent/src/workflow.py:118` 原文：`    if consecutive >= 4:`
- `:121-123`：`consecutive >= 2` → `REFLECT`（让 reasoning 模型解释为什么前几次修不好）
- `:110-113`：缺文件类错误 → `ADD_FILE`（新建文件而不是改现有文件）

总预算：

- `references/repos/cfd-agent/src/state.py:124` 原文：`    max_attempts: int = 30`

`consecutive_same_errors()` 只比较错误文本前 100 字符（``references/repos/cfd-agent/src/state.py:188`-201`）——比 foam-agent 的"全字段指纹"粗，但足以把"同一 FATAL"识别出来。

### 7 它怎么知道跑成功了（门禁问题）

**判据：`returncode == 0` 且 stdout+stderr 里没有 `FOAM FATAL`。**

- `references/repos/cfd-agent/src/steps/simulation.py:54` 原文：`    has_fatal_error = "FOAM FATAL" in combined_output`
- `references/repos/cfd-agent/src/steps/simulation.py:56` 原文：`    if returncode == 0 and not has_fatal_error:`

**但这个判据在自己实现的执行器里被短路了。** 本地执行把子进程输出整体重定向到 `case_run.log`：

- `references/repos/cfd-agent/src/steps/tools.py:124` 原文：`        command = f"cd {case_path} && setFields && {solver} > {log_file} 2>&1"`

`solver` 的 stdout/stderr 全部进了日志文件，`subprocess.run(capture_output=True)` 拿到的 `stdout`/`stderr` 只剩 bash 自己那点输出（正常为空）。于是：

- `combined_output` 实际恒为空 ⇒ `has_fatal_error` 恒为 `False`
- 成功判据退化为 **只等于退出码 0**

而"退出码 0"在 OpenFOAM 里并不等价于"跑完"：提前 `stopAt writeNow`、`residualControl` 提前收敛、`endTime` 被 LLM 改成很小（测试夹具里就有把 `endTime` 从 3000 降到 500、再到 100 的反射记录）都会返回 0。

**其余门禁全部缺失**：

- 无 `endTime` 目录检查（`grep -rn "endTime" src/steps/` 只有 controlDict 文本处理，无目录比对）
- 主链无 `checkMesh`：checkMesh 只存在于另一条 `MeshingAgent` 支线，且判定同样只看 FATAL 关键字，不看 `Mesh OK.`
  - `references/repos/cfd-agent/src/agents/meshing/steps.py:471` 原文：`            ["checkMesh", "-case", case_path],`
- 无物理量范围检查；`_parse_check_mesh_output` 只把指标存进 state，不做阈值合取

**结论**：cfd-agent 有一个**名义上的双信号判据**（退出码 + FATAL 关键字），但由于输出被重定向，FATAL 这一路在本地模式失效；Docker 模式是否同样失效取决于 `run_solver_docker` 的 stdout 处理（``references/repos/cfd-agent/src/steps/tools.py:141`` 起，未逐一核对）。因此实际门禁强度 ≈ **只有退出码**，比我们 G3（读日志断言无 `FOAM FATAL`）软，比 foam-agent（只看 `ERROR:` 正则 + 退出码）相当。

### 8 部署依赖

- **OpenFOAM 版本**：v2406，且与知识库绑死。`references/repos/cfd-agent/ReadMe.md:78` 原文：`| CFD Simulation Software | **OpenFOAM v2406** | ⚠️ Recommended version is v2406. Using other versions will lead to a mismatch with pre-built knowledge base files`
- **版本不一致的另一处证据**：docker 默认镜像写的是 OF11，与 README 的 v2406 不同 —— `references/repos/cfd-agent/src/config.py:265` 原文：`        image=config_data.get("docker_image", "openfoam/openfoam11-paraview510:latest"),`（同文件 `:187` 的 dataclass 默认值也是同一镜像）
- **Python**：3.11.4（README 表格）；明确要求**避开 3.12**（PyFoam 冲突）
- **关键三方包（`requirements.txt` 实测）**：`openai==1.39.0`、`streamlit==1.41.1`、`pyfoam==2023.7`、`pypdf2==3.0.1`、`langchain==0.1.19`、`pdfplumber==0.11.5`、`faiss-cpu==1.7.4`、`sentence-transformers==4.0.1`、`tiktoken==0.7.0`
- **LLM 端点**：OpenAI 兼容，`base_url` 默认 `https://openrouter.ai/api/v1`（``references/repos/cfd-agent/src/config.py:65``），模型名从 `INSTRUCT_MODEL_NAME` / `REASONING_MODEL_NAME` 环境变量取，默认为空
- **Docker**：可选（`docker_enabled`，默认 False）
- **GPU**：可选（README 表 "CUDA-enabled GPU | Optional"）

### 9 理论上优点 / 缺点

优点：

- 机制：把控制流写成数据（`STEPS` + `ROUTERS` 两张表，``references/repos/cfd-agent/src/workflow.py:43`-55`/`:158-170`），步骤函数只返回 `StateUpdate` 不互调 → 收益：新增/重排步骤不改调度代码，控制流可枚举、可画图
- 机制：纠错按"同一错误连续次数"分档（2 次反思、4 次整文件重写、缺文件则新建，``references/repos/cfd-agent/src/workflow.py:116`-126`）→ 收益：不同的失败形态走不同成本的修复路径，避免"每次都整文件重写"
- 机制：参考库按 solver/湍流/物理模型三级精确匹配 + domain 兜底（``references/repos/cfd-agent/src/database.py:130`-221`）→ 收益：检索结果与目标配置同类，不需要向量近似
- 机制：双模型分工（instruct 定位、reasoning 生成，``references/repos/cfd-agent/src/config.py:56`-57` + ``references/repos/cfd-agent/src/llm.py:156`/203`）→ 收益：定位这种短输出任务不必付推理模型的 token

缺点：

- 机制：结果截断用 `random.sample`（``references/repos/cfd-agent/src/database.py:217``）→ 代价：同一输入两次运行可能拿到不同参考字典，case 生成不可复现，失败也无法复现
- 机制：本地执行把 solver 输出重定向进日志（``references/repos/cfd-agent/src/steps/tools.py:124``），而成功判据读的是 `stdout/stderr`（``references/repos/cfd-agent/src/steps/simulation.py:54``）→ 代价：FATAL 检查空转，门禁退化为退出码；"发散但正常退出"被判成功
- 机制：参考库是 460 例的 14 MB 全文字典快照，键是 solver 名在路径里的子串（``references/repos/cfd-agent/src/database.py:169``）→ 代价：换 OF 版本后字典语法与库内快照不一致（v2406→v13 的 `solver` 条目、`foamRun` 调用方式都变了），检索越"成功"越容易把旧语法带进来
- 机制：`requirements.txt` 声明 faiss/sentence-transformers 但代码里没有使用点（`grep -rn faiss src/` → 0）→ 代价：安装体积与心智模型都被这两个不生效的依赖污染，README 的 "FAISS for vector similarity search" 与实际路径不符

### 10 对本项目的可迁移点

- **可迁移**：错误次数分档升级（``references/repos/cfd-agent/src/workflow.py:116`-126`）。我们目前的修复策略是"两轮修不好就停"（AGENTS.md R8.4）；可以改成 2 次改字段 → 3 次换参考 case → 4 次判定不可修，把"停"变成最后一档而不是唯一一档。
- **可迁移**：步骤函数只返回 `StateUpdate`、不互调（`src/workflow.py` 的 `StepFunction` 类型别名）。这与我们 `verify_case.sh` 的分步结构天然对齐，且能让每一步的输入输出直接落盘成 CSV 列。
- **不可迁移**：按 solver 名做路径子串匹配的参考库（``references/repos/cfd-agent/src/database.py:169``）。它把"版本"隐式编码进了路径字符串（`database_OFv24/`），一旦换版本，检索仍然成功但内容过期——正是 AGENTS.md R1/R9 警告的那种"证据悄悄指向非权威树"。
- **门禁对比结论**：它的门禁**比我们软**，而且软在一个可诊断的 bug 上（FATAL 检查读错了流）。唯一值得借鉴的是"缺文件 → 新建文件"这条分支：我们的 G 循环目前只会改现有字典，遇到"整个 `constant/` 目录缺文件"时会一直在错误的文件上打转。

---

## 12. ai-cfd-scientist（csml-rpi/AI-CFD-Scientist，tier B）

> **编排方在合并后追加的第 12 个项目。** 理由：它对应的论文 2605.06607（AI CFD Scientist）
> 在 `01-landscape.md` 的 25 篇表里，但初版参考库未下载它；而它是这批项目里**唯一**给出
> 与 G2 不同的网格判据机制、且明确论证「为什么不该只看退出码」的。实测体积 8 MB，远在 R10 线内。

### 0 一句话定位与规模

一句话：**套在 Foam-Agent 外面的科研流水线**——从文献检索 → 假设 → 实验需求 → 生成 case（借 FoamAgent）
→ 视觉判读 → 分析 → 出论文，共 7 个 stage，用 skill 文本 + scripts 编排。

实测规模（`references/repos/ai-cfd-scientist`）：

- `find . -name "*.py" -not -path "./.git/*" | wc -l` → `168`
- `find . -name "*.py" -exec wc -l {} +` → `90908 total`
- `skills/` 5 个：`cfd-code-mod`、`cfd-foamagent-runtime`、`cfd-mesh-independence`、`cfd-orchestrator`、`cfd-research`；
  `cfd-orchestrator/SKILL.md` 226 行、`cfd-foamagent-runtime/SKILL.md` 97 行
- 入口：`AGENTS.md`（Stage 0–7 的编排说明）+ `scripts/` 下每 stage 一个脚本

### 1 输入形态

用户给一个**研究主题**（不是 case 需求），加可选控制项 `max_papers` / `n_experiments` / `mesh_source`
（AGENTS.md「Stage 0」段）。Stage 0 先按意图路由三选一：标准 CFD 研究 / 需要改 OpenFOAM 源码 /
需要网格无关性。含糊时「问一个澄清问题」。

这一层的差别值得注意：**它把「一句话 → case」包在「一个课题 → 论文」里**，所以它不需要处理
「用户没说几何尺寸」这类问题——它自己生成假设与需求。

### 2 分层与模块边界

```
AGENTS.md / CLAUDE.md      编排说明（agent 读，不是程序读）
scripts/<stage>.py         7 个 stage 的可执行入口（lit / hypothesis / requirements /
                           foam_run / viz+interpret / analyze / paper_utils）
src/cfd_langgraph/         真正的库：agents / foam / foam_native / llm / prompts / manager
src/cfd_langgraph/foam_native/   vendored 的 Foam-Agent 原生实现（loop.py / review.py / rag.py /
                                 faiss_index.py / writer.py / parser.py / allrun.py）
skills/                    5 个 SKILL.md（agent 遵循的流程文本）
prompts/prompts.yaml       各 agent 的提示词
```

- **碰文件系统**：`references/repos/ai-cfd-scientist/scripts/foam_run.py`（写 case）、`references/repos/ai-cfd-scientist/src/cfd_langgraph/foam_native/writer.py`
- **碰 LLM**：`src/cfd_langgraph/llm/`，以及全部 `agents/`
- **跑仿真**：`references/repos/ai-cfd-scientist/scripts/foam_run.py:1720`（调 `check_logs_for_errors`）与 Foam-Agent 的 `run_local`

**关键边界事实（决定它能不能独立跑）**：`references/repos/ai-cfd-scientist/scripts/foam_run.py:22-23` 的 `bootstrap_paths()`
把 `root/"Foam-Agent"/"src"` 插进 `sys.path`，`references/repos/ai-cfd-scientist/scripts/foam_run.py:1409-1416` 直接从 `services.*`
导入 6 个模块。而仓内**没有** `services/` 目录（`ls services` → 不存在）。

```
references/repos/ai-cfd-scientist/scripts/foam_run.py:22    foam_src = root / "Foam-Agent" / "src"
references/repos/ai-cfd-scientist/scripts/foam_run.py:1409  from services.plan import generate_simulation_plan
```

⇒ **它必须把 Foam-Agent 克隆到同级 `Foam-Agent/` 才能启动**，否则第一步就 `ModuleNotFoundError`。
这是「依赖另一个仓库」而不是「依赖一个包」，也意味着它**继承 Foam-Agent 的 v10 约束**。

### 3 agent 拓扑

**两层异构**：

1. **顶层是 stage 流水线**（不是自由 agent）：AGENTS.md 固定 Stage 0→7，每 stage 一个脚本，
   顺序与产物文件（`lit.json` → `hypotheses.json` → `requirements.json` → `run_result.json` →
   `decision.json` → `analysis.json` → `paper/`）都在文档里写死。
2. **底层是 Foam-Agent 的多 agent 环路**（vendored 在 `foam_native/`）：plan → meshing → write →
   Allrun → run → review → rewrite，最多 10 轮（`references/repos/ai-cfd-scientist/scripts/foam_run.py:1261` `max_loops: int = 10`）。

另外有专门的 agent 角色：`ResultsInterpreterAgent`（视觉判读）、`HypothesisAgent`、`WriterAgent`、
`PaperReviewerAgent`，提示词都在 `prompts/prompts.yaml`。传输格式是 JSON 文件落盘（stage 之间不共享内存），
这一点比同族项目干净：**每次交接都能在磁盘上被审计**。

### 4 工具接口

**没有 function-calling 工具层**。agent 的「工具」就是 `scripts/*.py`，由编排者（人或上层 agent）
按 AGENTS.md 的次序调用。skill 文本（`skills/*/SKILL.md`）规定「什么时候跑哪个脚本」。

代价：它的可组合性靠**文档约定**而非代码约束——没有一个 `run(stage)` 的注册表，stage 之间靠文件名
约定串起来。收益：换编排器（Claude Code / Codex / OpenCode）不用改代码，AGENTS.md 首行就写了
「Orchestrator-agnostic pipeline」。

### 5 知识来源

三种并存：

1. **文献检索**：`scripts/lit.py` 走 Semantic Scholar API（AGENTS.md Stage 1：「S2 first」，`S2_API_KEY`）
2. **Foam-Agent 的 FAISS/RAG**：`src/cfd_langgraph/foam_native/faiss_index.py` + `rag.py`（vendored），
   教程语料由 Foam-Agent 的 `database/` 提供 —— 即**继承 v10 语料**
3. **提示词库**：`prompts/prompts.yaml`

值得单列：它的知识来源里**没有一项是「对本机 OpenFOAM 安装做 grep」**。全部知识来自离线索引与
模型权重。这与我们的 R1（源码是唯一权威、必须 grep）是两种哲学。

### 6 错误处理与自修正

两层，且层间不共享状态：

- **求解层**：Foam-Agent 的 reviewer 环路，`max_loops=10`（`references/repos/ai-cfd-scientist/scripts/foam_run.py:1261`），把 `collect_error_logs`
  的结果喂回 LLM 让它改文件。
- **判读层（这是它的特色）**：`references/repos/ai-cfd-scientist/scripts/interpret.py:58-64` 用 LLM 看 PyVista 出的图，产出三态
  `RERUN` / `REVISE` / `PROCEED`。若 `RERUN`，AGENTS.md Stage 5 规定：选最相似的成功 case、以失败 case
  当输入结构、据 feedback 改需求、重跑 —— 即**整个 case 重来**，而不是改字典。
- 还有一层 CFL 感知的兜底：反复超时/进展过慢时按小步增大 `deltaT`、`adjustTimeStep yes`、
  `maxCo ≤ 0.7`（AGENTS.md Stage 5 Policy）。

### 7 它怎么知道跑成功了（门禁问题，**最核心**）

它有两道，强度截然不同：

**第一道（求解层，继承自 Foam-Agent）**：`run_result.json` 的 `status` 由「有没有 error_logs」决定。

```
references/repos/ai-cfd-scientist/scripts/foam_run.py:1941
    "status": "success" if not error_logs else "failed",
```

而 `error_logs` 的来源 `collect_error_logs`（`loop.py:95`）在**日志存在时永远非空**（它会把每个
`log.*` 的末 200 行拼进去）。所以这一道的实际语义取决于 `check_logs_for_errors`（来自未 vendored 的
`services.run_hpc`）——**本机无法静态确定**，记为「未确定」。

**第二道（网格有效性，本批最有价值的一段）**：`mesh_check_errors` 不只看退出码，也不看 `Mesh OK.`，
而是**扫 checkMesh 日志里所有以 `***` 开头的行**，并排除白名单：

```
references/repos/ai-cfd-scientist/src/cfd_langgraph/foam_native/loop.py:63
_BENIGN_MESH_CHECKS = ("high aspect ratio",)
references/repos/ai-cfd-scientist/src/cfd_langgraph/foam_native/loop.py:77-80
    return [line for line in _mesh_check_lines(case_dir)
            if not any(benign in line.lower() for benign in _BENIGN_MESH_CHECKS)]
```

它的理由写在 docstring 里（`loop.py:67-75`）：

```
checkMesh EXITS 0 even when it finds negative-volume cells, so neither the
Allrun return code nor the "FOAM FATAL" scan notices a broken mesh.
```

**这条理由在我们这里不成立，已用 R1 核实**。v13 的 `checkMesh` 打印 `Mesh OK.` 与返回 0 是
**同一个条件**：

```
$FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:161
    if (nFailedChecks == 0) { Info<< "\n    Mesh OK.\n" << endl; }
$FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:180
    return nFailedChecks == 0;
```

所以 **v13 里「退出码 0 但网格坏」不可能发生**——两者同源。我们的 G2（`grep "Mesh OK."`）已经
等价于「所有 checkMesh 检查全过」，而且比只看退出码更强（崩溃但退出 0 的进程不会打印这句话）。

**第三道（物理合理性，LLM 视觉）**：`interpret.py:60-64`，判据是 `interp.get("rerun_required")` 与
`requirement_met` —— **纯 LLM 判断**，输入是 PyVista 图。论文口径是 14/16 通过。
这一道不是可机检的门禁：同一张图两次调用可能给不同标签，且没有阈值留在代码里。

**结论**：它的门禁**结构比我们完整**（求解 + 网格 + 物理三层），但**只有中间一层是确定性的**；
第一层语义未定（依赖未 vendored 模块），第三层是模型意见。我们的 G1–G4 全确定性，但缺「物理是否
像话」这一层——那是我们明确不做的（`README.md §9`：物理正确性需用户给参照）。两者没有谁更强，
是**测的东西不同**。

### 8 部署依赖

- **OpenFOAM**：`references/repos/ai-cfd-scientist/README.md:282` 原文：
  `- **OpenFOAM 10** — for any real CFD run. Install per upstream instructions; set WM_PROJECT_DIR to your install root.`
- **另一个仓库**：必须同级克隆 `Foam-Agent`（`references/repos/ai-cfd-scientist/scripts/foam_run.py:22`），而 Foam-Agent 自身要求 v10
  ⇒ **版本依赖是嵌套的**，不是单点声明
- **Python**：≥3.10（`requirements.txt` 注释）
- **关键三方包**：`langchain>=0.3.0`、`langgraph>=0.2.0`、`pyvista>=0.44`、`semanticscholar>=0.7.0`（`pyproject.toml`）
- **外部 API**：`S2_API_KEY`（文献）、LLM key（`langchain-openai` / `-anthropic` / `-aws` 三选一）
- **Docker**：未检出强依赖；**GPU**：未检出强依赖（PyVista 可离屏 CPU 渲染）

### 9 理论上优点 / 缺点（机制）

优点：

- 机制：stage 之间只通过 JSON 文件交接（`lit.json` / `hypotheses.json` / `requirements.json` /
  `run_result.json` / `decision.json`）→ 收益：**每一次交接都能在磁盘上被独立审计与重放**，
  出问题时能定位到具体 stage，而不是翻一段长对话
- 机制：网格有效性判据从「退出码」换成「扫 `***` 行 + 白名单」→ 收益：把「网格坏但求解器还在跑、
  reviewer 一直在改物理文件」这条最费 token 的错路掐断（docstring 明写这就是动机）
- 机制：判读层用视觉，且允许 `REVISE`（改需求重跑）而不只是 `RERUN`（原样重跑）→ 收益：区分了
  「算错了」与「问错了」两种失败，不会在错误的需求上无限重试
- 机制：`skills/` + `AGENTS.md` 而非代码编排 → 收益：换编排器（Claude Code / Codex / OpenCode）
  零改动，`AGENTS.md:3` 明写 orchestrator-agnostic

缺点：

- 机制：`bootstrap_paths()` 硬依赖同级 `Foam-Agent/` 目录（`references/repos/ai-cfd-scientist/scripts/foam_run.py:22`）→ 代价：
  「一个仓库」变成「两个仓库 + 两者版本必须匹配」；任何一方升级都可能静默失配，且 PIP 式安装不可能
- 机制：把物理合理性交给 LLM 看图（`references/repos/ai-cfd-scientist/scripts/interpret.py:60`）→ 代价：判据无阈值、不可复现、
  无法回答「同一个 case 两次判读是否一致」；14/16 这个数字无法在别处重算
- 机制：语料是 vendored 的 Foam-Agent FAISS 索引（v10）→ 代价：与我们的 R1 相反，它的知识是
  **离线快照**，安装版本一变，索引就不代表本机语法，而且没有任何检查会发现这件事
- 机制：7 个 stage 靠 AGENTS.md 文档约定串联，没有代码级注册表 → 代价：漏跑一个 stage 或跑错顺序
  不会被程序拦住，只会在下游产出空文件时才暴露

### 10 对本项目的可迁移点

- **可迁移（已核实可采纳）**：stage 间 JSON 文件交接。我们的 M4b runner 天然适合这个形状：
  每任务产出 `results.csv` 一行 + 一份 `case.meta`，arm 之间不共享内存。这与 `bench/preregistration.md`
  §12 的落盘布局一致，不需要改设计。
- **可迁移（作为 G2 的补强，非替代）**：加一条「扫 `***` 行」的辅助信号。注意**不是**因为
  「退出码不可信」（v13 里两者同源，已用 R1 证伪），而是因为它**指认了坏在哪一项检查**，
  能让失败分桶更细。成本：一条 grep。
- **不可迁移**：LLM 视觉判读。它违反我们 R6（数字必须实测）与 R12（判据须可重算）——同一张图
  两次判读可能不同，这是不可复现的判据。若将来要做物理校验，必须换成**带阈值、可重算**的检查
  （例如与我们已知参照解比 L2 误差），而不是让模型看图说话。
- **不可迁移**：嵌套仓库依赖（`Foam-Agent/` 同级克隆）。我们要的是一个 ≤200 MB 的独立体，
  依赖链越短越好；这条正好是反面教材。


---

## 本批汇总矩阵

| 项目 | 拓扑 | 工具接口 | 知识来源 | 有无自修正 | 成功判据类型 | tier | 部署强依赖 |
|---|---|---|---|---|---|---|---|
| foam-agent | 单图 8 节点 + 1 条回边（LangGraph），角色=节点 | MCP 7 tool（阶段粒度）；流水线内部无 function calling | 4 个 FAISS 索引 × 2 套版本语料，一 case 一块；仓内为 LFS 指针需重建 | 有：max_loop 25 + 错误指纹去重 + 进程级 1 次重试 | 仅"无 `ERROR:` 正则命中且退出码 0"，**无独立判据** | B | OF v10 基镜；语料须用本机 OF 重建 |
| metaopenfoam | 5 角色消息总线（MetaGPT Environment） | 无（纯 prompt，由 Action 代码执行） | FAISS 4 库，一文件一块，k=2，语料=openfoam10 tutorials | 有：3 个独立计数器，max_loop 20，无指纹 | `Executability` 0/1/2/3，3 = `endTime` 目录存在 | B | OF-10 + 外部 MetaGPT 源码 + API key |
| openfoam-mcp-server | 无 agent 循环（工具层，规划外包给客户端） | MCP 12 tool（主程序实际注册 9） | 硬编码 C++ 模板 + 概念图谱，无检索 | 无（try/catch 打包返回） | `blockMesh` 与 solver 两个退出码，solver 被默认构造固定为 `simpleFoam` | B（上界存疑，见下） | OF v12 库（编译期 `FATAL_ERROR`）+ C++20 |
| nullflux | 单 agent + 阶段状态机（`run_stage_*`）+ watchdog 熔断 | function calling 91 tool（含 5 个 `*_verify`） | 本机 tutorials 实时关键词检索（topK=12）+ 15 条错误正则 + skills 卡 | 有：阶段返工 ≤3 / 工具熔断 5 次 / 6h 上限 | 网格：`Mesh OK.` + 5 条阈值（硬）；求解：VLM 判残差+渲染图（**失败闭合**） | B | Node≥18 + OF v2206+（自动探测）+ LLM key；二进制不可改 |
| cfd-agent | 单 agent 显式状态机（11 步）+ 可选 2 阶段 Pipeline | 无 | 460 例结构化 JSON，四级回退，`random.sample` 截断 | 有：按同一错误连续次数分档（2 反思 / 4 重写），max 30 | 退出码 0 + `FOAM FATAL` 关键字（本地模式因重定向而失效） | B | OF v2406 且与库绑死；Python 3.11 |

---

## 本批 tier 修正与存疑

**修正数：0。五项均维持 registry.csv 里的 tier B。** 逐项依据：

- **foam-agent 保持 B**：默认路径不校验版本（`openfoam_target: str = ""`，``references/repos/foam-agent/src/config.py:46``），所以能在 v13 上启动；但语料必须用本机 OF 重建（``references/repos/foam-agent/init_database.py:40`` 的 `--openfoam_path`），且提示词/参考 case 全是 v10 语法（`docker/Dockerfile:2`）。属于"重建一次语料 + 改生成约定"的命令级适配，不到需要改代码的程度。
- **metaopenfoam 保持 B**：语料由 `src/Tutorial_postprocess.py` 从任意安装的 tutorials 现场生成（第 1 行注释即写明 openfoam10），可换成 v13 的 tutorials；但 prompt 里的求解器名（`pimpleFoam`/`rhoPimpleFoam` 等）与 Allrun 结构需要改，属命令/提示级适配。
- **openfoam-mcp-server 保持 B，但上界存疑**：它的适配面是 ``references/repos/openfoam-mcp-server/CMakeLists.txt:12`` 的一个路径变量 + ``references/repos/openfoam-mcp-server/src/openfoam/case_manager.hpp:56`` 的一个默认值，改完需重编译。若 v13 头文件与该 C++20 代码不兼容，则实际为 C——**本阶段禁止编译，故未确定**。
- **nullflux 保持 B**：版本无关（``references/repos/nullflux/server.js:102`` 的路径正则能匹配 `openfoam13`，教程检索直接走安装目录），但发行体是混淆 bundle、仓内 `server.js` 缺 `skills.js`（``references/repos/nullflux/server.js:12``），**适配只能靠 prompt/环境，不能改源码**；B 的"命令级适配"在这里退化成"提示级适配"。
- **cfd-agent 保持 B**：知识库路径名写死 `database_OFv24/`、README 明写换版本会导致 `*.json` 不匹配（``references/repos/cfd-agent/ReadMe.md:78``）；v13 的 `controlDict` 带 `solver` 条目，会被 `extract_solver_from_controldict` 当成可执行文件名（``references/repos/cfd-agent/src/steps/simulation.py:31``），直接跑会 127 退出。需改检索键与求解器调用约定，属命令级适配。

**无法从静态代码确定、明确标"未确定"的四项**：

1. **nullflux 的 sealed bundle 内部行为**（`server.bundle.mjs` 4.26 MB 字符串混淆，`grep -ci openfoam` 仅 2 处命中）：工具实现、项目记忆的落盘格式、`foam_run_solver_async` 是否另有门禁、`skills.js` 的 `learnedErrorPatterns` 存储位置，全部**未确定**。本报告对 nullflux 的结论只覆盖 `server.js` 可读部分。
2. **openfoam-mcp-server 能否在 v13 上编译**：`/opt/openfoam13/platforms/linux64GccDPInt32Opt/lib/libOpenFOAM.so` 与 `lib/dummy/libPstream.so` 存在，路径结构对得上；但 API 兼容性**未确定**（未编译）。
3. **foam-agent 语料的实际召回质量**：raw 文件是 LFS 指针（128–133 字节），真实内容（details 指针声明 `size 64026283`）不在检出内，因此"检索命中率/召回相关性"**未确定**，本报告只分析检索的结构与参数，不评价效果。
4. **metaopenfoam 依赖的 MetaGPT 版本**：README 只要求仓库根有 `MetaGPT/` 目录，``references/repos/metaopenfoam/src/config_path.py:58`` 只做 `sys.path.append(MetaGPT_PATH)`，**无版本约束、无 commit 记录**——其 `Role`/`Environment` 语义是否与当前 MetaGPT 主线兼容，**未确定**。

另有一项"读到但未深挖"的：**cfd-agent 的 Docker 执行路径**（``references/repos/cfd-agent/src/steps/tools.py:141`` 起）是否也把 solver 输出重定向到日志、从而使 `FOAM FATAL` 检查同样失效，本次只核对了本地路径，Docker 路径**未逐一核对**，故 §7 结论限定为"本地模式"。

---

本批规模实测（命令与输出，均在 `05_FOAM_Agent/` 下执行）：

```
$ for d in harnessfoam autofoam deepflow hpc-skills; do \
    echo -n "$d py="; find references/repos/$d -name '*.py' -not -path '*/.git/*' | wc -l; \
    echo -n " lines="; find references/repos/$d -name '*.py' -not -path '*/.git/*' -print0 | xargs -0 cat | wc -l; \
    echo -n " md="; find references/repos/$d -name '*.md' -not -path '*/.git/*' | wc -l; \
    echo -n " all="; find references/repos/$d -type f -not -path '*/.git/*' | wc -l; done
harnessfoam py=79 lines=5631 md=2 all=266
autofoam py=36 lines=10801 md=1 all=54
deepflow py=7 lines=1791 md=2 all=49
hpc-skills py=13 lines=912 md=272 all=439
```

chatcfd / openfoamgpt 无本地文件：前者按 R10 记 `docs_only`（registry `size_mb=562`，GitHub 报 576098 KB），后者 registry `kind=paper`、无官方代码仓。

---

## 6. harnessfoam（本地 references/repos/harnessfoam，tier A）

### 0 一句话定位与规模

LangGraph 编排的 9 节点多 agent 框架，把一句自然语言需求编译成整套 OpenFOAM-13 字典并跑到出结果，另带一套不调 LLM 的确定性验证层与 cavity 回归基准。

规模（命令见文首）：79 个 py / 5631 行；其中 `wc -l harnessfoam/agents/*.py | tail -1` → 1537，`.../api/*.py` → 1259，`.../core/*.py` → 522；测试 34 个 py。入口三处，各自独立：``references/repos/harnessfoam/harnessfoam/cli.py:58``（`def main():`，子命令 run/serve/mcp/benchmark 见 :63-77）、``references/repos/harnessfoam/harnessfoam/api/server.py:74``（`app = FastAPI(title="HarnessFOAM API", ...)`）、``references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8``（`mcp = FastMCP("HarnessFOAM")`）。

### 1 输入形态

两个自由文本框（需求 + 后处理需求）加一个输出目录，无结构化表单、无单位/量纲校验：README:38 `* **Simulation Requirement**: A text area to input natural language physical setups`、README:39 `* **Post-Processing Requirement**: A text area to define custom data visualization instructions.`。

进入点：``references/repos/harnessfoam/harnessfoam/cli.py:63`` 的 `run` 子命令（位置参数 `prompt`，`:65 run_parser.add_argument("-o", "--output", ...)`）；Web 走 ``references/repos/harnessfoam/harnessfoam/api/server.py:219` @app.websocket("/api/stream")`。两种入口都落到 `SimulationState` 的 `prompt` / `case_dir` 两个字段（``references/repos/harnessfoam/harnessfoam/agents/graph.py:10` class SimulationState(TypedDict, total=False):`）。

速度、粘度、Re、几何尺寸全由 LLM 从文本里猜——与 R3/R8「缺几何/物性/边界就停下问」相反。它的补偿手段是把猜测结果写进可校验的字典，再用 preflight 抓结构错。

### 2 分层与模块边界

| 目录 | 行数量级 | 碰文件系统 | 碰 LLM | 跑仿真 |
|---|---|---|---|---|
| `harnessfoam/agents/` | 1537 | 是（写字典、写 Allrun、写备份） | 是（唯一） | 否（调 runner 起子进程） |
| `harnessfoam/api/` | 1259 | 是（浏览/读写/重命名文件） | 是（模型列表、助手对话） | 否（转交 graph） |
| `harnessfoam/core/` | 522 | 是（数据库、job 状态） | 否 | 是（`hpc.py` 经 asyncssh 提交集群） |
| `validation.py` / `case_manifest.py` / `physics_validation.py` / `reference_benchmarks.py` | 138+48+71+21 | 只读文件与字符串 | 否 | 否 |
| `knowledge.py` | 160 | 只读 tutorial 树 | 否 | 否（一次 `wsl bash` 探测路径） |
| `benchmark.py` / `tutorial_regression.py` | 39+41 | 是（写临时 case） | 否 | 是（`subprocess.run(["wsl",...])`） |
| `web/` | — | 否 | 否 | 否（零依赖静态页） |

关键边界：**只有 `agents/` 调 LLM；只有 `agents/runner.py`、`benchmark.py`、`tutorial_regression.py`、`core/hpc.py` 起子进程；所有判据在四个不含 LLM 的文件里**。这个切分是本批最值得抄的结构——判据成了纯函数（输入 str 或目录 → 输出 bool + errors 列表），可单测、可换入口复用。

### 3 agent 拓扑

单 LangGraph `StateGraph`，9 节点、单主干 + 3 个条件边，不存在并行分支。

编排代码：``references/repos/harnessfoam/harnessfoam/agents/graph.py:453` def create_workflow() -> StateGraph:`，`:466 workflow.set_entry_point("architect")`，`:500 return workflow.compile()`。

角色与节点：Architect `:52`（出"要写哪些文件"清单）→ Meshing `:89`（决定 blockMesh 还是 gmsh，需要时把生成的 `mesh.py` 写盘）→ Input Writer `:117`（写字典，写前备份到 `.harnessfoam/backups/attempt_N`）→ Preflight `:159`（无 LLM）→ 条件沿 `route_after_preflight :447` 去 runner 或 reviewer → Runner `:176` → 条件沿 `should_review :417` 去 reviewer / physics_autopilot / visualizer / end → Reviewer `:298` → 条件沿 `route_after_review :440` 回 meshing 或 input_writer → Visualizer `:338`。

传输格式：**共享 TypedDict 状态**（``references/repos/harnessfoam/harnessfoam/agents/graph.py:10`-34`，字段 prompt/case_dir/plan/logs/errors/status/retry_history 等），不是消息列表；`llm_kwargs` 随状态下传（README:95）。重试计数在状态里：``references/repos/harnessfoam/harnessfoam/agents/graph.py:68` state['max_errors'] = 3`，reviewer 每次 `:302 state['errors'] += 1`。

### 4 工具接口

两套 FastMCP（stdio），各自 `mcp.run(transport='stdio')`：

A) ``references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8` mcp = FastMCP("HarnessFOAM")`，8 个 tool：
`get_knowledge_status` `:11`、`run_parameter_optimization` `:18`、`run_agentic_optimization` `:26`、`run_cavity_benchmark` `:34`、`run_cavity_repair_benchmark` `:41`、`search_repository` `:48`、`read_repository_file` `:55`、`run_cfd_simulation` `:65`（一个 tool 跑完整图，`await workflow.ainvoke(...)` 见 :83）。

B) ``references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6` app = FastMCP("HarnessFOAM-MCP")`，11 个 tool（`grep -c "@app.tool()"` = 11）：
`create_case` `:11`、`plan_simulation_structure` `:24`、`generate_file_content` `:30`、`generate_mesh` `:40`、`generate_hpc_script_tool` `:53`、`run_simulation` `:59`、`check_job_status` `:83`、`get_simulation_logs` `:92`、`review_and_suggest_fix` `:98`、`apply_fix` `:105`、`generate_visualization` `:148`。

粒度差异明显：A 是"一个 tool = 一条流水线"，B 是"一个 tool = 一个内部节点"。B 那套把生成/修文件都物化成可被外部编排器单步调用的接口，等于把 agent 内部状态机暴露出去了——同一仓库两套粒度，README 只宣传 `harnessfoam mcp`（``references/repos/harnessfoam/harnessfoam/cli.py:73``），没说哪个是权威。除 MCP 外另有 REST 面：`api/routes.py` 有 30+ 路由（文件读写、优化、助手工具、benchmark 矩阵）。

### 5 知识来源

三档，全部离线，**无向量库**（`pyproject.toml` 声明 `faiss-cpu>=1.7.4`，但 `grep -rn "faiss" harnessfoam/` 无命中——死依赖）：

1) 7 条硬编码 `KnowledgeChunk`（``references/repos/harnessfoam/harnessfoam/knowledge.py:17`-25`），例：`KnowledgeChunk("boundary-consistency", "All patches in blockMeshDict must appear in every volField boundaryField. Vector U uses vector dimensions and scalar p uses pressure dimensions.", (...))`（:20）。
2) 随仓 vendored 的 OpenFOAM-13 教程（`assets/openfoam_tutorials/OpenFOAM-13/`，`find assets/openfoam_tutorials -type f | wc -l` → 156，占全仓 266 个文件的 59%），只索引 20 个文件名的白名单（``references/repos/harnessfoam/harnessfoam/knowledge.py:27`` `_TUTORIAL_FILES = {"controlDict", "blockMeshDict", "snappyHexMeshDict", ...}`）。
3) 运行期兜底探测 `$FOAM_TUTORIALS`（``references/repos/harnessfoam/harnessfoam/knowledge.py:36`-59`，含一次 `wsl bash -lc` 探测 `:46`）。

切块与检索参数（全部实测行）：块 = 一个字典文件；单文件 >80 KB 跳过（`:75 if path.stat().st_size > 80_000: continue`）；正文只取前 6000 字符（`:82 excerpt = content[:6000]`）；标签取自"相对路径 + 前 15000 字符"的分词（`:84`），分词正则 `:33 r"[a-zA-Z][a-zA-Z0-9_+.-]*"`；打分 `:103 score = tag_hits * 4 + min(text_hits, 12)`；`retrieve(query, k=4)`（`:97`）；多面检索 5 个 facet（`:118-124`），多样性重排按 Jaccard>0.72 丢弃（`:136`）；角色路由 4 路 architect/input_writer/reviewer/postprocess（`:147-152`）。

机制：纯词袋 + 白名单 → 零安装、零索引时间、结果可复现（同一 query 同一 chunk 序）；代价是只认字面重合，同义改写（"盖驱动方腔" vs "lid driven cavity"）命中为 0，且没有跨语言的桥。

### 6 错误处理与自修正

三条路径按信号类型分流，最多 3 轮（``references/repos/harnessfoam/harnessfoam/agents/graph.py:68``）：

1) **结构错**（preflight 失败）→ Reviewer。``references/repos/harnessfoam/harnessfoam/agents/graph.py:447`-448 def route_after_preflight(state) -> str: return "review" if state.get('status') == 'FAILED' else "run"`；Reviewer 产 suggestions，``references/repos/harnessfoam/harnessfoam/agents/graph.py:440`-445` 里若任何 suggestion 的 `file` 是 `mesh.py` 就回 Meshing，否则回 Input Writer（`:442 if any(s.get('file') == 'mesh.py' for s in suggestions):`）。
2) **数值发散** → Physics Autopilot（``references/repos/harnessfoam/harnessfoam/agents/graph.py:387``）。判定在 `should_review :417-431`，读 `parse_physics_diagnostics`（``references/repos/harnessfoam/harnessfoam/validation.py:94``）的 7 个布尔：FPE（`:97`）、bounding k/epsilon/omega（`:98-100`）、continuity 指数增长（`:108 if len(continuity) > 10 and max(continuity[-5:]) > 1e3`）、Courant 爆炸（`:113 if courant and max(courant) > 100.0`）、残差反向增长（`:118`）。Autopilot 改完回 preflight（``references/repos/harnessfoam/harnessfoam/agents/graph.py:497` workflow.add_edge("physics_autopilot", "preflight")`），不重跑网格。
3) **其它失败** → Reviewer。

配套动作：
- 写回前整目录备份：``references/repos/harnessfoam/harnessfoam/agents/graph.py:139` backup_dir = os.path.join(case_dir, '.harnessfoam', 'backups', f"attempt_{state.get('errors', 0)}")`，逐文件 `shutil.copy2`（`:146`）。
- 每轮落失败账本：``references/repos/harnessfoam/harnessfoam/agents/graph.py:317`-325`，字段 `attempt/prompt/error/suggestions`，追加写 `.harnessfoam/failure_ledger.jsonl`。
- 轮数到顶标 `RETRY_EXHAUSTED`（``references/repos/harnessfoam/harnessfoam/agents/graph.py:312``）。
- 可选 per-agent 记忆 `.harnessfoam/memory/<agent>.md`，默认关（README:65）。

无 LLM 自评；Reviewer 只出"改哪个文件、怎么改"，是否通过仍由确定性判据决定。

### 7 它怎么知道跑成功了

信号链两条，必须同时成立：

**(1) 退出码。** ``references/repos/harnessfoam/harnessfoam/agents/runner.py:143` process.wait(timeout=300)` → `:145 return process.returncode, stdout_str, ""` → ``references/repos/harnessfoam/harnessfoam/agents/graph.py:253` if returncode != 0:` 则 `state['status'] = 'FAILED'`。

**(2) `validate_runtime(stdout_str, expected_version="13")`。** 调用点 ``references/repos/harnessfoam/harnessfoam/agents/graph.py:271``，逐字：

`            runtime_ok, metrics, metric_errors = validate_runtime(stdout_str, expected_version="13")`

函数体 ``references/repos/harnessfoam/harnessfoam/validation.py:125` def validate_runtime(log: str, expected_version: str = "", max_courant: float = 1.0)`，五条判据逐条：

- FATAL：``references/repos/harnessfoam/harnessfoam/validation.py:128` if re.search(r"FOAM FATAL|FOAM FATAL IO ERROR|FOAM aborting", log or "", re.I):`
- 完成标记：``references/repos/harnessfoam/harnessfoam/validation.py:130` if not metrics["has_end_marker"]:`，正则在 `:91`，逐字 `"has_end_marker": bool(re.search(r"(?:\nEnd\s*$|Simulation complete!\s*$)", log or "", re.M)),`
- 时间步非零：``references/repos/harnessfoam/harnessfoam/validation.py:132` if metrics["time_steps"] == 0:`（时间步由 `:82 re.findall(r"\bTime\s*=\s*([0-9.eE+-]+)", log or "")` 数出来）
- 版本：``references/repos/harnessfoam/harnessfoam/validation.py:134``（下详）
- Courant：``references/repos/harnessfoam/harnessfoam/validation.py:136` if metrics["max_courant"] is not None and metrics["max_courant"] > max_courant:`，默认 1.0（`:125`）

任一条不过 → ``references/repos/harnessfoam/harnessfoam/agents/graph.py:288` state['status'] = 'FAILED'`，错误串进 `execution_error`（`:289`）。

**(3) 只在 returncode==0 分支里的两级附加闸**（``references/repos/harnessfoam/harnessfoam/agents/graph.py:257` else:` 之后）：

- 物理闸 `validate_physics`（``references/repos/harnessfoam/harnessfoam/physics_validation.py:43``）：NaN/Inf（`:56`）、U>1e4（`:58`）、以及 `:60 if "cavity" in (prompt or "").lower() and solver == "icoFoam" and magnitudes and max(magnitudes) < 0.5:`。**没有数值时间目录时直接放行**：`:45-46 return True, {"status": "SKIPPED", "reason": "No written numeric time directory"}, []`。
- 参考闸 `evaluate_reference_case`（``references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:5``）：`:8 if benchmark != "cavity" and "cavity" not in text and "lid driven" not in text and "lid-driven" not in text:` → 直接 SKIPPED/True；启用时 5 条硬阈值（`:11-15`）：`openfoam13_final_time` last_time>=0.5、`courant_below_0.2` <=0.2、`continuity_below_1e-6` <=1e-6、`finite_velocity` U_max 非空、`moving_lid_velocity_reached` 0.5<=U_max<=2.0；`score == 1.0` 才 PASSED（`:20`）。

#### Version 13 断言到底在哪、怎么实现的

- 声明在 ``references/repos/harnessfoam/README.md:100``，逐字：`6. **OpenFOAM 13 Runtime Contract** – Each generated case receives \`.harnessfoam/manifest.json\`; solver logs must confirm OpenFOAM Version 13 before the run is accepted.`
- 实现在 ``references/repos/harnessfoam/harnessfoam/validation.py:134``，逐字：

`    if expected_version and not re.search(r"\bVersion:\s*" + re.escape(expected_version) + r"\b", log or ""):`

  失败时追加 `:135 f"OpenFOAM runtime version {expected_version} was not confirmed in solver log"`。传 `"13"` 的四个调用点：``references/repos/harnessfoam/harnessfoam/agents/graph.py:271``、``references/repos/harnessfoam/harnessfoam/benchmark.py:38``、``references/repos/harnessfoam/harnessfoam/tutorial_regression.py:39``、``references/repos/harnessfoam/harnessfoam/optimization.py:77``。
- 被匹配的字符串来自 OpenFOAM 本身（grep `/opt/openfoam13` 实测）：`grep -rn "Version:" /opt/openfoam13/src/OpenFOAM --include=*.C --include=*.H` 仅 1 条命中，即 ``$FOAM_SRC/OpenFOAM/db/IOobject/IOobjectI.H:83``，逐字 `    "    \\\\  /    A nd           | Version:  " << FOAMversion << "\n"`；打印点是 ``$FOAM_SRC/OpenFOAM/global/argList/argList.C:655`` 逐字 `            IOobject::writeBanner(Info, true)`（紧跟 `:656 << "Build  : " << Foam::FOAMbuild << nl`）。横幅每次 `argList` 初始化都打，故任何 v13 二进制（blockMesh/checkMesh/solver）的 stdout 第一条横幅即含 `Version:  13`。版本串编译期定死：`/opt/openfoam13/etc/bashrc:36 export WM_PROJECT_VERSION=13`，`src/OpenFOAM/global/global.Cver` 里 `const char* const Foam::FOAMversion = "VERSION_STRING";` 由 Makefile 规则替换。
- `log` 的来源：``references/repos/harnessfoam/harnessfoam/agents/runner.py:110` cmd = ["wsl", "bash", "-lc", f"cd '{wsl_case_dir}' && bash ./Allrun"]`，`:126-128` 逐行收 `process.stdout`；Allrun 内容由 `generate_local_script` 生成，顺序是 blockMesh → checkMesh → solver（``references/repos/harnessfoam/harnessfoam/agents/runner.py:88`-96`）。所以是"整段合并 stdout"，不是 solver 单日志。
- **易误读的一点**：`case_manifest.py` 的 `manifest.json` 里也有 `openfoam_version`，但那是**常量**：`:8 EXPECTED_OPENFOAM_VERSION = "13"`、`:22 "openfoam_version": EXPECTED_OPENFOAM_VERSION,`，写盘时完全不看日志。同文件 `:45 def parse_openfoam_version(log: str)`（正则 `\bVersion:\s*([0-9]+(?:\.[0-9]+)?)`）除测试外全仓无调用——`grep -rn "parse_openfoam_version" --include=*.py .` 只命中 ``references/repos/harnessfoam/harnessfoam/case_manifest.py:45`` 与 ``references/repos/harnessfoam/tests/unit/test_provenance_postprocess.py:14` assert parse_openfoam_version("Version: 13") == "13"`。因此 README:100 那句话的前半（写 manifest）属实，后半（日志确认）落在 `validation.py`；**只读 manifest 会看到 "13"，与实际跑的是哪个版本无关**。

#### 它是否比我们的 G3 更硬

我们的 G3（``references/repos/harnessfoam/README.md:182``）= 步数减到 2–3 步跑完 + 退出码 0 + 日志无 `FOAM FATAL`。逐项对比：

| 判据 | 我们 G3 | harnessfoam `validate_runtime` |
|---|---|---|
| 退出码 0 | 有 | 有（``references/repos/harnessfoam/harnessfoam/agents/graph.py:253``） |
| 无 FOAM FATAL | 有 | 有（``references/repos/harnessfoam/harnessfoam/validation.py:128``） |
| 完成标记 `End` / `Simulation complete!` | 无 | 有（`:91/:130`） |
| 时间步数 > 0 | 无 | 有（`:132`） |
| `Version: 13` | 无 | 有（`:134`） |
| maxCourant <= 1.0 | 无 | 有（`:136`） |
| `Mesh OK.` 逐字 | 有（G2） | **无**（见下） |

结论分三层：

1. **条数上更硬**：多 4 条判据（完成标记、时间步、版本、Courant），其中"完成标记 + 时间步"补的正是我们 G3 的空洞——一个 solver 因字典错在第一步就 FATAL 但被 shell 吞掉退出码时，我们只靠 `grep FOAM FATAL` 兜；反过来一个"退出 0 但一步没写"的运行，我们 G3 判过，harnessfoam 判不过。
2. **语义上硬在错的地方**：`Version: 13` 是**环境指纹**，证的是"这条 shell 里跑的 OpenFOAM 二进制是 13"（甚至只是 Allrun 里第一个 utility 是 13），不证生成的字典符合 v13 语义。它抓的失效模式恰好是 R11 要禁的那件——机器上存在第二份 OF 并被 source。所以这条的收益是"版本漂移检测"，不是"case 正确性"。
   - 正则有一个洞：`\b13\b` 对 `Version: 13.1` 也成立（`3` 与 `.` 之间是字词边界），对 `Version:  130` 不成立。要卡死应写 `\bVersion:\s*13\s*$`。
   - 还有一个通道洞：HPC 分支把日志换成常量 ``references/repos/harnessfoam/harnessfoam/agents/graph.py:230` stdout_str = "HPC Run Complete"`，于是 `validate_runtime` 既找不到 `Version:` 也找不到 `End`/`Time` → 该通道恒 FAILED。契约只对本地 WSL 通道有效。
3. **覆盖面上更窄**：全仓没有一处匹配 `Mesh OK.`——`grep -rn "Mesh OK" --include=*.py harnessfoam/` 返回 **0 条**（不是"只命中提示文本"，是一处都没有），G2 的逐字判据完全没有实现。它的 G2 只能靠生成脚本第一行 `set -e`（``references/repos/harnessfoam/harnessfoam/agents/runner.py:70``，`local_script = f"""#!/bin/bash\nset -e`）把 checkMesh 的非零退出码变成整体非零，即**退回退出码判据**；而 checkMesh 对"有 warning 但未 failed"的网格返回 0，这条路径上"`Mesh OK.` 逐字"的语义没被实现。

一句话：**它是「G3 + 环境指纹 + 日志完整性 + Courant」，同时丢了 G2 的逐字判据；对我们最值钱的是那行 `Version: 13`，成本是一次 grep。**

### 8 部署依赖

- OpenFOAM：README 顶部 badge 只写 `OpenFOAM-Compatible`（README:13），**没有版本号**；真正的版本声明是硬编码路径：``references/repos/harnessfoam/harnessfoam/benchmark.py:24` . /opt/openfoam13/etc/bashrc`、``references/repos/harnessfoam/harnessfoam/tutorial_regression.py:29` source = f"/opt/openfoam13/tutorials/{relative}"`、``references/repos/harnessfoam/harnessfoam/agents/runner.py:75` for foamrc in /opt/openfoam13/etc/bashrc /opt/openfoam*/etc/bashrc; do`。声明与实际一致（v13），是本批唯一直接对口 v13 的项目。
- Python：``references/repos/harnessfoam/pyproject.toml:9` requires-python = ">=3.10"`；README:12 `Python-3.10+`。
- 关键第三方包（`pyproject.toml` dependencies 原文）：`langgraph>=0.0.26`、`langchain>=0.1.0`、`langchain-openai>=0.0.2`、`pydantic>=2.0`、`faiss-cpu>=1.7.4`、`gmsh>=4.11.1`、`pyvista>=0.42.3`、`mcp>=1.0.0`、`python-dotenv>=1.0.0`、`rich>=13.0`、`fastapi>=0.100.0`、`uvicorn>=0.20.0`、`websockets>=11.0`、`httpx>=0.24.0`、`asyncssh>=2.14.0`。其中 `faiss-cpu` 是死依赖（无向量检索）。
- 容器：无 Dockerfile（`find . -name 'Dockerfile*'` 空）；但 ``references/repos/harnessfoam/harnessfoam/api/server.py:163` async def install_openfoam(websocket)` 提供 Web 一键装 OF，README:26 自称 "automatic environment provisioning (WSL/Docker/Native)" —— 与 R11 冲突，只能看不能点。
- 平台强依赖 WSL：``references/repos/harnessfoam/harnessfoam/benchmark.py:32` if not shutil.which("wsl"): return {"status": "UNSUPPORTED", "error": "OpenFOAM 13 smoke benchmark requires WSL on Windows"}`；``references/repos/harnessfoam/harnessfoam/tutorial_regression.py:25`` 同。纯 Linux 上两个回归直接 UNSUPPORTED。
- API key：`.env`（``references/repos/harnessfoam/harnessfoam/agents/runner.py:10` load_dotenv()`）+ Web 设置弹窗（README:47）；无本地模型、无 GPU 要求。
- 许可证：**无 LICENSE 文件**（`ls harnessfoam/LICENSE*` → No such file），但 README:14 badge 写 MIT、`pyproject.toml` classifier 写 `License :: OSI Approved :: MIT License`。存疑，见文末。

### 9 理论上优点 / 缺点

优点：
- 机制：判据集中在 4 个不调 LLM 的文件（`validation.py`/`physics_validation.py`/`reference_benchmarks.py`/`case_manifest.py`），输入只是字符串与目录 → 收益：同一份判据被 CLI、Web、MCP 三个入口复用，且能被 `tests/unit/` 单测；代价：判据与生成器两套代码，字典键改一次要同步两处。
- 机制：`validate_runtime` 只吃字符串、不碰 case 目录结构 → 收益：本地/WSL/HPC 理论上可共用一份判据；代价：某通道不回传日志（``references/repos/harnessfoam/harnessfoam/agents/graph.py:230``）时判据必然失败，那条通道等于没接。
- 机制：reviewer 写回前按 attempt 号整目录备份（``references/repos/harnessfoam/harnessfoam/agents/graph.py:139`-146`）→ 收益：坏改动可逐轮回滚，配合 `failure_ledger.jsonl` 能复现每次尝试；代价：备份落在 case 目录内，磁盘随轮数线性涨，也会污染"case 有几个文件"这类统计。
- 机制：`physics_autopilot` 与 `reviewer` 按日志诊断标志分流（``references/repos/harnessfoam/harnessfoam/agents/graph.py:418`-431`）→ 收益：数值发散不走"改字典"通用路，避免把发散当语法错修；代价：分流靠 7 条字符串正则，新 solver 的新报错形态不命中就静默退回通用路。

缺点：
- 机制：``references/repos/harnessfoam/harnessfoam/physics_validation.py:45`-46` 在"没有数值时间目录"时 `return True, {"status": "SKIPPED", ...}` → 代价：一个没写出场的 case 在物理闸上是"通过"，最终状态只由 runtime 判据决定，solver 正常结束但没写场仍可能 SUCCESS（非 cavity 类无兜底）。
- 机制：``references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:8`` 用 prompt 文本里有没有 "cavity"/"lid driven" 决定是否开物理硬阈值 → 代价：判据强度随用户措辞变化，同一条物理需求换个说法就退化成"无阈值"。
- 机制：版本断言读合并 stdout，而 Allrun 里 blockMesh 最先打横幅 → 代价：确认的是"这条 shell 的 OF 是 13"，同名但不同 build 的 solver 被替换时仍可能通过。
- 机制：9 节点图 + 6 个 LLM 角色 × `max_errors=3`，每轮都带 RAG 上下文（`format_context` 默认 `max_chars=2500`，``references/repos/harnessfoam/harnessfoam/knowledge.py:156``）→ 代价：一次失败最多三整轮 LLM 往返，token 成本对"最小框架"是主开销。

### 10 对本项目的可迁移点

可迁移（按性价比排序）：
1. **把 `Version: 13` 加进 G3**：照 ``references/repos/harnessfoam/harnessfoam/validation.py:134`` 改成 `grep -qE "Version:[[:space:]]*13([^0-9.]|$)" log.shortRun`。它抓的正是 R11 想禁的"跑到了别的 OF 版本"，成本一行；现 G3 只 grep `FOAM FATAL`（README:182），抓不到这个失效模式。
2. **preflight 的 patch 集合交叉检查**（``references/repos/harnessfoam/harnessfoam/validation.py:41`-59`）：从 blockMeshDict 的 `boundary (...)` 抽 patch 名集合，与 `0/U`、`0/p` 的 `boundaryField` 集合做**相等**比较，不等报 `Patch mismatch for 0/U: mesh=[...], field=[...]`（`:59`）。这是 R5「导入网格后必须读 boundary 拿真实 patch 名」的可执行化，纯文本、不跑命令，属 G1 加强而非新门。
3. **按 solver 的必需文件表**（``references/repos/harnessfoam/harnessfoam/validation.py:63`-74`）：`solver_requirements` 把 simpleFoam/interFoam/... 映射到必需文件。我们 G1 只查三个 system 文件 + `0/` 非空，没有 solver 维度；v13 里 `foamRun -solver incompressibleVoF` 缺 `0/alpha.water` 是典型 FATAL 源。
4. **完成标记 + 时间步数**（``references/repos/harnessfoam/harnessfoam/validation.py:91``/`:132`）补进 G3：退出 0 不等于写了步。
5. **失败账本**（`failure_ledger.jsonl`，``references/repos/harnessfoam/harnessfoam/agents/graph.py:317`-325`）：我们 `log.*` 有日志，缺"第几轮、改了哪个文件、为什么"。
6. cavity 那 5 条阈值（``references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:11`-15`）可作 M1 验收候选，但值是 cavity 专用常数（Courant<=0.2、|continuity|<=1e-6），不可平移到别的 case。

不可迁移：
- 9 节点 LangGraph + 6 个 LLM 角色：机制上每节点一次带 RAG 上下文的 LLM 调用，而我们 M1 的判据在命令输出里，多角色只加失败面不加判据。
- 双 MCP server（8 + 11 tool）：MCP 是给外部编排器的协议面，我们没有第二个消费者；两套粒度还会带来"谁是权威"的问题。
- VLM 视觉复核（README:102）：它自称 vision 不可用报 `SKIPPED` 而不假过，这条纪律对；但引入"不可用即跳过"的通道，与"没有独立判据就写没有"冲突。
- 自带 case 生成器（`cases/cavity.py` 把整套字典写成 Python 字符串）：与 R3「必须从 tutorial 派生」相反，且一旦 v13 字典语法变更就与系统树脱钩。

---

## 7. autofoam（本地 references/repos/autofoam，tier B）

### 0 一句话定位与规模

单 agent 的八段流水线：LLM 只负责把自然语言抽成 `CFDParams` 与在 FATAL 时改一个字典文件，其余（选 solver、算网格量、写字典、跑、打分）全是确定性 Python；围绕它有一整套自进化训练脚本。

规模：36 个 py / 10801 行（命令见文首）。最大文件：`openfoam_agent/gmsh_generator.py` 1730、`prompt_catalog.py` 1728、`case_writer.py` 1276、`agent.py` 585、`param_extractor.py` 445、`rag.py` 443、`knowledge_base.py` 431、`runner.py` 194、`scorer.py` 171、`self_correct.py` 149（`wc -l` 实测）。入口：``references/repos/autofoam/openfoam_agent/agent.py:65` def run(self, prompt, max_retries=3, use_gmsh=True, ...)`；CLI 在 ``references/repos/autofoam/scripts/run_agent.py:11` def main()`（参数 `prompt`/`--file`/`--no-gmsh`/`--retries`/`--timeout`/`--no-llm`，`:17-22`）；Web 在 ``references/repos/autofoam/openfoam_agent/ui.py:10` def launch_ui(...)`。

### 1 输入形态

一条自然语言 prompt（README 的 seed 里有 `"2D lid-driven cavity flow at Re=100"` 这类，``references/repos/autofoam/openfoam_agent/agent.py:21`-32` 共 10 条），可选 `max_retries`/`use_gmsh`/`sim_timeout`。进入函数 ``references/repos/autofoam/openfoam_agent/agent.py:65``，第一步是 LLM 改写 prompt（`:83 prompt_refiner.refine(...)`），第二步才是结构化抽取（`:102 param_extractor.extract(...)`）。

无上传、无几何文件、无网格文件——几何由 `CFDParams.geometry_type` 枚举 + 尺寸参数决定，网格由 13 个参数化 gmsh 模板生成。这一条与我们 R5 的边界直接冲突：它把"曲面几何"变成了 `gmsh_generator` 的模板选择问题。

### 2 分层与模块边界

| 文件 | 行数 | 职责 | 碰 LLM |
|---|---|---|---|
| `agent.py` | 585 | 8 段编排 + 重试循环 | 是（调下面三个） |
| `param_extractor.py` | 445 | 自然语言 → `CFDParams`（JSON schema 约束） | 是 |
| `prompt_refiner.py` | — | 同义改写 | 是 |
| `dict_fix.py` | 149 | FATAL → 定位文件 → LLM 出全文 → 写回 → 重跑 | 是 |
| `rag.py` | 443 | Chroma + sentence-transformers 检索 | 是（embedding） |
| `case_writer.py` | 1276 | 字典模板（f-string） | 否 |
| `gmsh_generator.py` | 1730 | 13 个参数化网格模板，写 `.geo`/`mesh.msh` | 否 |
| `solver_selector.py` | — | 8 个 solver 的规则表 | 否 |
| `numerical_policy.py` | — | y+ 感知的 schemes/松弛/容差 | 否 |
| `runner.py` | 194 | 子进程跑 blockMesh/checkMesh/solver + 解析日志 | 否 |
| `scorer.py` | 171 | 多分量奖励 | 否 |
| `self_correct.py` / `failure_diagnosis.py` | 149 / — | 失败信号采集与重试上下文 | 否 |
| `knowledge_base.py` | 431 | 10 条硬编码知识条目 | 否 |
| `training.py` + `scripts/train_*.py` | 298+ | QLoRA/DPO/主动学习 | 否（训练侧，不在推理链路） |

边界比 harnessfoam 更"哑"：没有 agent 循环框架，`agent.py` 就是一个 for 循环串函数（`:93 for attempt in range(max_retries):`）。**唯一碰文件系统的写操作在 `case_writer.write_all`（`:105`）与 `gmsh_generator.generate`；唯一跑仿真的在 `runner.py`；唯一判分的在 `scorer.py`。** LLM 的权限被压到"填参数"和"改一个文件"。

### 3 agent 拓扑

单循环，无 planner/executor 分离、无角色。README:49 自述：`├── agent.py           # 8-stage pipeline + Layer-1 retry orchestrator`。

流水线顺序（``references/repos/autofoam/openfoam_agent/agent.py:65`-327`）：refine → extract → 规则纠偏（多相/浮力/icoFoam/可压的字符串启发式，`:124-166`）→ `select_solver`（`:169`）→ `compute_mesh_resolution` + `compute_time_settings`（`:186-187`）→ `compute_numerical_policy`（`:196`）→ RAG 取 2 个参考 case（`:202 n_cases=2`）→ gmsh 网格（`:213`，失败退 blockMesh `:216`）→ 写字典（`:232`）→ 跑（`:238`）→ 打分（`:251`）→ `score>=0.5` 返回（`:273`）→ 否则采集信号（`:278`）→ 必要时 `dict_fix`（`:290`）→ 拼下一轮上下文（`:321`）。

传输格式：pydantic `CFDParams`（`schemas.py`）与 dataclass `RunResult`，不是消息/图状态；错误信息是以**字符串**拼进下一轮抽取输入（`:101 input_text = prompt + error_context`）。

### 4 工具接口

**无 function calling、无 MCP。** LLM 被当三个"结构化函数"用：`param_extractor.extract`、`dict_fix.propose_fix`、`prompt_refiner.refine`。对外接口是 CLI（``references/repos/autofoam/scripts/run_agent.py:17`-22`）与 Python API（`OpenFOAMAgent().run(...)`），另外 ``references/repos/autofoam/openfoam_agent/ui.py:10`` 起 gradio（`import gradio as gr`，`:11`）。

这一点值得记：它证明了"不用 tool calling 也能到 82% 级成功率"那条路线的形态——LLM 输出被 pydantic schema 卡死，工具是确定性代码。

### 5 知识来源

四档并存，检索只占一小块：
1. **RAG**：ChromaDB 持久化（``references/repos/autofoam/openfoam_agent/config.py:14` CHROMA_DIR = PROJECT_ROOT / "data/chroma_db"`）+ 本地 `SentenceTransformer`（``references/repos/autofoam/openfoam_agent/rag.py:118` self.encoder = SentenceTransformer(embedding_model)`），嵌入模型 ``references/repos/autofoam/openfoam_agent/config.py:20` EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"`。
   - 切块按**文件角色**而非长度：`case_summary` / `control_dict` / `fv_schemes` / `boundary_conditions` / `gmsh_geo`（``references/repos/autofoam/openfoam_agent/rag.py:151`-179` 逐类 append meta `chunk_type`），一个 tutorial case 最多 5 块。
   - 检索带 where 过滤：``references/repos/autofoam/openfoam_agent/rag.py:240` where={"chunk_type": "case_summary"}`，`n_results=min(n_results, self.collection.count())`（`:239`），默认 `n_results=3`（`:231`）。
   - `retrieve_with_content` 过采样 `oversample = max(n_cases * 4, 8)`（`:275`）后取 `n_cases=2`（``references/repos/autofoam/openfoam_agent/agent.py:202``），再按 case_name 拉同 case 的其余块（`:294 self.collection.get(...)`）。
   - 上下文截断：`max_chars_per_chunk=1500`（``references/repos/autofoam/openfoam_agent/self_correct.py:141``），另有 `max_chars_per_chunk: int = 2000` 默认（``references/repos/autofoam/openfoam_agent/rag.py:326``）。
2. **字典模板**：`case_writer.py` 1276 行，每个字典一个 f-string（`_control_dict :161`、`_fv_schemes :207`、`_fv_solution :311`、`_block_mesh_dict :648`），BC 由 patch 名硬映射（`:53 def _get_patch_bc(patch_name: str)`）。
3. **数值策略表**：``references/repos/autofoam/openfoam_agent/numerical_policy.py:37` compute_numerical_policy`，y+ 目标 30（壁面函数）或 1（解析），首层高度 `pol.first_cell_height = pol.y_plus_target * nu / u_tau`（`:90`）。
4. **硬编码 prompt/知识库**：`prompt_catalog.py` 1728 行（`PromptCase(prompt, params, case_tag, expert_notes)`）、`knowledge_base.py` 10 条 `KnowledgeEntry`。

机制：**模板优先、LLM 兜底**——字典主体不是生成的，只是参数化填空 → 语法正确率高到可以不装 preflight；代价是模板覆盖不到的 solver/BC 类型没有路径（`_get_patch_bc` 是硬映射，未知 patch 名只能落到默认）。

### 6 错误处理与自修正

- 触发条件（``references/repos/autofoam/openfoam_agent/self_correct.py:83`-93`）：`if score < threshold: return True`；`if signals.diverged or signals.has_nan or signals.has_fp_exception: return True`；`if mi == mi and mi > 1e-2: return True`（mi 为解析出的质量失衡）。阈值 ``references/repos/autofoam/openfoam_agent/config.py:26` RETRY_SCORE_THRESHOLD = float(... "0.7")`。
- 轮数：``references/repos/autofoam/openfoam_agent/agent.py:68` max_retries: int = 3`，第 n 轮独立目录 `:94 attempt_dir = CASES_DIR / f"{case_name}_attempt{attempt}"`（旧目录不覆盖）。
- 定向修复：仅当 `signals.failure_type.startswith("foam_fatal_")` 且 LLM 可用时（``references/repos/autofoam/openfoam_agent/agent.py:283`-292`）调 `dict_fix.try_dict_fix`：先 `parse_fatal_file_target` 从 FATAL 日志里认出文件名（``references/repos/autofoam/openfoam_agent/dict_fix.py:16``），只改那一个文件，立即重跑（`_rerun`），新分 ≥0.5 就收（``references/repos/autofoam/openfoam_agent/agent.py:303``）。认不出文件就整条路空转：``references/repos/autofoam/openfoam_agent/dict_fix.py:106`-107 if target is None or not target.exists():` / `    return None`。
- 失败分类：``references/repos/autofoam/openfoam_agent/failure_diagnosis.py:9`-17` 八类（`foam_fatal_mesh`/`foam_fatal_bc`/`foam_fatal_scheme`/`fp_exception`/`divergence`/`timeout`/`no_convergence`/`unknown`）。
- 重试上下文（``references/repos/autofoam/openfoam_agent/self_correct.py:111`-147`）：上轮 solver、湍流模型、scorer 反馈、发散提示、质量失衡数值、NaN 提示、FPE 提示、最后 40 行日志、RAG 原文。
- 无可选记忆、无 LLM 自评；改法由 LLM 出，改进与否由 `scorer` 判。

### 7 它怎么知道跑成功了

有独立判据，但是**加权分数 + 0.5 阈值**，不是布尔门。链条：

1. 网格闸（``references/repos/autofoam/openfoam_agent/runner.py:144``）：`if "has invalid cells" in check_log or ("Failed" in check_log and rc != 0):` → 直接返回失败（`error_message="checkMesh: invalid mesh"`）。注意它**不要求 `Mesh OK.`**，只抓这两个串。
2. 退出码：``references/repos/autofoam/openfoam_agent/runner.py:185` success=(rc == 0),`。
3. 收敛：``references/repos/autofoam/openfoam_agent/runner.py:29` def _check_convergence(log: str) -> bool:` —— `:30-34` 命中 `"SIMPLE solution converged"` / `"PISO: converged"` / `"solver converged"` 任一即 True；`:37 if "FOAM FATAL ERROR" in log or "FOAM FATAL Exception" in log: return False`；`:40 if "ExecutionTime" in log and "End" in log and "FOAM FATAL" not in log: return True`。
4. 打分（``references/repos/autofoam/openfoam_agent/scorer.py:97` compute_reward`）：
   - `:105` FATAL → `return 0.0`；`:107` TIMEOUT → `0.0`
   - `:111 if run_result.converged: score += 0.40`；未收敛但退出 0 → `:113 score += 0.15`（有残差）/ `:117 score += 0.05`（无残差）
   - 残差 `:123 max_res < 1e-4` → `+0.20`，`<1e-3` → `+0.10`
   - 残差趋势 `:134 score += trend * 0.10`
   - 质量守恒 `:140 if _check_mass_conservation(log): score += 0.05`
   - solver 与规则表一致 `:146 score += 0.10`
   - `_bc_valid`（`:152`）→ `+0.05`
   - 惩罚：非正交 >70° `-0.10`（`:157`）、runtime>300 s `-0.10`（`:161`）、残差平台 `-0.05`（`:165`）
5. 判定：``references/repos/autofoam/openfoam_agent/agent.py:254` success=score >= 0.5,`、`:273 if score >= 0.5:` → 写数据集并返回。

机制判读（这是本节要点）：
- **0.5 可在"未收敛"时被凑到**：未收敛但有残差 `0.15` + 残差<1e-4 `0.20` + 守恒 `0.05` + solver 一致 `0.10` + bc `0.05` = `0.55`。所以"成功"不等价于"收敛"，收敛只是 `+0.40` 的一项。
- **solver 一致项是自指的**：``references/repos/autofoam/openfoam_agent/scorer.py:145` expected = select_solver(params)`，而 `params` 正是用来生成 case 的同一份，`+0.10` 奖励的是"自洽"，不是物理。
- **守恒项取错数**：``references/repos/autofoam/openfoam_agent/scorer.py:56`-69` 扫含 "continuity" 的行，`:60 if "continuity errors" in low or "continuity" in low:` 后 `for tok in line.split()` 取**第一个能解析成浮点且 <1e-3** 的 token。OpenFOAM 那行是 `time step continuity errors : sum local = X, global = Y, cumulative = Z`，第一个数是 `sum local`，不是 `global`——`+0.05` 测的不是想测的量。
- **无场值检查**：全仓不读末时刻 `U`/`p` 文件，NaN 只靠日志里 `-nan`/`1.#ind` 字符串（``references/repos/autofoam/openfoam_agent/self_correct.py:66``）。物理正确性完全不在判据里（对比 harnessfoam 的 `physics_validation`）。
- 结论：**有独立判据（退出码 + 网格串 + 收敛标记 + 残差数值），比我们 G3 多"收敛/残差"维度；但它是可加总的分数，能被非收敛项凑过线，且不含任何场值/物理量断言。**

### 8 部署依赖

- OpenFOAM：README:3 `A self-evolving LLM-driven OpenFOAM v2412 case-authoring agent.`；README:152 表格 `| OpenFOAM v2412 | Must be sourced before running any simulation |`；README:187-188 `source /path/to/openfoam2412/etc/bashrc`。代码侧硬编码：``references/repos/autofoam/openfoam_agent/config.py:6` OPENFOAM_BASHRC = "/home/nvidia/miniconda3/envs/openfoam2412/etc/bashrc"`（作者机器路径，且是 conda 装法）。
- Python ≥3.10（README:153 `| Python ≥ 3.10 | With \`vllm\`, \`unsloth\`, \`gmsh\`, \`chromadb\`, \`pydantic\` |`）。
- 模型：本地 14B（``references/repos/autofoam/openfoam_agent/config.py:16` LLM_MODEL = ".../data/checkpoints/qwen_coder_14b_merged"`，`:19` 可用 `OPENFOAM_AGENT_LLM_OVERRIDE` 覆盖），vllm 加载（`:52 from vllm import LLM`，`dtype="bfloat16"` `:57`，`gpu_memory_utilization` 默认 0.85 `:23`）。
- GPU：README:154 `| NVIDIA GPU | ≥ 24 GB VRAM recommended (14 B model at bf16) |`。
- 权重：HF 私有仓，需申请（README:155、`:163-165 huggingface-cli download arungovindneelan/foam-cfd-unified-14b-private`）。
- 无 requirements/lockfile：仓库根 `ls` 只有 `README.md figures/ openfoam_agent/ scripts/ template.pdf`，无 `requirements.txt`、无 `pyproject.toml`；依赖只在 README:153/173 的 `pip install vllm unsloth gmsh chromadb pydantic sentence-transformers` 一行里，**无版本号**。
- 无 docker；训练侧另有 `scripts/train_qlora.py`/`train_dpo.py`/`active_learning.py`（298+ 行 `training.py`）——推理也要装 vllm+unsloth。

### 9 理论上优点 / 缺点

优点：
- 机制：字典由 1276 行 f-string 模板生成，LLM 只填 `CFDParams`（``references/repos/autofoam/openfoam_agent/case_writer.py:105` write_all`）→ 收益：字典语法错误几乎不可能，不需要 preflight 也能过多数 FATAL；代价：新 solver/新 BC 必须写模板，模板外的组合没有路径。
- 机制：每轮 attempt 独立目录（``references/repos/autofoam/openfoam_agent/agent.py:94``）→ 收益：轮次之间可对比、可回看，不覆盖上一轮产物；代价：磁盘随轮数线性增，且要自己清理。
- 机制：`dict_fix` 只改 FATAL 指名的那一个文件然后**立即重跑**（``references/repos/autofoam/openfoam_agent/dict_fix.py:96`-113`），新分 ≥0.5 就收（``references/repos/autofoam/openfoam_agent/agent.py:303``）→ 收益：改动半径最小、因果可归因；代价：`parse_fatal_file_target` 认不出文件时整条路径空转。
- 机制：`numerical_policy` 把 y+ 目标、首层高度、松弛因子做成参数化函数（`:37/:90`）→ 收益：网格与数值设置同源，改 Re 不需要人重算；代价：策略表是经验常数，没有对 v13 的默认值校对。

缺点：
- 机制：`scorer.py` 是可加总分数 + ``references/repos/autofoam/openfoam_agent/agent.py:273` score >= 0.5` → 代价：判据可被"未收敛但残差低"的组合凑过线（0.15+0.20+0.05+0.10+0.05），"成功"与"收敛"不等价。
- 机制：`_bc_valid` 只在 `0/` 里 grep `"inlet"` 和 `"outlet"` 字面（``references/repos/autofoam/openfoam_agent/scorer.py:13`-22`）→ 代价：无进出口的 case（cavity、周期通道）恒扣 0.05，奖励函数隐含"必须有进出口"的几何假设。
- 机制：三处绝对路径写死在 `config.py`（`:6` bashrc、`:7` TUTORIALS_DIR、`:16` model）→ 代价：换机器必须先改源码（或设一个环境变量覆盖模型路径），配置与代码没分离，也让 R10/R11 类审计无法自动化。
- 机制：无锁文件 + 训练/推理性同仓（`vllm`/`unsloth` 与 gradio/chromadb 混在一句 pip 里）→ 代价：复现只能照 README 手装，版本漂移无记录；纯推理也得吃训练栈的依赖树。

### 10 对本项目的可迁移点

可迁移：
- **独立 attempt 目录**（``references/repos/autofoam/openfoam_agent/agent.py:94``）：我们 `runs/<批次>/<case_id>/` 只有一层，重试会覆盖 `log.*`；改成 `<case_id>/attempt_N/` 才能对比轮次。代价是路径变长，`results.csv` 要多一列 `attempt`。
- **"FATAL 指名文件 → 只改它 → 立即重跑"**（``references/repos/autofoam/openfoam_agent/dict_fix.py:96`-113`）：这是我们 R8「G1–G3 连续两轮修不好就停」之前该有的最小修复协议，比"整份字典重生成"省一大截 token，也更容易归因。
- **完成标记 + `ExecutionTime` 双条件**（``references/repos/autofoam/openfoam_agent/runner.py:40``）：补进 G3。我们现在只查"无 FATAL"，不要求出现 `End`/`ExecutionTime`；一个被 `Ctrl-C` 或 shell `set -e` 掐断的运行，退出码可能仍是 0 而没有任何完成标记。
- **网格闸抓 `has invalid cells`**（``references/repos/autofoam/openfoam_agent/runner.py:144``）：这是 G2 的一条补充信号——比 `Mesh OK.` 更早、更直接。"`Mesh OK.` 出现"与"`has invalid cells` 不出现"并不等价（前者还要求没有 failed checks）。
- **参数化网格 + y+ 首层高度公式**（``references/repos/autofoam/openfoam_agent/numerical_policy.py:90``）：如果 M2 要做边界层加密，这行公式可以直接用（`first_cell_height = y+ * nu / u_tau`）。

不可迁移：
- 本地 14B + vllm + ≥24 GB GPU + 私有 HF 权重：与"最小框架"和本机条件都不符。
- Chroma + `bge-small` 索引：我们 R1 的结论是 grep 与专门检索层打平，索引的安装/版本成本换不来增量（04 的实测）。
- 训练闭环（QLoRA/DPO/主动学习/`regression_diff.py`）：机制上需要"大量跑批 + 评分"才闭环，我们的 R12 明确设计期禁跑。
- `gmsh_generator` 的 13 个模板：R5 明令曲面/多体场景停下问，不走 gmsh 自动生成。

---

## 8. deepflow（本地 references/repos/deepflow，tier B）

### 0 一句话定位与规模

PyQt5 桌面 CFD 助手：一个 LangChain ReAct agent + 11 个文件/命令工具 + FAISS 知识库，用户在对话框里指挥它改字典、跑 solver、看残差曲线。

规模：7 个 py / 1791 行（文首命令）。分布：`deepflow_agent/main_gui.py` 813、`openfoam_agent.py` 397、`log2csv.py` 186、`plot_data.py` 150、`scripts/create_knowledge_base_{sync,async}.py` 80/93、`create_wordcloud.py` 72。入口：``references/repos/deepflow/deepflow_agent/main_gui.py:426` class MainWindow(QMainWindow)`，agent 在 `:609 self.agent_handler = OpenFOAMRAGAgent(case_dir=self.case_dir, ...)` 创建；核心类 ``references/repos/deepflow/deepflow_agent/openfoam_agent.py:285` class OpenFOAMRAGAgent`，`run()` 在 `:380`。

注意 README:16 自述：`Due to the large size of the complete CFD case files ... this repository currently **only open-sources the core code and architecture implementation of the Agent component**.` 1791 行不代表系统规模。

### 1 输入形态

对话框自然语言 + 一个已存在的 case 目录。构造时硬校验目录：``references/repos/deepflow/deepflow_agent/openfoam_agent.py:287` if not os.path.isdir(case_dir): raise FileNotFoundError(f"Case directory '{case_dir}' does not exist.")`。输入进 `:384-387`：

`        result = self.executor.invoke({` / `            "input": user_input,` / `            "chat_history": self.chat_history` 

没有"从零生成一个 case"的路径——它假设 case 骨架已经在磁盘上（仓库根自带 `cavity/`、`mixerVessel2D/` 两个案例目录）。这与我们的 R3「从 tutorial 派生」相容，但把"派生"这一步留给了人。

### 2 分层与模块边界

| 文件 | 行数 | 职责 | 碰文件系统 | 碰 LLM | 跑仿真 |
|---|---|---|---|---|---|
| `main_gui.py` | 813 | Qt 界面、参数面板、残差图、工具确认闸 | 是 | 是（回调里发信号） | 间接（经工具） |
| `openfoam_agent.py` | 397 | 工具定义 + prompt + AgentExecutor + RAG 装载 | 是（工具内） | 是 | 是（`execute_shell_command`） |
| `log2csv.py` | 186 | 日志 → CSV（残差/流量） | 是 | 否 | 否 |
| `plot_data.py` | 150 | CSV → matplotlib | 否 | 否 | 否 |

**没有 runner 模块**：跑仿真这件事由 LLM 自己发一条 shell 命令完成（`execute_shell_command`，`:196`）。这是它和另外三个 CFD 项目最大的结构差异——没有"执行层"，只有"工具层"。判据也因此无处安放（见 §7）。

### 3 agent 拓扑

单 ReAct 循环，一个角色，无 planner/executor 分离：

- ``references/repos/deepflow/deepflow_agent/openfoam_agent.py:375` return create_openai_tools_agent(self.llm, self.tools, prompt)`
- `:299 self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)` —— **未传 `max_iterations`**，用 LangChain 默认。
- 消息格式：`ChatPromptTemplate.from_messages([...])`，四个槽：system prompt（`:342-369` 长段行为规则）、`MessagesPlaceholder("chat_history")`（`:371`）、`("user", "{input}")`（`:372`）、`MessagesPlaceholder("agent_scratchpad")`（`:373`）。
- 记忆：`chat_history` 只保留最近 20 条（`:396 self.chat_history = self.chat_history[-20:]`）。
- 人工闸在 UI 侧：``references/repos/deepflow/deepflow_agent/main_gui.py:107` def confirm_and_execute_wrapper(main_window, **kwargs) -> str:` + `:101 class UserConfirmationRequired(Exception)`。

### 4 工具接口

11 个 `@tool`（`grep -c "@tool" deepflow_agent/openfoam_agent.py` = 11）：`send_email` `:24`、`read_file` `:45`、`query_log_file` `:67`、`write_file` `:98`、`list_files` `:108`、`search_and_replace_in_file` `:126`、`insert_line_into_file` `:149`、`delete_lines_from_file` `:171`、`execute_shell_command` `:196`、`read_csv_file` `:232`、`read_log_tail` `:261`；另加一个 RAG 工具 `openfoam_knowledge_retriever`（`:327-331`，`create_retriever_tool`）。

实测缺陷两处：
- 构造函数注册的 `self.tools` 只列 10 个（`:290-294`），**漏了 `query_log_file`**；而 `read_file` 的 docstring 却指路给它：`:49 Note: If the target is a .log file and is larger than MAX_LOG_FILE_SIZE, this tool will refuse to read and prompt to use the 'query_log_file' tool.` → 模型被引到一个看不见的工具。
- `execute_shell_command` 禁复合语法：`:208 if any(op in command for op in ['|', '>', '<', '&&', '||', ';']):` → 标准 OF 用法 `simpleFoam > log.simpleFoam` 不可用，模型只能赌日志落在哪再用 `read_log_tail` 找。

### 5 知识来源

纯 RAG，两库合一：
- 嵌入：``references/repos/deepflow/deepflow_agent/openfoam_agent.py:304` embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_base=api_base)`。
- 索引：`faiss_index/faiss_index_database` 与 `faiss_index/tutorials` 两个 FAISS 目录分别 `FAISS.load_local`（`:316`、`:320`），再 `:321 vectorstore.merge_from(tutorials_vs)`。
- 建库参数（`references/repos/deepflow/scripts/create_knowledge_base_sync.py`）：`:28 text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`；`:44-47 DirectoryLoader(..., loader_cls=TextLoader, use_multithreading=True, silent_errors=True)`；`:61 FAISS.from_documents(documents=splits, embedding=embeddings)`；`:67 vector_store.save_local(index_path)`。
- 检索：`:325 retriever = vectorstore.as_retriever()` —— **未传 k / search_type**，用 LangChain 默认（相似度，k=4）。
- 降级：索引缺失时只打印不抛：`:308-313`（`print("\n!!! RAG Critical Error !!!")` … `RAG functionality will be unavailable.`），`:334-335` 的 except 也吞掉一切异常，工具集少一个但流程继续。

机制：这是本批唯一"外部 API 嵌入 + 本地 FAISS"的组合 → 收益：知识库可离线查、可按子领域换库（README:38 提到可换成专有案例库）；代价：建库要联网调 OpenAI embedding，且索引是磁盘二进制（`allow_dangerous_deserialization=True`，`:316`），不可 diff、不可审。

### 6 错误处理与自修正

**无自动重试、无自反思。** 替代物全在 prompt 里：
- `:360-363` 第 5 条规则：`a. Carefully analyze the standard error (stderr)... b. If this is an expected, solvable configuration issue, try to fix it as before. c. If this is an unexpected, serious computational crash (e.g., solver divergence), you **must** call the send_email tool.`
- `:358` 第 4 条：长任务只允许查一次状态（`you should **check the task status only once** and report to the user`）——机制上等于禁掉了"盯着日志等收敛"。
- 人工闸：``references/repos/deepflow/deepflow_agent/main_gui.py:107`` 每次工具调用前弹确认。

轮数无上限也无记录；改坏了没有备份机制（对比 harnessfoam 的 `.harnessfoam/backups/`）。唯一的回滚手段是 LLM 自己调 `search_and_replace_in_file` 反向替换。

### 7 它怎么知道跑成功了

**无独立判据，失败会被报成成功。**

- 唯一信号是命令返回串里的退出码：``references/repos/deepflow/deepflow_agent/openfoam_agent.py:225` output += f"\n--- Exit Code: {result.returncode} ---"`，整串交给 LLM 读。
- prompt 明确把"退出 0"定义成"正常"：`:364 d. **As long as computation is proceeding normally (exit code is 0), never proactively suggest modifying parameters.**`
- 没有收敛判据、不查 `End`、不查 `FOAM FATAL` 字符串、不读末时刻场、不检查时间目录。**OpenFOAM 发散到 NaN 常常正常退出 0**，这条路径下模型会如实报告"exit code 0，计算正常"。
- `log2csv.py` 能解析残差（`:23 time_pattern`、`:24-26 solver_pattern` 匹配 `^(?:smoothSolver|GAMG|DICPCG):\s+Solving for (\w+),.*Final residual = ([\d\.\-eE+]+)`），但它只服务画图（``references/repos/deepflow/deepflow_agent/main_gui.py:491`` 的残差画布），不参与判定。
- `plot_data.plot_residuals` 同理，是给人看的。

对照我们的门禁：G1（结构）它隐含在"case 目录已存在"里；G2（`Mesh OK.`）完全没有；G3（无 FATAL + 退出 0）只有退出码那一半，且判定主体是 LLM；G4（产物可读）没有。**它是本批 6 个里唯一一个可以把"发散的算例"报告成成功的实现。**

### 8 部署依赖

- OpenFOAM：README:4 badge `[![OpenFOAM](https://img.shields.io/badge/OpenFOAM-v2412-green.svg)]`；README:146 正文 `- **OpenFOAM**: v2412`。代码里无版本常量、无路径常量——它靠宿主的 `PATH`/`WM_PROJECT_DIR`，所以实际跑哪个版本不可控（也就无从校验）。
- Python 3.10（README:145 `- **Python**: 3.10`；README:3 badge `Python-3.10+`）。
- 依赖（`requirements.txt` 全 8 行，全部 `==` 钉死）：`numpy==2.2.6`、`pandas==2.3.1`、`matplotlib==3.10.3`、`wordcloud==1.9.4`、`PyQt5==5.15.11`、`langchain==0.3.27`、`langchain-community==0.3.27`、`langchain-openai==0.3.28`。
- **缺 `faiss-cpu`**：`grep -in faiss requirements.txt` 无命中，而 ``references/repos/deepflow/deepflow_agent/openfoam_agent.py:16` from langchain_community.vectorstores import FAISS` 需要它 → 照 requirements 装完，RAG 必 ImportError，被 `:334` 的 except 吞掉后退化成"仅文件工具"。这条解释了为什么"README 说用 FAISS"和"requirements 装不出 FAISS"能同时成立。
- API key：OpenAI 兼容 endpoint + key，从 ``references/repos/deepflow/deepflow_agent/main_gui.py:242` class SettingsDialog(QDialog)` 填，落本地设置文件。
- 无 GPU 要求、无 docker、无本地模型。

### 9 理论上优点 / 缺点

优点：
- 机制：文件编辑工具是"外科手术式"的（`search_and_replace_in_file :126`、`insert_line_into_file :149`、`delete_lines_from_file :171`），prompt 还强制优先用它们（`:354 Prefer Precise Modifications`）→ 收益：每步 diff 小、可审、token 少；代价：跨文件耦合错（patch 名在 blockMeshDict 与 0/U 不一致）无法靠单文件替换修好，只能整体重写。
- 机制：每次工具调用前人工确认（``references/repos/deepflow/deepflow_agent/main_gui.py:107``）→ 收益：破坏性命令有硬闸，适合"人机协同"而不是无人值守；代价：全自动场景不可用，且确认疲劳后闸等于没有。
- 机制：`execute_shell_command` 用 `shlex.split` + 禁 `| > < && || ;`（`:208`、`:211`）→ 收益：注入面被压到"单条命令 + 参数"，不会出现管道逃逸；代价：OF 的标准重定向用法不可用，日志位置变成猜。
- 机制：`log2csv.py` 用固定正则把残差/流量抽成 CSV（`:23-31`）→ 收益：残差曲线不依赖 LLM，可复算；代价：正则绑死 `smoothSolver|GAMG|DICPCG` 前缀，v13 换 solver 名或改日志格式时静默无数据。

缺点：
- 机制：没有执行层也没有判据（§7），成功=LLM 读退出码 → 代价：发散但退出 0 的算例被报成成功，与 R4「自述不算证据」正面冲突。
- 机制：`requirements.txt` 缺 `faiss-cpu`（§8）→ 代价：RAG 在生产里静默降级，用户以为有知识库在起作用。
- 机制：`self.tools` 漏注册 `query_log_file`（`:290-294` vs `:67`）→ 代价：大日志场景下模型被 docstring 引向不存在的工具，白耗一轮。
- 机制：`AgentExecutor` 未设 `max_iterations`（`:299`）→ 代价：轮数由框架默认决定，无上限记录、无失败账本，事后无法复现它试了几次。

### 10 对本项目的可迁移点

可迁移：
- **单条命令白名单式执行**（`:208/:211`）：我们的 `verify_case.sh` 是固定脚本，但 agent 若需要跑命令，禁复合语法这条可以直接照抄——它把"命令注入"与"日志重定向"两个问题一起简化了。
- **工具调用前确认**（``references/repos/deepflow/deepflow_agent/main_gui.py:107``）：可映射到 R8 的"停下问"，形式上给 agent 一个 `confirm` 语义。
- **`log2csv.py` 的残差正则**（`:23-26`）：比"grep `End`"强的一层——它能确认每个场每步都出了 `Final residual`，可作为 G3 通过后的"有数"证据，也可喂 G4。
- **"只有一步状态检查"的纪律**（`:358`）：明确写"不要连续盯日志"，避免 agent 把 token 花在轮询上。

不可迁移：
- 无 runner 无判据的整体形态（§7）——这是我们 R4 明确禁止的。
- OpenAI embedding + FAISS 双索引（`faiss_index/` 二进制、`allow_dangerous_deserialization=True`）：违背零安装，且索引不可审。
- PyQt5 桌面壳（813 行）：我们的交付面是 CLI + CSV，不是 GUI。
- 从"已存在的 case 目录"起步：我们要的是从 tutorial 派生（R3），起点不同。

---

## 9. hpc-skills（本地 references/repos/hpc-skills，tier A→B，见文末）

### 0 一句话定位与规模

22 个纯文本的 HPC skill 包（OpenFOAM / SU2 / LS-DYNA / FEniCS / PETSc / VASP / GROMACS …），用"`SKILL.md` 触发 + `references/` 渐进加载"分发，**不含任何 agent 运行时**。

规模（实测命令）：`ls skills | wc -l` → **22**；`find . -name '*.md' | wc -l` → 272；`wc -l skills/*/SKILL.md | tail -1` → 1498；`find . -name '*.py' | wc -l` → 13 / 912 行，其中 4 个是 `skills/hpc-orchestration/scripts/` 的 CLI（486 行），其余是网格/求解器模板脚本；全部文件 439。

CFD 相关只有 `hpc-openfoam` 一个：`SKILL.md` 89 行、17 篇 `references/`、3 套模板（`simplefoam-minimal/`、`interfoam-minimal/`、`openfoam-parallel-slurm.sh`）。入口即 ``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md`-4` 的 YAML frontmatter（`name: hpc-openfoam` / `description: Generate, review, debug, and recover OpenFOAM case files ...`）。

### 1 输入形态

输入不是需求，是**触发条件**：宿主 agent 拿 ``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md`` 的 `description` 判断要不要加载本 skill；加载后按 ``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md`-21` 的 10 条编号清单逐篇读 references：

`1. Read \`references/case-setup.md\` before creating or editing any OpenFOAM case.` … `10. Read \`references/error-recovery.md\` for diagnostic commands, decision tree, and fix sequences.`

没有目录选择、没有参数、没有 case 目录约定——所有"输入"都是宿主 agent 的任务描述。

### 2 分层与模块边界

三层，无代码：
1. `SKILL.md`（89 行）：路由 + 工作序列 + guardrails + 交付物要求。**碰 LLM 的只有这一层的"被读"**。
2. `references/*.md`（17 篇 / 全仓 272 篇）：专题知识，一篇一主题（`mesh-quality-and-generation-guide.md`、`numerics-and-schemes-guide.md`、`error-recovery.md` …）。
3. `assets/templates/`：可整目录复制的 case 骨架（`simplefoam-minimal/` 7 个文件，带内联注释）。

唯一可执行层是 `skills/hpc-orchestration/scripts/`（4 个 argparse CLI，486 行：`hpc_job_submitter.py` 190、`hpc_job_monitor.py` 109、`hpc_log_tracker.py` 104、`hpc_slurm_deploy.py` 83），负责生成/提交 slurm 作业、盯日志。**不碰文件系统（除模板复制）、不跑仿真、不调 LLM。**

### 3 agent 拓扑

无 agent 拓扑。仓库定义的是"谁读谁"的协议：
- ``references/repos/hpc-skills/AGENTS.md:9` - Keep \`SKILL.md\` concise and move deep domain knowledge into \`references/\`.`
- ``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md` Follow a progressive loading workflow.`
- ``references/repos/hpc-skills/skills-index.md:1` # Skills Index`（仓库级目录，按 HPC 生命周期分组：Foundations / MPI / Toolchains / Spack / Orchestration / GPU / Meshing / …）

所谓"角色"完全由宿主决定（Codex / Claude Code / 其它 CLI agent，``references/repos/hpc-skills/README.md:27`-31` 列了三种兼容目标），仓库侧不定义 agent、不定义状态、不定义轮数。

### 4 工具接口

无 MCP、无 function calling、无工具注册。可执行面两类：
- 4 个 CLI 脚本（`hpc_job_submitter.py` 等，argparse，输出纯文本）。
- `assets/templates/*.sh` 里的 slurm 脚本骨架（如 `hpc-openfoam/assets/templates/openfoam-parallel-slurm.sh`），是给人/agent 复制后改的，不是被调用的工具。

对比同批其它项目：它的"接口"是**文件路径**——`SKILL.md` 里每个引用都是一条可直接 `read_file` 的路径（`:12-21`、`:27-30`、`:57-60`）。

### 5 知识来源

全静态文本，无 RAG、无 embedding、无索引、无向量库。检索 = SKILL.md 里的**手写路由表**：
- `## Start`（`:10-21`）：固定 10 步读取顺序。
- `## Scenario Recipes`（`:23-30`）：按任务类型映射到 1 篇 references（如 `multiphase-vof-recipes.md` 对应 `interFoam setup, alpha transport, MULES settings, maxAlphaCo, phase initialization (setFields), VOF boundary conditions`）。
- `## Additional References`（`:53-60`）：按需加载 4 篇。

知识颗粒度 = 一篇 references 一个主题；`hpc-openfoam` 的 17 篇覆盖 case 结构、solver 选择、BC、湍流、数值、网格、VOF、传热、函数对象、并行、错误恢复。

机制：路由是**人写的固定映射**，不依赖任何检索打分 → 收益：确定性、零安装、可 review；代价：路由错就是知识错，且没有任何兜底（对比 harnessfoam 的词袋检索至少会返回 top-k）。

### 6 错误处理与自修正

无自动重试、无自反思、无轮数。替代物是文本决策树：``references/repos/hpc-skills/skills/hpc-openfoam/references/error-recovery.md`` 逐字 `  ├── "FOAM FATAL ERROR" + patch name → missing/mismatched patch in field file`，同文件还有 `:130 --> FOAM FATAL ERROR:`、`:178 [0] FOAM FATAL ERROR: number of processor patches ... does not match` 等真实报错样本 + 处置。

是否重试、几轮、怎么回滚，全由宿主 agent 决定，仓库不写上限——这一点与 harnessfoam（3 轮 + 备份 + 账本）和 autofoam（3 轮 + dict_fix）形成对照：**它把"重试策略"整块留给调用方**。

### 7 它怎么知道跑成功了

**无判据实现（纯文本、无执行器）。它给的是判据清单，不是判据。**

- ``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md`-45`：`4. Validate mesh and numerics before a long run:` / `   - run \`blockMesh\` or the mesh generator` / `   - run \`checkMesh\` — non-orthogonality > 70° needs correctors, > 85° needs remeshing` / `   - start with conservative schemes (upwind), upgrade to linearUpwind after stability`
- ``references/repos/hpc-skills/skills/hpc-openfoam/references/validation-parallel-and-observability.md:14`-18`：`1. generate or import the mesh` / `2. run \`checkMesh\`` / `3. verify field files and patch names` / `4. verify \`fvSchemes\` and \`fvSolution\`` / `5. do a short dry-start or limited startup run before a long production run`
- ``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md`-89 ## Outputs`：要求交付物写 `- validation commands run or still needed` —— 即"跑了哪些验证"，但**没有一条要求贴判据输出或退出码**。

所以：它能指导人/agent 去检查什么（`Mesh OK.` 这一条它没有，只有 70°/85° 非正交阈值），但它自己不知道也不记录跑没跑成。按 R4 的标准，这份 skill 的输出只能是"自述"。

与 G1–G4 逐条对照：
- G1 结构：它有 `case-setup.md` 讲必需文件，但没有可执行清单。
- G2 网格：**它的 70°/85° 双阈值是我们缺的量化补充**；反过来说，它的清单里没有 `Mesh OK.` 这个逐字判据。
- G3 短跑：`:18` 的 `do a short dry-start` 就是我们的 G3 概念来源。
- G4 产物可读：未涉及。

### 8 部署依赖

- OpenFOAM：**无版本统一声明**。唯一版本字符串在模板：``references/repos/hpc-skills/skills/hpc-openfoam/assets/templates/simplefoam-minimal/README.txt` Minimal steady incompressible OpenFOAM-11 case scaffold.`；`SKILL.md` 同时给两代语法并让读者自己分支：`:37 - \`simpleFoam\` or \`foamRun -solver incompressibleFluid\`: steady incompressible`、`:49-51 - if \`simpleFoam\`/\`pimpleFoam\`/\`interFoam\` exists, it is valid to run directly` / `  - otherwise prefer \`foamRun -solver <moduleName>\` and verify the module loads`。
- Python：仅 orchestration 脚本用到（`subprocess`/`argparse`/`os`），无版本声明、无第三方包、无 requirements。
- 容器 / GPU / API key：无。
- 许可证：`LICENSE`（MIT，registry 记 `MIT`）。
- 体积：4 MB（`du -sm`），439 文件。

### 9 理论上优点 / 缺点

优点：
- 机制：`SKILL.md` 只做路由（89 行指向 17 篇 references），正文按需加载 → 收益：上下文成本≈任务相关那 1–3 篇，而不是整个知识库；代价：路由靠 description 语义匹配，错了没有检索兜底。
- 机制：两代语法并列 + 显式运行期分支（`:49-51`）→ 收益：同一 skill 在 legacy 与 `foamRun` 两种安装上都给得出可执行命令；代价：分支判断交给读者/宿主，宿主不判就退化成"两个都试"。
- 机制：guardrails 写成否定句（`:62-71`，如 `Do not invent dictionary keys, patch types, or solver names.`、`Do not use \`p\` when the solver expects \`p_rgh\` (buoyant/VOF), or vice versa.`）→ 收益：约束短、可逐条人工对照；代价：没有一条是可执行断言，无法自动判违规。
- 机制：模板是"带注释的最小 case"（`simplefoam-minimal/` 7 个文件）→ 收益：可整目录复制后改参数；代价：模板写的是 OpenFOAM-11，v13 已把 `constant/transportProperties`/`turbulenceProperties` 换成 `physicalProperties`/`momentumTransport`，直接复制会 FATAL（与我们 R1 那条"两代语法"坑同型）。

缺点：
- 机制：无执行器（§7）→ 代价："验证过了"只能是自述，违反 R4。
- 机制：22 个 skill 里只有 `hpc-openfoam` 一个直接对口 OpenFOAM（另有 `hpc-su2`/`hpc-gmsh` 与 CFD 相关但非 OpenFOAM，其余是 LS-DYNA/VASP/Gaussian/PETSc…）→ 代价：439 文件、272 篇 md 的体积，对本项目只有 `hpc-openfoam/` 一个目录有效，装载/审计成本与收益不成比例。
- 机制：无版本锚点（§8），模板停在 OpenFOAM-11 → 代价：不能作为 v13 的源码事实来源（R9 的边界），只能当"别人怎么写"的旁证。
- 机制：`skillization-roadmap.md`/`ecosystem-roadmap.md` 这类元文档与知识文档混在 references 里 → 代价：按"读 references 取知识"的协议，元文档会被当成知识读进来。

### 10 对本项目的可迁移点

可迁移：
- **渐进加载结构**：一个 ~89 行的路由 `SKILL.md` + N 篇单一主题 references。这正是 M3「把 5.1/5.2 链固化为 skill」该用的形态——我们的 skill 现在倾向写成长文，拆成"路由 + 专题"能直接降上下文成本。
- **`## Outputs` 要求写"validation commands run or still needed"**（`:83-89`）：比"只写结论"强，可加进我们的报告模板（与 R4"必须是命令输出"互补：R4 管证据，这条管"缺的证据要声明"）。
- **checkMesh 的 70°/85° 双阈值**（`:44`）：补进 G2 失败时的解释文本（不改变判定，改变报错可读性）。
- **"dry start before production"**（``references/repos/hpc-skills/skills/hpc-openfoam/references/validation-parallel-and-observability.md:18``）：我们的 G3 就是这个概念的严格化版本，可把它作为 G3 的出处引用。
- **两代语法的显式分支写法**（`:37`/`:49-51`）：我们 README §6 说 v13 主线是 `foamRun`、`applications/legacy/` 另有旧式可执行——把这条分支写成"先 `command -v`，再决定 runner"的判定，比在文档里说"注意两代语法"更可执行。

不可迁移：
- 22 个 skill 的多软件覆盖面：我们只做 OF v13，多覆盖只增审计面。
- OpenFOAM-11 模板：与 R11 冲突，不能进我们的模板库。
- 纯文本无执行器的形态：R4 要命令输出，纯文本给不了。
- `agents/openai.yaml`（每个 skill 一份 UI 元数据）：我们没有 Codex 式 UI 消费者。

---

## 10. chatcfd（docs_only：仅 README + arXiv 2506.02019，tier B）

### 0 一句话定位与规模

（依据：文档级，未读源码）

DeepSeek-R1/V3 双模型的多 agent 系统：输入论文 PDF 或自然语言 + 网格文件，输出可跑的 OpenFOAM case，带结构化 JSON 知识库、错误定位器与反思闭环。

规模：**未下载，代码行数未测**。registry 记 `size_mb=562`（GitHub 报 576098 KB），按 R10 超 100 MB 线，`mode=docs_only`、`local_path` 空。据 README 的目录树（`chatcfd README:264-298`）源码为 8 个 py：`src/chatbot.py`、`file_preparation.py`、`main_run_chatcfd.py`、`preprocess_OF_tutorial.py`、`qa_modules.py`、`run_of_case.py`、`file_corrector.py`、`config.py`，另有 `utils/`。入口两条，README 均给了命令：`chatcfd README:216 streamlit run src/chatbot.py --server.port ...`（Web，推荐）与 `chatcfd README:251 python src/chatbot.py --document_path ... --grid_path ... --run_time ...`（批处理）。README 取自 `gh api repos/tianhanz/ChatCFD/readme`（base64 解码后 355 行，下文行号按此编号）。

### 1 输入形态

（依据：文档级，未读源码）

三件套：① 描述文档（PDF/TXT，可以是论文全文）；② 自然语言指令；③ 网格文件（README 说支持 Fluent `.msh`，OpenFOAM 原生网格需给 `polyMesh` 目录路径）。README:36-38 三步：`1. **Input Description:**` / `2. **Mesh Provision:** Users provide the corresponding mesh file (supporting OpenFOAM or Fluent formats).` / `3. **Automatic Configuration:**`。

中间有一步人机交互选择：系统从文档里抽出多个 case（`Case 1, Case 2`…），用户选定后再确认 solver/湍流模型/边界条件（paper §2.2 `Case Selection: Through natural language interaction, the system guides users to select a target case, provides detailed specifications for verification, and confirms the selection.`）。这一步与我们 R8「缺参数停下问」同构，但触发点是"文档里有多个 case"，不是"参数缺失"。

### 2 分层与模块边界

（依据：文档级，未读源码）

按 README 目录树 + 论文 §2 的 Stage 划分：

| 层 | 文件 | 职责 | 证据 |
|---|---|---|---|
| 输入层 | `src/chatbot.py` | Streamlit 对话 + 文档上传 + 网格上传 | README:286 `Main chatbot script, implements the conversational interface and user interaction` |
| 预处理/知识库 | `src/preprocess_OF_tutorial.py` | 把 tutorial 解析成 JSON 库 | README:289 |
| 编排 | `src/main_run_chatcfd.py` | 串 Stage 1–4 | README:288 `coordinates the entire CFD automation workflow` |
| 生成 | `src/file_preparation.py` | 写 case 文件 | README:287 |
| LLM 交互 | `src/qa_modules.py` | R1/V3 调用 + token 统计 | README:290 |
| 执行 | `src/run_of_case.py` | 跑算例（PyFoam） | README:291 |
| 纠错 | `src/file_corrector.py` | 定位并修配置错 | README:292 |
| 数据 | `database_OFv24/*.json` | 结构化知识库（db1–db4） | README:269-274 |

论文把流程切成 5 个 stage（paper §2）：Stage 0 知识库构建、Stage 1 用户输入处理、Stage 2 case 文件生成（三 phase）、Stage 3 纠错与反思、Stage 4 后处理（Physics Interpreter）。**碰 LLM 的层是 Stage 2/3/4；碰文件系统的是 file_preparation/file_corrector；跑仿真只有 run_of_case 一个入口**——这一点比 deepflow 干净（deepflow 让 LLM 自己发 shell 命令）。

### 3 agent 拓扑

（依据：文档级，未读源码）

双模型**角色分工**而非独立 agent 进程：同一个 pipeline 里按任务难度选 R1 或 V3。

- R1 负责：Stage 2 抽取参数与生成初版文件、Stage 3 定位错误文件、提修改方案、持久错误时做反思（paper §2.6 `In Stage 2, it extracts critical simulation parameters ... In Stage 3, it pinpoints error-causing files, proposes detailed correction strategies, and conducts reflection on persistent errors.`）。
- V3 负责：Stage 2 文件结构快速校验、Stage 3 挑"可疑文件"、按指令生成修正后的文件内容（paper §2.6 `In Stage 2, it performs quick file structure validation, while in Stage 3, it identifies suspicious or missing files and generates corrected file content based on provided instructions.`）。

模块清单（paper §2.4）：`ReferenceRetriever`（取 2 个参考文件）、`ContextRetriever`（把当前配置和修改轨迹打包成 JSON）、`Error Locator Module`（V3 粗筛 + R1 精定位）、`Error Correction Module`（V3 找联动文件 → R1 出改法 → V3 落格式）、`Reflection Module`（持久错误时生成 `<reflexion>` 反思块）。

传输格式：结构化 JSON（`ContextRetriever` 把配置编成 JSON）+ `<reflexion>` 标签包裹的反思块（paper §2.4 `These reflections are stored as reflection blocks within a <reflexion> tag in the reflection history`）。反思是否带工具调用协议，文档未写。

### 4 工具接口

（依据：文档级，未读源码）

**未公布工具清单。** 论文摘要只说 `ChatCFD's modular, MCP-compatible design directly enables collaborative multi-agent networks`——"MCP-compatible"是设计主张，不是接口文档；README 也没有 tool 名列表。可以确认的"能力"只有三个：正则 + `pyFoam` 抽边界名（paper §2.3.2 `Boundary names and types are extracted via regular expressions and tools like pyFoam`）、`file_corrector.py` 改文件、`run_of_case.py` 跑算例。工具名与注册处**未确定**（需读源码，本阶段不做）。

### 5 知识来源

（依据：文档级，未读源码）

两层知识库（paper §2.1 + README:269-274）：

1. **结构化 JSON（主）**，四个库：
   - `db1` File Dependency and Structure DB：按 solver × 湍流模型存"需要哪些文件"（paper §2.1 `This model is based on OpenFOAM tutorial cases and categorized primarily by solver type and turbulence model to store the necessary file structure for specific combinations.`）。
   - `db2` Boundary Condition DB：每种 BC 需要哪些附加关键字。
   - `db3` Parameter Dimension DB：各物理量的量纲规则与一致性约束。
   - `db4` Solver Template DB：tutorial case 的核心文件全文 + 元数据（solver / 湍流模型 / 物理类别）。消融实验里"去掉 db4 准确率掉到 48%"（paper 摘要 `removing the Solver Template DB collapses accuracy to 48%`）。
2. **向量库（辅）**：嵌入模型 `all-mpnet-base-v2`（README:151 `Download the embedding model all-mpnet-base-v2 required by ChatCFD.`），检索服务 FAISS-CPU 1.7.4（README:91 `FAISS-CPU 1.7.4 (for vector similarity search)`）。切块参数只公开了一个：`pdf_chunk_d` 默认 `1.5`（README:205，语义未在 README 说明，推测为 PDF 切块尺度——**未确定**）。检索时用 sentence-transformer 相似度 + 阈值过滤描述分块（paper §2.3.2 `user prompts enable filtering of segmented case description chunks using the sentence-transformer/all-mpnet-base-v2 library and a similarity threshold`），阈值数值未公布。参考文件数固定为 2（paper §2.4 `two reference files are selected to aid error detection and correction`）。

机制：**结构化库优先于向量库**——文件依赖、BC 关键字、量纲这类"必须有唯一答案"的信息走 JSON 查表，散文式背景才走向量检索。这个分工正是 db4 消融掉 48% 的原因：模板库提供的是"骨架"，LLM 只填肉。

### 6 错误处理与自修正

（依据：文档级，未读源码）

三层闭环，轮数上限在配置里：

- 通用错误（占运行时错误 70%+，paper §2.4 `These, comprising over 70% of runtime errors, include incorrect keywords, formatting issues, or floating-point errors.`）：V3 找可疑文件 → R1 确认 → ReferenceRetriever 取参考 → 出改法 → 改文件。
- 缺文件错误：V3 直接用参考 case 生成缺失文件，再做量纲校验（paper §2.4 `For missing file errors, DeepSeek-V3 directly generates the required file using reference cases, followed by dimensional validation`）。
- 持久错误：短期记忆（近期报错 + 修改轨迹）+ 长期记忆（反思历史）→ 生成 `<reflexion>` 块。
- 上限：`max_running_test_round` 默认 `30`（README:204 `"max_running_test_round":30,`）。论文另给一条经验界：反思超过上限 75%（约 22 轮）后基本修不好（paper §3.1 `reflections beyond 75% of the limit (approximately 22 iterations) often fail to resolve remaining errors`）。

注意"重试"的粒度是**跑一次 + 改一次**，不是"改完不跑直接再改"——所以每轮都有一次 solver 启动成本（这也是它平均 192.1k token/例的主要来源之一，paper 摘要 `an average of 192.1k tokens and $0.208 per case`）。

### 7 它怎么知道跑成功了

（依据：文档级，未读源码）

论文给了两个层次的定义，**都不是代码级门禁**：

1. **执行成功（run）**：paper §3.1 逐字 `Success is defined as the generation of error-free case files leading to converged simulations.` 即"文件无错 + 跑到收敛"。但论文没写"收敛"怎么判——是看 `Solver converged` 标记、残差阈值、还是最后时间步，**未确定**（需读源码）。
2. **物理保真（phy√）**：paper §3.2 的三级人工协议，逐字 `We define physical fidelity through a three-tier protocol. A case qualifies only if it meets all criteria without simplifications ...: Conditions Verification / Model Confirmation / Flow Feature Comparison`——这是**人工评审**（对比边界条件是否吻合描述、模型参数是否合适、可视化流场是否与 ground truth 一致），不是自动判据。

数字：README:306 `- **Execution Success Rate (run):** 82%`、README:308 `- **Physical Fidelity (phy√):** 59%`；论文摘要给 82.1% / 68.12%（两个 phy 数字口径不同，README 记 59%，论文摘要记 68.12%——**存疑，可能是 phy|run 与 phy 整体两个口径**，论文 §3.2 明确讨论过 `ChatCFD's physical fidelity rate among runnable cases (phy|run) is lower than Foam-Agent's, but its overall rate is higher`）。

值得本项目直接引用的一句（paper §3.2）：`Such misconfigurations rarely trigger convergence failures, allowing apparent success that misleads agents.` —— 这正是"退出码 0 ≠ 成功"的另一份实证，且它指出的失效面（边界条件/初始场错但能收敛）恰在我们 G1–G4 覆盖之外。

对 G1–G4 的映射：run 判据≈G1+G3（结构 + 跑通），phy 判据≈G4 的语义版但需人工；G2（`Mesh OK.`）它靠"用户提供网格"绕过；没有任何一条 G 是它对我们的增量。**论文未报告可复用的自动门禁实现**，只有评测口径。

### 8 部署依赖

（依据：文档级，未读源码）

- OpenFOAM：**v2406**，且是硬绑定。README:75 `- OpenFOAM v2406. If other versions of OpenFOAM are used, files like \`processed_merged_OF_cases.json\` in \`database_OFv24\` may become incompatible, affecting ChatCFD's performance.`；README:81 表格同义强调 `⚠️ Recommended version is v2406. Using other versions will lead to a mismatch with pre-built knowledge base files`。装法用 openfoam.com 的 Debian 源（README:175 加源、README:179 `sudo apt-get install openfoam2406-default`）。
- Python 3.11.4，且明确避开 3.12（README:74 `it is best to avoid Python 3.12 as this version may cause unknown issues when using PyFoam during direct execution.`）。
- 关键包（README:86-108 列表）：PyTorch 2.6.0、Transformers 4.50.3、Sentence-Transformers 4.0.1、FAISS-CPU 1.7.4、Scikit-learn 1.6.1、NumPy 1.26.4、Pandas 2.2.3、Streamlit 1.41.1、OpenAI 1.39.0、LangChain 0.1.19、PDFPlumber 0.11.5、PyPDF2 3.0.1、PDFMiner.six 20231228、**PyFoam 2023.7**（唯一直接耦合 OF 内部文件格式的依赖）。环境用 `chatcfd_env.yml` 锁（README:126 `conda env create -f chatcfd_env.yml`）。
- API：DeepSeek-V3 + DeepSeek-R1 两套 key/base_url/model（README:192-207 的 `chatcfd_config.json`），温度分别 0.7 / 0.9（README:196/200）。
- GPU：可选（README:76 `- CUDA-enabled GPU (Optional, but recommended for better performance).`），主要给 sentence-transformer。
- 容器：无 docker 说明。
- 对本项目：v2406 + PyFoam + 562 MB 预建库三者叠加，按 R11 不可能在本机 v13 上跑通；只能做静态对照。

### 9 理论上优点 / 缺点

（依据：文档级，未读源码）

优点：
- 机制：四张结构化 JSON 表（文件依赖 / BC 关键字 / 量纲 / solver 模板）+ 向量库只做辅助（paper §2.1）→ 收益：文件清单、量纲、BC 关键字这类"有唯一答案"的事不交给 LLM 猜，消融显示去掉模板库准确率从 82% 掉到 48%；代价：库绑定 v2406，换版本即全库失效（README:81 明说）。
- 机制：错误定位器拆成"V3 粗筛 + R1 精定位"（paper §2.4）→ 收益：便宜模型承担筛选、贵模型只做定位，token 成本被摊薄（平均 192.1k/例，约为 Foam-Agent 的一半）；代价：两级都错时没有第三方仲裁，只剩"改错文件"。
- 机制：反思写成 `<reflexion>` 结构化块并进历史（paper §2.4）→ 收益：跨轮信息是"结论+下一步"而不是原始日志堆，长上下文里衰减慢；代价：反思一旦错（模型自我归因错误）会被后续轮复用，错误被固化。
- 机制：无量纲字段用占位符替换非均匀场数据（`__CELL_COUNT__`/`__FACE_COUNT__`/`__SCALAR_DATA_PLACEHOLDER__`，paper §2.1）→ 收益：模板能进上下文，可用 case 数不被场数据挤掉；代价：模板里真实的分块数据不可见，若错误恰在 `nonuniform` 段就无从参考。

缺点：
- 机制：整个知识库按 v2406 预生成并随仓分发（`database_OFv24/*.json`）→ 代价：版本迁移成本=重建全库，而重建脚本 `preprocess_OF_tutorial.py` 的正确性本身没有判据。
- 机制：物理保真靠人工三级评审（paper §3.2）→ 代价：82% 的"run 成功"与 59%/68% 的"物理保真"之间那条 20+ 个百分点的缝，任何自动流水线都测不出来；论文自己承认 `Such misconfigurations rarely trigger convergence failures, allowing apparent success that misleads agents.`
- 机制：反思上限 30 轮 × 每轮一次 solver 启动（README:204）→ 代价：难 case 的成本是线性的，论文实测 22 轮后基本无收益（§3.1），即后 8 轮是纯浪费。
- 机制：依赖 PyFoam 读 OF 内部格式（README:108）+ Python 3.11 硬约束（README:74）→ 代价：OF 版本与 Python 版本任一变动都可能同时破库和破解析，失败面耦合。

### 10 对本项目的可迁移点

（依据：文档级，未读源码）

可迁移：
- **"文件依赖表 + BC 关键字表 + 量纲表"三张表**的存在形式：这是 harnessfoam `solver_requirements`（`references/repos/harnessfoam/harnessfoam/validation.py:63`–74）的完整版。我们的 G1 可以升级成"solver × 模型 → 必需文件集合"，量纲表则可作为 G1 的一条静态检查（`0/p` 的 `dimensions` 与 solver 类型是否一致）——两者都是纯文本、零执行成本。
- **"占位符替换非均匀场"**（§2.1）：如果 M2 要把 tutorial 塞进上下文，这是省 token 的标准手法；我们 R3 要求从 tutorial 派生，派生时可以保留非均匀段、只对"喂给 LLM 的副本"打占位符。
- **`<reflexion>` 结构化反思**：比"把最后 40 行日志丢回去"（autofoam 的做法）更省上下文，且可落盘成可审文件（对应我们缺的"第几轮改了什么"）。
- **论文那句失效面结论**（`Such misconfigurations rarely trigger convergence failures, allowing apparent success that misleads agents.`）：可直接引到我们 README §6 的"checkMesh 通过 ≠ 物理正确"旁边，作为外部证据。

不可迁移：
- v2406 + PyFoam + 预建 `database_OFv24` 的组合：R11 禁第二份 OF，且库与版本死绑。
- 双模型（R1 推理 + V3 执行）的成本结构：需要两个 API key 与调度逻辑，我们单模型 + grep 的路径没有这个必要。
- "MCP-compatible"的对外协议面：论文只给主张，没有接口规范，抄不到实现。
- 562 MB 的随仓知识库形态：与 R10 体积线直接冲突。

---

## 11. openfoamgpt（docs_only：仅 arXiv 2501.06327，无官方仓库，tier C）

### 0 一句话定位与规模

（依据：文档级，未读源码）

论文级系统：Builder / Executor / Interpreter+Builder+Runner 的分层 agent，RAG 提供 tutorial 案例做 few-shot，错误日志回灌用户 query 形成迭代闭环；模型是 GPT-4o 与 o1-preview。

规模：**无代码可测**。registry 记 `kind=paper`、`size_mb=0`、`local_path` 空；GitHub 只有第三方网站页（`YupengQI99/openfoamgpt-website`），无官方仓库。本节的"规模"只能是论文的实验规模：6 个 case（cavity / PitzDaily / hotRoom / damBreak / particle column / mixed vessel，paper §III.1）、两档模型、两种模式（zero-shot / RAG few-shot）。

入口：论文未给命令行；流程起点是"系统提示 + 用户 query 进 Builder"（paper §II `At the top, a system prompt is combined with a user query.`）。

### 1 输入形态

（依据：文档级，未读源码）

自然语言 query，可选附 `blockMeshDict` 文件。paper §III.1 逐字：`Providing a blockMeshDict file as part of the input is therefore more effective.`——论文实测"只给自然语言时，4o 只会做 cavity 这种二维方腔，o1-preview 能多做 hotRoom，但复杂几何仍失败"（Table 1 里 PitzDaily/Dambreak/Mixed vessel 在三个模型下都标 `blockMeshDict incorrect`）。

所以它的输入契约实际上是"自然语言 + 一个手写网格字典"，与我们 R5（blockMesh 或导入外部网格）同构，但它没有"从 tutorial 派生"这一步。

### 2 分层与模块边界

（依据：文档级，未读源码）

paper §II 逐字描述四层：`At the top, a system prompt is combined with a user query. The Builder module then interprets these instructions—consulting the RAG database as needed for domain-specific information—and transforms them into a structured plan. Next, the Executor orchestrates the workflow: it can direct the query to the LLM model for further reasoning or hand off tasks to the OpenFOAM agent for simulation-specific actions. Inside the OpenFOAM agent, an Interpreter, Builder, and Runner collaborate to set up and execute the necessary OpenFOAM operations.`

即：
| 层 | 职责 | 是否碰 LLM |
|---|---|---|
| 系统提示 + query | 输入 | 否 |
| Builder（外层） | 生成结构化 plan，可查 RAG | 是 |
| Executor | 路由：回 LLM 还是交 OpenFOAM agent | 是（判断） |
| OpenFOAM agent 内 Interpreter | 解释 OF 侧语义 | 是 |
| OpenFOAM agent 内 Builder | 写字典 | 是 |
| OpenFOAM agent 内 Runner | 跑命令、收日志 | 否 |

"Runner 是否只是 subprocess 包装"论文没写，**未确定**。整体特征是"同一套 Builder 逻辑在两层复用"（外层出 plan、内层出字典）。

### 3 agent 拓扑

（依据：文档级，未读源码）

planner-executor 双层，不是多角色并行：
- 外层 Builder → Executor（路由）→ 内层 OpenFOAM agent（Interpreter → Builder → Runner）。
- 闭环：Runner 之后监控错误日志，失败则把错误数据**追加到用户 query**再迭代（paper §II `Throughout the simulation, error logs are monitored; if a failure is detected, the error data is appended to the user query and the process iterates. Otherwise, the workflow concludes successfully.`）。
- 传输格式：论文只说"structured plan"，未给 schema；错误上下文以"追加到 query 的文本"形式传递（不是结构化对象）。

### 4 工具接口

（依据：文档级，未读源码）

**未公布工具清单**（无 tool 名、无 MCP、无函数签名）。论文只提到 Runner "执行 OpenFOAM 操作"（paper §II `hand off tasks to the OpenFOAM agent for simulation-specific actions`），以及 RAG 以"查库"形式被 Builder 调用。工具名与注册方式**未确定**。

### 5 知识来源

（依据：文档级，未读源码）

单一 RAG，无结构化表、无微调：
- 语料：`A dedicated RAG database—derived from OpenFOAM tutorial case descriptions—provides relevant details such as solver names, case names, and flow types.`（paper §II）
- 嵌入：`These descriptions are embedded into 1536-dimensional vectors via OpenAI's text-embedding-3-small model`（paper §II）
- 框架：`It is implemented through the LangChain framework`（paper §II）
- 检索方式：few-shot 把检索到的案例当示例拼进 prompt（§III.2 标题即 `Few-Shot Prompting with RAG`）；top-k、chunk 大小、相似度阈值**论文均未给**。
- 论文自己报了 RAG 的一个硬限制：`the output of kinematicCloudProperties is different from the file provided in RAG because the output file has a length limit`（§III.2）——即检索回来的文件被截断，导致 particle column 那例的复制不完整。

### 6 错误处理与自修正

（依据：文档级，未读源码）

有，但是**单层循环 + 错误文本回灌**，无反思、无分层定位：
- 触发：Runner 之后的日志监控发现失败（paper §II）。
- 上下文：错误数据直接追加到用户 query（`the error data is appended to the user query and the process iterates`）。
- 轮数：论文未给上限，只报实测次数（Table 2）：4o 从 cavity 的 2 轮到 particle column 的 10 轮；o1-preview 从 1 轮到 9 轮。
- 成本：4o 每例 $0.03–$0.36，o1-preview 高到 $1.65（Table 2 的 particle column `1.6475`）。

机制：没有"定位到哪个文件"这一步 → 收益：不需要文件依赖表，实现最薄；代价：每轮都把整份错误文本塞回 query，模型要自己重新判断错在哪个文件，粒度和 token 都不受控（论文 Table 2 的 token 从 6.6k 到 96k，跨度 14 倍）。

### 7 它怎么知道跑成功了

（依据：文档级，未读源码）

**论文未报告独立成功判据。**

论文只写了循环的退出条件（paper §II）：`Throughout the simulation, error logs are monitored; if a failure is detected, the error data is appended to the user query and the process iterates. Otherwise, the workflow concludes successfully.` —— "没有检出失败 → 结论成功"。

未报告的部分（逐条都是缺口）：判"failure"用什么（退出码？`FOAM FATAL`？正则？）、判"success"要不要收敛/完成标记/场文件、有没有物理量范围、Table 1 的 ✓/× 是人工判还是自动判。因此按本批模板的要求：**论文未报告独立成功判据，只有循环退出条件**；论文也明确把正确性责任留给人（§IV `a measure of human oversight remains critical to ensure correctness`）。

补充一条可用的旁证：Table 1 的失败原因标注是"哪个文件错"（如 `blockMeshDict incorrect`、`transportProperties incorrect`、`0 incorrect`、`kinematicCloudProperties incorrect`），说明评测时是人/作者去看文件判断的，不是 runner 判的。

### 8 部署依赖

（依据：文档级，未读源码）

- OpenFOAM：**v2406**。paper §II 逐字 `The version we use here is OpenFOAM-v2406 release.`
- 模型：OpenAI `gpt-4o` 与 `o1-preview`，走 OpenAI API（paper §II `each accessed through the OpenAI API`）。
- 成本口径（论文给的价目，用于其成本表）：4o `$2.50 per million input tokens and $10 per million output tokens`，o1 `$15.00 per million input tokens and $60 per million output tokens`（paper §II）。
- 嵌入：`text-embedding-3-small`（OpenAI API）。
- 框架：LangChain（paper §II）。
- Python 版本、第三方包清单、docker、GPU：**论文均未提**（无 GPU 需求，全走 API）。
- 对本项目：v2406 + OpenAI API 两处都不可满足于本机（R11 / 无外网 key 的默认环境），只能做静态对照。

### 9 理论上优点 / 缺点

（依据：文档级，未读源码）

优点：
- 机制：RAG 只做 few-shot 示例、不做结构化约束（paper §II）→ 收益：实现最薄，加一个子领域只需换语料（`by further extending the knowledge base ... our general-purpose CFD agent can be seamlessly adapted`）；代价：示例被截断即失真（§III.2 报的 `kinematicCloudProperties` 长度限制），且没有"必须有某文件"的硬约束兜底。
- 机制：错误文本整段回灌 query（§II）→ 收益：不需要错误分类器、不需要文件定位器，任何新报错都能进循环；代价：每轮上下文线性膨胀，token 跨度实测 14 倍（Table 2：6.6k→96k），且模型每轮都要重新定位。
- 机制：双层 Builder（外层出 plan、内层出字典），Executor 只在两者间路由（§II）→ 收益：plan 与实现分离，可单独替换其中一层；代价：两层都用同一族模型，错误会一致地犯（论文 §III.1 三个模型都把 PitzDaily 的 blockMeshDict 写错）。
- 机制：同时跑 4o 与 o1 两档（Table 1/2）→ 收益：给出"贵模型是否值得"的实测（o1 成本约 6 倍，只多解出 hotRoom 一例）；代价：结论随模型版本漂移，论文自己也提醒 `fluctuations in model performance over time ... users must carefully monitor this change`（§IV）。

缺点：
- 机制：无独立成功判据（§7）→ 代价：Table 1/2 的 ✓ 与"iterations"只能是人工判断，复现时无法区分"跑通"与"看起来跑通"。
- 机制：无文件级错误定位（对比 chatcfd 的 Error Locator）→ 代价：错误回灌整段文本，模型反复在多个文件间试，轮数与 token 不可控。
- 机制：RAG 语料是"tutorial case 描述"且输出有长度限制（§III.2）→ 代价：长文件（如 `kinematicCloudProperties`）永远被截断，这类 case 无论重试多少轮都拿不到完整参考。
- 机制：仅 6 个 case、单一 OF 版本、单一 API 供应商（§III.1）→ 代价：结论外推性受限，尤其对多物理耦合（particle column 是唯一未解出的）。

### 10 对本项目的可迁移点

（依据：文档级，未读源码）

可迁移：
- **"错误文本整段回灌 + 无上限重试"作为反例**：它证明最薄的闭环能跑通 5/6 个 case，但也把 token 从 6.6k 拉到 96k；我们的 G3 失败后应做的是"定位文件 + 有限轮"（harnessfoam / autofoam 的做法），而不是整段回灌。
- **"输入附 blockMeshDict 比纯自然语言更有效"**（§III.1）：这是我们 R3/R5 的外部佐证——几何字典让模型别猜（注意这不是同一臂的对照：纯自然语言最好成绩是 4o 的 1/6，附 blockMeshDict 后 o1-preview 到 5/6，中间同时换了模型；论文原话：`After supplying a detailed blockMeshDict file, the agent with o1 demonstrates improved performance: even without RAG, it successfully handles the Cavity flow, PitzDaily, Hotroom, Dambreak, and Mixed vessel cases.`）。
- **双层 Builder 的 plan/实现分离**：对应我们"先出文件清单（G1 的输入）再写文件"的顺序；chatcfd 的 db1 与 harnessfoam 的 `plan` 是同一思路的两种实现。
- **成本口径写法**：论文把 token 与美元单价一起给（§II），我们的 `bench/results.csv` 有 `tokens_total` 但没单价列；若要跨项目比成本，需要同时冻结价目表。

不可迁移：
- 纯 API 依赖（OpenAI 4o/o1 + text-embedding-3-small）：不可复现（模型会下线/漂移），与 R12「结果要能重算」冲突。
- v2406 目标版本：R11。
- 无判据的闭环形态（§7）：R4 直接禁止。
- RAG 语料随附（tutorial 描述 + 截断输出）：它自己报了失真，不值得抄。

---

## 本批汇总矩阵

| 项目 | 拓扑 | 工具接口 | 知识来源 | 有无自修正 | 成功判据类型 | tier | 部署强依赖 |
|---|---|---|---|---|---|---|---|
| harnessfoam | LangGraph 9 节点 / 6 LLM 角色 | 双 MCP（8 tool + 11 tool）+ REST | 词袋检索：7 条硬编码 + 20 文件名白名单 tutorial（块=文件，前 6000 字符，k=4） | 有：3 轮 + 目录备份 + `failure_ledger.jsonl` | 退出码 + 日志 5 判据（FATAL／`End`／Time 步数／`Version: 13`／Courant）+ cavity 5 阈值；**无 `Mesh OK.`** | A | OF 13 + WSL + LLM API key |
| autofoam | 单 agent 8 段流水线（无框架） | 无（CLI + Python API + gradio） | Chroma + `bge-small-en-v1.5`，按文件角色切 5 类块，`n_results=3`；1276 行字典模板 | 有：3 轮 + FATAL 单文件 `dict_fix` + 立即重跑 | 加权分数 ≥0.5（网格串／退出码／收敛标记／残差／守恒／solver 自洽／BC 字面） | B | OF v2412 + 本地 14B + ≥24 GB GPU + HF 私有权重 |
| deepflow | 单 ReAct（LangChain `AgentExecutor`） | 11 个 `@tool`（实际可见 10）+ 1 retriever | FAISS + `text-embedding-3-small`，`chunk_size=1000/overlap=200`，默认 k | 无 | **无独立判据**（LLM 读 `--- Exit Code: N ---`） | B | OF v2412 + OpenAI 兼容 API |
| hpc-skills | 无 agent（宿主驱动，渐进加载） | 无（4 个 argparse CLI + 模板文件） | 272 篇 md，手写路由表（无检索、无索引） | 无 | **无实现**（只给判据清单：checkMesh 70°/85°、dry-start） | A→B | 无（纯文本，4 MB） |
| chatcfd | 多 agent 双模型（R1 推理 / V3 执行） | 未公布（自称 MCP-compatible） | 结构化 JSON db1–db4 + FAISS `all-mpnet-base-v2`（`pdf_chunk_d=1.5`，参考文件固定 2 个） | 有：≤30 轮（反思 <reflexion>） | 论文定义"无错文件 + 跑到收敛"；物理保真为人工三级评审（README 59% / 论文 68.12%，两口径） | B | OF v2406 + DeepSeek R1/V3 API + PyFoam |
| openfoamgpt | planner-executor + 内层 agent | 未公布 | RAG（1536 维 `text-embedding-3-small`，tutorial 描述，LangChain） | 有：错误回灌，实测 1–10 轮 | **论文未报告独立成功判据**（只有循环退出条件） | C | OF v2406 + OpenAI API（4o / o1-preview） |

## 本批 tier 修正与存疑

1. **hpc-skills：tier A → B。** 依据：唯一版本声明是模板里的 OpenFOAM-11（`references/repos/hpc-skills/skills/hpc-openfoam/assets/templates/simplefoam-minimal/README.txt:1 Minimal steady incompressible OpenFOAM-11 case scaffold.`），`SKILL.md` 本身两代语法并列、不做版本断言（``references/repos/hpc-skills/skills/hpc-openfoam/SKILL.md``、`:49-51`）；registry 把它记 A 的理由是"纯 skill 文本集（20 个 hpc-* skill）"，那是**形态**判断不是版本判断。它是本批唯一"内容对我们有价值、但版本目标不是 v13"的项目，按本批 A/B 的用法（A=可直接对标本机 v13）应为 B。
2. **registry `hpc-skills` 的 note 与实测不符（数字修正，不改 tier）。** note 写 "20 个 hpc-* skill"，实测 `ls references/repos/hpc-skills/skills | wc -l` → **22**：求解器型 14 个（calculix/elmerfem/fenics/gaussian/gromacs/hypre/lammps/ls-dyna/openfoam/petsc/quantum-espresso/su2/trilinos/vasp），基础设施型 8 个（foundations/mpi/toolchains/spack/gpu-stack/orchestration/paraview/gmsh）。registry 的 "20" 无论按哪种切分都对不上（22 / 14 / 8 三个数都不是 20）。后续引用应以 22 为准。
3. **harnessfoam 许可证存疑（不改 tier）。** registry 记 `license=none(无 LICENSE 文件)`，实测 `ls references/repos/harnessfoam/LICENSE*` → No such file；但 README:14 有 MIT badge、`pyproject.toml` 有 `classifier = "License :: OSI Approved :: MIT License"`。三者不一致，按最保守（无许可文件）处理，引用其代码时需注明。
4. **harnessfoam 的 README:100 与实现不符其字面（不改 tier，但影响 §7 结论）。** README 说 "Each generated case receives `.harnessfoam/manifest.json`; solver logs must confirm OpenFOAM Version 13"，实际 manifest 里的版本是常量（``references/repos/harnessfoam/harnessfoam/case_manifest.py:8`/:22`），日志确认在 ``references/repos/harnessfoam/harnessfoam/validation.py:134``（由 ``references/repos/harnessfoam/harnessfoam/agents/graph.py:271`` 传参）；`parse_openfoam_version`（``references/repos/harnessfoam/harnessfoam/case_manifest.py:45``）除测试外无调用。**若按 README 字面理解"看 manifest"，会得到错误的实现模型。**
5. **autofoam 的 solver 表口径（不改 tier）。** README:53 自称 `# deterministic 7-solver rule table`，实测 ``references/repos/autofoam/openfoam_agent/solver_selector.py:6`-19` 有 8 个返回值（interFoam、rhoPimpleFoam、rhoSimpleFoam、buoyantPimpleFoam、buoyantSimpleFoam、icoFoam、pimpleFoam、simpleFoam）。按实测 8 处理。
6. **deepflow 依赖声明不自洽（不改 tier，但影响可运行性判断）。** `requirements.txt` 8 行内无 `faiss-cpu`（`grep -in faiss requirements.txt` 无命中），而 ``references/repos/deepflow/deepflow_agent/openfoam_agent.py:16`` 导入 `langchain_community.vectorstores.FAISS`；RAG 失败被 `:334` 静默吞掉。**"照 README 装完即有 RAG"是错的。**
7. **chatcfd 与本地 cfd-agent 同源——未确定。** registry note 写"代码疑似与 woog97/cfd-agent 同源，待核实"。本批按 docs_only 约定只读 README 与论文，未读 cfd-agent 源码，故**未确定**；下阶段可用一次字符串比对判定（例如比对 `max_running_test_round` 与 `database_OFv24` 两个标识是否同时出现在 cfd-agent 树里），但那属 batch 1 的范围。
8. **chatcfd 物理保真数字两口径——存疑。** README:308 记 `Physical Fidelity (phy√): 59%`，论文摘要记 68.12%；论文 §3.2 明确区分 `phy|run`（仅可运行 case 内）与整体 phy。两者可能分别是 phy|run 与整体 phy，**未确定**对应关系；引用时应写清口径。
9. **chatcfd / openfoamgpt 的代码实现层整体未确定。** 按 R10 docs_only 约定，两项目的"工具接口、判据实现、重试上限落地方式"均无源码证据，只能标"文档级"。凡本文件把这两项写成具体实现的段落，均已在节末标 `（依据：文档级，未读源码）`，且不含推测性代码描述。
10. **本批未改动任何 `references/repos/` 下文件**（只读）；未运行任何被测代码、未运行任何 OpenFOAM 命令、未安装软件。全部 OF 侧事实来自 `grep /opt/openfoam13`（见 §6.7 的 grep 命令与输出）。

---

## 合并与校验记录（编排方填写，不是子代理自述）

| 检查 | 命令 | 结果 |
|---|---|---|
| 引用格式规范化 | 合并脚本按 `## N. <pid>` 分段补全路径；尾节用全库唯一匹配 + 显式覆盖 | part1：新补 147 条、原已规范 84 条、显式覆盖 11 条；part2：新补 143 条、覆盖 11 条、原已规范 1 条 |
| 每条 path:line 回切真实文件 | `bash scripts/verify_references.sh` 的 G-DOC-1（逐条 `os.path.isfile` + `wc -l` 比行号） | **checked=314（去重后的 distinct 引用；含重复共出现 397 次）violations=0**。另 2 条 `$FOAM_SRC/...` 引用按 R1 单独核，见下两行 |
| 裸文件名引用清零 | 判定「token 前不含 `/`」 | 终态 `bare: []`（合并前 part2 有 155 条裸引用，全部补全） |
| 小节完整性 | `grep -c '^### '` | part1 = 55，part2 = 66（11 项目 × 11 小节） |
| 参考库未被改动 | `git -C references/repos/<r> status --porcelain` | 空（R9）；`scripts/verify_references.sh` G-R9-1 checked=9 violations=0 |
| OpenFOAM 源码引用（R1） | `sed -n '78,88p' $FOAM_SRC/OpenFOAM/db/IOobject/IOobjectI.H` | 第 83 行确为 `Version:  " << FOAMversion`，与 harnessfoam 版本断言一致 |
| 同上 | `sed -n '650,660p' $FOAM_SRC/OpenFOAM/global/argList/argList.C` | 第 655 行确为 `IOobject::writeBanner(Info, true)` |

### 合并时发现并修掉的 1 条编造

part1 的 nullflux §8 原文声称「`start.sh` 设 `--max-old-space-size=4096`（`start.sh:12`）」。实测：

```bash
$ ls references/repos/nullflux
README.md  server.js  cfdriver-linux-sealed.tar.gz
cfdriver-v10.0.0-linux-sealed.tar.gz  nullflux-linux-sealed.tar.gz  docs/
$ grep -rn "max-old-space-size" references/repos/nullflux   # 无输出
```

**该文件不存在，该参数在仓内 grep 不到。** 已删除该句，改为真实证据
（`README:9` badge `node-%3E%3D18`、`README:140` 表格 `18.x / 20.x LTS`）。

这是这批文档里唯一一条被抓住的编造，形态正是 R1 描述的那类：**看起来完全合理的细节
（Node 老程序常设 max-old-space）+ 一个格式正确的行号**，人眼审不出来，只有回切文件才抓得住。
它同时也说明子代理自述「80 条引文逐字比对 0 处不一致」**不可采信**——它比对的是自己挑的那 80 条，
而这 1 条不在其中。

**已知的文档级项目限制**：`chatcfd` 与 `openfoamgpt` 两节全部基于 README 与论文，
其代码实现细节**未读源码**，凡涉及实现的表述均已标注「（依据：文档级，未读源码）」。
这两项不得作为「它的门禁是这样实现的」的证据引用，只能作为「论文这么声称」引用。
