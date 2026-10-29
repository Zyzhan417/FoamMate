# OpenFOAM 智能体生态调研（2026-10-27）

> 调研范围：arXiv 全池 25 篇（全读，不抽样）+ GitHub 候选 37 条去重后精选。
> 方法学：查询式逐字见本文件附录 A；影响力打分公式与权重在取数前冻结，见附录 A。
> 本文只回答「这个领域有什么」，不回答「谁跑得快」（那是 bench 的事，本阶段禁跑）。
>
> 口径声明（先读这一段再看表）：
> - **阅读深度**：25 篇的 `<summary>` 全文逐条读过（100% 覆盖），并抓取了 23 篇的 arXiv HTML 版核对作者单位与首页声明；**未逐页读 25 篇 PDF**。因此凡涉及「全文里怎么写的」的强断言，本文一律降级为「摘要 + 代码可见范围 + HTML 版可见段落」。9 个本地仓的代码按 `path:line` 逐条核对，未下载的仓只读 README（`gh api repos/<r>/readme`）。
> - 论文题名/年份/arXiv id 全部逐字取自 2026-10-27 对 `export.arxiv.org/api` 的实际响应（25 条，`opensearch:totalResults` 亦为 25），落盘 XML 见附录 A 第 1 条命令。
> - 引用数全部取自 Semantic Scholar Graph API `paper/batch`，取值日 **2026-10-27**（附录 A 第 3 条命令）。
> - GitHub 星数/体积/推送时间全部取自 `gh api repos/<owner>/<repo>`，取值日 **2026-10-27 22:57 (+08:00)**（附录 A 第 4 条命令）。
> - 体积两种口径**分列标注**：`实测` = `du -sm references/repos/<id>`；`声明` = GitHub API `size` 字段（KB 级打包估算，含历史与 LFS 指针，与检出体积可差一个数量级）。
> - 本文所有「机制」描述只写它用什么信号、什么数据结构、什么环路；不写「效果好/性能优」。

## 0 结论摘要

1. **主流路线只有三条是被反复实现的**：多 agent 角色分工（2505.04997、2509.18178、2407.21320、2506.02019、2607.20346）、检索增强（2501.06327、2607.20346、2505.04997 的多索引、DeepFlow、MetaOpenFOAM 知识库）、微调（2504.09602 的 28716 对 NL2FOAM、2608.00003 的 252 条 prompt）。见 §3 路线 2–4。
2. **2026 年出现了一次明确的反转**：通用 coding agent + 轻量适配（2609.03718、2602.11689、2609.11941、2606.09774）在同等信息与修复预算下**打平或超过**多 agent 专门系统——单 agent 96.4% vs 多 agent 88.2%（2609.03718 摘要逐字）。这是本领域对我们最重要的一条外部证据。见 §3 路线 1、§4(a)。
3. **最有效的单一输入仍是 solver tutorial 原文**：2609.03718 摘要报「domain knowledge supplied as solver tutorials」是最大增益项（80.9% → 96.4%），而 scripted reflection 增益为零。这直接支持我们的 R1/R3。见 §4(b)。
4. **重复造轮子的地方集中在「让模型看懂 OpenFOAM 字典」这一层**：25 篇摘要里 **11 篇**提到检索/RAG（附录 A 第 5 条），其中至少 **7 篇各自建了自己的检索/知识库**（Foam-Agent 的 FAISS 多索引、MetaOpenFOAM 的 openfoam10 txt 库、ChatCFD 的 Solver Template DB、FoamPilot 的 code-insight 索引、IteraSim 的 HNSW、PhyNiKCE 的 Deterministic RAG、SIGA 的 adapter 检索），彼此不共享，且都绑定各自语料版本。见 §3 路线 3。
5. **「怎么知道跑成功了」是本领域最薄弱的一环**：25 篇摘要里 **0 篇**提到 `checkMesh`；报成功率的 7 篇全部以 solver 退出/日志标记为准。真正把判定从模型手里拿走、交给确定性检查的只有 3 个工作：CFD Forge（2610.14104，确定性 checks 裁决，36 个录制状态回放中模型放过 13 个可检故障里的 12 个、checks 放过 0 个）、AI CFD Scientist（2605.06607，视觉门禁检出 16 个「solver 级检查漏掉的静默失败」中的 14 个）、HarnessFOAM（`validation.py:125-138` + `physics_validation.py:43-71` 的命名检查 + 三态）。见 §4(c)。
6. **声明平台版本正好是 13 的只有一项：HarnessFOAM**（`README:100` 运行时契约「solver logs must confirm OpenFOAM Version 13」；`harnessfoam/case_manifest.py:8` `EXPECTED_OPENFOAM_VERSION = "13"`）。意义：它是 §2 表内 20 个候选项目（原始候选池 37 条）里唯一能在本机 v13 上「不做命令级适配就跑」的实现（tier A），也是唯一一个把「版本号」本身当作验收信号写进代码的——这与我们 R11「单一版本」是同一条约束的两种表达。见 §2、§4(d)。
7. **没有一篇做过「专门检索层 vs 原生 grep」的受控对照**。所有 RAG 工作报的是 retrieval coverage / 端到端成功率，没有一个在同一任务集上把检索层换成 grep 并比较 token 与体积。因此 04 的结论（各 7/7、省 5.2% token、+98 MB）在本领域**没有反例**，只有一个需要区分的替代解释（结构化模板库 ≠ 向量索引，见 §4(a)）。

## 1 论文全表（25 行）

引用数单位：次；取值日 2026-10-27（Semantic Scholar）。「有代码」= 论文摘要给出可解析的仓 URL 且 `gh api` 返回 200（重定向按最终仓计）。

