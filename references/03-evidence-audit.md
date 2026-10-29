# 三、证据审计：现在能说什么、不能说什么

> 用途：在动笔写任何结论之前，先确定**哪些话现在可以说**。本文件不产出新知识，只产出「许可证」。
> 依据：STATUS.md N5 五条缺口 · references/01-landscape.md · references/02-architectures.md ·
> bench/preregistration.md（已冻结，§1–§9 + §13 不得改动）。

## 0 口径与判据（本段已冻结，后续不得放宽；放宽须在 §7 记一条「口径变更」并说明原因）

### 0.1 证据等级（E0–E4）

| 代号 | 定义 | 允许的动词 |
|---|---|---|
| E0 | 本机命令输出（`grep`/`wc`/`checkMesh` … 附命令与输出） | 「是」「为」 |
| E1 | 本地仓源码 `path:line` 逐字 | 「实现为」「代码里是」 |
| E2 | 本地仓 README / 配置文本 `path:line` | 「其文档声明」 |
| E3 | 论文摘要 / arXiv HTML 可见段落 | 「其摘要写」 |
| E4 | 二手转述（别人的综述、我们旧报告未经复核的片段） | 「据说」——**不得进结论** |

### 0.2 本文件的红线

1. 任何一行结论都必须能指到本文件某节 + 一个 E0/E1 级锚点；指不到 = 该行作废。
2. 引用第三方代码一律写成 `references/repos/<repo>/<file>:<line>`，行号必须真实（G-DOC-1 会查）。
3. 不得出现跨臂成功率比较、性能优劣、"谁更强"类断言（见 §4 黑名单）。
4. 不得把 `bench/preregistration.md` §10（每臂预测，尚未冻结）当证据引用。
5. 数字必须来自刚跑的命令输出，表下写 `数据来源：<命令>`；禁止估算。

## 1 一句话结论（≤5 条，每条指向本文件某节）

1. N5 五条缺口里，两条已闭合（chatcfd / openfoamgpt 的文档级标注、A 档退化为单点参照的处置），**两条仍缺**（`***` soft 分支的复现、`human_interventions` 计数口径未定），**一条被误认为已补**（judge 七态归约的合成自测——`checked=12 failed=0` 只覆盖断言层，见 §2-1）。
2. 10 个 `full` 仓都读到了源码层，但 nullflux 只覆盖未混淆的 `server.js`，hpc-skills 是纯文本仓，chatcfd / openfoamgpt 只到 E2 / E3（见 §3）。
3. 现在能写的只有三样：Q1「部件清单 + 接口形态」（E1 级）、Q2「机制收敛度三档评级」、Q3「L1/L2 两档来源映射」；任何成功率比较都写不出来，因为 `bench/results.csv` 有 0 条数据行、`bench/runs/` 有 0 项（见 §4-1、§5）。
4. prereg §10 每臂预测与 `human_interventions` 数值都在黑名单里，理由分别是「§10 未冻结」与「计数口径三选一未定」（见 §4-3、§4-4）。
5. 本文件每行结论都能回切到 02 / prereg / STATUS 的行段，但它没有逐条复核 02 自报的 314 条引文（见 §6）。

## 2 N5 五条缺口逐条对账

缺口原文逐字抄自 `STATUS.md:113-120`。状态只取三值。

