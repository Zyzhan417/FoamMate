# 11 · 交付形态：A（工具包 + 入口文档）vs B（自带模型的独立 CLI）

> 状态：**讨论稿**（2026-10-28）。未进入冻结切片，不参与任何门禁。
> 上游：`README.md` §8 里程碑、`references/06-agent-anatomy.md` §4（最小骨架与砍部件的触发条件）、
> `references/09-architecture-and-test-plan.md` §2-A（「接 LLM 时只换 `extract_quad`」）。
> 外部资料的本地副本见 `references/external/INDEX.md`；引用格式 `references/external/<file>:<行>`。

---

## 0 这份文档回答什么

**回答**：把本项目「发布出去给别人用」时应该选哪种形态——A（交脚本 + 入口文档，模型由宿主提供）
还是 B（交一个自带 LLM 的独立命令行程序），以及这个选择的理论依据、代价和不 reversible 的点。

**不回答**（越界即作废，口径同 `references/03-evidence-audit.md` §4）：

1. 不出任何跨臂比较数字。本文一条绩效数字都没有（R12 / `03` §4-1 的禁止项）。
2. 外部文献只作为**方法论证据**，不作为 OpenFOAM 源码事实（R9 的口径扩展到博客：五个
   `$FOAM_*` 搜索根仍回答「本机怎么写字典」，`references/external/` 只回答「别人怎么做 agent 工程」）。
3. 不替用户做决定。第 9 节给推荐与理由，第 12 节给**什么证据会推翻它**——这是决策题，不是结论题。

---

## 1 先理清名字：我们交的不是「agent」，是「harness」

外部三份权威定义彼此并不一致，而这个不一致正好落在我们要做的选择上。

| 来源 | 定义 | A 形态是否算「agent」 |
|---|---|---|
| Anthropic《Building effective agents》 | 「**Workflows** are systems where LLMs and tools are orchestrated through predefined code paths.」/「**Agents** … are systems where LLMs dynamically direct their own processes and tool usage」（`anthropic-building-effective-agents.md:20-21`） | **不算**。A 是 workflow |
| OpenAI《A practical guide to building agents》 | 「Applications that integrate LLMs but don't use them to control workflow execution—think simple chatbots, single-turn LLMs, or sentiment classifiers—**are not agents**.」（`openai-practical-guide-extracted.md:3`） | **不算**。A 里 LLM 不控制 workflow 执行 |
| Anthropic《Demystifying evals》 | 「An **agent harness** (or scaffold) is the system that enables a model to act as an agent … When we evaluate “an agent,” we're evaluating the **harness and the model working together**.」（`anthropic-demystifying-evals.md:37`） | **算 harness**（这正是 A 的准确名称） |

**结论 1（命名风险，必须先解决）**：按 OpenAI 那份最严的定义，A 形态交出去的东西**不能叫智能体**。
如果我们对外宣称「智能体」而交付的是 A，验收时对方拿 `openai-practical-guide-extracted.md:3` 一问，
我们立刻无法自洽。

**结论 2（A 的正确自称）**：A = 一个 **agent harness / scaffold** + 一份被 harness 读的文档。
这个称法不是文字游戏：`anthropic-demystifying-evals.md:37` 把「评估一个 agent」明确定义为
「评估 harness 与模型的组合」——这与本项目 `bench/` 的「臂（arm）」设计完全同构：
`bench/results.csv` 的 `arm` 列就是「harness 标识」，模型是可换的那一半。

**结论 3（B 的准确定位)**：B = A 的全部内容 + 一个具体 agent 实例（我们选定模型、选定循环、选定停点）。

---

## 2 形式化：分界线不是「有没有 LLM」，是「谁拥有裁决权与调度权」

### 2.1 两个定义

**定义 A（工具包 + 入口文档）**
存在一个外部宿主（Claude Code / Codex / 其它 CLI agent 或人），它读我们的入口文档，
按文档调用我们提供的 CLI。**我们的进程内不存在任何 LLM 调用**；门禁的退出码由宿主消费，
下一步由宿主决定。

**定义 B（自带模型的独立 CLI）**
我们的进程内含 LLM 调用，且由我们的代码决定：下一步调哪个脚本、失败后是否重试、
重试几次、什么条件下停止并交还给人。