| arXiv id | 年-月 | 标题 | 机构/作者单位 | 有代码 | 引用数(2026-10-27) | 做了什么 | 与我们的关系 |
|---|---|---|---|---|---|---|---|
| 2608.00003 | 2026-05 | AutoFOAM: The Self-Refining Autonomous OpenFOAM Agent | SimuNetics（印度）；Onnes Cryogenics；Quasi AI（柏林） | 无（摘要未给 URL；同名仓 AGN000/AutoFOAM `references/00-project-readme.md:12-13` 自称 "the accompanying arXiv paper" 但未标 id） | 0 | Qwen2.5-14B 微调 252 条 prompt + 自进化环，7 solver/13 网格模板 | 参考：微调路线的成本结构（数据自造、绑定单一版本） |
| 2501.06327 | 2025-01 | OpenFOAMGPT: a RAG-Augmented LLM Agent for OpenFOAM-Based Computational Fluid Dynamics | TU Ilmenau；University of Stuttgart (SimTech) | 无 | 91 | GPT-4o / o1 双基座 + RAG，迭代纠错环跑单相/多相/传热/RANS/LES | 否决：RAG 层，与我们 04 实测结论同向但无对照实验 |
| 2607.20346 | 2026-07 | IteraSim RAG: A Multi-Stage Retrieval-Augmented Agentic Back-End for OpenFOAM-Based Computational Fluid Dynamics | ETH Zürich, Seminar for Applied Mathematics | 无（摘要称 benchmark 公开，未给 URL） | 0 | 查询扩展 + RRF 融合 + MMR 重排 + HNSW，Architect/InputWriter/Reviewer 三段 | 否决：检索链最重的一套；其 Reviewer 只用 solver log + canonical layer 这点可参考 |
| 2609.03718 | 2026-09 | What Do CAE Simulation Agents Really Need Beyond a Generic Harness? | DP Technology；Beihang University；AI for Science Institute | 无 | 0 | 固定信息获取与修复预算，消融多 agent/检索/反思各组件 | **采纳**：单 agent 96.4% > 多 agent 88.2%，tutorial 知识是唯一有效输入 |
| 2505.04997 | 2025-05 | Foam-Agent: A Large Language Model-Based Multi-Agent Framework for Automating Computational Fluid Dynamics Workflows | Rensselaer Polytechnic Institute | 有 github.com/csml-rpi/Foam-Agent | 9 | 四维多索引 FAISS + 依赖感知生成，Planner/Reviewer/InputWriter | 参考：多索引检索的最完整工程实现；v10 语法 |
| 2412.17146 | 2024-12 | LLM Agent for Fire Dynamics Simulations | University of Connecticut；FM Global Research Division | 无 | 12 | FoamPilot：FireFOAM 专用，code insight / case config / sim evaluation 三件套 | 参考：把「代码检索」当独立能力，与我们的 R1 同问题不同解 |
| 2504.09602 | 2025-04 | Fine-tuning a Large Language Model for Automating Computational Fluid Dynamics Simulations | Peking University（湍流与复杂系统国家重点实验室） | 有 github.com/YYgroup/AutoCFD | 48 | Qwen2.5-7B 在自建 NL2FOAM（28716 对含 CoT）上微调 + 多 agent 校验 | 参考：微调路线的数据规模基准；依赖 OF 2406 |
| 2602.11666 | 2026-02 | PhyNiKCE: A Neurosymbolic Agentic Framework for Autonomous Computational Fluid Dynamics | Hong Kong Polytechnic University | 无 | 2 | 把建 case 写成约束满足问题，符号引擎 + 确定性 RAG 强制物理约束 | 参考：「语义-物理断裂」的诊断术语；机制是 CSP 而非检索 |
| 2407.21320 | 2024-07 | MetaOpenFOAM: an LLM-based multi-agent framework for CFD | Tsinghua University, Institute for Aero Engine | 有 github.com/Terry-cyx/MetaOpenFOAM | 57 | MetaGPT 流水线范式分工，自然语言到 case + 后处理 | 参考：被池内 15 篇引用，是本领域的公共基线 |
| 2506.02019 | 2025-05 | ChatCFD: An LLM-Driven Agent for End-to-End CFD Automation with Structured Knowledge and Reasoning | 南方科技大学；北京航空航天大学 | 有 github.com/ConMoo/ChatCFD（302→tianhanz/ChatCFD） | 17 | 结构化知识库 + Error Locator + 迭代反思，315 例报 82.1% 执行成功 | 参考：Error Locator 是「日志→文件定位」的最强实现；模板 DB 消融掉到 48% |
| 2601.01357 | 2026-01 | Towards LLM-enabled autonomous combustion research: A literature-aware agent for self-corrective modeling workflows | Peking University；AI for Science Institute | 无 | 8 | FlamePilot：原子工具 + 文献知识，燃烧建模自纠错 | 参考：「原子工具」粒度设计，与我们门禁脚本同层 |
| 2503.01273 | 2025-03 | OptMetaOpenFOAM: Large Language Model Driven Chain of Thought for Sensitivity Analysis and Parameter Optimization based on CFD | Tsinghua University, Institute for Aero Engine | 有 github.com/Terry-cyx/MetaOpenFOAM | 9 | 在 MetaOpenFOAM 上接灵敏度分析/优化库，QDCOT + ICOT | 无关：优化环，我们本阶段不碰 |
| 2602.11689 | 2026-02 | A Preliminary Assessment of Coding Agents for CFD Workflows | AI for Science Institute；Peking University | 无 | 3 | 用通用 coding agent + 轻量 prompt（引导 tutorial 复用与日志驱动修复） | **采纳**：与我们的做法最接近；tutorial 派生类任务提升显著 |
| 2609.11941 | 2026-07 | A Case-Bundle Operating Model for Coding Agents in OpenFOAM-Based CFD | Peking University；AI for Science Institute | 无 | 0 | case-bundle 两模式（Build/Replay），含配置+网格脚本+远程执行+后处理+评审记录 | **采纳**：与我们 `case.meta` 同构，但把「评审记录」也纳入产物 |
| 2511.00122 | 2025-10 | Engineering.ai: A Platform for Teams of AI Engineers in Computational Design | University of Stuttgart；SimTech | 无 | 4 | 多 AI 工程师团队平台（OpenFOAMGPT + turbulence.ai 之上） | 无关：产品化平台，无可复用机制 |
| 2605.06607 | 2026-05 | AI CFD Scientist: Toward Open-Ended Computational Fluid Dynamics Discovery with Physics-Aware AI Agents | Rensselaer Polytechnic Institute | 有 github.com/csml-rpi/cfd-scientist（302→AI-CFD-Scientist） | 5 | 文献立意→执行→**视觉物理门禁**→改源码→写图，基于 Foam-Agent | **部分采纳**：采纳「需要一层物理合理性检查」这个层次（它报了 14/16 solver 级漏检），**不采纳其实现**——看代码后确认判据是 LLM 读图给三态标签（`interpret.py:60`），无阈值、不可重算，违反 R6/R12。详见 `02-architectures.md` §12 |
| 2408.11987 | 2024-08 | SimBench: A Framework for Evaluating and Diagnosing LLM-Based Digital-Twin Generation for Multi-Physics Simulation | University of Wisconsin–Madison | 无 | 3 | LLM-as-judge（规则 + 人工在环）给数字孪生打分，比较 33 个模型 | 参考：评测协议设计；非 OpenFOAM |
| 2509.18178 | 2025-09 | Foam-Agent 2.0: An End-to-End Composable Multi-Agent Framework for Automating CFD Simulation in OpenFOAM | Rensselaer Polytechnic Institute | 有 github.com/csml-rpi/Foam-Agent | 23 | 加 Meshing Agent（外部网格 + Gmsh 生成）与 HPC 脚本自动化 | 参考：可组合多 agent 的当前上限；v10/esi-v2006 |
| 2606.09774 | 2026-06 | Auto-Configuring Scientific Simulators with Lightweight Coding-Agent Adapters | University of California, San Diego | 无 | 2 | SIGA：给通用 coding agent 供「可执行契约」（检索+过程记忆+可调用校验+**校验门控终止**） | **采纳**：validation-gated termination 与我们 G1–G3 同构，且证明 adapter 可自进化 |
| 2610.14104 | 2026-10 | CFD Forge: A Physics-Constrained Agentic Framework for Autonomous CFD | Carnegie Mellon University | 无（摘要未给 URL；同主题仓 aakashoza31/physics-constrained-cfd-agent 未被论文声明） | 0 | 按流型注册确定性 checks，建 case→网格→求解→诊断→报告，验收由 checks 裁决 | **采纳**：本领域唯一做了「模型裁决 vs 规则裁决」对照的工作（36 状态回放） |
| 2205.12699 | 2022-05 | DRLinFluids -- An open-source python platform of coupling Deep Reinforcement Learning and OpenFOAM | Harbin Institute of Technology (Shenzhen) | 无（摘要未给 URL） | 94 | DRL 智能体闭环控制 OpenFOAM 算例 | 无关：这里的 agent 是强化学习智能体，非 LLM |
| 2604.14919 | 2026-04 | A Numerical and Experimental Evaluation of Microbubble Communication Using OpenFOAM | DFKI；RPTU Kaiserslautern-Landau | 无 | 0 | 微气泡通信的实验 + OpenFOAM 数值对照 | 无关：OpenFOAM 只是工具，无 agent |
| 2608.17504 | 2026-08 | Agentic Porting, Construction and Initial Verification and Validation of Libraries within the Open Source Unified TRAnsient Multi-Phase Advanced Reactor simulation Kit (Outram Park) Part I | Singapore Nuclear Research and Safety Institute | 无 | 0 | 人在环 agent 把 OpenFOAM 库移植到 Rust，V&V 成瓶颈 | 参考：V&V 而非生成才是瓶颈，与我们 R4 判断一致 |
| 2610.18938 | 2026-10 | Beyond Equation Search: Conjecture-Guided Discovery with SCOPE and ClosureBench | HK PolyU；Eastern Institute of Technology (Ningbo)；SJTU | 无 | 1 | 多 scientist agent 并行检验猜想，符号回归 | 无关：不涉及 OpenFOAM/建 case |
| 2610.32632 | 2026-10 | Toward Open ISA Supercomputing: A Comparative Study of RISC-V, Arm, and x86 Architectures on HPC Workloads | University of Bologna；CINECA；University of Trento | 无 | 0 | RISC-V/Arm/x86 在含 OpenFOAM 的 HPC 负载上对比 | 无关：体系结构基准，OpenFOAM 只是 workload |