| # | 缺口（原文） | 现有证据 | 状态 | 补它需要的具体动作 |
|---|---|---|---|---|
| 1 | **judge 的七态归约尚未做合成自测**（prereg §11 第 4 条）。断言层已自证（`selftest_expect.py` `checked=12 failed=0`），但"3 次 run → 任务级状态"那层没有任何测试。**在它补上之前，不许出任何跨臂结论。** | 断言层证据在 `bench/preregistration.md:373-378`，同段明写「**没有**证明 judge 的七态归约正确——那一层的合成自测仍属 M4b」。归约规格在 `bench/preregistration.md:362-363`，合成 fixture 的必测分支在 `bench/preregistration.md:364-367`（七态各 ≥1 例 = 7 项，外加边界 **5 项**：日志为空 / 含 `FOAM FATAL` 但退出码 0 / 末时刻场为 `nan` / `case.meta` 缺 `source` / `case/` 缺 `system/controlDict` → 合计 **12** 个 fixture）。仓内没有任何 judge 实现或 judge 自测：`ls bench/*judge* \| wc -l` → `0` | 被误认为已补 | 写 `bench/judge.py` + `bench/selftest_judge.py`，按 `bench/preregistration.md:364-367` 造 **7 + 5 = 12** 个合成 fixture（不碰真实项目），必须打印 `checked=12`，且「三次各不同 → `malformed` + `unstable=1`」单独一例。（注：`checked=12` 与断言层的 `checked=12` 数值相同但对象不同——前者是 judge 七态样本，后者是 12 个任务的 `expect_values`，引用时不得混为一谈）属 **M4b**（§11 明确写在 M4b 之前先定、实跑之后才验）。补上之前，本文件 §4-1 继续生效 |
| 2 | `***` 的 soft 分支（4 项豁免检查）**没有用 blockMesh 复现出来**，只由源码 4 处注释行确认。 | 4 项与其源码锚点写在 `bench/preregistration.md:94-96`：`checkEdgeLength` / `checkPointNearness` / `checkFaceAngles` / `checkFaceFlatness`，对应 `$FOAM_SRC/meshCheck/checkGeometry.C:902/924/950/978`。缺口在 `bench/preregistration.md:452` 被复述一次。02 与 01 全文没有任何 blockMesh 复现实验的记录，也无 `g2b=soft:N` 的实测样例行 | 仍缺 | 从 `$FOAM_TUTORIALS` 派生 1 个会触发软缺陷的 case（R3），跑 `blockMesh` + `checkMesh`，同时记录 `grep -cE '^\s*\*\*\*' log.checkMesh` 与 `Mesh OK.` 是否同现，把两个输出贴进 M1 报告。判定标准是先写在文档里的「`***` 行数 > 0 且 `Mesh OK.` 存在」。工作量：1 个 case + 2 条命令，属 **M1**。**【待定：用哪个 tutorial 派生才能稳定触发这 4 类软缺陷——须先试一次 `blockMesh` 才知道，试出来之前不写具体来源】** |
| 3 | **A 档只有 1 个项目（harnessfoam），主排名条件未满足**——prereg §7 的退化路径**已在冻结时生效**：交付形态是「ours 回归基线 + harnessfoam 单点参照 + 其余定性」，后续原文含比较性措辞，按本文件 §0.2 第 3 条不复述。 | 静态事实与处置都在 `bench/preregistration.md:254`（harnessfoam 唯一 A）、`:275-284`（退化路径 + 「该条件已静态触发」+ 三种交付形态）。`references/registry.csv:8` 的 tier=A 与之一致。**tier 分布存在源文件内部矛盾（见 §2 表下「tier 分布对账」）**：`references/registry.csv` 实测 `awk -F, 'NR>1{c[$8]++}'` → A=1 / **B=10** / C=1；`bench/preregistration.md:443`（冻结记录）与 STATUS.md 机器段 B 段同样是 **B=10**；但 `bench/preregistration.md:267` 写的是 **B=9**（`01:69` 已于 2026-10-28 更正为 B=10）。以 registry 实测为准（B=10），**A=1 这一条三处一致，故本行的判定不受影响** | 已补 | 无需再补证据——这条缺口在结构上填不满（不装第二个 OpenFOAM 就没有第二个 A）。M4b 只须照 `:280-282` 出三种交付物，且**不得生成任何跨臂排名表**（含表格形式）。属 **M4b** 的执行纪律，不是待办研究 |
| 4 | `human_interventions` 口径未定（N1），该列填 `unmeasured`，**不得进结论句**。 | 列定义在 `bench/preregistration.md:55`；三个候选口径 (i)(ii)(iii) 在 `:408` 并列但**未选定**；`unmeasured` 的处置在 `:413`、`:446`。`bench/results.csv` 目前只有表头（0 数据行），该列尚无任何实际取值 | 仍缺 | 需要用户在有三个选项的那一处做出选择（(i) 只算替它改字典 / (ii) 也算答问 / (iii) 也算重启整轮），然后把选定的定义写进 `bench/preregistration.md` 的非冻结区（§15 之后新增一节），并在本文件 §7 记一条口径变更。**【待定→已裁定（编排方 2026-10-28 实测）：合法路径是「在 preregistration.md 末尾 §15 之后新增一节」。依据：`bench/freeze_digest.py:28-32` 的 `SLICES` 只哈希 `## 1 测量路径`–`## 10`、`## 13`–`## 14`、`## 冻结记录`–`### 变更规则` 三段，`### 变更规则` 之后的内容不参与指纹；实测 `python3 bench/freeze_digest.py` 输出 `1bc8a4008c8a01da…` 与文档记录值一致，且三段行数分别为 308 / 78 / 38 行。因此末尾追加一节**不改指纹、不需要开新一轮**（§15 自身也明写「本小节不在被冻结的章节内」）。切勿改 `§13` 正文——那会直接让 G-R12-3 变红】** 在此之前 `results.csv` 该列只许写 `unmeasured`。属 **M4b** 首跑前的准备项 |
| 5 | 02-architectures 里 chatcfd / openfoamgpt 两节是**文档级**，未读源码，不得当实现证据引用。 | 两节的「依据：文档级，未读源码」标记在 `references/02-architectures.md:1878`、`:1893`、`:2020`、`:2031`；总述在 `:2120` 与 `:2156-2158`。`references/registry.csv:12-13` 两行的 `mode=docs_only`、`local_path` 为空，与之一致。全文该标记共 24 处（`grep -c '依据：文档级，未读源码'` → `24`） | 已补 | 标记层面无需再补。若要升级到实现级证据，唯一路径是读 `references/repos/cfd-agent`（`registry.csv:6` 记「即 ChatCFD 代码」），且必须先做一次同源指纹比对（`:2118` 给的判据：`max_running_test_round` 与 `database_OFv24` 是否同时出现）。属 **M4b** 的资料补全，不影响 M1–M3 |