### 2.2 一条 grep 就能判定自己在哪种形态（可判定，不用争论）

```bash
# 现状实测（2026-10-28，10-gap-register.md:222 同一条命令）
grep -rln 'openai\|anthropic\|api_key\|requests.post' scripts/ bench/
# （无输出）→ 当前处于 A 的骨架状态，且 A 的发布版必须保持这条为空
```

**推论**：A 的形态是可以被门禁式判定的（空 = A，非空 = B）。这比「架构文档里写我们是 A」强得多，
因为它不会因文档腐坏而失真（对照 `AGENTS.md` R13 的机制：能被命令测出来的才进机器段）。

### 2.3 数据流对照

```
A:  用户 → [宿主 agent 的循环] → 脚本 CLI → 退出码/日志 → 宿主读 → 宿主决定下一步
                                  ↑                          │
                                  └──── 宿主自己判断要不要回退 ┘

B:  用户 → [我们的 CLI 的循环] → 脚本 CLI → 退出码/日志 → 我们读 → 我们决定下一步
                                  ↑                          │
                                  └──── 我们的代码决定回退/重试/停 ┘
```

两条链的**中间那一层完全相同**（同一组脚本、同一套退出码、同一份门禁）。
差别只有一处：箭头回到谁手里。第 3–7 节的全部差异都由这一处派生。

---

## 3 外部理论：支持 A 的证据

### 3.1 「先取最简方案」——A 是官方推荐的第一步

> 「we recommend finding the simplest solution possible, and only increasing complexity when needed.
> This might mean not building agentic systems at all.」（`anthropic-building-effective-agents.md:27`）

同一篇对框架的批评也适用于「自己写一个 orchestrator」：

> frameworks 「often create extra layers of abstraction that can obscure the underlying prompts and
> responses, making them harder to debug.」（`anthropic-building-effective-agents.md:40`）

A 形态的实质就是「不写那一层，把它交给宿主」。这与 `references/00-project-readme.md:76-77` 的 P1
（「LLM 做翻译与决策，脚本做判定与调度」）同向：P1 里 LLM 的那一半本来就该由宿主提供。

### 3.2 skill 里可以、而且应该带确定性代码——A 不是「纯文档」

这条直接回答你提的问题「A 实际上就是个 skill 吧」：

> 「Skills can also include code for Claude to execute as tools at its discretion.」
> （`anthropic-agent-skills.md:70`）
>
> 「certain operations are better suited for traditional code execution … many applications
> require **the deterministic reliability that only code can provide**.」（`anthropic-agent-skills.md:72`）

也就是说，官方的 skill 形态本身就把「文档 + 可执行脚本」当作一个整体，
**不存在「纯 skill」与「带脚本的 skill」之分**——只有「脚本在不在包内」之分。
我们的 G1–G5 判据正好是那种「只有代码能提供的确定性可靠性」。

### 3.3 skill 格式已经跨平台标准化 → A 不绑死一家

> 「We've published Agent Skills as an **open standard for cross-platform portability**.
> (December 18, 2025)」（`anthropic-agent-skills.md:17`）

**这是 A 形态最重要的一条外部证据**：2025-12 之后，「入口文档 + 脚本」这种包不再是 Anthropic 私有格式。
补充一条来自项目内部调研的事实：`references/02-architectures.md:1738` 记录 hpc-skills 的立场是
「所有『角色』完全由宿主决定（Codex / Claude Code / 其它 CLI agent）」，仓库侧不定义 agent。

### 3.4 harness/trial/outcome 的定义与我们的 bench 同构

> 「Because model outputs vary between runs, we run **multiple trials** to produce more consistent
> results.」（`anthropic-demystifying-evals.md:32`）
>
> 「the **outcome** is the final state in the environment at the end of the trial … the outcome is
> whether a reservation exists in the environment's SQL database.」（`anthropic-demystifying-evals.md:35`）

前者正是 `bench/preregistration.md` 里「每任务跑 3 次取多数」的外部同型；后者正是我们
「G2 只 grep `Mesh OK.`、不看 agent 自述」的同型：**判据看环境终态，不看转述**。

同篇把 grader 分成 code-based / model-based / human 三类（`anthropic-demystifying-evals.md:68-70`），
我们全部押在 code-based 上，这是 A 与 B 都能继承的设计，不是形态选择。