**排除与可用篇数**：25 篇中排除 5 篇——2604.14919（微气泡通信，OpenFOAM 仅作数值工具，无 agent）、2205.12699（DRL 智能体，非 LLM，且 2022 年）、2610.18938（符号回归/猜想发现，不涉 OpenFOAM）、2610.32632（RISC-V 体系结构对比，OpenFOAM 是 workload）、2408.11987（SimBench 面向多物理数字孪生，非 OpenFOAM 专用，仅评测方法论可用）。
**排除后实际可用 20 篇**，其中 19 篇直接涉及「自然语言 → OpenFOAM case 生成/运行/诊断」，1 篇（2608.17504）是 agent 驱动的库移植。20 ≥ 10，故 top10 成立。

**关于 top-N 排序的一个警告（必须写在这里）**：按附录 A 冻结的公式排序，前 7 名全是 2025 年及以前、有代码的工作；本文件 §4(c) 认为机制上最强的三篇（2610.14104 CFD Forge、2609.03718、2606.09774 SIGA）分别排在并列末位与第 16 位——原因是它们发表于 2026 年下半年、Semantic Scholar 引用数还是 0，而公式里 `recency_ok` 只值 0.5。**该公式适合找「公共基线」，不适合找「最值得读」**。因此 §3/§4 的分类与裁决不按分数排序，按机制读。排序结果见附录 A。

## 2 GitHub 候选表（按 ★ 降序）

★ 与推送时间取值日 2026-10-27 22:57 (+08:00)。体积列口径逐行标注：`实测`（`du -sm`）或 `声明`（GitHub API `size`，`KB/1024` 换算，保留 1 位）。tier：A=本机 v13 可直接跑 / B=需命令级适配 / C=不可适配只做文档分析。

> **tier 的权威来源是 `references/registry.csv`，本表与它逐行一致（2026-10-27 核对）。**
> 本表曾把 `SciMate-AI/HPC-Skills` 记为 A，在 `02-architectures.md` 的逐项目分析中按冻结判据
> （`search-protocol.md` §5：声明别的版本的即 B）修正为 B，此处已同步。
> 全库实测分布：**A=1（仅 harnessfoam）/ B=10 / C=1**（2026-10-28 更正：原写 B=9，是漏数一个 full 仓所致；
> `references/registry.csv` 实测 `awk -F, 'NR>1{c[$8]++}'` → A=1 / B=10 / C=1，与 `bench/preregistration.md:443` 一致）。
> 注：`bench/preregistration.md:267` 仍写 B=9——那一行在预注册的冻结切片内，改动须按变更规则开新一轮，故未就地改。