数据来源：`ls bench/*judge* 2>/dev/null | wc -l`（→ 0）、`grep -c '依据：文档级，未读源码' references/02-architectures.md`（→ 24）、`wc -l < bench/results.csv`（→ 1，即表头）、`awk -F, 'NR>1{c[$8]++} END{for(k in c) print k, c[k]}' references/registry.csv`（→ A 1 / B 10 / C 1）

**tier 分布对账（源文件自相矛盾，本文件的处置）**

| 出处 | A | B | C | 判定 |
|---|---|---|---|---|
| `references/registry.csv` 实测（`awk` 见上） | 1 | **10** | 1 | **权威**（R10 规定 registry 为登记来源） |
| `bench/preregistration.md:443`（冻结记录） | 1 | **10** | 1 | 与 registry 一致 |
| `STATUS.md` 机器段 B 段 | 1 | **10** | 1 | 与 registry 一致 |
| `bench/preregistration.md:267`（§7 正文，**在冻结切片内**） | 1 | 9 | 1 | **错**，且不能就地改 |
| `references/01-landscape.md:69` | 1 | **10** | 1 | **已于 2026-10-28 更正为 10**（原写 9，转抄自上一行；01 非冻结件，用户批准后就地改） |

`B=9` 的成因可推定：`registry.csv` 有 12 行 = 10 full + 2 docs_only，若漏数一个 full 仓即得 9。
**现状（2026-10-28）**：`01:69` 已更正为 B=10；**唯一残留是 `prereg:267`**（冻结切片内，未改）。
**处置**：§7 正文属于 prereg 冻结切片（`bench/freeze_digest.py:29` 的 `§1–§9`），按
`bench/preregistration.md:458-462` 的变更规则「任何改动都算新一轮」，**本文件不就地修改**，
只登记为待用户裁定的项（见 §7）。凡引用 tier 分布的地方一律用 **A=1 / B=10 / C=1**。
`A=1` 三处一致（registry 第 8 行 harnessfoam、prereg:254、prereg:443），故 §2 第 3 行与 §4-2 的
「A 档只有一家 → 无排名对象」这一结论不受影响。

两条读法提醒：

- 第 1 条的「被误认为已补」不是指有人写了假的测试，而是指 `checked=12 failed=0` 这个数**很容易被读成「判定层已经自证」**——它只覆盖断言层（`bench/preregistration.md:375-378` 自己就把这个边界写清了）。凡是引用 `checked=12` 的段落，必须同时写出它覆盖的是哪一层。
- 第 3 条已补的只是「处置」，不是「条件」。任何人引用 harnessfoam 的数字时，必须写成「单点参照」，不得写成「与 ours 的对比结果」。

## 3 证据覆盖度：10 个 full 仓各读到哪一层

