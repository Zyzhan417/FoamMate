# 八、精简版报告：自然语言驱动 OpenFOAM 的智能体（2026-10-28）

> 定位：把 `references/01`–`07` 压成一页主线，供**外部评审**使用。
> **本文件不产生新事实**：每条断言后括注源文档全路径 + 行号；数字给出源行或命令。
> 三处阅读限制（先读这三句再读全文）：
> ① 论文侧——25 篇的摘要逐条读过，**未逐页读 PDF**（`references/01-landscape.md:8`），
> 故论文相关表述最高到摘要级；
> ② 实现侧——12 个入库项目里 10 个读了源码，chatcfd 与 openfoamgpt 只有文档级；
> ③ 锚点全部是**项目内相对路径**——拿到单文件的外部读者只能核对 §0–§3 的论证本身，不能核锚点。
> 证据分级（`references/03-evidence-audit.md:9`）：E0 本机命令输出 / E1 本地源码 `path:line` /
> E2 仓库文档 / E3 论文摘要 / E4 二手转述（**E4 不进结论**）。第三方代码一律写
> `references/repos/<repo>/<file>:<line>`。
> **锚点简写规则（全文唯一一条）**：` :N ` 一律解析为「**上文最近一次出现的完整锚点**所在文件」。
> 表格不设例外——每行首个完整锚点即该行其余简写的基准。
> 两个术语：**v13** = OpenFOAM 13（Foundation 编号；ESI 另有一套 `v2312` 式编号，两者不是同一序列）；
> **K** = 某机制在本领域被**独立实现**的个数（口径见 `references/05-cross-project-matrix.md:13`），
> K 只说明"不是孤例"，不说明"被验证有效"。

## 0 三句话

1. **背景**：领域重复劳动集中在「让模型看懂 OpenFOAM 字典」这一层（25 篇摘要里 11 篇提检索、
   其中 7 篇各自建库，`references/01-landscape.md:20`），而最薄弱的一环是「怎么知道跑成功了」
   （25 篇摘要里 0 篇提 `checkMesh`，`references/01-landscape.md:21`）；版本则分散在 v10 / v12 / v13 /
   v14 与 v2306–v2412 五段，与本机同版的只有 1 个（`references/01-landscape.md:189`）。
   **已被否掉的是** RAG 索引、微调、全角色多 agent、全量 MCP 封装、LLM／视觉裁判——否掉的理由是
   体积与可复算性，不是效果（§1.4、§3.5）。
2. **最小骨架**：6 个部件（需求解析 / grep 检索 / case 生成 / 求解执行 / 门禁判定 / 失败反馈修复）。
   判定权交给**命令输出 + 脚本校验**：模型仍决定"改什么"，但不再决定"过没过"（`references/00-project-readme.md:76`、`:77`）。
   8 条机制候选里只有两条落在「强」档——确定性门禁与失败反馈环（`references/05-cross-project-matrix.md:150`）。
3. **理论来源**：14 条机制映射为 3 条只写出名字 / 3 条只用了现成库 / 3 条纯自制 / 5 条只能算同构，
   外加 9 条形似配对已排除（`references/07-theory-provenance.md:182`）；**明示级只有 3 个名字、0 个
   arXiv id**，且这 3 条各有问题：RAG 名字写全了但实现是词袋、ReAct 名字写在 README 而实现是现成
   构造器、Reflexion 只写了小写 XML 标签（名字根本没写出，见 §3.2）。

## 1 背景：这个领域在解决什么，哪些路线站得住

### 1.1 出发点

1. **门槛在语法与版本，不在物理**：20 个候选里声明 v13 的只有 1 个，其余分属 v14（2）、v12（1）、
   v10（3）、2023/2024 系（7）与未声明（6），照着论文复现会先在版本上失败
   （`references/01-landscape.md:189`）；别人写的 prompt 与字典按 v10–v2412 写，不能当 v13 的语法证据（`:183`）。
2. **重复劳动集中在「让模型读懂字典/教程」这一层**：25 篇摘要里 11 篇提到检索，其中至少 7 篇各自
   建了自己的检索或知识库，彼此不共享且都绑定各自语料版本（`references/01-landscape.md:20`）。
   代价是同一份 tutorials 被反复切块索引，而索引一旦离开它对应的语料版本就不可用
   （`references/01-landscape.md:113`）。
3. **缺「跑完了算不算成功」的判据**：25 篇摘要里提 `checkMesh` 的为 0 篇，给出完成情况数字的 7 篇
   全部以 solver 退出码或日志标记为准（`references/01-landscape.md:21`、`:187`）。退出码只说明
   「没崩」：有算例 solver 正常跑完、平均阻力也收敛，侧向力仍在振荡而被拒收
   （`references/01-landscape.md:159`）。
4. **要闭环：生成 → 跑 → 诊断 → 修**：修复轮的有无在同一篇工作内部造成差异，差异显著（见 §1.3）
   （`references/01-landscape.md:103`）。这要求 harness 能读回执行反馈再生成，而不是一次性交付算例
   （`references/01-landscape.md:102`）。

### 1.2 六条技术路线的结构性代价