| repo | ★ | 体积 | license | 语言 | 最后推送 | 声明的 OpenFOAM 版本 | tier | 一句话 |
|---|---|---|---|---|---|---|---|---|
| csml-rpi/Foam-Agent | 352 | 实测 2 MB | MIT | Python | 2026-09-20 | v10（`README:35` 容器自带 v10；`README:244` "Foundation OpenFOAM v10 is the default native target"，另支持 esi-v2006） | B | 多 agent + 四维 FAISS 索引，本领域星数第一 |
| Terry-cyx/MetaOpenFOAM | 209 | 实测 5 MB | GPL-3.0 | Jupyter Notebook | 2026-04-10 | openfoam10（`src/Tutorial_postprocess.py:1` "convert tutorials of openfoam10 to txt file"） | B | MetaGPT 式流水线，池内 15 篇的公共基线 |
| webworn/openfoam-mcp-server | 125 | 实测 4 MB | NOASSERTION（见 LICENSE） | C++ | 2026-01-18 | OpenFOAM-12（`README:5` badge；`README:257` `apt install openfoam12`） | B | MCP 工具化的最大实现：`src/tools/` 39 个文件，工具按流型分（pipe/external/heat/multiphase/mesh_quality/rde_3d） |
| SciMate-AI/HPC-Skills | 95 | 实测 4 MB | MIT | Python | 2026-04-06 | 未统一（模板 `skills/hpc-openfoam/assets/templates/simplefoam-minimal/README.txt:1` "OpenFOAM-11 case scaffold"） | **B** | 纯 skill 文本集：`skills/` 22 个 skill，`hpc-openfoam/references/` 17 个文件，无执行代码 |
| tianhanz/ChatCFD | 70 | 声明 562.6 MB（576098 KB） | NOASSERTION | Python | 2026-04-09 | 未声明（README 无版本串；同源仓 woog97/cfd-agent `ReadMe.md:78` 要求 v2406） | B | 超 R10 体积线，`docs_only`，未下载；56 万 KB 里绝大多数是数据/图 |
| csml-rpi/AI-CFD-Scientist | 58 | 实测 8 MB | 无 LICENSE | Python | 2026-10-21 | OpenFOAM 10（`README:282` "**OpenFOAM 10** — for any real CFD run"） | B | 论文 2605.06607 的代码；skill 编排 + 视觉判读门禁。**已入库**（初版漏下，合并后补） |
| WyllDuck/OpenFOAM-ToolChain-for-Rocket-Aerodynamic-Analysis | 43 | 声明 16.9 MB（17282 KB） | 无 LICENSE | C++ | 2026-04-27 | 未声明（`README:8` 仅写 "ESI group distribution"） | C | Jinja2 模板批量生成 case，非 agent |
| LZF1111/nullflux | 37 | 实测 43 MB | 无 LICENSE | JavaScript | 2026-06-10 | v2206+ / 推荐 v2306（`docs/index.html:634` "OpenFOAM 推荐 v2306 以上"） | B | 随仓带 sealed 二进制 cfdriver，耦合外部求解器 |
| isabecurtis023-lang/HarnessFOAM | 17 | 实测 13 MB | 无 LICENSE | Python | 2026-09-03 | **13**（`README:100` "solver logs must confirm OpenFOAM Version 13"；`harnessfoam/case_manifest.py:8` `EXPECTED_OPENFOAM_VERSION = "13"`） | **A** | 唯一 v13 原生：确定性 preflight + 运行时契约 + 参考门禁 + 失败账本 |
| gchen19/AnkusDrive | 13 | 声明 37.7 MB（38645 KB） | Apache-2.0 | Python | 2026-10-15 | 未声明（`README:109` 只写 `ANKUSDRIVE_OPENFOAM_PATH` 环境变量） | C | 多求解器桌面容器，OpenFOAM 只是其中一个后端 |
| woog97/cfd-agent | 12 | 实测 66 MB | NOASSERTION（见 LICENSE.txt） | Python | 2025-12-31 | v2406（`ReadMe.md:78` "OpenFOAM v2406… 其他版本会与 `database_OFv24/*.json` 不匹配"） | B | ChatCFD 代码；版本绑死知识库 JSON |
| AGN000/AutoFOAM | 10 | 实测 28 MB | 无 LICENSE | Python | 2026-07-25 | v2412（`references/00-project-readme.md:3` "OpenFOAM v2412 case-authoring agent"；`references/00-project-readme.md:152`/`187` source 路径） | B | 论文 2608.00003 的代码；gmsh OCC 全自动建网格 |
| Pat2704/openfoam-gui | 10 | 声明 22.9 MB（23452 KB） | MIT | TypeScript | 2026-10-20 | openfoam14（`README:67` `apt install openfoam14`） | C | GUI 而非 agent，说明候选池噪声 |
| test1card/femis-skill | 8 | 声明 3.1 MB（3147 KB） | Apache-2.0 | Python | 2026-10-09 | 未声明 | C | skill 文本集（FEM 向），无 OpenFOAM 版本声明 |
| twj011/openfoam-agent-skills | 7 | 声明 0.02 MB（19 KB） | MIT | Python | 2026-01-25 | v2412（`README:14` "targets **ESI/OpenCFD OpenFOAM v2412**"） | B | 最小 skill 文本集，19 KB 全文本 |
| yuxuuan-hu/DeepFlow | 5 | 实测 14 MB | 无 LICENSE | C++ | 2025-11-30 | v2412（`references/00-project-readme.md:146`；`references/00-project-readme.md:4` badge） | B | LangChain + FAISS RAG + GUI（`references/00-project-readme.md:25`） |
| swtbkim/openfoam-claude-suite | 4 | 声明 0.1 MB（56 KB） | MIT | Shell | 2026-07-09 | v2412（`README:37` "OpenFOAM v2412 - source build or openfoam.com packages"） | B | Claude Code 插件形态的自然语言 case 自动化 |
| NLR-Theseus/cfdllmbench | 49 | 声明 22.7 MB（23222 KB） | BSD-3-Clause | Python | 2026-10-19 | 未声明（`README:43` "110 Basic + 16 Advanced OpenFOAM simulation tasks"） | 参考 | 基准而非 agent，FoamBench 的复现载体 |
| YYgroup/AutoCFD | 54 | 声明 40.8 MB（41817 KB） | GPL-3.0 | C++ | 2026-09-18 | 2406（`README:46` "OpenFOAM 2406"；`README:90` source 路径） | B | 论文 2504.09602 代码；微调 + 多 agent 校验 |
| 0xFFD/openfoam-mcp | 1 | 声明 1.1 MB（1111 KB） | MIT | Python | 2026-10-11 | OpenFOAM 14（`README:124` "OpenFOAM 14 (openfoam.org) on Ubuntu 22.04 / WSL2"） | C | 第二个 MCP 实现，更小、更贴 openfoam.org 14 |

已下载 9 个仓的 `commit_sha` 与 `size_mb` 以 `references/registry.csv` 为准（本文体积列复述该表实测值，未改动）。`docs_only` 的 tianhanz/ChatCFD 无 `local_path`，其版本判断只用 README + 同源仓 README。

## 3 形态分类（路线图）

### 路线 1 · 单 agent 循环 + 通用 harness
代表：2609.03718（单 agent harness）、2602.11689（coding agent + 轻量 prompt）、2609.11941（case-bundle）、2606.09774（SIGA adapter）、2610.14104（CFD Forge）、`references/repos/harnessfoam`。
机制：一个模型 + 文件读写/命令执行工具 + 「执行反馈 → 修复」环；知识以教程/契约文本注入，不做角色拆分。
结构性代价：能力上限由基座模型与反馈信号质量决定；**没有执行反馈就没有增益**（2609.03718 摘要：无修复轮 71.8%，有修复轮 96.4%，而 scripted reflection 增益为零）。因为只有一个环，失败模式无法通过「换个角色再审一遍」掩盖，必须靠外部检查器兜底。