依据是 02 里每个项目小节的 `### 5 知识来源` / `### 7 它怎么知道跑成功了` 是否引用到 `path:line` 粒度的源码，以及被引文件的类型。`✓` 只表示「该层被读过且本文能指到行段」，不表示读全。

| 项目 | 读过源码 | 只读 README | 只读论文摘要 | 未读 | 凭据（02 的行段） |
|---|---|---|---|---|---|
| foam-agent（134 文件 / 54 `.py`） | ✓ | — | — | — | `138-156`：引 `src/config.py:50`、`src/services/plan.py:158`/`:231`/`:249`、`src/services/input_writer.py:453`；结论行 `1218` |
| metaopenfoam（171 / 60） | ✓ | — | — | — | `360-373`：引 `src/qa_module.py:403`/`:414`/`:418`、`src/Langchain_database_add_tutorial.py:22`、`src/Tutorial_postprocess.py:35`；结论行 `1219` |
| openfoam-mcp-server（291 / 20） | ✓ | — | — | — | `543-547`：引 `src/tools/context_engine.hpp:236`、`src/tools/context_engine.cpp:274`、`src/openfoam/case_manager.cpp:420-436`；`551-556`：引 `src/tools/pipe_flow_tool.cpp:212`、`src/openfoam/pipe_flow.cpp:188`；结论行 `1220` |
| nullflux（12 / 0） | ✓（仅 `server.js`） | — | — | — | `723-743`：引 `server.js:1081`/`:1090-1098`/`:469`/`:537`/`:3412`；sealed bundle 未读，见 `1238`；结论行 `1221` |
| cfd-agent（114 / 46） | ✓ | — | — | — | `911-923`：引 `src/database.py:102-112`/`:130-221`/`:217`、`src/config.py:207-208`；`925-932`：引 `src/workflow.py:116`/`:118`/`:121-123`/`:110-113`；结论行 `1222` |
| ai-cfd-scientist（239 / 168） | ✓ | — | — | — | `1086-1102`：引 `references/repos/ai-cfd-scientist/scripts/foam_run.py:1261`、`references/repos/ai-cfd-scientist/scripts/interpret.py:58-64`、`references/repos/ai-cfd-scientist/src/cfd_langgraph/foam_native/faiss_index.py`（vendored） |
| harnessfoam（266 / 79） | ✓ | — | — | — | `1319-1343`：引 `harnessfoam/knowledge.py:17-25`/`:27`/`:75`/`:103`、`harnessfoam/agents/graph.py:68`/`:139`/`:387`；结论行 `2103` |
| autofoam（54 / 36） | ✓ | — | — | — | `1500-1517`：引 `openfoam_agent/rag.py:118`/`:151-179`/`:240`、`openfoam_agent/config.py:14`/`:20`/`:26`、`openfoam_agent/agent.py:68`/`:94`；结论行 `2104` |
| deepflow（49 / 7） | ✓ | — | — | — | `1636-1640`：引 `deepflow_agent/openfoam_agent.py:304`/`:316`/`:320`/`:321`/`:325`/`:308-313`/`:334-335`、`references/repos/deepflow/scripts/create_knowledge_base_sync.py:28`/`:44-47`/`:61`/`:67`；`1647-1648`：引 `openfoam_agent.py:358`/`:360-363`；结论行 `2105` |
| hpc-skills（439 / 13） | ✓（仅文本正文） | — | — | — | `1750-1757`：引 `skills/hpc-openfoam/SKILL.md` 的 `:10-21`/`:23-30`/`:53-60`；`1761`：引 `references/repos/hpc-skills/skills/hpc-openfoam/references/error-recovery.md:130`/`:178`；`1769-1771`：引 `SKILL.md` 的 `:45`/`:89` 与 `references/repos/hpc-skills/skills/hpc-openfoam/references/validation-parallel-and-observability.md:14`；结论行 `2106` |
| chatcfd（无本地文件） | — | ✓ | ✓ | — | `1876-1888`：引 README:91/151/205/269-274 + paper §2.1/§2.3.2/§2.4；`2119` 引 README:308；结论行 `2107` |
| openfoamgpt（无本地文件） | — | — | ✓ | — | `2018-2027`：全部为 paper §II/§III.2 逐字；无 README、无仓（`registry.csv:13` `kind=paper`）；结论行 `2108` |