本节用**两套互不换算的分类**，先说明它们的分工：
**下表 6 条路线按「实现形态」分**（一个系统长什么样：单 agent / 多 agent / 带检索 / 微调 / 纯文本 /
工具化），取自 `references/01-landscape.md:98`；
而 §3.1 与 §2.2 的 **8 条机制候选（C1–C8）按「机制」分**（tutorial 派生 / grep / 门禁 / 修复环 /
记忆 / 工具封装 / 状态机 / 版本断言），K/E/V 口径见 `references/05-cross-project-matrix.md:13`–`15`，候选表在 `:100`–`109`。
两者不是同一把尺、不能互相换算——同一个"路线"里可以有多条"机制"，反之亦然。
8 条候选按「收敛度 × 证据强度 × 版本无关性」机械落成强 / 中 / 弱三档，强档只有两条：确定性门禁（K=7）、
失败反馈环（K=6）（`references/05-cross-project-matrix.md:150`、`:152`）；该评级只表达这三重属性、
**不表达实测绩效**，也没有分母（`:143`、`:146`）。

| # | 路线 | 代表（≤3） | 机制一句话 | 可判定的站得住点 | 结构性代价 | 本项目取舍 |
|---|---|---|---|---|---|---|
| 1 | 单 agent 循环 + 通用 harness | 2609.03718、2602.11689、CFD Forge | 一个模型 + 读写/执行工具 + 反馈修复环（`references/01-landscape.md:102`） | 修复环有同篇消融对照（`:103`） | 无反馈即无增益，须外部检查器兜底（`:103`） | 采纳 |
| 2 | 多 agent 角色分工 | 2505.04997、2506.02019、HarnessFOAM | 固定角色 + 结构化交接对象（`:107`） | 交接对象是 pydantic/JSON，可机器读（`:107`） | 角色边界靠 prompt，无硬接口（`:108`） | 不采纳 |
| 3 | 检索增强（RAG） | 2501.06327、DeepFlow、cfd-agent | 切块嵌向量或建倒排，按查询拼 prompt（`:112`） | 预整理的模板库是明文 JSON，可被 grep 逐条核对（`:137`） | 索引与语料版本一对一，体积超线（`:113`） | 不采纳 |
| 4 | 微调 | 2504.09602、2608.00003 | 「自然语言 → 字典」当监督学习（`:117`） | 数据规模可核：28716 对 vs 252 条（`:118`） | 固化即与版本脱钩，数据不公开（`:118`） | 不采纳 |
| 5 | agent-skill 文本集 | hpc-skills、AI-CFD-Scientist | 领域知识写成渐进加载的 markdown（`:122`） | 体量可核：22 个 skill / 19 KB / 56 KB 三档（`:121`） | 零执行门禁，正确性只能靠人读（`:123`） | 部分采纳 |
| 6 | MCP 工具化 | openfoam-mcp-server、HarnessFOAM | 动作封成 JSON-RPC tool（`:127`） | 门禁可放进 tool 返回值（`:128`） | 工具粒度即能力上限，不解版本与判据（`:128`） | 不采纳 |

取舍列只判「机制是否踩本项目的硬约束」，不判效果：路线 2 借的是其中的判据层、不是角色数量
（`references/05-cross-project-matrix.md:130`），路线 5 借的是文本组织方式、不收它的版本声明
（`references/01-landscape.md:123`）——「部分采纳」只指向能拆走的部件，不指向整条路线
（`references/05-cross-project-matrix.md:130`）。

### 1.3 唯一可用的量化对照（各文自己内部的消融，非我们实测、我们未复现）

> 百分号在全报告只出现于两处：本节的表，以及附录 A 里对源文档的逐字引用窗口。四行分属**两篇不同
> 工作**，数字不可互相换算。

| 结论 | 数字 | 来源（该文内部） | 口径限制 |
|---|---|---|---|
| 单 agent vs 多 agent（同等信息与修复预算） | 96.4% vs 88.2% | 2609.03718 摘要（`references/01-landscape.md:18`） | 该文自报，我们未复现 |
| 有无修复轮 | 71.8% → 96.4% | 2609.03718 同篇消融（`:103`） | 该文自报，我们未复现 |
| scripted reflection 的增益 | 原句 "adds nothing"，未给数字 | 2609.03718 同篇消融（`:139`） | 该文自报 |
| 去掉 Solver Template DB 后的 accuracy（该文原句 "collapses accuracy to 48%"） | 48% | **另一篇**：2506.02019 消融（`:137`） | 该文自报，我们未复现；与上三行不可换算 |

以上数字全部来自各文自报，我们一次也没跑过，只说明「这条路值不值得抄」，不能用来说明我们做得如何；
四行分属两篇不同工作、不可换算，也不可拼成一条跨臂结论（`references/03-evidence-audit.md:112`）。

### 1.4 五条已被证否或成本过高（机制级）

下表的否定理由全部落在体积、可复算性与接口位置三处，与「效果没达到」无关——效果我们没有任何
可跑臂可比（`references/05-cross-project-matrix.md:146`）。

| # | 不采用的东西 | 可量化代价 | 锚点 | 一句话理由 |
|---|---|---|---|---|
| 1 | RAG 层（向量索引 + 嵌入模型） | chatcfd 随仓库 562 MB、cfd-agent 66 MB；foam-agent 的索引文件是 133 字节 LFS 指针（声明 size 64026283） | `references/05-cross-project-matrix.md:128` | 体积超本项目「单项目 ≤100 MB」上限，语料与版本一对一 |
| 2 | 微调 | 28716 对 vs 252 条；推理侧 ≥24 GB 显存 | `references/05-cross-project-matrix.md:129` | 数据不公开不可比，固化即脱钩 |
| 3 | 全角色多 agent 拆分 | 6–7 个 LLM 角色 × 最多 3 轮，每轮上下文 2500 字符 | `references/05-cross-project-matrix.md:130` | 角色边界靠 prompt，失败被摊薄 |
| 4 | 全面 MCP 封装 | 主程序只注册 9 个 tool（另有 7 个只在测试程序里注册）；默认 solver 写死 `simpleFoam` → v13 无此可执行，恒 127 退出 | `references/05-cross-project-matrix.md:131` | 粒度即上限，且不解版本与判据 |
| 5 | 视觉/LLM 物理门禁 | 判据 `"correct" in response.content.lower()`，`"incorrect"` 即命中 `"correct"` → 趋近恒 PASSED | `references/05-cross-project-matrix.md:132` | 判据不可复算，同图两次判读可不同 |