### 路线 2 · 多 agent 角色分工
代表：2505.04997 / 2509.18178（Planner/Reviewer/InputWriter/Meshing）、2407.21320（MetaGPT 流水线）、2506.02019（含 Error Locator）、2607.20346（Architect/InputWriter/Reviewer）、HarnessFOAM（6 个 agent：architect/input_writer/reviewer/meshing/runner/visualizer）。
机制：把「选 solver / 写字典 / 查错 / 可视化」切成固定角色，角色间传结构化对象（pydantic schema 或 JSON plan）。
结构性代价：token 与延迟随角色数线性增长；角色边界靠 prompt 维持，没有硬接口；最致命的是 2609.03718 的实测——同等信息与修复预算下多 agent 反而低 8.2 个百分点（88.2% vs 96.4%），且「让同一个 agent 既起草又审自己」在 2607.20346 里被明确当作缺陷动机，但拆开审并不自动带来正确性。

### 路线 3 · 检索增强（RAG）
代表：2501.06327、2607.20346（查询扩展+RRF+MMR+HNSW）、2505.04997（四维 FAISS 多索引）、`references/repos/deepflow`（FAISS + LangChain）、`references/repos/metaopenfoam`（openfoam10 tutorials → txt 库）、2602.11666（Deterministic RAG）。
机制：把 tutorials/文档切块嵌向量或建倒排索引，按查询取回片段拼进 prompt；进阶版按工作流阶段选不同索引（Foam-Agent），或按 solver/湍流/边界条件分路检索（PhyNiKCE）。
结构性代价：索引与语料版本强绑定——`references/repos/cfd-agent/ReadMe.md:78` 直说换版本会让预建 `database_OFv24/*.json` 失效；体积上 ChatCFD 仓 562.6 MB、Foam-Agent 仓仅 2 MB 但索引需另建（`init_database.py:122-136` 读 `index.faiss`/`index.pkl`）；且检索质量指标与任务成功之间没有桥（2607.20346 只报 coverage 77.9%）。

### 路线 4 · 微调
代表：2504.09602（Qwen2.5-7B + 28716 对 NL2FOAM 含 CoT）、2608.00003（Qwen2.5-14B + 252 条 prompt）。
机制：把「自然语言 → 字典」当监督学习任务，用 CoT 标注把中间推理也纳入目标；推理期仍套多 agent 校验环（2504.09602）。
结构性代价：数据自造、不可比（28716 对 vs 252 条差两个数量级）；模型一旦固化就与 OpenFOAM 版本脱钩，换版本需重训；且训练集来源不公开，无法判断是否已把目标 benchmark 泄漏进去（两篇都未给数据集链接）。

### 路线 5 · agent-skill 文本集
代表：`references/repos/hpc-skills`（`skills/` 22 个 skill，`hpc-openfoam/SKILL.md` 89 行 + 17 个 references）、`twj011/openfoam-agent-skills`（19 KB）、`swtbkim/openfoam-claude-suite`（56 KB）、`csml-rpi/AI-CFD-Scientist`（`cfd-skills/cfd-<stage>/SKILL.md`）。
机制：把领域知识写成渐进加载的 markdown（先读 case-setup，再按需读 solver-selection / BC playbook / error-recovery），由宿主 agent 自己决定何时加载。
结构性代价：**零执行门禁**——文本对不对没有任何程序判定，正确性完全依赖模型遵循与读者审阅；且文本里的版本信息是自由书写（HPC-Skills 模板写 OpenFOAM-11，twj011 写 v2412），无法被机器校验。

### 路线 6 · MCP 工具化
代表：`webworn/openfoam-mcp-server`（`src/tools/` 39 文件，工具按流型分：pipe_flow / external_flow / heat_transfer / multiphase_flow / mesh_quality / rde_3d）、`0xFFD/openfoam-mcp`、HarnessFOAM（`harnessfoam/api/mcp_server.py`，工具含 `run_parameter_optimization`）、2506.02019（摘要自称 "MCP-compatible"）、2509.18178（摘要提 MCP）。
机制：把「跑一个算例/查网格质量/查湍流模型」封成 JSON-RPC 工具，模型只选工具与参数，不在文件层面自由编辑。
结构性代价：工具粒度即能力上限——一个 `pipe_flow` 工具只能跑管流，遇到没封装的情形 agent 无从下手；接口层不解决版本问题（OpenFOAM-12/14 各写各的），也不解决「跑完算不算成功」（HarnessFOAM 是唯一把门禁放进 MCP 工具返回值的）。

## 4 与我们项目设计的直接对照

### (a) 04 已实测否决的 RAG 层：本领域有没有反例？

**结论：没有能推翻的反例；有一个必须区分的替代解释。**

- **在摘要与代码可见范围内没有找到一篇做了受控对照**。25 篇里报检索质量的只有 2607.20346（mean retrieval coverage 77.9%，median 79.1%）；报端到端成功率的 7 篇都是「多 agent / 单 agent / 知识库开关」这一类消融，没有一篇把「专门检索层」换成「在 tutorial 上直接 grep」再比 token 与体积；9 个本地仓里也没有这样的对照实现。因此 04 的「各 7/7、省 5.2% token、+98 MB」在本领域既未被复现也未被反驳——**这是证据缺口，不是反例**（若将来有人做了该对照并显示检索层显著更省，本节结论需推翻）。
- 唯一看起来像反例的是 2506.02019 的消融：「removal of Solver Template DB collapses accuracy to 48%」。但它的机制是**预先整理的模板库**（结构化字段，不是向量近邻），而模板本身来自 tutorials——这与我们 R3「从 tutorial 派生」是同一条路，不是「建检索层」。区别可判定：模板库能被 grep 逐条核对（`database_OFv24/*.json` 是明文 JSON），向量索引不能。
- 2602.11666 的 "context poisoning" 是对**语义检索**的直接批评（"reliance on purely semantic RAG often leads to context poisoning"），其解法是把检索变成确定性约束求解，即**减少**检索的自由度——方向上支持我们，而不是反对。
- 2609.03718 的消融给了最强的一条正面证据：唯一显著有效的输入是「solver tutorials 原文」（80.9% → 96.4%）；同一篇的另两项是**负**证据——多 agent 分解在同等条件下低于单 agent（96.4% vs 88.2%）、scripted reflection「adds nothing」。摘要只把 tutorial 点名为「唯一仍有帮助的输入」。我们的 grep 正是「在 tutorial 原文上检索」的零索引实现。

### (b) P2「case 必须从 tutorial 派生」