数据来源：`grep -n '^## ' references/02-architectures.md`（取各项目小节起点）、`grep -n '^### ' references/02-architectures.md | grep -E ':### (5|10|1)[^0-9]'`（取 `### 5` 行号）、`for d in foam-agent metaopenfoam openfoam-mcp-server nullflux cfd-agent ai-cfd-scientist harnessfoam autofoam deepflow hpc-skills; do printf '%-22s files=%s ' "$d" "$(find references/repos/$d -type f -not -path '*/.git/*' | wc -l)"; printf 'py=%s\n' "$(find references/repos/$d -name '*.py' -not -path '*/.git/*' | wc -l)"; done`

三处必须跟脚注一起引用的单元格：

- **nullflux** 的 `✓` 只覆盖 `server.js`（该仓 12 个文件、0 个 `.py`）。混淆后的 `server.bundle.mjs` 未读，`02:1238` 已把工具实现、记忆落盘格式、`foam_run_solver_async` 是否有额外门禁列为「未确定」。凡引 nullflux 的机制描述，只能写「`server.js` 里可见的部分」。
- **hpc-skills** 的 `✓` 指 `.md` 正文（SKILL.md + 17 篇 references）——该仓没有可执行程序，其「源码」就是文本。13 个 `.py`（4 个 argparse CLI）只到 `02:2106` 的「4 个 argparse CLI」粒度，未逐行读，故不得引用其 CLI 内部逻辑。
- **chatcfd / openfoamgpt** 的两列 `✓` 全部是 E2 / E3：README 取自 GitHub 页面、论文取自 arXiv 摘要与可见段落，两者 `local_path` 均为空（`registry.csv:12-13`）。它们在任何段落里都只能以「其文档声明」「其摘要写」开头（§0.1 的 E2/E3 动词）。

两个可直接回切的第三方行号（本节判定不依赖它们，但它们是 §3 判定的原始锚点，供 G-DOC-1 复核）：

- `references/repos/harnessfoam/harnessfoam/case_manifest.py:8` 原文 `EXPECTED_OPENFOAM_VERSION = "13"` —— 该仓属 v13 的代码级判据（02:2115 指出 README:100 的字面表述与实现不一致，实现以此行为准）。
- `references/repos/hpc-skills/skills/hpc-openfoam/assets/templates/simplefoam-minimal/README.txt:1` 原文 `Minimal steady incompressible OpenFOAM-11 case scaffold.` —— hpc-skills 全仓唯一的版本声明，也是它由 A 修正为 B 的依据（`02:2112`）。

另需注意的口径差：`02:2103`/`2104` 等结论行里的「知识来源」列是对上述 §5 的压缩重述，本身不是新证据；引用时以 §5 的行段为准，不要引结论行。

## 4 禁用主张清单（黑名单）

判据：一条主张只要落在下表任何一行，写出来即作废——与本文件 §0.2 同级，不需要再讨论。