唯一保留了层次的是视觉物理门禁：「物理是否像话」值得留，但须先改成结构化枚举 + 显式阈值（`:132`）；
其余四条在本机都没有可落地形态——索引须重建、权重须私有、tool 面没有第二个消费者（`:128`、`:131`）。

### 1.5 领域的六个空白（在这 25 篇摘要的范围内）

六条按 `references/01-landscape.md:185` 的原顺序列出（原顺序不是按"我们能不能补上"排的，本报告未重排）；
每条末尾的「——」后是它对我们的含义。

1. **网格质量不进验收判据**：25 篇摘要提 `checkMesh` 的为 0 篇，最细的实现也只判「无 `FOAM FATAL` + 有 `ExecutionTime` 与 `End`」（`references/01-landscape.md:187`）——把 `checkMesh` 的 `Mesh OK.` 当验收判据（下称 **G2**）在这 25 篇摘要覆盖的范围内未见有人做，是否全领域如此未核（我们未读全文）。
2. **没有「检索层 vs grep」的对照**：所有 RAG 工作的对照臂都是「无检索」，不是「换一种检索」（`:188`）；这是证据缺口，不是反例——我们的 grep 选择既未被复现，也未被反驳（`:136`）。
3. **版本断代**：20 个候选里 v13 的 1 个、14 的 2 个、12 的 1 个、10 的 3 个、2023/2024 系 7 个、未声明 6 个（`:189`）——这让「这行命令能不能跑」在跨版本比较里没有确定答案，也是把版本固定为 v13 的原因（`:183`）。
4. **成本只报 token，不报存储**：25 篇里给每例 token 与费用的只有 2506.02019，无一篇报索引体积（`:190`）——我们在上一阶段检索层实验里自测的 98 MB 只能记为「我们自己的实测」，不是领域已验证（`references/03-evidence-audit.md:120`）。
5. **结果状态多为二值**：给出完成情况数字的 7 篇无一篇定义「没产出任何 case」该记什么，唯一在代码里区分「不可判定」的是 HarnessFOAM 的 `SKIPPED`（`references/01-landscape.md:191`）——该态在我们这里独立成七态之一 `no_artifact`。
6. **微调数据不可比、不公开**：28716 对与 252 条差两个数量级，两篇都未给数据集链接，也没在共同测试集上比过（`references/01-landscape.md:192`）——「值不值得微调」在本领域目前无法回答，故不作为本阶段的选项。

合起来看，**纯属我们自己净增量的只有一处**：把 `checkMesh` 的 `Mesh OK.` 当验收判据
（`references/01-landscape.md:187` 原句即为「我们的 G2 相对领域的净增量」）。另两处是**把别人已有、
领域多数没有的做法补进自己的门**，不是首创：`no_artifact` 态在 HarnessFOAM 的代码里已经实现
（`references/01-landscape.md:167` 原句「它已经在代码里做了，我们还在文档里」）；版本运行时断言同样
先在 HarnessFOAM 出现（`:183` 原句「它把版本号做成了运行时断言……这也是它成为唯一 tier A 的原因」），
我们复用它的判定结构。三处都不需要装第二个 OpenFOAM，也不依赖任何跨项目数字，共同点是判定不交给
模型、而交给能落盘的命令输出（`:159`、`:170`）。

> 关于版本断言的边界（避免与 §2.3、§4-2 打架）：**砍掉的是独立的前置版本检查部件**；§4-2 要求并进
> G3 的那一行日志断言是同一信号的零成本形态，不新增部件、不新增一次调用——两者不矛盾。

## 2 第一性原理：最少需要什么

### 2.1 从一句话到一个跑得起来的 case：五段

`references/06-agent-anatomy.md:307` 论证的是 **6 个部件**各自不可再减，不是"五步"。下面按
**产出物**把它归并成 5 段——**这个归并是本报告的整理，不是 06 的结论**：段 1 与段 2 是部件 1 的
入口与出口，段 3 是部件 2，段 4 是部件 3 + 部件 4，段 5 是部件 5 + 部件 6。README §5.1 把这套动作
写成 7 行命令链（`references/00-project-readme.md:131`），其中 `verify：G1 → G2 → G3` 一行就是本文段 5（`references/00-project-readme.md:136`）。

1. **自然语言需求** —— 用户原话，无 schema，四元组的唯一来源（`references/06-agent-anatomy.md:309`）。
2. **结构化需求（四元组）** —— 几何 / 物性 / 边界条件 / 求解目标；任一键为空即停、不许填默认值，
   否则「需求没被满足」会被悄悄转成「门全过」（`references/06-agent-anatomy.md:59`；
   停下问用户的规则见 `AGENTS.md:194`）。
3. **找到可用模板与正确语法** —— 在 `$FOAM_TUTORIALS` / `$FOAM_SRC` 上按字面 grep 取路径与行段；
   派生源必须是命中结果，不能凭印象指定（`references/00-project-readme.md:83`、`AGENTS.md:141`）。
4. **产出 case 文件树并执行** —— 从命中 tutorial 派生、改写字典、写 `case.meta`，再起子进程，
   收退出码与固定名日志（`references/00-project-readme.md:79`、`references/00-project-readme.md:182`）。