支持：
- 2602.11689：明确把「tutorial reuse」写进给 agent 的轻量配置，报「tutorial-derivative 任务的执行完成率大幅提升、无效工具调用减少」。
- 2609.03718：tutorial 作知识输入是最大增益项（80.9% → 96.4%）。
- 2609.11941：case-bundle 的 Replay 模式——把已评审的 case 复用到 140 个 STL 变体，本质是「派生 + 受控改动」。
- `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:17-21`：把 cavity/pitzDaily/damBreak/shockTube 四个官方 tutorial 做成回归注册表，逐个复制到隔离目录再跑同一套 v13 门禁——这是「tutorial 当基线」的代码化。

相反（脱离 tutorial 的地方）：
- 2608.00003 / `references/repos/autofoam`：13 个参数化网格模板 + gmsh OCC 全自动建模，几何不是从 tutorial 派生的。
- 2505.04997 / 2509.18178：Meshing Agent 用 Gmsh 生成新几何、支持外部网格文件。
- 2605.06607：会编译 case-local C++ 库来改物理模型，已超出「改字典」范畴。
→ 这三类都落在我们 R5 明确划出的边界外（曲面/多体/STL 一律停下问人）。**结论：P2 在「字典层」被支持，在「几何层」被绕过；我们不需要因为别人会 gmsh 就松开 R5。**

### (c) 门禁 G1–G4：谁给出了更硬的「怎么知道跑成功了」

我们的现状：G1 结构 / G2 `checkMesh` 含 `Mesh OK.` / G3 短跑无 `FOAM FATAL` 且退出码 0 / G4 产物可读。按「判定信号是否独立于模型」排序，有三个工作比我们硬：

1. **CFD Forge（2610.14104）—— 唯一做了裁决对照**。机制：按流型注册确定性 checks，"acceptance is not left to the model"，模型只提动作（closed set），checks 决定接受与否。证据：把 36 个录制的仿真状态（部分被人为篡改诊断）回放给同一模型——不看 check 结果时模型在三次重复里放过了 13 个可检故障中的 12 个；由 checks 裁决时放过 0 个。**它还给了我们 G3 的一个反例**：一个湍流立方体算例 solver 正常跑完、平均阻力也收敛了，但侧向力振荡仍在增长，事后判定拒绝接受——**「跑完 + 一个指标收敛」不足以判成功**。
2. **AI CFD Scientist（2605.06607）—— 把 G4 从「可读」推到「物理可信」**。机制：vision-language 门禁在结果被接受/重跑/写进论文之前检查渲染后的流场图；"solver completion does not imply physical validity and many failure modes appear only in field-level imagery rather than in solver logs"。证据：植入故障的对照实验里，该门禁检出 16 个 solver 级检查漏掉的静默失败中的 14 个。对我们 G4 的直接含义：**判「产物可读」只挡住了「没产物」，挡不住「产物是垃圾」**。
3. **HarnessFOAM（`references/repos/harnessfoam`）—— 与我们门禁逐条同构，且多了三态与版本信号**：
   - `harnessfoam/validation.py:125-138` `validate_runtime()` 判 5 件事：日志含 `FOAM FATAL|FOAM aborting`（失败）、无完成标记（失败）、`time_steps == 0`（失败）、**日志里的 `Version:` 不等于期望版本（失败）**、`max_courant` 超限（失败）。第 4 条是我们没有的：它把「跑的是不是那个版本」变成硬信号（对应 `case_manifest.py:8` 的 `"13"`）。
   - `harnessfoam/validation.py:12-75` `validate_case_files()`：必需文件清单、`FoamFile` 头、占位内容 `"Mock OpenFOAM content"` 一律拒绝、`blockMeshDict` 的 `boundary` 块必须可解析、**`0/U`、`0/p` 的 `boundaryField` patch 名必须与网格 patch 集合完全相等**（不等就报 `Patch mismatch`），再按 solver 名追加必需文件（`interFoam` → `0/alpha.water` + `constant/g`）。这是 G1 的强版本：我们只查结构存在，它查**跨文件一致性**。
   - `harnessfoam/validation.py:78-121`：从日志正则抽 `Final residual` / `global =`（连续性）/ `Courant Number mean|max` / `Time =` 计数 / 结束标记，并单独判数值发散标记（`bounding k|epsilon|omega`、Courant > 100、末 5 个连续性误差 > 1e3、末 10 个初始残差 > 1.0）。
   - `harnessfoam/physics_validation.py:43-71` `validate_physics()`：读最新时间目录的 `U`/`p` 场，判 NaN/Inf、`|U| > 1e4` 荒谬上限、以及 cavity 专属的「1 m/s 动盖下最大速度 < 0.5 m/s 即失败」。这一条是 G4 的物理版，且失败时返回**命名检查**而不是布尔。
   - `harnessfoam/reference_benchmarks.py:10-20`：5 个命名检查 + 分数（`score = passed/5`，全过才 PASSED），检查名逐字：`openfoam13_final_time`、`courant_below_0.2`、`continuity_below_1e-6`、`finite_velocity`、`moving_lid_velocity_reached`。
   - 三态：`physics_validation.py:46` 与 `:70` 在无写出时间目录/无 U 无 p 时返回 `status: "SKIPPED"` 而不是通过；`README:102` 明写视觉审查不可用时「reported as `SKIPPED`, never as a false pass」。这正对应我们 R12 的 `no_artifact` 态——**它已经在代码里做了，我们还在文档里**。
4. 次级证据：2606.09774 SIGA 的 "validation-gated termination"（校验不过就不许终止，且 adapter 的内容可被历史轨迹重写）；2506.02019 的 Error Locator（把 solver log 的行映射回具体字典文件）+ 自报 68.12% "physical fidelity"（比成功率更接近 G4，但指标定义未公开）；2609.03718 的 "execution-feedback repair"（71.8% → 96.4%，证明修复环本身是主要增益来源）。

**采纳建议（本节可执行结论）**：G3 增加「日志版本行 == 13」；G1 增加「`0/U`/`0/p` 的 patch 集合 == `constant/polyMesh/boundary` 的 patch 集合」；G4 增加「写出时间目录里 U/p 全为有限值 + 一个与物理量级挂钩的上限」；判定结果从布尔改为 `pass|fail|no_artifact|malformed` 四态（HarnessFOAM 只用三态，`malformed` 是我们的补充）。这些都不需要装第二个 OpenFOAM。

### (d)「不装第二个 OpenFOAM」：谁把我们挡在 v13 之外