---

## 4 外部理论：支持 B 的证据

### 4.1 「控制流自有」是 B 的核心论据

> 「**Factor 8: Own Your Control Flow** … If you own your control flow, you can do lots of fun things.
> Build your own control structures that make sense for your specific use case.」
> （`humanlayer-12-factor-agents.md:578`）

A 形态把控制流整块让给宿主，恰好放弃这一条。代价具体到本项目：
「F 修几轮后停下问人」（`max_attempts` 与 `declined`）的判定权不在我们手里。

### 4.2 OpenAI 的 HITL 触发条件必须由执行者实现

> 「**Exceeding failure thresholds**: Set limits on agent retries or actions. If the agent exceeds
> these limits … escalate to human intervention.」（`openai-practical-guide-extracted.md:304`）

这条要求「有个人在数重试次数」。A 形态下数数的是宿主；我们只能把 `max_attempts` 写进文档，
无法保证被执行。B 形态下它是程序流的一部分。

### 4.3 Anthropic 对 agent 的定义本身要求「动态决定」

> 「Agents … are systems where LLMs **dynamically direct their own processes and tool usage**,
> maintaining control over how they accomplish tasks.」（`anthropic-building-effective-agents.md:21`）

如果「智能体」这个名号对交付方有实质意义（例如立项书里写的是「智能体」），
那么只有 B 满足字面定义。

---

## 5 外部理论：同时约束两边的四条

| 原则 | 原文位置 | 对我们的直接含义 |
|---|---|---|
| Poka-yoke 工具（让错误参数无法表达） | `anthropic-building-effective-agents.md:228` | 我们的 `find_template.sh:93`（搜索根落在 `$HOME/OpenFOAM` → `die 64`）就是这个范式；A 形态下它是**唯一能强制执行规则的地方** |
| 错误响应要可操作，而非不透明错误码 | `anthropic-writing-tools-for-agents.md:188` | 退出码 12/13/20–23/31–33/40/64 必须配一句「下一步做什么」，否则宿主只会重试同一个错误 |
| 工具是「确定性系统与非确定性 agent 之间的契约」 | `anthropic-writing-tools-for-agents.md:38` | 契约的两端在 A 里是两个主体，在 B 里是同一个进程；契约内容不变 |
| 好工具「可组合进不同 workflow」 | `anthropic-writing-tools-for-agents.md:214` | 支持 A 的广度论点：同一套 CLI 可被多宿主组合 |

还有一条对两边都成立、但对 A 更致命的观察：

> 「most of the products out there billing themselves as “AI Agents” are not all that agentic.
> A lot of them are **mostly deterministic code, with LLM steps sprinkled in** at just the right points」
> （`humanlayer-12-factor-agents.md:15`）

它说的是：**市面上自称 agent 的东西，大部分内容物就是 A 形态的内容物**。所以 A 不是「偷工减料」，
而是「业界常态」；但它同时说明「agent」这个词在市面上的信噪比很低——第 1 节的命名风险不是我们独有的。

---

## 6 十维对照

| 维度 | A（工具包 + 入口文档） | B（自带模型的 CLI） |
|---|---|---|
| 裁决权（谁决定下一步） | 宿主 | 我们 |
| 门禁是否强制 | **约定**：宿主可以跳过 `verify_case.sh` 直接改字典 | **程序流**：跳不过 |
| `R4`「能跑」的证据 | 同一脚本的退出码，但消费者是宿主 | 同一脚本的退出码，消费者是我们 |
| 失败可见性 | **静默退化**（跳过门禁、只看退出码、凭记忆写字典） | 显式失败 + 完整日志 |
| 不确定性成本 | 0（不在我们账上） | token ×3（3 次取多数）+ 重试 + 限流 |
| 版本风险 | 外包给用户（用户装错版本 → 假红/假绿，我们无法测） | 收回来，但仍要求 v13 环境 |
| 模型换代影响 | 无 | 需重验「校验器契约不变」这条硬判据 |
| 交付体积 | 2674 行用户面脚本 + 1 份入口文档（纯标准库 + bash） | 再加 orchestrator、prompt、密钥与错误处理 |
| 验收归因 | 三方混合（文档质量 / 脚本 / 宿主能力），坏了分不清 | 单一（我们） |
| 演进方向 | A→B 是**加法**（接口不变，外面加一层） | B→A 是减法（沉没成本） |