5. **判定（不满意则回到段 4）** —— 对文件树 / 网格 / 日志做纯函数判定并出退出码；这一回路带轮数
   上限与 `attempt_<n>/` 整目录备份，`attempt >= max_attempts` 时必须返回终止
   （`references/00-project-readme.md:230`、`references/06-agent-anatomy.md:149`）。

段 4 与段 5 必须由脚本接管：「能不能跑」不能由模型自述，只能由命令输出的退出码与关键日志行判定
（`references/00-project-readme.md:76`、`:77`）。这不表示模型在这两段不出现——改哪一个 entry、下一轮修什么仍由模型决定，
被移出模型的是「过没过」这件事本身，而不是「怎么改」（`references/00-project-readme.md:215`、`:228`）。

### 2.2 最小骨架：6 个部件

门名缩写（`references/00-project-readme.md:180`–`184`）：**G1** 结构齐全 · **G2** `checkMesh` 含 `Mesh OK.` ·
**G3** 短跑无 `FOAM FATAL` 且退出码 0 · **G4** 末时刻场可读 · **G2b** 是辅助信号不是门；
**G5 范围门**（改动不得越出请求范围）只在预注册里定义（`bench/preregistration.md:89`），README 尚未写入。

| # | 部件 | 职责（一句） | 输入 → 输出 | 判定归属 | 支撑（K 或规则） | 唯一性 |
|---|---|---|---|---|---|---|
| 1 | 需求→四元组解析 | 把一句话翻成四个可填槽位 | 原话文本 → 四元组 dict | 模型+脚本校验 | K 不适用（非候选机制） | 入口唯一：无它则后五件输入类型不存在（`references/06-agent-anatomy.md:309`） |
| 2 | 知识检索（grep） | 在 tutorials 与 src 上按字面取路径与行段 | 关键词 + 固定搜索根 → `path:line` 命中 | 脚本 | K=3（`references/05-cross-project-matrix.md:103`） | 派生源只能由它产出（`references/06-agent-anatomy.md:311`） |
| 3 | case 生成 | 从命中 tutorial 派生并改写字典 | 派生源 + 四元组 → `cases/<id>/` 树 | 模型+脚本校验 | K=3（`references/05-cross-project-matrix.md:102`）+「一切 case 从最近的 tutorial 派生」（`references/00-project-readme.md:79`） | 唯一产出 case 树者（`references/06-agent-anatomy.md:313`） |
| 4 | 求解执行 | 起子进程跑命令，收退出码与日志 | case 目录 + 步数 → `log.*` 与 returncode | 脚本 | K 不适用（非候选机制） | 门禁层没有它就没有输入（`:315`） |
| 5 | 门禁判定 | 对文件树 / 网格 / 日志做纯函数判定 | case + 日志 → 退出码 0–4（`references/00-project-readme.md:230`） | 脚本 | K=7、强档（`references/05-cross-project-matrix.md:104`） | 唯一把「能跑」移出自述（`references/06-agent-anatomy.md:317`） |
| 6 | 失败反馈与修复 | 失败串定位到文件与 entry，改完重跑 | 失败串 + attempt → 新字典 + 备份 | 模型+脚本校验 | K=6、强档（`references/05-cross-project-matrix.md:105`） | 唯一让一次生成变成收敛（`references/06-agent-anatomy.md:319`） |

部件 1 与部件 4 标「K 不适用（非候选机制）」：它们是任何 agent 都有的步骤，K 恒等于实现数、
不携带信息（`references/06-agent-anatomy.md:342`、`:346`）。判定归属一列只取三值，6 行里 0 行是
纯「模型」——`references/06-agent-anatomy.md:38` 明写这一栏为空是本项目「翻译归模型、判定归脚本」
原则的直接结果；同一分法用在完整版 11 个部件上是 6 个脚本 / 5 个模型+脚本 / 0 个纯模型（`:388`）。

### 2.3 砍掉的 5 件与各自的加回触发条件

| # | 暂时不写 | 现在不写的理由 | 加回触发条件（可判定） |
|---|---|---|---|
| 1 | 阶段状态机 | 单趟跑完即结束，退出码已按 G1–G4 分流（`references/00-project-readme.md:230`） | `runs/<batch>/<case_id>/` 下出现第二份 `log.run` 且不在 `attempt_<n>/` 里（`references/06-agent-anatomy.md:324`） |
| 2 | 反思记忆 | 落账本本身不产生增益，可检索复用才可能（`references/05-cross-project-matrix.md:106`） | 同一 FATAL 首行出现在 ≥3 个不同 case 的 `log.shortRun`（`references/06-agent-anatomy.md:326`） |
| 3 | 工具接口（MCP / function calling） | 本阶段没有第二个消费者，MCP 已否决（`references/00-project-readme.md:120`） | 出现第二个消费者且参数形状与现有 CLI 不同（`references/06-agent-anatomy.md:329`） |
| 4 | 版本断言（独立的前置检查部件） | 只允许一份 OpenFOAM、版本号恒定，本项目禁装第二份（`AGENTS.md:238`）；§4-2 并进 G3 的是同一信号的一行日志断言，不新增部件 | `ls -d /opt/openfoam*` 的行数 > 1，或换机复跑成为验收要求（`references/06-agent-anatomy.md:332`） |
| 5 | 人机停点 | 修复轮数到顶本身就是停点（`references/06-agent-anatomy.md:335`） | 同一 case 连续 2 次非 0 退出且失败串首行相同（`:334`） |

第 5 条的触发条件与「G1–G3 连续两轮修不好就停下问用户」这条规则同构（`AGENTS.md:197`、
`references/06-agent-anatomy.md:335`），第 4 条在当前约束下只能经「允许装第二份版本」的豁免才生效
（`references/06-agent-anatomy.md:333`）；五条判据都落在具体文件与具体条件上，没有一条写成「当需要时」。