| # | 禁止的主张 | 为什么禁用 |
|---|---|---|
| 1 | 任何跨臂成功率 / 准确率比较，包括「某臂 12/12」「某任务只有 X 通过」「A 比 B 高 N 个百分点」，也包括把两个不同来源的百分比并列成一句话 | `bench/results.csv` 只有 1 行（表头）= **0 条数据行**，`bench/runs/` 有 **0 项**（`ls bench/runs \| wc -l` → `0`）。没有数据行就不存在可比较的分子分母；同时 R12 规定设计期禁跑，`bench/preregistration.md:275-284` 已把「主排名不成立」写死。任何这样的数字只能来自编造或来自别的实验被搬过来 |
| 2 | 任何「某项目效果更好 / 某架构优于另一架构」的优劣结论，或任何形式的跨项目排序（含「按判据强度排序」这类软排序） | A 档只有 harnessfoam 一家（`bench/preregistration.md:254`、`:443` → **A=1 / B=10 / C=1**，与 `references/registry.csv` 实测一致；`prereg:267` 误写 B=9，见 §2 表下「tier 分布对账」），退化路径在冻结时已生效（`:275-284`）：交付形态是「ours 回归基线 + harnessfoam 单点参照 + 其余定性」，并明写「不出任何『比较性』数字」。没有第二个可跑臂，排序无对象 |
| 3 | 引用 `bench/preregistration.md` §10 的每臂预测作为证据（「预期 X 臂会失败」「按预注册，ours 应达到 …」） | §10 尚未冻结，且**被显式排除在冻结范围外**：`bench/preregistration.md:4`、`:420`（冻结范围写「§10 每臂预测不在本次冻结内」）、`:332`（段标题自带「分段冻结」）。未冻结的预测不是判据，也不是证据；它只能是待验证的假设 |
| 4 | `human_interventions` 的任何数值，包括 `0`（「全程无人工干预」同样禁用） | 计数口径未定：三个候选口径 (i)(ii)(iii) 在 `bench/preregistration.md:408` 并列而**未选定**，列定义只有一句（`:55`），处置是「填 `unmeasured` 且不得进结论句」（`:413`、`:446`）。口径不同，同一个实验可以是 0 也可以是 5，写任何数都是伪精确。唯一允许的写法是 `unmeasured` |
| 5 | chatcfd / openfoamgpt 的任何实现细节：函数级机制、判据如何实现、重试上限落在哪个变量、工具接口叫什么名字 | 两者 `mode=docs_only`、`local_path` 为空（`references/registry.csv:12-13`），`size_mb=562` 超 R10 线未下载；`references/02-architectures.md:2120` 明写其「工具接口、判据实现、重试上限落地方式」均无源码证据，`:2156-2158` 再次限定为「论文这么声称」。把它们写成实现，等于把 E3 冒充 E1 |
| 6 | 把 02 自报「未确定」的四项当成已知：nullflux 混淆 bundle 的内部行为、openfoam-mcp-server 能否在 v13 上编译、foam-agent 语料的召回质量、metaopenfoam 依赖的 MetaGPT 版本 | 四项都在 `references/02-architectures.md:1236-1241` 逐条标了「未确定」。其中 foam-agent 的语料正文是 LFS 指针（`:1240`）、mcp-server 未编译（`:1239`）——这两条属于「结构上无法在本阶段确定」，不是「还没查」 |
| 7 | 复活 02 合并时已删掉的那条编造：nullflux `start.sh` 设 `--max-old-space-size=4096` | `references/02-architectures.md:2137-2153` 记录了它被删的全过程：`ls references/repos/nullflux` 只有 12 个文件、无 `start.sh`，`grep -rn "max-old-space-size" references/repos/nullflux` 无输出。它当时的形态是「合理的细节 + 格式正确的行号」，与 R1 描述的那类编造同型 |
| 8 | 用「判据条数多」当质量依据（「它有 5 条判据所以判得更严」），或用 02 §0 表的「强度」列做跨项目排序 | `references/02-architectures.md:38-46` 自己写明「多条」不等于「确定性」：nullflux 的物理层靠 VLM、autofoam 是加权分 0.5、ai-cfd-scientist 的物理层靠 LLM 读图。`强度` 列是对「判据是否独立于模型」的分类，不是可排序的量 |
| 9 | 把 `04_RAG_HMS` 的实测数字（各 7/7、省 5.2% token、+98 MB）当成本领域的比较结论 | `references/01-landscape.md:134`：本领域**没有**做过「专门检索层 vs tutorial 上 grep」的受控对照，「这是证据缺口，不是反例」。04 的数字只能写成「我们自己的实测」，不能写成「领域内已验证」 |
| 10 | 把 §3 的 `✓` 转述成「该仓已读全」（例如「nullflux 的实现已审」） | §3 表下三条脚注已限定：nullflux 只覆盖 `server.js`、hpc-skills 只覆盖 `.md` 正文、chatcfd / openfoamgpt 只到 E2/E3。转述时丢掉限定，就等于把「部分」写成「全部」 |

数据来源：`wc -l < bench/results.csv`（→ 1，表头）、`ls bench/runs | wc -l`（→ 0）、`ls bench/*judge* 2>/dev/null | wc -l`（→ 0）

黑名单的使用方式：写任何结论句之前先扫一遍本表；命中即改写或删除，不要靠「加一句『可能』」来绕过——加软化词不改变主张的证据等级。

## 5 对三问的许可证（Q1 / Q2 / Q3 各自最高能答到哪一级）