> 2674 = `check_contracts.py` 429 + `find_template.sh` 151 + `fix_case.py` 718 + `new_case.sh` 206 +
> `parse_requirement.py` 290 + `run_case.sh` 251 + `verify_case.sh` 629。复核：`wc -l scripts/*`。

---

## 7 失败形状不对称 —— 比上面的优缺点表更重要的一条

### 7.1 A 的失败是静默的，B 的失败是显式的

这一条我认为是整个选择的真正分界。

- **A 的失效形态**：宿主 agent 不读文档、跳过门禁、把 G2「优化」成看 `checkMesh` 退出码、
  凭记忆写字典。结果**看起来是绿的**，而我们与用户都不知道它是假的。
- **B 的失效形态**：FATAL、超时、token 超限、模型胡说被校验器判 `complete=false`。
  有日志、能归因、能进 `bench/results.csv`、能算 `unstable`。

**这不是理论推测，本项目已经实测过一次同型事故**：`AGENTS.md` R1 记录 04_RAG_HMS 的三臂实验里，
「禁工具的裸问答臂 12 条答案里 5 条编造、5 条弃答，错误形态是『路径根本不存在』和『语义等价的改写』——
**人眼审不出来**」。A 形态把这种失效模式放大到交付层面：**审不出来，且没有日志可查**。

而同项目里最贵的一条教训（`STATUS.md` N3 #19）恰好就是这个形状：
`checkMesh` 打印 `Failed 1 mesh checks.` 时**退出码仍是 0**。A 形态下宿主把 G2 改成看退出码，
**所有不合格网格都会被放行**，而我们不在现场。

### 7.2 因此两种形态的质量策略不同

| | A | B |
|---|---|---|
| 我们能保证的质量 | 「**别人复现得了**」（判据是脚本，证据在对方手里） | 「**我们自己测得准**」（判据 + 归因都在我们手里） |
| 无法保证的质量 | 对方是否真的执行了判据 | 模型换代后判据是否仍成立 |
| 对应的验收命令 | 陌生用户照文档跑通 cavity，五门 RC=0 | 12 任务 × 3 次，结论从 `results.csv` 重算 |

`anthropic-demystifying-evals.md:32` 的「多次 trial」只在 B 下有对象——
A 下「我们的 agent 跑了几次」这个问题不成立，因为跑的是别人的 agent。

### 7.3 一条反直觉的推论

A 把不确定性外包出去，**降低了自己的成本，同时把「不可判定性」转移给了下游**。
在「禁止自欺」是本项目第一价值的语境下（P1 整条都是这件事），这个转移方向是**逆着项目价值**的。

B 反过来：它把不确定性收进来，代价是 3 倍成本与一套稳定性设计（`preregistration.md` §11 已备好）。
收进来的好处是**它变成可测的**——可测就可以改进；外包出去的不可测，只能永远假设。

---

## 8 与项目既有决策的对齐检查

这一节是本文档的价值所在：形态选择会与已冻结/已决策的内容相互约束。

| 既有决策 | A | B | 判定 |
|---|---|---|---|
| `06-agent-anatomy.md:300-348` 最小骨架 6 部件；砍掉的 5 部件各有可判定加回条件 | 不需要任何加回 | 至少要加回 §4 的部件 7（状态机）、9（工具接口）、11（人机停点） | **B 现在违反项目自己的判据**：三者的触发条件（`06:324-336`）一条都没满足 |
| `06:329` 部件 9 的触发条件：「出现**第二个消费者**且它的参数形状与现有 CLI 不同」 | A 的发布行为本身就在造第二个消费者 | B 只有一个消费者（我们自己） | **A 反而更早触发部件 9** → A 是通往 B 的正常路径 |
| `AGENTS.md` R11 单一 OpenFOAM 版本 | 版本风险外包，且我们无权验证 | 只能要求「请在 v13 环境跑」 | 两边都必须写死 **v13-only**；A 更要写清「别的版本我测不了」 |
| `AGENTS.md` R4「说能跑必须先过 G1–G3」 | 退化为**约定** | 保持**强制** | A 的发布版必须把这条降级声明写进文档，否则是对 R4 的隐形违反 |
| `references/00-project-readme.md:76-77` P1（LLM 翻译 / 脚本判定） | 完全一致 | 完全一致 | 两边都不违反 P1；P1 只规定分工，不规定谁持有循环 |
| `bench/` 与 `adapters/` 的意义 | bench 从「内部验收」升级为「对外可比 harness」 | bench 只能量我们自己 | **A 与 bench 设计同构**（`evals:37` 的 harness 定义） |
| `references/00-project-readme.md:120`「MCP 被否决」（原文：「检索层被否决；MCP 被否决；向量通道被否决」） | 一致：不封 MCP，只给 CLI | B 更容易滑向 MCP 化 | A 更符合已决结论 |
| `references/00-project-readme.md:56`「不做 GUI / Web」 | 一致 | 一致 | 与形态无关 |