### 2.4 「轻」具体指什么（四条可判定含义）

1. **零索引** —— 知识层就是 `$FOAM_TUTORIALS` 与 `$FOAM_SRC`，取用方式是 grep；不建索引、不做
   向量检索（`references/00-project-readme.md:53`、`AGENTS.md:36`）。
2. **零服务** —— 无 MCP、无 GUI/Web（`references/00-project-readme.md:53`、`:56`、`:120`）。
3. **单版本** —— `ls -d /opt/openfoam*` 只有 `openfoam13`（`AGENTS.md:238`、`:259`）。
4. **依赖面** —— 只有 v13 自带命令：`blockMesh` / `checkMesh` / `foamRun` / `foamDictionary` /
   `foamCloneCase`（`references/00-project-readme.md:17`、`:23`、`:25`、`:108`、`:182`、`:183`），加一个 LLM 模型调用
   （分工见 `references/00-project-readme.md:76`：LLM 做翻译与决策、脚本做判定与调度）；不含向量库（`references/00-project-readme.md:53`）；
   批跑入口是 `batch.py`（`references/00-project-readme.md:266`）。

代价：几何能力上限低（`references/00-project-readme.md:51`：不做 STL/CAD、不做 `snappyHexMesh`），也不判物理正确性
（`references/00-project-readme.md:57`）；这是刻意取舍、不是待办，两条都写进了「本版本明确不做」（`:49`）。

### 2.5 三个不可省略的部件

§2.2 说的是功能上缺一断链；这里再收紧一层，按「证据强度 + 结构单向依存」只剩 3 根承重柱。理由只取
两类依据：机制候选的强档评级 / K 值，或 `README.md` 的派生规则与结构单向依存
（`references/06-agent-anatomy.md:305`）。

1. **门禁判定** —— 确定性门禁 K=7、评级「强」（`references/05-cross-project-matrix.md:104`）；
   它是唯一把「能不能跑」从 agent 自述移到命令输出的部件（`references/00-project-readme.md:76`）。
2. **失败反馈与修复** —— 失败反馈环 K=6、评级「强」，是 8 条候选里落强档的两条之一
   （`references/05-cross-project-matrix.md:105`、`:152`）；没有它，智能体退化为一次生成器，
   没有第二次机会（`references/06-agent-anatomy.md:412`）。
3. **case 生成** —— 结构单向依存：删掉它，部件 5 没有判定对象、部件 6 没有修复对象，这条依存不能
   用别的部件替代（`references/06-agent-anatomy.md:416`）；它同时是「一切 case 从最近的 tutorial
   派生」这条规则的落地处（`references/00-project-readme.md:79`）。

## 3 参考了哪些 AI 工程经验与理论

本节只建立「来源关系」，不建立「效果验证」：某一档成立不等于该架构有效
（`references/07-theory-provenance.md:254`）。分级判据取自 `07` 的 §0：L1 = 代码或论文里写出了理论名
或论文 id，L2 = 机制逐条对得上但项目没有引用文本，L3 = 只有一个模糊相似点
（`references/07-theory-provenance.md:11`、`:12`、`:13`）。L1 再分学术与工程两个子档，另设 P-实践档
承接「连库都没 import」的机制（`:28`、`:29`、`:32`）。（本节简写服从文首唯一规则：取上文最近的完整锚点，故 §3.1–§3.3 里多数简写指
`references/07-theory-provenance.md`。）

### 3.1 计数结论：14 条机制 → 3 / 3 / 3 / 5

| 级别 | 条数 | 是哪些机制 | 允许的写法 |
|---|---|---|---|
| L1-学术（写出理论名） | 3 | 检索层自称 RAG、失败反思块写成 `<reflexion>`、主循环自称 ReAct | 「引用」，只到名字级 |
| L1-工程（import 库/调现成工具） | 3 | tutorial 派生用现成 `foamCloneCase`、工具封装用 `FastMCP`、流程编排用 `LangGraph`/`MetaGPT` | 「选了某个库」，非学术传承 |
| P-实践（无库、无理论名，纯自制） | 3 | 手写 grep + 词袋打分、退出码 + 自写打分函数、自写版本正则 | 「纯工程实践，无出处」 |
| L2 同构（机制对得上、无引用文本） | 5 | 执行结果作批判信号（CRITIC）、反思落盘复用（Reflexion）、技能入库门控（Voyager）、接口粒度（SWE-agent ACI）、让模型当裁判（LLM-as-judge） | 只许「与 X 同构」 |
| L3 形似（已排除，不进分母） | 9 | 5 条对论文/算法、4 条对工程范式 | 不得引用为论据 |

分母是 `07` §1.1 主表的 14 行：一行一条机制、一行一个级别，不重复计；L3 的 9 条单独数、不进分母
（`references/07-theory-provenance.md:184`、`:210`、`:216`）。同一篇 Reflexion 在「名字被写出」与
「记忆机制对得上」两格各出现一次，不是重复计数（`:66`）。**3 + 3 + 3 + 5 = 14**；L3 的 9 条不计入
这个和，所以全表加起来是 23，不是 14。

数据来源（`07` §4 的三条命令，原样输出）：