| 问 | 最高能答到哪一级 | 用什么证据 | 明确不能答什么 |
|---|---|---|---|
| **Q1 代码层面包括什么部分** | **「部件清单 + 接口形态」（E1 级）**：列出有哪些组件（图节点/角色/工具/检索层/判据层）、各自的接口形状（MCP tool 数、function calling 数、`add_edge` 顺序、字典关键字），每条挂 `path:line` | 02 的两张 8 列汇总矩阵（`1216-1222`、`2101-2108`）给出拓扑 / 工具接口 / 知识来源 / 自修正 / 判据类型五列；各项目小节的 `### 1 输入形态` / `### 2 分层与模块边界` / `### 3 agent 拓扑` / `### 4 工具接口` 四段给到类名与函数名（各项目小节的起止行与 `### 5 知识来源` 行段见 §3 表；`### 1`–`### 4` 在 `### 5` 之前，同一小节内向上翻即可），判据层的部件以 harnessfoam 最细（`validation.py:125-138`、`physics_validation.py:43-71`，见 `01:161-167`） | 不能说某个部件「起了多大作用」——没有消融就没有贡献度；不能给 docs_only 两项的部件形态（§4-5）；不能给 nullflux 混淆 bundle 内的工具实现（§4-6）；不能把「有 9 个图节点」读成「9 个节点都在工作」 |
| **Q2 哪些架构相对稳定可靠** | **只能到「收敛度 K + 证据强度 E + 版本无关性 V」的三档评级（强 / 中 / 弱）**，逐机制出，不出总分 | 口径在 `references/05-cross-project-matrix.md:13-15`（K = 互不相关独立实现的个数、E = `有对照`/`仅实现`/`无`、V = `无关`/`绑 <对象>`）、`:17-20`（同源去重：cfd-agent 与 ChatCFD 计 1，Foam-Agent 与 AI-CFD-Scientist 计 1，OptMetaOpenFOAM 与 MetaOpenFOAM 计 1）、`:22-25`（三档阈值，V 绑定一律最高「中」）；K 的计数依据是 02 各项目 §5/§7 的 E1 行段 | 不能说哪一套架构在实践中表现更好（§4-2：A 档只有一家，没有可比较对象）；不能把 K/E/V 合成总分（`05:9` 明令禁止合成）；不能声称任何机制 `E=有对照`——本领域在同一任务集上没有对照实验（`01:136`：这是证据缺口，不是反例）；不能把「出现在 N 个项目里」说成「N 个项目都验证过它」 |
| **Q3 设计源于哪些理论或工程实践** | **只能到 L1 / L2 两档**：L1 = 项目自己写出的理论名或论文 id（可写「引用」），L2 = 机制逐条对得上但项目无引用文本（只能写「与 X 同构」） | 口径在 `references/07-theory-provenance.md:9-15`（L1/L2/L3 三档判据 + 「不得写源于」）；L1 的实例可从 02 汇总矩阵直接取：foam-agent 的 LangGraph 图（`1218`）、metaopenfoam 的 MetaGPT `Environment` 与 `Role`（`1219`）、autofoam 的 Chroma + `bge-small-en-v1.5`（`2104`）；L2 的实例：harnessfoam 的 `validate_runtime()` 五判据与我们的 G1–G4（`01:161-167` 已写成「逐条同构」） | 不能答「效果验证」——L1/L2 只说明来源关系，不说明它有效；L3（形似）不得写出（`07:13` 只能进「已排除」清单）；不能把 L2 写成「源于」（`07:12`）；不能给理论侧的效果数字（如「换成该理论后成功率提高到 …」），那属于 §4-1 |

使用约定：三问的答案必须**逐问分别标级**，不许一句跨两级。例如「Q1 可到 E1、Q2 只到三档评级、Q3 只到 L1/L2」不能合并成一句「架构分析已完成」——合并后读者无法判断哪一部分是可回切的事实。

## 6 本文件的自我限制