声明版本与本机 v13 不符、因此在本机只能做文档级对比的（附证据行）：
- `references/repos/foam-agent/README.md:35`（容器自带 v10）、`:76`（`--openfoam_target esi-v2006`）、`:244`（默认 native target 是 Foundation v10，"Each native target uses its own tutorial/FAISS corpus"）→ 连语料与 guard 都按版本分家，换 v13 等于换一套索引。
- `references/repos/metaopenfoam/src/Tutorial_postprocess.py:1`（`openfoam10` 的 tutorials 转 txt 建库）→ 知识库内容本身是 v10 语法。
- `references/repos/openfoam-mcp-server/README.md:5`（badge OpenFOAM-12）、`:257`（`apt install openfoam12`）→ C++ 链接系统 OF 库，换版本要重编。
- `references/repos/cfd-agent/ReadMe.md:78`（必须 v2406，否则 `database_OFv24/*.json` 不匹配）→ 知识库与版本一对一。
- `references/repos/autofoam/README.md:3`/`:152`/`:187`（v2412）；`references/repos/deepflow/README.md:146`（v2412）；`references/repos/nullflux/docs/index.html:634`（推荐 ≥v2306，且随仓带 sealed 二进制 cfdriver，无可读源码 → 适配性无法从代码判断）。
- 外部仓：`csml-rpi/AI-CFD-Scientist` `README:282`（OpenFOAM 10）、`YYgroup/AutoCFD` `README:46`（2406）、`twj011/openfoam-agent-skills` `README:14`（v2412）、`swtbkim/openfoam-claude-suite` `README:37`（v2412）、`0xFFD/openfoam-mcp` `README:124`（OpenFOAM 14）、`Pat2704/openfoam-gui` `README:67`（openfoam14）。
- 论文侧另有：2506.02019（对应代码 v2406）、2607.20346（v2506 上跑通）、2609.11941（OpenFOAM-7 interFoam）。

**唯一声明 13 的是 HarnessFOAM**（`README:100`、`case_manifest.py:8`），且它把版本号做成了运行时断言而不是文档声明——这也是它成为唯一 tier A 的原因。**这条对照的实践含义**：别人写的 prompt/字典不能当 v13 语法证据（R9 已写），而别人写的**门禁逻辑**可以——因为门禁逻辑判的是信号（`Version:` 行、patch 集合、NaN），不判具体关键字拼写。所以本阶段可复用的是 2610.14104 与 HarnessFOAM 的判定结构，不可复用的是任何一份字典模板。

## 5 已知缺口（这个领域没人做的事）

1. **网格质量不进成功判据**：25 篇摘要中提及 `checkMesh` 的为 **0 篇**（`grep -oi 'checkmesh' arxiv_openfoam_agent.xml | wc -l` → 0，见附录 B）；报成功率的 7 篇全部以 solver 退出/日志标记为准。连做得最细的 Autofoam 也是 `openfoam_agent/runner.py:37-41` 这种「无 `FOAM FATAL` + 有 `ExecutionTime` 与 `End`」判据，`checkMesh` 不进验收。→ 这是我们的 G2 相对领域的净增量。
2. **没有「检索层 vs grep」的对照**：见 §4(a)。所有 RAG 论文的对照臂都是「无检索」，不是「换一种检索」。→ 04 的结论目前无人复现，也无人反驳。
3. **版本断代严重**：§2 的 20 个候选项目里声明 v13 的 **1** 个（HarnessFOAM），声明 14 的 **2** 个（`Pat2704/openfoam-gui`、`0xFFD/openfoam-mcp`），声明 12 的 **1** 个（`webworn/openfoam-mcp-server`），声明 10 的 **3** 个（`csml-rpi/Foam-Agent`、`Terry-cyx/MetaOpenFOAM`、`csml-rpi/AI-CFD-Scientist`），2023/2024 系（v2306–v2412）的 **7** 个，未声明的 **6** 个。**领域默认版本落后本机 v13 一到两代**，因此任何「照着论文跑一遍」的复现计划都会先在版本上失败。
4. **成本只报 token，不报存储与索引体积**：25 篇里给出每例 token/费用的只有 2506.02019（192.1k tokens、$0.208/case）；没有任何一篇报索引体积或知识库占用。→ 我们的 04 结论里那 98 MB 在领域内无处对标。
5. **结果状态多为二值**：报「成功率」的 7 篇里没有一篇定义「没产出任何 case」该记为什么；唯一在代码里区分「不可判定」的是 HarnessFOAM 的 `SKIPPED`（`physics_validation.py:46`/`:70`、`README:102`）。→ 对应我们 R12 的三态要求，领域内基本空白。
6. **微调数据不可比、不公开**：28716 对（2504.09602）与 252 条（2608.00003）相差两个数量级，两篇都未给数据集链接，也没有在共同测试集上比过。→ 「微调值不值得」这个问题在本领域目前无法回答。

## 附录 A 查询与打分（逐字记录，可复现）

### A.1 实际执行过的命令

```bash
# ① arXiv 主查询（2026-10-27，返回 25 条，totalResults=25）
curl -sL 'https://export.arxiv.org/api/query?search_query=abs:%22OpenFOAM%22+AND+%28abs:%22LLM%22+OR+abs:%22agent%22+OR+abs:%22language+model%22%29&start=0&max_results=40&sortBy=relevance' \
  -o arxiv_openfoam_agent.xml
grep -c '<entry>' arxiv_openfoam_agent.xml          # → 25
grep -o '<opensearch:totalResults[^<]*<' arxiv_openfoam_agent.xml   # → <opensearch:totalResults>25

# ② 同义查询计数（编排方实测，本次未复跑，标注为二手数据）
#    OpenFOAM+agent 22 / OpenFOAM+LLM 17 / CFD+agent+LLM 20 / OpenFOAM+RAG 7

# ③ Semantic Scholar 引用数（批量端点；2026-10-27）
#    首次 429，第 5 次尝试成功；单篇端点也大量 429，故改用 batch
POST https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,citationCount,influentialCitationCount
  body: {"ids":["ARXIV:2608.00003", ... 共 25 个 ...]}
#    另取 references 用于「池内被引为基线」：
POST https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,references.title
#    → 25/25 有 citationCount，无 null

# ④ GitHub 元数据（每个候选仓一次；2026-10-27 22:57 +08:00）
gh api repos/<owner>/<repo> --jq '[.stargazers_count,.forks_count,.size,.full_name,(.language//"-"),(.pushed_at|tostring),(.license.spdx_id//"none"),(.created_at|tostring)]|@tsv'
#    覆盖 gh_candidates.tsv 全部 37 行（去重后 37 个仓），星数与 22:52 的 tsv 一致

# ⑤ 摘要关键词计数（用于 §5 缺口，统计对象 = 25 条 <summary> 原文）
python3: sum(1 for r in rows if re.search(r'checkmesh', r['summary'], re.I))   # → 0
         'success' → 7 篇；'retriev|RAG' → 11 篇；'multi-agent' → 7 篇
         'fine-tun' → 2 篇；'MCP' → 2 篇；'tutorial' → 5 篇

# ⑥ 机构：优先取 arXiv HTML 版作者块
curl -sL 'https://arxiv.org/html/<id>' -o html/<id>.html
#    2 篇无 HTML（2407.21320、2503.01273）改从 PDF 首页解压文本流，得到
#    "Institute for Aero Engine, Tsinghua University, Beijing 100084, China"

# ⑦ 仓存在性核对（无代码/有代码判定的依据）
gh api repos/ConMoo/ChatCFD --jq .full_name        # → tianhanz/ChatCFD（302 重定向）
gh api repos/csml-rpi/cfd-scientist --jq .full_name # → csml-rpi/AI-CFD-Scientist
gh api repos/csml-rpi/Foam-Agent --jq .full_name   # → 原样
```