```bash
$ sed -n '/^## 1 /,/^## 2 /p' references/07-theory-provenance.md | awk -F'|' '$2 ~ /^ *(C[0-9]|补)/' | wc -l
14
$ sed -n '/^## 1 /,/^## 2 /p' references/07-theory-provenance.md | awk -F'|' '$2 ~ /^ *(C[0-9]|补)/ {gsub(/^ +| +$/,"",$6); n[$6]++} END{for(k in n) print n[k], k}' | sort -rn
5 L2
3 P-实践（无理论来源）
3 L1-工程（无论文）
3 L1-学术（仅名字，无 id）
$ sed -n '/^## 3 /,/^## 4 /p' references/07-theory-provenance.md | awk -F'|' 'NF==5 && $2 ~ /vs/' | wc -l
9
```

免责（本节面向外部评审）：这 25 篇的来源判定只基于摘要与仓库可见代码，**未逐页读 PDF**
（`references/01-landscape.md:8`）；其中 2 个项目（chatcfd、openfoamgpt）只有文档级证据、无源码，
其实现细节不得写成实现（`references/registry.csv:12`、`:13`、`references/03-evidence-audit.md:116`）。

### 3.2 明示级的三个名字、零个 id

1. **RAG** —— harnessfoam 的 README 把 "Retrieval-Augmented Generation" 写成功能项名
   （`references/repos/harnessfoam/README.md:96`），但同仓检索实现是词袋打分
   （`references/repos/harnessfoam/harnessfoam/knowledge.py:103`），无嵌入模型，故名字与机制不同层。
2. **Reflexion** —— ChatCFD 论文 §2.4 把反思写成 `<reflexion>` 标签块并并入反思历史
   （`references/02-architectures.md:1868`），但全文只有小写 XML 标签、**未出现理论名 "Reflexion"**，
   此格属边界成立（`references/07-theory-provenance.md:54`）。
3. **ReAct** —— deepflow 的 README 有一句 "decision-making loop based on the ReAct framework"
   （`references/repos/deepflow/README.md:31`），其实现是 LangChain 现成的 agent 构造器（`references/07-theory-provenance.md:61`）。

三条都停在名字级：**本领域无一条写出 arXiv id**（`references/07-theory-provenance.md:232`、`references/07-theory-provenance.md:249`）。用 LangGraph 不等于引用 ReAct、
用 FastMCP 不等于引用任何工具学习论文——库只证明「这个轮子被装上了」，不证明「某个学术结论被继承」
（`references/07-theory-provenance.md:243`）。

### 3.3 同构级 5 条与本领域的反例

| # | 机制 | 对着哪个理论（L2） | 本领域的实现 | 本领域的反例 |
|---|---|---|---|---|
| 1 | 执行结果作批判信号 | CRITIC（`references/07-theory-provenance.md:53`） | foam-agent 错误指纹守卫（`references/repos/foam-agent/src/nodes/reviewer_node.py:23`） | autofoam 认不出 FATAL 指名文件即 `return None`，定向修复空转（`references/repos/autofoam/openfoam_agent/dict_fix.py:106`） |
| 2 | 跨试次留文本经验 | Reflexion 的 verbal memory（`references/07-theory-provenance.md:55`） | harnessfoam 写 `failure_ledger.jsonl`（`references/repos/harnessfoam/harnessfoam/agents/graph.py:317`） | 账本汇总只进 API 返回串、不回流 prompt；记忆开关默认关（`references/repos/harnessfoam/README.md:65`） |
| 3 | 技能入库门控 | Voyager（`references/07-theory-provenance.md:56`） | nullflux 无 `*_verify` 通过即拒绝 `skill_save`（`references/repos/nullflux/server.js:3719`） | 无反例，但该候选的 K=2，只有 nullflux 一家有入库门控（`references/05-cross-project-matrix.md:106`） |
| 4 | 接口粒度即能力上限 | SWE-agent ACI（`references/07-theory-provenance.md:58`） | harnessfoam 两套粒度并存（`references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8`、`references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6`） | openfoam-mcp-server 主程序只注册 9 个（4 个单工具 + 1 个注册函数注册的 5 个独立工具），另 7 个只在测试程序（`references/repos/openfoam-mcp-server/src/main.cpp:53`、`references/repos/openfoam-mcp-server/src/tools/cfd_assistant_registration.cpp:102`、`references/repos/openfoam-mcp-server/src/main_test.cpp:52`） |
| 5 | 让模型充当裁判 | LLM-as-judge（`references/07-theory-provenance.md:52`） | harnessfoam 第五道视觉闸（`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100`） | 判据 `"correct" in …`，而 `"incorrect"` 含 `"correct"` → 趋近恒 PASSED（`references/05-cross-project-matrix.md:132`） |

第 3 行是本节唯一没有反例的行：不是没找出反例，而是该入库门控在本领域只有 nullflux 一家实现
（该候选 K=2，harnessfoam 侧只有账本、没有入库门控），凑不出反面样本
（`references/05-cross-project-matrix.md:106`）。其余四行的反例说明同一件事：**有来源不等于有效**
（`references/07-theory-provenance.md:255`）。

### 3.4 我们实际采纳的工程经验（4 条）

| # | 采纳项 | 来源级别 | 在本项目落成什么 |
|---|---|---|---|
| 1 | 校验门控终止 / 确定性门禁 | P-实践（领域侧 K=7、同篇有对照） | 「可运行」= G1–G3 全过，agent 自述不算证据（`AGENTS.md:149`） |
| 2 | 执行反馈修复环 | L2（与 CRITIC 同构，领域 K=6） | 错误→定位→改文件→重跑，带轮数上限（`references/05-cross-project-matrix.md:105`） |
| 3 | 契约 + 七态判定 | P-实践 + 契约测试 | 冻结清单逐文件 `sha256sum -c`；`no_artifact` 是七态之一（`references/07-theory-provenance.md:139`、`AGENTS.md:257`） |
| 4 | case.meta ↔ 统一的 case 清单 | L1-工程 | 每 case 写 `case.meta`（来源 tutorial、四元组、改动清单），`source` 必须真实存在（`AGENTS.md:143`） |