- **没有跑任何东西**：没有 `blockMesh` / `checkMesh` / `foamRun`，没有装软件，没有启动任何被测项目；本文所有 E0 数字只来自 `wc` / `ls` / `grep -c` 这类文件与计数命令。
- **没有做新调研**：一切事实来自 STATUS.md / 01 / 02 / prereg / registry.csv 五处（外加 §5 引用的两份口径文件 05 与 07 的定义段）；没有读论文原文，没有新增仓库，没有访问网络。
- **没有复核 02 的每一条主张**：02 自报 G-DOC-1 `checked=314 violations=0`（`02:2130`）。本文初稿只按项目核对 §3 表里引用的 10 段行段，**独立 critic 全量回切（口径：`path:line` + `:N` 简写 + 裸 02 行号/区间，按（文件,行段）去重）得 125 条坐标**，第一轮发现 3 段行号区间不含其声称的引用（openfoam-mcp-server 的 `pipe_flow_tool.cpp:212` 实在 `02:555`、cfd-agent 的 `workflow.py:116` 实在 `02:929`、deepflow 的 `openfoam_agent.py:358` 实在 `02:1648`），已改为分段标注；另 1 条 fixture 计数由「7+6」修正为「7+5=12」（`prereg:364-367` 实际只列 5 个边界）。第二轮 critic 同口径回切 125 条：成立 123、不可本地核验 2（chatcfd 的 `README:91`/`README:308`，该仓 docs_only 无本地文件，属 E2 级非虚假引用）、不成立 0。即便如此，本文**没有**重跑那 314 条的逐条校验，也没有复核 02 对 OpenFOAM 源码的 `grep` 结论（那需要按 R1 重跑 `$FOAM_SRC` 侧命令）。这条自我限制的强度到此为止，不得再往高写。
- **没有验证「未确定」四项中的任何一项**：nullflux bundle、mcp-server 的 v13 编译、foam-agent 语料召回、metaopenfoam 的 MetaGPT 版本（`02:1236-1241`）在本文里仍是「未确定」，本文只做转述与禁用，不做判定。
- **没有替 M4b 做决定**：§2 第 4 条的三个口径、(i)/(ii)/(iii) 的选择权在用户，本文只标出「未选定」及其后果；§2 第 2 条的具体派生来源也留作待定。
- **没有动任何被测仓与冻结件**：`references/repos/**`、`bench/preregistration.md`、`bench/tasks/**`、`bench/results.csv`、`scripts/**` 全程只读；本文的改动范围限于本文件 §1–§8。
- **发现一道门禁的盲区（G-DOC-1 只查带仓库前缀的引用）**：`scripts/verify_references.sh:229` 的正则要求 `references/repos/<repo>/` 前缀，因此 02 里 **76 条裸 `README:<N>` 引用从未被任何门禁校验过**（`grep -oE '(README[^ \`"()<>:]*):[0-9]+' references/02-architectures.md | wc -l` → 76）。这些引用的语义约定是「本小节那个项目的 README」，但至少有一处不遵守：`references/02-architectures.md:1433` 写「现 G3 只 grep `FOAM FATAL`（README:182）」，而它指的是**本项目** references/00-project-readme.md:182（第 182 行确为 G3 那行），harnessfoam 的 `README.md` 只有 334 行且**第 182 行是空行**——同一串字符在两种命名空间下指向不同文件，门禁看不见。本文件（03）不评判 02 是否该改，只登记该盲区；04 已把这条标为「02 主张 #34 证伪」。

## 7 口径变更记录

（本段保持为空：至今未对 §0 做任何放宽。）

## 8 待用户裁定的项（不由本文件决定）

| # | 事项 | 为什么必须用户定 | 阻塞什么 |
|---|---|---|---|
| 1 | `bench/preregistration.md:267` 的「B=9」应为「B=10」（registry / `prereg:443` / STATUS 三处均为 10） | 该行在 prereg 的**冻结切片**内（`bench/freeze_digest.py:29` 的 `§1–§9`），按 `bench/preregistration.md:458-462` 任何改动都算**新一轮**，需重算指纹 + 在「轮次记录」追加一行 + 旧轮数据标 void | 不阻塞本阶段（A=1 三处一致）；但 M4b 前必须处理，否则冻结文档与 registry 自相矛盾 |
| 2 | ~~`references/01-landscape.md:69` 的「B=9」应改为 10~~ **已处理（2026-10-28，用户批准）** | 01 不是冻结件，不需新一轮 | — 已闭合；同时把下游 13 条 `01:N`（N>68）引用整体 +2 重切 |
| 3 | `human_interventions` 三口径 (i)/(ii)/(iii) 选哪一个（`prereg:408`） | 口径是价值判断（严/中/宽），没有实测能替用户选 | M4b 首跑 |
| 4 | `***` soft 分支复现要用哪个 tutorial 派生 | 需先试一次 `blockMesh` 才知道能否稳定触发，属 M1 工作量 | M1 |