**一条需要注意的冲突**：`README.md` §1 的能力表用的是「任务」（建 case / 改 case / 二次开发 /
批量运行），不是「agent」。A 形态与这张表天然一致；B 形态需要重写这张表（因为「一个 agent 能听懂
任意需求」与「四条任务链」是两种不同的能力承诺）。

---

## 9 结论与推荐路径

> **已裁决（2026-10-28，用户）**：**按 A 先做，B 作为以后的目标**——A 实现并且能够有不错的表现之后
> 再考虑 B。本文的推荐与分析保留在此，作为该裁决的依据与边界；**不再需要重新讨论"A 还是 B"**，
> 只需按第 12 节监控三条推翻条件。
>
> 裁决带来的两个直接后果：① 第 10 节的 6 个阻塞项成为**当前工作范围**（不再是可选清单）；
> ② 第 9.3 节的三个不可逆点（I1/I2/I3）**必须在发布前钉死**，B 阶段不允许再改。
>
> 执行计划见 `specs/001-release-a-harness/`（speckit 三件套：spec / plan / tasks）。

### 9.1 推荐：先 A，且把 A 当成 B 的第一阶段（不是替代品）

理由三条，按强度排序：

1. **演进可逆性不对称**：A→B 是加法（`09` §2-A：「接 LLM 时只换 `extract_quad`」，接口形状不变），
   B→A 是减法（已写的 orchestrator 与 prompt 全部沉没）。**不可逆性应当最后承担。**
2. **A 的发布行为本身就是部件 9 的触发条件**（`06:329`）：发给别人用 → 出现第二个消费者 →
   接口契约被真实使用检验过 → 此时再写 orchestrator，参数形状是**被验证过的**，不是猜的。
3. **理论证据的方向一致**：Anthropic 说「先取最简方案」，OpenAI 说「先最大化单个 agent 的能力」，
   12-factor 说「好的 agent 大部分是确定性代码」。三份文献的**共同点**是「复杂度和控制权应当最后加」，
   而不是「一开始就拥有控制流」。

### 9.2 B 不是被否掉，是被推迟：三个可判定的加回触发条件

沿用 `06` §4 的写法（每个条件都必须可判定，不许写「当需要时」）：

1. **T-B1（模型层必要性）**：出现「用固定词表抽不出四元组」的需求 ≥3 次，且每次都以
   `complete=false` 停给人 → 说明确定性半边已经到顶，此时才值得接 LLM。
2. **T-B2（控制流必要性）**：宿主实际执行时**跳过**门禁 ≥2 次（判据：`runs/<batch>/<case_id>/`
   下存在 `log.run` 但缺 `log.g1..g5`，或 `status=pass` 而 `g2` 为空）→ 说明约定已失效，必须收权。
3. **T-B3（归因必要性）**：出现一次「用户报失败但我们无法复现、也无法判断是不是我们的错」→
   说明三方归因已经不成立，必须自己持有循环。

**T-B2 是我认为最可能出现的一条**，因为它就是第 7 节那个「静默失败」的可判定形态。

### 9.3 三个不可逆点（发布前必须钉死，B 阶段不允许再改）