第 1、2 行的领域侧证据与反例同表并列（`references/05-cross-project-matrix.md:104`、`:105`）；第 3 行
对应领域侧「`SKIPPED` 不算假过」（`references/repos/harnessfoam/harnessfoam/physics_validation.py:46`、
`references/01-landscape.md:167`）；第 4 行的对照是领域三家各自手写复制、无统一清单
（`references/05-cross-project-matrix.md:102`）。

本项目自有方法论（非本领域来源）——四条都不来自论文：

1. **测量前先定判定器**：先写「怎样算通过」再动手（`references/07-theory-provenance.md:285`）。
2. **自报不可采信**：agent 声称完成不算证据（`references/07-theory-provenance.md:286`）。
3. **预注册冻结**：判据与作废条件先冻结再跑，注册制来自实验科学而非本领域论文（`references/07-theory-provenance.md:142`）。
4. **门禁变异自测**：冻结前后各跑一轮，证明门禁真的会红（`bench/preregistration.md:483`）。

这四条在 `references/07-theory-provenance.md` 里没有 L1/L2 标签——前两条承自上一阶段的实验方法论
（`references/07-theory-provenance.md:285`、`:329`），后两条分别是注册制与门禁自测。

### 3.5 明确不采纳的 3 条

1. **LLM-as-judge 充当终判**：终判落在模型输出上，同一输入两次判读可以不同，违反「判据须可重算」，
   故只在 §3.3 记为同构、不进我们的判据层（`references/07-theory-provenance.md:52`、
   `references/05-cross-project-matrix.md:132`）。
2. **视觉物理门禁**：判据写成 `"correct" in response.content.lower()`，而 `"incorrect"` 含 `"correct"`，
   且提示词自身也含 `correct`，该闸趋近恒 PASSED（`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100`、`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:92`）。
3. **嵌入检索（RAG）**：知识库体积与 OpenFOAM 版本一对一，同时违反「单项目体积上限」与「只允许一份
   OpenFOAM」两条硬约束，且同任务集内没有「检索层 vs tutorial 上 grep」的对照
   （`references/05-cross-project-matrix.md:128`）。

## 4 施工顺序（内部实施路径，供评审判断成熟度）

本节**不回答上面三个问题**，只让评审看到「研究报告 → 可跑系统」之间还缺什么。当前状态：
`bench/results.csv` 只有表头、`bench/runs/` 为 0 项、一行被测代码都没跑。

1. **单例闭环**：落 `scripts/new_case.sh` + `verify_case.sh`，直接复用 `references/00-project-readme.md:180`–`184` 的
   G1–G4 与 G2b、`bench/preregistration.md:89` 的 G5、`bench/assert_lib.py` 的取值实现（`STATUS.md:121`）。
2. **门禁补三条**（`references/01-landscape.md:170`）：G3 增「日志版本行 == 13」；G1 增「`0/U`、`0/p`
   的 patch 集合 == `constant/polyMesh/boundary` 的 patch 集合」（这一条**与原 `references/00-project-readme.md:223` 的判断不同**：那里以「G3 反正会 FATAL」为由
   不单独设门，属效率考虑；这里是 fail-fast 取舍——多一次比对，换「不必跑完才知道」。不是否认
   README 的理由，是明确改判）；G4 增「场值有限 + 一个与物理量级挂钩的上限」。
3. **七态归约自测**：`bench/judge.py` + 12 个合成 fixture（7 态 + 5 边界），必须打印 `checked=12`；
   未补上之前不许出任何跨臂结论（`STATUS.md:132`）。
4. **`***` 的 soft 分支**：从 `$FOAM_TUTORIALS` 派生 1 个 case，记录「`***` 行数 > 0 且 `Mesh OK.`
   同时存在」的实测样例（`STATUS.md:135`）。
5. **人工干预计数口径**：三个候选 (i)/(ii)/(iii) 未选（`bench/preregistration.md:408`），裁定前只写
   `unmeasured`（未测量，不是 0）。
6. **最后才是实跑**：补预注册 §10 每臂预测 → 冻结补填 → `adapters/` 适配 → 跑 12 个任务
   （§10 不在冻结内，`bench/preregistration.md:420`）。

## 5 本报告不能回答什么

本节六条不是谦辞，是可判定的边界——每条都指明「为什么现在写不出来」与「需要什么才能写」。
**"臂"（arm）= 一次被比较的完整配置**：冻结时预定两条——基准臂（自研实现的 12 任务回归基线）与
参照臂（唯一能在 v13 直接跑的那个项目），任务集共 12 个（`bench/tasks/`）。
**基准臂尚未实现**（`bench/preregistration.md:439`），当前 0 条数据行。

1. **任何跨臂的比较性数字**（含把两个不同来源的百分比并列成一句）：`bench/results.csv` 只有表头
   （0 条数据行），`bench/runs/` 为 0 项，且本项目规定实跑前必须先冻结判据、设计期禁跑。
   没有分子分母，任何这样的数字只能来自编造或搬自别的实验（`references/03-evidence-audit.md:112`）。
2. **任何跨项目排序（含软排序）**：**A 档 = 与本机 v13 可直接跑**，B 档 = 需命令级适配，
   C 档 = 不可适配、只做静态分析（定义见 `references/01-landscape.md:64`）；A 档只有 1 个项目
   （`references/registry.csv` 实测 A=1 / B=10 / C=1），
   跨臂比较的前提不成立，退化路径在冻结时即已生效（`bench/preregistration.md:275`）。
   交付形态是「自研回归基线 + 单点参照 + 其余定性」。