### A.2 影响力打分（取数前冻结，权重未改）

```
score = 3*has_code + 2*cited_as_baseline + 1*log10(1+stars) + 1*log10(1+citations) + 0.5*recency_ok
```

| 项 | 取值规则 | 取数来源 |
|---|---|---|
| `has_code` | 1 = 论文摘要/正文给出仓 URL 且 `gh api` 返回 200（重定向按最终仓）；否则 0。**仅「同名仓自称 accompanying paper」不算（故 AutoFOAM 记 0）** | arXiv `<summary>` + `gh api repos/...` |
| `cited_as_baseline` | 1 = 池内至少 1 篇论文的参考文献里出现该文；否则 0（二值，不按次数加权） | S2 `references.title` 与池内标题做 token Jaccard ≥ 0.5 匹配（停用词剔除；`foam-agent`/`foam agent` 归一到 `foamagent`） |
| `stars` | 该论文仓的 `stargazers_count`；无代码记 0 | `gh api repos/<repo>` |
| `citations` | S2 `citationCount` | S2 batch（2026-10-27） |
| `recency_ok` | 1 = `published` ≥ 2025-01；否则 0 | arXiv `<published>` |

**排序结果（前 10，公式计算值）**：2509.18178 9.43 · 2407.21320 9.09 · 2505.04997 9.05 · 2504.09602 8.93 · 2503.01273 8.82 · 2506.02019 8.61 · 2605.06607 8.05 · 2501.06327 4.46 · 2601.01357 3.45 · 2511.00122 3.20。
**公式的三处已知偏置（如实记录）**：(i) 2026 年新作 citations=0 直接沉底，`recency_ok` 只补 0.5，导致机制最强的 2610.14104 与 2609.03718 排并列末位（0.5）；(ii) 多篇论文共用一个仓时 stars 被重复计入（Foam-Agent ×2、MetaOpenFOAM ×2），抬高 2505.04997/2503.01273；(iii) `cited_as_baseline` 的二值化让「被引 15 次」与「被引 1 次」得分相同。

### A.3 本次实际遇到的反常

1. **Semantic Scholar 重度 429**：单篇端点在 25 次连续请求里只有 3 次成功；批量端点在 90 秒内连续 4 次 429 后成功。结论：必须用 batch + 退避，不能用单篇循环。
2. **S2 标题与 arXiv 题名不一致**：2501.06327 在 S2 的记录标题是 "OpenFOAMGPT: a retrieval-augmented large language model (LLM) agent for OpenFOAM-based computational fluid dynamics"（已发表版），与 arXiv 题名不同。本文表内一律用 arXiv 题名，`cited_as_baseline` 的匹配因此需要 Jaccard 模糊匹配而非串等。
3. **arXiv id 与发表月不对应**：2609.11941 的 id 前缀是 2609，但 `<published>` 为 2026-07；2608.00003 的 id 是 2608 而 `<published>` 为 2026-05。表内「年-月」列一律取 `<published>`，不取 id。
4. **arXiv HTML 抓取受限**：`arxiv.org/html/<id>` 对 23/25 篇可用，2407.21320 无 HTML；`ar5iv` 对 2503.01273 只返回外壳页。两篇最终靠 PDF 流解压取到机构。另外 arXiv 在 23:00–23:15 间对连续抓取明显限速（单篇 HTML 需 1–3 分钟）。
5. **OpenAlex 机构字段不可用**：按 DOI 批量查 `authorships.institutions` 出现明显错配（2608.00003 被标成医院），故全部弃用，机构一律以论文原文为准。
6. **`ConMoo/ChatCFD` 与 `csml-rpi/cfd-scientist` 均已重命名**，论文里写的 URL 现在 302。若不查重定向，会得出「论文给的仓不存在」的错误结论。
7. **registry.csv 的 `size_mb` 与 GitHub `size` 差一个数量级**（如 Foam-Agent：实测 2 MB vs 声明 43.6 MB；ChatCFD：声明 562.6 MB vs 未下载）。本文两列分开口径标注，未混写。

## 附录 B 自检（实测，供复核）

实际执行（2026-10-27，本机，工作目录 `05_FOAM_Agent`），输出为逐字复制：

```
$ grep -c '^| [0-9]\{4\}\.[0-9]\{4,5\} |' references/01-landscape.md
25

$ grep -E '^\| 2[0-9]{3}\.' references/01-landscape.md | grep -c 'github.com/'
7

$ awk '/^\| repo \| ★/,/^$/' references/01-landscape.md | grep -c '^| .*| [0-9]\+ |'
20

$ grep -oi 'checkmesh' arxiv_openfoam_agent.xml | wc -l
0

$ find references/repos -newer references/registry.csv -type f      # R9 门禁
(空)
```

- 论文表行数 = **25**（`grep -c` 实测 25，与 `grep -c '<entry>'` 的 25 一致）
- 有代码篇数 = **7**（判据见 A.2：2505.04997、2509.18178、2407.21320、2503.01273、2506.02019、2504.09602、2605.06607；AutoFOAM 因未给 URL 记 0）
- GitHub 表行数 = **20**
- 声明版本为 13 的项目 = **1**（isabecurtis023-lang/HarnessFOAM：`README:100` + `harnessfoam/case_manifest.py:8`）
- 引用数覆盖 = **25/25**，取值日 2026-10-27，无 null
- 未下载仓的体积一律写「声明 X MB（Y KB）」，已下载的一律写「实测 X MB」，无一行混用
- R9 门禁复跑为空；核对过程中 `git rev-parse`/`git status` 会刷新 `.git/index` 的 mtime 从而让门禁误报，已用 `git -C <repo> status --porcelain` 逐个确认 9 个仓工作树干净（均 0 行）后把 index 的 mtime 复位