| ID | 不可逆点 | 为什么不可逆 | 现在应定的值 |
|---|---|---|---|
| **I1** | CLI 契约：argv 形状、退出码语义、返回值必须带 `status` | 一旦有外部消费者，改名 = 破坏兼容 | 沿用现有退出码（12/13/20–23/31–33/40/64），一个动作一个子命令，一律传绝对路径（对应 `anthropic-building-effective-agents.md:230` 的绝对路径教训） |
| **I2** | 对外措辞：是否承诺「agent」 | 措辞会写进对方的验收标准（见第 1 节） | A 阶段自称 **harness / 工具包**，不写「智能体」；B 阶段才改名 |
| **I3** | 版本声明：v13-only 还是多版本 | 多版本 = 判据要分叉，判据分叉 = 假红假绿 | **v13-only**，并在入口文档第一段声明「其它版本我测不了」（R11 的后果） |

---

## 10 若选 A：发布前的阻塞项（每条带判据）

> 状态列更新于 2026-10-29。执行计划见 `specs/001-release-a-harness/`；`tasks.md` 是 v0.1 执行记录
> （2026-10-29 冻结），**当前进度只以 `STATUS.md` 为准**（R13）。本表只记「阻塞项的判据形态」，状态列是当时的快照。

| # | 阻塞项 | 现状判据 | 验收命令 | 状态 |
|---|---|---|---|---|
| 1 | **入口文档**（M3 的交付物，`references/00-project-readme.md:346`） | 尚不存在（`README.md` 是内部文档，通篇依赖 R1/R12/P1 等只在 `AGENTS.md` 有定义的编号） | 陌生用户只读本文档 + 脚本能跑通 cavity | P4 待做 |
| 2 | **路径解耦** | 已解耦（2026-10-29）：`find_template.sh` 用 `resolve_bash_rc()` 按 `$WM_PROJECT_DIR` 推导，仅回退分支保留字面前缀 | `pytest tests/unit/test_portability.py -q` 全绿；判据**不是**「出现 0 次」（回退分支必然 1 次），而是「每个非注释命中必须同时出现 `WM_PROJECT_DIR`」 | **完成** |
| 3 | **preflight** | 不存在。外部用户忘了 source → `foamRun` 不在 PATH → 与「求解失败」同形（`STATUS.md` N3 #15） | 一个前置检查：`foamRun`/`foamDictionary`/`blockMesh` 在 PATH、`$FOAM_TUTORIALS` 可读、python3 版本；任一缺 → 直接报「环境未 source」 | P2 待做 |
| 4 | **能力表对齐** | `references/00-project-readme.md:47` 与 §5.4 写了「批量运行」，但 `scripts/batch.py` 不存在（M2 未做）；`references/00-project-readme.md:152` 指向的 skill 在 `~/.hermes/skills/` 下，**不在仓库里** | 二选一：做 M2 并把 skill 搬进仓库 doc/，或从发布版能力表删掉这两条 | P4 待做（**已定：删，不做 M2**） |
| 5 | **范围声明 + 许可** | 仓库根无 LICENSE、无版本号 | 两份文件存在即可；许可证内容**待用户裁定**，不凭空生成 | P3/P4 待做 |
| 6 | **端到端 quickstart** | 无需新跑：M1 的 cavity 记录（跑到 `Time = 10s`、22 个时间目录、五门 RC=0）可直接整理为预期输出 | 文档里的预期输出与实际一致 | P4 待做（**须重跑取真实输出，不许照抄摘要**） |

**发布包放什么**：用户面 7 个脚本 + 入口文档 + preflight + quickstart + LICENSE。
**不放**：`status_snapshot.py`、`verify_references.sh`（项目治理仪器，依赖 `bench/` 与 `references/`，
删掉那两个目录后它们会直接变红，对外部用户是噪音）、`bench/`、`references/`、`AGENTS.md`、`STATUS.md`。

---

## 11 若选 B：最小可行规格

只做三件事，其余一律不做：

1. **换一个函数**：`extract_quad` 换成 LLM 实现，硬判据是
   `tests/unit/test_parse_requirement.py` 的 16 项**一行不改**仍全绿（`10-gap-register.md:231-233`）。
2. **加一个循环**：按 `gather → act → verify → repeat` 组织（`anthropic-claude-agent-sdk.md:33` 的
   同型循环），循环里的 verify 必须是现有 `verify_case.sh`，不许另写一份判据。
3. **加一个停点**：`max_attempts` + `declined` + 「连续两轮修不好 → 停」（对应 R8-4 与
   `openai-practical-guide-extracted.md:304`）。