3. **人工干预次数的任何数值**（含 0）：计数口径三选一未定，只许写 `unmeasured`
   （`bench/preregistration.md:446`）。
4. **chatcfd / openfoamgpt 的实现细节**：两项是文档级（`docs_only`，只读了 README 与论文、未读源码），
   只有 E2/E3 证据；把它们写成实现等于把文档冒充源码（`references/registry.csv:12`、`:13`）。
5. **预注册 §10 的每臂预测**：分段冻结的未冻部分，不是判据也不是证据，只能是待验证假设
   （`bench/preregistration.md:332`、`:420`）。
6. **脚注（一处已知笔误）**：预注册文档 §7 正文写「B=9」，而登记表实测、冻结记录与本项目的状态文档
   三处都是 B=10（`STATUS.md:152`）。本报告统一用实测值，正文那处按既定处置只在脚注说明。

## 附录 A 关键锚点核对表（12 条）

复核方式：对每行跑表内的命令，输出应与「命中片段」列一致（2026-10-28 实测）。
**本表只核「行号对不对 + 那一行里有没有这个数」；语义是否支撑整句话仍需逐条读原文。**

| # | 断言 | 取数命令 | 实测行号 | 命中片段（`grep -o` 的真实输出） |
|---|---|---|---|---|
| 1 | 25 篇摘要里 0 篇提 `checkMesh` | `grep -o -m1 '.\{0,22\}checkMesh' references/01-landscape.md` | 21 | `：25 篇摘要里 **0 篇**提到 ``checkMesh` |
| 2 | 25 篇里 11 篇提检索、7 篇各建库 | `grep -o -m1 '.\{0,20\}11 篇.\{0,34\}' references/01-landscape.md` | 20 | ` 字典」这一层**：25 篇摘要里 **11 篇**提到检索/RAG（附录 A 第 5 条），其中至少 **7 篇各` |
| 3 | 单 agent 与多 agent 的同篇对照 | `grep -o -m1 '.\{0,20\}88\.2.\{0,34\}' references/01-landscape.md` | 18 | `nt 96.4% vs 多 agent 88.2%（2609.03718 摘要逐字）。这是本领域对我们最重要的一条外` |
| 4 | 无修复轮 → 有修复轮的同篇消融 | `grep -o -m1 '.\{0,20\}71\.8.\{0,34\}' references/01-landscape.md` | 103 | `（2609.03718 摘要：无修复轮 71.8%，有修复轮 96.4%，而 scripted reflection` |
| 5 | scripted reflection 增益原句 | `grep -o -m1 '.\{0,20\}adds nothing.\{0,34\}' references/01-landscape.md` | 139 | `scripted reflection「adds nothing」。摘要只把 tutorial 点名为「唯一仍有帮助的输入」。我们的` |
| 6 | 去掉 Solver Template DB 后的 accuracy | `grep -o -m1 '.\{0,20\}collapses accuracy.\{0,34\}' references/01-landscape.md` | 137 | ` Solver Template DB collapses accuracy to 48%」。但它的机制是**预先整理的模板库**（结构化字段，` |
| 7 | 版本断代：20 候选中只 1 个声明 v13 | `grep -o -m1 '.\{0,20\}版本断代.\{0,34\}' references/01-landscape.md` | 189 | `3. **版本断代严重**：§2 的 20 个候选项目里声明 v13 的 **1**` |
| 8 | 8 条机制候选的强弱结论 | `sed -n '150p' references/05-cross-project-matrix.md` | 150 | `## 6 问题②的结论句（强 / 中 / 弱三档）` |
| 9 | 确定性门禁的 K、E、V 与「强」档 | `grep -o -m1 'C3 .\{0,60\}' references/05-cross-project-matrix.md` | 104 | `C3 ｜ 确定性门禁（判据是纯函数或命令输出，**不经模型**）｜ 7 ｜ 有对照 ｜ 无关 ｜ **强**` |
| 10 | 6 部件骨架与 11 部件完整版 | `grep -o -m1 '.\{0,10\}最小骨架.\{0,20\}' references/06-agent-anatomy.md` | 300 | `## 4 最小骨架（6 部件）与完整版（11 部件）的取舍` |
| 11 | 14 条机制映射的 3/3/3/5 计数 | `grep -o -m1 '.\{0,6\}计数（L1.\{0,24\}' references/07-theory-provenance.md` | 182 | `## 4 计数（L1/L2/L3 与「论文 / 工程实践」各几条，附` |
| 12 | 十条禁用主张（黑名单） | `grep -n -m1 '禁用主张' references/03-evidence-audit.md` | 106 | `## 4 禁用主张清单（黑名单）` |

本表是抽查样本，不替代全文回切。全文所有锚点（含 `README.md` / `STATUS.md` / `AGENTS.md` / `bench/`）走这条：

```bash
grep -oE 'references/[A-Za-z0-9._/-]+:[0-9]+|README\.md:[0-9]+|STATUS\.md:[0-9]+|AGENTS\.md:[0-9]+|bench/[A-Za-z0-9._/-]+:[0-9]+' \
  references/08-condensed-report.md | sort -u | while IFS=: read -r p l; do
    [ -f "$p" ] || { echo "MISSING $p"; continue; }
    n=$(wc -l < "$p"); [ "$l" -le "$n" ] || echo "OOR $p:$l > $n"
  done
# 期望：无 MISSING、无 OOR
# 注意：本命令只判「坐标能打开」，不判「打开的是不是那句话」——语义层必须人工逐条读该行。
```