**明确不做**（`06` §4 的砍件清单原样保留）：反思记忆、阶段状态机落盘、版本断言部件、工具接口封装。
理由不变：它们的加回条件（`06:324-336`）在 B 的最小版本里同样不满足。

---

## 12 什么证据会推翻本文的推荐

三条，任一成立都应回到选择题：

1. **目标用户不使用 agent**。如果对方是「只想点一个按钮的人」，A 的前提（有人读文档、会编排 CLI）不成立，
   此时 A 和 B 都不合适，正解是 GUI——而 `references/00-project-readme.md:56` 明确「不做 GUI / Web」，说明这属于**改项目范围**，
   不是改形态。
2. **必须支持多版本**。若验收要求覆盖 v12 / v2406，A 的文档要给多代语法分支（`02-architectures.md:1783`
   记录 hpc-skills 就是这么做的：「同时给两代语法并让读者自己分支」），而我们的判据是单值的
   （`Mesh OK.`、`foamRun`、`solver <module>`）。**判据分叉 = 假红假绿**，此时 A 的成本可能高于 B。
3. **T-B2 被满足**（宿主跳过门禁 ≥2 次）：这不推翻 A 的**内容物**，但推翻「约定足以维持纪律」这个前提，
   应当立刻启动 B 的第 1、3 件事。

---

## 13 引用边界与复核

- 外部文献引用格式：`references/external/<file>:<行>`。文件、行数、字节与 sha256 见
  `references/external/INDEX.md`；复核命令也在该文件末尾。
- 外部文献**不是** OpenFOAM 源码事实来源（R9）。本文没有一句关于 v13 字典语法的陈述。
- 内部引用格式：`<path>:<行>`，与 `references/03-evidence-audit.md` 的口径一致。
- 本文档不含任何跨臂数字，不得被 `08-condensed-report.md` 的对外版本引用为「效果证据」。

```bash
# 复核本文档的三条可判定主张（2026-10-29 重跑过，输出与注释一致）
grep -rln 'openai\|anthropic\|api_key\|requests.post' scripts/ bench/   # 空 → 当前是 A 的骨架
wc -l scripts/*.py scripts/*.sh | tail -1                                # 2684 = 7 个用户面脚本合计（P1 加 resolve_bash_rc 后 +10，原 2674；不含 preflight.sh / make_release.sh / check_release_docs.py）
grep -c 'BASH_RC="\$(resolve_bash_rc)"' scripts/find_template.sh          # 1 → 路径已解耦（阻塞项 2 完成）
```



---

## 14 附 · 本仓库的开源发布边界（2026-10-29）

> 本节原先写在 `AGENTS.md` 的「附二」，2026-10-29 迁出：它的读者是**看这个开源仓库的人**，
> 不是在本目录工作的 agent（对 agent 而言那些文件是存在的）。权威表达是 `.gitignore` 的分组注释，
> 机器执行它；本节只解释「为什么」。

本文件随开源代码发布。但下面这些**不发布**，因此文中提到它们的地方在本仓库里点不开：

| 提到的东西 | 在哪条规则里 | 开源仓库里的情况 |
|---|---|---|
| `STATUS.md`（接续点） | `AGENTS.md` R13 | 不发布。它是维护者的会话接续文件，不是产品的一部分 |
| `specs/`（本轮 speckit 计划与任务勾选） | — | 不发布。属于「我们怎样造这个东西」的过程记录 |
| `dist/`（发布包构建产物） | — | 不发布，可由 `scripts/make_release.sh` 重新生成 |
| `.hermes/`（本地进度日志） | — | 不发布 |
| `references/repos/`（第三方代码副本，约 185 MB） | `AGENTS.md` R9/R10 | 不发布。**R9/R10 的规则本身仍然有效**，只是它们约束的对象在你本地不存在 |

**对使用者的实际影响只有一条**：`AGENTS.md` R13 的「刷新 STATUS.md」不适用（没有那个文件）。
其余规则（R1 grep 强制、R2 不改系统树、R3 派生、R4 门禁、R5 前处理边界、R6 数字实测、
R11 单一版本、R12 预注册）对你照样成立——它们是这套工具为什么可信的全部理由。
